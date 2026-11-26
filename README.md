# Sahayak: a multilingual agent for Indian government schemes

Ask in Hindi, Tamil, Hinglish or English, for example *"My mother is 62, a widow, BPL card holder. What can she get?"*, and Sahayak:

1. pulls the facts out of the question and asks follow-up questions when something is missing
2. searches a scheme database
3. **decides eligibility in plain Python rules, never with the LLM**
4. replies in the user's language with benefits, documents, how to apply and the official source

## Why eligibility is decided in code

If an LLM wrongly tells a widow she qualifies for a pension, she may lose a day's wages queueing at an office for nothing. So the model only *collects facts*. A deterministic engine (`sahayak/rules.py`) returns one of three verdicts:

| Verdict | Meaning | What the agent does |
|---|---|---|
| `eligible` | every rule passed | explains benefits, caveats, documents, source |
| `not_eligible` | a rule failed | says which rule and why |
| `need_info` | nothing failed, but facts are missing | asks the user for exactly those facts |

A missing fact is never treated as true or false. The test suite checks that an empty profile is never `eligible`.

Two more safety layers sit on top: a **runtime guard** (`sahayak/guard.py`) checks every final answer and blocks any scheme offered as available that the rule engine didn't confirm (one corrective retry, then a safe fallback listing only verified schemes), and strips links that aren't official sources. **Aadhaar, PAN and phone numbers are masked** (`sahayak/privacy.py`) before a message ever reaches the LLM provider.

## Architecture

```
 web/ (Next.js)  ──SSE──▶  server/ (FastAPI)  ──▶  sahayak/ agent loop ──tools──▶ search · eligibility rules · scheme details
   chat, scheme cards,        sessions, rate limit,       any OpenAI-compatible LLM            data/schemes.json
   quick replies, "why"       streaming events            (NVIDIA, Gemini, Groq, Ollama)            ▲
                                                                                                    │ human-approved merges
 research/ (LangGraph): official page/PDF ─▶ extract ─▶ verify quotes ─▶ validate ─▶ auditor agent ─▶ retry ─▶ YOU review ─▶ candidate
 sahayak/datagen: dummy users ─▶ teacher agent ─▶ grader ─▶ train.jsonl ─▶ LoRA student (next)
```

| Part | What it does | Docs |
|---|---|---|
| `sahayak/` | the chat agent: tool-calling loop, three tools, rule engine, search, MCP server | this file |
| `server/` | public API: streams tool calls, eligibility results and the answer as Server-Sent Events | `docs/API.md` |
| `web/` | the app people use: mobile-first, four languages, result cards, "Why this answer?" | `web/README.md` |
| `research/` | multi-agent LangGraph pipeline: an extractor turns official scheme pages into records with a verbatim quote for every rule (numbers compared exactly), an independent auditor agent hunts for misreadings, and a human approves before anything is merged | `research/README.md`, `research/GRAPH.md` |
| `sahayak/datagen/` | dummy users and a grader that produce distillation data for the LoRA student | below |

## Run the full app locally

```powershell
# terminal 1: backend (after loading a key, e.g. . .\scripts\use_nvidia.ps1)
$env:SAHAYAK_SEARCH="bm25"
uvicorn server.main:app --port 8000

# terminal 2: frontend
cd web; npm install
$env:NEXT_PUBLIC_API_URL="http://localhost:8000"; npm run dev      # open http://localhost:3000
# or, with no backend at all: $env:NEXT_PUBLIC_MOCK="1"; npm run dev
```

## Deploy

**Step-by-step checklist (GitHub -> Render -> Vercel -> verify, costs, rollback, troubleshooting): [DEPLOY.md](DEPLOY.md).** After deploying, run `python scripts/smoke_test.py <backend_url> --frontend <frontend_url>`.

- **Backend → Render** (free): New → Blueprint → this repo (uses `render.yaml` + `Dockerfile`). Set `NVIDIA_API_KEY` (or `LLM_*`) and `ALLOWED_ORIGINS=https://<your-vercel-app>.vercel.app` as secrets. Free instances sleep when idle, so the first request after a while is slow.
- **Frontend → Vercel** (free): import the repo, set *Root Directory* = `web`, env `NEXT_PUBLIC_API_URL=https://<your-render-service>.onrender.com` (set it before the first build; it is baked in at build time).
- The public chat spends your LLM credits: keep the rate limit (`RATE_LIMIT_PER_10MIN`) and watch usage.

## Grow the scheme database (research agent)

```powershell
python -m research run https://www.myscheme.gov.in/schemes/<scheme>   # pauses for your review
python -m research review <thread-id> --approve                        # or --reject / --edit fixed.json
python -m research merge --run-tests                                   # adds approved schemes to data/schemes.json
```

