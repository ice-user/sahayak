# Sahayak web

Next.js (App Router, TypeScript strict) + Tailwind CSS v4 + shadcn/ui-style components + lucide-react + react-markdown.
Mobile-first UI in English, हिन्दी, Hinglish and தமிழ். It talks to the FastAPI backend described in [`../docs/API.md`](../docs/API.md).

## Setup

```bash
cd web
npm install
npm run dev        # http://localhost:3000, mock mode when NEXT_PUBLIC_API_URL is unset
```

Scripts: `npm run dev | build | start | lint | test`.

## Environment variables

| Variable | Meaning |
|---|---|
| `NEXT_PUBLIC_API_URL` | Backend base URL, no trailing slash (e.g. `https://api.example.com`). Falls back to `http://localhost:8000` in production builds. |
| `NEXT_PUBLIC_MOCK` | `1` forces the built-in mock backend. `0` disables the dev auto-mock. |
| `NEXT_PUBLIC_SITE_URL` | Optional public origin used for OpenGraph URLs. |

Both `NEXT_PUBLIC_*` values are inlined at **build** time. See `.env.example`.

## Mock mode

Active when `NEXT_PUBLIC_MOCK=1`, or in `npm run dev` when `NEXT_PUBLIC_API_URL` is unset. No server needed:

- Schemes come from `src/data/schemes.json` (a copy of `../data/schemes.json`; re-copy when the data changes).
- `/api/chat` is faked in the browser (`src/lib/mock/`). It produces a real SSE **byte stream**, deliberately split mid-event and mid-UTF-8 character, so the same parser and reducer run as against the real server. It emits `session`, `tool_call`, `tool_result` (search + eligibility with eligible / need_info / not_eligible), `token`, `answer`, `suggestions`, `done`.
- Eligibility is computed by a TypeScript port of the Python rule engine, and a tiny keyword extractor reads age, widow, BPL etc. in en/hi/hinglish/ta, so follow-up chips ("Yes, we have a BPL card") change the next result.
- Failure cases (each fails once, the retry succeeds): include `mock:error` (stream `error` event, `llm_error`), `mock:ratelimit` (HTTP 429 + `Retry-After`), `mock:busy` (HTTP 409), `mock:toolarge` (HTTP 413) or `mock:overloaded` (HTTP 503 + `Retry-After`) in a message. Two more simulate session problems: `mock:expire` makes the mock forget the conversation (the next reply shows the "conversation was restarted" notice) and `mock:sessionlimit` sends the per-session message cap `error` event (offers "Start new conversation").

- `/plan?s=id1,id2` (the "Make my plan" button in chat) uses `mockPlan` in `src/lib/mock/mock-plan.ts`: checklist, steps, watch-outs, where-to-go trips, built from the bundled scheme data. Ticked documents are kept in `localStorage` per plan.

## Real backend

```bash
NEXT_PUBLIC_API_URL=http://localhost:8000 npm run dev
```

The backend's `ALLOWED_ORIGINS` must include the web origin (CORS). Handled behaviours beyond the written contract: HTTP 409 (session still streaming) shows "Still working on your last question…", HTTP 429 and 503 show friendly messages using `Retry-After`, HTTP 413 asks to shorten the message, an `error` event with `session_limit` offers "Start new conversation", HTTP 400 and 422 are treated as bad requests, a stream with only `session` + `error` renders as an error, the stored `session_id` is always overwritten by the one in the `session` event, and the UI is fully usable when no `token` events arrive (status line + typing dots).

## Structure

```
src/app/                 routes: / , /schemes , /schemes/[id] , /about
src/components/          header, footer, language chips, chat/*, schemes/*, ui/* (button, badge, collapsible)
src/hooks/               use-chat (stream + sessionStorage), use-schemes (cached list)
src/lib/sse.ts           SSE parser (+ typed event mapping, fetch stream reader)
src/lib/chat-state.ts    reducer: SSE events -> UI state
src/lib/rules-text.ts    machine rules -> plain language per language
src/lib/i18n/            typed dictionaries (en, hi, hinglish, ta)
src/lib/mock/            mock backend
```

## Tests

`npm test` runs Vitest (hook tests use jsdom + a mocked `fetch`/`ReadableStream`): SSE parser (chunking, CRLF, UTF-8 splits, malformed events), chat reducer (all events, no-token streams, 409/429/llm_error, retry), rule-to-plain-language rendering in all four languages, and the mock backend end to end.

## Deploy to Vercel

Import the repo, set **Root Directory = `web`**, framework Next.js, and add `NEXT_PUBLIC_API_URL` (your deployed backend) or `NEXT_PUBLIC_MOCK=1` for a demo. Set `NEXT_PUBLIC_API_URL` **before the first build**: it is inlined at build time and also feeds the CSP `connect-src`, so changing it needs a redeploy (the build log warns when it is missing). No `vercel.json` is needed. Add the Vercel domain to the backend's `ALLOWED_ORIGINS`. Full checklist: [`../DEPLOY.md`](../DEPLOY.md).

**Cold starts (free-tier backend):** on page load the app sends one `GET /api/health` (`src/components/wake-up.tsx`, `wakeServer` in `src/lib/api.ts`) so a sleeping Render instance starts early; if a chat request gets no first event within 8 s (`WAKE_DELAY_MS` in `use-chat.ts`) the status line switches to the localized "Waking up the server..." text (`chat.status.waking`) until the first event arrives.

## Security

- `next.config.ts` sets a Content-Security-Policy and headers (`default-src 'self'`; `connect-src 'self'` plus the `NEXT_PUBLIC_API_URL` origin; `img-src 'self' data:`; `font-src 'self'`; `frame-ancestors 'none'`; `Referrer-Policy: strict-origin-when-cross-origin`; `X-Content-Type-Options: nosniff`). The API origin is read at build time, so rebuild when it changes.
- `script-src` keeps `'unsafe-inline'` because the App Router emits inline hydration scripts and nonces would force every page to render dynamically; `'unsafe-eval'` and `ws://localhost` are added only in `next dev`. Upgrade path: nonces via a Next proxy file.
- Chat markdown drops images and raw HTML, and only absolute http(s) links render as links (`rel="noopener noreferrer"`). `source_url` values are validated the same way before use as an href.

## Conversation storage

`sessionStorage` holds a versioned entry (`sahayak.chat`) with a save timestamp. Entries older than 25 minutes (the server expires sessions after 30), of another version or with a wrong shape are dropped. If the server answers with a different session id than the one sent, the UI shows a "conversation was restarted" notice and dims earlier messages.

## Privacy

No login. The browser keeps the session id and the transcript in `sessionStorage` only (cleared when the tab closes); the language choice is in `localStorage`. Fonts (Mukta, Mukta Malar) are self-hosted through `@fontsource`, so nothing is fetched from Google at build or run time.

## Screenshots

`screenshots/` holds captures from mock mode, made with `scripts/screenshots.mjs` (Playwright driving a system Chrome).
