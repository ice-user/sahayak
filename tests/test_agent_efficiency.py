"""Fewer round trips, tool-result cache, answer styles, per-turn language hint, reasoning-control env vars."""
import json

import pytest

from sahayak.agent import (ANSWER_STYLES, BRIEF_MAX_TOKENS, SYSTEM_PROMPT, Agent, build_system_prompt, env_extra_body)
from sahayak.lang import REPLY_LANGUAGE_HINTS, reply_language_hint
from sahayak.tools import Toolbox
from tests.llm_fakes import FakeLLM, collect, text_msg, text_stream, tool_msg

TB = Toolbox(search_mode="bm25")
WIDOW = {"profile": {"age": 62, "gender": "female", "marital_status": "widowed", "bpl": True}}


def make(script, tb=TB, **kw):
    client = FakeLLM(script)
    kw.setdefault("stream", False)
    return Agent(client=client, model="fake", toolbox=tb, **kw), client


class CountingToolbox(Toolbox):
    def __init__(self):
        super().__init__(search_mode="bm25")
        self.calls = []

    def call(self, name, arguments):
        self.calls.append(name)
        return super().call(name, arguments)


# ---- eligible items carry documents and how_to_apply
def test_eligible_items_include_documents_and_how_to_apply():
    result = TB.check_eligibility(**WIDOW)
    assert result["eligible"]
    for item in result["eligible"]:
        scheme = TB.schemes[item["scheme_id"]]
        assert item["documents"] == scheme.documents and item["how_to_apply"] == scheme.how_to_apply
        assert item["documents"] and item["how_to_apply"]
        assert item["benefits"] and item["source_url"]                       # still there
    for item in result["need_info"] + result["not_eligible"]:
        assert "documents" not in item and "how_to_apply" not in item


def test_eligible_documents_survive_the_tool_json_round_trip():
    parsed = json.loads(TB.call("check_eligibility", json.dumps(WIDOW)))
    assert all(isinstance(i["documents"], list) and isinstance(i["how_to_apply"], str) for i in parsed["eligible"])


def test_documents_are_copies_not_the_scheme_lists():
    item = TB.check_eligibility(**WIDOW)["eligible"][0]
    item["documents"].append("x")
    assert "x" not in TB.schemes[item["scheme_id"]].documents


# ---- prompt
def test_prompt_says_check_first_and_not_to_use_details_for_checked_schemes():
    for style in ANSWER_STYLES:
        p = build_system_prompt(style)
        assert "check_eligibility FIRST" in p and "Do not call search_schemes first" in p
        assert "Never call get_scheme_details for a scheme that check_eligibility already returned" in p
        assert "at most one tool per step" in p.lower()
        assert "only for a topic question with no personal facts" in p
    assert SYSTEM_PROMPT == build_system_prompt("full")


def test_brief_prompt_vs_full_prompt():
    brief, full = build_system_prompt("brief"), build_system_prompt("full")
    assert "120 words" in brief and "one line per eligible scheme" in brief.lower()
    assert "at most 3 short follow-up questions" in brief and "cards" in brief and "do NOT list them" in brief
    assert "120 words" not in full and "key documents, how to apply" in full


def test_invalid_style_is_rejected():
    with pytest.raises(ValueError):
        build_system_prompt("verbose")
    with pytest.raises(ValueError):
        Agent(client=FakeLLM([]), toolbox=TB, answer_style="verbose")


def test_default_style_is_full_and_brief_sets_max_tokens():
    agent, client = make([text_msg("hi")])
    assert agent.answer_style == "full" and agent.max_tokens is None
    agent.chat("hello")
    assert "max_tokens" not in client.sent[0] and "120 words" not in client.sent[0]["messages"][0]["content"]
    agent, client = make([text_msg("hi")], answer_style="brief")
    agent.chat("hello")
    assert client.sent[0]["max_tokens"] == BRIEF_MAX_TOKENS == 700
    assert "120 words" in client.sent[0]["messages"][0]["content"]
    agent, client = make([text_msg("hi")], answer_style="brief", max_tokens=300)
    agent.chat("hello")
    assert client.sent[0]["max_tokens"] == 300