## Quick start with your NVIDIA key (Windows PowerShell)

```powershell
cd $HOME\Documents\scheme-sahayak
python -m venv .venv; .venv\Scripts\activate
pip install -r requirements.txt

Set-ExecutionPolicy -Scope Process Bypass    # allows the helper script for this window only
. .\scripts\use_nvidia.ps1                   # reads NVIDIA_API_KEY from ..\source-trail\backend\.env
python -m sahayak.check_llm                  # confirms the model is reachable AND supports tool calling
python -m evals.run_agent_evals
streamlit run app.py                         # NVIDIA is preselected; key comes from the session
```

If `check_llm` says the model didn't call a tool, try another one:
`. .\scripts\use_nvidia.ps1 -Model "meta/llama-3.3-70b-instruct"`

## Quick start with other providers (Windows PowerShell)

```powershell
cd scheme-sahayak
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m pytest -q          # runs with no API key

# pick ONE provider (any OpenAI-compatible API works):
$env:LLM_BASE_URL="https://generativelanguage.googleapis.com/v1beta/openai/"   # Gemini
$env:LLM_API_KEY="<your key>"
$env:LLM_MODEL="gemini-2.5-flash"

python -m sahayak.cli --show-tools   # terminal chat
streamlit run app.py                 # web chat (paste the key in the sidebar instead if you like)
```

The first run with hybrid search downloads a ~220 MB multilingual embedding model. Set `$env:SAHAYAK_SEARCH="bm25"` to skip it.

Other providers:

| Provider | LLM_BASE_URL | LLM_MODEL (example) |
|---|---|---|
| NVIDIA | `https://integrate.api.nvidia.com/v1` | `meta/llama-3.3-70b-instruct` (or just set `NVIDIA_API_KEY`) |
| Groq | `https://api.groq.com/openai/v1` | `llama-3.3-70b-versatile` |
| OpenAI | *(leave unset)* | `gpt-4o-mini` |
| Ollama (local, free) | `http://localhost:11434/v1` | `qwen2.5:7b` (set `LLM_API_KEY=ollama`) |

Check model names against your provider's current docs; they change often.

## Layout

```
data/schemes.json          10 central schemes: rules, benefits, documents, source URL
sahayak/models.py          Profile (all fields optional) + Scheme
sahayak/rules.py           three-verdict eligibility engine
sahayak/search.py          BM25 keyword search (no dependencies)
sahayak/hybrid.py          multilingual embeddings + BM25 merged with Reciprocal Rank Fusion; falls back to BM25
sahayak/mcp_server.py      the same 3 tools as an MCP server (Claude desktop, Cursor, ...)
app.py                     Streamlit debug chat showing tool calls, verdicts, latency and tokens (the public UI is web/)
sahayak/tools.py           the 3 agent tools + JSON schemas; tools never raise, errors go back to the model
sahayak/agent.py           tool-calling loop, step limit, per-turn trace (latency, tokens, tool calls)
sahayak/topics.py          topical scope as data + localized redirect / greeting texts + scope prompts
sahayak/topic_guard.py     topic guard: rules layer, LLM classifier, parallel TopicGate (see "Staying on topic")
sahayak/cli.py             terminal chat
sahayak/datagen/           dummy users, simulated user, grader, data generation runner
sahayak/check_llm.py       checks the configured model is reachable and supports tool calling
scripts/use_nvidia.ps1     loads the NVIDIA key from another project's .env into the current session
evals/eligibility_cases.json  22 deterministic rule cases (run in pytest)
evals/agent_cases.json     10 end-to-end cases in EN / HI / TA / Hinglish
evals/run_agent_evals.py   scores a real model: tool use, recall, false claims, follow-ups
evals/topic_cases.json     205 on/off-topic, follow-up, greeting and jailbreak cases (en / hi / Hinglish / ta)
evals/run_topic_eval.py    topic guard eval: off-topic recall, on-topic false positives, classifier latency
evals/retrieval_cases.json 20 search queries (12 English, 8 Hindi/Tamil/Hinglish)
evals/run_retrieval_eval.py  BM25 vs embeddings vs hybrid: hit@1, hit@3, MRR
tests/                     300+ tests: rules, search, agent, datagen, API server, research agent (fake LLM, no downloads)
server/                    FastAPI streaming API (see docs/API.md); Dockerfile + render.yaml deploy it
web/                       Next.js frontend (108 Vitest tests; mock mode for demos without a backend)
research/                  LangGraph scheme-research agent (fetch, extract, verify evidence, validate, review, merge)
docs/API.md                the contract between web/ and server/
```

