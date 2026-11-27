"""Score bullet -> rules extractors against a gold file.

    python scripts/eval_extractors.py --models lora,qwen3-4b,qwen3-0.6b-base,nemotron \
        --lora-dir models/qwen3-0.6b-bullets-lora [--gold data/finetune/test_gold.jsonl] [--limit 60]

Models: lora (base + LoRA adapter, CPU, short prompt), qwen3-0.6b-base (same prompt, no adapter),
qwen3-4b (Ollama, teacher few-shot prompt, /no_think, JSON-schema format), nemotron (NVIDIA API, teacher prompt),
ollama-lora (the merged fine-tune served by Ollama: same messages as `lora`, --ollama-model <tag>).
Outputs: data/finetune/eval/predictions_<model>_<gold>.jsonl and summary_<model>_<gold>.json, plus a markdown table.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import random
import re
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

EVAL_DIR = ROOT / "data" / "finetune" / "eval"
GOLD_DEFAULT = ROOT / "data" / "finetune" / "test_gold.jsonl"
SILVER = ROOT / "data" / "finetune" / "test.jsonl"
NEMOTRON_MODEL = "nvidia/nemotron-3.5-super-vl-120b-a12b"
OLLAMA_URL = "http://localhost:11434"
OLLAMA_MODEL = "qwen3-4b-16k"
NVIDIA_ENV = ROOT.parent / "source-trail" / "backend" / ".env"
ALL_MODELS = ("lora", "qwen3-4b", "qwen3-0.6b-base", "nemotron", "ollama-lora")


# ============================================================ metrics (pure functions, unit-tested)
def _norm_value(v):
    if isinstance(v, bool):
        return v
    if isinstance(v, float) and v == int(v):
        return int(v)
    if isinstance(v, str):
        return " ".join(v.casefold().split())
    if isinstance(v, list):
        items = [_norm_value(x) for x in v]
        return sorted(items, key=lambda x: json.dumps(x, sort_keys=True))
    if isinstance(v, dict):
        return {k: _norm_value(x) for k, x in sorted(v.items())}
    return v


def rule_key(rule: dict) -> tuple:
    """(field, op, normalised value) as a hashable key."""
    return (str(rule.get("field")), str(rule.get("op")), json.dumps(_norm_value(rule.get("value")), sort_keys=True))


def rule_keys(rules) -> set:
    return {rule_key(r) for r in rules if isinstance(r, dict)}


def _tokens(text: str) -> list[str]:
    return re.findall(r"\w+", str(text).casefold())


def quotes_overlap(a: str, b: str) -> bool:
    """Two quotes overlap if one contains the other, or at least half of the shorter one's tokens are shared."""
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return False
    sa, sb = " ".join(ta), " ".join(tb)
    if sa in sb or sb in sa:
        return True
    shared = len(set(ta) & set(tb))
    return shared / min(len(set(ta)), len(set(tb))) >= 0.5


def score_bullet(gold: dict, pred: dict | None) -> dict:
    """Per-bullet counts. `pred` None/invalid means no prediction (every gold rule is a miss)."""
    g_rules = [r for r in (gold.get("rules") or []) if isinstance(r, dict)]
    p_rules = [r for r in ((pred or {}).get("rules") or []) if isinstance(r, dict)] if isinstance(pred, dict) else []
    G, P = rule_keys(g_rules), rule_keys(p_rules)
    g_fields = {k[0] for k in G}
    tp = len(G & P)
    wrong = [k for k in P - G if k[0] in g_fields]            # right field, wrong op/value: a wrong age/income bound
    halluc = [k for k in P - G if k[0] not in g_fields]        # no gold rule on that field at all
    p_quotes = [str(r.get("quote", "")) for r in p_rules]
    if isinstance(pred, dict):
        p_quotes += [str(u.get("quote", "")) for u in (pred.get("unmapped") or []) if isinstance(u, dict)]
    g_um = [str(u.get("quote", "")) for u in (gold.get("unmapped") or []) if isinstance(u, dict)]
    um_hit = sum(1 for q in g_um if any(quotes_overlap(q, pq) for pq in p_quotes))
    return {"tp": tp, "n_gold": len(G), "n_pred": len(P), "safety_errors": len(wrong), "hallucinated": len(halluc),
            "exact": isinstance(pred, dict) and G == P, "um_gold": len(g_um), "um_hit": um_hit}


def _pct(x: float) -> float:
    return round(100 * x, 1)


