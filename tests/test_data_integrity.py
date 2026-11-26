"""Data hygiene: web copy in sync, rule reasons agree with rule values."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "schemes.json"


def test_web_copy_of_schemes_is_byte_identical():
    assert DATA.read_bytes() == (ROOT / "web" / "src" / "data" / "schemes.json").read_bytes()


def _numbers(text: str) -> set[int]:
    return {int(n.replace(",", "")) for n in re.findall(r"\d[\d,]*", text)}


def reason_mismatches(rule: dict) -> list[str]:
    """Numeric rule values that don't appear in the rule's reason ('60 or older' <-> 60).
    For 'lte', the reason may state the first excluded number ('Rs 10,000 or more' <-> lte 9999; 'below 10' <-> lte 9)."""
    nums = _numbers(rule["reason"])
    problems = []
    if rule["op"] == "any_child":
        subs = rule["value"]
    else:
        subs = [rule]
    for sub in subs:
        v = sub["value"]
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            continue
        ok = v in nums or (sub["op"] == "lte" and v + 1 in nums)
        if not ok:
            problems.append(f"{sub['field']} {sub['op']} {v} not in reason {rule['reason']!r}")
    return problems


def test_lint_catches_a_mismatch():
    assert reason_mismatches({"field": "age", "op": "gte", "value": 60, "reason": "Applicant must be 65 or older"})
    assert reason_mismatches({"field": "age", "op": "lte", "value": 79, "reason": "Covers ages 40-79"}) == []
    assert reason_mismatches({"field": "monthly_pension", "op": "lte", "value": 9999, "reason": "Rs 10,000 or more excluded"}) == []


def test_every_rule_reason_matches_its_value():
    schemes = json.loads(DATA.read_text(encoding="utf-8"))["schemes"]
    problems = [f"{s['id']}: {p}" for s in schemes for r in s["rules"] for p in reason_mismatches(r)]
    assert not problems, problems