## Latency

What costs time: every LLM round trip resends the whole context, and a long answer takes long to generate. Sahayak therefore (all covered by tests with fake clients; real-world effect is yours to measure):

- **Fewer round trips.** The prompt tells the model to call `check_eligibility` first for any question with personal facts (it checks every scheme at once), and `check_eligibility`'s `eligible` items now carry `documents` and `how_to_apply`, so `get_scheme_details` is not needed for them. Target: 2 LLM calls per typical turn (one tool call, one answer). Identical tool calls are served from a per-conversation cache. `done.llm_calls` and the trace (`trace.llm_calls`) show what each turn took.
- **Short answers in the web app.** `answer_style="brief"` (server default, `ANSWER_STYLE=full` to undo): about 120 words, `max_tokens` 450, documents and how-to-apply left to the cards. CLI and `Agent()` default to `"full"`.
- **Streaming.** The final answer is streamed as `token` events (`<think>` blocks are stripped); the guarded `answer` event always follows and replaces the tokens. If the provider rejects streaming, the call is repeated without it.
- **Retries.** 429/500/502/503/504, timeouts, connection errors and "temporarily unavailable" messages are retried twice (about 1 s, 3 s). 400/401/403/404 are not.
- **Reply script.** Each turn the user's language is detected and a hint is added to the system prompt (for example Hinglish must be written in Latin letters, not Devanagari).

Environment variables:

| Variable | Default | Effect |
|---|---|---|
| `LLM_STREAM` | on | `0` disables streaming |
| `ANSWER_STYLE` | `brief` (server) | `brief` or `full` |
| `MAX_TOKENS` | `450` (server) | max tokens per LLM call; raise it for models that think inline |
| `LLM_EXTRA_BODY` | unset | JSON object passed as `extra_body` to `chat.completions.create` |
| `LLM_SYSTEM_PREFIX` | unset | text prepended to the system prompt |

`LLM_EXTRA_BODY` and `LLM_SYSTEM_PREFIX` are things to **try and measure**: we have not verified which NVIDIA models honour them. Examples to test on a reasoning model: `LLM_SYSTEM_PREFIX="detailed thinking off"` (some Nemotron models), or `LLM_EXTRA_BODY='{"chat_template_kwargs": {"enable_thinking": false}}'` (the key depends on the model's chat template; a model that ignores it is unaffected, one that rejects it returns a 400, which shows up as errors in the benchmark). Compare with and without using the benchmark below, and check answer quality, not only speed.

### Measure it

```powershell
# one model, all 10 agent cases (brief answers, streaming on); prints latency, TTFT, LLM calls, tokens, quality
python -m evals.run_agent_evals --model meta/llama-3.3-70b-instruct

# compare models: p50/p90 latency, p50 time-to-first-token, mean LLM calls and tokens, pass rate; saves evals/results/bench-*.json
python -m evals.bench_latency --models nvidia/nemotron-3.5-super-vl-120b-a12b,meta/llama-3.3-70b-instruct,meta/llama-3.1-8b-instruct --repeat 3
python -m evals.bench_latency --models meta/llama-3.3-70b-instruct --only en_widow,hinglish,ta_ --repeat 5
$env:LLM_STREAM="0"; python -m evals.bench_latency --models <model> --no-stream     # baseline without streaming
```

Suggested NVIDIA models to compare: the configured Nemotron model, `meta/llama-3.3-70b-instruct` and a small fast one such as `meta/llama-3.1-8b-instruct`. **These names must be checked on build.nvidia.com** (names, tool-calling support and availability change; a wrong name appears as errors in the table). A small model may be fast but miss eligibility facts or the reply script: read the pass rate and the saved answers before choosing. Provider failures (503 etc.) are counted as `errors` and excluded from latency and quality numbers; each failed case is retried once first. Run a few repeats: single runs on a shared API vary a lot.

## Staying on topic

Sahayak answers about government welfare schemes only: eligibility, benefits, documents, how and where to apply, application-status pointers, and the civic documents schemes need (ration/BPL card, income or caste certificate, Aadhaar linking, a bank account for DBT). General knowledge, coding, homework, entertainment, investment, medical or legal advice, politics, unrelated writing and jailbreak attempts are redirected: the user gets one short localized text (en / hi / Hinglish / ta) saying what Sahayak can do, with 3 example questions. The scope is data in `sahayak/topics.py`; the rules, the classifier prompt and the system prompt are all generated from it.

Three layers, cheapest first (`sahayak/topic_guard.py`):

1. **Rules, no LLM.** Greetings and thanks get a canned reply (0 LLM calls). Obvious jailbreak patterns ("ignore your instructions", "show your system prompt", "you are now DAN", in four languages) are redirected. Scheme keywords (pension, yojana, योजना, BPL, ration, Ayushman, PM-KISAN, திட்டம், ஓய்வூதியம், ...), questions about Sahayak, and short replies to the assistant's own question ("yes", "haan", "62", "Tamil Nadu", "my mother", "pata nahi") are allowed. The rules never say "off topic": anything they do not recognise is "unsure" and is passed on, so a missing keyword can never block a user.
2. **LLM classifier, in parallel.** Only when the rules are unsure. A small prompt (scope + the last assistant message for context + the user message) returns `{"verdict": "on_topic" | "off_topic" | "jailbreak", "reason": ...}`. It starts at the same moment as the main turn. Timeout 4 s; timeout, error or an unreadable reply means **allow** (fail open).
3. **System prompt.** The main prompt carries a concise scope section, so the model itself declines briefly even if the classifier is off or failed.

How the parallel classifier meets streaming and history: while the verdict is pending, the turn's events (`tool_call`, `tool_result`, `token`) are buffered. `on_topic` flushes them in order; `off_topic` / `jailbreak` drops them, sends the redirect as the `answer`, stops the main turn at its next step (tools are not run, no second model call) and rolls the history back exactly like a cancelled turn. Trade-off: a slow classifier delays the first visible token (the small model normally answers before the main model's first token, so the delay is usually zero; `topic_guard.main_wait_s` in the trace shows it), and an off-topic turn still pays for the one main-model call that was already running. The main answer is never committed before the verdict is in.

