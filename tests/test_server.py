"""HTTP-level tests for the FastAPI backend, using a scripted fake LLM (never a real provider)."""
import asyncio
import json
import time
from types import SimpleNamespace as NS

import pytest
from fastapi.testclient import TestClient

from sahayak.agent import Agent
from sahayak.models import load_schemes
from sahayak.tools import Toolbox
from server.config import Settings
from server.main import create_app
from server.sessions import SessionStore
from server.streaming import Cancelled, AgentRun

WIDOW = {"profile": {"age": 62, "gender": "female", "marital_status": "widowed"}}


def tool_msg(name, args, call_id="c1"):
    return NS(content="", tool_calls=[NS(id=call_id, function=NS(name=name, arguments=json.dumps(args)))])


def text_msg(text):
    return NS(content=text, tool_calls=None)


class FakeClient:
    """Replays scripted messages (or raises scripted exceptions) and records what it was sent."""

    def __init__(self, script):
        self.script = list(script)
        self.sent = []
        self.chat = NS(completions=NS(create=self._create))

    def _create(self, **kwargs):
        self.sent.append({**kwargs, "messages": list(kwargs["messages"])})
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return NS(choices=[NS(message=item)], usage=NS(total_tokens=100))


@pytest.fixture(scope="module")
def toolbox():
    return Toolbox(search_mode="bm25")


def make_app(toolbox, script, **settings):
    client = FakeClient(script)
    app = create_app(lambda tb: Agent(client=client, model="fake", toolbox=tb), toolbox, Settings(**settings))
    return app, client


def parse_sse(text):
    events = []
    for block in text.strip().split("\n\n"):
        if block.startswith(":"):
            continue
        name, data = block.split("\n", 1)
        events.append((name.removeprefix("event: "), json.loads(data.removeprefix("data: "))))
    return events


def chat(tc, message, session_id=None):
    body = {"message": message, **({"session_id": session_id} if session_id else {})}
    return tc.post("/api/chat", json=body)


def test_event_order_and_payloads(toolbox):
    app, _ = make_app(toolbox, [tool_msg("check_eligibility", WIDOW), text_msg("Here is what you can get.")])
    with TestClient(app) as tc:
        r = chat(tc, "My mother is 62 and a widow")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
    events = parse_sse(r.text)
    assert [n for n, _ in events] == ["session", "tool_call", "tool_result", "answer", "suggestions", "done"]
    data = dict(events)
    assert data["session"]["session_id"]
    assert data["tool_call"] == {"id": "c1", "name": "check_eligibility", "arguments": WIDOW}
    assert data["tool_result"]["id"] == "c1" and data["tool_result"]["name"] == "check_eligibility"
    assert {"eligible", "need_info", "not_eligible"} <= data["tool_result"]["result"].keys()
    assert data["answer"] == {"content": "Here is what you can get."}
    assert data["suggestions"]["options"] == ["Yes, we have a BPL card", "No BPL card", "Not sure"]
    assert data["done"]["llm_calls"] == 2 and data["done"]["tokens"] == 200
    assert data["done"]["latency_s"] >= 0


def test_no_tool_call_means_no_suggestions(toolbox):
    app, _ = make_app(toolbox, [text_msg("Namaste! How can I help?")])
    with TestClient(app) as tc:
        names = [n for n, _ in parse_sse(chat(tc, "hello").text)]
    assert names == ["session", "answer", "done"]


@pytest.mark.parametrize("message, first_option", [
    ("मेरी माँ 62 साल की विधवा हैं", "हाँ, बीपीएल कार्ड है"),
    ("Meri maa 62 saal ki vidhwa hain", "Haan, BPL card hai"),
    ("என் அம்மா 62 வயது விதவை", "ஆம், பிபிஎல் அட்டை உள்ளது"),
    ("My mother is 62 and a widow", "Yes, we have a BPL card"),
])
def test_suggestions_follow_user_language(toolbox, message, first_option):
    app, _ = make_app(toolbox, [tool_msg("check_eligibility", WIDOW), text_msg("ok")])
    with TestClient(app) as tc:
        events = dict(parse_sse(chat(tc, message).text))
    assert events["suggestions"]["options"][0] == first_option


def test_language_sticks_when_reply_has_no_letters(toolbox):
    app, _ = make_app(toolbox, [text_msg("आपकी उम्र?"), tool_msg("check_eligibility", WIDOW), text_msg("ok")])
    with TestClient(app) as tc:
        sid = dict(parse_sse(chat(tc, "मुझे पेंशन चाहिए").text))["session"]["session_id"]
        events = dict(parse_sse(chat(tc, "62", sid).text))
    assert events["suggestions"]["options"][0] == "हाँ, बीपीएल कार्ड है"


