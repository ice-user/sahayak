"""evals/judge.py: JSON parsing, deterministic checks, and the judge flow with a fake client (no network)."""
import json
from types import SimpleNamespace as NS

from evals import judge as J
from evals.run_agent_evals import summarize, threshold_failures
from sahayak.models import load_schemes

SCHEMES = load_schemes()
WIDOW = {"id": "w", "lang": "en", "query": "I am 62, a widow, BPL.",
         "profile": {"age": 62, "gender": "female", "marital_status": "widowed", "bpl": True, "has_bank_account": True},
         "expect_eligible": ["ignwps", "ignoaps"], "expect_tool": "check_eligibility"}
GOOD = ("You can get the Indira Gandhi National Widow Pension Scheme (IGNWPS): Rs 300/month. "
        "Documents: Aadhaar, BPL card. Apply at the Gram Panchayat. Source: " + SCHEMES["ignwps"].source_url)


class FakeClient:
    def __init__(self, *replies):
        self.replies, self.calls = list(replies), []
        self.chat = NS(completions=NS(create=self._create))

    def _create(self, **kw):
        self.calls.append(kw)
        r = self.replies.pop(0)
        if isinstance(r, Exception):
            raise r
        return NS(choices=[NS(message=NS(content=r, tool_calls=None))], usage=None)


def reply(f=4, lang=5, c=4):
    return json.dumps({k: {"score": v, "rationale": "ok"} for k, v in
                       (("faithfulness", f), ("language_match", lang), ("completeness", c))})


# ----------------------------------------------------------------------------- parsing
def test_parse_plain_and_fenced_and_prose():
    raw = reply(4, 5, 3)
    for wrapped in (raw, f"```json\n{raw}\n```", f"Here you go: {raw} Hope this helps", f"<think>{{x}}</think>{raw}"):
        got = J.parse_judge_json(wrapped)
        assert {k: v["score"] for k, v in got.items()} == {"faithfulness": 4, "language_match": 5, "completeness": 3}


def test_parse_clamps_and_coerces():
    got = J.parse_judge_json('{"faithfulness": {"score": 9, "rationale": "r"}, "language_match": "4/5", "completeness": 0.2}')
    assert got["faithfulness"]["score"] == 5 and got["language_match"]["score"] == 4 and got["completeness"]["score"] == 1


def test_parse_flat_and_nested_scores_shapes():
    flat = J.parse_judge_json('{"faithfulness": 3, "faithfulness_rationale": "why", "completeness_score": 2}')
    assert flat["faithfulness"] == {"score": 3, "rationale": "why"} and flat["completeness"]["score"] == 2
    nested = J.parse_judge_json('{"scores": {"faithfulness": {"score": 2}}}')
    assert nested["faithfulness"]["score"] == 2


def test_parse_garbage_never_raises():
    for raw in ("", None, "not json", "{", '{"faithfulness": {"score": "n/a"}}', "[1,2]", '{"faithfulness": true}'):
        assert J.parse_judge_json(raw) == {}


def test_parse_prefers_the_object_with_most_criteria():
    got = J.parse_judge_json('{"faithfulness": 1} then {"faithfulness": 4, "language_match": 5, "completeness": 5}')
    assert got["faithfulness"]["score"] == 4 and len(got) == 3


# ------------------------------------------------------------------------ deterministic checks
def test_ground_truth_from_rule_engine():
    t = J.ground_truth(WIDOW, SCHEMES)
    assert {"ignwps", "ignoaps"} <= set(t["eligible"]) and "apy" in t["not_eligible"]
    assert J.ground_truth({"id": "x", "query": "q"}, SCHEMES) is None


def test_offering_a_not_eligible_scheme_is_decided_by_code():
    det = J.deterministic_checks(WIDOW, "You can get PM-JAY Ayushman Vay Vandana health cover.", SCHEMES)
    assert det["decided"]["faithfulness"][0] == 1
    assert det["violations"] == [{"scheme": "pmjay_senior", "verdict": "not_eligible"}]


def test_negated_scheme_is_not_a_violation():
    det = J.deterministic_checks(WIDOW, "You are not eligible for APY. You can get IGNWPS.", SCHEMES)
    assert det["violations"] == [] and "faithfulness" not in det["decided"]


def test_need_info_scheme_offered_caps_faithfulness_at_2():
    case = {**WIDOW, "profile": {"age": 62, "gender": "female", "marital_status": "widowed", "bpl": True}}
    det = J.deterministic_checks(case, "You can get PMSBY accident insurance.", SCHEMES)
    assert det["violations"][0]["verdict"] == "need_info" and det["caps"]["faithfulness"][0] == 2


def test_unsupported_amounts_flagged_but_data_and_user_numbers_allowed():
    assert J.unsupported_amounts("Rs 300/month, Rs 2 lakh cover, Rs 6,000 a year", WIDOW, SCHEMES) == []
    assert J.unsupported_amounts("You get Rs 12345 monthly and Rs 300", WIDOW, SCHEMES) == ["12345"]
    assert J.unsupported_amounts("my income is Rs 90,000", {**WIDOW, "query": "income Rs 90,000"}, SCHEMES) == []


