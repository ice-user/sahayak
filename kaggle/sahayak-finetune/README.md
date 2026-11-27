# Sahayak bullet-extractor fine-tune on Kaggle (free GPU)

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
