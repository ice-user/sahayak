"""Split a myscheme.gov.in snapshot into single eligibility bullets (the unit of the fine-tuning task).

A snapshot (scripts/collect_myscheme.py) starts with a navigation menu that already contains the word
"Eligibility"; the real section is the SECOND line that is exactly "Eligibility" and runs until the next
section heading ("Exclusions", "Application Process", "Documents Required", "Benefits", ...).
"""
from __future__ import annotations

import re
from pathlib import Path

SECTION_HEADINGS = frozenset(h.casefold() for h in (
    "Details", "Benefits", "Eligibility", "Exclusions", "Application Process", "Documents Required",
    "Frequently Asked Questions", "Sources And References", "Feedback", "News and Updates", "Share",
))
MIN_CHARS = 12
MIN_WORDS = 3
_BOILERPLATE = re.compile(
    r"^(?:n/?a|not applicable|none|nil|no (?:specific )?(?:criteria|eligibility)[^.]*|as per (?:the )?(?:scheme )?"
    r"guidelines?\.?|refer (?:to )?(?:the )?(?:scheme )?guidelines?\.?|click here.*|visit .*website.*|"
    r"was this helpful\??|[-•*\s.]*)$", re.I)
_BULLET_PREFIX = re.compile(r"^\s*(?:[-•*●▪>]+|\(?\d{1,2}[.)]|\(?[a-z][.)]|\(?[ivx]{1,4}[.)])\s+")
# an abbreviation before a full stop must not end a sentence
_ABBREV = re.compile(r"(?:\b(?:rs|no|nos|dr|mr|mrs|ms|st|govt|dept|sr|jr|vs|viz|etc|approx|min|max|incl|sh|smt|"
                     r"e\.g|i\.e|a\.k\.a|w\.e\.f|u\.p|m\.p|h\.p|j&k|prof|co|ltd|pvt|dist|rd|sec|art|cl|"
                     r"p\.a|p\.m|a\.m|ph|fig|vol|ed))$", re.I)
_SENT_END = re.compile(r"(?<=[.;?!])\s+(?=[A-Z(‘“\"'])")


def is_heading(line: str) -> bool:
    return line.strip().casefold() in SECTION_HEADINGS


def eligibility_lines(snapshot: str) -> list[str]:
    """Lines of the second 'Eligibility' section (empty list if the snapshot has none)."""
    lines = [ln.strip() for ln in snapshot.splitlines()]
    starts = [i for i, ln in enumerate(lines) if ln.casefold() == "eligibility"]
    if len(starts) < 2:
        return []
    out: list[str] = []
    for ln in lines[starts[1] + 1:]:
        if is_heading(ln):
            break
        out.append(ln)
    return out


def _sentences(line: str) -> list[str]:
    parts: list[str] = []
    cur = ""
    for piece in _SENT_END.split(line):
        cur = f"{cur} {piece}".strip() if cur else piece
        if _ABBREV.search(cur.rstrip(".;?! ")) and cur.endswith("."):
            continue                       # "Rs." / "Govt." is not a sentence end; keep gluing
        parts.append(cur)
        cur = ""
    if cur:
        parts.append(cur)
    return parts


def split_bullets(lines: list[str]) -> list[str]:
    """Bullets/sentences from section lines: prefixes stripped, boilerplate and group headings dropped, deduped."""
    out: list[str] = []
    seen: set[str] = set()
    for raw in lines:
        line = _BULLET_PREFIX.sub("", raw.replace(" ", " ")).strip()
        if not line or _BOILERPLATE.match(line):
            continue
        if line.endswith(":") and len(line.split()) <= 14:    # "For Mentor Institute (MI):" labels a group
            continue
        for s in _sentences(line):
            s = _BULLET_PREFIX.sub("", s).strip()
            if len(s) < MIN_CHARS or len(s.split()) < MIN_WORDS or _BOILERPLATE.match(s):
                continue
            key = re.sub(r"\W+", " ", s).casefold().strip()
            if key in seen:
                continue
            seen.add(key)
            out.append(s)
    return out


def snapshot_url(snapshot: str) -> str:
    m = re.match(r"\s*Source URL:\s*(\S+)", snapshot)
    return m.group(1) if m else ""


def bullets_from_snapshot(snapshot: str) -> list[str]:
    return split_bullets(eligibility_lines(snapshot))


def bullets_from_file(path: str | Path) -> tuple[str, list[str]]:
    text = Path(path).read_text(encoding="utf-8")
    return snapshot_url(text), bullets_from_snapshot(text)