def test_guard_still_works_in_brief_style():
    agent, client = make([text_msg("You can get IGNOAPS."), tool_msg("check_eligibility", WIDOW, "c2"),
                          text_msg("IGNOAPS: monthly pension. Caveat: state top-up may differ.")], answer_style="brief")
    answer, trace = agent.chat("My mother is 62, a widow, BPL")
    assert [s["action"] for s in trace.steps if s["kind"] == "guard"] == ["retry"] and "IGNOAPS" in answer


# ---- typical flow is two LLM calls
def test_typical_turn_is_one_tool_call_and_one_answer():
    agent, client = make([tool_msg("check_eligibility", WIDOW), text_msg("Mother can get IGNWPS and IGNOAPS.")],
                         answer_style="brief")
    answer, trace = agent.chat("My mother is 62, a widow, BPL card holder")
    assert trace.llm_calls == 2 and len(client.sent) == 2
    assert trace.steps[-1]["kind"] == "answer" and trace.steps[-1]["llm_calls"] == 2
    assert [c["name"] for c in trace.tool_calls()] == ["check_eligibility"]


def test_trace_counts_llm_calls_per_turn_not_per_conversation():
    agent, _ = make([tool_msg("check_eligibility", WIDOW), text_msg("Mother can get IGNWPS."), text_msg("Welcome.")])
    _, t1 = agent.chat("mother 62 widow BPL")
    _, t2 = agent.chat("thanks")
    assert (t1.llm_calls, t2.llm_calls) == (2, 1)


# ---- tool-result cache
def test_identical_tool_call_is_served_from_cache():
    tb = CountingToolbox()
    agent, _ = make([tool_msg("check_eligibility", WIDOW, "a"), tool_msg("check_eligibility", WIDOW, "b"),
                     text_msg("Mother can get IGNWPS.")], tb=tb)
    events = []
    _, trace = agent.chat("mother 62 widow BPL", on_event=lambda k, d: events.append((k, d)))
    assert tb.calls == ["check_eligibility"]                                  # executed once
    calls = trace.tool_calls()
    assert [c.get("cached", False) for c in calls] == [False, True] and calls[0]["result"] == calls[1]["result"]
    # the protocol is unchanged: both calls were announced and answered, under their own ids
    assert [(k, d["id"]) for k, d in events if k in ("tool_call", "tool_result")] == [
        ("tool_call", "a"), ("tool_result", "a"), ("tool_call", "b"), ("tool_result", "b")]
    assert [m["tool_call_id"] for m in agent.messages if m["role"] == "tool"] == ["a", "b"]


def test_cache_ignores_argument_key_order_and_spans_turns():
    tb = CountingToolbox()
    agent, _ = make([tool_msg("check_eligibility", {"profile": {"age": 62, "gender": "female"}}),
                     text_msg("What is her marital status?"),
                     tool_msg("check_eligibility", {"profile": {"gender": "female", "age": 62}}),
                     text_msg("Done.")], tb=tb)
    agent.chat("my mother is 62")
    agent.chat("she is female")
    assert tb.calls == ["check_eligibility"]


def test_different_arguments_are_not_cached_and_verdicts_follow_the_latest_check():
    tb = CountingToolbox()
    agent, _ = make([tool_msg("check_eligibility", {"profile": {"age": 62}}),
                     tool_msg("check_eligibility", WIDOW, "c2"), text_msg("ok")], tb=tb)
    agent.chat("mother is 62, a widow, BPL")
    assert tb.calls == ["check_eligibility", "check_eligibility"]
    assert agent.verdicts["ignwps"] == "eligible"


def test_errors_are_not_cached():
    tb = CountingToolbox()
    bad = {"profile": {"age": "sixty"}}
    agent, _ = make([tool_msg("check_eligibility", bad), tool_msg("check_eligibility", bad, "c2"), text_msg("?")], tb=tb)
    agent.chat("father is old")
    assert tb.calls == ["check_eligibility"] * 2


def test_search_results_are_cached_too():
    tb = CountingToolbox()
    agent, _ = make([tool_msg("search_schemes", {"query": "widow pension"}),
                     tool_msg("search_schemes", {"query": "widow pension"}, "c2"), text_msg("ok")], tb=tb)
    agent.chat("tell me about widow pension")
    assert tb.calls == ["search_schemes"]


