"""Human-readable review summary and field-by-field diff for updates."""
from __future__ import annotations

import json
from typing import Any

from sahayak.models import Scheme

from .freetext import URL_ERR_PREFIX

_SCALARS = ("name", "ministry", "category", "summary", "benefits", "how_to_apply", "source_url")
_LISTS = ("caveats", "documents", "tags", "aliases")


def _rule_str(r: dict) -> str:
    return f"{r['field']} {r['op']} {json.dumps(r['value'], ensure_ascii=False)}"


def diff_records(old: dict, new: dict) -> list[str]:
    """Lines describing what an update would change ('' list if identical)."""
    out: list[str] = []
    for k in _SCALARS:
        if (old.get(k) or "") != (new.get(k) or ""):
            out.append(f"~ {k}:\n    was: {old.get(k)}\n    now: {new.get(k)}")
    old_rules = {_rule_str(r) for r in old.get("rules", [])}
    new_rules = {_rule_str(r) for r in new.get("rules", [])}
    out += [f"- rule removed: {r}" for r in sorted(old_rules - new_rules)]
    out += [f"+ rule added:   {r}" for r in sorted(new_rules - old_rules)]
    for k in _LISTS:
        o, n = old.get(k, []), new.get(k, [])
        out += [f"- {k} removed: {x}" for x in o if x not in n]
        out += [f"+ {k} added:   {x}" for x in n if x not in o]
    return out


def build_review(state: dict, existing: dict[str, Scheme]) -> dict:
    """Assemble the interrupt payload (JSON-serialisable) shown to the human."""
    cand = state.get("candidate")
    rec = state.get("scheme_record")
    diff: list[str] | None = None
    # URL-only problems can be approved explicitly (--allow-url); everything else must be fixed first
    blocking = [e for e in state.get("errors", []) if not e.startswith(URL_ERR_PREFIX)]
    if rec and rec["id"] in existing:
        diff = diff_records(existing[rec["id"]].model_dump(), rec)
    return {
        "type": "scheme_review",
        "source": state.get("source"), "source_url": state.get("source_url"),
        "status": state.get("status"), "attempts": len(state.get("attempts", [])),
        "errors": state.get("errors", []), "warnings": state.get("warnings", []),
        "note": state.get("review_note", ""),
        "candidate": cand, "scheme_record": rec,
        "evidence_report": state.get("evidence_report", []),
        "unmapped_criteria": (cand or {}).get("unmapped_criteria", []),
        "is_update": bool(state.get("is_update")), "diff": diff,
        "truncated": bool(state.get("truncated")),
        "auditor_notes": state.get("auditor_notes", []), "audit": state.get("audit") or {},
        "contact_flags": state.get("contact_flags", []), "unapproved_urls": state.get("unapproved_urls", []),
        "allowed_actions": ["approve", "reject", "edit"] if not blocking else ["reject", "edit"],
    }


def format_review(p: dict) -> str:
    """Plain-text rendering of a review payload."""
    L: list[str] = []
    rec, cand = p.get("scheme_record"), p.get("candidate")
    L.append(f"STATUS: {p['status']}   source: {p.get('source_url') or p.get('source')}   "
             f"LLM attempts: {p['attempts']}")
    if p.get("note"):
        L.append(f"NOTE: {p['note']}")
    if p.get("truncated"):
        L.append("WARNING: source text was truncated to the size limit; later parts were not seen.")
    if p["errors"]:
        L.append("\nBLOCKING ERRORS (cannot approve until fixed; use --edit or --reject; URL-only errors can also "
                 "be approved with --allow-url):")
        L += [f"  x {e}" for e in p["errors"]]
    if p["warnings"]:
        L.append("\nWarnings:")
        L += [f"  ! {w}" for w in p["warnings"]]
    audit = p.get("audit") or {}
    if audit:
        if audit.get("status") == "ok":
            L.append(f"\nAuditor ({audit.get('model') or 'same model'}): {audit.get('blocking', 0)} blocking "
                     f"finding(s) on the latest attempt, {audit.get('warnings', 0)} warning(s), "
                     f"{len(audit.get('dropped', []))} dropped (quote not in source).")
        else:
            L.append(f"\nAuditor: DID NOT RUN ({audit.get('detail')}).")
    if p.get("auditor_notes"):
        L.append("Auditor notes (independent second reading of the source; judge each yourself):")
        L += [f"  ? {n}" for n in p["auditor_notes"]]
    flags = p.get("contact_flags") or []
    if flags:
        L.append("\nContact details in free text (verify every one; hostile pages plant fake helplines/links):")
        for f in flags:
            tag = {"ok": "gov/source domain", "blocked": "BLOCKED: not on allowlist", "approved": "approved by reviewer",
                   "verify": "verify"}[f["status"]]
            L.append(f"  - {f['kind']}: {f['value']}  [{tag}; {'appears' if f['in_source'] else 'NOT'} in source]"
                     f"  in {f['field']}")
    if cand:
        L.append(f"\n{'UPDATE of existing' if p['is_update'] else 'NEW scheme'}: {cand['name']}  [{cand['id']}]")
        L.append(f"  ministry: {cand.get('ministry') or '-'}   category: {cand['category']}")
        L.append(f"  summary:  {cand['summary']}")
        L.append(f"  benefits: {cand['benefits']}")
        L.append("\nRules (checked by the engine) with evidence:")
        if not cand["rules"]:
            L.append("  (none)")
        for r in cand["rules"]:
            L.append(f"  * {_rule_str(r)}   -- {r['reason']}\n      evidence: \"{r['evidence']}\"")
        if p["unmapped_criteria"]:
            L.append("\nUnmapped criteria (kept as caveats, NOT checked by the engine):")
            for u in p["unmapped_criteria"]:
                L.append(f"  * {u['criterion']}\n      evidence: \"{u['evidence']}\"")
        if cand.get("documents"):
            L.append("\nDocuments: " + "; ".join(d["item"] for d in cand["documents"]))
        if cand.get("how_to_apply"):
            L.append(f"How to apply: {cand['how_to_apply']}")
        bad = [e for e in p["evidence_report"] if not e["found"]]
        L.append(f"\nEvidence check: {len(p['evidence_report']) - len(bad)}/{len(p['evidence_report'])} quotes "
                 "found in the source text" + ("" if not bad else " (see errors)"))
    if p.get("diff") is not None:
        L.append("\nDIFF vs current record:" if p["diff"] else "\nNo differences from the current record.")
        L += [("  " + ln.replace("\n", "\n  ")) for ln in p["diff"]]
    L.append("\nActions: " + ", ".join(p["allowed_actions"]))
    return "\n".join(L)


def summary_of(p: dict) -> Any:
    """One-line description for batch reports."""
    c = p.get("candidate") or {}
    return f"{c.get('name', '?')} [{c.get('id', '?')}]"
