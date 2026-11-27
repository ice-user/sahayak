"""LLM-as-judge for agent answers, with deterministic checks run first.

Three criteria, each scored 1-5 with a short rationale:

  faithfulness     every scheme the answer offers as available must be in the rule engine's eligible set for the
                   case profile, and the rupee amounts it quotes must exist in data/schemes.json
  language_match   the answer is in the user's language (en / hi / ta / hinglish)
  completeness     for eligible schemes: benefits, documents, how to apply, source link; when facts are missing:
                   it asks for them

Code decides first (the judge LLM is only used for what code cannot decide):
  * scheme polarity (sahayak.mentions) against the rule engine verdicts: offering a not_eligible scheme is
    faithfulness 1, offering a need_info scheme is capped at 2, an unsupported rupee amount caps it at 3
  * script-based language detection (sahayak.lang) settles hi / ta and most en answers without the model
  * a missing source link or a missing follow-up question caps completeness
  * an empty answer scores 1 everywhere with no model call
The LLM then scores the remaining criteria (claims vs. scheme data, Hinglish, quality of benefits/documents/steps)
and must return strict JSON. A reply that cannot be parsed leaves those criteria unscored (None) instead of guessing.

Reuses sahayak's client/config (make_client, resolve_config), request options (model_extra_body) and retrying
call (sahayak.llm.complete); nothing about the provider is duplicated here.
"""
from __future__ import annotations

import json
import os
import re
from typing import Any

from sahayak.agent import clean_answer, make_client, resolve_config
from sahayak.lang import DEVANAGARI, HINGLISH_MARKERS, TAMIL, detect_language
from sahayak.llm import complete
from sahayak.llm_options import model_extra_body
from sahayak.mentions import offered_schemes
from sahayak.models import Profile, Scheme, load_schemes
from sahayak.rules import check_all

CRITERIA = ("faithfulness", "language_match", "completeness")
_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")
_AMOUNT = re.compile(r"(?:Rs\.?|INR|₹)\s*(\d[\d,]*(?:\.\d+)?)", re.I)
_URL = re.compile(r"https?://[^\s)>\]]+|(?:www\.)?[a-z0-9-]+(?:\.[a-z0-9-]+)*\.gov\.in", re.I)

JUDGE_SYSTEM = """You are a strict evaluator of answers from Sahayak, an assistant for Indian government welfare schemes.
You receive the user's question, the answer, the OFFICIAL rule-engine verdicts for the user's profile, the official scheme records, and deterministic findings.
Score ONLY the listed criteria, each an integer 1-5 (5 = fully correct), with a one-sentence rationale.
- faithfulness: every scheme the answer calls available must be eligible in the official verdicts; every benefit amount, document, rule or step must agree with the official records. Invented or contradicted facts: 1-2. Minor imprecision: 3-4.
- language_match: the answer is written in the user's language (en English, hi Hindi in Devanagari, ta Tamil, hinglish Hindi in Latin script). Scheme names and URLs may stay in English.
- completeness: for each scheme offered: benefits, documents, how to apply, source link. If facts are missing (need_info), a clear question asking for exactly those facts is complete. Out-of-scope questions: politely declining is complete.
Reply with ONLY a JSON object, no prose, no code fence, in exactly this shape (include only the requested criteria):
{"faithfulness": {"score": 4, "rationale": "..."}, "language_match": {"score": 5, "rationale": "..."}, "completeness": {"score": 3, "rationale": "..."}}"""


# --------------------------------------------------------------------------- ground truth and deterministic checks
def ground_truth(case: dict, schemes: dict[str, Scheme] | None = None) -> dict[str, list[str]] | None:
    """Rule-engine verdicts for the case profile ({eligible, not_eligible, need_info}); None for cases with no profile."""
    if "profile" not in case:
        return None
    schemes = schemes or load_schemes()
    results = check_all(Profile(**case["profile"]), schemes)
    return {v: [r.scheme_id for r in results if r.verdict == v] for v in ("eligible", "not_eligible", "need_info")}


