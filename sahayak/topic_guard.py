"""Topical guardrail: keep Sahayak on government welfare schemes without adding latency.

Layers, cheapest first (scope itself lives in sahayak/topics.py):

  1. rules_check()   no LLM. greeting/thanks -> canned reply; obvious jailbreak -> redirect; scheme keywords,
                     questions about Sahayak, short follow-ups in an ongoing chat -> allow. Anything else: None
                     ("unsure"). The rules layer NEVER says off_topic: a weak keyword miss must not block anyone.
  2. classify()      small LLM call, only when the rules are unsure. Fail open: timeout / error / garbage -> on_topic.
  3. the main system prompt carries the scope too (sahayak/topics.py:scope_prompt_section).

Mode (env TOPIC_GUARD): "off" | "prompt" (layers 1 and 3) | "classifier" (default, layers 1-3).

TopicGate runs the classifier IN PARALLEL with the main agent turn. While the verdict is pending, the turn's events
(tool_call, tool_result, token) are buffered; on_topic flushes them in order, off_topic/jailbreak discards them,
sends the localized redirect as the answer and aborts the main turn (the agent rolls its history back).
"""
from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
import unicodedata
from dataclasses import dataclass
from typing import Any, Callable

from .llm_options import model_extra_body
from . import topics
from .llm import TurnCancelled

log = logging.getLogger("sahayak.topic")

MODES = ("off", "prompt", "classifier")
VERDICTS = ("on_topic", "off_topic", "jailbreak")
BLOCKING = frozenset({"off_topic", "jailbreak"})
DEFAULT_TIMEOUT_S = 4.0
MAX_USER_CHARS, MAX_ASSISTANT_CHARS = 700, 500
# A short reply is auto-allowed up to this many tokens; up to the larger bound when the assistant just asked a question.
SHORT_REPLY_TOKENS, ANSWER_TO_QUESTION_TOKENS = 5, 12


def env_topic_mode() -> str:
    """TOPIC_GUARD: off | prompt | classifier (default). A typo keeps the guard ON (with a warning)."""
    raw = os.environ.get("TOPIC_GUARD", "classifier").strip().lower() or "classifier"
    if raw not in MODES:
        log.warning("TOPIC_GUARD=%r is not one of %s; using 'classifier'", raw, MODES)
        return "classifier"
    return raw


def env_topic_timeout() -> float:
    try:
        value = float(os.environ.get("TOPIC_GUARD_TIMEOUT_S", DEFAULT_TIMEOUT_S))
    except ValueError:
        return DEFAULT_TIMEOUT_S
    return value if value > 0 else DEFAULT_TIMEOUT_S


@dataclass
class RuleDecision:
    verdict: str            # on_topic | greeting | jailbreak
    reason: str
    kind: str = ""          # for greeting: "hello" | "thanks"


@dataclass
class TopicResult:
    verdict: str            # on_topic | off_topic | jailbreak
    layer: str              # classifier
    reason: str = ""
    latency_s: float = 0.0
    fail_open: str = ""     # "" | timeout | error | unparseable


class TopicBlocked(TurnCancelled):
    """The classifier judged the message off-topic: abort the main turn (the agent rolls its history back)."""

    def __init__(self, result: TopicResult):
        super().__init__(result.verdict)
        self.result = result


# --- layer 1: rules ---------------------------------------------------------------------------------------------------
_ZERO_WIDTH = dict.fromkeys(map(ord, "​‌‍⁠﻿"))
_EDGE_PUNCT = ".,;:!?…\"'`()[]{}<>-_*~|/\\।॥“”‘’«»"


def normalise(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "").translate(_ZERO_WIDTH)
    text = text.replace("’", "'").replace("‘", "'")
    return re.sub(r"\s+", " ", text).strip().casefold()


def _has_letter(token: str) -> bool:
    return any(unicodedata.category(ch)[0] in "LMN" for ch in token)


def tokens_of(text: str) -> list[str]:
    """Whitespace tokens of the normalised text, edge punctuation removed, emoji / pure punctuation dropped."""
    out = []
    for raw in normalise(text).split(" "):
        tok = raw.strip(_EDGE_PUNCT)
        if tok and _has_letter(tok):
            out.append(tok)
    return out


def _latin_pattern(words: tuple[str, ...]) -> re.Pattern:
    alt = "|".join(sorted((re.escape(w) for w in words), key=len, reverse=True))
    return re.compile(rf"(?<![a-z0-9])(?:{alt})(?:s|es)?(?![a-z0-9])")


_LATIN_KW = _latin_pattern(topics.SCHEME_KEYWORDS_LATIN)
_JAILBREAK = [re.compile(p, re.I | re.S) for p in topics.JAILBREAK_PATTERNS]
_ABOUT_SELF = [re.compile(p, re.I) for p in topics.ABOUT_SELF_PATTERNS]


def has_scheme_keyword(text: str) -> bool:
    norm = normalise(text)
    return bool(_LATIN_KW.search(norm)) or any(k in norm for k in topics.SCHEME_KEYWORDS_NATIVE)


