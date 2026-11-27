"""Tool-calling agent loop over any OpenAI-compatible chat API.

Works with OpenAI, Gemini (OpenAI-compatible endpoint), Groq, OpenRouter,
or a local Ollama server. Configure with environment variables:

  LLM_BASE_URL   e.g. https://generativelanguage.googleapis.com/v1beta/openai/
  LLM_API_KEY    your key ("ollama" for local Ollama)
  LLM_MODEL      e.g. gemini-2.5-flash, llama-3.3-70b-versatile, qwen2.5:7b
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from .guard import hosts_of, neutralize_urls, violations
from .lang import (EMPTY_ANSWER_MESSAGES, FIELD_LABELS, GUARD_FALLBACK_ASK, MAX_FALLBACK_QUESTIONS, GUARD_FALLBACK_NO_SCHEMES, GUARD_FALLBACK_WITH_SCHEMES,
                   MAX_STEPS_MESSAGES, detect_session_language, reply_language_hint)
from .llm import RETRY_DELAYS, Reply, ThinkFilter, TurnCancelled, complete  # noqa: F401 (TurnCancelled re-exported)
from .privacy import mask_pii
from .topic_guard import (MODES, TopicBlocked, TopicGate, classify, env_topic_mode,
                          env_topic_timeout, greeting_lang_hint, rules_check)
from .topics import reply_text, scope_prompt_section
from .llm_options import env_extra_body, model_extra_body  # noqa: F401 (env_extra_body re-exported)
from .tools import TOOL_SCHEMAS, Toolbox

log = logging.getLogger("sahayak.agent")

PROMPT_INTRO = "You are Sahayak, an assistant that helps people in India find government welfare schemes they can get.\n"

TOOL_GUIDANCE = """How to use the tools (every extra tool call makes the user wait):
- If the user's message contains personal facts (age, gender, family, income, BPL card, occupation, ...), call check_eligibility FIRST, right away, with those facts and without scheme_ids: it checks every scheme at once. Do not call search_schemes first.
- Use search_schemes only for a topic question with no personal facts, or to look a scheme up by name.
- Never call get_scheme_details for a scheme that check_eligibility already returned: eligible items already include benefits, documents, how_to_apply and source_url. Use it only for a scheme you have no data on, when the user asks about it.
- Call at most one tool per step unless you truly need more. After the tool result, write the answer."""

RULES = """Rules you must follow:
1. Never decide eligibility yourself. Always call check_eligibility, and only say someone is eligible if the tool returned that scheme under "eligible".
2. Only pass facts the user actually stated. Never guess age, income, BPL status or anything else.
3. If the tool returns "need_info", ask short, simple questions for the missing facts (at most 3 at a time), starting with the facts that matter for the schemes most relevant to what the user asked. Ask at most 2 rounds of questions; after that, give your answer with what you know. If schemes are already "eligible", tell the user about them even while asking about others. Some schemes belong to one state: if "state" is among the missing facts, ask which state or union territory the user lives in, and pass it as the official name ("Uttar Pradesh", not "UP").
4. {style_rule}
5. Mention caveats the tool returns, and that state governments often add to the central amount, so the final amount can differ.
6. Reply in the same language and script the user wrote in (Hindi, Tamil, Hinglish, English, ...). Keep scheme names in English in brackets.
7. If nothing matches, say so plainly and suggest the local Gram Panchayat, municipal office or myscheme.gov.in. Do not invent schemes.
8. For a scheme under "not_eligible", say plainly that the user does not qualify. Then read that scheme's "caveats": if one says the person may still qualify another way, mention it briefly and say it must be checked with the official body. Example: "You don't qualify for the 70+ card, but you may still be covered by regular PM-JAY, so check on the Ayushman app." Never present a not_eligible scheme as available.
9. Aadhaar, PAN and phone numbers are removed from user messages for privacy and appear as "[number removed]". Never ask for them; you do not need them.
10. Every answer is machine-checked: describing a scheme as available when check_eligibility did not return it under "eligible" will be rejected. Use only links that came from the tools (source_url) or official gov.in sites.
"""

STYLE_RULES = {
    "full": ("For each eligible scheme give: what they get, key documents, how to apply, and the source link from "
             "the tool."),
    "brief": ("Keep the whole reply under about 120 words, with no headings and no introduction. Write one line per "
              "eligible scheme: the scheme name (in English) and what they get, in a few words. Mention key caveats "
              "in a few words. If facts are missing, end with at most 3 short follow-up questions. The app shows "
              "documents, how to apply and links to the user automatically as cards, so do NOT list them unless the "
              "user asks."),
}
ANSWER_STYLES = tuple(STYLE_RULES)
BRIEF_MAX_TOKENS = 700  # room for a short answer even if a model spends a few tokens on preamble


def build_system_prompt(style: str = "full", prefix: str = "", scope: bool = False) -> str:
    """System prompt for an answer style ("full" for CLI/MCP, "brief" for the web app); `prefix` is prepended
    verbatim (env LLM_SYSTEM_PREFIX, e.g. "detailed thinking off" for some reasoning models). `scope` appends the
    topical scope section (on whenever the topic guard is not "off")."""
    if style not in STYLE_RULES:
        raise ValueError(f"answer_style must be one of {ANSWER_STYLES}, got {style!r}")
    parts = [PROMPT_INTRO, TOOL_GUIDANCE, "", RULES.format(style_rule=STYLE_RULES[style])]
    if scope:
        parts += ["", scope_prompt_section()]
    body = "\n".join(parts)
    return f"{prefix.strip()}\n\n{body}" if prefix and prefix.strip() else body


SYSTEM_PROMPT = build_system_prompt("full")


@dataclass
class Trace:
    """Per-turn record of every step, for debugging and evals."""
    steps: list[dict] = field(default_factory=list)

    def add(self, kind: str, **data):
        self.steps.append({"t": round(time.time(), 3), "kind": kind, **data})

    def tool_calls(self) -> list[dict]:
        return [s for s in self.steps if s["kind"] == "tool_call"]

    def llm_steps(self) -> list[dict]:
        return [s for s in self.steps if s["kind"] == "llm"]

    @property
    def llm_calls(self) -> int:
        """How many model calls this turn took (retries after provider errors are not counted)."""
        return len(self.llm_steps())

    @property
    def topic(self) -> str | None:
        """Topic verdict of this turn (on_topic / off_topic / jailbreak / greeting), None when the guard was off."""
        for s in reversed(self.steps):
            if s["kind"] == "topic_guard":
                return s["verdict"]
        return None

    @property
    def ttft_s(self) -> float | None:
        """Seconds from the start of the turn to the first streamed token, None if nothing was streamed."""
        for s in self.steps:
            if s["kind"] == "first_token":
                return s["since_start_s"]
        return None


NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"
NVIDIA_DEFAULT_MODEL = "nvidia/nemotron-3.5-super-vl-120b-a12b"


def resolve_config() -> tuple[str | None, str, str]:
    """(base_url, api_key, model). LLM_* variables win; otherwise NVIDIA_API_KEY selects NVIDIA's API."""
    if os.environ.get("LLM_API_KEY") or os.environ.get("LLM_BASE_URL"):
        return (os.environ.get("LLM_BASE_URL"), os.environ.get("LLM_API_KEY", "missing"),
                os.environ.get("LLM_MODEL", "gemini-2.5-flash"))
    if os.environ.get("NVIDIA_API_KEY"):
        return (NVIDIA_BASE_URL, os.environ["NVIDIA_API_KEY"],
                os.environ.get("LLM_MODEL") or os.environ.get("NVIDIA_MODEL") or NVIDIA_DEFAULT_MODEL)
    return None, "missing", os.environ.get("LLM_MODEL", "gemini-2.5-flash")


