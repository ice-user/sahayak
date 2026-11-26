"""Deterministic evidence matching: is a quoted claim really in the source text?

Normalisation makes the check robust to what LLMs and HTML extraction commonly change
(whitespace, smart quotes, dash variants, case, zero-width characters, NBSP) without
loosening it into "close enough in spirit". Devanagari and other scripts are untouched
apart from Unicode NFKC composition and zero-width removal.
"""
from __future__ import annotations

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from decimal import Decimal

from rapidfuzz import fuzz

MIN_QUOTE_CHARS = 5       # shorter quotes prove nothing
FUZZY_MIN_CHARS = 20      # below this length only exact (normalised) matches count
FUZZY_THRESHOLD = 95.0    # rapidfuzz partial_ratio; tolerates a stray character or two (never a changed number)

_QUOTES = str.maketrans({"‘": "'", "’": "'", "‚": "'", "‛": "'", "′": "'",
                         "“": '"', "”": '"', "„": '"', "‟": '"', "«": '"', "»": '"'})
_DASHES = re.compile("[‐‑‒–—―−]")
_INVISIBLE = re.compile("[​‌‍⁠﻿­]")
_WS = re.compile(r"\s+")
_ELLIPSIS = re.compile(r"\s*(?:…|\.{3,})\s*")


def _ascii_digits(text: str) -> str:
    """Map every non-ASCII decimal digit (Devanagari, Tamil, Bengali, ...) to 0-9."""
    return "".join(str(unicodedata.decimal(c)) if ord(c) > 127 and unicodedata.category(c) == "Nd" else c
                   for c in text)


def normalize(text: str) -> str:
    """Lower-case, NFKC, digits to ASCII, straighten quotes/dashes, drop zero-width chars, collapse whitespace."""
    t = _ascii_digits(unicodedata.normalize("NFKC", text or ""))
    t = _INVISIBLE.sub("", t).translate(_QUOTES)
    t = _DASHES.sub("-", t).replace(" ", " ")
    return _WS.sub(" ", t).strip().casefold()




# ------------------------------------------------------------------ numbers
# A fuzzy score cannot tell "1,00,000" from "2,00,000" (97.9 / 100), so numbers are compared exactly,
# as values: Indian/western grouping, decimals, lakh/crore/thousand words (Latin, Devanagari, Tamil),
# English number words, and non-ASCII digits (normalised to ASCII by ``normalize``).
_MULT_WORDS = {"lakh": 10**5, "lakhs": 10**5, "lac": 10**5, "lacs": 10**5, "crore": 10**7, "crores": 10**7,
               "cr": 10**7, "thousand": 1000, "hundred": 100, "लाख": 10**5, "करोड़": 10**7, "करोड": 10**7,
               "हजार": 1000, "हज़ार": 1000, "லட்சம்": 10**5, "கோடி": 10**7, "ஆயிரம்": 1000}
_MULT_ALT = "|".join(sorted((re.escape(w) for w in _MULT_WORDS), key=len, reverse=True))
_NUM_RE = re.compile(r"(?<!\d)(?:\d{1,3}(?:,\d{3})+|\d{1,2}(?:,\d{2})*,\d{3}|\d+)(?!\d)(?:\.\d+)?"
                     rf"(?:\s*(?:{_MULT_ALT})(?![a-z]))?")
_MULT_AFTER = re.compile(rf"\s*(?:{_MULT_ALT})(?![a-z])")
_UNITS = {w: i for i, w in enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen "
    "seventeen eighteen nineteen".split())}
