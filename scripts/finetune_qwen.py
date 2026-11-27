"""LoRA SFT of a small Qwen3 model: eligibility bullet -> rules JSON.  SELF-CONTAINED (no repo imports) so the
same file runs on Kaggle.  The short instruction below is THE prompt format: scripts/eval_extractors.py imports
`build_messages` from here, so training and evaluation can never drift.

    python scripts/finetune_qwen.py --train data/finetune/train.jsonl --val data/finetune/val.jsonl \
        --model Qwen/Qwen3-0.6B --epochs 2 --out models/qwen3-0.6b-bullets-lora

Device: CUDA (fp16 on T4/P100, bf16 where supported, bigger batch) else CPU fp32.  Loss on assistant tokens only,
best adapter by val loss kept in --out, loss curve in <out>/train_log.json.
"""
from __future__ import annotations

import argparse
import json
import math
import random
import time
from collections import defaultdict
from pathlib import Path

INSTRUCTION = """Convert ONE eligibility bullet of an Indian government scheme into JSON. Output JSON only:
{"rules":[{"field":..,"op":..,"value":..,"quote":..}],"unmapped":[{"quote":..,"reason":..}]}
rules: conditions a field below can express. ops: eq, ne, gte, lte, in, any_child. Numbers are integers (rupees as plain integers, age in years; "below 18" = lte 17). quote = verbatim span of the bullet.
unmapped: every other condition (caste, occupation, disability, documents...) with a short reason. No condition: both lists empty.
Fields:
age int; gender male|female|other; marital_status single|married|widowed|divorced|separated; bpl bool; annual_income int; ever_income_tax_payer bool; income_tax_payer_last_year bool; has_bank_account bool; owns_cultivable_land bool; is_govt_employee bool; monthly_pension int; household_has_lpg bool; pregnant_or_lactating bool; in_regular_govt_employment bool; children (op any_child, value = list of age/gender conditions); state (op eq or in, exact name).
States: Andaman and Nicobar Islands; Andhra Pradesh; Arunachal Pradesh; Assam; Bihar; Chandigarh; Chhattisgarh; Dadra and Nagar Haveli and Daman and Diu; Delhi; Goa; Gujarat; Haryana; Himachal Pradesh; Jammu and Kashmir; Jharkhand; Karnataka; Kerala; Ladakh; Lakshadweep; Madhya Pradesh; Maharashtra; Manipur; Meghalaya; Mizoram; Nagaland; Odisha; Puducherry; Punjab; Rajasthan; Sikkim; Tamil Nadu; Telangana; Tripura; Uttar Pradesh; Uttarakhand; West Bengal"""


def build_messages(bullet: str) -> list[dict]:
    return [{"role": "system", "content": INSTRUCTION}, {"role": "user", "content": f"Bullet: {bullet}"}]


def target_text(target: dict) -> str:
    return json.dumps(target, ensure_ascii=False, separators=(",", ":"))


def prompt_ids(tok, bullet: str) -> list[int]:
    text = tok.apply_chat_template(build_messages(bullet), tokenize=False, add_generation_prompt=True,
                                   enable_thinking=False)
    return tok(text, add_special_tokens=False)["input_ids"]


def read_jsonl(p) -> list[dict]:
    return [json.loads(line) for line in Path(p).read_text(encoding="utf-8").splitlines() if line.strip()]


def stratified_subsample(rows: list[dict], n: int, seed: int = 0) -> list[dict]:
    """Keep ~n rows, spread proportionally over the first rule's field ('none' if no rules)."""
    if n <= 0 or n >= len(rows):
        return rows
    rng = random.Random(seed)
    groups: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        rules = r["target"]["rules"]
        groups[rules[0]["field"] if rules else "none"].append(r)
    for g in groups.values():
        rng.shuffle(g)
    out: list[dict] = []
    while len(out) < n and any(groups.values()):      # round robin keeps rare fields represented
        for g in groups.values():
            if g and len(out) < n:
                out.append(g.pop())
    return out


def encode(tok, rows: list[dict], max_len: int):
    """-> (examples, n_truncated). An example that does not fit max_len is dropped (cutting a JSON target would teach garbage)."""
    eos = tok.convert_tokens_to_ids("<|im_end|>")
    ex, dropped, longest = [], 0, 0
    for r in rows:
        p = prompt_ids(tok, r["bullet"])
        t = tok(target_text(r["target"]), add_special_tokens=False)["input_ids"] + [eos]
        longest = max(longest, len(p) + len(t))
        if len(p) + len(t) > max_len:
            dropped += 1
            continue
        ex.append((p + t, [-100] * len(p) + t))
    return ex, dropped, longest


