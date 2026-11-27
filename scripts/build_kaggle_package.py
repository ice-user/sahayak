"""Build kaggle/sahayak-finetune/ (+ .zip): everything needed to train the LoRA adapters on a free Kaggle GPU.

    python scripts/build_kaggle_package.py
"""
from __future__ import annotations

import json
import shutil
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = ROOT / "kaggle" / "sahayak-finetune"

REQ = "peft>=0.14\ntransformers>=4.51\ndatasets\naccelerate\n"

README = """# Sahayak bullet-extractor fine-tune on Kaggle (free GPU)

Trains LoRA adapters for Qwen3-0.6B and Qwen3-1.7B that turn one scheme eligibility bullet into rules JSON
(about 3,700 training bullets, 2 epochs each, fp16).

On **GPU T4 x2** both models train **at the same time**: the notebook starts one background process per GPU
(`CUDA_VISIBLE_DEVICES=0` for 0.6B, `=1` for 1.7B), each writing its own log, and prints the last log line of each
every 60 s (step, loss, ETA) until both finish. The 1.7B run uses gradient checkpointing (batch 4 x accumulation 4)
so it fits in a T4's 15 GB; the 0.6B run uses batch 8 x accumulation 2. With a single GPU (e.g. P100) the notebook
detects that and trains them one after the other. Expect about 20-40 min for 0.6B and 60-120 min for 1.7B.
If either process fails, the cell prints its log tail and raises.

## Steps

1. Sign in at kaggle.com. Verify your phone number (Settings > Phone verification): Internet access in notebooks and
   GPU quota both need it.
2. Upload the data: **Create > New Dataset**. Drag in `sahayak-finetune.zip` (Kaggle unzips it) or the four files
   `train.jsonl`, `val.jsonl`, `finetune_qwen.py`, `requirements.txt`. Name it `sahayak-finetune`, click Create.
3. **Create > New Notebook**. **File > Import Notebook** and pick `sahayak_finetune.ipynb`.
4. **Add Input** (right side) > Your datasets > `sahayak-finetune`.
5. Right side **Session options**: Accelerator = **GPU T4 x2** (or **GPU P100**); Internet = **On**.
6. **Run All**. Watch the progress lines and each epoch's `val_loss`.
7. When it finishes, open the **Output** tab (or the `/kaggle/working` panel) and download
   `qwen3-0.6b-bullets-lora.zip` and `qwen3-1.7b-bullets-lora.zip` (adapter, tokenizer files, `train_log.json`).
8. Unzip both into the repo's `models/` folder, so you get
   `models/qwen3-0.6b-bullets-lora/adapter_model.safetensors` and `models/qwen3-1.7b-bullets-lora/...`.

Then, in the repo (CPU is fine; the base model downloads from Hugging Face on first use):

    .venv/Scripts/python scripts/eval_extractors.py --models lora --lora-dir models/qwen3-0.6b-bullets-lora
    .venv/Scripts/python scripts/eval_extractors.py --models lora --lora-dir models/qwen3-1.7b-bullets-lora

## Notes

- The prompt format lives in `finetune_qwen.py` (`INSTRUCTION`); the repo's eval imports the same file.
- If CUDA runs out of memory for 1.7B, lower `--bs` to 2 (and raise `--grad-accum` to 8) in the notebook's JOBS list.
- The notebook just runs `python finetune_qwen.py --model ... --out ...`; any machine with a GPU works the same way.
"""

