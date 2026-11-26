# Deploying Sahayak (free tier): Render + Vercel

The backend (FastAPI, Docker) runs on **Render**; the web app (Next.js) runs on **Vercel**. Both have free plans.
Do the steps in this order: the web app needs the backend's URL, and the backend needs the web app's URL.

You need: a GitHub account, a Render account, a Vercel account, and an NVIDIA API key (free credits).

## 0. Before you start: get an NVIDIA API key

1. Go to <https://build.nvidia.com>, sign in, open any model page (e.g. `meta/llama-3.3-70b-instruct`) and click **Get API Key**.
2. Copy the key (starts with `nvapi-`). Treat it like a password: it goes only into Render's dashboard, never into a file or chat.

## 1. Push the code to GitHub

The folder is already a git repository with one commit. Create an empty repository on GitHub (New repository; private or public, your choice; do NOT tick "Add a README"), then:

```bash
cd scheme-sahayak
git remote add origin https://github.com/<you>/<repo>.git
git push -u origin main
```

Private repos work with both Render and Vercel (you authorize their GitHub apps during the steps below). Vercel's free "Hobby" plan is for non-commercial use.

## 2. Backend on Render

1. <https://dashboard.render.com> -> **New +** -> **Blueprint** -> connect GitHub and select your repo.
2. Render reads `render.yaml` and shows the service `sahayak-api` (plan: Free). It asks for the values marked secret:

   | Name | Value |
   |---|---|
   | `NVIDIA_API_KEY` | your `nvapi-...` key |
   | `ALLOWED_ORIGINS` | not known yet: type `https://placeholder.vercel.app` for now, you fix it in step 4 |
   | `LLM_MODEL`, `TOPIC_GUARD_MODEL` | leave empty (defaults: `meta/llama-3.3-70b-instruct`; the guard uses the same model) |

3. Click **Apply** / **Deploy**. The first build takes a few minutes (Docker image + Python packages).
4. When it says **Live**, open `https://<your-service>.onrender.com/api/health`. You should see `{"ok":true,"schemes":10}`. That URL (without `/api/health`) is your **backend URL**.
5. Check **Logs**: you should see a line `LLM provider configured: ... model=meta/llama-3.3-70b-instruct`. If you see `NO LLM PROVIDER CONFIGURED`, the key is missing (Environment tab -> add `NVIDIA_API_KEY` -> redeploy).

## 3. Frontend on Vercel

1. <https://vercel.com/new> -> import the same GitHub repo.
2. **Root Directory: `web`** (click Edit next to it). Framework preset: Next.js (auto-detected). Leave build/install commands as they are.
3. Open **Environment Variables** and add, **before the first deploy**:

   | Name | Value |
   |---|---|
   | `NEXT_PUBLIC_API_URL` | your Render backend URL, e.g. `https://sahayak-api.onrender.com` (no trailing slash, no `/api`) |

   > **Important:** `NEXT_PUBLIC_*` values are baked into the app (and into its Content-Security-Policy) **at build time**. If you add or change this variable after a deploy, you must **Redeploy** (Deployments -> ... -> Redeploy). Without it the site would try to call `http://localhost:8000` and chat would fail. The build log prints a `[sahayak] WARNING` if it is missing.
4. Click **Deploy**. When done, note your site URL, e.g. `https://sahayak-xyz.vercel.app`. Use the **production** domain (Settings -> Domains), not a per-deployment preview URL.

No `vercel.json` is needed. `NEXT_PUBLIC_MOCK=1` (instead of the API URL) deploys a demo that needs no backend at all.

## 4. Tell the backend about the frontend (CORS)

1. Render -> `sahayak-api` -> **Environment** -> edit `ALLOWED_ORIGINS` to your exact Vercel origin: `https://sahayak-xyz.vercel.app` (scheme included, no trailing slash, no path). Several origins: comma-separated, e.g. a custom domain as well.
2. Save. Render redeploys automatically (or click **Manual Deploy -> Deploy latest commit**).

## 5. Verify end to end

Automatic check (needs only Python 3, no packages):

```bash
python scripts/smoke_test.py https://<your-service>.onrender.com --frontend https://<your-app>.vercel.app
```

It waits for a sleeping server to wake, then checks health, the scheme list, CORS for your frontend (and that other origins are refused), the frontend's CSP, a real chat round trip (prints event order, total time and time to first token), that an off-topic message gets redirected, and that "Namaste" is answered instantly. Exit code 0 = everything passed. It sends 3 chat messages (the per-IP limit is 20 per 10 minutes).

By hand: open the Vercel URL, tap a sample question, and you should get an answer with scheme cards. Switch to Hindi/Tamil and try again. In the browser dev tools (F12 -> Console) there should be no red CORS errors.

## Costs and limits (free tiers)

- **Render free web service**: sleeps after about 15 minutes without traffic; the first request afterwards takes up to ~1 minute. The web app pings `/api/health` as soon as a page opens and shows "Waking up the server..." if a chat reply is slow. 512 MB RAM (Sahayak uses about 90 MB with the default `bm25` search; do **not** switch to `hybrid` on the free plan). About 750 free instance hours per month per workspace. Free instances have no persistent disk: conversations live in memory and vanish on restart or redeploy (the app handles that).
- **Keeping it awake (optional)**: an external uptime monitor (e.g. UptimeRobot free) hitting `/api/health` every 10 minutes avoids sleeping, but uses up your monthly free hours faster.
- **Vercel Hobby**: free, generous for a project like this; non-commercial use only.
- **NVIDIA**: free credits are limited and can run out. Each chat message uses 1-2 model calls (+1 small classifier call when the off-topic guard is unsure). Protect yourself with the limits in `render.yaml`: `RATE_LIMIT_PER_10MIN=20` per visitor and `GLOBAL_CHAT_PER_MIN=30` overall. Lower them if you share the link widely. Watch your usage on build.nvidia.com.
- Limits and prices change; check the providers' pricing pages.