def test_session_reuse_keeps_history_and_reset_clears_it(toolbox):
    app, client = make_app(toolbox, [text_msg("one"), text_msg("two"), text_msg("three")])
    with TestClient(app) as tc:
        sid = dict(parse_sse(chat(tc, "first").text))["session"]["session_id"]
        second = dict(parse_sse(chat(tc, "second", sid).text))
        assert second["session"]["session_id"] == sid
        roles = [m["role"] for m in client.sent[1]["messages"]]
        assert roles == ["system", "user", "assistant", "user"]

        assert tc.post("/api/session/reset", json={"session_id": sid}).json() == {"ok": True}
        third = dict(parse_sse(chat(tc, "third", sid).text))
        assert third["session"]["session_id"] != sid
        assert [m["role"] for m in client.sent[2]["messages"]] == ["system", "user"]


def test_reset_unknown_session_is_ok(toolbox):
    app, _ = make_app(toolbox, [])
    with TestClient(app) as tc:
        assert tc.post("/api/session/reset", json={"session_id": "nope"}).json() == {"ok": True}


def test_concurrent_message_on_same_session_is_rejected(toolbox):
    app, _ = make_app(toolbox, [text_msg("x")])
    with TestClient(app) as tc:
        session = app.state.sessions.get_or_create(None)
        session.busy = True
        r = chat(tc, "hi", session.id)
    assert r.status_code == 409 and "previous message" in r.json()["detail"]


def test_session_is_released_after_turn(toolbox):
    app, _ = make_app(toolbox, [text_msg("a")])
    with TestClient(app) as tc:
        sid = dict(parse_sse(chat(tc, "hi").text))["session"]["session_id"]
        deadline = time.time() + 2
        while app.state.sessions.get_or_create(sid).busy and time.time() < deadline:
            time.sleep(0.01)
        assert not app.state.sessions.get_or_create(sid).busy


@pytest.mark.parametrize("body", [
    {"message": ""}, {"message": "   "}, {"message": "x" * 2001}, {}, {"message": 5},
    {"message": "hi", "session_id": "s" * 200},
])
def test_validation_errors_return_400(toolbox, body):
    app, _ = make_app(toolbox, [])
    with TestClient(app) as tc:
        r = tc.post("/api/chat", json=body)
    assert r.status_code == 400 and isinstance(r.json()["detail"], str)


def test_message_at_limit_is_accepted(toolbox):
    app, _ = make_app(toolbox, [text_msg("ok")])
    with TestClient(app) as tc:
        assert chat(tc, "x" * 2000).status_code == 200


def test_rate_limit_per_ip(toolbox):
    app, _ = make_app(toolbox, [text_msg("a"), text_msg("b")], rate_limit_per_10min=2)
    with TestClient(app) as tc:
        assert chat(tc, "one").status_code == 200
        assert chat(tc, "two").status_code == 200
        r = chat(tc, "three")
    assert r.status_code == 429 and "detail" in r.json() and int(r.headers["retry-after"]) >= 1


def test_forwarded_for_only_trusted_when_enabled(toolbox):
    script = [text_msg("a")] * 4
    for trust, expected in [(False, [200, 429]), (True, [200, 200])]:
        app, _ = make_app(toolbox, list(script), rate_limit_per_10min=1, trust_proxy=trust)
        with TestClient(app) as tc:
            codes = [tc.post("/api/chat", json={"message": "hi"}, headers={"X-Forwarded-For": ip}).status_code
                     for ip in ("1.1.1.1", "2.2.2.2")]
        assert codes == expected


def test_llm_exception_becomes_error_event_without_leaking(toolbox, monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "sk-super-secret-key-123")
    app, client = make_app(toolbox, [RuntimeError("boom sk-super-secret-key-123"), text_msg("recovered")])
    with TestClient(app) as tc:
        r = chat(tc, "hi")
        events = parse_sse(r.text)
        assert [n for n, _ in events] == ["session", "error"]
        err = events[-1][1]
        assert err["code"] == "llm_error" and "secret" not in r.text and "boom" not in r.text
        sid = events[0][1]["session_id"]
        # the session is released BEFORE the error event is sent, so an instant retry works.
        # The failed turn left no dangling history, and the session still works
        ok = dict(parse_sse(chat(tc, "again", sid).text))
    assert ok["answer"]["content"] == "recovered"
    assert [m["role"] for m in client.sent[1]["messages"]] == ["system", "user"]