def _numbers(text: str) -> set[str]:
    return {n.replace(",", "").rstrip(".") for n in _NUMBER.findall(text or "")}


def _scheme_numbers(schemes: dict[str, Scheme]) -> set[str]:
    out: set[str] = set()
    for s in schemes.values():
        out |= _numbers(" ".join([s.summary, s.benefits, s.how_to_apply, *s.caveats, *s.documents,
                                  *(str(r.get("reason", "")) for r in s.rules)]))
    return out


def unsupported_amounts(answer: str, case: dict, schemes: dict[str, Scheme]) -> list[str]:
    """Rupee amounts quoted in the answer that appear neither in data/schemes.json nor in the user's own question."""
    allowed = _scheme_numbers(schemes) | _numbers(case.get("query", ""))
    for v in (case.get("profile") or {}).values():
        if isinstance(v, int) and not isinstance(v, bool):
            allowed.add(str(v))
    bad = []
    for m in _AMOUNT.findall(answer or ""):
        n = m.replace(",", "").rstrip(".")
        if n not in allowed and n not in bad:
            bad.append(n)
    return bad


def _script_ratio(text: str, pattern: re.Pattern) -> float:
    letters = [c for c in text if c.isalpha()]
    return sum(1 for c in letters if pattern.match(c)) / len(letters) if letters else 0.0


def language_check(expected: str, answer: str) -> tuple[int | None, str]:
    """(score, reason) when code can decide the language criterion, (None, reason) when the LLM must."""
    got = detect_language(answer)
    if expected in ("hi", "ta"):
        ratio = _script_ratio(answer, DEVANAGARI if expected == "hi" else TAMIL)
        if ratio >= 0.4:
            return 5, f"{ratio:.0%} of letters are in the expected script"
        if ratio < 0.1:
            return 1, f"expected {expected} but the answer is detected as {got}"
        return None, f"mixed script ({ratio:.0%} {expected})"
    if expected == "en":
        if got in ("hi", "ta"):
            return 1, f"expected English but the answer is detected as {got}"
        return (5, "English answer") if got == "en" else (None, "English question, answer looks Hinglish")
    if expected == "hinglish":
        if got in ("hi", "ta"):
            return 2, f"expected Latin-script Hinglish but the answer is in {got} script"
        words = set(re.findall(r"[a-z]+", answer.lower()))
        if got == "hinglish" and len(words & HINGLISH_MARKERS) >= 3:
            return 5, "Latin script with several Hindi marker words"
        return None, "Hinglish needs a judgement call"
    return None, f"unknown expected language {expected!r}"


def deterministic_checks(case: dict, answer: str, schemes: dict[str, Scheme] | None = None) -> dict:
    """Everything code can decide. Returns {truth, offered, violations, unsupported_amounts, missing_sources,
    language, caps, decided}; `decided` maps a criterion to (score, rationale) when no LLM is needed for it and
    `caps` maps a criterion to (max_score, reason) that bounds the LLM's score."""
    schemes = schemes or load_schemes()
    truth = ground_truth(case, schemes)
    answer = answer or ""
    offered = offered_schemes(answer)
    out: dict[str, Any] = {"truth": truth, "offered": offered, "violations": [], "unsupported_amounts": [],
                           "missing_sources": [], "language": None, "caps": {}, "decided": {}}
    caps, decided = out["caps"], out["decided"]

    if not answer.strip():
        for c in CRITERIA:
            decided[c] = (1, "empty answer")
        return out

    # faithfulness: offered schemes vs. rule-engine verdicts
    allowed = set(truth["eligible"]) if truth else set()
    for sid in offered:
        if sid not in allowed:
            verdict = "not_eligible" if truth and sid in truth["not_eligible"] else "need_info" if truth else "no_profile"
            out["violations"].append({"scheme": sid, "verdict": verdict})
    hard = [v for v in out["violations"] if v["verdict"] in ("not_eligible", "no_profile")]
    if hard:
        decided["faithfulness"] = (1, "offers as available: " + ", ".join(f"{v['scheme']} ({v['verdict']})" for v in hard))
    elif out["violations"]:
        caps["faithfulness"] = (2, "offers schemes whose verdict is need_info: " + ", ".join(v["scheme"] for v in out["violations"]))
    out["unsupported_amounts"] = unsupported_amounts(answer, case, schemes)
    if out["unsupported_amounts"] and "faithfulness" not in decided:
        prev = caps.get("faithfulness", (5, ""))[0]
        caps["faithfulness"] = (min(prev, 3), "amounts not in schemes.json: " + ", ".join(out["unsupported_amounts"]))

    # language
    lang_score, lang_reason = language_check(case.get("lang", "en"), answer)
    out["language"] = lang_reason
    if lang_score is not None:
        decided["language_match"] = (lang_score, lang_reason)

    # completeness: source link for each offered eligible scheme; follow-up question when facts are missing
    for sid in offered:
        if sid in allowed and sid in schemes:
            src = schemes[sid].source_url
            host = re.sub(r"^https?://", "", src).split("/")[0]
            if src not in answer and host not in answer:
                out["missing_sources"].append(sid)
    if out["missing_sources"]:
        caps["completeness"] = (3, "no source link for: " + ", ".join(out["missing_sources"]))
    if case.get("expect_followup") and "?" not in answer:
        caps["completeness"] = (2, "facts are missing but the answer asks no question")
    return out


