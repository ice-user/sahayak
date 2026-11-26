"""Mask identifiers the model never needs before a user message is sent to an LLM provider."""
from __future__ import annotations

import re

MASK = "[number removed]"

_AADHAAR = re.compile(r"(?<!\d)\d{4}[ -]?\d{4}[ -]?\d{4}(?!\d)")
_PAN = re.compile(r"\b[A-Za-z]{5}\d{4}[A-Za-z]\b")
# 10 digits starting 6-9, optionally prefixed by +91 / 91 / 0 (separators allowed only after a prefix)
_PHONE_PLAIN = re.compile(r"(?<!\d)(?:(?:\+91|91|0)[ -]?)?[6-9]\d{9}(?!\d)")
_PHONE_SPACED = re.compile(r"(?<!\d)(?:\+91|91)[ -]*[6-9]\d{4}[ -]?\d{5}(?!\d)")


def mask_pii(text: str) -> str:
    """Replace likely Aadhaar (12 digits, optionally 4-4-4), PAN (AAAAA9999A) and Indian mobile numbers.
    Heuristic: bare 5+5 spaced numbers without a +91 prefix are not treated as phone numbers (they look like amounts)."""
    for pattern in (_AADHAAR, _PAN, _PHONE_SPACED, _PHONE_PLAIN):
        text = pattern.sub(MASK, text)
    return text
