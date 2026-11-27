"""Deterministic eligibility engine.

The LLM never decides eligibility. It collects facts; this module applies the
scheme's rules and returns one of three verdicts:

  eligible      every rule passed (caveats may still apply)
  not_eligible  at least one rule failed (with the reason)
  need_info     no rule failed, but some facts are missing (lists them)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .models import Profile, Scheme
from .states import normalise_state

PASS, FAIL, UNKNOWN = "pass", "fail", "unknown"


def _compare(actual: Any, op: str, expected: Any) -> bool:
    if op == "eq":
        return actual == expected
    if op == "ne":
        return actual != expected
    if op == "gte":
        return actual >= expected
    if op == "lte":
        return actual <= expected
    if op == "in":
        return actual in expected
    raise ValueError(f"Unknown op: {op}")


def eval_condition(data: dict, cond: dict) -> tuple[str, list[str]]:
    """Return (status, missing_fields) for one condition against a dict."""
    field_name, op, expected = cond["field"], cond["op"], cond["value"]
    actual = data.get(field_name)

    if op == "any_child":
        if actual is None:
            return UNKNOWN, [field_name]
        if not actual:  # explicitly no children
            return FAIL, []
        saw_unknown = False
        for child in actual:
            statuses = [eval_condition(child, sub)[0] for sub in expected]
            if all(s == PASS for s in statuses):
                return PASS, []
            if FAIL not in statuses:
                saw_unknown = True
        return (UNKNOWN, [f"{field_name}.age/gender"]) if saw_unknown else (FAIL, [])

    if field_name == "state":
        # compare canonical names; a state we cannot recognise is unknown, never a match or a mismatch
        actual = normalise_state(actual)
        if op == "in":
            expected = [normalise_state(x) or x for x in expected]
        else:
            expected = normalise_state(expected) or expected
    if actual is None:
        return UNKNOWN, [field_name]
    return (PASS if _compare(actual, op, expected) else FAIL), []


@dataclass
class EligibilityResult:
    scheme_id: str
    scheme_name: str
    verdict: str  # eligible | not_eligible | need_info
    failed_reasons: list[str] = field(default_factory=list)
    missing_fields: list[str] = field(default_factory=list)
    caveats: list[str] = field(default_factory=list)
    benefits: str = ""
    source_url: str = ""

    def to_dict(self) -> dict:
        return self.__dict__.copy()


def check_scheme(profile: Profile, scheme: Scheme) -> EligibilityResult:
    data = profile.model_dump()
    if data.get("children") is not None:
        data["children"] = [c if isinstance(c, dict) else c.model_dump() for c in data["children"]]

    # Paying tax last year means having paid it at some point; never paying means not last year either.
    if data.get("income_tax_payer_last_year") is True and data.get("ever_income_tax_payer") is None:
        data["ever_income_tax_payer"] = True
    if data.get("ever_income_tax_payer") is False and data.get("income_tax_payer_last_year") is None:
        data["income_tax_payer_last_year"] = False

    failed, missing = [], []
    for cond in scheme.rules:
        status, miss = eval_condition(data, cond)
        if status == FAIL:
            failed.append(cond["reason"])
        elif status == UNKNOWN:
            missing.extend(miss)

    if failed:
        verdict = "not_eligible"
    elif missing:
        verdict = "need_info"
    else:
        verdict = "eligible"

    return EligibilityResult(
        scheme_id=scheme.id,
        scheme_name=scheme.name,
        verdict=verdict,
        failed_reasons=failed,
        missing_fields=sorted(set(missing)),
        caveats=scheme.caveats,
        benefits=scheme.benefits if verdict != "not_eligible" else "",
        source_url=scheme.source_url,
    )


def check_all(profile: Profile, schemes: dict[str, Scheme], ids: list[str] | None = None) -> list[EligibilityResult]:
    targets = ids or list(schemes)
    return [check_scheme(profile, schemes[i]) for i in targets if i in schemes]
