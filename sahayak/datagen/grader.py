"""Automatic grading of a generated conversation against the dummy user's known truth.

A conversation is kept for training only if ALL checks pass:
  used_tool      called check_eligibility at least once
  facts_ok       every fact passed to check_eligibility was already told by the user, with the right value
  recall_ok      the final answer POSITIVELY offers every scheme the user is eligible for (given what they told);
                 "you are not eligible for X" does not count as naming X
  no_false_claim NO assistant turn offers a scheme the user wasn't shown eligible for at that point
                 (clause-level polarity, see sahayak/mentions.py)
  language_ok    the final answer is in the user's language (ratio-based, see script_ok)
  finished       didn't hit the step limit
"""
from __future__ import annotations

import json
import re

from ..lang import HINGLISH_MARKERS
from ..mentions import claimed_available
from ..models import Profile, load_schemes
from ..rules import check_all
from .profiles import Scenario

_SCHEMES = load_schemes()
# letters only: no digits, danda or Tamil numerals
DEVANAGARI = re.compile(r"[ऀ-ॣॱ-ॿ]")
TAMIL = re.compile(r"[஀-௥]")
LATIN = re.compile(r"[A-Za-z]")
# URLs/domains, Latin text in brackets (one nested bracket level, e.g. "(Old Age Pension Scheme (IGNOAPS))"), ALL-CAPS acronyms
_STRIP = re.compile(r"https?://\S+|\b[\w-]+(?:\.[\w-]+)+\S*|\((?:[A-Za-z0-9 .,&'/+-]|\([A-Za-z0-9 .,&'/+-]*\))+\)|\b[A-Z][A-Z0-9-]+\b")
_WORD = re.compile(r"[a-z]+")
MIN_SCRIPT_RATIO = 0.5
MIN_HINGLISH_MARKERS = 2


def _values_match(field: str, given, truth) -> bool:
    if field == "annual_income" and isinstance(given, (int, float)) and truth:
        return abs(given - truth) <= 0.15 * truth  # users say "about"
    if field == "children":
        if not isinstance(given, list):
            return False
        want = sorted((c["age"], c["gender"]) for c in truth)
        got = sorted((c.get("age"), c.get("gender")) for c in given if isinstance(c, dict))
        return got == want
    if field == "state":
        return isinstance(given, str) and given.strip().lower() == str(truth).lower()
    return given == truth


def script_ok(text: str, lang: str) -> bool:
    """Is `text` in the user's language?

    Ratio based, so one sentence in the right script cannot launder an answer in another language.
    URLs, ALL-CAPS scheme acronyms and Latin text in brackets (the prompt asks for English names in brackets)
    are ignored.
      hi / ta   at least half of the remaining letters are Devanagari / Tamil (and at least 3 of them)
      en        at most 10% of the letters are Devanagari or Tamil
      hinglish  at most 10% non-Latin letters AND at least 2 distinct common Hindi-in-Latin words
                (HINGLISH_MARKERS: hai, aap, ke, sakta, ...), so a plain English answer fails for a Hinglish user
    """
    body = _STRIP.sub(" ", text)
    dev, tam, lat = len(DEVANAGARI.findall(body)), len(TAMIL.findall(body)), len(LATIN.findall(body))
    total = dev + tam + lat
    if lang == "hi":
        return dev >= 3 and dev / total >= MIN_SCRIPT_RATIO
    if lang == "ta":
        return tam >= 3 and tam / total >= MIN_SCRIPT_RATIO
    if total and (dev + tam) / total > 0.1:
        return False
    if lang == "hinglish":
        return len(HINGLISH_MARKERS.intersection(_WORD.findall(body.lower()))) >= MIN_HINGLISH_MARKERS
    return True


def _eligible_given(truth: dict, known: set[str]) -> set[str]:
    profile = Profile(**{k: v for k, v in truth.items() if k in known})
    return {r.scheme_id for r in check_all(profile, _SCHEMES) if r.verdict == "eligible"}


def grade(scenario: Scenario, turns: list[dict]) -> dict:
    """turns: [{"revealed": set_of_fields_known_before_this_turn, "tool_calls": [...], "answer": str, "stopped": bool}]"""
    reasons: list[str] = []
    truth = scenario.profile
    calls = [(t["revealed"], tc) for t in turns for tc in t["tool_calls"] if tc["name"] == "check_eligibility"]

    used_tool = bool(calls)
    if not used_tool:
        reasons.append("never called check_eligibility")

    facts_ok = True
    for revealed, tc in calls:
        try:
            profile = (json.loads(tc["arguments"]) if isinstance(tc["arguments"], str) else tc["arguments"]).get("profile", {})
        except (json.JSONDecodeError, AttributeError):
            facts_ok = False
            reasons.append("unparseable tool arguments")
            continue
        for k, v in (profile or {}).items():
            if v is None or k not in truth:
                continue
            if k not in revealed:
                facts_ok = False
                reasons.append(f"guessed '{k}'={v!r} before the user said it")
            elif not _values_match(k, v, truth[k]):
                facts_ok = False
                reasons.append(f"wrong value for '{k}': {v!r} (truth {truth[k]!r})")

    per_turn_eligible = [_eligible_given(truth, set(t.get("revealed_after", t.get("revealed", ())))) for t in turns]
    eligible_known = per_turn_eligible[-1] if turns else set()
    answer = turns[-1]["answer"] if turns else ""

    missed = [s for s in sorted(eligible_known) if not claimed_available(answer, s)]
    recall_ok = not missed
    if missed:
        reasons.append(f"final answer does not offer eligible schemes {missed}")
    no_false_claim = True
    for i, (t, eligible) in enumerate(zip(turns, per_turn_eligible), 1):
        false_claims = [s for s in _SCHEMES if s not in eligible and claimed_available(t["answer"], s)]
        if false_claims:
            no_false_claim = False
            reasons.append(f"offers schemes the user can't get (or isn't shown eligible for) [turn {i}: {false_claims}]")

    language_ok = script_ok(answer, scenario.lang)
    if not language_ok:
        reasons.append(f"answer not in {scenario.lang} script")
    finished = not any(t.get("stopped") for t in turns)
    if not finished:
        reasons.append("hit the step limit")

    checks = dict(used_tool=used_tool, facts_ok=facts_ok, recall_ok=recall_ok, no_false_claim=no_false_claim,
                  language_ok=language_ok, finished=finished)
    return {"passed": all(checks.values()), "checks": checks, "reasons": reasons,
            "eligible_known": sorted(eligible_known), "user_turns": len(turns)}
