"""Deterministic validation of a candidate record.

Three layers: (1) structure and typing of every rule against ``Profile``; (2) cross-record checks
(id format/uniqueness, source_url, contradictions); (3) behavioural boundary tests that build
profiles from the rules and require the real engine (``sahayak.rules.check_scheme``) to agree.
Everything returns plain strings so they can be fed back to the LLM verbatim.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

from pydantic import ValidationError

from sahayak.models import Profile, Scheme
from sahayak.rules import check_scheme

from sahayak.states import STATES, normalise_state

from .evidence import normalize, numbers_in, value_in_evidence
from .fields import CHILD_FIELDS, NUMERIC, OPS, PERIOD_OF, PROFILE_FIELDS, FieldSpec
from .schema import ExtractedScheme, to_scheme_dict

SNAKE = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$")
BIG = 10**12


def _bounds(spec: FieldSpec) -> tuple[float, float]:
    """Valid range of a numeric field, derived from the Profile/Child model (ge/le), never hard-coded here."""
    return (spec.lo if spec.lo is not None else 0), (spec.hi if spec.hi is not None else BIG)


def _step(spec: FieldSpec) -> float:
    """Smallest meaningful change of a numeric field: 1 for integers, 0.1 for fractional ones (hectares)."""
    return 1 if spec.kind == "int" else 0.1


def _num(x: float, spec: FieldSpec):
    return round(x, 6) if spec.kind == "float" else x


@dataclass
class Validation:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    is_update: bool = False
    checks_run: int = 0


# ---------------------------------------------------------------- rule typing

def _value_ok(spec: FieldSpec, v: Any) -> str | None:
    """Return a problem description, or None if ``v`` is a valid single value for the field."""
    if spec.kind == "bool":
        return None if isinstance(v, bool) else f"must be true/false, got {v!r}"
    if spec.kind in NUMERIC:
        if isinstance(v, bool) or not isinstance(v, int if spec.kind == "int" else (int, float)):
            return f"must be {'an integer' if spec.kind == 'int' else 'a number'}, got {v!r}"
        lo, hi = _bounds(spec)
        if not lo <= v <= hi:
            return f"must be within {lo}..{hi} (the range Profile accepts), got {v}"
        return None
    if spec.kind == "enum":
        return None if v in spec.choices else f"must be one of {list(spec.choices)}, got {v!r}"
    if spec.kind == "state":
        if isinstance(v, str) and v in STATES:
            return None
        hint = normalise_state(v)
        return (f"must be spelled exactly as a canonical state/UT name; use {hint!r}" if hint
                else f"is not a recognised Indian state/UT name, got {v!r} (allowed: {list(STATES)})")
    if spec.kind == "str":
        return None if isinstance(v, str) and v.strip() else f"must be a non-empty string, got {v!r}"
    return "unsupported field kind"


def check_condition(cond: dict, specs: dict[str, FieldSpec], where: str, *, top: bool) -> list[str]:
    """Validate one condition dict (top-level rule or any_child sub-condition)."""
    errs: list[str] = []
    f, op, val = cond.get("field"), cond.get("op"), cond.get("value")
    if f not in specs:
        scope = "Profile" if top else "Child"
        return [f"{where}: field {f!r} does not exist on {scope} (allowed: {sorted(specs)}). "
                "Do not invent fields; move this criterion to unmapped_criteria."]
    if op not in OPS:
        return [f"{where}: unknown op {op!r} (allowed: {list(OPS)})"]
    spec = specs[f]
    if spec.kind == "children":
        if op != "any_child":
            return [f"{where}: field 'children' only supports op 'any_child'"]
        if not top:
            return [f"{where}: nested any_child is not supported"]
        if not isinstance(val, list) or not val:
            return [f"{where}: any_child value must be a non-empty list of sub-conditions"]
        for j, sub in enumerate(val):
            if not isinstance(sub, dict):
                errs.append(f"{where}.value[{j}]: sub-condition must be an object")
                continue
            errs += check_condition(sub, CHILD_FIELDS, f"{where}.value[{j}]", top=False)
        return errs
    if op == "any_child":
        return [f"{where}: op 'any_child' is only valid on field 'children'"]
    if spec.kind == "state" and op == "ne":
        return [f"{where}: state only supports eq or in (a scheme limited to some states); express exclusions as "
                "an unmapped criterion"]
    if op in ("gte", "lte"):
        if spec.kind not in NUMERIC:
            return [f"{where}: op {op} needs a numeric field, but {f} is {spec.kind}"]
        p = _value_ok(spec, val)
        return [f"{where}: value for {f} {p}"] if p else []
    if op in ("eq", "ne"):
        p = _value_ok(spec, val)
        return [f"{where}: value for {f} {p}"] if p else []
    if op == "in":
        if not isinstance(val, list) or not val:
            return [f"{where}: op 'in' needs a non-empty list value"]
        if spec.kind == "bool":
            return [f"{where}: op 'in' makes no sense on boolean field {f}"]
        for x in val:
            p = _value_ok(spec, x)
            if p:
                errs.append(f"{where}: list item for {f} {p}")
    return errs


def _contradictions(rules: list[dict]) -> tuple[list[str], list[str]]:
    errors, warnings = [], []
    by_field: dict[str, list[dict]] = {}
    for r in rules:
        if r.get("field") in PROFILE_FIELDS and r.get("op") != "any_child":
            by_field.setdefault(r["field"], []).append(r)
    seen = set()
    for r in rules:
        key = repr((r.get("field"), r.get("op"), r.get("value")))
        if key in seen:
            warnings.append(f"duplicate rule: {r.get('field')} {r.get('op')} {r.get('value')!r}")
        seen.add(key)
    for f, rs in by_field.items():
        spec = PROFILE_FIELDS[f]
        if spec.kind in NUMERIC:
            lo = max((r["value"] for r in rs if r["op"] == "gte"), default=None)
            hi = min((r["value"] for r in rs if r["op"] == "lte"), default=None)
            eqs = {r["value"] for r in rs if r["op"] == "eq"}
            if lo is not None and hi is not None and lo > hi:
                errors.append(f"contradictory rules on {f}: >= {lo} and <= {hi} can never both hold")
            if len(eqs) > 1:
                errors.append(f"contradictory rules on {f}: equal to several different values {sorted(eqs)}")
            for e in eqs:
                if (lo is not None and e < lo) or (hi is not None and e > hi):
                    errors.append(f"contradictory rules on {f}: eq {e} lies outside the gte/lte bounds")
        allowed: set | None = None
        for r in rs:
            if r["op"] == "eq":
                s = {r["value"]}
            elif r["op"] == "in":
                s = set(r["value"])
            else:
                continue
            allowed = s if allowed is None else allowed & s
        if allowed is not None:
            for r in rs:
                if r["op"] == "ne":
                    allowed.discard(r["value"])
            if not allowed and spec.kind not in NUMERIC:
                errors.append(f"contradictory rules on {f}: no value satisfies all eq/in/ne rules")
    return errors, warnings


# ---------------------------------------------------------------- behavioural tests

def _satisfying_value(spec: FieldSpec, rs: list[dict]) -> Any:
    eq = [r["value"] for r in rs if r["op"] == "eq"]
    if eq:
        return eq[0]
    ins = [set(r["value"]) for r in rs if r["op"] == "in"]
    ne = {r["value"] for r in rs if r["op"] == "ne"}
    if ins:
        cands = [v for v in sorted(set.intersection(*ins), key=repr) if v not in ne]
        return cands[0] if cands else None
    if spec.kind in NUMERIC:
        lo = max((r["value"] for r in rs if r["op"] == "gte"), default=None)
        hi = min((r["value"] for r in rs if r["op"] == "lte"), default=None)
        v = lo if lo is not None else (hi if hi is not None else 30)
        while v in ne:
            v += _step(spec)
        return v
    if spec.kind == "bool":
        return (not next(iter(ne))) if ne else True
    if spec.kind == "enum":
        return next((c for c in spec.choices if c not in ne), None)
    if spec.kind == "state":
        return next((s for s in STATES if s not in ne), None)
    return next((s for s in ("Karnataka", "Kerala", "Bihar") if s not in ne), "Zz")


def _child_for(subs: list[dict]) -> dict:
    out: dict = {}
    for f in {s["field"] for s in subs}:
        out[f] = _satisfying_value(CHILD_FIELDS[f], [s for s in subs if s["field"] == f])
    return out


def _to_profile_dict(d: dict) -> dict:
    """Computed fields are not Profile fields: per_capita_monthly_income=v becomes a household of one with that
    monthly income (an explicit household_size / income in the same dict wins)."""
    out = {k: v for k, v in d.items() if not PROFILE_FIELDS.get(k, FieldSpec(k, "str")).derived}
    if "per_capita_monthly_income" in d:
        out.setdefault("household_size", 1)
        out.setdefault("monthly_income", int(d["per_capita_monthly_income"] * out["household_size"]))
    return out


def _verdict(scheme: Scheme, profile_dict: dict) -> str:
    return check_scheme(Profile(**_to_profile_dict(profile_dict)), scheme).verdict


def behavioural_checks(scheme: Scheme) -> tuple[list[str], int]:
    """Generate boundary profiles from the rules and compare engine verdicts to expectations."""
    errors: list[str] = []
    n = 0
    rules = scheme.rules
    plain = [r for r in rules if r["op"] != "any_child"]
    child_rules = [r for r in rules if r["op"] == "any_child"]
    used = {r["field"] for r in plain}
    if "per_capita_monthly_income" in used and used & {"household_size", "monthly_income", "annual_income"}:
        return [], 0  # a computed field plus its inputs in one scheme: no safe boundary profile to generate
    base: dict[str, Any] = {}
    for f in used:
        v = _satisfying_value(PROFILE_FIELDS[f], [r for r in plain if r["field"] == f])
        if v is None:
            return [], 0  # contradiction already reported elsewhere
        base[f] = v
    for r in child_rules:
        base.setdefault("children", []).append(_child_for(r["value"]))

    def expect(label: str, profile: dict, want: str):
        nonlocal n
        n += 1
        try:
            got = _verdict(scheme, profile)
        except Exception as e:  # engine or Profile rejected the generated profile
            errors.append(f"behavioural test '{label}' crashed: {e}")
            return
        if got != want:
            errors.append(f"behavioural test '{label}': expected {want} but engine said {got} (profile {profile})")

    if rules:
        expect("empty profile is never eligible", {}, "need_info")
        expect("profile built from the rules is eligible", base, "eligible")
    for r in plain:
        f, op, v = r["field"], r["op"], r["value"]
        spec = PROFILE_FIELDS[f]
        others = [x for x in plain if x["field"] == f and x is not r]

        def with_value(val):
            return {**base, f: val}

        def fits_others(val):
            return all(_cmp(val, x["op"], x["value"]) for x in others)

        if op == "gte":
            below = _num(v - _step(spec), spec)
            if fits_others(v):
                expect(f"{f} at threshold {v}", with_value(v), "eligible")
            if below >= _bounds(spec)[0] and fits_others(below):
                expect(f"{f} just below threshold ({below})", with_value(below), "not_eligible")
        elif op == "lte":
            above = _num(v + _step(spec), spec)
            if fits_others(v):
                expect(f"{f} at limit {v}", with_value(v), "eligible")
            if above <= _bounds(spec)[1] and fits_others(above):
                expect(f"{f} just above limit ({above})", with_value(above), "not_eligible")
        elif op == "eq":
            alt = _other_value(spec, v)
            if alt is not None and fits_others(alt):
                expect(f"{f} differs from required {v!r}", with_value(alt), "not_eligible")
        elif op == "ne":
            expect(f"{f} equals excluded {v!r}", with_value(v), "not_eligible")
        elif op == "in":
            out_val = _outside(spec, v)
            if out_val is not None and fits_others(out_val):
                expect(f"{f} outside allowed list", with_value(out_val), "not_eligible")
    for r in child_rules:
        expect("no children fails any_child", {**{k: x for k, x in base.items() if k != "children"},
                                                "children": []}, "not_eligible")
        if len(child_rules) != 1:
            continue
        for sub in r["value"]:
            alt = _flip_child(sub)
            if alt is not None:
                bad_child = {**_child_for(r["value"]), sub["field"]: alt}
                expect(f"only child violates {sub['field']} {sub['op']} {sub['value']!r}",
                       {**base, "children": [bad_child]}, "not_eligible")
    return errors, n


def _other_value(spec: FieldSpec, v):
    """Some valid value of the field different from ``v`` (None if impossible)."""
    if spec.kind == "bool":
        return not v
    if spec.kind == "enum":
        return next((c for c in spec.choices if c != v), None)
    if spec.kind in NUMERIC:
        alt = _num(v + _step(spec), spec)
        return None if alt > _bounds(spec)[1] else alt
    if spec.kind == "state":
        return next((s for s in STATES if s != v), None)
    return "Other-State"


def _cmp(actual, op, expected) -> bool:
    return {"eq": lambda: actual == expected, "ne": lambda: actual != expected,
            "gte": lambda: actual >= expected, "lte": lambda: actual <= expected,
            "in": lambda: actual in expected}[op]()


def _outside(spec: FieldSpec, allowed: list):
    if spec.kind == "enum":
        return next((c for c in spec.choices if c not in allowed), None)
    if spec.kind in NUMERIC:
        top = _num(max(allowed) + _step(spec), spec)
        return top if top <= _bounds(spec)[1] else None
    if spec.kind == "state":
        return next((s for s in STATES if s not in allowed), None)
    return "Zz-Not-Listed"


def _flip_child(sub: dict):
    spec = CHILD_FIELDS[sub["field"]]
    op, v = sub["op"], sub["value"]
    if op == "gte":
        return v - 1 if v - 1 >= _bounds(spec)[0] else None
    if op == "lte":
        return v + 1 if v + 1 <= _bounds(spec)[1] else None
    if op == "eq":
        return _other_value(spec, v)
    if op == "ne":
        return v
    if op == "in":
        return _outside(spec, v)
    return None


# ---------------------------------------------------------------- entry point

def _numeric_values(rule_value: Any, op: str, field: str) -> list[tuple[int, str, str]]:
    """(value, op, field) for every integer a rule asserts (top level, ``in`` lists, any_child sub-conditions)."""
    if op == "any_child" and isinstance(rule_value, list):
        out: list[tuple[int, str, str]] = []
        for sub in rule_value:
            if isinstance(sub, dict):
                out += _numeric_values(sub.get("value"), str(sub.get("op")), str(sub.get("field")))
        return out
    vals = rule_value if isinstance(rule_value, list) else [rule_value]
    return [(v, op, field) for v in vals if isinstance(v, (int, float)) and not isinstance(v, bool)]


_MONTHLY_QUOTE = re.compile(r"\b(?:per month|a month|monthly|each month|every month|per mensem|p\.m\.)|/\s*month|"
                            r"प्रति माह|प्रतिमाह|मासिक|महीने|மாதம்|மாத")
_ANNUAL_QUOTE = re.compile(r"\b(?:per annum|per year|a year|annual|annually|yearly|each year|every year|p\.a\.)|"
                           r"/\s*(?:year|annum)|प्रति वर्ष|वार्षिक|सालाना|ஆண்டு")
_AREA_UNITS = re.compile(r"\b(?:acres?|bighas?|gunthas?|kanals?|cents?|sq\.? ?(?:m|ft|metres?|feet))\b")


def quote_period(quote: str) -> str | None:
    """'monthly' or 'annual' when the quote names exactly one period, else None (none given, or both)."""
    low = normalize(quote)
    m, a = bool(_MONTHLY_QUOTE.search(low)), bool(_ANNUAL_QUOTE.search(low))
    return "monthly" if m and not a else ("annual" if a and not m else None)


def period_problems(c: ExtractedScheme) -> list[str]:
    """BLOCKING: an income rule must use the field of the period its own quote states. "Rs 15,000 per month"
    on annual_income (or "per annum" on monthly_income) silently turns a limit into a different one; this is the
    error the auditor caught on PMAY-G. Land in acres/bighas on land_holding_hectares is the same kind of error."""
    errs: list[str] = []
    for i, rule in enumerate(c.rules):
        want = PERIOD_OF.get(rule.field)
        if want:
            got = quote_period(rule.evidence)
            if got and got != want:
                right = {"annual": "annual_income", "monthly": "monthly_income"}[got]
                errs.append(f"rules[{i}]: period mismatch: {rule.field} is a {want} figure but the quote states a "
                            f"{got} one (\"{rule.evidence[:120]}\"). Use {right} with the number as the source "
                            "states it (do not convert), or move the criterion to unmapped_criteria")
        if rule.field == "land_holding_hectares" and _AREA_UNITS.search(normalize(rule.evidence)) \
                and "hectare" not in normalize(rule.evidence):
            errs.append(f"rules[{i}]: land_holding_hectares is in hectares but the quote uses another unit "
                        f"(\"{rule.evidence[:120]}\"). Convert only if the source gives hectares; otherwise move "
                        "the criterion to unmapped_criteria")
    return errs


def rule_value_problems(c: ExtractedScheme) -> list[str]:
    """BLOCKING: a rule's number must literally appear in its own evidence quote (digit-boundary exact;
    1,00,000 = 100000 = 1 lakh; 60 does not match 160). Only exclusive bounds are derived; the income period must match the quote (period_problems)."""
    errs: list[str] = period_problems(c)
    for i, rule in enumerate(c.rules):
        for v, op, field in _numeric_values(rule.value, rule.op, rule.field):
            if not value_in_evidence(v, rule.evidence, op=op, field=field):
                shown = sorted(str(n) for n in numbers_in(rule.evidence)) or ["none"]
                errs.append(f"rules[{i}]: value {v} for {field} is not present in its own evidence quote "
                            f"(numbers in the quote: {', '.join(shown)}). Use the number the source states, "
                            f"or quote the sentence that contains {v}: \"{rule.evidence[:120]}\"")
    return errs


def _state_rules(c: ExtractedScheme) -> list:
    return [x for x in c.rules if x.field == "state" and x.op in ("eq", "in")]


def level_problems(c: ExtractedScheme) -> list[str]:
    """BLOCKING: a state-run scheme must be gated by a state rule (otherwise the agent would offer a Kerala-only
    scheme to a resident of Uttar Pradesh), a central scheme must not be, and each state in a rule must be
    named in that rule's own quote."""
    errs: list[str] = []
    st = _state_rules(c)
    if c.level is None:
        errs.append("level is missing: set \"level\" to \"central\" (open to residents of every state) or "
                    "\"state\" (run by or limited to one or more states/UTs), with level_evidence")
    elif c.level == "state":
        if not st:
            errs.append("level is 'state' but there is no rule on field 'state': add {field: state, op: eq|in, "
                        "value: <canonical state name(s)>} with a quote naming the state, otherwise residents of "
                        "other states would be told they qualify")
        if not c.level_evidence.strip():
            errs.append("level is 'state' but level_evidence is empty: quote the text showing which state runs "
                        "or covers the scheme")
    elif st:
        errs.append("level is 'central' but a state rule exists: set level to 'state', or remove the state rule "
                    "if the scheme is open to every state")
    for i, rule in enumerate(c.rules):
        if rule.field != "state" or rule.op not in ("eq", "in"):
            continue
        vals = rule.value if isinstance(rule.value, list) else [rule.value]
        low = rule.evidence.casefold().replace("&", "and")
        for v in vals:
            if isinstance(v, str) and v in STATES and not _state_named(v, low):
                errs.append(f"rules[{i}]: state {v!r} is not named in its own evidence quote; quote the sentence "
                            f"that names the state: \"{rule.evidence[:120]}\"")
    return errs


