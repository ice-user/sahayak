"""Detect which schemes an answer mentions, and whether it OFFERS them as available.

Polarity is decided per clause, not per sentence, so "You cannot get PMJJBY, but you can get Sukanya and PMUY"
denies PMJJBY and offers the other two. Each clause is labelled:

  pos    offers / says the user can get it ("you can get", "eligible", "पात्र हैं", "mil sakta hai", "கிடைக்கும்", ...)
  neg    denies it ("not eligible", "do not qualify", "ineligible", "nahi", "नहीं", "இல்லை", ...) - always beats pos
  hedge  "you may still be covered ... check on the app": a possibility plus a pointer to verify; not an offer
  cond   conditional ("if you have a BPL card ..."); not an offer
  None   merely mentions it (description, documents)

Clauses are split on sentence ends, commas/semicolons, dashes, contrast words (but / lekin / लेकिन / ஆனால்)
and "and you ...". A clause without its own cue inherits from the previous clause of the same sentence
(comma lists) or, for list items, from the nearest header above ("Not available for you:" then "- APY").
After a contrast word nothing is inherited. Known limits: it is a regex heuristic, so unusual phrasings
can be misread; the runtime guard and the datagen grader both lean on it, so keep the adversarial table in
tests/test_polarity.py growing.
"""
from __future__ import annotations

import re
from functools import lru_cache

# How each scheme may be written in an answer (any language keeps the English name in brackets per the prompt)
MENTIONS = {
    "ignoaps": [r"IGNOAPS", r"old age pension", r"वृद्धावस्था पेंशन", r"budhapa pension", r"முதியோர் ஓய்வூதிய"],
    "ignwps": [r"IGNWPS", r"widow pension", r"vidhwa pension", r"विधवा पेंशन", r"விதவை ஓய்வூதிய", r"Vidh?wa Pension Yojana"],
    "apy": [r"\bAPY\b", r"Atal Pension"],
    "pmjjby": [r"PMJJBY", r"Jeevan Jyoti"],
    "pmsby": [r"PMSBY", r"Suraksha Bima"],
    "pmjay_senior": [r"PM-?JAY", r"Ayushman", r"Vay Vandana"],
    "pm_kisan": [r"PM-?KISAN", r"Kisan Samman"],
    "pmuy": [r"PMUY", r"Ujjwala", r"उज्ज्वला"],
    "ssy": [r"\bSSY\b", r"Sukanya"],
    "pmmvy": [r"PMMVY", r"Matru Vandana"],
}

_I = re.I
NEG = re.compile(
    r"\bnot(?!\s+only)\b|\b\w+n't\b|\bcannot\b|\bineligible\b|\bunavailable\b|\bunable\b|\bno\s+longer\b|"
    r"\bexclud\w*|\brejected\b|\bdenied\b|\bbarred\b|\bdisqualif\w*|"
    r"\bnahi\b|\bnahin\b|\bnhi\b|\bna\s+mil\w*|नहीं|नही|न\s+मिल|अपात्र|अयोग्य|"
    r"இல்லை|இல்ல\b|கிடைக்காது|முடியாது|இயலாது|அல்ல\b|தகுதியற்ற", _I)
POS = re.compile(
    r"\beligible\b|\bqualif(?:y|ies)\b|\bentitled\b|\bcan\s+(?:get|apply|avail|join|enrol\w*|open|receive|claim|benefit|take|register|use)\b|"
    r"\bwill\s+get\b|\b(?:you|she|he|they)\s+(?:also\s+)?gets?\b|\bavailable\b|(?<!how to )\bapply\b|\bopen\s+(?:a|an|the)\b|\bjoin\b|"
    r"\benrol\w*|\bregister\b|\bavail\b|\bcovered\b|\brecommend\w*|\bsign\s*up\b|"
    r"पात्र|योग्य|मिल\s*सक|मिलेगा|मिलेगी|मिलेंगे|मिलता\s+है|ले\s+सक|आवेदन\s+कर|खाता\s+खोल|लाभ\s+(?:ले|उठा|मिल)|हकदार|जुड़\s+सक|पा\s+सक|"
    r"\bpa(?:a)?tr\b|\byogya\b|\bmil\s+sak\w*|\bmilega\b|\bmilegi\b|\bmilenge\b|\bmilta\s+hai\b|\ble\s+sak\w*|\bapply\s+kar\w*|"
    r"\bavail\s+kar\w*|\bhak(?:h)?daar\b|\bjud\s+sak\w*|"
    r"தகுதி|கிடைக்கும்|கிடைக்கலாம்|பெறலாம்|பெற\s*முடியும்|விண்ணப்பிக்க|சேரலாம்|பயன்பெற|உரிமை", _I)
