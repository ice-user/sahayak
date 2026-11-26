"""Retry of transient provider errors (429/500/502/503/504, timeouts, connection errors, "temporarily unavailable")."""
import pytest

from sahayak import llm
from sahayak.agent import Agent
from sahayak.llm import TurnCancelled, complete, is_transient
from sahayak.tools import Toolbox
from tests.llm_fakes import (APITimeoutError, FakeLLM, StatusError, collect, text_msg, text_stream, tool_msg)

TB = Toolbox(search_mode="bm25")
SAFETY_503 = "Error code: 503 - content safety screening is temporarily unavailable"


class ConnectionFailed(Exception):
    pass


ConnectionFailed.__name__ = "APIConnectionError"


@pytest.mark.parametrize("exc", [
    StatusError(429), StatusError(500), StatusError(502), StatusError(503, SAFETY_503), StatusError(504),
    APITimeoutError("Request timed out."), ConnectionFailed("Connection error."), TimeoutError(), ConnectionResetError(),
    RuntimeError("service temporarily unavailable"), RuntimeError("upstream timed out"),
    Exception("content safety screening is temporarily unavailable"),
])
def test_transient_errors(exc):
    assert is_transient(exc)


@pytest.mark.parametrize("exc", [
    StatusError(400, "bad request"), StatusError(401, "bad key"), StatusError(403, "forbidden"),
    StatusError(404, "model not found"), StatusError(422, "unprocessable"),
    StatusError(400, "temporarily unavailable"),       # a status that says "your fault" wins over the wording
    StatusError(401, "service unavailable"), ValueError("bad json"), KeyError("x"), TurnCancelled(),
])
def test_permanent_errors(exc):
    assert not is_transient(exc)


def test_status_on_response_attribute_is_honoured():
    from types import SimpleNamespace as NS
    e = Exception("x")
    e.response = NS(status_code=503)
    assert is_transient(e)
    e.response = NS(status_code=401)
    assert not is_transient(e)


def make(script, **kw):
    client = FakeLLM(script)
    kw.setdefault("stream", False)
    return Agent(client=client, model="fake", toolbox=TB, **kw), client


def test_default_backoff_is_one_then_three_seconds():
    assert llm.RETRY_DELAYS == (1.0, 3.0)
    assert Agent(client=FakeLLM([]), model="fake", toolbox=TB).retry_delays == (1.0, 3.0)


def test_503_is_retried_with_backoff_and_the_turn_succeeds(monkeypatch):
    waits = []
    monkeypatch.setattr(llm, "wait", lambda delay, cancelled: waits.append(delay))
    agent, client = make([StatusError(503, SAFETY_503), StatusError(503, SAFETY_503), text_msg("Namaste!")])
    answer, trace = agent.chat("hi")
    assert answer == "Namaste!" and waits == [1.0, 3.0] and len(client.sent) == 3
    assert trace.llm_calls == 1 and trace.llm_steps()[0]["retries"] == 2          # retries are not extra LLM calls
    assert [s["attempt"] for s in trace.steps if s["kind"] == "llm_retry"] == [1, 2]


def test_gives_up_after_two_retries_and_raises_the_provider_error():
    agent, client = make([StatusError(503, SAFETY_503)] * 4, retry_delays=(0, 0))
    with pytest.raises(StatusError):
        agent.chat("hi")
    assert len(client.sent) == 3 and len(agent.messages) == 1


@pytest.mark.parametrize("status", [400, 401, 403, 404])
def test_client_errors_are_never_retried(status):
    agent, client = make([StatusError(status, "nope"), text_msg("unused")], retry_delays=(0, 0))
    with pytest.raises(StatusError):
        agent.chat("hi")
    assert len(client.sent) == 1


@pytest.mark.parametrize("exc", [StatusError(429), StatusError(500), StatusError(502), StatusError(504),
                                 APITimeoutError("timeout"), ConnectionFailed("down"),
                                 RuntimeError("temporarily unavailable")])
def test_each_transient_kind_recovers(exc):
    agent, client = make([exc, text_msg("fine")], retry_delays=(0, 0))
    assert agent.chat("hi")[0] == "fine" and len(client.sent) == 2


def test_retry_in_the_middle_of_a_turn_after_a_tool_call():
    agent, client = make([tool_msg("check_eligibility", {"profile": {"age": 62}}), StatusError(503, SAFETY_503),
                          text_msg("Done.")], retry_delays=(0, 0))
    answer, trace = agent.chat("I am 62")
    assert answer == "Done." and trace.llm_calls == 2 and len(client.sent) == 3
    assert client.sent[2]["messages"][-1]["role"] == "tool"                         # retried with the same history


def test_cancellation_between_retries_stops_without_another_call(monkeypatch):
    client = FakeLLM([StatusError(503, SAFETY_503), text_msg("must not be reached")])
    flag = {"cancel": False}

    def on_retry(attempt, exc, delay):
        flag["cancel"] = True                      # the user closed the tab while we were backing off

    with pytest.raises(TurnCancelled):
        complete(client, {"model": "m", "messages": []}, stream=False, cancelled=lambda: flag["cancel"],
                 delays=(1.0, 3.0), on_retry=on_retry)
    assert len(client.sent) == 1


def test_agent_passes_cancelled_to_the_retry_loop():
    agent, client = make([StatusError(503), text_msg("unused")], retry_delays=(0.0, 0.0))
    with pytest.raises(TurnCancelled):
        agent.chat("hi", cancelled=lambda: True)
    assert len(client.sent) == 1 and len(agent.messages) == 1


def test_wait_polls_cancellation(monkeypatch):
    calls = []
    monkeypatch.setattr(llm.time, "sleep", lambda s: calls.append(s))
    n = {"i": 0}

    def cancelled():
        n["i"] += 1
        return n["i"] > 3

    with pytest.raises(TurnCancelled):
        llm.wait(30, cancelled)
    assert len(calls) == 3 and all(c <= 0.1 for c in calls)


def test_streaming_503_at_open_is_retried_without_streaming_then_succeeds():
    agent, client = make([StatusError(503, SAFETY_503), text_msg("Vanakkam")], stream=True, retry_delays=(0, 0))
    answer, trace, events = collect(agent, "hi")
    assert answer == "Vanakkam" and [bool(s.get("stream")) for s in client.sent] == [True, False]
    assert trace.llm_steps()[0]["retries"] == 1


def test_streaming_success_after_nothing_wrong_makes_one_call():
    agent, client = make([text_stream("ok")], stream=True)
    collect(agent, "hi")
    assert len(client.sent) == 1


def test_tamil_503_case_from_the_field():
    """The reported failure: 503 'content safety screening is temporarily unavailable' on a Tamil question."""
    agent, client = make([StatusError(503, SAFETY_503), text_msg("உங்களுக்கு உதவ முடியும்.")], retry_delays=(0, 0))
    answer, _ = agent.chat("என் அம்மாவுக்கு 62 வயது, அவர் விதவை")
    assert "உதவ" in answer and len(client.sent) == 2
