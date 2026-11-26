"""Streaming the final answer: delta accumulation, <think> stripping, fallback to non-streaming, guard overwrite."""
import pytest

from sahayak.agent import Agent
from sahayak.llm import ThinkFilter, consume_stream
from sahayak.tools import Toolbox
from tests.llm_fakes import (Broken, FakeLLM, StatusError, chunk, collect, split, tc_delta, text_msg, text_stream,
                             tool_msg, tool_stream, usage_chunk)

TB = Toolbox(search_mode="bm25")
WIDOW = {"profile": {"age": 62, "gender": "female", "marital_status": "widowed", "bpl": True}}


def make(script, **kw):
    client = FakeLLM(script)
    kw.setdefault("stream", True)
    kw.setdefault("retry_delays", (0, 0))
    return Agent(client=client, model="fake", toolbox=TB, **kw), client


def tokens(events):
    return [d["delta"] for k, d in events if k == "token"]


# ---- delta accumulation
def test_text_deltas_become_token_events_then_answer():
    agent, client = make([text_stream("Hello, how can I help you today?", size=4)])
    answer, trace, events = collect(agent, "hi")
    assert "".join(tokens(events)) == answer == "Hello, how can I help you today?"
    assert [k for k, _ in events][-1] == "answer" and set(k for k, _ in events) == {"token", "answer"}
    assert client.sent[0]["stream"] is True
    assert trace.ttft_s is not None and trace.llm_steps()[0]["streamed"] is True


def test_tool_call_args_split_across_chunks_with_id_only_in_first_chunk():
    args = {"profile": {"age": 62, "gender": "female", "marital_status": "widowed", "bpl": True}}
    agent, client = make([tool_stream("check_eligibility", args, "call_abc", size=3),
                          text_stream("Your mother can get IGNWPS.", size=6)])
    answer, trace, events = collect(agent, "mother 62 widow BPL")
    call = [d for k, d in events if k == "tool_call"][0]
    assert call == {"id": "call_abc", "name": "check_eligibility", "arguments": args}
    assert trace.tool_calls()[0]["name"] == "check_eligibility"
    result = [d for k, d in events if k == "tool_result"][0]
    assert result["id"] == "call_abc" and any(i["scheme_id"] == "ignwps" for i in result["result"]["eligible"])
    # history keeps the merged call; the tool message answers it
    assistant = [m for m in agent.messages if m.get("tool_calls")][0]
    assert assistant["tool_calls"][0]["id"] == "call_abc"
    assert assistant["tool_calls"][0]["function"]["name"] == "check_eligibility"
    # no tokens for the tool-call message, tokens only after tool_result
    kinds = [k for k, _ in events]
    assert kinds[:2] == ["tool_call", "tool_result"] and "token" in kinds[2:] and kinds[-1] == "answer"
    assert "".join(tokens(events)) == answer


def test_two_parallel_tool_calls_interleaved_by_index():
    chunks = [
        chunk(tool_calls=[tc_delta(0, "a", "search_schemes", '{"que')]),
        chunk(tool_calls=[tc_delta(1, "b", "search_schemes", '{"qu')]),
        chunk(tool_calls=[tc_delta(0, None, None, 'ry": "widow pension"}')]),
        chunk(tool_calls=[tc_delta(1, None, None, 'ery": "girl savings"}')]),
        chunk(finish="tool_calls"),
    ]
    reply = consume_stream(iter(chunks), lambda t: None, 0)
    assert [(c.id, c.function.name, c.function.arguments) for c in reply.tool_calls] == [
        ("a", "search_schemes", '{"query": "widow pension"}'), ("b", "search_schemes", '{"query": "girl savings"}')]


def test_repeated_name_is_not_doubled_and_missing_index_and_id_are_handled():
    chunks = [chunk(tool_calls=[tc_delta(0, "x", "get_scheme_details", '{"scheme')]),
              chunk(tool_calls=[tc_delta(0, None, "get_scheme_details", '_id": "ssy"}')])]
    reply = consume_stream(iter(chunks), lambda t: None, 0)
    assert reply.tool_calls[0].function.name == "get_scheme_details"
    assert reply.tool_calls[0].function.arguments == '{"scheme_id": "ssy"}'
    # providers that send whole calls without index or id
    chunks = [chunk(tool_calls=[tc_delta(None, None, "search_schemes", '{"query": "a"}')])]
    reply = consume_stream(iter(chunks), lambda t: None, 0)
    assert reply.tool_calls[0].id == "call_1" and reply.tool_calls[0].function.arguments == '{"query": "a"}'