HEDGE = re.compile(r"\b(?:may|might|could|perhaps|possibly|maybe|shayad|sambhav)\b|शायद|हो\s+सकता|संभव|ஒருவேளை|கூடும்", _I)
VERIFY = re.compile(
    r"\b(?:check|verify|confirm|ask|visit|contact|app|portal|website|office)\b|जांच|जाँच|देखें|देख\s+लें|पता\s+कर|पुष्टि|चेक|संपर्क|"
    r"சரிபார்|பாருங்கள்|உறுதி|அணுக", _I)
CONDITIONAL_ANY = re.compile(r"\bwhether\b|\bagar\b|\bjab\b|अगर|यदि|जब\s|என்றால்|இருந்தால்|ஆனால்\s*மட்டும்", _I)
_IF_EN = re.compile(r"\bif\b", _I)

_SENTENCE = re.compile(r"(?<=[.!?।])\s+")
_CLAUSE = re.compile(
    r"(\s*;\s*|\s*,\s*|\s+[—–]\s+|\s+-\s+|"
    r"\s+(?:but|however|though|whereas|lekin|magar|parantu)\s+|\s*(?:लेकिन|परंतु|किंतु|मगर|ஆனால்|ஆனாலும்)\s*|"
    r"\s+(?:and|aur)\s+(?=(?:you|aap|she|he|they)\b)|\s+(?:और)\s+(?=आप\b))", _I)
_CONTRAST = re.compile(r"but|however|though|whereas|lekin|magar|parantu|लेकिन|परंतु|किंतु|मगर|ஆனால்|ஆனாலும்", _I)
_ITEM = re.compile(r"^\s*(?:[-*•+]|\d+[.)])\s+")


def mentioned(answer: str, scheme_id: str) -> bool:
    return any(re.search(p, answer, re.I) for p in MENTIONS[scheme_id])


def _own_polarity(clause: str) -> str | None:
    if NEG.search(clause):
        return "neg"
    if POS.search(clause):
        return "pos"
    return None


def _is_header(line: str) -> bool:
    s = line.strip()
    if _ITEM.match(line):
        return False
    bare = s.strip("*#_ \t")
    return s.startswith("#") or bare.endswith(":") or (s.startswith("**") and s.endswith("**") and len(s) < 90)


def _clauses_of_sentence(sentence: str) -> list[tuple[str, bool]]:
    """[(clause text, preceded by a contrast word)]"""
    parts = _CLAUSE.split(sentence)
    out, contrast = [], False
    for i, part in enumerate(parts):
        if i % 2 == 1:  # delimiter
            contrast = bool(_CONTRAST.search(part)) or contrast
            continue
        if part.strip():
            out.append((part.strip(), contrast))
        contrast = False
    return out


@lru_cache(maxsize=512)
def clause_polarities(answer: str) -> tuple[tuple[str, str | None], ...]:
    """Every clause of the answer with its polarity label (see module docstring)."""
    result: list[tuple[str, str | None]] = []
    section: str | None = None  # polarity of the header above the current list
    for line in answer.splitlines():
        if not line.strip():
            continue
        line_has_verify = bool(VERIFY.search(line))
        is_item = bool(_ITEM.match(line))
        text = _ITEM.sub("", line)
        if _is_header(line):
            text = text.strip("*#_ \t")
            section = _own_polarity(text)
            result.append((text, None if section is None else section))
            continue
        carried = section if is_item else None
        for sentence in _SENTENCE.split(text):
            if not sentence.strip():
                continue
            cond_all = bool(CONDITIONAL_ANY.search(sentence)) or bool(re.match(r"\s*if\b", sentence, _I))
            tail = None
            m = None if cond_all else _IF_EN.search(sentence)
            if m:  # "You can get X if you have land": the head still counts, the condition does not
                sentence, tail = sentence[:m.start()], sentence[m.start():]
            prev = carried
            for clause, contrast in _clauses_of_sentence(sentence):
                pol = _own_polarity(clause)
                if pol is None and not contrast:
                    pol = prev
                prev = pol
                if cond_all:
                    pol = "cond" if pol else None
                elif pol == "pos" and HEDGE.search(clause) and line_has_verify:
                    pol = "hedge"
                result.append((clause, pol))
            if tail:
                result.append((tail, "cond"))
        if not is_item:
            section = None
    return tuple(result)


def polarities(answer: str, scheme_id: str) -> list[str | None]:
    return [pol for clause, pol in clause_polarities(answer) if mentioned(clause, scheme_id)]


def claimed_available(answer: str, scheme_id: str) -> bool:
    """The answer offers the scheme as available to the user (at least one clause says so, none of which is
    negated, conditional or a hedge-plus-verify pointer). Used for recall and false-claim grading and by the runtime guard."""
    return "pos" in polarities(answer, scheme_id)


def offered_schemes(answer: str) -> list[str]:
    return [sid for sid in MENTIONS if claimed_available(answer, sid)]
