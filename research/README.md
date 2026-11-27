# research: the scheme-research agent

Turns an official scheme web page or PDF into a validated, evidence-backed candidate record for
`data/schemes.json`. A human approves every addition; nothing is written to `schemes.json` until
`python -m research merge`. Built with LangGraph; see [GRAPH.md](GRAPH.md) for the diagram and the role
of each node.

## Install

```powershell
pip install langgraph langgraph-checkpoint-sqlite httpx beautifulsoup4 pypdf rapidfuzz rich
```

(`openai` and `pydantic` are already in requirements.txt. `langgraph-checkpoint-sqlite` is optional but
needed if a paused review should survive a restart; without it the CLI falls back to in-memory state.)

## Real-world workflow (NVIDIA key)

```powershell
. .\scripts\use_nvidia.ps1                       # sets NVIDIA_API_KEY / model, as for the main app
# (or any OpenAI-compatible provider via LLM_BASE_URL / LLM_API_KEY / LLM_MODEL; same as sahayak.agent)

# 1. research one page: a public http(s) URL, or a local file via the explicit --file flag
python -m research run https://www.myscheme.gov.in/schemes/<slug>
python -m research run --file data/saved_page.pdf --source-url https://official.example/scheme   # say where it came from
#    local files must live under RESEARCH_ALLOWED_DIRS (default: the repo's data/ and tests/fixtures/)

# 2. read the review panel: proposed record, evidence quote for each rule, unmapped criteria,
#    warnings, and (if the id already exists) a diff against the current record. Then decide:
python -m research review <thread-id> --approve
python -m research review <thread-id> --approve --allow-url https://x.example/y   # only for off-allowlist URLs you checked
python -m research review <thread-id> --reject --note "duplicate of pm_kisan"
python -m research show <thread-id> --json > edit.json   # fix by hand, then:
python -m research review <thread-id> --edit edit.json   # re-validated; shown again for approval

# 3. many at once: file of URLs (one per line, # comments allowed) or links harvested from a listing page
python -m research batch urls.txt --workers 3
python -m research batch --from-page https://example.org/list --link-pattern "/schemes/"
#    writes a markdown report (ready for review / needs fix / failed); re-running reuses pending reviews

# 3b. myscheme.gov.in is a JavaScript app: the plain fetcher sees no text. Render it once with a headless browser
#     (pip install playwright; python -m playwright install chromium), at most 1 action per 2 s:
python scripts/collect_myscheme.py list                                   # -> data/sources/myscheme_urls.txt (central / state:<State> per line)
python scripts/collect_myscheme.py snapshot --from-file data/sources/myscheme_urls.txt --group central --limit 20
python -m research batch data/sources/myscheme_urls.txt --snapshots data/sources/myscheme --limit 20 --workers 2

# 4. put approved candidates into the database (all-or-nothing, re-validates, atomic write, timestamped backup,
#    refreshes web/src/data/schemes.json)
python -m research merge --dry-run
python -m research merge                 # add --allow-update to replace existing ids, --run-tests for pytest,
                                         # --allow-unverified for a candidate whose source snapshot is missing
python -m pytest -q                      # then run the suite yourself
```

Thread ids are derived from the source, so running the same source twice finds the same pending review.
Starting a source again always begins from a clean slate (the `fetch` node resets every per-run field), so a transient
fetch or LLM failure never poisons the thread. State lives in `research/.state/checkpoints.sqlite` (override with `--state-db` / `RESEARCH_STATE_DB`);
candidates in `data/candidates/` (`--candidates-dir`).

