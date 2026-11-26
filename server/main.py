"""FastAPI app: chat over SSE, scheme catalogue, session reset, health."""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Callable

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field, field_validator

from sahayak.agent import Agent, default_trace_dir, make_client, resolve_config
from sahayak.lang import upgrade_language
from sahayak.tools import Toolbox

from .chat import NOT_CONFIGURED, error_event, event_stream, sse
from .config import Settings
from .phrases import SESSION_LIMIT
from .ratelimit import RateLimiter
from .sessions import SessionStore, StoreFull
from .streaming import AgentRun
from .suggestions import detect_language, has_letters

log = logging.getLogger("sahayak.server")
SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"}
LLM_TIMEOUT_S = 30.0
HSTS = "max-age=31536000; includeSubDomains"


class ChatRequest(BaseModel):
    session_id: str | None = Field(None, max_length=128)
    message: str

    @field_validator("message")
    @classmethod
    def _message_length(cls, v: str) -> str:
        v = v.strip()
        if not 1 <= len(v) <= Settings.max_message_chars:
            raise ValueError(f"message must be 1-{Settings.max_message_chars} characters")
        return v


class ResetRequest(BaseModel):
    session_id: str


def client_ip(request: Request, settings: Settings | bool) -> str:
    """The rate-limit key. Without TRUST_PROXY: the TCP peer. With it: the entry `trusted_proxy_hops` from the
    RIGHT of X-Forwarded-For, i.e. the address our own proxy saw. The left-most entries are client-controlled
    and are never used. Fewer entries than hops means the header is not from our proxy: fall back to the peer."""
    trust, hops = (settings.trust_proxy, settings.trusted_proxy_hops) if isinstance(settings, Settings) else (settings, 1)
    if trust:
        parts = [p.strip() for p in request.headers.get("x-forwarded-for", "").split(",") if p.strip()]
        if len(parts) >= hops:
            return parts[-hops]
    return request.client.host if request.client else "unknown"


class BodyTooLarge(Exception):
    pass


class BodyLimitMiddleware:
    """Reject request bodies over `max_bytes` with 413: by Content-Length before reading, and by counting
    streamed bytes (chunked uploads have no Content-Length)."""

    def __init__(self, app, max_bytes: int):
        self.app, self.max_bytes = app, max_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        declared = dict(scope["headers"]).get(b"content-length")
        if declared is not None and declared.isdigit() and int(declared) > self.max_bytes:
            return await self._reject(send)
        seen, too_large = 0, False

        async def limited_receive():
            nonlocal seen, too_large
            message = await receive()
            if message["type"] == "http.request":
                seen += len(message.get("body", b""))
                if seen > self.max_bytes:
                    too_large = True
                    raise BodyTooLarge()
            return message

        async def guarded_send(message):
            if not too_large:  # once over the cap, whatever the framework answers (it may say 400) is replaced by 413
                await send(message)

        try:
            await self.app(scope, limited_receive, guarded_send)
        except BodyTooLarge:
            pass
        if too_large:
            await self._reject(send)

    async def _reject(self, send):
        await JSONResponse({"detail": "Request body too large."}, status_code=413)({"type": "http"}, None, send)


class SecurityHeadersMiddleware:
    """nosniff + no-referrer on every response; HSTS only when the request came in over https
    (directly, or via a proxy we trust)."""

    def __init__(self, app, trust_proxy: bool):
        self.app, self.trust_proxy = app, trust_proxy

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = dict(scope["headers"])
        https = scope.get("scheme") == "https" or (
            self.trust_proxy and headers.get(b"x-forwarded-proto", b"").split(b",")[-1].strip() == b"https")

        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                extra = [(b"x-content-type-options", b"nosniff"), (b"referrer-policy", b"no-referrer")]
                if https:
                    extra.append((b"strict-transport-security", HSTS.encode()))
                message = {**message, "headers": [*message.get("headers", []), *extra]}
            await send(message)

        await self.app(scope, receive, send_with_headers)


