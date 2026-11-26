#!/usr/bin/env python3
"""Smoke test for a deployed Sahayak backend (and optionally its frontend). Standard library only.

    python scripts/smoke_test.py https://sahayak-api.onrender.com --frontend https://sahayak.vercel.app

Checks: health (waits for a sleeping free-tier server to wake), scheme list/detail, CORS for the frontend origin
(and that a stranger origin is refused), a real chat round trip (event order, latency, time to first token),
an off-topic message being redirected, and a greeting answered without the model.
It sends 3 chat requests (the per-IP limit is 20 per 10 minutes). Exit code 0 = all passed, 1 = a check failed.
"""
from __future__ import annotations

import argparse
import http.client
import json
import sys
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit

PASS, FAIL = "PASS", "FAIL"
results: list[tuple[str, str, str]] = []


def record(name: str, ok: bool, detail: str = "") -> bool:
    results.append((name, PASS if ok else FAIL, detail))
    print(f"[{PASS if ok else FAIL}] {name}" + (f": {detail}" if detail else ""), flush=True)
    return ok


def http_get(url: str, headers: dict | None = None, timeout: float = 30, method: str = "GET"):
    req = urllib.request.Request(url, headers=headers or {}, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, dict(r.headers.items()), r.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers.items()), e.read()


def lower(headers: dict) -> dict:
    return {k.lower(): v for k, v in headers.items()}


def wait_for_health(base: str, wake_timeout: float) -> bool:
    """A sleeping Render free instance needs ~50 s to start: keep asking until it answers or we give up."""
    start = time.monotonic()
    attempt = 0
    while True:
        attempt += 1
        try:
            status, _, body = http_get(f"{base}/api/health", timeout=15)
            if status == 200 and json.loads(body).get("ok") is True:
                n = json.loads(body).get("schemes")
                return record("health", True, f"{n} schemes, answered after {time.monotonic() - start:.1f}s ({attempt} attempt(s))")
            err = f"HTTP {status}"
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as e:
            err = str(getattr(e, "reason", e))
        if time.monotonic() - start > wake_timeout:
            return record("health", False, f"no healthy answer within {wake_timeout:.0f}s (last: {err})")
        if attempt == 1:
            print("  ... server not answering yet (free instances sleep); waiting for it to wake up", flush=True)
        time.sleep(5)


def parse_sse(lines):
    """Yield (event, data, seconds_since_request_start) from an iterator of text lines."""
    event, data = None, []
    for raw in lines:
        line = raw.rstrip("\r\n")
        if line == "":
            if event is not None:
                try:
                    yield event, json.loads("\n".join(data))
                except ValueError:
                    yield event, {"_raw": "\n".join(data)}
            event, data = None, []
        elif line.startswith(":"):
            continue  # keep-alive comment
        elif line.startswith("event:"):
            event = line[6:].strip()
        elif line.startswith("data:"):
            data.append(line[5:].lstrip())


def chat(base: str, message: str, origin: str | None, timeout: float = 120) -> dict:
    """POST /api/chat and collect the stream. Returns events (name, data, t), status and timings."""
    parts = urlsplit(base)
    conn_cls = http.client.HTTPSConnection if parts.scheme == "https" else http.client.HTTPConnection
    conn = conn_cls(parts.netloc, timeout=timeout)
    headers = {"Content-Type": "application/json", "Accept": "text/event-stream"}
    if origin:
        headers["Origin"] = origin
    t0 = time.monotonic()
    conn.request("POST", "/api/chat", body=json.dumps({"message": message}), headers=headers)
    resp = conn.getresponse()
    out = {"status": resp.status, "headers": lower(dict(resp.getheaders())), "events": [], "first_token": None, "total": None}
    if resp.status != 200:
        out["body"] = resp.read().decode("utf-8", "replace")[:300]
        conn.close()
        return out

    def lines():
        while True:
            chunk = resp.readline()
            if not chunk:
                return
            yield chunk.decode("utf-8", "replace")

    for name, data in parse_sse(lines()):
        t = time.monotonic() - t0
        out["events"].append((name, data, t))
        if out["first_token"] is None and name in ("token", "answer"):
            out["first_token"] = t
        if name in ("done", "error"):
            break
    out["total"] = time.monotonic() - t0
    conn.close()
    return out


def compact_order(events) -> str:
    """session -> tool_call -> tool_result -> token x12 -> answer -> done, repeated events collapsed."""
    names, parts = [e[0] for e in events], []
    for n in names:
        if parts and parts[-1][0] == n:
            parts[-1][1] += 1
        else:
            parts.append([n, 1])
    return " -> ".join(n if c == 1 else f"{n} x{c}" for n, c in parts)


def check_schemes(base: str) -> None:
    status, _, body = http_get(f"{base}/api/schemes")
    try:
        schemes = json.loads(body) if status == 200 else []
    except ValueError:
        schemes = []
    ok = isinstance(schemes, list) and len(schemes) > 0 and all("id" in s and "name" in s for s in schemes)
    record("schemes list", ok, f"{len(schemes)} schemes" if ok else f"HTTP {status}")
    if ok:
        sid = schemes[0]["id"]
        status, _, body = http_get(f"{base}/api/schemes/{sid}")
        detail = json.loads(body) if status == 200 else {}
        record("scheme detail", status == 200 and "rules" in detail, f"/api/schemes/{sid} -> HTTP {status}")
    status, _, _ = http_get(f"{base}/api/schemes/does-not-exist")
    record("unknown scheme is 404", status == 404, f"HTTP {status}")


