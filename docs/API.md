# Sahayak HTTP API contract (v1)

Backend: FastAPI in `server/`. Frontend: Next.js in `web/`. Both must follow this file exactly.
Base URL comes from `NEXT_PUBLIC_API_URL` (frontend) and defaults to `http://localhost:8000`.

## POST /api/chat  → Server-Sent Events

Request JSON:
```json
{ "session_id": "optional string; omit to start a new conversation", "message": "user text (1–2000 chars)" }
```

Response: `Content-Type: text/event-stream`. Each event is `event: <name>\ndata: <json>\n\n`. Order:

| event | data | notes |
|---|---|---|
| `session` | `{"session_id": "abc123"}` | always first |
| `tool_call` | `{"id": "call_1", "name": "check_eligibility", "arguments": {...}}` | 0..n times |
| `tool_result` | `{"id": "call_1", "name": "...", "result": {...}}` | follows its tool_call. For `check_eligibility`, `result` is exactly the tool's output: `{"eligible": [{"scheme_id","scheme_name","verdict","failed_reasons","missing_fields","caveats","benefits","source_url","documents","how_to_apply"}], "need_info": [{"scheme_id","scheme_name","missing_fields"}], "not_eligible": [{"scheme_id","scheme_name","reasons","caveats"}]}`. `documents` (list of strings) and `how_to_apply` (string) are only on `eligible` items; they are the same values as `get_scheme_details`, so the model never needs that tool for a scheme `check_eligibility` returned, and cards can use them directly. A `not_eligible` item's `caveats` may say the person can still qualify another way (e.g. under 70: "may still qualify for regular PM-JAY"), so show them. `missing_fields` names are profile fields; the income-tax ones are `ever_income_tax_payer` (Atal Pension Yojana) and `income_tax_payer_last_year` (PM-KISAN). Invalid tool input (unknown profile key, out-of-range value, unknown `scheme_ids`) gives `{"error": "...", "details"?: [{"field","problem"}], "valid_ids"?/"valid_fields"?}` with no internal/Python details. For `search_schemes`: list of `{"scheme_id","name","summary","score"}`. For `get_scheme_details`: the scheme dict. On tool error: `{"error": "..."}` |
| `token` | `{"delta": "text"}` | optional, 0..n times, only after the last `tool_result`: incremental text of the final answer (the server streams from the provider unless `LLM_STREAM=0` or the provider does not stream). `<think>` reasoning is never sent. Tokens stop early if the text so far would offer an unverified scheme. After a guard or empty-answer correction the rest of the turn is not streamed. Tokens are append-only; the `answer` below replaces them |
| `answer` | `{"content": "full final answer (markdown)"}` | always sent once, even if tokens were streamed. It is the guarded text: render it in place of any tokens |
| `suggestions` | `{"options": ["Yes, we have a BPL card", "No BPL card", "Not sure"]}` | optional quick replies, in the user's language, derived deterministically from the latest `need_info.missing_fields` (max 4) |
| `done` | `{"latency_s": 3.2, "llm_calls": 2, "tokens": 1450, "topic": "on_topic"}` | always last on success. `llm_calls` counts main-model round trips (provider retries and the topic classifier call are not counted); `tokens` is the provider's usage, or a rough estimate (chars/4) for streamed calls whose provider sent no usage. `topic` (optional; absent when `TOPIC_GUARD=off`; clients should ignore unknown fields) is `"on_topic"`, `"off_topic"`, `"greeting"` or `"jailbreak"`, see "Staying on topic" below |
| `error` | `{"message": "human-readable, in the user's language where we have it", "code": "llm_error" \| "session_limit"}` | replaces `done` on failure. `llm_error`: provider failure, timeout, or a cancelled run (the turn is rolled back; retrying is safe). `session_limit`: the conversation reached its message cap (default 20 user messages); sent right after `session`, the UI should offer "Start new conversation". |

The final `answer` is checked by the server before it is sent: a scheme described as available that `check_eligibility` did not confirm is replaced by a safe fallback listing only confirmed schemes, links that are not tool-provided `source_url`s or on gov.in / nic.in are replaced by `[link removed]`, and an empty or reasoning-only answer becomes a localized error text. The `answer` event may therefore differ from any streamed `token`s: always render `answer`. Aadhaar, PAN and phone numbers in user messages are replaced by `[number removed]` before reaching the model.

### Staying on topic
Sahayak only answers about government welfare schemes (scope: `sahayak/topics.py`). Env `TOPIC_GUARD`: `off`, `prompt` (deterministic rules + scope in the system prompt) or `classifier` (default: also a small LLM classifier, `TOPIC_GUARD_MODEL`, `TOPIC_GUARD_TIMEOUT_S` default 4, run in parallel with the main model and failing open).