def make_client(**kwargs):
    """OpenAI-compatible client for the configured provider; extra kwargs (timeout, max_retries) pass through."""
    from openai import OpenAI
    base_url, api_key, _ = resolve_config()
    return OpenAI(base_url=base_url, api_key=api_key, **kwargs)


EventHandler = Callable[[str, dict[str, Any]], None]
"""Receives (kind, data) for kind in tool_call / tool_result / answer while a turn runs."""

_THINK = re.compile(r"<think>.*?</think>", re.S)
_THINK_OPEN = re.compile(r"<think>.*", re.S)  # reasoning that never closes (e.g. cut off by max_tokens)


def clean_answer(text: str) -> str:
    """Remove reasoning-model output that must not reach the user: closed <think>...</think> blocks, an unclosed
    <think>... tail, and a leaked reasoning prefix that ends with a stray </think>."""
    text = _THINK.sub("", text or "")
    text = _THINK_OPEN.sub("", text)
    if "</think>" in text:
        text = text.rsplit("</think>", 1)[1]
    return text.strip()


def env_stream_enabled() -> bool:
    """Streaming is on unless LLM_STREAM=0 (also "false"/"off"/"no")."""
    return os.environ.get("LLM_STREAM", "1").strip().lower() not in ("0", "false", "off", "no")