# ---- reply language hint, per turn
@pytest.mark.parametrize("lang,message,expect", [
    ("en", "My mother is 62, a widow", "Reply in English"),
    ("hi", "मेरी माँ 62 साल की विधवा हैं", "Devanagari"),
    ("hinglish", "Mere dadaji 74 saal ke hain, unke liye hospital ka koi free scheme hai kya?", "Latin letters"),
    ("ta", "என் அம்மாவுக்கு 62 வயது, அவர் விதவை", "Tamil script"),
])
def test_language_hint_is_in_the_system_prompt_each_turn(lang, message, expect):
    agent, client = make([text_msg("ok")])
    agent.chat(message)
    system = client.sent[0]["messages"][0]
    assert system["role"] == "system" and REPLY_LANGUAGE_HINTS[lang] in system["content"]
    assert expect in system["content"].split("\n\n")[-1]
    assert "Keep scheme names in English" in REPLY_LANGUAGE_HINTS[lang]
    assert agent.messages[0]["content"] == build_system_prompt("full")        # the stored prompt has no hint


def test_hinglish_hint_forbids_devanagari():
    assert "NOT Devanagari" in reply_language_hint("hinglish") and "Roman" in reply_language_hint("hinglish")
    assert reply_language_hint("zz") == reply_language_hint("en")


def test_hint_is_recomputed_every_turn_and_stays_sticky():
    agent, client = make([text_msg("a"), text_msg("b"), text_msg("c")])
    agent.chat("What schemes exist?")
    agent.chat("Mera naam Ravi hai, meri umar 40 saal hai")
    agent.chat("yes")                                                         # a later English reply does not flip it
    tails = [c["messages"][0]["content"].split("\n\n")[-1] for c in client.sent]
    assert tails == [REPLY_LANGUAGE_HINTS["en"], REPLY_LANGUAGE_HINTS["hinglish"], REPLY_LANGUAGE_HINTS["hinglish"]]


def test_hint_does_not_accumulate_within_a_turn_with_tool_calls():
    agent, client = make([tool_msg("check_eligibility", WIDOW), text_msg("ok")])
    agent.chat("मेरी माँ 62 साल की विधवा हैं")
    assert all(c["messages"][0]["content"].count(REPLY_LANGUAGE_HINTS["hi"]) == 1 for c in client.sent)


# ---- reasoning control env vars
def test_llm_extra_body_env_is_passed_through(monkeypatch):
    monkeypatch.setenv("LLM_EXTRA_BODY", '{"chat_template_kwargs": {"thinking": false}}')
    agent, client = make([text_msg("hi")])
    agent.chat("hello")
    assert client.sent[0]["extra_body"] == {"chat_template_kwargs": {"thinking": False}}


def test_extra_body_absent_by_default_and_explicit_argument_wins(monkeypatch):
    agent, client = make([text_msg("hi")])
    agent.chat("hello")
    assert "extra_body" not in client.sent[0]
    monkeypatch.setenv("LLM_EXTRA_BODY", '{"a": 1}')
    agent, client = make([text_msg("hi")], extra_body={"b": 2})
    agent.chat("hello")
    assert client.sent[0]["extra_body"] == {"b": 2}


@pytest.mark.parametrize("raw", ["not json", "[1, 2]", '"str"', "  "])
def test_bad_extra_body_is_ignored(monkeypatch, raw):
    monkeypatch.setenv("LLM_EXTRA_BODY", raw)
    assert env_extra_body() is None


def test_llm_system_prefix_is_prepended(monkeypatch):
    monkeypatch.setenv("LLM_SYSTEM_PREFIX", "detailed thinking off")
    agent, client = make([text_msg("hi")])
    agent.chat("hello")
    assert client.sent[0]["messages"][0]["content"].startswith("detailed thinking off\n\nYou are Sahayak")
    agent, client = make([text_msg("hi")], system_prefix="")
    assert agent.messages[0]["content"] == SYSTEM_PROMPT


def test_extra_body_and_streaming_together():
    agent, client = make([text_stream("hello")], stream=True, extra_body={"k": "v"})
    collect(agent, "hi")
    assert client.sent[0]["extra_body"] == {"k": "v"} and client.sent[0]["stream"] is True
