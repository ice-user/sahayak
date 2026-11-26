"""Generate distillation data: dummy users talk to the teacher agent; passing
conversations become LoRA training data.

    # 1. make dummy users (no API needed)
    python -m sahayak.datagen scenarios --n 3000 --out data/distill/scenarios.jsonl

    # 2. test the whole pipeline offline with the stand-in teacher
    python -m sahayak.datagen run --teacher oracle --limit 50 --out data/distill_dryrun

    # 3. real run with the large model (NVIDIA, Gemini, ... from your LLM settings)
    python -m sahayak.datagen run --teacher api --workers 4 --out data/distill

    # 4. summary
    python -m sahayak.datagen stats --out data/distill

Output in --out:  train.jsonl (passed), rejected.jsonl (failed, with reasons).
Runs are resumable: scenarios already in either file are skipped. A crash can leave a truncated last line;
it is dropped on the next start. Writes are safe for the worker threads of ONE process (single lock, one
os.write + fsync per record); do not run two `run` processes on the same --out directory.
"""
from __future__ import annotations

import json
import logging
import os
import random
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from ..agent import Agent, make_client, resolve_config
from ..tools import TOOL_SCHEMAS, Toolbox
from .grader import grade
from .oracle import OracleClient
from .profiles import Scenario, generate
from .simuser import SimUser

PARAPHRASE_PROMPT = """Rewrite this message so it sounds like a real person typing on their phone, in the SAME language and script ({lang}).
Keep every fact exactly (numbers, yes/no facts, relationships). Do NOT add any new fact. Return only the rewritten message.

Message: {text}"""


log = logging.getLogger("sahayak.datagen")
_WRITE_LOCK = threading.Lock()


def read_jsonl(path: Path) -> list[dict]:
    """All parseable records; blank and corrupt lines are skipped (with a warning)."""
    out: list[dict] = []
    if not Path(path).exists():
        return out
    with open(path, encoding="utf-8", errors="replace") as f:
        for n, line in enumerate(f, 1):
            if not line.strip():
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                log.warning("%s line %d is not valid JSON; skipped", path, n)
    return out