def looks_like_jailbreak(text: str) -> bool:
    norm = normalise(text)
    return any(p.search(norm) for p in _JAILBREAK)


def _greeting_kind(toks: list[str]) -> str:
    """"hello" / "thanks" when every token is greeting vocabulary and at least one is a real greeting, else ""."""
    if not toks or len(toks) > 6:
        return ""
    vocab = topics.GREETING_CORE | topics.THANKS_CORE | topics.GREETING_FILLER
    if not all(t in vocab for t in toks):
        return ""
    if any(t in topics.THANKS_CORE for t in toks):
        return "thanks"
    if any(t in topics.GREETING_CORE for t in toks):
        return "hello"
    return ""


def greeting_lang_hint(text: str) -> str | None:
    """A greeting written in Latin-script Hindi ("namaste", "dhanyavad") answers in Hinglish."""
    return "hinglish" if any(t in topics.HINGLISH_GREETING_WORDS for t in tokens_of(text)) else None


def asked_question(assistant_text: str | None) -> bool:
    return bool(assistant_text) and any(q in assistant_text[-400:] for q in ("?", "？", "؟"))


def rules_check(message: str, last_assistant: str | None = None) -> RuleDecision | None:
    """Deterministic pre-check. None means unsure (defer to the classifier or the main prompt).

    `last_assistant` is the previous assistant message, or None for the first turn of a conversation."""
    norm = normalise(message)
    if not norm:
        return None
    if looks_like_jailbreak(message):
        return RuleDecision("jailbreak", "jailbreak pattern")
    toks = tokens_of(message)
    kind = _greeting_kind(toks)
    if kind:
        return RuleDecision("greeting", f"greeting vocabulary ({kind})", kind)
    if has_scheme_keyword(message):
        return RuleDecision("on_topic", "scheme keyword")
    if any(p.search(norm) for p in _ABOUT_SELF):
        return RuleDecision("on_topic", "question about Sahayak")
    if last_assistant:  # an ongoing conversation: short replies answer the assistant
        suspicious = any(c in f" {norm} " for c in topics.OFFTOPIC_CUES)
        starts_like_request = bool(toks) and toks[0] in topics.REQUEST_STARTERS
        is_question = norm.endswith(("?", "？"))
        limit = ANSWER_TO_QUESTION_TOKENS if asked_question(last_assistant) else SHORT_REPLY_TOKENS
        if toks and len(toks) <= limit and not (suspicious or starts_like_request or is_question):
            return RuleDecision("on_topic", "short follow-up in an ongoing conversation")
    return None


# --- layer 2: LLM classifier ------------------------------------------------------------------------------------------
_THINK = re.compile(r"<think>.*?</think>|<think>.*", re.S)
_JSON = re.compile(r"\{[^{}]*\}", re.S)


def parse_verdict(raw: str) -> tuple[str, str] | None:
    """(verdict, reason) from the classifier's reply, tolerating <think> blocks, code fences and prose around the
    JSON. None when nothing usable is found."""
    text = _THINK.sub("", raw or "")
    if "</think>" in text:
        text = text.rsplit("</think>", 1)[1]
    for match in _JSON.finditer(text):
        try:
            obj = json.loads(match.group(0))
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict):
            continue
        verdict = str(obj.get("verdict", "")).strip().lower().replace("-", "_").replace(" ", "_")
        if verdict in VERDICTS:
            return verdict, str(obj.get("reason", ""))[:160]
    return None


def build_classifier_messages(message: str, last_assistant: str | None) -> list[dict]:
    last = (last_assistant or "").strip()
    context = last[-MAX_ASSISTANT_CHARS:] if last else "(none: this is the first message)"
    user = f"Previous assistant message:\n{context}\n\nUser's last message:\n{message.strip()[:MAX_USER_CHARS]}"
    return [{"role": "system", "content": topics.classifier_system_prompt()}, {"role": "user", "content": user}]


def classify(client: Any, model: str, message: str, last_assistant: str | None,
             timeout_s: float = DEFAULT_TIMEOUT_S) -> TopicResult:
    """One small LLM call. Never raises and never takes longer than `timeout_s`: timeout, provider error and an
    unparseable reply all FAIL OPEN (verdict on_topic, `fail_open` says why). `message` must already be PII-masked."""
    started = time.monotonic()
    box: dict[str, Any] = {}

    def call() -> None:
        try:
            kwargs: dict[str, Any] = dict(
                model=model, messages=build_classifier_messages(message, last_assistant), temperature=0,
                max_tokens=80, timeout=timeout_s)
            extra = model_extra_body(model)
            if extra:
                kwargs["extra_body"] = extra
            resp = client.chat.completions.create(**kwargs)
            box["raw"] = resp.choices[0].message.content or ""
        except BaseException as exc:  # noqa: BLE001 - classified below, never propagated
            box["error"] = exc

    worker = threading.Thread(target=call, name="topic-classifier", daemon=True)
    worker.start()
    worker.join(timeout_s)
    latency = round(time.monotonic() - started, 3)
    if worker.is_alive():
        log.warning("topic classifier timed out after %.1fs; allowing", timeout_s)
        return TopicResult("on_topic", "classifier", "classifier timed out", latency, "timeout")
    if "error" in box:
        status = getattr(box["error"], "status_code", None)
        log.warning("topic classifier failed (%s%s); allowing%s", type(box["error"]).__name__,
                    f" {status}" if status else "",
                    " - model retired or wrong name? set TOPIC_GUARD_MODEL" if status in (404, 410) else "")
        return TopicResult("on_topic", "classifier", f"classifier error: {type(box['error']).__name__}", latency,
                           "error")
    parsed = parse_verdict(box.get("raw", ""))
    if parsed is None:
        log.warning("topic classifier reply not parseable; allowing")
        return TopicResult("on_topic", "classifier", "unparseable classifier reply", latency, "unparseable")
    return TopicResult(parsed[0], "classifier", parsed[1], latency)