def test_language_checks():
    assert J.language_check("hi", "आप विधवा पेंशन के लिए पात्र हैं")[0] == 5
    assert J.language_check("hi", "You are eligible for the widow pension")[0] == 1
    assert J.language_check("ta", "நீங்கள் விதவை ஓய்வூதியத்திற்கு தகுதி")[0] == 5
    assert J.language_check("en", "You can apply at the Gram Panchayat.")[0] == 5
    assert J.language_check("en", "आप पात्र हैं")[0] == 1
    assert J.language_check("hinglish", "आप पात्र हैं")[0] == 2
    assert J.language_check("hinglish", "Aap IGNWPS ke liye eligible hain, lekin aapko apply karna hoga")[0] == 5
    assert J.language_check("hinglish", "You can apply at the office.")[0] is None


def test_missing_source_and_followup_caps():
    det = J.deterministic_checks(WIDOW, "You can get IGNWPS, Rs 300/month. Apply at the Gram Panchayat.", SCHEMES)
    assert det["missing_sources"] == ["ignwps"] and det["caps"]["completeness"][0] == 3
    ok = J.deterministic_checks(WIDOW, GOOD, SCHEMES)
    assert ok["missing_sources"] == [] and "completeness" not in ok["caps"]
    ask = J.deterministic_checks({"id": "v", "lang": "en", "query": "farmer", "profile": {}, "expect_followup": True,
                                  "expect_eligible": []}, "Here are some schemes for farmers.", SCHEMES)
    assert ask["caps"]["completeness"][0] == 2


# ------------------------------------------------------------------------------- the judge
def test_empty_answer_scores_one_with_no_llm_call():
    client = FakeClient()
    out = J.Judge(client=client, model="m", schemes=SCHEMES).judge(WIDOW, "  ")
    assert [out[c]["score"] for c in J.CRITERIA] == [1, 1, 1] and client.calls == []


def test_llm_scores_only_what_code_could_not_decide():
    client = FakeClient(json.dumps({"faithfulness": {"score": 5, "rationale": "matches"},
                                    "completeness": {"score": 4, "rationale": "all there"}}))
    out = J.Judge(client=client, model="m", schemes=SCHEMES).judge(WIDOW, GOOD)
    assert out["language_match"]["source"] == "code"
    assert out["faithfulness"] == {"score": 5, "rationale": "matches", "source": "llm"}
    assert out["completeness"]["score"] == 4 and "error" not in out
    prompt = client.calls[0]["messages"][1]["content"]
    assert "Criteria to score: faithfulness, completeness" in prompt and "ignwps" in prompt
    assert client.calls[0]["temperature"] == 0 and client.calls[0]["model"] == "m"


def test_code_caps_override_an_overgenerous_judge():
    answer = "You can get IGNWPS, Rs 300/month. Apply at the Gram Panchayat. You also get Rs 99999."
    client = FakeClient(reply(5, 5, 5))
    out = J.Judge(client=client, model="m", schemes=SCHEMES).judge(WIDOW, answer)
    assert out["faithfulness"]["score"] == 3 and out["faithfulness"]["source"] == "llm+cap"
    assert out["completeness"]["score"] == 3  # no source link


def test_hard_violation_skips_llm_for_faithfulness():
    client = FakeClient(json.dumps({"completeness": {"score": 2, "rationale": "thin"}}))
    out = J.Judge(client=client, model="m", schemes=SCHEMES).judge(WIDOW, "You can get PM-JAY Ayushman cover.")
    assert out["faithfulness"]["score"] == 1 and out["faithfulness"]["source"] == "code"
    assert "Criteria to score: completeness" in client.calls[0]["messages"][1]["content"]


def test_unparsable_judge_reply_leaves_scores_none_not_guesses():
    out = J.Judge(client=FakeClient("I think it is fine!"), model="m", schemes=SCHEMES).judge(WIDOW, GOOD)
    assert out["faithfulness"]["score"] is None and out["completeness"]["score"] is None
    assert out["language_match"]["score"] == 5 and "no parsable scores" in out["error"]


def test_provider_error_is_captured_not_raised():
    class Boom(Exception):
        status_code = 401

    out = J.Judge(client=FakeClient(Boom("bad key")), model="m", schemes=SCHEMES, delays=()).judge(WIDOW, GOOD)
    assert out["faithfulness"]["score"] is None and "Boom" in out["error"]


# --------------------------------------------------------------------- summary and thresholds
def test_summary_includes_judge_means_and_thresholds():
    def row(f):
        return {"latency_s": 1, "llm_calls": 1, "tokens": 1, "used_tool": True,
                "judge": {"faithfulness": {"score": f}, "language_match": {"score": 5}, "completeness": {"score": None}}}

    s = summarize([row(5), row(3), {"error": "x", "latency_s": 1}])
    assert s["judge_faithfulness_mean"] == 4.0 and s["judge_language_match_mean"] == 5.0
    assert s["judge_completeness_mean"] is None and s["judged"] == 2
    assert "judge_faithfulness_mean" not in summarize([{"latency_s": 1, "llm_calls": 1, "tokens": 1, "used_tool": True}])
    assert threshold_failures({"pass_rate": 0.8, "judge_faithfulness_mean": 3.9}, 0.85, 4)
    assert threshold_failures({"pass_rate": 0.9}, 0.85, 4)  # missing faithfulness counts as a failure
    assert threshold_failures({"pass_rate": 0.9, "judge_faithfulness_mean": 4.2}, 0.85, 4) == []