def _state_named(state: str, low_quote: str) -> bool:
    names = {state.casefold().replace("&", "and")}
    names |= {k for k, v in _state_aliases().items() if v == state}
    return any(n in low_quote for n in names)


def _state_aliases() -> dict[str, str]:
    from sahayak.states import _RAW_ALIASES
    return {k.casefold(): v for k, v in _RAW_ALIASES.items() if len(k) > 3}


def validate_candidate(cand: dict | ExtractedScheme, existing: dict[str, Scheme] | None = None,
                       *, source_url: str | None = None) -> Validation:
    """Validate a candidate (extract-format dict or model). Never raises."""
    existing = existing or {}
    out = Validation()
    try:
        c = cand if isinstance(cand, ExtractedScheme) else ExtractedScheme(**cand)
    except ValidationError as e:
        out.errors += [f"schema: {'.'.join(map(str, x['loc']))}: {x['msg']}" for x in e.errors()]
        return out
    rec = to_scheme_dict(c)
    if source_url:
        rec["source_url"] = source_url
    r = validate_record(rec, existing, evidence_rules=[r.model_dump() for r in c.rules])
    # extra, extraction-only checks: every number a rule uses must be in the rule's own quote (blocking)
    r.errors += rule_value_problems(c)
    r.errors += level_problems(c)
    if not c.rules and not c.unmapped_criteria:
        r.warnings.append("no eligibility criteria found at all; scheme would match everybody")
    return r


