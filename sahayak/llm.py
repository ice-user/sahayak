"""LLM call plumbing shared by the agent: transient-error retry, streaming with tool-call delta merging,
and <think> stripping for streamed text.

Nothing here knows about schemes or the guard; the agent decides what to do with the reply.
"""
from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from types import SimpleNamespace as NS
from typing import Any, Callable

log = logging.getLogger("sahayak.llm")

RETRY_DELAYS = (1.0, 3.0)                      # seconds before retry 1 and retry 2
TRANSIENT_STATUS = frozenset({429, 500, 502, 503, 504})
NEVER_RETRY_STATUS = frozenset({400, 401, 403, 404})
_TRANSIENT_CLASS_NAMES = frozenset({
    "APIConnectionError", "APITimeoutError", "TimeoutException", "ReadTimeout", "ConnectTimeout", "ConnectError",
    "RemoteProtocolError", "ReadError", "TimeoutError", "ConnectionError"})
_TRANSIENT_TEXT = re.compile(
    r"temporar|unavailable|overloaded|timed?\s*out|timeout|connection\s+(?:error|reset|refused|aborted)|"
    r"rate.?limit|too many requests|try again later|bad gateway|gateway time", re.I)


class TurnCancelled(Exception):
    """The consumer went away (closed tab, newer message): abort the turn; the agent rolls its history back."""


_NO_STREAM_MODELS: set = set()  # models whose provider rejected streaming in this process


def _status_of(exc: BaseException) -> int | None:
    status = getattr(exc, "status_code", None)
    if status is None:
        status = getattr(getattr(exc, "response", None), "status_code", None)
    return status if isinstance(status, int) else None


def is_transient(exc: BaseException) -> bool:
    """True for errors worth retrying: 429/500/502/503/504, timeouts, connection errors and 'temporarily
    unavailable' style messages. Never for 400/401/403/404 (or any other 4xx) or for cancellation."""
    if isinstance(exc, TurnCancelled):
        return False
    status = _status_of(exc)
    if status is not None:
        if status in NEVER_RETRY_STATUS:
            return False
        if status in TRANSIENT_STATUS:
            return True
        if 400 <= status < 500:
            return False
    if isinstance(exc, (TimeoutError, ConnectionError)):
        return True
    if any(c.__name__ in _TRANSIENT_CLASS_NAMES for c in type(exc).__mro__):
        return True
    return bool(_TRANSIENT_TEXT.search(str(exc)))


def wait(delay: float, cancelled: Callable[[], bool] | None) -> None:
    """Sleep `delay` seconds in short slices, raising TurnCancelled as soon as `cancelled()` is true.
    The check also runs once before sleeping, so a cancelled turn never starts another call."""
    end = time.monotonic() + delay
    while True:
        if cancelled is not None and cancelled():
            raise TurnCancelled()
        remaining = end - time.monotonic()
        if remaining <= 0:
            return
        time.sleep(min(remaining, 0.1))