def repair_jsonl(path: Path) -> None:
    """Make an append-only JSONL file safe to append to after a crash: a last line without a newline is
    kept (and terminated) if it parses, otherwise cut off."""
    path = Path(path)
    if not path.exists():
        return
    data = path.read_bytes()
    if not data or data.endswith(b"\n"):
        return
    cut = data.rfind(b"\n") + 1
    try:
        json.loads(data[cut:].decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        log.warning("%s: dropping truncated last line (%d bytes)", path, len(data) - cut)
        with open(path, "r+b") as f:
            f.truncate(cut)
    else:
        with open(path, "ab") as f:
            f.write(b"\n")


def append_record(path: Path, record: dict) -> None:
    """Append one JSON line with a single write call, flushed to disk. Thread-safe within one process."""
    data = (json.dumps(record, ensure_ascii=False, default=list) + "\n").encode("utf-8")
    with _WRITE_LOCK:
        fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
        try:
            view = memoryview(data)
            while view:  # os.write may be partial for very large records
                view = view[os.write(fd, view):]
            os.fsync(fd)
        finally:
            os.close(fd)


def save_scenarios(n: int, seed: int, out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        for s in generate(n, seed):
            f.write(json.dumps(s.to_dict(), ensure_ascii=False) + "\n")
    print(f"Wrote {n} dummy users to {out}")


def load_scenarios(path: Path) -> list[Scenario]:
    return [Scenario(**rec) for rec in read_jsonl(path)]


def _chat_with_retry(agent: Agent, message: str, retries: int = 5):
    for attempt in range(retries):
        n = len(agent.messages)
        try:
            return agent.chat(message)
        except Exception as e:  # rate limits, timeouts, 5xx
            del agent.messages[n:]
            if attempt == retries - 1:
                raise
            wait = min(60, 2 ** attempt * 3) + random.random()
            print(f"  retry in {wait:.0f}s after {type(e).__name__}: {str(e)[:120]}")
            time.sleep(wait)


def _paraphrase(client, model: str, text: str, lang: str) -> str:
    try:
        r = client.chat.completions.create(model=model, temperature=0.9, messages=[
            {"role": "user", "content": PARAPHRASE_PROMPT.format(lang=lang, text=text)}])
        out = (r.choices[0].message.content or "").strip()
        return out if 10 < len(out) < 3 * len(text) + 50 else text
    except Exception:
        return text


def _export_messages(messages: list[dict]) -> list[dict]:
    """OpenAI-format messages with tool-call arguments as dicts (what HF chat templates expect)."""
    out = []
    for m in messages:
        m = dict(m)
        if m.get("tool_calls"):
            m["tool_calls"] = [{"type": "function", "id": tc["id"],
                                "function": {"name": tc["function"]["name"],
                                             "arguments": _safe_json(tc["function"]["arguments"])}}
                               for tc in m["tool_calls"]]
        out.append(m)
    return out


def _safe_json(s):
    try:
        return json.loads(s) if isinstance(s, str) else s
    except json.JSONDecodeError:
        return s


def run_episode(scenario: Scenario, teacher: str, toolbox: Toolbox, client=None, model: str | None = None,
                max_user_turns: int = 4, paraphrase: bool = False) -> dict:
    sim = SimUser(scenario)
    if teacher == "oracle":
        client, model = OracleClient(sim), "oracle"
    agent = Agent(client=client, model=model, toolbox=toolbox)

    opening = scenario.opening
    if paraphrase and teacher == "api":
        opening = _paraphrase(client, model, opening, scenario.lang)

    turns, message = [], opening
    while message and len(turns) < max_user_turns:
        known = set(sim.revealed) - sim.dont_know
        answer, trace = _chat_with_retry(agent, message)
        turns.append({"revealed": known, "revealed_after": known, "answer": answer,
                      "stopped": any(s.get("stopped") for s in trace.steps),
                      "tool_calls": [{"name": s["name"], "arguments": s["arguments"]} for s in trace.tool_calls()]})
        message = sim.reply(agent.messages)

    result = grade(scenario, turns)
    return {"id": scenario.id, "lang": scenario.lang, "persona": scenario.persona,
            "messages": _export_messages(agent.messages), "tools": TOOL_SCHEMAS,
            "grade": result, "teacher": model}


def run(scenarios_path: Path, out_dir: Path, teacher: str, workers: int, limit: int | None,
        paraphrase: bool, model: str | None) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    train, rejected = out_dir / "train.jsonl", out_dir / "rejected.jsonl"
    done = set()
    for p in (train, rejected):
        repair_jsonl(p)
        done |= {rec["id"] for rec in read_jsonl(p) if "id" in rec}

    scenarios = [s for s in load_scenarios(scenarios_path) if s.id not in done]
    if limit:
        scenarios = scenarios[:limit]
    client = model_name = None
    if teacher == "api":
        base_url, _, default_model = resolve_config()
        client, model_name = make_client(), model or default_model
        print(f"Teacher: {model_name} at {base_url or 'OpenAI'}")
    toolbox = Toolbox(search_mode="bm25")  # retrieval isn't what's being distilled; keep it fast and fixed
    print(f"{len(scenarios)} conversations to run ({len(done)} already done), {workers} workers")

    counts, t0 = Counter(), time.time()

    def work(s):
        try:
            return run_episode(s, teacher, toolbox, client, model_name, paraphrase=paraphrase)
        except Exception as e:
            return {"id": s.id, "lang": s.lang, "persona": s.persona, "error": f"{type(e).__name__}: {e}",
                    "grade": {"passed": False, "reasons": ["error"]}}

    with ThreadPoolExecutor(max_workers=workers) as pool:
        for i, fut in enumerate(as_completed([pool.submit(work, s) for s in scenarios]), 1):
            rec = fut.result()
            passed = rec["grade"]["passed"]
            append_record(train if passed else rejected, rec)
            counts["passed" if passed else "rejected"] += 1
            if i % 25 == 0 or i == len(scenarios):
                rate = i / (time.time() - t0)
                print(f"  {i}/{len(scenarios)}  passed {counts['passed']}  rejected {counts['rejected']}  "
                      f"({rate * 60:.0f}/min)")
    stats(out_dir)


def stats(out_dir: Path) -> None:
    train, rej = read_jsonl(out_dir / "train.jsonl"), read_jsonl(out_dir / "rejected.jsonl")
    total = len(train) + len(rej)
    if not total:
        print("No data yet.")
        return
    print(f"\n{len(train)}/{total} passed ({len(train) / total:.0%})")
    by_lang = Counter(r["lang"] for r in train)
    by_lang_all = Counter(r["lang"] for r in train + rej)
    print("pass rate by language: " + ", ".join(f"{k} {by_lang[k]}/{v}" for k, v in sorted(by_lang_all.items())))
    turns = Counter(r["grade"].get("user_turns") for r in train)
    print("user turns in kept conversations: " + ", ".join(f"{k}: {v}" for k, v in sorted(turns.items())))
    reasons = Counter(r_.split(" '")[0].split(" [")[0] for r in rej for r_ in r["grade"]["reasons"])
    if reasons:
        print("top rejection reasons:")
        for reason, n in reasons.most_common(8):
            print(f"  {n:>4}  {reason}")
