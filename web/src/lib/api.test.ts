import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, _resetWakeServerForTests, chatStream, codeForStatus, errorFromResponse, wakeServer } from "./api";
import type { ChatEvent } from "./types";

const json = (status: number, body: unknown, headers: Record<string, string> = {}) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json", ...headers } });

afterEach(() => vi.unstubAllGlobals());

describe("errorFromResponse", () => {
  it.each([
    [400, "bad_request"],
    [422, "bad_request"],
    [409, "busy"],
    [413, "too_large"],
    [429, "rate_limited"],
    [503, "overloaded"],
    [500, "internal"],
    [502, "internal"],
  ] as const)("HTTP %i -> %s", async (status, code) => {
    expect(codeForStatus(status)).toBe(code);
    const e = await errorFromResponse(json(status, { detail: "nope" }));
    expect(e).toBeInstanceOf(ApiError);
    expect(e).toMatchObject({ code, status, message: "nope" });
  });

  it("reads numeric Retry-After on 503 and 429, ignores junk", async () => {
    expect((await errorFromResponse(json(503, { detail: "busy" }, { "Retry-After": "30" }))).retryAfter).toBe(30);
    expect((await errorFromResponse(json(429, { detail: "x" }, { "Retry-After": "540" }))).retryAfter).toBe(540);
    expect((await errorFromResponse(json(503, {}, { "Retry-After": "Wed, 21 Oct 2026 07:28:00 GMT" }))).retryAfter).toBeUndefined();
    expect((await errorFromResponse(json(503, {}))).retryAfter).toBeUndefined();
  });

  it("survives a non-JSON body and array details", async () => {
    expect((await errorFromResponse(new Response("<html>bad gateway</html>", { status: 502 }))).message).toBe("HTTP 502");
    expect((await errorFromResponse(json(422, { detail: [{ loc: ["body"], msg: "x" }] }))).message).toContain("loc");
  });
});

describe("chatStream", () => {
  async function collect(it: AsyncGenerator<ChatEvent>) {
    const out: ChatEvent[] = [];
    for await (const e of it) out.push(e);
    return out;
  }

  it("posts session_id only when known and yields parsed events", async () => {
    const fetchMock = vi.fn(async () =>
      new Response('event: session\ndata: {"session_id":"s9"}\n\nevent: answer\ndata: {"content":"hi"}\n\n', {
        status: 200,
        headers: { "Content-Type": "text/event-stream" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);
    const events = await collect(chatStream("hello", "s1"));
    expect(events.map((e) => e.type)).toEqual(["session", "answer"]);
    const [, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(JSON.parse(init.body as string)).toEqual({ session_id: "s1", message: "hello" });
    await collect(chatStream("hello", null));
    expect(JSON.parse((fetchMock.mock.calls[1] as unknown as [string, RequestInit])[1].body as string)).toEqual({ message: "hello" });
  });

  it("throws a typed ApiError for 413 and 503 before streaming", async () => {
    vi.stubGlobal("fetch", async () => json(413, { detail: "too big" }));
    await expect(collect(chatStream("x", null))).rejects.toMatchObject({ code: "too_large", status: 413 });
    vi.stubGlobal("fetch", async () => json(503, { detail: "busy" }, { "Retry-After": "12" }));
    await expect(collect(chatStream("x", null))).rejects.toMatchObject({ code: "overloaded", retryAfter: 12 });
  });

  it("maps a fetch failure to a network error and rethrows aborts untouched", async () => {
    vi.stubGlobal("fetch", async () => {
      throw new TypeError("Failed to fetch");
    });
    await expect(collect(chatStream("x", null))).rejects.toMatchObject({ code: "network" });
    vi.stubGlobal("fetch", async () => {
      throw new DOMException("aborted", "AbortError");
    });
    await expect(collect(chatStream("x", null))).rejects.toMatchObject({ name: "AbortError" });
  });
});

describe("wakeServer", () => {
  it("pings GET /api/health once per page load and never throws", async () => {
    _resetWakeServerForTests();
    const fetchMock = vi.fn().mockRejectedValue(new TypeError("offline"));
    vi.stubGlobal("fetch", fetchMock);
    await expect(wakeServer()).resolves.toBeUndefined();
    await wakeServer();
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit | undefined];
    expect(url).toBe("http://localhost:8000/api/health");
    expect(init?.method ?? "GET").toBe("GET");
  });
});