| Variable | Default | Effect |
|---|---|---|
| `TOPIC_GUARD` | `classifier` | `off` (nothing), `prompt` (rules + scope in the system prompt, no extra call), `classifier` (all three layers) |
| `TOPIC_GUARD_MODEL` | the main model | classifier model. A small fast model such as `meta/llama-3.1-8b-instruct` on NVIDIA is the intended choice (**check the name on build.nvidia.com**); the same provider and key are used |
| `TOPIC_GUARD_TIMEOUT_S` | `4` | classifier timeout; past it the message is allowed |

`Agent()` reads the same variables (`topic_guard=`, `topic_model=`, `topic_client=`, `topic_timeout_s=` override them). The trace has a `topic_guard` step (`verdict`, `layer`, `latency_s`, `overlapped`, `main_wait_s`, `fail_open`) and the SSE `done` event carries `"topic"` (see `docs/API.md`). Greetings, redirects and blocked turns are not kept in the conversation history.

**Measure it** (over-blocking is the main risk, so the headline number is the on-topic false-positive rate, target <= 2%, and the follow-up one):

```powershell
python -m evals.run_topic_eval --layer rules --list-misses     # no network: the deterministic layer
$env:NVIDIA_API_KEY="nvapi-..."
$env:TOPIC_GUARD_MODEL="meta/llama-3.1-8b-instruct"            # verify the model name first
python -m evals.run_topic_eval --layer full --list-misses       # rules + real classifier, per-language report
python -m evals.run_topic_eval --layer full --agent-sample 12 --model meta/llama-3.3-70b-instruct   # + overlap with real main turns
```

