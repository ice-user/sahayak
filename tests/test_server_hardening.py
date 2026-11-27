"""Server hardening: proxy trust, budgets, body caps, abandoned runs, language stickiness, prod hygiene."""
import asyncio
import json
import threading
import time
from pathlib import Path
from types import SimpleNamespace as NS

import httpx
import pytest
from fastapi.testclient import TestClient

from sahayak.agent import Agent
from sahayak.tools import Toolbox
from server.config import Settings
from server.main import create_app, make_agent
from server.ratelimit import RateLimiter
from tests.test_server import FakeClient, WIDOW, chat, make_app, parse_sse, text_msg, tool_msg

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def toolbox():
    return Toolbox(search_mode="bm25")


# ---- item 9: proxy trust, global budget, pruning
def test_spoofed_left_most_forwarded_for_does_not_bypass_the_limit(toolbox):
    app, _ = make_app(toolbox, [text_msg("a")] * 60, rate_limit_per_10min=2, trust_proxy=True,
                      global_chat_per_min=1000)
    with TestClient(app) as tc:
        codes = [tc.post("/api/chat", json={"message": "hi"},
                         headers={"X-Forwarded-For": f"10.0.0.{i}, 203.0.113.7"}).status_code for i in range(50)]
    assert codes.count(200) == 2 and codes.count(429) == 48


def test_trusted_proxy_hops_selects_nth_from_right(toolbox):
    app, _ = make_app(toolbox, [text_msg("a")] * 10, rate_limit_per_10min=1, trust_proxy=True,
                      trusted_proxy_hops=2, global_chat_per_min=1000)
    with TestClient(app) as tc:
        codes = [tc.post("/api/chat", json={"message": "hi"},
                         headers={"X-Forwarded-For": f"spoof{i}, 198.51.100.9, 10.1.1.1"}).status_code for i in range(3)]
        other = tc.post("/api/chat", json={"message": "hi"},
                        headers={"X-Forwarded-For": "spoof, 198.51.100.10, 10.1.1.1"}).status_code
    assert codes == [200, 429, 429] and other == 200


def test_settings_proxy_hops_default_and_env(monkeypatch):
    monkeypatch.delenv("TRUSTED_PROXY_HOPS", raising=False)
    assert Settings.from_env().trusted_proxy_hops == 1
    monkeypatch.setenv("TRUSTED_PROXY_HOPS", "3")
    monkeypatch.setenv("GLOBAL_CHAT_PER_MIN", "7")
    s = Settings.from_env()
    assert s.trusted_proxy_hops == 3 and s.global_chat_per_min == 7
    monkeypatch.delenv("GLOBAL_CHAT_PER_MIN")
    assert Settings.from_env().global_chat_per_min == 30


def test_global_budget_returns_503_with_retry_after(toolbox):
    app, _ = make_app(toolbox, [text_msg("a")] * 5, global_chat_per_min=2, trust_proxy=True)
    with TestClient(app) as tc:
        codes = [tc.post("/api/chat", json={"message": "hi"}, headers={"X-Forwarded-For": f"1.1.1.{i}"})
                 for i in range(3)]
    assert [r.status_code for r in codes] == [200, 200, 503]
    assert int(codes[2].headers["retry-after"]) >= 1 and "detail" in codes[2].json()


def test_rate_limiter_prunes_idle_keys():
    now = [0.0]
    limiter = RateLimiter(5, window_s=10, clock=lambda: now[0])
    for key in "abc":
        assert limiter.check(key) is None
    assert limiter.size() == 3
    now[0] = 100.0
    limiter.check("d")
    assert limiter.size() == 1


# ---- item 10: cost caps
def test_turn_cap_per_session_gives_friendly_error(toolbox):
    app, _ = make_app(toolbox, [text_msg("a"), text_msg("b"), text_msg("c")], max_turns_per_session=2)
    with TestClient(app) as tc:
        sid = dict(parse_sse(chat(tc, "one").text))["session"]["session_id"]
        chat(tc, "two", sid)
        r = chat(tc, "three", sid)
    events = dict(parse_sse(r.text))
    assert r.status_code == 200 and events["session"]["session_id"] == sid
    assert events["error"]["code"] == "session_limit" and "new" in events["error"]["message"].lower()


def test_turn_cap_message_is_localized(toolbox):
    app, _ = make_app(toolbox, [text_msg("a")], max_turns_per_session=1)
    with TestClient(app) as tc:
        sid = dict(parse_sse(chat(tc, "मुझे पेंशन चाहिए").text))["session"]["session_id"]
        err = dict(parse_sse(chat(tc, "फिर से", sid).text))["error"]["message"]
    assert any("ऀ" <= c <= "ॿ" for c in err)


def test_body_over_16kb_is_rejected_before_parsing(toolbox):
    app, client = make_app(toolbox, [text_msg("a")])
    with TestClient(app) as tc:
        r = tc.post("/api/chat", content=b'{"message": "' + b"x" * 17000 + b'"}',
                    headers={"Content-Type": "application/json"})
        assert client.sent == []  # never reached the model
        ok = chat(tc, "hi")
    assert r.status_code == 413 and "detail" in r.json()
    assert ok.status_code == 200


