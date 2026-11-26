"""Deterministic quick-reply chips: language detection + options for the next missing profile fields."""
from __future__ import annotations

from typing import Any, Iterable

from sahayak.lang import detect_language, has_letters, upgrade_language  # noqa: F401  (shared with the agent)

from .phrases import PHRASES

MAX_OPTIONS = 4
MAX_FIELDS = 2


def missing_fields(check_eligibility_result: Any) -> list[str]:
    """Distinct missing fields from a check_eligibility result, in order of first appearance."""
    if not isinstance(check_eligibility_result, dict):
        return []
    seen: dict[str, None] = {}
    for item in check_eligibility_result.get("need_info", []):
        for name in item.get("missing_fields", []):
            seen.setdefault(name)
    return list(seen)


def suggestions_for(fields: Iterable[str], language: str) -> list[str]:
    """Options for the first field, plus the second field's if everything still fits in MAX_OPTIONS.
    Numeric / free-text fields (no phrase table entry) yield no chips."""
    options: list[str] = []
    for name in list(fields)[:MAX_FIELDS]:
        table = PHRASES.get(name)
        if table is None:
            break
        phrases = table.get(language) or table["en"]
        if options and len(options) + len(phrases) > MAX_OPTIONS:
            break
        options.extend(phrases[:MAX_OPTIONS])
    return options
