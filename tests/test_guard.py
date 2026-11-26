"""Runtime guard (sahayak/guard.py), empty/leaked answers, localized fallbacks, PII masking in the agent loop."""
import json
from types import SimpleNamespace as NS

import pytest

from sahayak.agent import SYSTEM_PROMPT, Agent, clean_answer
from sahayak.guard import neutralize_urls, violations
from sahayak.tools import Toolbox

TB = Toolbox(search_mode="bm25")
WIDOW = {"profile": {"age": 62, "gender": "female", "marital_status": "widowed", "bpl": True}}


def tool_msg(name, args, call_id="c1"):
    return NS(content="", tool_calls=[NS(id=call_id, function=NS(name=name, arguments=json.dumps(args)))])


def text_msg(text):
    return NS(content=text, tool_calls=None)


class FakeClient:
    def __init__(self, script):
        self.script = list(script)
        self.sent = []
        self.chat = NS(completions=NS(create=self._create))

    def _create(self, **kwargs):
        self.sent.append({**kwargs, "messages": list(kwargs["messages"])})
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return NS(choices=[NS(message=item)], usage=NS(total_tokens=10))


def make(script, **kw):
    client = FakeClient(script)
    return Agent(client=client, model="fake", toolbox=TB, **kw), client


def guard_steps(trace):
    return [s for s in trace.steps if s["kind"] == "guard"]


# ---- item 5: guard
def test_violations_unit():
    assert violations("You can get IGNOAPS.", {}) == ["ignoaps"]
    assert violations("You can get IGNOAPS.", {"ignoaps": "eligible"}) == []
    assert violations("You can get IGNOAPS.", {"ignoaps": "need_info"}) == ["ignoaps"]
    assert violations("You can get IGNOAPS.", {"ignoaps": "not_eligible"}) == ["ignoaps"]
    assert violations("You are not eligible for IGNOAPS.", {"ignoaps": "not_eligible"}) == []
    assert violations("Namaste! How can I help?", {}) == []


def test_claim_without_any_tool_call_is_corrected_on_retry():
    agent, client = make([text_msg("You can get the old age pension (IGNOAPS)."),
                          tool_msg("check_eligibility", WIDOW, "c2"),
                          text_msg("Based on the check you can get IGNOAPS.")])
    answer, trace = agent.chat("My mother is 62, a widow, BPL")
    assert answer == "Based on the check you can get IGNOAPS."
    g = guard_steps(trace)
    assert len(g) == 1 and g[0]["action"] == "retry" and g[0]["schemes"] == ["ignoaps"]
    # the corrective note reached the model...
    assert "check_eligibility" in client.sent[1]["messages"][-1]["content"]
    # ...but neither the bad answer nor the note stay in the history
    assert all("You can get the old age pension" not in (m.get("content") or "") for m in agent.messages)
    assert [m["role"] for m in agent.messages].count("user") == 1


def test_persistent_violation_is_replaced_by_safe_fallback_listing_only_verified_schemes():
    agent, _ = make([tool_msg("check_eligibility", WIDOW),
                     text_msg("You can get Atal Pension Yojana (APY)."),
                     text_msg("Definitely, you can get Atal Pension Yojana (APY).")])
    answer, trace = agent.chat("My mother is 62, a widow, BPL")
    assert "APY" not in answer and "Atal" not in answer
    assert "IGNOAPS" in answer and "IGNWPS" in answer
    assert "myscheme.gov.in" in answer
    assert [g["action"] for g in guard_steps(trace)] == ["retry", "fallback"]
    assert agent.messages[-1] == {"role": "assistant", "content": answer}


def test_fallback_without_any_verified_scheme_and_localized():
    agent, _ = make([text_msg("आप IGNOAPS के लिए पात्र हैं।"), text_msg("आप IGNOAPS के लिए पात्र हैं।")])
    answer, trace = agent.chat("मेरी माँ 62 साल की हैं")
    assert "IGNOAPS" not in answer
    assert sum("ऀ" <= ch <= "ॿ" for ch in answer) > 20
    assert guard_steps(trace)[-1]["action"] == "fallback"


def test_correct_answer_passes_without_guard_step():
    agent, _ = make([tool_msg("check_eligibility", WIDOW), text_msg("You can get IGNOAPS and IGNWPS.")])
    _, trace = agent.chat("62 widow bpl")
    assert guard_steps(trace) == []


