"""Offline regression gate for evals/agent_cases.json: no LLM.

Each case's profile goes through the deterministic rule engine and must produce exactly the verdict sets the case
records under "expect" (so a change to data/schemes.json or sahayak/rules.py that flips a verdict fails here, not in
a paid eval run). The hand-written expectations the LLM eval scores (expect_eligible, expect_not_claimed,
expect_followup) must agree with those verdicts.
"""
import json
from pathlib import Path

import pytest

from sahayak.models import Profile, load_schemes
from sahayak.rules import check_all

CASES = json.loads((Path(__file__).resolve().parent.parent / "evals" / "agent_cases.json").read_text(encoding="utf-8"))
PROFILED = [c for c in CASES if "profile" in c]
SCHEMES = load_schemes()


def verdicts(profile: dict) -> dict[str, set[str]]:
    results = check_all(Profile(**profile), SCHEMES)
    return {v: {r.scheme_id for r in results if r.verdict == v} for v in ("eligible", "not_eligible", "need_info")}


def test_case_ids_unique_and_schema():
    ids = [c["id"] for c in CASES]
    assert len(ids) == len(set(ids))
    for c in CASES:
        assert {"id", "lang", "query", "expect_eligible"} <= set(c), c["id"]
        assert c["lang"] in ("en", "hi", "ta", "hinglish"), c["id"]
        assert c["id"].split("_")[0] == c["lang"], c["id"]


def test_suite_is_broad_enough():
    assert len(CASES) >= 40
    assert {c["lang"] for c in CASES} == {"en", "hi", "ta", "hinglish"}
    covered = {s for c in PROFILED for s in c["expect"]["eligible"] + c["expect"]["not_eligible"]}
    assert covered == set(SCHEMES), "every scheme in data/schemes.json needs an eligible or not_eligible case"
    positive = {s for c in PROFILED for s in c["expect_eligible"]}
    assert positive == set(SCHEMES), f"no positive case for {set(SCHEMES) - positive}"
    assert any(c.get("expect_followup") and c["expect"]["need_info"] for c in PROFILED)
    assert sum(1 for c in CASES if c.get("expect_not_claimed")) >= 10


@pytest.mark.parametrize("case", PROFILED, ids=lambda c: c["id"])
def test_rule_engine_matches_case(case):
    got = verdicts(case["profile"])
    exp = case["expect"]
    assert got == {k: set(exp[k]) for k in ("eligible", "not_eligible", "need_info")}


@pytest.mark.parametrize("case", PROFILED, ids=lambda c: c["id"])
def test_llm_expectations_agree_with_engine(case):
    got = verdicts(case["profile"])
    assert set(case["expect_eligible"]) <= got["eligible"]
    # a scheme the answer must not offer has to be one the engine really rejects
    assert set(case.get("expect_not_claimed", [])) <= got["not_eligible"]
    if case.get("expect_followup"):
        assert got["need_info"], "a follow-up case needs at least one missing fact"


def test_cases_without_profile_expect_nothing():
    for c in CASES:
        if "profile" not in c:
            assert c["expect_eligible"] == []
