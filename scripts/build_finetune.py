"""Build the bullet->rules fine-tuning dataset from data/sources/myscheme snapshots.

  python scripts/build_finetune.py label [--limit N] [--out DIR]   # teacher-label every bullet (resumable)
  python scripts/build_finetune.py split [--out DIR]               # scheme-level train/val/test + README

Teacher: NVIDIA via research.llm.LLM (set NVIDIA_API_KEY and LLM_MODEL in the environment; --env-file reads the
key from a .env without printing it). Labels are kept only if research.bullet_check passes.
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import random
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

SNAPS = ROOT / "data" / "sources" / "myscheme"
URLS = ROOT / "data" / "sources" / "myscheme_urls.txt"
DEFAULT_OUT = ROOT / "data" / "finetune"
SEED = 20261127
WORKERS = 4


def load_env_key(env_file: Path) -> None:
    """Put NVIDIA_API_KEY from a .env file into the environment (never printed)."""
    for ln in env_file.read_text(encoding="utf-8").splitlines():
        m = re.match(r"\s*(?:export\s+)?NVIDIA_API_KEY\s*=\s*(.*)$", ln)
        if m:
            os.environ["NVIDIA_API_KEY"] = m.group(1).strip().strip("'\"")
            return
    sys.exit("NVIDIA_API_KEY not found in env file")


def levels() -> dict[str, str]:
    out = {}
    for ln in URLS.read_text(encoding="utf-8").splitlines():
        if ln.strip() and not ln.startswith("#") and "#" in ln:
            u, tag = ln.split("#", 1)
            out[u.strip().rsplit("/", 1)[-1]] = "central" if tag.strip() == "central" else "state"
    return out


def collect_bullets() -> list[dict]:
    from research.bullets import bullets_from_file
    lv = levels()
    rows = []
    for p in sorted(SNAPS.glob("*.txt")):
        url, bullets = bullets_from_file(p)
        for b in bullets:
            rows.append({"scheme_id": p.stem, "url": url, "level": lv.get(p.stem, "unknown"), "bullet": b})
    return rows


def label_one(llm, bullet: str) -> tuple[dict | None, str]:
    """(label, error). One retry on API/parse errors."""
    from research.bullet_prompt import build_messages
    from research.llm import LLMOutputError, parse_json_object
    err = ""
    for attempt in range(2):
        try:
            return parse_json_object(llm.complete(build_messages(bullet))), ""
        except LLMOutputError as e:
            err = f"parse: {e}"
        except Exception as e:  # noqa: BLE001 - network/API errors
            err = f"api: {type(e).__name__}: {str(e)[:120]}"
            time.sleep(2)
    return None, err


def cmd_label(a) -> None:
    from research import llm as llm_mod
    from research.bullet_check import check_label
    if a.env_file:
        load_env_key(Path(a.env_file))
    for k in ("LLM_API_KEY", "LLM_BASE_URL"):      # force the NVIDIA branch of resolve_config
        os.environ.pop(k, None)
    if a.model:
        os.environ["LLM_MODEL"] = a.model
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    labels_path, stats_path = out / "labels.jsonl", out / "label_stats.json"
    done: dict[str, dict] = {}
    if labels_path.exists():
        for ln in labels_path.read_text(encoding="utf-8").splitlines():
            r = json.loads(ln)
            done[r["scheme_id"] + "\t" + r["bullet"]] = r
    rows = [r for r in collect_bullets() if r["scheme_id"] + "\t" + r["bullet"] not in done]
    if a.limit:
        rows = rows[: a.limit]
    print(f"{len(done)} labelled already, {len(rows)} to do", flush=True)
    llm = llm_mod.LLM(temperature=0.0, max_tokens=1024)
    prior = json.loads(stats_path.read_text()) if stats_path.exists() else {"calls": 0, "tokens": 0, "model": None}
    lock = threading.Lock()
    f = labels_path.open("a", encoding="utf-8")
    n = {"done": 0}

    def work(r):
        label, err = label_one(llm, r["bullet"])
        problems = [err] if err else check_label(label, r["bullet"])
        rec = {**r, "label": label, "valid": not problems, "problems": problems[:4]}
        with lock:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            f.flush()
            n["done"] += 1
            if n["done"] % 100 == 0:
                print(f"  {n['done']}/{len(rows)} calls={llm_mod.STATS['calls']} tokens={llm_mod.STATS['tokens']}",
                      flush=True)

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        list(pool.map(work, rows))
    f.close()
    stats = {"calls": prior["calls"] + llm_mod.STATS["calls"], "tokens": prior["tokens"] + llm_mod.STATS["tokens"],
             "model": os.environ.get("LLM_MODEL") or llm.model}
    stats_path.write_text(json.dumps(stats), encoding="utf-8")
    print("this run:", llm_mod.STATS, "cumulative:", stats)


def _norm(s: str) -> str:
    return re.sub(r"\W+", " ", s).casefold().strip()


def cmd_split(a) -> None:
    out = Path(a.out)
    recs = [json.loads(ln) for ln in (out / "labels.jsonl").read_text(encoding="utf-8").splitlines()]
    stats = json.loads((out / "label_stats.json").read_text()) if (out / "label_stats.json").exists() else {}
    # drop bullets whose current splitter output no longer exists is unnecessary: labels.jsonl is the source of truth
    by_scheme: dict[str, list[dict]] = collections.defaultdict(list)
    for r in recs:
        by_scheme[r["scheme_id"]].append(r)
    lvl = {s: rs[0]["level"] for s, rs in by_scheme.items()}
    rng = random.Random(SEED)
    assign: dict[str, str] = {}
    for level in sorted(set(lvl.values())):          # stratified by level so each split mirrors the mix
        ids = sorted(s for s in lvl if lvl[s] == level)
        rng.shuffle(ids)
        n_test, n_val = round(len(ids) * 0.1), round(len(ids) * 0.1)
        for i, s in enumerate(ids):
            assign[s] = "test" if i < n_test else "val" if i < n_test + n_val else "train"
    test_norm = {_norm(r["bullet"]) for s, rs in by_scheme.items() if assign[s] == "test" for r in rs}
    splits: dict[str, list[dict]] = {"train": [], "val": [], "test": []}
    test_all: list[dict] = []
    leaked = 0
    for s, rs in sorted(by_scheme.items()):
        sp = assign[s]
        for r in rs:
            base = {"scheme_id": s, "url": r["url"], "level": r["level"], "bullet": r["bullet"]}
            if sp == "test":
                test_all.append({**base, "target": r["label"] if r["valid"] else None})
            if not r["valid"]:
                continue
            if sp != "test" and _norm(r["bullet"]) in test_norm:
                leaked += 1                           # identical bullet text must not straddle train/test
                continue
            splits[sp].append({**base, "target": r["label"]})
    for name, rows in {**splits, "test_all": test_all}.items():
        with (out / f"{name}.jsonl").open("w", encoding="utf-8", newline="\n") as fh:
            for r in rows:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    write_readme(out, recs, by_scheme, assign, splits, test_all, leaked, stats)
    print({k: len(v) for k, v in splits.items()}, "test_all", len(test_all), "dropped duplicates of test", leaked)


def write_readme(out, recs, by_scheme, assign, splits, test_all, leaked, stats) -> None:
    n, ok = len(recs), sum(r["valid"] for r in recs)
    fields = collections.Counter(x["field"] for r in recs if r["valid"] for x in r["label"]["rules"])
    ops = collections.Counter(x["op"] for r in recs if r["valid"] for x in r["label"]["rules"])
    nr = sum(len(r["label"]["rules"]) for r in recs if r["valid"])
    nu = sum(len(r["label"]["unmapped"]) for r in recs if r["valid"])
    empty = sum(1 for r in recs if r["valid"] and not r["label"]["rules"] and not r["label"]["unmapped"])
    with_rules = sum(1 for r in recs if r["valid"] and r["label"]["rules"])
    probs = collections.Counter(re.sub(r"[\d\[\]]+|'[^']*'|\"[^\"]*\"", "#", p.split(":", 1)[-1].strip())[:60]
                                for r in recs if not r["valid"] for p in r["problems"][:1])
    sch = collections.Counter(assign.values())
    lev = collections.Counter(r["level"] for rs in by_scheme.values() for r in rs[:1])
    test_valid = sum(1 for r in test_all if r["target"] is not None)
    L = ["# Bullet-to-rules fine-tuning dataset", "",
         "One task: map a single eligibility bullet from a scheme page to structured rules "
         "(`research/fields.py` fields, canonical state names) plus `unmapped` conditions that no field can express.",
         "", "## How it was built", "",
         "1. `scripts/collect_myscheme.py snapshot` rendered myscheme.gov.in scheme pages "
         f"({len(by_scheme)} schemes with at least one eligibility bullet; a seeded random sample, about 40% central / 60% state, "
         "spread over states, throttled to one page per 2 s).",
         "2. `research/bullets.py` takes the second `Eligibility` heading's section (the first is the nav menu) up to the "
         "next section heading and splits it into bullets/sentences, dropping empty and boilerplate lines.",
         f"3. Teacher `{stats.get('model')}` (NVIDIA API, thinking off, temperature 0) labelled every bullet with a compact "
         "few-shot prompt (`research/bullet_prompt.py`), 4 threads, one retry on API/parse errors.",
         "4. `research/bullet_check.py` keeps a label only if: the JSON shape is exact; each rule's field/op/value is valid "
         "per `research/fields.py` and `research/validate.py` (types, ranges, canonical state names, no contradictions); "
         "each quote is a verbatim substring of the bullet; each number in a rule appears in its quote; and every number "
         "in the bullet is covered by some quote.",
         "5. Splits are by scheme (no scheme appears in two splits), 80/10/10, stratified by central/state "
         f"(seed {SEED}). Bullets identical to a test bullet were removed from train/val ({leaked} dropped).",
         "", "## Files", "",
         "Each line: `{scheme_id, url, level, bullet, target}`; target = "
         '`{"rules": [{field, op, value, quote}], "unmapped": [{quote, reason}]}`.',
         "", "- `train.jsonl`, `val.jsonl`, `test.jsonl`: checked labels only.",
         "- `test_all.jsonl`: every test-scheme bullet; `target` is null where the teacher label failed the check, "
         "so the test set is not biased toward easy bullets.",
         "- `labels.jsonl`: every teacher output with its check result and first problems (provenance).", "",
         "## Counts", "",
         f"- Schemes: {len(by_scheme)} (train {sch['train']}, val {sch['val']}, test {sch['test']}); "
         f"central {lev['central']}, state {lev['state']}",
         f"- Bullets labelled: {n}; passed the checker: {ok}",
         f"- **Teacher pass rate: {ok / n:.1%}**" if n else "- Teacher pass rate: n/a",
         f"- train {len(splits['train'])}, val {len(splits['val'])}, test {len(splits['test'])}, "
         f"test_all {len(test_all)} ({test_valid} with a target, {len(test_all) - test_valid} null)",
         f"- Among passed labels: {with_rules} bullets have at least one rule, {empty} have no rules and no unmapped "
         f"entries (no condition), {nr} rules and {nu} unmapped items in total",
         "", "## Rule field distribution (passed labels)", "", "| field | rules |", "|---|---|"]
    L += [f"| {k} | {v} |" for k, v in fields.most_common()]
    L += ["", "Ops: " + ", ".join(f"{k} {v}" for k, v in ops.most_common()), "",
          "## Most common reasons a teacher label failed", ""]
    L += [f"- {k}: {v}" for k, v in probs.most_common(8)] or ["- none"]
    L += ["", "## Teacher usage", "",
          f"- Calls: {stats.get('calls')}, total tokens: {stats.get('tokens')} (prompt + completion, as reported by the API)",
          "", "## Known limitations", "",
          "- **Labels are silver, not human gold**: they come from the teacher model and were only checked by code "
          "(shape, validity, verbatim quotes, number grounding). A label can pass and still be semantically wrong "
          "(for example a missed condition without numbers, or a field choice a human would disagree with).",
          "- The field set is small (`sahayak.models.Profile`), so most real conditions (caste, occupation, disability, "
          "education) are `unmapped`.",
          "- Bullets come from one site's English text; labels were not reviewed per state. Pages differ in style.",
          "- Sentence splitting is heuristic; some bullets are fragments or run-ons.", ""]
    (out / "README.md").write_text("\n".join(L), encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("label", "split"):
        s = sub.add_parser(name)
        s.add_argument("--out", default=str(DEFAULT_OUT))
        if name == "label":
            s.add_argument("--limit", type=int)
            s.add_argument("--env-file")
            s.add_argument("--model")
    a = ap.parse_args()
    {"label": cmd_label, "split": cmd_split}[a.cmd](a)


if __name__ == "__main__":
    main()
