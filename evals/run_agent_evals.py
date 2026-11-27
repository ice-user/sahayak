"""Run the agent on evals/agent_cases.json with a real LLM and score it.

Usage (after setting LLM_BASE_URL / LLM_API_KEY / LLM_MODEL, or NVIDIA_API_KEY):
    python -m evals.run_agent_evals                    # all cases, "brief" answers like the web app
    python -m evals.run_agent_evals --only hi          # cases whose id contains "hi" (comma-separate for several)
    python -m evals.run_agent_evals --style full --no-stream --model nvidia/nemotron-3-super-120b-a12b

Quality metrics per case:
  used_tool        called the expected tool (usually check_eligibility)
  recall           share of expected-eligible schemes the answer mentions
  no_false_claim   none of the "expect_not_claimed" schemes is named in the answer
                   as if available (heuristic: name appears without a negation nearby)
  asked_followup   for vague questions, the answer asks a question
Hardship cases (optional case keys; "turns" = earlier user messages sent first, "query" is the last one):
  max_questions            questions_ok: the answer has at most this many "?"
  no_terms                 no_forbidden: none of these regexes matches the answer (e.g. an LPG question for a homeless user)
  expect_help              help_present: the answer points to each listed resource id of data/help_resources.json
  expect_lead_help         leads_with_help: that resource appears in the first 220 characters
  expect_no_tools          no_tools: no tool was called (a crisis reply must not start a scheme checklist)
  expect_no_false_eligibility  no_false_eligibility: no scheme is offered as available unless the rule engine says eligible
Optional --judge [--judge-model M] adds an LLM-as-judge pass (evals/judge.py): deterministic checks first, then a
strict-JSON rubric scoring faithfulness / language_match / completeness 1-5. The means appear in SUMMARY as
judge_*_mean. --min-pass-rate / --min-faithfulness make the run exit 1 when a threshold is missed (used by CI).
Cost metrics per case: latency_s, ttft_s (first streamed token; empty when not streaming), llm_calls, tokens.

A provider/network failure is an ERROR, not a quality fail: transient ones are retried once, and rows that still
fail are reported separately ("errors") and left out of every quality and latency average.
The mention detector is a heuristic. Read the saved answers in evals/results/ before trusting any single number.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import Callable

from sahayak.agent import Agent
from sahayak.llm import is_transient
from sahayak.mentions import MENTIONS, claimed_available, mentioned  # noqa: F401
from sahayak.models import Profile, load_schemes
from sahayak.rules import check_all
from sahayak.vulnerability import mentions_resource

HERE = Path(__file__).parent
QUALITY_KEYS = ("used_tool", "recall", "no_false_claim", "asked_followup", "questions_ok", "no_forbidden", "help_present",
                "leads_with_help", "no_tools", "no_false_eligibility")
RETRY_PAUSE_S = 2.0


def score(case: dict, answer: str, tool_names: list[str]) -> dict:
    s: dict = {}
    if case.get("expect_tool"):
        s["used_tool"] = case["expect_tool"] in tool_names
    exp = case.get("expect_eligible", [])
    if exp:
        s["recall"] = sum(mentioned(answer, i) for i in exp) / len(exp)
    if case.get("expect_not_claimed"):
        s["no_false_claim"] = not any(claimed_available(answer, i) for i in case["expect_not_claimed"])
    if case.get("expect_followup"):
        s["asked_followup"] = "?" in answer
    if "max_questions" in case:
        s["questions_ok"] = answer.count("?") + answer.count("\uff1f") <= case["max_questions"]
    if case.get("no_terms"):
        s["no_forbidden"] = not any(re.search(t, answer, re.I) for t in case["no_terms"])
    if case.get("expect_help"):
        s["help_present"] = all(mentions_resource(answer, r) for r in case["expect_help"])
    if case.get("expect_lead_help"):
        s["leads_with_help"] = mentions_resource(answer[:220], case["expect_lead_help"])
    if case.get("expect_no_tools"):
        s["no_tools"] = not tool_names
    if case.get("expect_no_false_eligibility"):
        s["no_false_eligibility"] = not false_eligibility_claims(case, answer)
    return s


def false_eligibility_claims(case: dict, answer: str) -> list[str]:
    """Schemes the answer offers as available although the rule engine does not say eligible for the case's facts
    (a case without a profile has no confirmed scheme at all)."""
    schemes = load_schemes()
    results = check_all(Profile(**case["profile"]), schemes) if case.get("profile") else []
    eligible = {r.scheme_id for r in results if r.verdict == "eligible"}
    return [sid for sid in schemes if sid not in eligible and claimed_available(answer, sid)]


def load_cases(only: str = "") -> list[dict]:
    """Cases whose id contains any of the comma-separated fragments in `only` (all cases when empty)."""
    wanted = [w.strip() for w in only.split(",") if w.strip()]
    cases = json.loads((HERE / "agent_cases.json").read_text(encoding="utf-8"))
    return [c for c in cases if not wanted or any(w in c["id"] for w in wanted)]


def passed(row: dict) -> bool | None:
    """True when every quality check present on the row passed; None for an error row (neither pass nor fail)."""
    if row.get("error"):
        return None
    return all(row[k] >= 1.0 if k == "recall" else bool(row[k]) for k in QUALITY_KEYS if k in row)


def _describe(exc: BaseException) -> str:
    status = getattr(exc, "status_code", None)
    return f"{type(exc).__name__}{f' ({status})' if status else ''}: {str(exc)[:200]}"


def run_case(case: dict, make_agent: Callable[[], Agent], retries: int = 1,
             sleep: Callable[[float], None] = time.sleep) -> dict:
    """One fresh conversation. Transient provider errors are retried up to `retries` more times."""
    attempts = 0
    while True:
        attempts += 1
        agent = make_agent()
        t0 = time.time()
        first_token: list[float] = []

        def on_event(kind: str, data: dict) -> None:
            if kind == "token" and not first_token:
                first_token.append(time.time() - t0)

        try:
            for earlier in case.get("turns", []):  # earlier user messages of a multi-turn case
                agent.chat(earlier)
            t0 = time.time()
            answer, trace = agent.chat(case["query"], on_event=on_event)
        except Exception as exc:  # noqa: BLE001 - reported as an error row, never as a quality failure
            if attempts <= retries and is_transient(exc):
                sleep(RETRY_PAUSE_S)
                continue
            return {"id": case["id"], "lang": case["lang"], "latency_s": round(time.time() - t0, 2), "attempts": attempts,
                    "error": _describe(exc), "answer": ""}
        latency = time.time() - t0
        tools = [s["name"] for s in trace.tool_calls()]
        ttft = trace.ttft_s if trace.ttft_s is not None else (first_token[0] if first_token else None)
        return {"id": case["id"], "lang": case["lang"], "latency_s": round(latency, 2),
                "ttft_s": round(ttft, 2) if ttft is not None else None, "llm_calls": trace.llm_calls,
                "tokens": sum(s.get("tokens") or 0 for s in trace.llm_steps()), "tools": tools, "attempts": attempts,
                **score(case, answer, tools), "answer": answer}


def percentile(values: list[float], p: float) -> float | None:
    """Linear-interpolated percentile (p in 0..100); None for no data."""
    if not values:
        return None
    xs = sorted(values)
    k = (len(xs) - 1) * p / 100
    lo = int(k)
    hi = min(lo + 1, len(xs) - 1)
    return round(xs[lo] + (xs[hi] - xs[lo]) * (k - lo), 3)


def _mean(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 3) if values else None


def summarize(rows: list[dict]) -> dict:
    """Aggregate rows. Error rows are counted in `errors` and excluded from everything else."""
    ok = [r for r in rows if not r.get("error")]
    summary: dict = {"runs": len(rows), "errors": len(rows) - len(ok)}
    if any("judge" in r for r in ok):
        from evals.judge import judge_means
        summary["judged"] = sum(1 for r in ok if "judge" in r)
        summary.update(judge_means(ok))
    for key in QUALITY_KEYS:
        summary[key] = _mean([float(r[key]) for r in ok if key in r])
    verdicts = [passed(r) for r in ok]
    summary["pass_rate"] = _mean([float(v) for v in verdicts]) if verdicts else None
    lat = [r["latency_s"] for r in ok]
    summary.update(
        latency_p50=percentile(lat, 50), latency_p90=percentile(lat, 90), latency_mean=_mean(lat),
        ttft_p50=percentile([r["ttft_s"] for r in ok if r.get("ttft_s") is not None], 50),
        llm_calls_mean=_mean([r["llm_calls"] for r in ok]), tokens_mean=_mean([r["tokens"] for r in ok]))
    return summary


def threshold_failures(summary: dict, min_pass_rate: float | None, min_faithfulness: float | None) -> list[str]:
    """Human-readable reasons the run misses its gates (a missing metric counts as a failure when a gate is set)."""
    out = []
    for name, value, floor in (("pass_rate", summary.get("pass_rate"), min_pass_rate),
                               ("judge_faithfulness_mean", summary.get("judge_faithfulness_mean"), min_faithfulness)):
        if floor is not None and (value is None or value < floor):
            out.append(f"{name}={value} < {floor}")
    return out


def default_agent_factory(model: str | None, style: str, stream: bool | None, client=None) -> Callable[[], Agent]:
    from sahayak.agent import make_client
    shared = client or make_client(timeout=120, max_retries=0)
    return lambda: Agent(client=shared, model=model, answer_style=style, stream=stream)


def main(argv: list[str] | None = None, make_agent: Callable[[], Agent] | None = None) -> dict:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", default="", help="comma-separated id fragments")
    ap.add_argument("--model", default=None, help="default: LLM_MODEL / NVIDIA_MODEL")
    ap.add_argument("--style", choices=("brief", "full"), default="brief")
    ap.add_argument("--no-stream", action="store_true", help="measure without streaming (no TTFT)")
    ap.add_argument("--judge", action="store_true", help="LLM-as-judge scoring (faithfulness, language, completeness)")
    ap.add_argument("--judge-model", default=None, help="default: JUDGE_MODEL, else the configured LLM model")
    ap.add_argument("--min-pass-rate", type=float, default=None, help="exit 1 when pass_rate is below this")
    ap.add_argument("--min-faithfulness", type=float, default=None, help="exit 1 when the faithfulness mean is below this")
    args = ap.parse_args(argv)

    cases = load_cases(args.only)
    make = make_agent or default_agent_factory(args.model, args.style, False if args.no_stream else None)
    judge = None
    if args.judge:
        from evals.judge import Judge
        judge = Judge(model=args.judge_model)
    rows = []
    for case in cases:
        row = run_case(case, make)
        if judge is not None and not row.get("error"):
            row["judge"] = judge.judge(case, row["answer"])
        rows.append(row)
        flags = {k: row[k] for k in QUALITY_KEYS if k in row}
        extra = f"ERROR {row['error']}" if row.get("error") else \
            f"{row['latency_s']}s ttft={row['ttft_s']} calls={row['llm_calls']} tokens={row['tokens']}"
        if "judge" in row:
            flags["judge"] = {c: (row["judge"][c] or {}).get("score") for c in ("faithfulness", "language_match", "completeness")}
        print(f"{case['id']:<32} {flags}  {extra}")

    summary = summarize(rows)
    print("\nSUMMARY", json.dumps(summary))
    out_dir = HERE / "results"
    out_dir.mkdir(exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    (out_dir / f"run-{stamp}.json").write_text(json.dumps({"summary": summary, "rows": rows}, ensure_ascii=False, indent=2),
                                               encoding="utf-8")
    failures = threshold_failures(summary, args.min_pass_rate, args.min_faithfulness)
    for msg in failures:
        print("THRESHOLD FAILED:", msg)
    if failures:
        sys.exit(1)
    return summary


if __name__ == "__main__":
    main()