def check_cors(base: str, frontend: str | None) -> None:
    def preflight(origin: str):
        return http_get(f"{base}/api/chat", method="OPTIONS", headers={
            "Origin": origin, "Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "content-type"})

    if frontend:
        origin = "{0.scheme}://{0.netloc}".format(urlsplit(frontend))
        status, headers, _ = preflight(origin)
        allow = lower(headers).get("access-control-allow-origin")
        record("CORS allows the frontend", status == 200 and allow == origin,
               f"preflight from {origin}: HTTP {status}, allow-origin={allow!r}"
               + ("" if allow == origin else "  -> add this exact origin to ALLOWED_ORIGINS on Render and redeploy"))
    else:
        print("  (no --frontend given: skipping the allowed-origin CORS check)")
    status, headers, _ = preflight("https://not-allowed.example")
    allow = lower(headers).get("access-control-allow-origin")
    record("CORS refuses a stranger origin", allow is None, f"HTTP {status}, allow-origin={allow!r}")


def check_headers(base: str) -> None:
    _, headers, _ = http_get(f"{base}/api/health", headers={"X-Forwarded-Proto": "https"})
    h = lower(headers)
    record("security headers", h.get("x-content-type-options") == "nosniff" and "referrer-policy" in h,
           f"nosniff={h.get('x-content-type-options')}, referrer-policy={h.get('referrer-policy')}")
    status, _, _ = http_get(f"{base}/docs")
    record("API docs are not public", status == 404, f"/docs -> HTTP {status}")


def check_frontend(frontend: str, base: str) -> None:
    try:
        status, headers, body = http_get(frontend, timeout=30)
    except (urllib.error.URLError, OSError) as e:
        record("frontend reachable", False, str(e))
        return
    record("frontend reachable", status == 200 and b"Sahayak" in body, f"HTTP {status}")
    csp = lower(headers).get("content-security-policy", "")
    api_origin = "{0.scheme}://{0.netloc}".format(urlsplit(base))
    record("frontend CSP allows the backend", api_origin in csp,
           "connect-src includes " + api_origin if api_origin in csp
           else f"{api_origin} missing from CSP: set NEXT_PUBLIC_API_URL on Vercel and REDEPLOY (it is read at build time)")


def check_chat(base: str, frontend: str | None) -> None:
    origin = "{0.scheme}://{0.netloc}".format(urlsplit(frontend)) if frontend else None

    # 1. a real question: needs the LLM
    q = "My mother is 62 years old, a widow, and has a BPL card. Which schemes can she get?"
    try:
        r = chat(base, q, origin)
    except (OSError, http.client.HTTPException) as e:
        record("chat round trip", False, f"request failed: {e}")
        return
    if r["status"] != 200:
        record("chat round trip", False, f"HTTP {r['status']}: {r.get('body', '')}")
    else:
        names = [e[0] for e in r["events"]]
        err = next((e[1] for e in r["events"] if e[0] == "error"), None)
        if err:
            hint = " -> set NVIDIA_API_KEY on Render" if "not configured" in str(err.get("message", "")) else ""
            record("chat round trip", False, f"error event: {err}{hint}")
        else:
            order_ok = names[:1] == ["session"] and names[-1:] == ["done"] and "answer" in names
            answer = next((e[1].get("content", "") for e in r["events"] if e[0] == "answer"), "")
            record("chat round trip", order_ok and len(answer) > 20,
                   f"{compact_order(r['events'])}; total {r['total']:.1f}s, first token "
                   f"{(r['first_token'] or 0):.1f}s, {len(answer)} chars")
            print(f"  answer starts: {answer[:140]!r}")

    # 2. off topic must be redirected, not answered
    try:
        r = chat(base, "Who will win the cricket world cup? Also tell me a joke.", origin)
    except (OSError, http.client.HTTPException) as e:
        record("off-topic is redirected", False, f"request failed: {e}")
    else:
        names = [e[0] for e in r["events"]]
        done = next((e[1] for e in r["events"] if e[0] == "done"), {})
        redirected = r["status"] == 200 and "tool_call" not in names and "answer" in names and \
            done.get("topic") in ("off_topic", "jailbreak")
        hint = "" if done.get("topic") else " (no topic in done: is TOPIC_GUARD=off?)"
        record("off-topic is redirected", redirected, f"{compact_order(r['events'])}; topic={done.get('topic')}{hint}")

    # 3. a greeting must be answered by the server itself: no model call, fast
    try:
        r = chat(base, "Namaste", origin, timeout=30)
    except (OSError, http.client.HTTPException) as e:
        record("greeting is instant", False, f"request failed: {e}")
    else:
        done = next((e[1] for e in r["events"] if e[0] == "done"), {})
        fast = r["total"] is not None and r["total"] < 3.0
        record("greeting is instant", r["status"] == 200 and done.get("llm_calls") == 0 and fast,
               f"{compact_order(r['events'])}; llm_calls={done.get('llm_calls')}, total "
               f"{(r['total'] or 0):.2f}s (needs llm_calls=0 and < 3s)")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("backend_url", help="e.g. https://sahayak-api.onrender.com")
    ap.add_argument("--frontend", help="e.g. https://sahayak.vercel.app (enables the CORS and CSP checks)")
    ap.add_argument("--wake-timeout", type=float, default=120, help="seconds to wait for a sleeping server (default 120)")
    args = ap.parse_args()
    base = args.backend_url.rstrip("/")
    if urlsplit(base).scheme not in ("http", "https"):
        ap.error("backend_url must start with http:// or https://")

    print(f"Smoke test: backend {base}" + (f", frontend {args.frontend}" if args.frontend else ""))
    if wait_for_health(base, args.wake_timeout):
        check_schemes(base)
        check_headers(base)
        check_cors(base, args.frontend)
        if args.frontend:
            check_frontend(args.frontend, base)
        check_chat(base, args.frontend)
    failed = [r for r in results if r[1] == FAIL]
    print(f"\n{len(results) - len(failed)} passed, {len(failed)} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