TRAIN_CELL = '''
import subprocess, shutil, os, time
JOBS = [("Qwen/Qwen3-0.6B", "qwen3-0.6b-bullets-lora", "--bs 4 --grad-accum 4 --grad-ckpt"),
        ("Qwen/Qwen3-1.7B", "qwen3-1.7b-bullets-lora", "--bs 4 --grad-accum 4 --grad-ckpt")]   # fp16; checkpointing keeps 1.7B inside 15 GB
n_gpu = torch.cuda.device_count()
print("GPUs:", n_gpu, "->", "training both models at the same time" if n_gpu >= 2 else "one GPU: training one after the other")

def launch(model, name, extra, gpu):
    cmd = (f"python -u {PKG}/finetune_qwen.py --train {PKG}/train.jsonl --val {PKG}/val.jsonl "
           f"--model {model} --epochs 2 --dtype fp16 --out /kaggle/working/{name} {extra}")
    log = open(f"/kaggle/working/{name}.log", "w")
    print(f"[gpu {gpu}] {cmd}")
    return subprocess.Popen(cmd, shell=True, stdout=log, stderr=subprocess.STDOUT,
                            env={**os.environ, "CUDA_VISIBLE_DEVICES": str(gpu)})

def last_line(name):
    try:
        lines = [l for l in open(f"/kaggle/working/{name}.log", errors="ignore").read().splitlines() if l.strip()]
        return lines[-1][:160] if lines else "(starting...)"
    except FileNotFoundError:
        return "(no log yet)"

def wait(procs):
    while any(p.poll() is None for p in procs.values()):
        time.sleep(60)
        for name, p in procs.items():
            state = "running" if p.poll() is None else f"exit {p.poll()}"
            print(f"{time.strftime('%H:%M:%S')} {name} [{state}] {last_line(name)}")

if n_gpu >= 2:
    procs = {name: launch(m, name, extra, i) for i, (m, name, extra) in enumerate(JOBS)}
    wait(procs)
else:
    procs = {}
    for m, name, extra in JOBS:
        procs[name] = launch(m, name, extra, 0)
        wait({name: procs[name]})
for name, p in procs.items():
    print(name, "exit code", p.returncode)
failed = [n for n, p in procs.items() if p.returncode != 0]
for _, name, _ in JOBS:     # zip every model that finished (adapter + tokenizer files + train_log.json), even if the other failed
    if name not in failed and os.path.isdir(f"/kaggle/working/{name}"):
        shutil.make_archive(f"/kaggle/working/{name}", "zip", "/kaggle/working", name)
        print("wrote", f"/kaggle/working/{name}.zip", os.path.getsize(f"/kaggle/working/{name}.zip") // 1_000_000, "MB")
if failed:
    for n in failed:
        print("---- tail of", n, "----")
        print("\\n".join(open(f"/kaggle/working/{n}.log", errors="ignore").read().splitlines()[-30:]))
    raise RuntimeError(f"training failed: {failed} (finished models were still zipped above)")
'''

SUMMARY_CELL = '''
import json
for n in ("qwen3-0.6b-bullets-lora", "qwen3-1.7b-bullets-lora"):
    p = f"/kaggle/working/{n}/train_log.json"
    if os.path.exists(p):
        l = json.load(open(p))
        print(n, "wall", l.get("wall_time_s"), "s; best epoch", l.get("best_epoch"), "val", l.get("best_val_loss"))
        for e in l["epochs_log"]: print("  ", e)
print(os.listdir("/kaggle/working"))
'''

CHECK_CELL = '''
import glob, os, torch
PKG = os.path.dirname(glob.glob("/kaggle/input/**/finetune_qwen.py", recursive=True)[0])
print("package:", PKG, os.listdir(PKG))
assert torch.cuda.is_available(), "No GPU: set Session options > Accelerator to GPU T4 x2 or P100"
for i in range(torch.cuda.device_count()): print(i, torch.cuda.get_device_name(i))
print(torch.__version__)
'''


def notebook() -> dict:
    def code(src: str) -> dict:
        return {"cell_type": "code", "metadata": {}, "execution_count": None, "outputs": [],
                "source": src.strip("\n").splitlines(True)}

    def md(src: str) -> dict:
        return {"cell_type": "markdown", "metadata": {}, "source": src.strip("\n").splitlines(True)}

    return {
        "cells": [
            md("# Sahayak bullet extractor: LoRA fine-tune\n"
               "Attach the `sahayak-finetune` dataset, set Accelerator to GPU T4 x2, Internet On, then Run All. "
               "With two GPUs both models train at the same time."),
            # Kaggle ships torchao 0.10; recent peft refuses to import next to an old torchao (we don't use it).
            code("!pip install -q -r $(dirname $(find /kaggle/input -name finetune_qwen.py | head -1))/requirements.txt\n"
                 "!pip uninstall -y -q torchao"),
            code(CHECK_CELL),
            md("## Train Qwen3-0.6B and Qwen3-1.7B (2 epochs each); progress is printed every 60 s"),
            code(TRAIN_CELL),
            code(SUMMARY_CELL),
        ],
        "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
                     "language_info": {"name": "python"}},
        "nbformat": 4, "nbformat_minor": 5,
    }


def main() -> None:
    if PKG.exists():
        shutil.rmtree(PKG)
    PKG.mkdir(parents=True)
    for f in ("train.jsonl", "val.jsonl"):
        shutil.copy(ROOT / "data" / "finetune" / f, PKG / f)
    shutil.copy(ROOT / "scripts" / "finetune_qwen.py", PKG / "finetune_qwen.py")
    (PKG / "requirements.txt").write_text(REQ, encoding="utf-8")
    (PKG / "README.md").write_text(README, encoding="utf-8")
    (PKG / "sahayak_finetune.ipynb").write_text(json.dumps(notebook(), indent=1), encoding="utf-8")
    zp = PKG.parent / "sahayak-finetune.zip"
    with zipfile.ZipFile(zp, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(PKG.iterdir()):
            z.write(f, f"sahayak-finetune/{f.name}")
    print(f"{zp} ({zp.stat().st_size / 1e6:.2f} MB)")


if __name__ == "__main__":
    main()
