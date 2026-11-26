import json

from sahayak.datagen.grader import grade, script_ok
from sahayak.datagen.profiles import generate
from sahayak.datagen.run import load_scenarios, run, run_episode, save_scenarios
from sahayak.datagen.simuser import SimUser
from sahayak.tools import Toolbox

TB = Toolbox(search_mode="bm25")
SCEN = generate(200, seed=7)


def _turn(revealed, args, answer, stopped=False):
    return {"revealed": set(revealed), "revealed_after": set(revealed), "answer": answer, "stopped": stopped,
            "tool_calls": [{"name": "check_eligibility", "arguments": json.dumps({"profile": args})}]}


def _widow():
    return next(s for s in SCEN if s.persona == "elderly_widow" and s.profile["bpl"] and s.lang == "en")


def test_generation_is_deterministic():
    assert [s.opening for s in generate(20, seed=3)] == [s.opening for s in generate(20, seed=3)]


def test_profiles_are_consistent():
    for s in generate(500, seed=11):
        p = s.profile
        assert p["is_govt_employee"] == p["in_regular_govt_employment"]
        if p["pregnant_or_lactating"]:
            assert p["gender"] == "female"
        for c in p["children"]:
            assert 18 <= p["age"] - c["age"] <= 45


def test_language_mix_and_script():
    langs = {s.lang for s in SCEN}
    assert langs == {"en", "hi", "hinglish", "ta"}
    for s in SCEN:
        if s.lang in ("hi", "ta"):
            assert script_ok(s.opening + " " * 0 + s.opening, s.lang)


def test_simuser_answers_only_missing_fields():
    s = _widow()
    sim = SimUser(s, dont_know_rate=0)
    tool_result = {"need_info": [{"scheme_id": "x", "missing_fields": ["has_bank_account"]}]}
    msgs = [{"role": "assistant", "content": "", "tool_calls": [{"id": "c1", "function": {"name": "check_eligibility"}}]},
            {"role": "tool", "tool_call_id": "c1", "content": json.dumps(tool_result)},
            {"role": "assistant", "content": "Does she have a bank account?"}]
    reply = sim.reply(msgs)
    assert "bank account" in reply and "has_bank_account" in sim.revealed


def test_simuser_ends_after_final_answer():
    sim = SimUser(_widow())
    assert sim.reply([{"role": "assistant", "content": "She can get IGNOAPS."}]) is None


def test_grader_passes_good_conversation():
    s = _widow()
    known = {k: s.profile[k] for k in s.revealed}
    from sahayak.models import Profile
    from sahayak.rules import check_all
    eligible = [r.scheme_name for r in check_all(Profile(**known), TB.schemes) if r.verdict == "eligible"]
    g = grade(s, [_turn(s.revealed, known, "She can get: " + "; ".join(eligible) + ".")])
    assert g["passed"], g["reasons"]


def test_grader_rejects_guessed_fact():
    s = _widow()
    hidden = next(f for f in ("has_bank_account", "ever_income_tax_payer", "owns_cultivable_land") if f not in s.revealed)
    args = {**{k: s.profile[k] for k in s.revealed}, hidden: s.profile[hidden]}
    g = grade(s, [_turn(s.revealed, args, "IGNOAPS")])
    assert not g["checks"]["facts_ok"] and any("guessed" in r for r in g["reasons"])


def test_grader_rejects_wrong_value():
    s = _widow()
    args = {k: s.profile[k] for k in s.revealed}
    args["age"] = s.profile["age"] - 30
    assert not grade(s, [_turn(s.revealed, args, "x")])["checks"]["facts_ok"]


def test_grader_rejects_false_claim_and_wrong_language():
    s = _widow()
    args = {k: s.profile[k] for k in s.revealed}
    g = grade(s, [_turn(s.revealed, args, "You can get Atal Pension Yojana (APY). आप पात्र हैं")])
    assert not g["checks"]["no_false_claim"]
    hi = next(x for x in SCEN if x.lang == "hi")
    g2 = grade(hi, [_turn(hi.revealed, {}, "Only English here.")])
    assert not g2["checks"]["language_ok"]


def test_oracle_episodes_pass_and_export_dict_arguments():
    passed = 0
    for s in SCEN[:60]:
        rec = run_episode(s, "oracle", TB)
        passed += rec["grade"]["passed"]
        calls = [tc for m in rec["messages"] for tc in (m.get("tool_calls") or [])]
        assert calls and all(isinstance(tc["function"]["arguments"], dict) for tc in calls)
        assert rec["messages"][0]["role"] == "system"
    assert passed == 60


def test_run_is_resumable(tmp_path):
    scen = tmp_path / "s.jsonl"
    save_scenarios(30, 1, scen)
    assert len(load_scenarios(scen)) == 30
    run(scen, tmp_path / "out", "oracle", workers=2, limit=10, paraphrase=False, model=None)
    run(scen, tmp_path / "out", "oracle", workers=2, limit=None, paraphrase=False, model=None)
    ids = [json.loads(line)["id"] for line in open(tmp_path / "out" / "train.jsonl", encoding="utf-8")]
    assert len(ids) == len(set(ids)) == 30