# ------------------------------------------------------------------------------------------- JSON parsing
def _clamp(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, str):
        m = re.search(r"\d+(?:\.\d+)?", value)
        if not m:
            return None
        value = float(m.group())
    if isinstance(value, (int, float)):
        return max(1, min(5, int(round(value))))
    return None


def _json_objects(text: str):
    """Every top-level JSON object found in `text`, in order (tolerates prose and code fences around it)."""
    dec, i = json.JSONDecoder(), 0
    while True:
        i = text.find("{", i)
        if i < 0:
            return
        try:
            obj, end = dec.raw_decode(text, i)
        except json.JSONDecodeError:
            i += 1
            continue
        if isinstance(obj, dict):
            yield obj
        i = end


def parse_judge_json(raw: str) -> dict[str, dict]:
    """Parse a judge reply into {criterion: {"score": int 1-5, "rationale": str}}; criteria that are missing or
    unusable are left out. Never raises. Accepts <think> blocks, ```json fences, text around the object, scores as
    ints / floats / "4" / "4/5", and the flat shape {"faithfulness": 4, "faithfulness_rationale": "..."}."""
    text = re.sub(r"```(?:json)?", "", clean_answer(raw or ""))
    best: dict[str, dict] = {}
    for obj in _json_objects(text):
        if isinstance(obj.get("scores"), dict):
            obj = {**obj, **obj["scores"]}
        found: dict[str, dict] = {}
        for crit in CRITERIA:
            entry = obj.get(crit, obj.get(f"{crit}_score"))
            if isinstance(entry, dict):
                score, why = _clamp(entry.get("score")), entry.get("rationale", entry.get("reason", ""))
            else:
                score = _clamp(entry)
                why = obj.get(f"{crit}_rationale", obj.get(f"{crit}_reason", ""))
            if score is not None:
                found[crit] = {"score": score, "rationale": str(why or "").strip()[:400]}
        if len(found) > len(best):
            best = found
    return best


# ------------------------------------------------------------------------------------------------ the judge
def _records(case: dict, det: dict, schemes: dict[str, Scheme]) -> str:
    ids = list(dict.fromkeys([*(det["truth"] or {}).get("eligible", []), *det["offered"], *case.get("expect_not_claimed", [])]))
    return json.dumps([{"id": s.id, "name": s.name, "benefits": s.benefits, "documents": s.documents,
                        "how_to_apply": s.how_to_apply, "source_url": s.source_url, "caveats": s.caveats}
                       for s in (schemes[i] for i in ids if i in schemes)], ensure_ascii=False)


