"""Pydantic models for what the LLM must produce (a scheme record plus evidence quotes).

The final database record is :class:`sahayak.models.Scheme`; ``to_scheme_dict`` strips the
evidence so the extra bookkeeping never reaches data/schemes.json.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class EvidencedRule(BaseModel):
    """One machine-checkable eligibility rule plus the verbatim source quote that justifies it."""
    model_config = ConfigDict(extra="forbid")
    field: str
    op: str
    value: Any
    reason: str = Field(min_length=3, description="Plain-English reason shown to a citizen when this rule fails")
    evidence: str = Field(min_length=1, description="Verbatim quote from the source document")


class EvidencedDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")
    item: str = Field(min_length=1)
    evidence: str = Field(min_length=1)


class UnmappedCriterion(BaseModel):
    """An eligibility criterion that no Profile field can express (goes to caveats, never to rules)."""
    model_config = ConfigDict(extra="forbid")
    criterion: str = Field(min_length=3)
    evidence: str = Field(min_length=1)


class ExtractedScheme(BaseModel):
    """Candidate scheme as produced by the extract node (and by human edits)."""
    model_config = ConfigDict(extra="forbid")
    id: str
    name: str = Field(min_length=2)
    name_evidence: str = Field(min_length=1)
    ministry: str = ""
    category: str = Field(min_length=2)
    summary: str = Field(min_length=10)
    benefits: str = Field(min_length=3)
    benefits_evidence: list[str] = Field(min_length=1)
    level: Literal["central", "state"] | None = Field(
        None, description="central = open to residents of any state; state = run by / limited to one or more "
                          "states or UTs (then a state rule is mandatory)")
    level_evidence: str = Field("", description="Verbatim quote showing who runs the scheme / which state(s) it covers")
    rules: list[EvidencedRule]
    unmapped_criteria: list[UnmappedCriterion] = []
    caveats: list[str] = []
    documents: list[EvidencedDocument] = []
    how_to_apply: str = ""
    how_to_apply_evidence: list[str] = []
    source_url: str = ""
    tags: list[str] = []
    aliases: list[str] = []


def to_scheme_dict(c: ExtractedScheme | dict) -> dict:
    """Database-format record (data/schemes.json shape) with all evidence stripped.

    Unmapped criteria are appended to ``caveats`` so the citizen-facing agent still mentions them.
    """
    d = c.model_dump() if isinstance(c, ExtractedScheme) else ExtractedScheme(**c).model_dump()
    caveats = list(d["caveats"])
    for u in d["unmapped_criteria"]:
        if u["criterion"] not in caveats:
            caveats.append(u["criterion"])
    return {
        "id": d["id"], "name": d["name"], "ministry": d["ministry"], "category": d["category"],
        "tags": d["tags"], "aliases": d["aliases"], "summary": d["summary"], "benefits": d["benefits"],
        "rules": [{"field": r["field"], "op": r["op"], "value": r["value"], "reason": r["reason"]}
                  for r in d["rules"]],
        "caveats": caveats, "documents": [x["item"] for x in d["documents"]],
        "how_to_apply": d["how_to_apply"], "source_url": d["source_url"],
    }


def evidence_items(c: ExtractedScheme) -> list[tuple[str, str]]:
    """Flatten every (claim label, quote) pair so evidence can be verified uniformly."""
    items: list[tuple[str, str]] = [("name", c.name_evidence)]
    if c.level_evidence.strip():
        items.append(("level", c.level_evidence))
    items += [(f"benefits[{i}]", q) for i, q in enumerate(c.benefits_evidence)]
    items += [(f"rules[{i}] {r.field} {r.op} {r.value!r}", r.evidence) for i, r in enumerate(c.rules)]
    items += [(f"documents[{i}] {d.item!r}", d.evidence) for i, d in enumerate(c.documents)]
    items += [(f"unmapped_criteria[{i}]", u.evidence) for i, u in enumerate(c.unmapped_criteria)]
    items += [(f"how_to_apply[{i}]", q) for i, q in enumerate(c.how_to_apply_evidence)]
    return items
