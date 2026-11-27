"""Section splitter and document-alias mapping for myscheme.gov.in snapshots ("how to apply" records).

A snapshot lists every section heading twice: first in the navigation menu, then as the real section. The
splitter takes the SECOND occurrence of each heading line (a heading that occurs only once was just the menu
entry, so the section is absent from the page).
"""
from __future__ import annotations

import re
from pathlib import Path

from .evidence import normalize

SECTIONS = ("Details", "Benefits", "Eligibility", "Exclusions", "Application Process", "Documents Required",
            "Frequently Asked Questions", "Sources And References")
_END_MARKERS = ("Was this helpful?", "News and Updates")
_MODE_LINES = {"online", "offline"}


def strip_header(text: str) -> str:
    """Drop the 'Source URL: ...' first line of a snapshot."""
    lines = text.splitlines()
    if lines and lines[0].startswith("Source URL:"):
        return "\n".join(lines[1:])
    return text


def source_url_of(text: str) -> str | None:
    first = text.splitlines()[0] if text else ""
    return first.split(":", 1)[1].strip() if first.startswith("Source URL:") else None


def split_sections(text: str) -> dict[str, str]:
    """{heading: body} for every section that really has a body (second heading occurrence)."""
    lines = strip_header(text).splitlines()
    heads: list[tuple[int, str]] = []
    for name in SECTIONS:
        idx = [i for i, ln in enumerate(lines) if ln.strip() == name]
        if len(idx) >= 2:
            heads.append((idx[1], name))
    heads.sort()
    out: dict[str, str] = {}
    for k, (i, name) in enumerate(heads):
        end = heads[k + 1][0] if k + 1 < len(heads) else len(lines)
        body = lines[i + 1:end]
        if name == "Sources And References" or k + 1 == len(heads):
            for j, ln in enumerate(body):
                if ln.strip() in _END_MARKERS:
                    body = body[:j]
                    break
        out[name] = "\n".join(body).strip()
    return out


def body_lines(section: str) -> list[str]:
    """Non-empty stripped lines of a section body."""
    return [ln.strip() for ln in section.splitlines() if ln.strip()]


def mode_lines(section_application: str) -> list[str]:
    """The leading 'Online' / 'Offline' tab labels of an Application Process section (lower-case, in order)."""
    out = []
    for ln in body_lines(section_application):
        if ln.lower().split(" - ")[0].strip() in _MODE_LINES:
            out.append(ln.lower().split(" - ")[0].strip())
        else:
            break
    return out


def load_snapshot(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# ------------------------------------------------------------------ documents -> canonical ids
def _alias_re(alias: str) -> re.Pattern:
    return re.compile(r"(?<![a-z0-9])" + re.escape(normalize(alias)) + r"(?![a-z0-9])")


def map_document_line(line: str, docs: dict[str, dict]) -> list[str]:
    """Canonical doc ids whose alias occurs (word-bounded) in ``line``. Longest alias wins on overlap, so
    'bank passbook' is not also read as 'passbook'-less 'bank' etc. Order follows first appearance."""
    t = normalize(line)
    spans: list[tuple[int, int, str]] = []
    for doc_id, d in docs.items():
        for alias in d.get("aliases", []):
            for m in _alias_re(alias).finditer(t):
                spans.append((m.start(), m.end(), doc_id))
    spans.sort(key=lambda s: (-(s[1] - s[0]), s[0]))
    taken: list[tuple[int, int, str]] = []
    for s, e, doc_id in spans:
        if any(s < e2 and s2 < e for s2, e2, _ in taken):
            continue
        taken.append((s, e, doc_id))
    taken.sort()
    ids: list[str] = []
    for _, _, doc_id in taken:
        if doc_id not in ids:
            ids.append(doc_id)
    return ids


_OPTIONAL = re.compile(r"\b(?:not mandatory(?! for)|optional|if available|if any|any one of|whichever)\b")


def line_is_mandatory(line: str) -> bool:
    """False when the line itself says the document is optional / one of several alternatives."""
    t = normalize(line)
    return not (_OPTIONAL.search(t) or re.search(r"\bor\b| / ", t))


# ------------------------------------------------------------------ alternative documents ("any one of")
from sahayak.planner import derive_routes  # noqa: E402,F401  (re-exported: one definition of "route")

ALT_CUE = re.compile(r"\bany one of\b|\bor\b|/|\beither\b|\bin their absence\b|\bno valid document\b|\bwhichever\b|\bin lieu\b",
                     re.I)
_OPTIONAL_WORDS = re.compile(r"\b(?:not mandatory|optional|if available|if any)\b", re.I)
_CONTINUES = re.compile(r"\bin their absence\b|\bno valid document\b|\bin lieu\b", re.I)
ALT_GROUPS = {"id_proof": {"aadhaar", "voter_id", "ration_card", "photo_id"},
              "address_proof": {"residence_proof", "electricity_bill", "voter_id", "aadhaar", "ration_card"},
              "age_proof": {"age_proof", "birth_certificate", "school_certificate", "ration_card", "voter_id"},
              "family_proof": {"ration_card", "self_declaration", "migrant_declaration"}}


def _line_group(doc_ids: set[str]) -> str | None:
    if "residence_proof" in doc_ids:
        return "address_proof"
    if "age_proof" in doc_ids:
        return "age_proof"
    if "ration_card" in doc_ids and doc_ids & {"self_declaration", "migrant_declaration"}:
        return "family_proof"
    if len(doc_ids & ALT_GROUPS["id_proof"]) >= 2:
        return "id_proof"
    return None


def assign_alternatives(documents: list[dict]) -> list[dict]:
    """Add ``alternatives_group`` to documents whose quote offers alternatives (any one of / or / / / either / in their
    absence). Documents listed together on one line form the group; a continuation line ("in their absence ...") joins
    the previous group. A grouped document counts as required (one of the group is needed) unless its line says optional.
    Returns new dicts; documents without alternatives are copied unchanged."""
    by_quote: dict[str, set[str]] = {}
    for d in documents:
        by_quote.setdefault(d["quote"], set()).add(d["doc"])
    out, last = [], None
    for d in documents:
        d = {k: v for k, v in d.items() if k != "alternatives_group"}
        q = d["quote"]
        gid = None
        if ALT_CUE.search(q):
            if last and _CONTINUES.search(q) and d["doc"] in ALT_GROUPS[last]:
                gid = last
            else:
                gid = _line_group(by_quote[q])
        if gid and d["doc"] in ALT_GROUPS[gid]:
            d["alternatives_group"] = gid
            if not _OPTIONAL_WORDS.search(q):
                d["mandatory"] = True
            last = gid
        elif not ALT_CUE.search(q):
            last = None
        out.append(d)
    return out