def test_streamed_body_without_content_length_is_capped(toolbox):
    app, _ = make_app(toolbox, [text_msg("a")])

    def chunks():
        yield b'{"message": "'
        for _ in range(20):
            yield b"x" * 1000
        yield b'"}'

    with TestClient(app) as tc:
        r = tc.post("/api/chat", content=chunks(), headers={"Content-Type": "application/json"})
    assert r.status_code == 413


def test_production_agent_caps_tokens_steps_and_history(toolbox):
    client = FakeClient([text_msg("a")])
    s = Settings()
    assert (s.max_tokens, s.max_steps, s.max_turns_per_session, s.max_body_bytes) == (700, 6, 20, 16 * 1024)
    assert s.answer_style == "brief"
    agent = make_agent(client, toolbox, s)
    assert agent.max_tokens == 700 and agent.answer_style == "brief" and agent.max_steps == 6 and agent.max_history_turns == s.history_turns
    app = create_app(toolbox=toolbox, settings=s, llm_client=client)
    with TestClient(app) as tc:
        assert chat(tc, "hello").status_code == 200
    assert client.sent[0]["max_tokens"] == 700


# ---- item 11: abandoned runs, release ordering, concurrency cap
class SlowClient(FakeClient):
    """First call blocks until `gate` is set (a stuck provider call)."""

    def __init__(self, script):
        super().__init__(script)
        self.gate = threading.Event()
        self.started = threading.Event()
        self.block_next = True

    def _create(self, **kwargs):
        if self.block_next:
            self.block_next = False
            self.started.set()
            self.gate.wait(10)
        return super()._create(**kwargs)


def _app_with(client, **settings):
    return create_app(lambda tb: Agent(client=client, model="fake", toolbox=tb), Toolbox(search_mode="bm25"),
                      Settings(**settings))


async def _post(ac, message, sid=None):
    return await ac.post("/api/chat", json={"message": message, **({"session_id": sid} if sid else {})})


def test_retry_after_abandoned_request_cancels_the_old_run_and_proceeds():
    client = SlowClient([text_msg("late first"), text_msg("second answer")])
    app = _app_with(client, busy_wait_s=3.0)

    async def scenario():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as ac:
            sid = app.state.sessions.get_or_create(None).id
            task = asyncio.create_task(_post(ac, "first", sid))
            await asyncio.get_running_loop().run_in_executor(None, client.started.wait, 3)
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            threading.Timer(0.3, client.gate.set).start()          # the provider call finally returns
            r = await _post(ac, "retry", sid)
            return r

    r = asyncio.run(scenario())
    assert r.status_code == 200
    events = dict(parse_sse(r.text))
    assert events["answer"]["content"] == "second answer"


def test_busy_session_that_cannot_unwind_still_gets_409():
    client = SlowClient([text_msg("late")])
    app = _app_with(client, busy_wait_s=0.3)

    async def scenario():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as ac:
            sid = app.state.sessions.get_or_create(None).id
            task = asyncio.create_task(_post(ac, "first", sid))
            await asyncio.get_running_loop().run_in_executor(None, client.started.wait, 3)
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            t0 = time.monotonic()
            r = await _post(ac, "retry", sid)
            client.gate.set()
            return r, time.monotonic() - t0

    r, waited = asyncio.run(scenario())
    assert r.status_code == 409 and 0.25 <= waited < 2.5


def test_instant_retry_after_llm_error_is_never_409(toolbox):
    """The session must be released BEFORE the terminal error event reaches the client."""
    script = []
    for _ in range(26):
        script += [RuntimeError("boom"), text_msg("ok")]
    app, _ = make_app(toolbox, script, global_chat_per_min=1000, rate_limit_per_10min=1000)
    with TestClient(app) as tc:
        sid = dict(parse_sse(chat(tc, "hi").text))["session"]["session_id"]  # first script item raises
        for _ in range(25):
            ok = chat(tc, "again", sid)
            assert ok.status_code == 200, ok.text
            err = chat(tc, "fail", sid)
            assert [n for n, _ in parse_sse(err.text)] == ["session", "error"]


def test_global_concurrency_cap_returns_503():
    client = SlowClient([text_msg("late"), text_msg("fine")])
    app = _app_with(client, max_concurrent_runs=1)

    async def scenario():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as ac:
            first = asyncio.create_task(_post(ac, "first"))
            await asyncio.get_running_loop().run_in_executor(None, client.started.wait, 3)
            second = await _post(ac, "second")
            client.gate.set()
            await first
            third = await _post(ac, "third")
            return second, third

    second, third = asyncio.run(scenario())
    assert second.status_code == 503 and int(second.headers["retry-after"]) >= 1
    assert third.status_code == 200