def batches(ex, bs, pad_id, shuffle, seed):
    """Length-bucketed LEFT-padded batches (so target tokens sit at the end: logits are computed only there)."""
    idx = list(range(len(ex)))
    rng = random.Random(seed)
    if shuffle:
        rng.shuffle(idx)
        chunks = [sorted(idx[i:i + bs * 16], key=lambda j: len(ex[j][0])) for i in range(0, len(idx), bs * 16)]
        idx = [j for c in chunks for j in c]
    else:
        idx.sort(key=lambda j: len(ex[j][0]))
    out = [idx[i:i + bs] for i in range(0, len(idx), bs)]
    if shuffle:
        rng.shuffle(out)
    import torch
    for b in out:
        L = max(len(ex[j][0]) for j in b)
        ids = torch.full((len(b), L), pad_id, dtype=torch.long)
        lab = torch.full((len(b), L), -100, dtype=torch.long)
        att = torch.zeros((len(b), L), dtype=torch.long)
        for k, j in enumerate(b):
            a, l = ex[j]
            ids[k, L - len(a):] = torch.tensor(a)
            lab[k, L - len(a):] = torch.tensor(l)
            att[k, L - len(a):] = 1
        yield ids, lab, att


def loss_fn(model, ids, lab, att, dev):
    import torch
    import torch.nn.functional as F
    ids, lab, att = ids.to(dev), lab.to(dev), att.to(dev)
    tgt_len = int((lab != -100).sum(1).max())            # targets are right-aligned: keep only the last tgt_len+1 positions
    keep = tgt_len + 1
    logits = model(input_ids=ids, attention_mask=att, logits_to_keep=keep).logits   # (B, keep, V)
    pred = logits[:, :-1].float()
    gold = lab[:, -keep + 1:]
    return F.cross_entropy(pred.reshape(-1, pred.size(-1)), gold.reshape(-1), ignore_index=-100)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--train", default="data/finetune/train.jsonl")
    ap.add_argument("--val", default="data/finetune/val.jsonl")
    ap.add_argument("--model", default="Qwen/Qwen3-0.6B")
    ap.add_argument("--out", default="models/qwen3-0.6b-bullets-lora")
    ap.add_argument("--merged-out", default="", help="also save a merged full model here")
    ap.add_argument("--epochs", type=int, default=2)
    ap.add_argument("--bs", type=int, default=0, help="micro-batch (default: 8 on GPU, 4 on CPU)")
    ap.add_argument("--grad-accum", type=int, default=0, help="default: 2 on GPU, 4 on CPU (effective batch 16)")
    ap.add_argument("--lr", type=float, default=2e-4)
    ap.add_argument("--max-len", type=int, default=1024)
    ap.add_argument("--max-train", type=int, default=0, help="stratified-by-field subsample of train (0 = all)")
    ap.add_argument("--max-val", type=int, default=0)
    ap.add_argument("--max-steps", type=int, default=0, help="stop after N optimizer steps (smoke test)")
    ap.add_argument("--dtype", default="auto", choices=["auto", "fp32", "fp16", "bf16"])
    ap.add_argument("--grad-ckpt", action="store_true", help="gradient checkpointing (for 1.7B on a 15 GB GPU)")
    ap.add_argument("--cache-dir", default=None)
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()

    import torch
    from peft import LoraConfig, get_peft_model
    from transformers import AutoModelForCausalLM, AutoTokenizer

    torch.manual_seed(a.seed)
    torch.set_flush_denormal(True)       # CPU: denormal floats can make fp32 matmuls crawl
    cuda = torch.cuda.is_available()
    dev = torch.device("cuda:0" if cuda else "cpu")
    if a.dtype == "auto":
        dtype = (torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16) if cuda else torch.float32
    else:
        dtype = {"fp32": torch.float32, "fp16": torch.float16, "bf16": torch.bfloat16}[a.dtype]
    bs = a.bs or (8 if cuda else 4)
    accum = a.grad_accum or (2 if cuda else 4)
    print(f"device={dev} ({torch.cuda.get_device_name(0) if cuda else 'cpu'}) dtype={dtype} bs={bs} accum={accum}", flush=True)

    tok = AutoTokenizer.from_pretrained(a.model, cache_dir=a.cache_dir)
    pad_id = tok.pad_token_id if tok.pad_token_id is not None else tok.eos_token_id
    train_rows = stratified_subsample(read_jsonl(a.train), a.max_train, a.seed)
    val_rows = stratified_subsample(read_jsonl(a.val), a.max_val, a.seed)
    tr, tr_drop, tr_long = encode(tok, train_rows, a.max_len)
    va, va_drop, va_long = encode(tok, val_rows, a.max_len)
    print(f"train {len(tr)} (dropped {tr_drop} over {a.max_len} tokens; longest {tr_long}), "
          f"val {len(va)} (dropped {va_drop}; longest {va_long})", flush=True)

    model = AutoModelForCausalLM.from_pretrained(a.model, torch_dtype=dtype, cache_dir=a.cache_dir).to(dev)
    model.config.use_cache = False
    if a.grad_ckpt:                                    # trades ~30% speed for much less activation memory
        model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False})
        model.enable_input_require_grads()
    model = get_peft_model(model, LoraConfig(r=16, lora_alpha=32, lora_dropout=0.05, task_type="CAUSAL_LM",
                                             target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                                                             "gate_proj", "up_proj", "down_proj"]))
    for p in model.parameters():                       # trainable LoRA weights stay fp32 (fp16 AdamW is unstable)
        if p.requires_grad:
            p.data = p.data.float()
    model.print_trainable_parameters()
    params = [p for p in model.parameters() if p.requires_grad]
    opt = torch.optim.AdamW(params, lr=a.lr, weight_decay=0.0)
    steps_per_epoch = math.ceil(math.ceil(len(tr) / bs) / accum)
    total = a.max_steps or steps_per_epoch * a.epochs
    sched = torch.optim.lr_scheduler.LambdaLR(
        opt, lambda s: min(1.0, (s + 1) / max(1, int(0.05 * total))) * max(0.0, 0.5 * (1 + math.cos(math.pi * min(1.0, s / total)))))
    use_amp = cuda and dtype == torch.float16
    scaler = torch.amp.GradScaler("cuda", enabled=use_amp)
    amp_dtype = dtype if cuda else None

    def evaluate() -> float:
        model.eval()
        tot, n = 0.0, 0
        with torch.no_grad():
            for ids, lab, att in batches(va, bs * 2, pad_id, False, 0):
                with torch.autocast(device_type="cuda", dtype=amp_dtype, enabled=cuda):
                    l = loss_fn(model, ids, lab, att, dev)
                k = int((lab != -100).sum())
                tot += float(l) * k
                n += k
        model.train()
        return tot / max(1, n)

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    log = {"model": a.model, "device": str(dev), "dtype": str(dtype), "bs": bs, "grad_accum": accum, "lr": a.lr,
           "epochs": a.epochs, "n_train": len(tr), "n_val": len(va), "dropped_train": tr_drop, "dropped_val": va_drop,
           "longest_example_tokens": max(tr_long, va_long), "max_len": a.max_len, "steps": [], "epochs_log": []}
    best, step, t0 = float("inf"), 0, time.time()
    model.train()
    done = False
    for ep in range(a.epochs):
        run, nrun = 0.0, 0
        micro = 0
        for ids, lab, att in batches(tr, bs, pad_id, True, a.seed + ep):
            with torch.autocast(device_type="cuda", dtype=amp_dtype, enabled=cuda):
                loss = loss_fn(model, ids, lab, att, dev)
            scaler.scale(loss / accum).backward()
            run += float(loss.detach())
            nrun += 1
            micro += 1
            if micro <= 12:
                print(f"  micro {micro} loss {float(loss.detach()):.3f} {time.time() - t0:.0f}s", flush=True)
            if micro % accum == 0:
                scaler.unscale_(opt)
                torch.nn.utils.clip_grad_norm_(params, 1.0)
                scaler.step(opt)
                scaler.update()
                opt.zero_grad(set_to_none=True)
                sched.step()
                step += 1
                if step % 10 == 0 or step <= 5:
                    el = time.time() - t0
                    print(f"ep {ep + 1} step {step}/{total} loss {run / nrun:.4f} lr {sched.get_last_lr()[0]:.2e} "
                          f"{el:.0f}s (eta {el / step * (total - step):.0f}s)", flush=True)
                    log["steps"].append({"step": step, "loss": run / nrun, "elapsed_s": round(el, 1)})
                if a.max_steps and step >= a.max_steps:
                    done = True
                    break
        vl = evaluate()
        entry = {"epoch": ep + 1, "step": step, "train_loss": run / max(1, nrun), "val_loss": vl,
                 "elapsed_s": round(time.time() - t0, 1)}
        log["epochs_log"].append(entry)
        print(entry, flush=True)
        if vl < best:
            best = vl
            model.save_pretrained(out)
            tok.save_pretrained(out)
            log["best_epoch"], log["best_val_loss"] = ep + 1, vl
        (out / "train_log.json").write_text(json.dumps(log, indent=1), encoding="utf-8")
        if done:
            break
    log["wall_time_s"] = round(time.time() - t0, 1)
    (out / "train_log.json").write_text(json.dumps(log, indent=1), encoding="utf-8")
    print(f"done in {log['wall_time_s']}s; best val loss {best:.4f}; adapter in {out}", flush=True)

    if a.merged_out:
        from peft import PeftModel
        base = AutoModelForCausalLM.from_pretrained(a.model, torch_dtype=torch.float32, cache_dir=a.cache_dir)
        merged = PeftModel.from_pretrained(base, str(out)).merge_and_unload()
        merged.save_pretrained(a.merged_out)
        tok.save_pretrained(a.merged_out)
        print(f"merged model in {a.merged_out}")


if __name__ == "__main__":
    main()