def test_same_index_reused_for_a_new_call_with_new_id():
    chunks = [chunk(tool_calls=[tc_delta(0, "a", "search_schemes", '{"query": "one"}')]),
              chunk(tool_calls=[tc_delta(0, "b", "search_schemes", '{"query": "two"}')])]
    reply = consume_stream(iter(chunks), lambda t: None, 0)
    assert [c.id for c in reply.tool_calls] == ["a", "b"]
    assert [c.function.arguments for c in reply.tool_calls] == ['{"query": "one"}', '{"query": "two"}']


def test_usage_in_final_chunk_is_used_and_missing_usage_is_estimated():
    agent, _ = make([text_stream("ok then", size=3, usage=777)])
    _, trace, _ = collect(agent, "hi")
    assert trace.llm_steps()[0]["tokens"] == 777 and "tokens_estimated" not in trace.llm_steps()[0]
    agent, _ = make([text_stream("ok then", size=3)])
    _, trace, _ = collect(agent, "hi")
    step = trace.llm_steps()[0]
    assert step["tokens"] > 0 and step["tokens_estimated"] is True


def test_empty_choices_and_none_delta_chunks_are_ignored():
    chunks = [usage_chunk(5), chunk("a"), type(chunk("x"))(choices=[type(chunk("x"))(delta=None)], usage=None),
              chunk("b"), usage_chunk(9)]
    seen = []
    reply = consume_stream(iter(chunks), seen.append, 0)
    assert reply.content == "ab" and seen == ["a", "b"] and reply.tokens == 9


def test_stream_is_closed():
    agent, client = make([text_stream("hello there", size=4)])
    collect(agent, "hi")
    assert client.closed == 1


# ---- <think> stripping
THINKING = "<think>The user greets me. I should answer briefly.</think>\n\nNamaste! How can I help?"


@pytest.mark.parametrize("size", [1, 2, 3, 5, 7, 11, 100])
def test_think_block_is_never_streamed_whatever_the_chunk_boundaries(size):
    agent, _ = make([text_stream(THINKING, size=size)])
    answer, _, events = collect(agent, "hi")
    shown = "".join(tokens(events))
    assert "think" not in shown and "greets" not in shown
    assert shown == answer == "Namaste! How can I help?"


def test_think_tag_split_exactly_at_every_position():
    for i in range(1, len(THINKING)):
        f = ThinkFilter()
        out = f.feed(THINKING[:i]) + f.feed(THINKING[i:]) + f.flush()
        assert out.strip() == "Namaste! How can I help?", i


def test_unclosed_think_is_buffered_and_dropped():
    f = ThinkFilter()
    assert f.feed("Hi <thi") == "Hi " and f.feed("nk>secret reasoning") == "" and f.flush() == ""
    agent, _ = make([text_stream("<think>endless reasoning that never closes", size=6), text_msg("Answer after retry.")])
    answer, trace, events = collect(agent, "hi")
    assert tokens(events) == [] and answer == "Answer after retry."  # empty-answer retry delivers it via `answer`


def test_partial_tag_that_is_not_a_tag_is_released():
    f = ThinkFilter()
    assert f.feed("a < b and <th") == "a < b and " and f.feed("ird thing") == "<third thing"
    assert f.feed("5 <") == "5 " and f.flush() == "<"


def test_stray_closing_tag_is_dropped_and_answer_replaces_leaked_prefix():
    agent, _ = make([text_stream("I should be brief.</think>Final answer here.", size=5)])
    answer, _, events = collect(agent, "hi")
    assert answer == "Final answer here."                    # clean_answer drops the leaked reasoning
    assert "</think>" not in "".join(tokens(events)) and events[-1] == ("answer", {"content": answer})


def test_leading_whitespace_after_think_is_trimmed():
    agent, _ = make([text_stream("<think>x</think>\n\n  Hello", size=4)])
    _, _, events = collect(agent, "hi")
    assert "".join(tokens(events)) == "Hello"


# ---- fallback to non-streaming
def test_provider_rejecting_stream_falls_back_to_a_normal_call():
    agent, client = make([StatusError(400, "stream is not supported"), text_msg("Plain reply.")])
    answer, trace, events = collect(agent, "hi")
    assert answer == "Plain reply." and tokens(events) == []
    assert [bool(s.get("stream")) for s in client.sent] == [True, False]
    step = trace.llm_steps()[0]
    assert step["stream_fallback"] is True and step["streamed"] is False and trace.llm_calls == 1


def test_stream_that_dies_before_any_token_falls_back():
    agent, client = make([Broken([], RuntimeError("connection dropped")), text_msg("Recovered.")])
    answer, _, _ = collect(agent, "hi")
    assert answer == "Recovered." and [bool(s.get("stream")) for s in client.sent] == [True, False]


def test_stream_error_after_tokens_is_not_retried_and_rolls_back():
    agent, client = make([Broken([chunk("Partial ans")], RuntimeError("reset")), text_msg("never used")])
    with pytest.raises(RuntimeError):
        collect(agent, "hi")
    assert len(client.sent) == 1 and len(agent.messages) == 1