class ThinkFilter:
    """Incremental <think>...</think> remover for streamed text.

    feed(chunk) returns the text that is safe to show. Text inside a think block is dropped; a possible tag
    split across chunks ("<thi" + "nk>") is held back until it resolves; a block that opens is buffered until its
    closing tag, and if the stream ends first the rest is discarded (never shown). A stray "</think>" (the model
    leaked reasoning without an opening tag) is dropped; what was already shown cannot be taken back, and the final
    `answer` event, built with agent.clean_answer, replaces the streamed text.
    """
    OPEN, CLOSE = "<think>", "</think>"

    def __init__(self) -> None:
        self._buf = ""
        self._in_think = False

    @staticmethod
    def _partial_suffix(text: str, *tags: str) -> int:
        """Length of the longest suffix of `text` that is a proper prefix of one of `tags`."""
        best = 0
        for tag in tags:
            for n in range(min(len(tag) - 1, len(text)), 0, -1):
                if text.endswith(tag[:n]):
                    best = max(best, n)
                    break
        return best

    def feed(self, chunk: str) -> str:
        self._buf += chunk
        out: list[str] = []
        while True:
            if self._in_think:
                i = self._buf.find(self.CLOSE)
                if i < 0:
                    keep = self._partial_suffix(self._buf, self.CLOSE)
                    self._buf = self._buf[len(self._buf) - keep:]
                    break
                self._buf = self._buf[i + len(self.CLOSE):]
                self._in_think = False
                continue
            o, c = self._buf.find(self.OPEN), self._buf.find(self.CLOSE)
            hits = [(i, tag) for i, tag in ((o, self.OPEN), (c, self.CLOSE)) if i >= 0]
            if hits:
                i, tag = min(hits)
                out.append(self._buf[:i])
                self._buf = self._buf[i + len(tag):]
                self._in_think = tag == self.OPEN
                continue
            keep = self._partial_suffix(self._buf, self.OPEN, self.CLOSE)
            out.append(self._buf[:len(self._buf) - keep])
            self._buf = self._buf[len(self._buf) - keep:]
            break
        return "".join(out)

    def flush(self) -> str:
        """End of stream: held-back text that never became a tag is shown; an unclosed think block is dropped."""
        rest, self._buf = ("" if self._in_think else self._buf), ""
        self._in_think = False
        return rest


@dataclass
class Reply:
    """A normalised model reply (streamed or not)."""
    content: str = ""
    tool_calls: list = field(default_factory=list)   # objects with .id and .function.name / .function.arguments
    tokens: int | None = None                         # provider-reported total_tokens, None if it did not say
    streamed: bool = False
    ttft_s: float | None = None                       # seconds to the first content delta (streamed calls only)
    retries: int = 0
    fell_back: bool = False                           # streaming was rejected / broke before any token


class _Slot:
    __slots__ = ("id", "name", "args")

    def __init__(self) -> None:
        self.id, self.name, self.args = "", "", ""


def _merge_tool_delta(slots: list[_Slot], by_index: dict[Any, _Slot], tc: Any) -> None:
    """Merge one streamed tool-call delta into its slot. Calls are keyed by `index`; the id usually arrives only in
    the first chunk, the name too (repeated names are not doubled), and arguments are concatenated. Providers that
    omit `index` (or reuse 0 for every call) are told apart by a new non-empty id."""
    idx = getattr(tc, "index", None)
    fn = getattr(tc, "function", None)
    tc_id = getattr(tc, "id", None) or ""
    name = getattr(fn, "name", None) or ""
    args = getattr(fn, "arguments", None) or ""
    slot = by_index.get(idx) if idx is not None else (slots[-1] if slots else None)
    if slot is not None and tc_id and slot.id and tc_id != slot.id:
        slot = None                                    # a different call reusing the same index
    if slot is None:
        slot = _Slot()
        slots.append(slot)
    if idx is not None:
        by_index[idx] = slot                           # later chunks of a re-used index continue the newest call
    slot.id = slot.id or tc_id
    if name and name != slot.name:
        slot.name = slot.name + name if slot.name else name
    slot.args += args if isinstance(args, str) else ""