_TENS = {w: 10 * i for i, w in enumerate("_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()) if w != "_"}
_BIG = {"thousand": 1000, "lakh": 10**5, "lakhs": 10**5, "lac": 10**5, "lacs": 10**5, "crore": 10**7,
        "crores": 10**7}
_WORD_RE = re.compile(r"[a-z]+")


def _dec(x) -> Decimal:
    return Decimal(x).normalize()


def _digit_value(tok: str) -> Decimal:
    m = re.match(rf"([\d,.]+)\s*({_MULT_ALT})?", tok)
    val = Decimal(m.group(1).replace(",", ""))
    if m.group(2):
        val *= _MULT_WORDS[m.group(2)]
    return _dec(val)


def _word_numbers(text: str) -> list[Decimal]:
    """Values of English number words ("sixty", "twenty-five", "one lakh"); a lone "one" is ignored."""
    out: list[Decimal] = []
    words = _WORD_RE.findall(text.replace("-", " "))
    total = cur = 0
    seq: list[str] = []

    def flush():
        nonlocal total, cur, seq
        if seq and seq != ["one"] and not (total == 0 and cur == 0 and "zero" not in seq):
            out.append(_dec(total + cur))
        total = cur = 0
        seq = []

    for w in words:
        if w in _UNITS or w in _TENS:
            r = cur % 100
            if (w in _TENS and r != 0) or (w in _UNITS and r != 0 and not (r >= 20 and r % 10 == 0)):
                flush()
            cur += _UNITS.get(w, _TENS.get(w, 0))
            seq.append(w)
        elif w == "hundred" and seq:
            cur = (cur or 1) * 100
            seq.append(w)
        elif w in _BIG and seq:
            total += (cur or 1) * _BIG[w]
            cur = 0
            seq.append(w)
        else:
            flush()
    flush()
    return out


def numbers_in(text: str) -> Counter:
    """Multiset of the numeric values mentioned in ``text`` (any script), as Decimals."""
    t = normalize(text)
    found: Counter = Counter()
    masked = []
    pos = 0
    for m in _NUM_RE.finditer(t):
        found[_digit_value(m.group(0))] += 1
        masked.append(t[pos:m.start()])
        masked.append(" # ")
        pos = m.end()
    masked.append(t[pos:])
    for v in _word_numbers("".join(masked)):
        found[v] += 1
    return found


def _expand_to_numbers(hay: str, s: int, e: int) -> tuple[int, int]:
    """Grow the window [s, e) so it never cuts a number (or its lakh/crore word) in half."""
    n = len(hay)
    if s < n and hay[s].isdigit():
        while s > 0 and (hay[s - 1].isdigit() or (hay[s - 1] in ",." and s > 1 and hay[s - 2].isdigit())):
            s -= 1
    if e > 0 and hay[e - 1].isdigit():
        while e < n and (hay[e].isdigit() or (hay[e] in ",." and e + 1 < n and hay[e + 1].isdigit())):
            e += 1
        m = _MULT_AFTER.match(hay, e)
        if m:
            e = m.end()
    return s, e


def _numbers_agree(frag: str, hay: str, s: int, e: int) -> bool:
    want = numbers_in(frag)
    if not want:
        return True
    s2, e2 = _expand_to_numbers(hay, s, e)
    return numbers_in(hay[s2:e2]) == want


def _wordch(c: str) -> bool:
    return unicodedata.category(c)[0] in "LNM"


def _find_bounded(frag: str, hay: str) -> bool:
    """Exact occurrence on word boundaries whose numbers equal the quote's numbers."""
    start = 0
    while True:
        i = hay.find(frag, start)
        if i < 0:
            return False
        j = i + len(frag)
        ok = not (_wordch(frag[0]) and i > 0 and _wordch(hay[i - 1]))
        ok = ok and not (_wordch(frag[-1]) and j < len(hay) and _wordch(hay[j]))
        if ok and _numbers_agree(frag, hay, i, j):
            return True
        start = i + 1

@dataclass
class Match:
    found: bool
    score: float
    method: str  # exact | fuzzy | missing | too_short | empty

    def __bool__(self) -> bool:
        return self.found


def _match_fragment(frag: str, haystack: str) -> Match:
    if len(frag) < MIN_QUOTE_CHARS:
        return Match(False, 0.0, "too_short")
    if _find_bounded(frag, haystack):
        return Match(True, 100.0, "exact")
    if len(frag) >= FUZZY_MIN_CHARS:
        al = fuzz.partial_ratio_alignment(frag, haystack)
        score = al.score if al else 0.0
        if al and score >= FUZZY_THRESHOLD:
            # a fuzzy hit is only acceptable when every number in the quote is also in the matched window
            if _numbers_agree(frag, haystack, al.dest_start, al.dest_end):
                return Match(True, float(score), "fuzzy")
            return Match(False, float(score), "number_mismatch")
        return Match(False, float(score), "missing")
    return Match(False, 0.0, "missing")


def find_quote(quote: str, source_text: str, *, _normalized_source: str | None = None) -> Match:
    """Check ``quote`` against ``source_text``.

    A quote containing an ellipsis ("..." or the single character) is split and every fragment
    must be present (order is not enforced; fragments are short quotes, each verified alone).
    """
    q = normalize(quote).strip("\"' ")  # models often wrap quotes in quote marks
    if not q:
        return Match(False, 0.0, "empty")
    hay = _normalized_source if _normalized_source is not None else normalize(source_text)
    fragments = [f for f in _ELLIPSIS.split(q) if f.strip()]
    if not fragments:
        return Match(False, 0.0, "empty")
    results = [_match_fragment(f.strip(), hay) for f in fragments]
    worst = min(results, key=lambda m: m.score if m.found else -1)
    if all(r.found for r in results):
        method = "exact" if all(r.method == "exact" for r in results) else "fuzzy"
        return Match(True, min(r.score for r in results), method)
    return Match(False, worst.score, worst.method)


def verify_all(items: list[tuple[str, str]], source_text: str) -> list[tuple[str, str, Match]]:
    """Return (label, quote, match) for every item; callers pick the failures."""
    hay = normalize(source_text)
    return [(label, quote, find_quote(quote, source_text, _normalized_source=hay)) for label, quote in items]


_EXCL_UPPER = re.compile(r"\b(?:below|under|less than|lower than|younger than|before|fewer than)\b")
_EXCL_LOWER = re.compile(r"\b(?:above|over|more than|greater than|higher than|older than|exceed(?:s|ing)?|"
                         r"beyond|after)\b")
_MONTHLY = re.compile(r"\b(?:per month|a month|monthly|each month|every month|/\s*month|p\.m\.)")


def value_in_evidence(value: int, evidence: str, *, op: str | None = None, field: str | None = None) -> bool:
    """Is the rule's numeric ``value`` stated in its own evidence quote (digit-exact)?

    Accepted forms: the number itself in any notation (60, 6,0 no; 1,00,000 = 100000 = 1 lakh; Devanagari digits;
    English number words). Two derived readings are allowed and nothing else: an exclusive bound
    ("below 18" -> lte 17, "above 60" -> gte 61) and a monthly amount converted to annual (x12) for annual_income.
    """
    nums = numbers_in(evidence)
    if _dec(value) in nums:
        return True
    ev = normalize(evidence)
    if op == "lte" and _EXCL_UPPER.search(ev) and _dec(value + 1) in nums:
        return True
    if op == "gte" and _EXCL_LOWER.search(ev) and _dec(value - 1) in nums:
        return True
    if field == "annual_income" and _MONTHLY.search(ev) and any(_dec(n * 12) == _dec(value) for n in nums):
        return True
    return False