def test_provider_status_codes_get_specific_messages(toolbox):
    class Busy(Exception):
        status_code = 429
    client = FakeClient([Busy("rate limit from provider")] * 3)  # 429 is retried twice before the turn fails
    app = create_app(lambda tb: Agent(client=client, model="fake", toolbox=tb, retry_delays=(0, 0)), toolbox, Settings())
    with TestClient(app) as tc:
        err = dict(parse_sse(chat(tc, "hi").text))["error"]
    assert "busy" in err["message"] and len(client.sent) == 3


def test_schemes_list_hides_rules(toolbox):
    app, _ = make_app(toolbox, [])
    with TestClient(app) as tc:
        r = tc.get("/api/schemes")
    schemes = r.json()
    assert r.status_code == 200 and len(schemes) == len(toolbox.schemes) == len(load_schemes())
    assert all("rules" not in s for s in schemes)
    assert set(schemes[0]) == {"id", "name", "category", "summary", "benefits", "documents", "how_to_apply",
                               "source_url", "tags", "aliases", "caveats"}


def test_scheme_detail_includes_rules_and_404(toolbox):
    app, _ = make_app(toolbox, [])
    with TestClient(app) as tc:
        ok = tc.get("/api/schemes/ignwps")
        missing = tc.get("/api/schemes/nope")
    body = ok.json()
    assert ok.status_code == 200 and body["id"] == "ignwps"
    assert body["rules"] and set(body["rules"][0]) >= {"field", "op", "value", "reason"}
    assert missing.status_code == 404 and missing.json() == {"detail": "Unknown scheme"}


def test_health_never_exposes_keys(toolbox, monkeypatch):
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
    monkeypatch.setenv("LLM_API_KEY", "sk-super-secret-key-123")
    monkeypatch.setenv("LLM_MODEL", "my-model")
    app = create_app(toolbox=toolbox, settings=Settings())
    with TestClient(app) as tc:
        r = tc.get("/api/health")
    assert r.json() == {"ok": True, "schemes": len(load_schemes())}  # no model name or provider status for the public
    assert "secret" not in r.text and "my-model" not in r.text


def test_unconfigured_provider_gives_friendly_error(toolbox, monkeypatch):
    for var in ("LLM_API_KEY", "LLM_BASE_URL", "NVIDIA_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    app = create_app(toolbox=toolbox, settings=Settings())
    with TestClient(app) as tc:
        events = parse_sse(chat(tc, "hi").text)
    assert events[0][0] == "error" and events[0][1]["code"] == "llm_error"


def test_cors_allows_configured_origin_only(toolbox):
    app, _ = make_app(toolbox, [], allowed_origins=["https://sahayak.example"])
    with TestClient(app) as tc:
        good = tc.get("/api/health", headers={"Origin": "https://sahayak.example"})
        bad = tc.get("/api/health", headers={"Origin": "https://evil.example"})
    assert good.headers["access-control-allow-origin"] == "https://sahayak.example"
    assert "access-control-allow-origin" not in bad.headers


def test_session_store_expiry_and_eviction():
    now = [0.0]
    made = []
    store = SessionStore(lambda: made.append(1) or object(), ttl_s=100, max_sessions=2, clock=lambda: now[0])
    a = store.get_or_create(None)
    now[0] = 10
    b = store.get_or_create(None)
    now[0] = 20
    store.get_or_create(a.id)  # refresh a, so b is the oldest
    c = store.get_or_create(None)
    assert store.get_or_create(a.id) is a and store.get_or_create(b.id) is not b
    now[0] = 500
    assert len(store) == 0 and store.get_or_create(c.id) is not c


def test_cancelled_run_rolls_back_history_and_releases(toolbox):
    client = FakeClient([tool_msg("check_eligibility", WIDOW), text_msg("never sent")])
    agent = Agent(client=client, model="fake", toolbox=toolbox)
    released = asyncio.Event()

    async def scenario():
        run = AgentRun(agent, "hi", released.set, keepalive_s=5)
        run.cancel()  # consumer disconnected before the first event
        run.start()
        with pytest.raises(Cancelled):
            async for _ in run.events():
                pass
        await asyncio.wait_for(released.wait(), 2)

    asyncio.run(scenario())
    assert [m["role"] for m in agent.messages] == ["system"]


def test_agent_chat_without_callback_unchanged(toolbox):
    agent = Agent(client=FakeClient([text_msg("<think>x</think>hello")]), model="fake", toolbox=toolbox)
    answer, trace = agent.chat("hi")
    assert answer == "hello" and trace.steps[-1]["kind"] == "answer"
