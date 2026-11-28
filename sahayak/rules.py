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

# Fields a rule may use that are not stored on Profile: they are computed from Profile facts (see derive_facts).
# value: the Profile facts that must be known to compute it (what to ask for when it is unknown).
DERIVED_FIELDS = {"per_capita_monthly_income": ("monthly_income", "household_size")}


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


def derive_facts(data: dict) -> dict:
    """Fill facts that follow from other stated facts, never guessing: an unknown stays None (-> need_info).

    - income period: monthly_income x 12 is annual_income and annual_income / 12 is monthly_income, but only when
      the other one is unknown (a stated value is never overwritten); per_capita_monthly_income needs
      household_size plus either income.
    - paying tax last year / currently means having paid it at some point; never paying means neither.
    - house_type implies has_pucca_house; owns_cultivable_land and land_holding_hectares imply each other for 0.
    """
    d = dict(data)
    if d.get("income_tax_payer_last_year") is True and d.get("ever_income_tax_payer") is None:
        d["ever_income_tax_payer"] = True
    if d.get("is_current_income_tax_payer") is True and d.get("ever_income_tax_payer") is None:
        d["ever_income_tax_payer"] = True
    if d.get("ever_income_tax_payer") is False:
        for k in ("income_tax_payer_last_year", "is_current_income_tax_payer"):
            if d.get(k) is None:
                d[k] = False

    annual, monthly = d.get("annual_income"), d.get("monthly_income")
    if annual is None and monthly is not None:
        d["annual_income"] = monthly * 12
    elif monthly is None and annual is not None:
        d["monthly_income"] = annual / 12
    size = d.get("household_size")
    if d.get("monthly_income") is not None and size:
        d["per_capita_monthly_income"] = d["monthly_income"] / size

    house = d.get("house_type")
    if d.get("has_pucca_house") is None and house is not None:
        d["has_pucca_house"] = house == "pucca"

    if d.get("owns_cultivable_land") is False and d.get("land_holding_hectares") is None:
        d["land_holding_hectares"] = 0.0
    if d.get("land_holding_hectares") is not None and d.get("owns_cultivable_land") is None:
        d["owns_cultivable_land"] = d["land_holding_hectares"] > 0
    return d


def _askable(missing: list[str], data: dict) -> list[str]:
    """Replace a computed field by the Profile facts that are still unknown and would settle it."""
    out: list[str] = []
    for f in missing:
        if f in DERIVED_FIELDS:
            out += [x for x in DERIVED_FIELDS[f] if data.get(x) is None
                    and not (x == "monthly_income" and data.get("annual_income") is not None)]
        else:
            out.append(f)
    return out


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

    data = derive_facts(data)

    failed, missing = [], []
    for cond in scheme.rules:
        status, miss = eval_condition(data, cond)
        if status == FAIL:
            failed.append(cond["reason"])
        elif status == UNKNOWN:
            missing.extend(_askable(miss, data))

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