def make_agent(client, toolbox: Toolbox, settings: Settings) -> Agent:
    """The per-conversation agent with the production cost caps applied."""
    return Agent(client=client, toolbox=toolbox, max_steps=settings.max_steps, max_tokens=settings.max_tokens,
                 max_history_turns=settings.history_turns, trace_dir=default_trace_dir(),
                 answer_style=settings.answer_style, topic_guard=settings.topic_guard,
                 topic_model=settings.topic_guard_model, topic_timeout_s=settings.topic_timeout_s)


def create_app(agent_factory: Callable[[Toolbox], Agent] | None = None, toolbox: Toolbox | None = None,
               settings: Settings | None = None, llm_client=None) -> FastAPI:
    """Build the app. Tests inject `agent_factory` (called per new session with the shared Toolbox)
    or a fake `llm_client` (then the real make_agent caps apply)."""
    settings = settings or Settings.from_env()
    toolbox = toolbox or Toolbox(search_mode=os.environ.get("SAHAYAK_SEARCH"))
    injected = agent_factory is not None or llm_client is not None
    if not injected:
        log_startup_summary(settings, toolbox)
    if agent_factory is None:
        shared_client = llm_client or make_client(timeout=settings.llm_timeout_s, max_retries=0)  # retries live in sahayak.llm (visible in the trace)
        agent_factory = lambda tb: make_agent(shared_client, tb, settings)  # noqa: E731

    store = SessionStore(lambda: agent_factory(toolbox), settings.session_ttl_s, settings.max_sessions)
    limiter = RateLimiter(settings.rate_limit_per_10min)
    global_limiter = RateLimiter(settings.global_chat_per_min, window_s=60.0)
    inflight = [0]
    public = {sid: s.model_dump(exclude={"rules", "ministry"}) for sid, s in toolbox.schemes.items()}

    docs = settings.enable_docs
    app = FastAPI(title="Sahayak API", version="1", docs_url="/docs" if docs else None,
                  redoc_url="/redoc" if docs else None, openapi_url="/openapi.json" if docs else None)
    app.state.sessions = store
    # innermost first: body cap, CORS (so 413s carry CORS headers), security headers outermost
    app.add_middleware(BodyLimitMiddleware, max_bytes=settings.max_body_bytes)
    app.add_middleware(CORSMiddleware, allow_origins=settings.allowed_origins,
                       allow_methods=["GET", "POST", "OPTIONS"], allow_headers=["Content-Type"])
    app.add_middleware(SecurityHeadersMiddleware, trust_proxy=settings.trust_proxy)

    @app.exception_handler(RequestValidationError)
    async def _bad_request(_: Request, exc: RequestValidationError) -> JSONResponse:
        problem = exc.errors()[0] if exc.errors() else {}
        field = ".".join(str(p) for p in problem.get("loc", ())[1:])
        msg = problem.get("msg", "invalid request").removeprefix("Value error, ")
        return JSONResponse({"detail": f"{field}: {msg}" if field else msg}, status_code=400)

    def busy_response(detail: str, retry_after: float) -> JSONResponse:
        return JSONResponse({"detail": detail}, status_code=503, headers={"Retry-After": str(max(1, int(retry_after)))})

    @app.post("/api/chat", response_model=None)
    async def chat(body: ChatRequest, request: Request) -> StreamingResponse | JSONResponse:
        ip = client_ip(request, settings)
        retry_after = limiter.check(ip)
        if retry_after is not None:
            log.warning("rate limited ip=%s", ip)
            return JSONResponse({"detail": "Too many requests. Please wait a few minutes and try again."},
                                status_code=429, headers={"Retry-After": str(int(retry_after))})
        retry_after = global_limiter.check("global")
        if retry_after is not None:
            log.warning("global chat budget exhausted")
            return busy_response("The service is very busy right now. Please try again in a minute.", retry_after)
        if not injected and not _provider_configured():
            return StreamingResponse(iter([error_event("llm_error", NOT_CONFIGURED)]),
                                     media_type="text/event-stream", headers=SSE_HEADERS)
        try:
            session = store.get_or_create(body.session_id)
        except StoreFull:
            return busy_response("Server is busy. Please try again shortly.", 5)

        if session.busy:
            # The previous run is probably abandoned (closed tab, dropped connection): cancel it and give it a
            # moment to unwind instead of locking the user out until the slow LLM call returns.
            if session.run is not None:
                session.run.cancel()
            deadline = asyncio.get_running_loop().time() + settings.busy_wait_s
            while session.busy and asyncio.get_running_loop().time() < deadline:
                await asyncio.sleep(0.02)
            if session.busy:
                return JSONResponse({"detail": "Still answering your previous message in this conversation. "
                                                "Please wait for it to finish."}, status_code=409)

        if has_letters(body.message):
            session.language = upgrade_language(session.language, detect_language(body.message))

        turns = sum(1 for m in session.agent.messages if m["role"] == "user")
        if turns >= settings.max_turns_per_session:
            text = SESSION_LIMIT.get(session.language, SESSION_LIMIT["en"])
            return StreamingResponse(iter([sse("session", {"session_id": session.id}),
                                           error_event("session_limit", text)]),
                                     media_type="text/event-stream", headers=SSE_HEADERS)
        if inflight[0] >= settings.max_concurrent_runs:
            return busy_response("Too many conversations are being answered right now. Please try again in a few seconds.", 5)

        session.busy = True
        inflight[0] += 1
        holder: dict[str, AgentRun] = {}

        def release() -> None:
            inflight[0] -= 1
            if session.run is holder.get("run"):
                session.busy = False
                session.run = None
                store.touch(session)

        run = AgentRun(session.agent, body.message, release, settings.keepalive_s)
        holder["run"] = session.run = run
        run.start()
        return StreamingResponse(event_stream(run, session.id, session.language),
                                 media_type="text/event-stream", headers=SSE_HEADERS)

    @app.get("/api/schemes")
    async def list_schemes() -> list[dict]:
        return list(public.values())

    @app.get("/api/schemes/{scheme_id}")
    async def get_scheme(scheme_id: str) -> dict:
        scheme = toolbox.schemes.get(scheme_id)
        if scheme is None:
            raise HTTPException(404, "Unknown scheme")
        return {**public[scheme_id], "rules": scheme.rules}

    @app.post("/api/session/reset")
    async def reset(body: ResetRequest) -> dict:
        store.reset(body.session_id)
        return {"ok": True}

    @app.head("/api/health", include_in_schema=False)  # uptime monitors (e.g. UptimeRobot free) probe with HEAD
    @app.get("/api/health")
    async def health() -> dict:
        return {"ok": True, "schemes": len(toolbox.schemes)}  # nothing about the model or provider is public

    return app


def _provider_configured() -> bool:
    base_url, api_key, _ = resolve_config()
    return api_key != "missing" or base_url is not None


def log_startup_summary(settings: Settings, toolbox: Toolbox) -> None:
    """One clear line about the provider (never the key itself), so a missing key shows up in the host's logs."""
    base_url, api_key, model = resolve_config()
    if api_key == "missing" and base_url is None:
        log.warning("NO LLM PROVIDER CONFIGURED: set NVIDIA_API_KEY (or LLM_BASE_URL / LLM_API_KEY / LLM_MODEL). "
                    "The API is up, but /api/chat will answer 'The AI provider is not configured on this server.'")
    else:
        log.info("LLM provider configured: base_url=%s model=%s", base_url or "(OpenAI default)", model)
    log.info("Sahayak API ready: schemes=%d search=%s topic_guard=%s answer_style=%s origins=%s",
             len(toolbox.schemes), os.environ.get("SAHAYAK_SEARCH") or "default", settings.topic_guard or "default",
             settings.answer_style, ",".join(settings.allowed_origins))


def _configure_logging() -> None:
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"),
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)  # request URLs only, but keep INFO quiet


_configure_logging()
app = create_app()
