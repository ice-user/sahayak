"""Deterministic checker for one labelled eligibility bullet (the fine-tuning target).

Target shape::

    {"rules":    [{"field", "op", "value", "quote"}],
     "unmapped": [{"quote", "reason"}]}

A label passes only if: the JSON shape is exact; every rule is valid per research/fields.py and
research/validate.py (field, op, value type/range, canonical state names, no contradictions); every quote is a
verbatim (whitespace/case/quote-mark normalised) substring of the bullet; every number a rule asserts appears
in its own quote; a state rule names the state in its quote; and every number in the bullet is covered by some
quote (so a numeric condition cannot be silently dropped).
"""
from __future__ import annotations

from typing import Any

from sahayak.states import STATES

from .evidence import find_quote, normalize, numbers_in, value_in_evidence
from .fields import PROFILE_FIELDS
from .validate import _contradictions, _numeric_values, _state_named, check_condition

RULE_KEYS = {"field", "op", "value", "quote"}
UNMAPPED_KEYS = {"quote", "reason"}
MAX_REASON_CHARS = 160


def _quote_problem(quote: Any, bullet: str, where: str) -> str | None:
    if not isinstance(quote, str) or not quote.strip():
        return f"{where}: quote must be a non-empty string"
    if ("..." in quote or "…" in quote) and not ("..." in bullet or "…" in bullet):
        return f"{where}: quote must be one contiguous span of the bullet (no ellipsis)"
    m = find_quote(quote, bullet)
    if not m.found:
        return f"{where}: quote is not a verbatim substring of the bullet ({m.method}): {quote[:80]!r}"
    if m.method != "exact":
        return f"{where}: quote only matches approximately; it must be verbatim: {quote[:80]!r}"
    return None


def check_label(label: Any, bullet: str) -> list[str]:
    """Return a list of problems (empty list = the label passes)."""
    if not isinstance(label, dict):
        return ["label must be a JSON object"]
    if set(label) != {"rules", "unmapped"}:
        return [f"label keys must be exactly 'rules' and 'unmapped', got {sorted(label)}"]
    rules, unmapped = label["rules"], label["unmapped"]
    if not isinstance(rules, list) or not isinstance(unmapped, list):
        return ["'rules' and 'unmapped' must both be lists"]
    errs: list[str] = []
    quotes: list[str] = []
    good_rules: list[dict] = []
    for i, r in enumerate(rules):
        where = f"rules[{i}]"
        if not isinstance(r, dict) or set(r) != RULE_KEYS:
            errs.append(f"{where}: keys must be exactly {sorted(RULE_KEYS)}")
            continue
        n0 = len(errs)
        errs += check_condition({"field": r["field"], "op": r["op"], "value": r["value"]}, PROFILE_FIELDS,
                                where, top=True)
        q = _quote_problem(r["quote"], bullet, where)
        if q:
            errs.append(q)
            continue
        quotes.append(r["quote"])
        for v, op, fld in _numeric_values(r["value"], r["op"], r["field"]):
            if not value_in_evidence(v, r["quote"], op=op, field=fld):
                errs.append(f"{where}: number {v} for {fld} does not appear in its quote")
        if r["field"] == "state" and r["op"] in ("eq", "in"):
            vals = r["value"] if isinstance(r["value"], list) else [r["value"]]
            low = r["quote"].casefold().replace("&", "and")
            for v in vals:
                if isinstance(v, str) and v in STATES and not _state_named(v, low):
                    errs.append(f"{where}: state {v!r} is not named in its quote")
        if len(errs) == n0:
            good_rules.append(r)
    for i, u in enumerate(unmapped):
        where = f"unmapped[{i}]"
        if not isinstance(u, dict) or set(u) != UNMAPPED_KEYS:
            errs.append(f"{where}: keys must be exactly {sorted(UNMAPPED_KEYS)}")
            continue
        reason = u["reason"]
        if not isinstance(reason, str) or not reason.strip() or len(reason) > MAX_REASON_CHARS:
            errs.append(f"{where}: reason must be a short non-empty string")
        q = _quote_problem(u["quote"], bullet, where)
        if q:
            errs.append(q)
        else:
            quotes.append(u["quote"])
    if not errs and good_rules:
        e, _ = _contradictions([{"field": r["field"], "op": r["op"], "value": r["value"]} for r in good_rules])
        errs += e
    if not errs:
        covered: set = set()
        for q in quotes:
            covered |= set(numbers_in(q))
        missing = sorted(format(n, "f") for n in set(numbers_in(bullet)) - covered)
        if missing:
            errs.append(f"numbers in the bullet are in neither a rule nor an unmapped quote: {', '.join(missing)}")
    return errs


def is_valid(label: Any, bullet: str) -> bool:
    return not check_label(label, bullet)


def canonical(label: dict) -> str:
    """Stable text form used for dedupe/comparison."""
    import json
    return json.dumps(label, sort_keys=True, ensure_ascii=False)