def test_llm_timeout_is_30_seconds():
    import server.main as m
    assert m.LLM_TIMEOUT_S == 30


# ---- item 12: sticky language
def test_hinglish_chips_survive_english_one_word_replies(toolbox):
    app, _ = make_app(toolbox, [text_msg("Aur kuch?"), tool_msg("check_eligibility", WIDOW), text_msg("ok")])
    with TestClient(app) as tc:
        sid = dict(parse_sse(chat(tc, "meri maa 62 saal ki vidhwa hain").text))["session"]["session_id"]
        events = dict(parse_sse(chat(tc, "female", sid).text))
    assert events["suggestions"]["options"][0] == "Haan, BPL card hai"


def test_language_can_still_upgrade(toolbox):
    app, _ = make_app(toolbox, [text_msg("?"), tool_msg("check_eligibility", WIDOW), text_msg("ok")])
    with TestClient(app) as tc:
        sid = dict(parse_sse(chat(tc, "my mother is old").text))["session"]["session_id"]
        events = dict(parse_sse(chat(tc, "वो 62 साल की हैं", sid).text))
    assert events["suggestions"]["options"][0] == "हाँ, बीपीएल कार्ड है"


# ---- item 13: tool errors don't leak internals over SSE
def test_bad_tool_arguments_do_not_leak_python_internals(toolbox):
    app, _ = make_app(toolbox, [tool_msg("check_eligibility", {"profile": {}, "bogus": 1}), text_msg("Could you tell me more?")])
    with TestClient(app) as tc:
        r = chat(tc, "hi")
    result = dict(parse_sse(r.text))["tool_result"]["result"]
    for leak in ("TypeError", "Toolbox", "keyword", "unexpected"):
        assert leak not in r.text
    assert "bogus" in result["error"]


# ---- item 14: prod hygiene
@pytest.mark.parametrize("path", ["/docs", "/redoc", "/openapi.json"])
def test_docs_disabled_by_default_and_enabled_by_flag(toolbox, path):
    app, _ = make_app(toolbox, [])
    with TestClient(app) as tc:
        assert tc.get(path).status_code == 404
    app, _ = make_app(toolbox, [], enable_docs=True)
    with TestClient(app) as tc:
        assert tc.get(path).status_code == 200


def test_health_exposes_only_ok_and_scheme_count(toolbox):
    app, _ = make_app(toolbox, [])
    with TestClient(app) as tc:
        assert tc.get("/api/health").json() == {"ok": True, "schemes": 10}


def test_security_headers(toolbox):
    app, _ = make_app(toolbox, [], trust_proxy=True)
    with TestClient(app) as tc:
        plain = tc.get("/api/health")
        behind_https = tc.get("/api/health", headers={"X-Forwarded-Proto": "https"})
        err = tc.post("/api/chat", json={})
    for r in (plain, behind_https, err):
        assert r.headers["x-content-type-options"] == "nosniff"
        assert r.headers["referrer-policy"] == "no-referrer"
    assert "strict-transport-security" not in plain.headers
    assert "max-age" in behind_https.headers["strict-transport-security"]


def test_hsts_not_trusted_from_header_without_trust_proxy(toolbox):
    app, _ = make_app(toolbox, [])
    with TestClient(app) as tc:
        assert "strict-transport-security" not in tc.get("/api/health", headers={"X-Forwarded-Proto": "https"}).headers


def test_production_requires_allowed_origins(monkeypatch):
    monkeypatch.setenv("ENV", "production")
    monkeypatch.delenv("ALLOWED_ORIGINS", raising=False)
    with pytest.raises(RuntimeError, match="ALLOWED_ORIGINS"):
        Settings.from_env()
    monkeypatch.setenv("ALLOWED_ORIGINS", "https://sahayak.example")
    assert Settings.from_env().allowed_origins == ["https://sahayak.example"]
    monkeypatch.setenv("ENV", "development")
    monkeypatch.delenv("ALLOWED_ORIGINS")
    assert Settings.from_env().allowed_origins == ["http://localhost:3000"]


def test_deploy_files():
    docker = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "--limit-concurrency 100" in docker and "--timeout-keep-alive 5" in docker and "HEALTHCHECK" in docker
    ignore = (ROOT / ".dockerignore").read_text(encoding="utf-8").split()
    for entry in ("data/candidates", "data/distill*", "data/*.bak"):
        assert entry in ignore
    render = (ROOT / "render.yaml").read_text(encoding="utf-8")
    assert "ENV" in render and "production" in render and "TRUSTED_PROXY_HOPS" in render


def test_allowed_origins_ignore_trailing_slash(monkeypatch):
    """A pasted 'https://app.vercel.app/' must still match the browser's Origin header (sent without a slash)."""
    from server.config import Settings
    monkeypatch.setenv("ALLOWED_ORIGINS", "https://a.vercel.app/, https://b.example.com ,/")
    assert Settings.from_env().allowed_origins == ["https://a.vercel.app", "https://b.example.com"]
