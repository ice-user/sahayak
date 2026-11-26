"""Compare latency, time-to-first-token, LLM round trips, tokens and quality across models.

    python -m evals.bench_latency --models nvidia/nemotron-3.5-super-vl-120b-a12b,nvidia/nemotron-3-super-120b-a12b,nvidia/nemotron-3-nano-30b-a3b
    python -m evals.bench_latency --models nvidia/nemotron-3-super-120b-a12b --only en_widow,hinglish,ta_ --repeat 3
    python -m evals.bench_latency --models a,b --style full --no-stream

All models are called through the provider configured by LLM_BASE_URL / LLM_API_KEY (or NVIDIA_API_KEY).
Model names must exist on that provider: check them on build.nvidia.com first; a wrong name shows up as errors.
Provider errors are reported separately and excluded from latency and quality numbers.
Results are saved to evals/results/bench-<timestamp>.json.
"""
from __future__ import annotations

import argparse
import json
import os
import time
from typing import Callable

from sahayak.agent import Agent

from .run_agent_evals import HERE, default_agent_factory, load_cases, run_case, summarize

COLUMNS = [("model", "model", 40), ("runs", "runs", 5), ("errors", "err", 4), ("latency_p50", "p50 s", 7),
           ("latency_p90", "p90 s", 7), ("ttft_p50", "ttft50", 7), ("llm_calls_mean", "calls", 6),
           ("tokens_mean", "tokens", 8), ("pass_rate", "pass", 6), ("recall", "recall", 6),
           ("no_false_claim", "no-fc", 6)]


def run_bench(models: list[str], cases: list[dict], repeat: int,
              make_agent_for: Callable[[str], Callable[[], Agent]], progress: Callable[[str], None] = print) -> dict:
    report: dict = {}
    for model in models:
        make = make_agent_for(model)
        rows = []
        for r in range(repeat):
            for case in cases:
                row = run_case(case, make)
                row["repeat"] = r + 1
                rows.append(row)
                state = f"ERROR {row['error']}" if row.get("error") else f"{row['latency_s']}s calls={row['llm_calls']}"
                progress(f"[{model}] {case['id']} #{r + 1}: {state}")
        report[model] = {"summary": summarize(rows), "rows": rows}
    return report


def format_table(report: dict) -> str:
    def cell(value, width: int) -> str:
        text = "-" if value is None else (f"{value:.2f}" if isinstance(value, float) else str(value))
        return text[-width:].rjust(width) if width < 40 else text[:width].ljust(width)

    lines = ["  ".join(title.ljust(w) if key == "model" else title.rjust(w) for key, title, w in COLUMNS)]
    lines.append("  ".join("-" * w for _, _, w in COLUMNS))
    for model, data in report.items():
        s = {**data["summary"], "model": model}
        lines.append("  ".join(cell(s.get(key), w) for key, _, w in COLUMNS))
    failing = [(m, r["id"], r["error"]) for m, d in report.items() for r in d["rows"] if r.get("error")]
    if failing:
        lines.append("")
        lines.append("errors (provider/network failures; excluded from the numbers above):")
        seen = set()
        for model, cid, err in failing:
            if (model, err) not in seen:
                seen.add((model, err))
                lines.append(f"  {model}: {err}")
    return "\n".join(lines)


def main(argv: list[str] | None = None, make_agent_for: Callable[[str], Callable[[], Agent]] | None = None) -> dict:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--models", required=True, help="comma-separated model names on your provider")
    ap.add_argument("--only", default="", help="comma-separated case-id fragments (default: all 10 cases)")
    ap.add_argument("--repeat", type=int, default=1, help="runs per case per model (use 3+ for stable percentiles)")
    ap.add_argument("--style", choices=("brief", "full"), default="brief")
    ap.add_argument("--no-stream", action="store_true", help="disable streaming (then there is no TTFT)")
    ap.add_argument("--out", default=None, help="JSON path (default evals/results/bench-<timestamp>.json)")
    args = ap.parse_args(argv)

    models = [m.strip() for m in args.models.split(",") if m.strip()]
    cases = load_cases(args.only)
    if not models or not cases or args.repeat < 1:
        ap.error("need at least one model, one matching case and --repeat >= 1")
    make_for = make_agent_for or (lambda m: default_agent_factory(m, args.style, False if args.no_stream else None))

    started = time.strftime("%Y-%m-%d %H:%M:%S")
    report = run_bench(models, cases, args.repeat, make_for)
    print("\n" + format_table(report))

    out = args.out or str(HERE / "results" / f"bench-{time.strftime('%Y%m%d-%H%M%S')}.json")
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    meta = {"started": started, "models": models, "cases": [c["id"] for c in cases], "repeat": args.repeat,
            "style": args.style, "stream": not args.no_stream and os.environ.get("LLM_STREAM", "1") != "0",
            "llm_extra_body": os.environ.get("LLM_EXTRA_BODY") or None,
            "llm_system_prefix": os.environ.get("LLM_SYSTEM_PREFIX") or None}
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"meta": meta, "models": report}, f, ensure_ascii=False, indent=2)
    print(f"\nsaved {out}")
    return report


if __name__ == "__main__":
    main()