def validate_record(rec: dict, existing: dict[str, Scheme] | None = None, *,
                    evidence_rules: list[dict] | None = None) -> Validation:
    """Validate a database-format record (also used by merge, where evidence is not needed)."""
    existing = existing or {}
    out = Validation()
    sid = rec.get("id", "")
    if not isinstance(sid, str) or not SNAKE.match(sid):
        out.errors.append(f"id {sid!r} must be snake_case (lowercase letters, digits, underscores)")
    elif sid in existing:
        out.is_update = True
        out.warnings.append(f"id {sid!r} already exists: this is an UPDATE of the current record")
    su = rec.get("source_url") or ""
    p = urlparse(su)
    if p.scheme not in ("http", "https") or not p.netloc:
        out.errors.append("source_url is missing or not an http(s) URL")
    try:
        scheme = Scheme(**rec)
    except ValidationError as e:
        out.errors += [f"schema: {'.'.join(map(str, x['loc']))}: {x['msg']}" for x in e.errors()]
        return out
    for i, rule in enumerate(scheme.rules):
        if not isinstance(rule, dict) or "reason" not in rule or not str(rule.get("reason", "")).strip():
            out.errors.append(f"rules[{i}]: missing 'reason'")
            continue
        out.errors += check_condition(rule, PROFILE_FIELDS, f"rules[{i}]", top=True)
    if not out.errors:
        e, w = _contradictions(scheme.rules)
        out.errors += e
        out.warnings += w
    if not out.errors:
        errs, n = behavioural_checks(scheme)
        out.errors += errs
        out.checks_run = n
    if sid not in existing:
        for other in existing.values():
            if other.name.strip().casefold() == scheme.name.strip().casefold() or \
                    (other.source_url == su and su):
                out.warnings.append(f"looks like a duplicate of existing scheme {other.id!r} "
                                    f"(same name or source_url) but has a different id")
    if not scheme.benefits.strip():
        out.errors.append("benefits is empty")
    return out