## Updating and rolling back

- **Update**: `git push` to `main`. Render (`autoDeploy: true`) and Vercel both redeploy automatically. The backend and web app are deployed separately.
- **Roll back the backend**: Render -> service -> **Events**/**Deploys** -> pick an earlier successful deploy -> **Rollback** (if offered on your plan) or revert the commit in git and push. Env var changes: edit in the Environment tab, then redeploy.
- **Roll back the frontend**: Vercel -> Deployments -> an earlier deployment -> **...** -> **Promote to Production** (instant).
- **Emergency stop** (e.g. credits draining): Render -> service -> **Suspend**, or delete the `NVIDIA_API_KEY` variable (chat then answers "AI provider is not configured"; the scheme browser keeps working), or revoke the key on build.nvidia.com.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Browser console: `blocked by CORS policy` / chat says "Could not reach the server" | `ALLOWED_ORIGINS` does not contain the exact origin of the page | Set it to e.g. `https://sahayak-xyz.vercel.app` (https, no trailing slash, no path), save, wait for the redeploy. Preview URLs (`...-git-branch-...vercel.app`) are different origins: add them too or test on the production domain. `smoke_test.py --frontend ...` pinpoints this. |
| Console: `Refused to connect ... Content Security Policy` | The site was built without (or with a wrong) `NEXT_PUBLIC_API_URL` | Set it in Vercel -> Settings -> Environment Variables, then **Redeploy** (it is read at build time). |
| Chat answers "The service is very busy right now" (HTTP 503) | `GLOBAL_CHAT_PER_MIN` (30) or `MAX_CONCURRENT_RUNS` reached | Wait a minute (the message shows when to retry), or raise the values in the Render environment. |
| "You have sent many questions in a short time" (429) | `RATE_LIMIT_PER_10MIN` per visitor | Wait, or raise it. Behind Render's proxy `TRUST_PROXY=1` must stay set, or all visitors share one IP. |
| Off-topic or normal questions get a "guard" error / the topic check seems stuck | The classifier model call failed or is slow (it fails open after `TOPIC_GUARD_TIMEOUT_S`, default 4 s) | Check Render logs. Set `TOPIC_GUARD=prompt` (rules only, no extra model call) as a fallback. |
| First message takes ~1 minute | Free instance was asleep (cold start) | Expected. The UI shows "Waking up the server..." after 8 s. Use an uptime monitor to keep it awake if needed. |
| Render deploy fails with `ALLOWED_ORIGINS must be set when ENV=production` | The variable is empty | Environment tab -> set `ALLOWED_ORIGINS` (any valid origin; fix later). |
| Chat says "The AI provider is not configured on this server" | `NVIDIA_API_KEY` missing or empty | Add it on Render (check logs for `NO LLM PROVIDER CONFIGURED`), redeploy. |
| "The AI service is not configured correctly" (401/403 from provider) | Wrong or expired key | Create a new key on build.nvidia.com and update it. |
| "The AI service had a problem" / logs show 404 "model not found" | `LLM_MODEL` names a model your key cannot use or that was renamed | Clear `LLM_MODEL` (use the default) or pick a current model id from build.nvidia.com; run locally `python -m sahayak.check_llm` to test it. |
| Render health check fails, deploy never goes Live | App crashed at startup | Render -> Logs. The line before the traceback says why. |
| Vercel build: `Root Directory` errors / "No Next.js version detected" | Root directory not set | Project Settings -> General -> Root Directory = `web`. |
| `/docs` shows 404 | By design in production (`ENABLE_DOCS` is off) | See `docs/API.md`. |

## Environment variables reference (backend)

Set in `render.yaml` or the Render dashboard. Secrets are marked `sync: false` in the blueprint, so they are never stored in git.

| Name | Default in render.yaml | Meaning |
|---|---|---|
| `NVIDIA_API_KEY` | (secret) | NVIDIA key. Or use `LLM_BASE_URL` + `LLM_API_KEY` + `LLM_MODEL` for another OpenAI-compatible provider. |
| `ALLOWED_ORIGINS` | (secret) | Comma-separated frontend origins allowed by CORS. Required when `ENV=production`. |
| `LLM_MODEL`, `TOPIC_GUARD_MODEL` | empty | Optional model overrides. |
| `ENV` | `production` | Enforces `ALLOWED_ORIGINS`; API docs stay off. |
| `SAHAYAK_SEARCH` | `bm25` | Scheme search; `hybrid` needs ~1 GB RAM and a build with `INSTALL_HYBRID=1`. |
| `RATE_LIMIT_PER_10MIN` / `GLOBAL_CHAT_PER_MIN` / `MAX_CONCURRENT_RUNS` | `20` / `30` / `6` | Abuse and cost caps. |
| `ANSWER_STYLE` | `brief` | Short answers with document and how-to-apply cards; `full` is longer. |
| `LLM_STREAM` | `1` | Stream tokens to the browser. |
| `TOPIC_GUARD` | `classifier` | `off`, `prompt` or `classifier`. |
| `TRUST_PROXY`, `TRUSTED_PROXY_HOPS` | `1`, `1` | Read the visitor IP from Render's `X-Forwarded-For`. |

## Running the container locally (optional)

```bash
docker build -t sahayak-api .
docker run --rm -p 8000:8000 -e ENV=production -e ALLOWED_ORIGINS=http://localhost:3000 -e NVIDIA_API_KEY=nvapi-... sahayak-api
python scripts/smoke_test.py http://localhost:8000
```