# --- parallel orchestration ---------------------------------------------------------------------------------------------
Forward = Callable[[str, dict], None]


class TopicGate:
    """Sits between a running agent turn and its event listener while the classifier is still thinking.

    states: pending -> allowed (flush buffered events, then pass events through) | blocked (drop them, send the
    redirect `answer`, make the next gate call raise TopicBlocked) | closed. The first resolution wins; a verdict
    that arrives after the safety wait has already allowed the turn is ignored.

    `forward` is the real listener (None when nobody listens). It may be called from the classifier's thread (flush
    / redirect), so it must be thread-safe, as server.streaming.AgentRun is.
    """

    def __init__(self, forward: Forward | None, trace: Any, redirect: Callable[[TopicResult], str],
                 timeout_s: float = DEFAULT_TIMEOUT_S):
        self._forward = forward
        self._trace = trace
        self._redirect = redirect
        self._timeout = timeout_s
        self._lock = threading.RLock()
        self._ready = threading.Event()
        self._buffer: list[tuple[str, dict]] = []
        self._step: dict | None = None
        self._exc: BaseException | None = None
        self.state = "pending"
        self.result: TopicResult | None = None

    # -- classifier side
    def start(self, run: Callable[[], TopicResult]) -> None:
        def work() -> None:
            try:
                result = run()
            except BaseException as exc:  # noqa: BLE001 - classify() never raises; belt and braces
                result = TopicResult("on_topic", "classifier", f"classifier error: {type(exc).__name__}", 0.0, "error")
            self.resolve(result)
        threading.Thread(target=work, name="topic-gate", daemon=True).start()

    def resolve(self, result: TopicResult) -> None:
        with self._lock:
            if self.state != "pending":
                return
            self.result = result
            data = {"verdict": result.verdict, "layer": result.layer, "reason": result.reason,
                    "latency_s": result.latency_s, "overlapped": True, "held_events": len(self._buffer)}
            if result.fail_open:
                data["fail_open"] = result.fail_open
            self._trace.add("topic_guard", **data)
            self._step = self._trace.steps[-1]
            if result.verdict in BLOCKING:
                self.state = "blocked"
                self._buffer.clear()
                self._send("answer", {"content": self._redirect(result)})
            else:
                self.state = "allowed"
                for kind, payload in self._buffer:
                    self._send(kind, payload)
                self._buffer.clear()
            self._ready.set()

    def _send(self, kind: str, data: dict) -> None:
        if self._forward is None or self._exc is not None:
            return
        try:
            self._forward(kind, data)
        except BaseException as exc:  # noqa: BLE001 - e.g. the consumer went away; surfaced on the main thread
            self._exc = exc

    # -- main-turn side
    @property
    def blocked(self) -> bool:
        return self.state == "blocked"

    def raise_stored(self) -> None:
        if self._exc is not None:
            exc, self._exc = self._exc, None
            raise exc

    def emit(self, kind: str, data: dict) -> None:
        """The agent's on_event while the gate is up."""
        with self._lock:
            self.raise_stored()
            if self.state == "blocked":
                raise TopicBlocked(self.result)  # type: ignore[arg-type]
            if self.state == "pending":
                self._buffer.append((kind, data))
                return
            if self.state == "allowed" and self._forward is not None:
                self._forward(kind, data)

    def wait_verdict(self) -> None:
        """Called by the agent just before it commits its final answer: hold until the verdict is in."""
        started = time.monotonic()
        if not self._ready.wait(self._timeout + 1.0):  # safety net: classify() has its own timeout
            self.resolve(TopicResult("on_topic", "classifier", "gate wait expired", self._timeout, "timeout"))
        waited = round(time.monotonic() - started, 3)
        with self._lock:
            if self._step is not None:
                self._step["main_wait_s"] = waited
            self.raise_stored()
            if self.state == "blocked":
                raise TopicBlocked(self.result)  # type: ignore[arg-type]

    def close(self) -> None:
        with self._lock:
            if self.state == "pending":
                self._buffer.clear()
            if self.state != "blocked":
                self.state = "closed"