Environment: `RESEARCH_VERIFIER_MODEL` (auditor model, default: the extractor's), `RESEARCH_ALLOWED_DOMAINS`
(e.g. `gov.in,nic.in`; default: any public host, with a warning for non-government domains), `RESEARCH_ALLOWED_DIRS`,
`RESEARCH_STATE_DB`, `RESEARCH_CANDIDATES_DIR`.

## Two agents: extractor and auditor

The graph is a real two-agent design, not one model checking itself.

- The **extractor** (`extract`) turns the page into a candidate with a verbatim quote for every claim.
- Deterministic checks (`verify_evidence`, `validate`) prove each quote exists, each number in a rule is in its quote,
  and the rules obey the engine.
- The **auditor** (`verify_semantics`) is a separate LLM call with an adversarial role ("find every way these rules
  misread the source"). It sees only the cleaned source text and the candidate as it would ship, not the extractor's
  reasoning, retry history or evidence quotes, so it cannot be anchored by them. It returns structured findings
  (`issues` with severity, plus `missing_criteria`), each with a supporting quote.

Why: a quote existing does not mean the rule reads it correctly. "aged 40 to 79" became only `age gte 40` in the
hand-written data and passed every evidence check. A second reader with a different job catches errors the author is
blind to; using a different model (`RESEARCH_VERIFIER_MODEL`) decorrelates the failures further.

The auditor can hallucinate too, so its output is not trusted either: every supporting quote goes through the same
deterministic matcher, and findings whose quote is not in the source (or whose numbers differ) are dropped and counted.
Surviving *blocking* findings go back to `extract` as `auditor:` feedback (each round counts toward the 3-attempt cap);
*warnings* appear under "Auditor notes" in the review. The auditor runs only after the deterministic checks pass, is
not re-run on a human edit (the review says so), and if it cannot run (API error, malformed JSON after one re-ask) the
review shows "AUDITOR DID NOT RUN" rather than a silent pass. The human still approves everything.

## What a candidate file contains

`data/candidates/<id>.json`: `scheme` (exact `schemes.json` format), `evidence` (the candidate with a
verbatim quote per claim, plus the match report), `unmapped_criteria`, `warnings`, and `provenance`
(source, source_url, final_url, whether source_url was explicit, fetched_at, sha256 of the cleaned text, model,
number of LLM attempts, auditor result and notes, URL/phone/e-mail flags, whether a human edited it, reviewer
decision/name/note/time/approved URLs). The cleaned source text is saved next to it in
`data/candidates/sources/<id>.txt` so merge can re-check the evidence later.

## Safety properties

- The LLM cannot add facts without a quote that exists in the source text; invented quotes fail `verify_evidence`.
  Numbers are compared as values, never fuzzily: "Rs 1,00,000" vs "Rs 2,00,000" (fuzzy score 97.9) is a mismatch, `60`
  does not match `160`, `1,00,000 = 100000 = 1 lakh`. A rule value that is not in its own quote is a blocking error.
- Free text (benefits, how_to_apply, caveats, ...) is scanned: every URL/phone/e-mail is listed for the reviewer, and
  URLs outside gov.in / nic.in / the source's own host are blocking unless approved explicitly (`--allow-url`).
- Fetching is SSRF-hardened and local files need `--file` (see GRAPH.md, "Network and file safety").
- Rules can only use `Profile` fields (derived from `sahayak/models.py`, so no drift). Anything else becomes an
  unmapped criterion, written into `caveats` so the citizen-facing agent still mentions it.
- The source is treated as untrusted data (delimited in the prompt; injected instructions cannot satisfy the evidence check).
- `source_url` is set by the pipeline, never by the model. Approval is refused while blocking errors exist.
- Eligibility remains decided by `sahayak.rules`, not the LLM; validation runs boundary profiles through that engine.

## Tests

`python -m pytest -q -p no:cacheprovider tests/test_research*.py`: all offline, using synthetic
fixtures in `tests/fixtures/research/` (clearly labelled, fictional) and a scripted fake LLM.

## Limitations

- Never run against live sites or a real LLM in development (network was blocked); prompt quality is tuned only on a small pilot. The `__NEXT_DATA__` fallback does not help on myscheme.gov.in (its HTML carries no scheme text); use `scripts/collect_myscheme.py` snapshots. Expect to tune
  `research/prompts.py` per model. JS-rendered pages that expose no text need a saved PDF/text file instead.
- Scanned PDFs are not OCR'd (clear error). Pages are cut at 60,000 characters (flagged as a warning).
- Evidence proves a quote exists and the auditor cross-checks the reading, but both are LLM-adjacent: the human review
  is still the real check on semantics, and the boundary tests check consistency, not truth. The auditor's quote check
  proves its quote is real, not that its objection is right. Number words are understood in English only (Hindi/Tamil
  number words such as "साठ" are not parsed; their digit forms and lakh/crore words are).
- Fetching ignores proxy environment variables on purpose (a proxy would resolve DNS and bypass IP validation), so a
  deployment that can only reach the internet through a proxy needs an egress-filtered network instead.
- State schemes are gated by a rule on `state` (`eq` or `in`, canonical names from `sahayak/states.py`); the extractor must
  declare `level` (`central` | `state`) with a quote, and validation fails a `state` scheme without a state rule (and a
  `central` one with it). A user whose state is unknown gets `need_info`. State-specific amounts, district limits,
  caste/occupation/land-size criteria stay as caveats.
- Only rules over existing `Profile` fields are supported. Adding a field means changing `Profile` first.
- Model JSON output is requested by prompt only (no provider-specific JSON mode) for portability.
- `merge` rewrites `schemes.json` with 2-space indentation (content preserved, formatting of the hand-written file is not), keeps a timestamped backup per merge (old backups are never pruned) and mirrors the file to `web/src/data/schemes.json`.
- No rate limiting beyond `--workers`; be polite to government servers.