def percentile(xs: list[float], q: float) -> float:
    if not xs:
        return 0.0
    s = sorted(xs)
    k = (len(s) - 1) * q
    lo, hi = int(k), min(int(k) + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def summarise(records: list[dict]) -> dict:
    """records: {bullet, gold, pred (dict|None), valid_json, check_ok, latency_s, tokens}."""
    n = len(records)
    sc = [score_bullet(r["gold"], r["pred"] if r["valid_json"] else None) for r in records]
    tp = sum(s["tp"] for s in sc)
    n_pred = sum(s["n_pred"] for s in sc)
    n_gold = sum(s["n_gold"] for s in sc)
    prec = tp / n_pred if n_pred else (1.0 if not n_gold else 0.0)
    rec = tp / n_gold if n_gold else 1.0
    f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
    um_gold = sum(s["um_gold"] for s in sc)
    lat = [r["latency_s"] for r in records if r.get("latency_s") is not None]
    return {
        "n": n,
        "valid_json_rate": _pct(sum(r["valid_json"] for r in records) / n) if n else 0.0,
        "bullet_check_pass_rate": _pct(sum(bool(r["check_ok"]) for r in records) / n) if n else 0.0,
        "rule_precision": _pct(prec), "rule_recall": _pct(rec), "rule_f1": _pct(f1),
        "exact_match": _pct(sum(s["exact"] for s in sc) / n) if n else 0.0,
        "safety_errors": sum(s["safety_errors"] for s in sc),
        "bullets_with_safety_error": sum(1 for s in sc if s["safety_errors"]),
        "hallucinated_rules": sum(s["hallucinated"] for s in sc),
        "unmapped_recall": _pct(sum(s["um_hit"] for s in sc) / um_gold) if um_gold else None,
        "latency_p50_s": round(percentile(lat, 0.5), 2), "latency_p90_s": round(percentile(lat, 0.9), 2),
        "tokens_per_bullet": round(statistics.mean(r.get("tokens", 0) for r in records), 1) if n else 0.0,
        "total_tokens": sum(r.get("tokens", 0) for r in records),
        "gold_rules": n_gold, "pred_rules": n_pred,
    }


def markdown_table(summaries: dict[str, dict], label: str) -> str:
    cols = [("n", "n"), ("valid_json_rate", "valid JSON %"), ("bullet_check_pass_rate", "check pass %"),
            ("rule_precision", "P %"), ("rule_recall", "R %"), ("rule_f1", "F1 %"), ("exact_match", "exact %"),
            ("safety_errors", "safety err"), ("hallucinated_rules", "halluc"), ("unmapped_recall", "unmapped R %"),
            ("latency_p50_s", "p50 s"), ("latency_p90_s", "p90 s"), ("tokens_per_bullet", "tok/bullet"),
            ("cost_usd", "cost $")]
    head = f"| model ({label}) | " + " | ".join(c[1] for c in cols) + " |"
    sep = "|" + "---|" * (len(cols) + 1)
    rows = [f"| {m} | " + " | ".join("-" if s.get(k) is None else str(s.get(k)) for k, _ in cols) + " |"
            for m, s in summaries.items()]
    return "\n".join([head, sep, *rows])


# ============================================================ extractors
def load_finetune_module():
    spec = importlib.util.spec_from_file_location("finetune_qwen", ROOT / "scripts" / "finetune_qwen.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class LocalHF:
    """Greedy decoding with the short prompt on CPU: base model, optionally + a LoRA adapter folder."""

    def __init__(self, base: str, lora_dir: str | None = None):
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer
        self.torch = torch
        self.ft = load_finetune_module()
        if lora_dir:
            cfg = json.loads((Path(lora_dir) / "adapter_config.json").read_text(encoding="utf-8"))
            base = cfg.get("base_model_name_or_path") or base      # 0.6B or 1.7B: the adapter says which
        self.tok = AutoTokenizer.from_pretrained(base)
        model = AutoModelForCausalLM.from_pretrained(base, torch_dtype=torch.float32)
        if lora_dir:
            from peft import PeftModel
            model = PeftModel.from_pretrained(model, lora_dir).merge_and_unload()
        self.model = model.eval()
        self.base = base

    def __call__(self, bullet: str) -> tuple[str, int]:
        ids = self.ft.prompt_ids(self.tok, bullet)
        x = self.torch.tensor([ids])
        with self.torch.no_grad():
            out = self.model.generate(input_ids=x, attention_mask=self.torch.ones_like(x), do_sample=False,
                                      max_new_tokens=640, pad_token_id=self.tok.eos_token_id,
                                      eos_token_id=self.tok.convert_tokens_to_ids("<|im_end|>"))
        gen = out[0][len(ids):]
        return self.tok.decode(gen, skip_special_tokens=True), len(ids) + len(gen)


def _rules_schema() -> dict:
    rule = {"type": "object", "properties": {"field": {"type": "string"}, "op": {"type": "string"}, "value": {},
                                              "quote": {"type": "string"}}, "required": ["field", "op", "value", "quote"]}
    um = {"type": "object", "properties": {"quote": {"type": "string"}, "reason": {"type": "string"}},
          "required": ["quote", "reason"]}
    return {"type": "object", "properties": {"rules": {"type": "array", "items": rule},
                                              "unmapped": {"type": "array", "items": um}},
            "required": ["rules", "unmapped"]}


class OllamaTeacher:
    def __init__(self, model: str = OLLAMA_MODEL):
        self.model = model
        from research.bullet_prompt import build_messages
        self.build = build_messages
        self.use_format = True

    def __call__(self, bullet: str) -> tuple[str, int]:
        import httpx
        msgs = self.build(bullet)
        msgs[-1] = {**msgs[-1], "content": msgs[-1]["content"] + "\n/no_think"}
        body = {"model": self.model, "messages": msgs, "stream": False, "think": False,
                "options": {"temperature": 0, "num_predict": 1024}}
        if self.use_format:
            body["format"] = _rules_schema()
        r = httpx.post(f"{OLLAMA_URL}/api/chat", json=body, timeout=600)
        if r.status_code == 400 and self.use_format:
            self.use_format = False                                  # this Ollama rejects schema formats
            return self(bullet)
        r.raise_for_status()
        d = r.json()
        return d["message"]["content"], int(d.get("prompt_eval_count", 0)) + int(d.get("eval_count", 0))


class OllamaLora:
    """The fine-tuned extractor served by Ollama (GGUF import): same messages as `lora`, greedy, think off."""

    def __init__(self, model: str, use_format: bool = False, url: str = OLLAMA_URL, post=None):
        self.model, self.use_format, self.url = model, use_format, url
        self.ft = load_finetune_module()
        if post is None:
            import httpx
            post = httpx.post
        self.post = post

    def __call__(self, bullet: str) -> tuple[str, int]:
        body = {"model": self.model, "messages": self.ft.build_messages(bullet), "stream": False, "think": False,
                "keep_alive": "30m", "options": {"temperature": 0, "num_predict": 400}}
        if self.use_format:
            body["format"] = _rules_schema()
        r = self.post(f"{self.url}/api/chat", json=body, timeout=600)
        r.raise_for_status()
        d = r.json()
        return d["message"]["content"], int(d.get("prompt_eval_count", 0)) + int(d.get("eval_count", 0))


def load_nvidia_key() -> None:
    """Put NVIDIA_API_KEY from the source-trail .env into os.environ (never printed)."""
    if os.environ.get("NVIDIA_API_KEY"):
        return
    for line in NVIDIA_ENV.read_text(encoding="utf-8").splitlines():
        m = re.match(r"\s*(?:export\s+)?NVIDIA_API_KEY\s*=\s*(.*)", line)
        if m:
            os.environ["NVIDIA_API_KEY"] = m.group(1).strip().strip("'\"")
            return
    raise SystemExit("NVIDIA_API_KEY not found in " + str(NVIDIA_ENV))


class Nemotron:
    def __init__(self, model: str = NEMOTRON_MODEL):
        load_nvidia_key()
        from openai import OpenAI
        from research.bullet_prompt import build_messages
        from research.llm import LLM
        from sahayak.agent import NVIDIA_BASE_URL
        self.llm = LLM(client=OpenAI(base_url=NVIDIA_BASE_URL, api_key=os.environ["NVIDIA_API_KEY"]), model=model,
                       max_tokens=1024)
        self.build = build_messages

    def __call__(self, bullet: str) -> tuple[str, int]:
        from research import llm as llm_mod
        before = llm_mod.STATS["tokens"]
        text = self.llm.complete(self.build(bullet))
        return text, llm_mod.STATS["tokens"] - before


# ============================================================ driver
def read_jsonl(p: Path) -> list[dict]:
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]


def evaluate(name: str, fn, rows: list[dict], out_pred: Path) -> list[dict]:
    from research.bullet_check import check_label
    from research.llm import LLMOutputError, parse_json_object
    recs = []
    with out_pred.open("w", encoding="utf-8") as fh:
        for i, row in enumerate(rows, 1):
            t0 = time.perf_counter()
            raw, toks, err = "", 0, None
            try:
                raw, toks = fn(row["bullet"])
            except Exception as e:                                   # a failed call counts as an invalid answer
                err = f"{type(e).__name__}: {str(e)[:200]}"
            lat = time.perf_counter() - t0
            pred, valid = None, False
            try:
                pred = parse_json_object(raw)
                valid = True
            except LLMOutputError:
                pass
            ok = valid and not check_label(pred, row["bullet"])
            rec = {"bullet": row["bullet"], "gold": row["target"], "pred": pred, "valid_json": valid, "check_ok": ok,
                   "latency_s": round(lat, 3), "tokens": toks}
            recs.append(rec)
            fh.write(json.dumps({**rec, "raw": raw[:2000], **({"error": err} if err else {})}, ensure_ascii=False) + "\n")
            if i % 10 == 0 or i == len(rows):
                print(f"  [{name}] {i}/{len(rows)}  last {lat:.1f}s", flush=True)
    return recs


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default="lora,qwen3-4b,qwen3-0.6b-base")
    ap.add_argument("--gold", default=str(GOLD_DEFAULT))
    ap.add_argument("--test", default=None, help="file to take bullets from (default: the gold file's own bullets)")
    ap.add_argument("--lora-dir", default="models/qwen3-0.6b-bullets-lora")
    ap.add_argument("--base-model", default="Qwen/Qwen3-0.6B", help="base for qwen3-0.6b-base (the adapter names its own)")
    ap.add_argument("--limit", type=int, default=0, help="evaluate a seeded random sample of N bullets (same for every model)")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--ollama-model", default="", help="Ollama tag for the ollama-lora model")
    ap.add_argument("--ollama-format", action="store_true", help="ollama-lora: constrain output with the JSON schema")
    ap.add_argument("--limit-for", default="", help="comma list of models the --limit applies to (default: all)")
    ap.add_argument("--price-per-mtok", type=float, default=0.0, help="USD per million NVIDIA tokens (0 = free credits)")
    a = ap.parse_args()

    gold_path = Path(a.gold)
    label = "gold"
    if not gold_path.exists():
        print(f"{gold_path} not found: falling back to silver labels in {SILVER}")
        gold_path, label = SILVER, "silver"
    gold_rows = [r for r in read_jsonl(gold_path) if r.get("target")]
    rows = gold_rows
    if a.test:
        by_bullet = {r["bullet"]: r for r in gold_rows}
        rows = [{**t, "target": by_bullet[t["bullet"]]["target"]} for t in read_jsonl(Path(a.test)) if t["bullet"] in by_bullet]
    random.Random(a.seed).shuffle(rows)
    EVAL_DIR.mkdir(parents=True, exist_ok=True)
    limit_for = set(filter(None, a.limit_for.split(",")))
    summaries: dict[str, dict] = {}
    for name in [m.strip() for m in a.models.split(",") if m.strip()]:
        if name not in ALL_MODELS:
            raise SystemExit(f"unknown model {name!r}; choose from {ALL_MODELS}")
        out_name = name
        sub = rows[:a.limit] if a.limit and (not limit_for or name in limit_for) else rows
        print(f"== {name}: {len(sub)} bullets ({label})", flush=True)
        if name == "lora":
            fn = LocalHF(a.base_model, a.lora_dir)
        elif name == "qwen3-0.6b-base":
            fn = LocalHF(a.base_model)
        elif name == "qwen3-4b":
            fn = OllamaTeacher()
        elif name == "ollama-lora":
            if not a.ollama_model:
                raise SystemExit("ollama-lora needs --ollama-model <tag>")
            fn = OllamaLora(a.ollama_model, a.ollama_format)
            out_name = "ollama_" + re.sub(r"[^\w.-]", "_", a.ollama_model) + ("_fmt" if a.ollama_format else "")
        else:
            fn = Nemotron()
        recs = evaluate(name, fn, sub, EVAL_DIR / f"predictions_{out_name}_{label}.jsonl")
        s = summarise(recs)
        s["gold_label"] = label
        s["cost_usd"] = round(s["total_tokens"] * a.price_per_mtok / 1e6, 4) if name == "nemotron" else 0.0
        if name == "lora":
            s["base_model"] = fn.base
            s["adapter"] = a.lora_dir
        (EVAL_DIR / f"summary_{out_name}_{label}.json").write_text(json.dumps(s, indent=1), encoding="utf-8")
        summaries[out_name] = s
        del fn
    print("\n" + markdown_table(summaries, label))


if __name__ == "__main__":
    main()
