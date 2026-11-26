import json
from pathlib import Path

import pytest

from sahayak.models import Profile, load_schemes
from sahayak.rules import check_all

SCHEMES = load_schemes()
CASES = json.loads((Path(__file__).parent.parent / "evals" / "eligibility_cases.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_eligibility_case(case):
    results = {r.scheme_id: r for r in check_all(Profile(**case["profile"]), SCHEMES)}
    for verdict, ids in case["expect"].items():
        for sid in ids:
            assert results[sid].verdict == verdict, (
                f"{sid}: expected {verdict}, got {results[sid].verdict} "
                f"(failed={results[sid].failed_reasons}, missing={results[sid].missing_fields})")


@pytest.mark.parametrize("case", [c for c in CASES if "expect_not_eligible_caveats" in c or "expect_eligible_caveats" in c],
                         ids=lambda c: c["id"])
def test_caveats_survive_in_tool_output(case):
    """not_eligible items keep the caveat that says the person may still qualify another way."""
    from sahayak.tools import Toolbox
    out = Toolbox(search_mode="bm25").check_eligibility(case["profile"])
    for bucket, key in (("not_eligible", "expect_not_eligible_caveats"), ("eligible", "expect_eligible_caveats")):
        for sid, needle in case.get(key, {}).items():
            item = next(i for i in out[bucket] if i["scheme_id"] == sid)
            assert any(needle in c for c in item["caveats"]), (sid, item["caveats"])


def test_empty_profile_never_eligible():
    """With no facts at all, nothing may come back as eligible."""
    results = check_all(Profile(), SCHEMES)
    assert all(r.verdict != "eligible" for r in results)


def test_failure_beats_missing_info():
    """A definite failure wins over missing facts (no point asking more)."""
    r = {x.scheme_id: x for x in check_all(Profile(age=25), SCHEMES)}["ignoaps"]
    assert r.verdict == "not_eligible"


def test_not_eligible_hides_benefits():
    r = {x.scheme_id: x for x in check_all(Profile(age=25), SCHEMES)}["ignoaps"]
    assert r.benefits == ""


def test_every_scheme_has_source():
    for s in SCHEMES.values():
        assert s.source_url.startswith("https://"), s.id