def default_trace_dir() -> str | None:
    """Traces hold user messages: write them only when SAHAYAK_TRACES=1."""
    return "traces" if os.environ.get("SAHAYAK_TRACES") == "1" else None


GUARD_NOTE = ("[Automated check, not from the user] Your last reply described {names} as available, but "
              "check_eligibility has not confirmed that. Call check_eligibility with the facts the user stated if you "
              "have not yet, then answer again describing as available ONLY schemes it returned under \"eligible\". "
              "Do not mention this note.")
EMPTY_NOTE = ("[Automated check, not from the user] Your last reply was empty. Reply to the user's last message "
              "now, in their language, without hidden reasoning.")


def _parse_json(raw: Any, default: Any) -> Any:
    try:
        return json.loads(raw) if isinstance(raw, str) else (raw if raw is not None else default)
    except json.JSONDecodeError:
        return default


def _source_urls(obj: Any) -> list[str]:
    """Every "source_url" string found anywhere in a (parsed) tool result."""
    found: list[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == "source_url" and isinstance(v, str):
                found.append(v)
            else:
                found += _source_urls(v)
    elif isinstance(obj, list):
        for v in obj:
            found += _source_urls(v)
    return found


class Agent:
    """One conversation.

    guard             run the deterministic answer check (sahayak/guard.py) on every final answer
    max_tokens        passed to the model when set (answer_style "brief" defaults to BRIEF_MAX_TOKENS)
    max_history_turns send only the last N user turns (whole turns, so tool call/result pairs stay intact; the
                      system prompt is always kept). The full history is still stored.
    answer_style      "full" (CLI default: benefits, documents, how to apply, link) or "brief" (server default:
                      about 120 words; documents and how-to-apply are shown as cards by the UI)
    stream            stream the final answer as `token` events (default: env LLM_STREAM, on unless "0"); only used
                      when chat() gets an on_event callback. Falls back to a normal call if streaming fails.
    extra_body        dict passed to chat.completions.create(extra_body=...) (default: env LLM_EXTRA_BODY)
    system_prefix     text prepended to the system prompt (default: env LLM_SYSTEM_PREFIX)
    retry_delays      seconds to wait before each retry of a transient provider error (default 1 s, 3 s)
    topic_guard       "off" | "prompt" | "classifier" (default: env TOPIC_GUARD, else "classifier"); see
                      sahayak/topic_guard.py. Off-topic / greeting / jailbreak turns are answered with a canned
                      localized text and are not kept in the history.
    topic_client / topic_model / topic_timeout_s
                      the classifier's client (default: the main client), model (default: env TOPIC_GUARD_MODEL, else
                      the main model) and timeout (default: env TOPIC_GUARD_TIMEOUT_S, else 4 s)
    `verdicts` maps scheme_id -> eligible / need_info / not_eligible from the latest check_eligibility that covered it.
    Tool results are cached per conversation: the same tool and arguments return the earlier result.
    """

    def __init__(self, client=None, model: str | None = None, toolbox: Toolbox | None = None,
                 max_steps: int = 8, trace_dir: str | None = None, guard: bool = True,
                 max_tokens: int | None = None, max_history_turns: int | None = None,
                 answer_style: str = "full", stream: bool | None = None, extra_body: dict | None = None,
                 system_prefix: str | None = None, retry_delays: tuple[float, ...] = RETRY_DELAYS,
                 topic_guard: str | None = None, topic_client=None, topic_model: str | None = None,
                 topic_timeout_s: float | None = None):
        self.client = client or make_client(max_retries=0)  # transient errors are retried by sahayak.llm, not twice
        self.model = model or resolve_config()[2]
        self.tools = toolbox or Toolbox()
        self.max_steps = max_steps
        self.answer_style = answer_style
        prefix = os.environ.get("LLM_SYSTEM_PREFIX", "") if system_prefix is None else system_prefix
        self.topic_mode = env_topic_mode() if topic_guard is None else topic_guard
        if self.topic_mode not in MODES:
            raise ValueError(f"topic_guard must be one of {MODES}, got {self.topic_mode!r}")
        self.topic_client = topic_client or self.client
        self.topic_model = topic_model or os.environ.get("TOPIC_GUARD_MODEL", "").strip() or self.model
        self.topic_timeout_s = topic_timeout_s or env_topic_timeout()
        self.messages: list[dict] = [{"role": "system", "content": build_system_prompt(
            answer_style, prefix, scope=self.topic_mode != "off")}]
        self.trace_dir = Path(trace_dir) if trace_dir else None
        self.guard = guard
        self.max_tokens = max_tokens or (BRIEF_MAX_TOKENS if answer_style == "brief" else None)
        self.max_history_turns = max_history_turns
        self.stream = env_stream_enabled() if stream is None else stream
        self.extra_body = model_extra_body(self.model) if extra_body is None else (extra_body or None)
        self.retry_delays = retry_delays
        self.verdicts: dict[str, str] = {}
        self.missing: dict[str, list[str]] = {}  # scheme_id -> facts the latest check_eligibility still needed
        self.source_hosts: set[str] = set()
        self._turn_starts: list[int] = []
        self._tool_cache: dict[str, str] = {}
        self._lang_hint = ""
        self._cancelled: Callable[[], bool] | None = None
        self._before_answer: Callable[[], None] | None = None

    def chat(self, user_message: str, on_event: EventHandler | None = None,
             cancelled: Callable[[], bool] | None = None) -> tuple[str, Trace]:
        """Run one user turn. `on_event(kind, data)` is called as the turn progresses:
        tool_call {id, name, arguments}, tool_result {id, name, result}, token {delta} (streamed text of the final
        answer, only when streaming is on) and finally answer {content}, which is authoritative: it is the guarded
        text and replaces any tokens. `cancelled()` is polled between provider retries (raise TurnCancelled).
        If the turn fails (or `on_event` raises, e.g. to cancel), the history is rolled back so the
        conversation never holds a dangling tool call.

        Topic guard (see sahayak/topic_guard.py): greetings, jailbreak attempts and off-topic messages are answered
        with a canned localized text and leave the history untouched. With mode "classifier" and unsure rules, a
        small classifier runs in parallel with this turn: events are held back until it says on_topic, and an
        off_topic verdict replaces the whole turn by the redirect (`on_event` may then be called from another thread)."""
        if self.topic_mode == "off":
            return self._chat_core(user_message, on_event, cancelled, Trace())
        safe = mask_pii(user_message)
        last = self._last_assistant_text()
        decision = rules_check(safe, last)
        if decision is not None and decision.verdict in ("greeting", "jailbreak"):
            return self._canned_turn(user_message, safe, decision, on_event)
        if decision is None and self.topic_mode == "classifier":
            return self._chat_gated(user_message, safe, last, on_event, cancelled)
        trace = Trace()
        trace.add("topic_guard", verdict="on_topic", layer="rules" if decision else "prompt",
                  reason=decision.reason if decision else "unsure; the system prompt scope rules apply",
                  latency_s=0.0)
        return self._chat_core(user_message, on_event, cancelled, trace)

    def _last_assistant_text(self) -> str | None:
        for m in reversed(self.messages):
            if m.get("role") == "assistant" and isinstance(m.get("content"), str) and m["content"].strip() \
                    and not m.get("tool_calls"):
                return m["content"]
        return None

    def _topic_language(self, safe_message: str, greeting: bool = False) -> str:
        lang = detect_session_language(self.messages + [{"role": "user", "content": safe_message}])
        if greeting and lang == "en":
            lang = greeting_lang_hint(safe_message) or lang
        return lang

    def _canned_turn(self, user_message: str, safe: str, decision, on_event: EventHandler | None) -> tuple[str, Trace]:
        """Greeting or jailbreak decided by the rules: no LLM call, nothing added to the history."""
        t0 = time.time()
        greeting = decision.verdict == "greeting"
        lang = self._topic_language(safe, greeting)
        text = reply_text(decision.kind if greeting else "jailbreak", lang)
        trace = Trace()
        trace.add("user", content=safe)
        trace.add("topic_guard", verdict=decision.verdict, layer="rules", reason=decision.reason,
                  latency_s=round(time.time() - t0, 4))
        trace.add("answer", content=text, llm_calls=0)
        self._save(trace)
        if on_event is not None:
            on_event("answer", {"content": text})
        return text, trace

    def _chat_gated(self, user_message: str, safe: str, last: str | None, on_event: EventHandler | None,
                    cancelled: Callable[[], bool] | None) -> tuple[str, Trace]:
        """The main turn and the classifier run at the same time; see TopicGate."""
        trace = Trace()
        lang = self._topic_language(safe)
        gate = TopicGate(on_event, trace, lambda r: reply_text(r.verdict if r.verdict == "jailbreak" else "off_topic",
                                                              lang), self.topic_timeout_s)
        gate.start(lambda: classify(self.topic_client, self.topic_model, safe, last, self.topic_timeout_s))
        self._before_answer = gate.wait_verdict
        stop = (lambda: gate.blocked or bool(cancelled and cancelled()))
        try:
            return self._chat_core(user_message, gate.emit, stop, trace, listening=on_event is not None)
        except TurnCancelled as exc:
            if not gate.blocked:
                raise
            gate.raise_stored()
            result = exc.result if isinstance(exc, TopicBlocked) else gate.result
            text = reply_text("jailbreak" if result.verdict == "jailbreak" else "off_topic", lang)
            trace.add("answer", content=text, llm_calls=trace.llm_calls, stopped="topic_" + result.verdict)
            self._save(trace)
            return text, trace
        finally:
            self._before_answer = None
            gate.close()

    def _chat_core(self, user_message: str, on_event: EventHandler | None, cancelled: Callable[[], bool] | None,
                   trace: Trace, listening: bool | None = None) -> tuple[str, Trace]:
        checkpoint = (len(self.messages), dict(self.verdicts), set(self.source_hosts), list(self._turn_starts),
                      dict(self.missing))
        self._cancelled = cancelled
        try:
            return self._run_turn(user_message, on_event, trace, on_event is not None if listening is None else listening)
        except BaseException:
            n, self.verdicts, self.source_hosts, self._turn_starts, self.missing = checkpoint
            del self.messages[n:]
            raise
        finally:
            self._cancelled = None

    def _window(self) -> list[dict]:
        """What is sent to the model: the system prompt (plus this turn's reply-language hint) and the history."""
        system = self.messages[0]
        if self._lang_hint:
            system = {**system, "content": f"{system['content'].rstrip()}\n\n{self._lang_hint}"}
        if self.max_history_turns and len(self._turn_starts) > self.max_history_turns:
            return [system] + self.messages[self._turn_starts[-self.max_history_turns]:]
        return [system] + self.messages[1:]

    def _call_tool(self, name: str, arguments: str) -> tuple[str, bool]:
        """(result JSON, from_cache). Identical tool name + arguments return the cached result; errors are not cached."""
        parsed = _parse_json(arguments, None)
        key = f"{name}:{json.dumps(parsed, sort_keys=True, ensure_ascii=False)}" if isinstance(parsed, dict) else None
        if key is not None and key in self._tool_cache:
            return self._tool_cache[key], True
        result = self.tools.call(name, arguments)
        if key is not None and "error" not in (_parse_json(result, {}) if result.startswith("{") else {}):
            self._tool_cache[key] = result
        return result, False

    def _record_tool_result(self, name: str, result: str) -> None:
        parsed = _parse_json(result, None)
        self.source_hosts |= hosts_of(*_source_urls(parsed))
        if name == "check_eligibility" and isinstance(parsed, dict) and "error" not in parsed:
            for bucket in ("eligible", "need_info", "not_eligible"):
                for item in parsed.get(bucket) or []:
                    self.verdicts[item["scheme_id"]] = bucket
                    self.missing[item["scheme_id"]] = list(item.get("missing_fields") or []) if bucket == "need_info" else []

    def _make_sink(self, emit: EventHandler, trace: Trace, t_turn: float):
        """(on_text, finish) turning raw content deltas into `token` events: <think> blocks are removed, and if the
        text so far would already offer an unverified scheme the stream stops (the guarded `answer` follows)."""
        think, state = ThinkFilter(), {"text": "", "stopped": False}

        def push(visible: str) -> None:
            if not visible or state["stopped"]:
                return
            if not state["text"]:
                visible = visible.lstrip()
                if not visible:
                    return
            if self.guard and violations(state["text"] + visible, self.verdicts):
                state["stopped"] = True
                trace.add("guard", action="stream_stopped", reason="unverified_scheme")
                return
            state["text"] += visible
            if trace.ttft_s is None:
                trace.add("first_token", since_start_s=round(time.time() - t_turn, 3))
            emit("token", {"delta": visible})

        return (lambda raw: push(think.feed(raw))), (lambda: push(think.flush()))

    def _call_llm(self, emit: EventHandler, trace: Trace, t_turn: float, stream_tokens: bool) -> Reply:
        kwargs: dict[str, Any] = {"model": self.model, "messages": self._window(), "tools": TOOL_SCHEMAS,
                                  "temperature": 0.2}
        if self.max_tokens:
            kwargs["max_tokens"] = self.max_tokens
        if self.extra_body:
            kwargs["extra_body"] = self.extra_body
        on_text, finish = self._make_sink(emit, trace, t_turn) if stream_tokens else (None, None)

        def on_retry(attempt: int, exc: BaseException, delay: float) -> None:
            trace.add("llm_retry", attempt=attempt, error=type(exc).__name__,
                      status=getattr(exc, "status_code", None), delay_s=delay)

        t0 = time.time()
        reply = complete(self.client, kwargs, stream=stream_tokens, on_text=on_text, cancelled=self._cancelled,
                         delays=self.retry_delays, on_retry=on_retry)
        if finish is not None and reply.streamed and not reply.tool_calls:
            finish()
        tokens, estimated = reply.tokens, False
        if tokens is None and reply.streamed:  # provider sent no usage chunk: rough estimate, flagged as such
            chars = len(json.dumps(kwargs["messages"], ensure_ascii=False, default=str)) + len(reply.content) + \
                sum(len(tc.function.arguments or "") for tc in reply.tool_calls)
            tokens, estimated = chars // 4, True
        trace.add("llm", latency_s=round(time.time() - t0, 2), tokens=tokens, streamed=reply.streamed,
                  ttft_s=reply.ttft_s, retries=reply.retries, stream_fallback=reply.fell_back,
                  **({"tokens_estimated": True} if estimated else {}))
        return reply

    def _run_turn(self, user_message: str, on_event: EventHandler | None, trace: Trace,
                  listening: bool) -> tuple[str, Trace]:
        emit: EventHandler = on_event or (lambda kind, data: None)
        t_turn = time.time()
        safe_message = mask_pii(user_message)
        self._turn_starts.append(len(self.messages))
        self.messages.append({"role": "user", "content": safe_message})
        trace.add("user", content=safe_message)
        lang = detect_session_language(self.messages)
        self._lang_hint = reply_language_hint(lang)
        guard_retries, empty_retries = 1, 1
        stream_tokens = bool(self.stream and listening)  # no listener, no point streaming
        ephemeral: list[dict] = []  # corrective notes and rejected answers: sent once, never kept in history

        for _ in range(self.max_steps):
            msg = self._call_llm(emit, trace, t_turn, stream_tokens)

            if not msg.tool_calls:
                answer = clean_answer(msg.content)
                if not answer:
                    if empty_retries:
                        empty_retries -= 1
                        stream_tokens = False  # tokens already shown would be glued to the retry's: let `answer` deliver it
                        trace.add("guard", action="retry", reason="empty_answer")
                        note = {"role": "user", "content": EMPTY_NOTE}
                        self.messages.append(note)
                        ephemeral.append(note)
                        continue
                    return self._finish(trace, EMPTY_ANSWER_MESSAGES[lang], emit, ephemeral, save=False,
                                        stopped="empty_answer")
                if self.guard:
                    bad = violations(answer, self.verdicts)
                    if bad and guard_retries:
                        guard_retries -= 1
                        stream_tokens = False
                        trace.add("guard", action="retry", reason="unverified_scheme", schemes=bad)
                        names = ", ".join(self.tools.schemes[s].name if s in self.tools.schemes else s for s in bad)
                        pair = [{"role": "assistant", "content": answer},
                                {"role": "user", "content": GUARD_NOTE.format(names=names)}]
                        self.messages.extend(pair)
                        ephemeral.extend(pair)
                        continue
                    if bad:
                        trace.add("guard", action="fallback", reason="unverified_scheme", schemes=bad,
                                  rejected_answer=answer)
                        return self._finish(trace, self._fallback(lang), emit, ephemeral)
                    cleaned = neutralize_urls(answer, self.source_hosts)
                    if cleaned != answer:
                        trace.add("guard", action="urls_removed")
                        answer = cleaned
                return self._finish(trace, answer, emit, ephemeral)

            self.messages.append({
                "role": "assistant", "content": msg.content or "",
                "tool_calls": [{"id": tc.id, "type": "function",
                                "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                               for tc in msg.tool_calls],
            })
            for tc in msg.tool_calls:
                emit("tool_call", {"id": tc.id, "name": tc.function.name,
                                   "arguments": _parse_json(tc.function.arguments, {})})
                result, cached = self._call_tool(tc.function.name, tc.function.arguments)
                self._record_tool_result(tc.function.name, result)
                trace.add("tool_call", name=tc.function.name, arguments=tc.function.arguments, result=result,
                          **({"cached": True} if cached else {}))
                self.messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})
                emit("tool_result", {"id": tc.id, "name": tc.function.name,
                                     "result": _parse_json(result, {"error": "unreadable tool result"})})

        return self._finish(trace, MAX_STEPS_MESSAGES[lang], emit, ephemeral, save=False, stopped="max_steps")

    def _fallback(self, lang: str) -> str:
        """Safe answer that lists only schemes the rule engine confirmed for this conversation."""
        names = [self.tools.schemes[s].name for s, v in self.verdicts.items()
                 if v == "eligible" and s in self.tools.schemes]
        base = GUARD_FALLBACK_WITH_SCHEMES[lang].format(names="; ".join(names)) if names else GUARD_FALLBACK_NO_SCHEMES[lang]
        ask = self._missing_facts_question(lang)
        return f"{base}\n\n{ask}" if ask else base

    def _missing_facts_question(self, lang: str) -> str:
        """Question naming the facts the rule engine still needs (most-needed first, at most 3); "" if none."""
        counts: dict[str, int] = {}
        for sid, verdict in self.verdicts.items():
            if verdict == "need_info":
                for f in self.missing.get(sid, []):
                    counts[f] = counts.get(f, 0) + 1
        top = sorted(counts, key=lambda f: -counts[f])[:MAX_FALLBACK_QUESTIONS]  # stable: ties keep tool order
        if not top:
            return ""
        labels = [FIELD_LABELS.get(f, {}).get(lang) or FIELD_LABELS.get(f, {}).get("en") or f.replace("_", " ") for f in top]
        return GUARD_FALLBACK_ASK[lang].format(facts=", ".join(labels))

    def _finish(self, trace: Trace, answer: str, emit: EventHandler, ephemeral: list[dict],
                save: bool = True, **extra) -> tuple[str, Trace]:
        if self._before_answer is not None:
            self._before_answer()  # topic guard: hold the answer until the classifier has spoken (may raise TopicBlocked)
        if ephemeral:
            self.messages[:] = [m for m in self.messages if not any(m is e for e in ephemeral)]
        if save:  # a step-limit / empty-answer apology is not part of the conversation history
            self.messages.append({"role": "assistant", "content": answer})
        trace.add("answer", content=answer, llm_calls=trace.llm_calls, **extra)
        self._save(trace)
        emit("answer", {"content": answer})
        return answer, trace

    def _save(self, trace: Trace):
        if not self.trace_dir:
            return
        self.trace_dir.mkdir(parents=True, exist_ok=True)
        with open(self.trace_dir / "traces.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(trace.steps, ensure_ascii=False) + "\n")
