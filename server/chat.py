"""Turn an AgentRun into the SSE event stream defined in docs/API.md."""
from __future__ import annotations

import json
import logging
import time
from typing import Any, AsyncIterator

from .config import redact
from .streaming import FINISHED, PING, AgentRun, trace_stats
from .suggestions import missing_fields, suggestions_for

log = logging.getLogger("sahayak.chat")

ERROR_MESSAGES = {
    429: "The AI service is busy right now. Please try again in a moment.",
    401: "The AI service is not configured correctly. Please contact the administrator.",
    403: "The AI service is not configured correctly. Please contact the administrator.",
}
DEFAULT_LLM_ERROR = "The AI service had a problem. Please try again."
NOT_CONFIGURED = "The AI provider is not configured on this server."


def sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def error_event(code: str, message: str) -> str:
    return sse("error", {"message": message, "code": code})


def llm_error_message(exc: BaseException) -> str:
    """User-facing text for a provider failure; never includes the provider's own message."""
    return ERROR_MESSAGES.get(getattr(exc, "status_code", None), DEFAULT_LLM_ERROR)


async def event_stream(run: AgentRun, session_id: str, language: str) -> AsyncIterator[str]:
    """session -> tool_call/tool_result* -> answer -> suggestions? -> done, or ... -> error."""
    started = time.monotonic()
    latest_check: Any = None
    finished = False
    yield sse("session", {"session_id": session_id})
    try:
        async for kind, data in run.events():
            if kind == PING:
                yield ": ping\n\n"
            elif kind == FINISHED:
                finished = True
                options = suggestions_for(missing_fields(latest_check), language)
                if options:
                    yield sse("suggestions", {"options": options})
                llm_calls, tokens = trace_stats(data)
                latency = round(time.monotonic() - started, 1)
                log.info("turn ok session=%s lang=%s llm_calls=%d tokens=%d latency_s=%s",
                         session_id[:6], language, llm_calls, tokens, latency)
                done = {"latency_s": latency, "llm_calls": llm_calls, "tokens": tokens}
                topic = getattr(data, "topic", None)
                if topic:
                    done["topic"] = topic
                yield sse("done", done)
            else:
                if kind == "tool_result" and data["name"] == "check_eligibility":
                    latest_check = data["result"]
                yield sse(kind, data)
    except Exception as exc:
        log.error("turn failed session=%s error=%s status=%s detail=%s", session_id[:6], type(exc).__name__,
                  getattr(exc, "status_code", None), redact(str(exc))[:200])
        yield error_event("llm_error", llm_error_message(exc))
    finally:
        if not finished:
            run.cancel()  # client went away or we failed: stop the worker at its next step
