import argparse
from pathlib import Path

from .run import run, save_scenarios, stats

DEFAULT_SCENARIOS = Path("data/distill/scenarios.jsonl")

ap = argparse.ArgumentParser(prog="python -m sahayak.datagen", description="Dummy users -> distillation data")
sub = ap.add_subparsers(dest="cmd", required=True)

p = sub.add_parser("scenarios", help="generate dummy users (no API)")
p.add_argument("--n", type=int, default=3000)
p.add_argument("--seed", type=int, default=0)
p.add_argument("--out", type=Path, default=DEFAULT_SCENARIOS)

p = sub.add_parser("run", help="dummy users talk to the teacher agent")
p.add_argument("--scenarios", type=Path, default=DEFAULT_SCENARIOS)
p.add_argument("--out", type=Path, default=Path("data/distill"))
p.add_argument("--teacher", choices=["api", "oracle"], default="api")
p.add_argument("--model", help="override the teacher model")
p.add_argument("--workers", type=int, default=4)
p.add_argument("--limit", type=int)
p.add_argument("--paraphrase", action="store_true", help="let the teacher rewrite openings more naturally")

p = sub.add_parser("stats", help="summarise a run")
p.add_argument("--out", type=Path, default=Path("data/distill"))

a = ap.parse_args()
if a.cmd == "scenarios":
    save_scenarios(a.n, a.seed, a.out)
elif a.cmd == "run":
    run(a.scenarios, a.out, a.teacher, a.workers, a.limit, a.paraphrase, a.model)
else:
    stats(a.out)