- `greeting` (hello / thanks): canned localized reply, `llm_calls: 0`. Flow: `session` -> `answer` -> `done`.
- `off_topic` / `jailbreak` (e.g. a joke, stock advice, "ignore your instructions"): `answer` is a short localized redirect that says what Sahayak can do with 3 example questions. No `tool_call`, `tool_result` or `token` events are sent for such a turn, and it is not kept in the conversation history (it does not count towards `MAX_TURNS_PER_SESSION`).
- While the classifier is still deciding (only when the rules are unsure), the turn's `tool_call` / `tool_result` / `token` events are held back and released together, in order, once the verdict is `on_topic`; for an off-topic verdict the redirect `answer` is sent as soon as the verdict arrives and `done` follows when the abandoned model call unwinds. A classifier timeout, error or unreadable reply counts as `on_topic`.

### HTTP errors before streaming starts
All are JSON `{"detail": "..."}`:

| status | when | notes |
|---|---|---|
| 400 | validation: empty/over-long `message` (max 2000 chars), bad types, `session_id` > 128 chars | |
| 409 | the same session is still answering and could not be cancelled within ~2 s | a new message normally CANCELS the session's previous run (e.g. after a closed tab) and proceeds; 409 only if the old LLM call cannot unwind. Retry shortly. |
| 413 | request body over 16 KB (checked on `Content-Length` and on streamed bytes) | |
| 429 | per-IP limit exceeded | `Retry-After` seconds |
| 503 | global budget (`GLOBAL_CHAT_PER_MIN`, default 30/min), concurrency cap (`MAX_CONCURRENT_RUNS`, default 8) or session store full | `Retry-After` seconds |

### Session restart behaviour
An unknown or expired `session_id` (server restart, 30 min idle expiry, eviction, after `/api/session/reset`) silently starts a NEW conversation with no history. Compare the `session` event's `session_id` with the one you sent: if it differs, show a "conversation restarted" notice. A reset session id behaves the same way.

## GET /api/schemes
`200 [{"id","name","category","summary","benefits","documents","how_to_apply","source_url","tags","aliases","caveats"}]`  (no `rules`)

## GET /api/schemes/{id}
`200` one scheme as above plus `"rules": [{"field","op","value","reason"}]` (shown as "who can get it"); `404 {"detail": "Unknown scheme"}`

## POST /api/session/reset
Request `{"session_id": "abc123"}` → `200 {"ok": true}`

## GET /api/health
`200 {"ok": true, "schemes": 10}` (nothing about the model, provider or keys is public)

`/docs`, `/redoc` and `/openapi.json` return 404 unless env `ENABLE_DOCS=1`.

## Notes
- Sessions live in server memory (dict of session_id → Agent), expire after 30 min idle, max 1000 sessions.
- CORS origins from env `ALLOWED_ORIGINS` (comma-separated; default `http://localhost:3000`).
- Per-IP rate limit (default 20 chat requests / 10 min, env `RATE_LIMIT_PER_10MIN`) plus a global budget (`GLOBAL_CHAT_PER_MIN`, default 30). With `TRUST_PROXY=1` the client IP is the Nth entry from the RIGHT of `X-Forwarded-For` (`TRUSTED_PROXY_HOPS`, default 1); left-most entries are client-controlled and ignored.
- Cost caps: `MAX_TURNS_PER_SESSION` (20), `HISTORY_TURNS` (last 12 turns sent to the model), `MAX_TOKENS` (700 per call), `MAX_STEPS` (6 LLM calls per message), `LLM_TIMEOUT_S` (30), `MAX_CONCURRENT_RUNS` (8).
- Sticky language: chip language only upgrades within a session (en -> hinglish -> hi/ta); a later English "yes" does not flip it.
- Responses carry `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`, and HSTS when served over https. With `ENV=production` the server refuses to start unless `ALLOWED_ORIGINS` is set. Agent traces (user text) are written only with `SAHAYAK_TRACES=1`.
- Answers are short by default: `ANSWER_STYLE=brief` (about 120 words: one line per eligible scheme, key caveats, at most 3 follow-up questions; documents and how-to-apply are left to the cards). `ANSWER_STYLE=full` restores the long form. Reasoning models that think inline spend `MAX_TOKENS` on the thinking: raise it if answers come back empty.
- Provider errors 429/500/502/503/504, timeouts and connection errors are retried twice inside the request (about 1 s and 3 s apart) before an `error` event is sent; 400/401/403/404 are not retried. A closed tab cancels the wait between retries.
- `LLM_STREAM=0` turns token streaming off; `LLM_EXTRA_BODY` (JSON) and `LLM_SYSTEM_PREFIX` are passed to the provider as `extra_body` / prepended to the system prompt (see README, Latency).
- `TOPIC_GUARD` (`classifier` default | `prompt` | `off`), `TOPIC_GUARD_MODEL` (default: the main model; a small fast model such as `nvidia/nemotron-3-nano-30b-a3b` on NVIDIA is intended, check the name against your provider) and `TOPIC_GUARD_TIMEOUT_S` (4) configure the topic guard (README, "Staying on topic").
- LLM settings from the same env vars as the CLI (`LLM_*` or `NVIDIA_API_KEY`), see `sahayak/agent.py:resolve_config`.
