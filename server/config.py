"""Server settings, read from environment variables."""
from __future__ import annotations

import os
from dataclasses import dataclass, field

from sahayak.topic_guard import env_topic_mode, env_topic_timeout

SECRET_MARKERS = ("KEY", "TOKEN", "SECRET", "PASSWORD")


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


def _float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return default


def _style(value: str) -> str:
    value = value.strip().lower()
    return value if value in ("brief", "full") else "brief"


@dataclass(frozen=True)
class Settings:
    allowed_origins: list[str] = field(default_factory=lambda: ["http://localhost:3000"])
    rate_limit_per_10min: int = 20         # per client IP
    global_chat_per_min: int = 30          # across all clients; protects the LLM bill
    trust_proxy: bool = False
    trusted_proxy_hops: int = 1            # proxies in front of us; the client is the Nth entry from the RIGHT of X-Forwarded-For
    session_ttl_s: float = 30 * 60
    max_sessions: int = 1000
    max_message_chars: int = 2000
    max_body_bytes: int = 16 * 1024
    max_turns_per_session: int = 20        # user messages per conversation
    history_turns: int = 12                # last N user turns are sent to the model
    max_tokens: int = 700                  # per LLM call (brief answers; raise it for reasoning models that think inline)
    answer_style: str = "brief"            # "brief" (cards show documents / how to apply) or "full"
    max_steps: int = 6                     # LLM calls per user message
    max_concurrent_runs: int = 8           # turns in flight at once (each holds a worker thread and an LLM call)
    busy_wait_s: float = 2.0               # how long a new message waits for a cancelled run to unwind
    llm_timeout_s: float = 30.0
    keepalive_s: float = 15.0
    enable_docs: bool = False              # /docs, /redoc, /openapi.json
    topic_guard: str | None = None         # "off" | "prompt" | "classifier"; None = the Agent's default (env TOPIC_GUARD)
    topic_guard_model: str | None = None   # classifier model; None = env TOPIC_GUARD_MODEL, else the main model
    topic_timeout_s: float | None = None   # classifier timeout; None = env TOPIC_GUARD_TIMEOUT_S, else 4 s

    @classmethod
    def from_env(cls) -> "Settings":
        production = os.environ.get("ENV", "").lower() == "production"
        origins = os.environ.get("ALLOWED_ORIGINS")
        if production and not (origins and origins.strip()):
            raise RuntimeError("ALLOWED_ORIGINS must be set when ENV=production (comma-separated frontend origins)")
        origins = origins or "http://localhost:3000"
        return cls(
            allowed_origins=[o.strip().rstrip("/") for o in origins.split(",") if o.strip().rstrip("/")],  # browsers send Origin without a trailing slash
            rate_limit_per_10min=_int("RATE_LIMIT_PER_10MIN", 20),
            global_chat_per_min=_int("GLOBAL_CHAT_PER_MIN", 30),
            trust_proxy=os.environ.get("TRUST_PROXY") == "1",
            trusted_proxy_hops=max(1, _int("TRUSTED_PROXY_HOPS", 1)),
            max_turns_per_session=_int("MAX_TURNS_PER_SESSION", 20),
            history_turns=_int("HISTORY_TURNS", 12),
            max_tokens=_int("MAX_TOKENS", 700),
            answer_style=_style(os.environ.get("ANSWER_STYLE", "brief")),
            max_steps=_int("MAX_STEPS", 6),
            max_concurrent_runs=_int("MAX_CONCURRENT_RUNS", 8),
            llm_timeout_s=_float("LLM_TIMEOUT_S", 30.0),
            enable_docs=os.environ.get("ENABLE_DOCS") == "1",
            topic_guard=env_topic_mode(),
            topic_guard_model=os.environ.get("TOPIC_GUARD_MODEL", "").strip() or None,
            topic_timeout_s=env_topic_timeout(),
        )


def redact(text: str) -> str:
    """Mask any secret-looking environment value that appears in `text` (for logs)."""
    for name, value in os.environ.items():
        if value and len(value) >= 8 and any(m in name.upper() for m in SECRET_MARKERS):
            text = text.replace(value, "***")
    return text