def consume_stream(stream: Any, on_text: Callable[[str], None], started: float,
                   mark_emitted: Callable[[], None] | None = None) -> Reply:
    """Drain an OpenAI-style chunk iterator into a Reply, calling `on_text(delta)` for each content delta.
    Usage may arrive in a final chunk (with empty `choices`) or never."""
    parts: list[str] = []
    slots: list[_Slot] = []
    by_index: dict[Any, _Slot] = {}
    reply = Reply(streamed=True)
    try:
        for chunk in stream:
            usage = getattr(chunk, "usage", None)
            total = getattr(usage, "total_tokens", None) if usage is not None else None
            if isinstance(total, int):
                reply.tokens = total
            choices = getattr(chunk, "choices", None) or []
            if not choices:
                continue
            delta = getattr(choices[0], "delta", None)
            if delta is None:
                continue
            text = getattr(delta, "content", None)
            if isinstance(text, str) and text:
                if reply.ttft_s is None:
                    reply.ttft_s = round(time.time() - started, 3)
                parts.append(text)
                if mark_emitted:
                    mark_emitted()
                on_text(text)
            for tc in getattr(delta, "tool_calls", None) or []:
                _merge_tool_delta(slots, by_index, tc)
    finally:
        close = getattr(stream, "close", None)
        if callable(close):
            try:
                close()
            except Exception:  # noqa: BLE001 - closing is best effort
                pass
    reply.content = "".join(parts)
    reply.tool_calls = [NS(id=s.id or f"call_{n + 1}", type="function", function=NS(name=s.name, arguments=s.args))
                        for n, s in enumerate(slots) if s.name]
    return reply


def _from_response(resp: Any) -> Reply:
    msg = resp.choices[0].message
    usage = getattr(resp, "usage", None)
    total = getattr(usage, "total_tokens", None)
    return Reply(content=msg.content or "", tool_calls=list(getattr(msg, "tool_calls", None) or []),
                 tokens=total if isinstance(total, int) else None)


def complete(client: Any, kwargs: dict, *, stream: bool, on_text: Callable[[str], None] | None = None,
             cancelled: Callable[[], bool] | None = None, delays: tuple[float, ...] = RETRY_DELAYS,
             on_retry: Callable[[int, BaseException, float], None] | None = None) -> Reply:
    """One logical LLM call: streaming if asked, retrying transient failures, falling back to non-streaming.

    - transient error (see is_transient): wait `delays[n]` (cancellable) and try again, at most len(delays) times
    - streaming rejected (e.g. 400) or broken before the first token: that call is repeated without streaming
    - error after tokens were already handed to `on_text`: raised as is (a retry would duplicate the text)
    - 401/403/404 and other 4xx are never retried
    """
    model_key = kwargs.get("model")
    use_stream = stream and on_text is not None and model_key not in _NO_STREAM_MODELS
    fell_back = False
    retries = 0
    emitted = [False]

    def mark() -> None:
        emitted[0] = True

    while True:
        started = time.time()
        try:
            if use_stream:
                resp = client.chat.completions.create(**kwargs, stream=True)
                if hasattr(resp, "choices"):        # provider ignored stream=True and sent a whole reply
                    reply = _from_response(resp)
                else:
                    reply = consume_stream(resp, on_text, started, mark)
            else:
                reply = _from_response(client.chat.completions.create(**kwargs))
            reply.retries, reply.fell_back = retries, fell_back
            return reply
        except TurnCancelled:
            raise
        except Exception as exc:  # noqa: BLE001 - classified below, re-raised when not retryable
            if emitted[0]:
                raise
            transient = is_transient(exc)
            if use_stream:
                # streaming is switched off for the rest of this call; a non-transient failure (typically "stream not
                # supported") costs no retry, since it is a fallback rather than a repeat, except for auth failures
                use_stream, fell_back = False, True
                status = _status_of(exc)
                if not transient and status not in (401, 403, 404, 410):
                    # remember it: later calls to this model skip the doomed streaming attempt (saves a round trip)
                    _NO_STREAM_MODELS.add(model_key)
                    log.warning("streaming failed (%s %s: %s); using non-streaming for model %s from now on",
                                type(exc).__name__, status, str(exc)[:160], model_key)
                    continue
            if not transient or retries >= len(delays):
                raise
            delay = delays[retries]
            retries += 1
            log.warning("transient LLM error (%s), retry %d in %.1fs", type(exc).__name__, retries, delay)
            if on_retry:
                on_retry(retries, exc, delay)
            wait(delay, cancelled)
