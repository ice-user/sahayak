"""What rules may reference, derived from ``sahayak.models.Profile`` so it can never drift."""
from __future__ import annotations

import typing
from dataclasses import dataclass
from typing import Annotated, Any, Literal, get_args, get_origin

from sahayak.models import MAX_MONEY, Child, Profile
from sahayak.rules import DERIVED_FIELDS
from sahayak.states import STATES

try:  # X | None syntax
    from types import UnionType as _UnionType
except ImportError:  # pragma: no cover
    _UnionType = None

OPS = ("eq", "ne", "gte", "lte", "in", "any_child")


@dataclass(frozen=True)
class FieldSpec:
    name: str
    kind: str                      # bool | int | float | str | enum | state | children
    choices: tuple = ()            # for enum
    lo: float | None = None        # inclusive bounds declared on the model (ge/le), for int/float fields
    hi: float | None = None
    description: str = ""
    derived: bool = False          # computed by the engine from other facts, not stored on Profile


NUMERIC = ("int", "float")


def _constraints(obj: Any, acc: dict) -> None:
    """Collect ge/le from pydantic metadata objects (Annotated args, nested FieldInfo, field.metadata)."""
    for m in getattr(obj, "metadata", None) or ():
        _constraints(m, acc)
    for key, name in (("ge", "lo"), ("le", "hi")):
        v = getattr(obj, key, None)
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            acc[name] = v


def _kind(ann: Any, info: Any = None) -> tuple[str, tuple, dict]:
    """Reduce an annotation (Optional / Annotated / Literal / list / StrictBool ...) to a field kind."""
    acc: dict = {}
    _constraints(info, acc)
    while True:
        origin = get_origin(ann)
        if origin is typing.Union or (_UnionType is not None and origin is _UnionType):
            args = [a for a in get_args(ann) if a is not type(None)]
            ann = args[0]
        elif origin is Annotated:
            args = get_args(ann)
            for extra in args[1:]:
                _constraints(extra, acc)
            ann = args[0]
        else:
            break
    if get_origin(ann) is Literal:
        return "enum", get_args(ann), acc
    if get_origin(ann) is list:
        return "children", (), acc
    if ann is bool:
        return "bool", (), acc
    if ann is int:
        return "int", (), acc
    if ann is float:
        return "float", (), acc
    return "str", (), acc


def _specs(model) -> dict[str, FieldSpec]:
    out = {}
    for n, f in model.model_fields.items():
        kind, choices, c = _kind(f.annotation, f)
        if n == "state":                      # free text on Profile, but rules may only use canonical names
            kind, choices = "state", STATES
        out[n] = FieldSpec(n, kind, choices, c.get("lo"), c.get("hi"), f.description or "")
    return out


PROFILE_FIELDS: dict[str, FieldSpec] = _specs(Profile)
CHILD_FIELDS: dict[str, FieldSpec] = _specs(Child)

# Computed fields: usable in rules, never stored on Profile (the engine derives them; see sahayak.rules.derive_facts).
_DERIVED_DESCRIPTIONS = {
    "per_capita_monthly_income": "household monthly income divided by household_size, rupees per month per person; "
                                 "use ONLY for a limit stated 'per capita' / 'per member' / 'per person' per month",
}
for _n in DERIVED_FIELDS:
    PROFILE_FIELDS[_n] = FieldSpec(_n, "int", (), 0, MAX_MONEY, _DERIVED_DESCRIPTIONS.get(_n, ""), True)

# Income fields have a period. A rule's quote must name the same period (research.validate checks this).
PERIOD_OF = {"annual_income": "annual", "monthly_income": "monthly", "per_capita_monthly_income": "monthly"}


def describe_fields() -> str:
    """Human/LLM-readable list of allowed fields for the extraction prompt."""
    lines = []
    for s in PROFILE_FIELDS.values():
        if s.kind == "children":
            sub = ", ".join(f"{c.name} ({c.kind}{'' if not c.choices else ': ' + '|'.join(c.choices)})"
                            for c in CHILD_FIELDS.values())
            lines.append(f"- {s.name}: list of children; ONLY usable with op any_child whose value is a list of "
                         f"sub-conditions over: {sub}")
        elif s.kind == "state":
            lines.append("- state: the citizen's state/UT. ONLY ops eq (one state) or in (a list of states); values must "
                         "be spelled EXACTLY as one of: " + "; ".join(s.choices))
        elif s.kind == "enum":
            lines.append(f"- {s.name}: one of {'|'.join(s.choices)}" + (f". {s.description}" if s.description and
                         not s.description.startswith("Main work") else ""))
        else:
            lines.append(f"- {s.name}: {s.kind}" + (" (ops gte/lte allowed)" if s.kind in NUMERIC else "")
                         + (f". {s.description}" if s.description else ""))
    return "\n".join(lines)