`evals/topic_cases.json` has 205 hand-written cases (en / hi / Hinglish / ta, about 51 each): 117 on-topic (49 conversational follow-ups that carry the assistant's preceding question, 28 borderline in-scope such as "how do I get an income certificate?", "when will my PM-KISAN money come?"), 60 off-topic (including borderline: bank FD, medicine for knee pain, whom to vote for, resume, suing an employer, and mid-conversation off-topic requests), 12 greetings and 16 jailbreaks. Rules-layer result on it (deterministic, reproducible): on-topic false positives **0 / 117 (0.0%)**, follow-up false positives **0 / 49**, jailbreak recall 12 / 16 (75%; the misses are paraphrases and a message that also mentions "schemes", which the rules deliberately leave to the classifier or the prompt), greeting fast path 12 / 12, off-topic recall 0% by design (the rules never block plain off-topic text), 79% of on-topic messages decided without a classifier call. The cases were written together with the rules, so treat these as optimistic; the full-stack off-topic recall and false-positive numbers need a run with a real model and are not measured in this repository yet. Results are saved to `evals/results/topic-*.json`.

## Evals

```powershell
python -m evals.run_agent_evals       # needs a real LLM; saves evals/results/run-*.json
```

Reports `used_tool`, `recall` (expected schemes mentioned), `no_false_claim` (doesn't offer a scheme the user can't get) and `asked_followup`, with latency and tokens. Mention detection is a heuristic, so read the saved answers before trusting any single number. Run the same evals on 2–3 models and put the comparison table in this README.

### Retrieval

```powershell
python -m evals.run_retrieval_eval
```

BM25 baseline on the 20 queries: hit@1 **0.65** overall but only **0.12** on the 8 non-English queries, since keywords can't match Hindi or Tamil text against English scheme descriptions. Run the eval to fill in the dense and hybrid rows:

| Search | hit@1 (all) | hit@3 (all) | hit@1 (non-English) |
|---|---|---|---|
| BM25 | 0.65 | 0.70 | 0.12 |
| Embeddings | ? | ? | ? |
| Hybrid (RRF) | ? | ? | ? |

## MCP server

```powershell
python -m sahayak.mcp_server
```

Add it to Claude desktop's `claude_desktop_config.json` (the path is in the docstring of `sahayak/mcp_server.py`). Then any MCP client can use the scheme tools, and you've shown the tools are reusable outside your own agent.

## Schemes covered (central share only)

IGNOAPS (old-age pension) · IGNWPS (widow pension) · Atal Pension Yojana · PMJJBY · PMSBY · Ayushman Bharat PM-JAY for 70+ · PM-KISAN · PM Ujjwala · Sukanya Samriddhi · PM Matru Vandana.
Facts were checked against official or reputable sources on 2026-11-25/26; every scheme stores its `source_url`. States add their own amounts and rules, and schemes change, so re-check before relying on this.

## Distillation data (for the LoRA student model)

Dummy users with hidden profiles talk to the teacher agent; only conversations that pass automatic checks become training data.

```powershell
python -m sahayak.datagen run --teacher oracle --limit 50 --out data/distill_dryrun   # offline pipeline test, no API
python -m sahayak.datagen run --teacher api --limit 20 --workers 2                     # small real run first
python -m sahayak.datagen stats                                                         # pass rate, rejection reasons
python -m sahayak.datagen run --teacher api --workers 4                                 # the rest (resumable)
```

- `data/distill/scenarios.jsonl`: 3,000 dummy users (11 personas; en 30% / hi 30% / hinglish 25% / ta 15%). Each has a complete hidden profile, the facts mentioned up front, an opening message and the correct answer from the rule engine. Regenerate with `python -m sahayak.datagen scenarios --n 3000`.
- `data/distill/heldout_scenarios.jsonl`: 300 different dummy users (another seed) for testing the student. **Never train on these.**
- **Simulated user** (`sahayak/datagen/simuser.py`): answers follow-up questions truthfully from the hidden profile, up to 3 facts at a time, and says "I don't know" 8% of the time.
- **Grader** (`sahayak/datagen/grader.py`): keeps a conversation only if the agent called `check_eligibility`, never passed a fact the user hadn't said (or with the wrong value), named every scheme the user qualifies for, offered no other scheme, replied in the user's script, and finished within the step limit.
- `--teacher oracle` is a template stand-in for testing the pipeline only. Its 100% pass rate shows the plumbing works; don't train on its output.
- Output: `train.jsonl` (OpenAI/TRL `messages` + `tools` format, tool arguments as dicts) and `rejected.jsonl` (with reasons; read these to improve the teacher prompt).

**How much data:** about 300–500 passing conversations teach the format; **1,500–3,000 is the target**; beyond about 5,000 adds little for a task this narrow. Conversations average about 8,600 characters (roughly 2.5–3k tokens), so train with `max_length` 4096.

## Known limitations

- Central schemes only; state schemes and state top-ups aren't modelled yet.
- Some criteria can't be checked from a chat (e.g. whether a household is on the state BPL list, PM-JAY's SECC criteria for under-70s). These appear as caveats rather than rules.
- Only 10 schemes, so retrieval numbers are optimistic; they'll drop as the database grows, which is the point of measuring them.

## Roadmap

1. Working agent, rules, evals ✅ · hybrid search ✅ · MCP server ✅
2. FastAPI backend ✅ · Next.js frontend ✅ · LangGraph research agent ✅ · distillation data pipeline ✅
3. **Next:** run evals and the research agent with a real model; fix failures; publish the comparison table
4. Add Profile fields many schemes need (caste category, disability, student, occupation) and grow to 50+ schemes with the research agent
5. Deploy (Vercel + Render), add tracing, then a Telegram/WhatsApp front end; get real users
6. **Agent distillation:** generate teacher data, LoRA-fine-tune a 1.5B model on Kaggle, compare on the held-out dummy users, run it locally with OpenVINO
