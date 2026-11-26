"""The API forwards `token` events in the order documented in docs/API.md, and applies the production settings."""
import pytest
from fastapi.testclient import TestClient

from server.config import Settings
from server.main import create_app, make_agent
from sahayak.agent import Agent
from sahayak.tools import Toolbox
from tests.llm_fakes import FakeLLM, StatusError, text_msg, text_stream, tool_stream
from tests.test_server import chat, parse_sse

TB = Toolbox(search_mode="bm25")
WIDOW = {"profile": {"age": 62, "gender": "female", "marital_status": "widowed", "bpl": True}}


def app_for(client, **agent_kw):
    agent_kw.setdefault("retry_delays", (0, 0))
    return create_app(lambda tb: Agent(client=client, model="fake", toolbox=tb, stream=True, **agent_kw), TB, Settings())


def test_events_in_documented_order_with_streamed_tokens():
    client = FakeLLM([tool_stream("check_eligibility", WIDOW),
                      text_stream("Your mother can get IGNWPS and IGNOAPS. Do you have a bank account?", size=6)])
    with TestClient(app_for(client)) as tc:
        events = parse_sse(chat(tc, "My mother is 62, a widow, BPL").text)
    names = [n for n, _ in events]
    first, last = names.index("token"), len(names) - 1 - names[::-1].index("token")
    assert names[:first] == ["session", "tool_call", "tool_result"]
    assert set(names[first:last + 1]) == {"token"}
    assert names[last + 1:] == ["answer", "suggestions", "done"]
    streamed = "".join(d["delta"] for n, d in events if n == "token")
    answer = dict(events[last + 1:])["answer"]["content"]
    assert streamed == answer
    done = events[-1][1]
    assert done["llm_calls"] == 2 and done["tokens"] > 0


def test_answer_event_carries_the_guarded_text_not_the_streamed_one():
    bad = "You can get IGNWPS. Apply at https://evil.example.com now."
    client = FakeLLM([text_stream(bad, size=5), text_msg(bad)])
    with TestClient(app_for(client)) as tc:
        events = parse_sse(chat(tc, "hello").text)
    names = [n for n, _ in events]
    assert names[-2:] == ["answer", "done"]
    answer = dict(events)["answer"]["content"]
    assert "IGNWPS" not in answer and "evil.example.com" not in answer
    assert "IGNWPS" not in "".join(d["delta"] for n, d in events if n == "token")


def test_no_tokens_when_streaming_is_disabled():
    client = FakeLLM([text_msg("Namaste!")])
    app = create_app(lambda tb: Agent(client=client, model="fake", toolbox=tb, stream=False), TB, Settings())
    with TestClient(app) as tc:
        names = [n for n, _ in parse_sse(chat(tc, "hi").text)]
    assert names == ["session", "answer", "done"] and "stream" not in client.sent[0]


def test_transient_provider_error_is_retried_inside_the_request():
    client = FakeLLM([StatusError(503, "content safety screening is temporarily unavailable"), text_msg("Vanakkam!")])
    with TestClient(app_for(client)) as tc:
        events = parse_sse(chat(tc, "வணக்கம்").text)
    assert [n for n, _ in events] == ["session", "answer", "done"] and len(client.sent) == 2


def test_auth_failure_is_not_retried_and_does_not_leak():
    client = FakeLLM([StatusError(401, "Invalid API key sk-xyz"), text_msg("unused")])
    with TestClient(app_for(client)) as tc:
        r = chat(tc, "hi")
    err = dict(parse_sse(r.text))["error"]
    assert err["code"] == "llm_error" and "sk-xyz" not in r.text and len(client.sent) == 1


def test_production_agent_is_brief_and_streams_by_default(monkeypatch):
    monkeypatch.delenv("LLM_STREAM", raising=False)
    agent = make_agent(FakeLLM([]), TB, Settings())
    assert agent.answer_style == "brief" and agent.max_tokens == 700 and agent.stream is True
    assert "120 words" in agent.messages[0]["content"]


def test_answer_style_setting_from_env(monkeypatch):
    monkeypatch.setenv("ANSWER_STYLE", "full")
    s = Settings.from_env()
    assert s.answer_style == "full" and make_agent(FakeLLM([]), TB, s).answer_style == "full"
    monkeypatch.setenv("ANSWER_STYLE", "nonsense")
    assert Settings.from_env().answer_style == "brief"
    monkeypatch.setenv("MAX_TOKENS", "900")
    assert Settings.from_env().max_tokens == 900


def test_cancelled_run_stops_retrying():
    """AgentRun hands its cancel flag to the agent, so a closed tab does not keep a retry loop alive."""
    import asyncio
    from server.streaming import AgentRun

    client = FakeLLM([StatusError(503), text_msg("unused")])
    agent = Agent(client=client, model="fake", toolbox=TB, stream=False, retry_delays=(0.0, 0.0))

    async def scenario():
        run = AgentRun(agent, "hi", lambda: None)
        run.cancel()
        run.start()
        with pytest.raises(Exception) as info:
            async for _ in run.events():
                pass
        return info.value

    exc = asyncio.run(scenario())
    assert type(exc).__name__ in ("TurnCancelled", "Cancelled") and len(client.sent) <= 1