def build_messages(case: dict, answer: str, det: dict, todo: list[str], schemes: dict[str, Scheme]) -> list[dict]:
    truth = det["truth"]
    findings = {"schemes_answer_offers_as_available": det["offered"], "violations": det["violations"],
                "amounts_not_in_schemes_json": det["unsupported_amounts"], "missing_source_links": det["missing_sources"],
                "language_check": det["language"]}
    body = (f"Criteria to score: {', '.join(todo)}\n"
            f"User language: {case.get('lang')}\nUser question: {case['query']}\n"
            f"User must be asked a follow-up (facts missing): {bool(case.get('expect_followup'))}\n"
            f"Official rule-engine verdicts for the user's profile: {json.dumps(truth) if truth else 'no profile (out of scope question)'}\n"
            f"Official scheme records: {_records(case, det, schemes)}\n"
            f"Deterministic findings: {json.dumps(findings, ensure_ascii=False)}\n\n"
            f"ANSWER TO EVALUATE:\n{answer}")
    return [{"role": "system", "content": JUDGE_SYSTEM}, {"role": "user", "content": body}]


class Judge:
    """Scores one agent answer. `client` is any OpenAI-compatible client (default: sahayak's configured one)."""

    def __init__(self, client=None, model: str | None = None, schemes: dict[str, Scheme] | None = None,
                 delays: tuple[float, ...] = (1.0, 3.0)):
        self.client = client
        self.model = model or os.environ.get("JUDGE_MODEL") or resolve_config()[2]
        self.schemes = schemes or load_schemes()
        self.delays = delays

    def _call(self, messages: list[dict]) -> str:
        if self.client is None:
            self.client = make_client(timeout=120, max_retries=0)
        kwargs: dict[str, Any] = {"model": self.model, "messages": messages, "temperature": 0, "max_tokens": 900}
        extra = model_extra_body(self.model)
        if extra:
            kwargs["extra_body"] = extra
        return clean_answer(complete(self.client, kwargs, stream=False, delays=self.delays).content)

    def judge(self, case: dict, answer: str) -> dict:
        """{faithfulness, language_match, completeness: {score|None, rationale, source: code|llm|llm+cap},
        deterministic: {...}, judge_model, error?}"""
        det = deterministic_checks(case, answer, self.schemes)
        result: dict[str, Any] = {c: None for c in CRITERIA}
        todo = [c for c in CRITERIA if c not in det["decided"]]
        for c, (score, why) in det["decided"].items():
            result[c] = {"score": score, "rationale": why, "source": "code"}
        parsed: dict[str, dict] = {}
        error = None
        if todo:
            try:
                parsed = parse_judge_json(self._call(build_messages(case, answer, det, todo, self.schemes)))
            except Exception as exc:  # noqa: BLE001 - a judge failure must not kill the eval run
                error = f"{type(exc).__name__}: {str(exc)[:200]}"
            if error is None and not any(c in parsed for c in todo):
                error = "judge reply had no parsable scores"
        for c in todo:
            if c not in parsed:
                result[c] = {"score": None, "rationale": error or "criterion missing from judge reply", "source": "llm"}
                continue
            score, why, source = parsed[c]["score"], parsed[c]["rationale"], "llm"
            if c in det["caps"] and score > det["caps"][c][0]:
                score, why, source = det["caps"][c][0], f"{why} [capped: {det['caps'][c][1]}]", "llm+cap"
            result[c] = {"score": score, "rationale": why, "source": source}
        det_out = {k: det[k] for k in ("offered", "violations", "unsupported_amounts", "missing_sources", "language")}
        out = {**result, "deterministic": det_out, "judge_model": self.model}
        if error:
            out["error"] = error
        return out


def judge_means(rows: list[dict]) -> dict[str, float | None]:
    """Mean score per criterion over rows that carry a judge result (unscored criteria are skipped)."""
    out: dict[str, float | None] = {}
    for c in CRITERIA:
        vals = [r["judge"][c]["score"] for r in rows
                if isinstance(r.get("judge"), dict) and isinstance(r["judge"].get(c), dict)
                and r["judge"][c].get("score") is not None]
        out[f"judge_{c}_mean"] = round(sum(vals) / len(vals), 3) if vals else None
    return out