def test_verdicts_persist_across_turns_and_latest_check_wins():
    agent, _ = make([tool_msg("check_eligibility", WIDOW), text_msg("You can get IGNOAPS."),
                     text_msg("As I said, IGNOAPS is available to you."),             # no new check: still fine
                     tool_msg("check_eligibility", {"profile": {**WIDOW["profile"], "age": 50}}, "c3"),
                     text_msg("You can get IGNOAPS."), text_msg("You can get IGNOAPS.")])  # age 50: no longer eligible
    agent.chat("62 widow bpl")
    _, t2 = agent.chat("remind me")
    assert guard_steps(t2) == []
    answer, t3 = agent.chat("sorry she is 50")
    assert guard_steps(t3)[-1]["action"] == "fallback" and "IGNWPS" in answer


def test_rollback_restores_verdicts_when_turn_fails():
    agent, _ = make([tool_msg("check_eligibility", WIDOW), RuntimeError("provider down")])
    with pytest.raises(RuntimeError):
        agent.chat("hi")
    assert agent.verdicts == {} and len(agent.messages) == 1


def test_guard_can_be_disabled():
    agent, _ = make([text_msg("You can get IGNOAPS.")], guard=False)
    answer, _ = agent.chat("hi")
    assert answer == "You can get IGNOAPS."


# ---- URLs
@pytest.mark.parametrize("text, kept", [
    ("Apply at https://evil.example/apply now", False),
    ("See https://www.myscheme.gov.in/schemes/pmjjby.", True),
    ("See https://pmjay.gov.in/about", True),
    ("Go to https://gov.in.evil.example/x", False),
    ("Go to https://nic.in", True),
    ("visit evil.com/pay or www.phish.net", False),
    ("Official page: https://vendor.example/scheme", True),     # tool-provided source_url host
])
def test_url_neutralisation(text, kept):
    out = neutralize_urls(text, {"vendor.example"})
    if kept:
        assert out == text
    else:
        assert "evil" not in out and "phish" not in out
        assert "[link removed]" in out


def test_markdown_link_keeps_its_text_and_other_text_untouched():
    out = neutralize_urls("Read [the guide](https://evil.example/x), then apply. Docs: Aadhaar.", set())
    assert out == "Read the guide, then apply. Docs: Aadhaar."


def test_agent_strips_foreign_urls_and_emits_trace_step():
    agent, _ = make([tool_msg("check_eligibility", WIDOW),
                     text_msg("You can get IGNOAPS. Apply at https://evil.example/x or https://www.myscheme.gov.in/")])
    answer, trace = agent.chat("62 widow bpl")
    assert "evil" not in answer and "myscheme.gov.in" in answer
    assert any(g["action"] == "urls_removed" for g in guard_steps(trace))


def test_scheme_source_url_from_tool_result_is_allowed():
    url = TB.schemes["ignoaps"].source_url
    agent, _ = make([tool_msg("check_eligibility", WIDOW), text_msg(f"You can get IGNOAPS. Source: {url}")])
    answer, trace = agent.chat("62 widow bpl")
    assert url in answer and guard_steps(trace) == []


# ---- item 5/1: caveat mentions for not_eligible schemes are not violations
def test_not_eligible_caveat_pointer_is_allowed():
    agent, _ = make([tool_msg("check_eligibility", {"profile": {"age": 65}}),
                     text_msg("You don't qualify for the 70+ card, but you may still be covered by regular PM-JAY. "
                              "Please check on the Ayushman app.")])
    _, trace = agent.chat("I am 65")
    assert guard_steps(trace) == []


# ---- item 6: empty / leaked answers
@pytest.mark.parametrize("raw, expected", [
    ("<think>reasoning</think>Answer", "Answer"),
    ("<think>reasoning that never closes", ""),
    ("Answer<think>partial reasoning", "Answer"),
    ("reasoning leaked</think>\nAnswer", "Answer"),
    ("<think>a</think><think>b", ""),
    (None, ""), ("   ", ""),
])
def test_clean_answer(raw, expected):
    assert clean_answer(raw) == expected


def test_empty_answer_retries_once_then_succeeds():
    agent, client = make([text_msg("<think>hmm</think>"), text_msg("Hello! How can I help?")])
    answer, trace = agent.chat("hi")
    assert answer == "Hello! How can I help?" and len(client.sent) == 2
    assert [m["content"] for m in agent.messages if m["role"] == "assistant"] == ["Hello! How can I help?"]