def test_auth_error_on_stream_is_not_retried_or_repeated():
    agent, client = make([StatusError(401, "bad key"), text_msg("never")])
    with pytest.raises(StatusError):
        collect(agent, "hi")
    assert len(client.sent) == 1


def test_provider_that_ignores_stream_and_returns_a_whole_reply():
    class Ignoring(FakeLLM):
        def _create(self, **kw):
            kw.pop("stream", None)
            return super()._create(**kw)

    client = Ignoring([text_msg("Whole reply.")])
    agent = Agent(client=client, model="fake", toolbox=TB, stream=True)
    answer, _, events = collect(agent, "hi")
    assert answer == "Whole reply." and tokens(events) == []


def test_no_listener_means_no_streaming_and_env_switch(monkeypatch):
    client = FakeLLM([text_msg("hello")])
    agent = Agent(client=client, model="fake", toolbox=TB, stream=True)
    agent.chat("hi")                                           # no on_event: plain call
    assert "stream" not in client.sent[0]
    monkeypatch.setenv("LLM_STREAM", "0")
    assert Agent(client=client, toolbox=TB).stream is False
    monkeypatch.setenv("LLM_STREAM", "1")
    assert Agent(client=client, toolbox=TB).stream is True
    monkeypatch.delenv("LLM_STREAM")
    assert Agent(client=client, toolbox=TB).stream is True     # on by default
    assert Agent(client=client, toolbox=TB, stream=False).stream is False


# ---- guard after streaming
def test_guard_correction_overwrites_streamed_violation():
    bad = "You can get the widow pension (IGNWPS) right away."
    agent, _ = make([text_stream(bad, size=4),                          # claims IGNWPS with no check at all
                     # after a guard retry the rest of the turn is not streamed: `answer` delivers it
                     tool_msg("check_eligibility", {"profile": {"age": 34, "marital_status": "widowed", "bpl": True,
                                                                  "gender": "female"}}),
                     text_msg("You do not qualify for IGNWPS at 34.")])
    answer, trace, events = collect(agent, "I am a widow, can I get the widow pension?")
    assert "IGNWPS" not in "".join(tokens(events)).split("You do not")[0]   # violating clause never reached the UI
    assert events[-1] == ("answer", {"content": answer}) and "do not qualify" in answer
    assert any(s.get("action") == "stream_stopped" for s in trace.steps if s["kind"] == "guard")
    assert any(s.get("action") == "retry" for s in trace.steps if s["kind"] == "guard")


def test_guard_fallback_is_the_final_answer_event_after_streaming():
    bad = "You can get the widow pension (IGNWPS)."
    agent, _ = make([text_stream(bad, size=3), text_msg(bad)])
    answer, trace, events = collect(agent, "hello")
    assert "IGNWPS" not in "".join(tokens(events))             # stream stopped before the violation was shown
    assert events[-1][0] == "answer" and "myscheme.gov.in" in answer and "IGNWPS" not in answer


def test_streamed_answer_with_unverified_link_is_cleaned_in_answer_event():
    agent, _ = make([tool_stream("check_eligibility", WIDOW),
                     text_stream("You can get IGNWPS. Apply at https://evil.example.com/x now.", size=7)])
    answer, _, events = collect(agent, "mother 62 widow BPL")
    assert "evil.example.com" not in answer and "[link removed]" in answer
    assert events[-1] == ("answer", {"content": answer})


def test_retry_rounds_do_not_stream_tokens_after_the_first_attempt():
    agent, _ = make([text_stream("", pieces=[]), text_msg("Second try.")])
    answer, _, events = collect(agent, "hi")
    assert answer == "Second try." and tokens(events) == []   # retry text arrives via `answer`


def test_cancel_during_stream_aborts_and_rolls_back():
    class Stop(Exception):
        pass

    agent, client = make([text_stream("A fairly long answer to stream.", size=3)])

    def on_event(kind, data):
        if kind == "token":
            raise Stop()

    with pytest.raises(Stop):
        agent.chat("hi", on_event=on_event)
    assert len(agent.messages) == 1 and client.closed == 1


def test_streaming_flow_event_order_and_two_llm_calls():
    agent, client = make([tool_stream("check_eligibility", WIDOW), text_stream("Mother can get IGNWPS and IGNOAPS.")])
    answer, trace, events = collect(agent, "My mother is 62, a widow, BPL")
    kinds = [k for k, _ in events]
    first_token = kinds.index("token")
    assert kinds[:first_token] == ["tool_call", "tool_result"] and kinds[-1] == "answer"
    assert set(kinds[first_token:-1]) == {"token"}
    assert trace.llm_calls == 2 and trace.steps[-1]["llm_calls"] == 2
    assert [bool(s.get("stream")) for s in client.sent] == [True, True]
    assert trace.ttft_s is not None