@pytest.mark.parametrize("user, check", [
    ("hello", lambda a: "Sorry" in a),
    ("मुझे पेंशन चाहिए", lambda a: sum("ऀ" <= c <= "ॿ" for c in a) > 15),
    ("mujhe pension chahiye", lambda a: "nahi" in a.lower() or "dobara" in a.lower() or "kripya" in a.lower()),
    ("எனக்கு ஓய்வூதியம் வேண்டும்", lambda a: sum("஀" <= c <= "௿" for c in a) > 15),
])
def test_persistently_empty_answer_gives_localized_error(user, check):
    agent, client = make([text_msg(""), text_msg("<think>still thinking")])
    answer, trace = agent.chat(user)
    assert answer.strip() and check(answer) and len(client.sent) == 2
    assert trace.steps[-1]["stopped"] == "empty_answer"
    assert [m["role"] for m in agent.messages] == ["system"] + ["user"]     # failed turn answer not kept as history


@pytest.mark.parametrize("user, check", [
    ("hello", lambda a: a.startswith("Sorry")),
    ("मेरी माँ विधवा हैं", lambda a: sum("ऀ" <= c <= "ॿ" for c in a) > 15),
    ("meri maa vidhwa hain", lambda a: "Maaf" in a or "maaf" in a),
    ("என் அம்மா விதவை", lambda a: sum("஀" <= c <= "௿" for c in a) > 15),
])
def test_max_steps_fallback_is_localized(user, check):
    agent, _ = make([tool_msg("search_schemes", {"query": "x"}, f"c{i}") for i in range(2)], max_steps=2)
    answer, trace = agent.chat(user)
    assert check(answer) and trace.steps[-1]["stopped"] == "max_steps"


def test_max_steps_language_ignores_numeric_followups():
    agent, _ = make([text_msg("आपकी उम्र?")] + [tool_msg("search_schemes", {"query": "x"}, f"c{i}") for i in range(2)],
                    max_steps=2)
    agent.chat("मुझे पेंशन चाहिए")
    answer, _ = agent.chat("62")
    assert sum("ऀ" <= c <= "ॿ" for c in answer) > 15


# ---- item 15: privacy
def test_pii_is_masked_before_the_model_sees_it():
    agent, client = make([text_msg("Thanks. How old is she?")])
    agent.chat("Her Aadhaar is 1234 5678 9012, PAN ABCDE1234F, phone +91 9876543210. She is a widow")
    sent = json.dumps(client.sent[0]["messages"])
    for secret in ("1234 5678 9012", "ABCDE1234F", "9876543210"):
        assert secret not in sent
    assert json.dumps(client.sent[0]["messages"][1]).count("[number removed]") == 3
    assert "privacy" in SYSTEM_PROMPT and "[number removed]" in SYSTEM_PROMPT
    assert "1234 5678" not in json.dumps(agent.messages) and "9876543210" not in json.dumps(agent.messages)


def test_traces_are_off_by_default(monkeypatch):
    from sahayak.agent import default_trace_dir
    monkeypatch.delenv("SAHAYAK_TRACES", raising=False)
    assert default_trace_dir() is None
    monkeypatch.setenv("SAHAYAK_TRACES", "1")
    assert default_trace_dir() == "traces"


def test_cli_and_streamlit_use_default_trace_dir():
    import pathlib
    root = pathlib.Path(__file__).resolve().parent.parent
    for f in ("sahayak/cli.py", "app.py"):
        src = (root / f).read_text(encoding="utf-8")
        assert 'trace_dir="traces"' not in src and "default_trace_dir" in src


# ---- item 10 (agent side): bounded model context and max_tokens
def test_history_window_keeps_turn_boundaries_and_tool_pairs():
    agent, client = make([tool_msg("check_eligibility", WIDOW, "a1"), text_msg("t1"),
                          text_msg("t2"), text_msg("t3")], max_history_turns=2)
    for q in ("one", "two", "three"):
        agent.chat(q)
    sent = client.sent[-1]["messages"]
    roles = [m["role"] for m in sent]
    assert roles == ["system", "user", "assistant", "user"]            # only the last 2 user turns, system kept
    assert sent[1]["content"] == "two"
    assert len(agent.messages) > len(sent)                              # full history is still stored
    # the turn that had the tool call is cut out whole: no orphan tool message is ever sent
    for call in client.sent:
        ids = {tc["id"] for m in call["messages"] for tc in (m.get("tool_calls") or [])}
        assert all(m["tool_call_id"] in ids for m in call["messages"] if m["role"] == "tool")


def test_max_tokens_is_passed_to_the_model():
    agent, client = make([text_msg("hi")], max_tokens=321)
    agent.chat("hello")
    assert client.sent[0]["max_tokens"] == 321
    agent, client = make([text_msg("hi")])
    agent.chat("hello")
    assert "max_tokens" not in client.sent[0]
