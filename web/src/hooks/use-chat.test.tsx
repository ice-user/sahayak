// @vitest-environment jsdom
import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { newAssistant, type AssistantMessage, type ChatMessage } from "@/lib/chat-state";
import { serializeStored, STORAGE_KEY, MAX_AGE_MS } from "@/lib/storage";
import { useChat, WAKE_DELAY_MS } from "./use-chat";
import { DICTS } from "@/lib/i18n";

const enc = new TextEncoder();
const sse = (event: string, data: unknown) => `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;
const DONE = sse("done", { latency_s: 1, llm_calls: 1, tokens: 5 });

/** A response whose body the test feeds by hand. */
function liveStream() {
  let controller!: ReadableStreamDefaultController<Uint8Array>;
  const body = new ReadableStream<Uint8Array>({ start: (c) => (controller = c) });
  return {
    response: new Response(body, { status: 200, headers: { "Content-Type": "text/event-stream" } }),
    push: (...events: string[]) => events.forEach((e) => controller.enqueue(enc.encode(e))),
    close: () => controller.close(),
    error: (e: unknown) => controller.error(e),
  };
}
const okResponse = (...events: string[]) =>
  new Response(events.join(""), { status: 200, headers: { "Content-Type": "text/event-stream" } });
const jsonResponse = (status: number, detail: string, headers: Record<string, string> = {}) =>
  new Response(JSON.stringify({ detail }), { status, headers: { "Content-Type": "application/json", ...headers } });

const asst = (s: { messages: ChatMessage[] }, i = s.messages.length - 1) => s.messages[i] as AssistantMessage;
const bodies = (fetchMock: ReturnType<typeof vi.fn>) =>
  fetchMock.mock.calls.map((c) => JSON.parse((c[1] as RequestInit).body as string) as { session_id?: string; message: string });

let fetchMock: ReturnType<typeof vi.fn>;
beforeEach(() => {
  sessionStorage.clear();
  fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => vi.unstubAllGlobals());

const history = (): ChatMessage[] => [
  { id: "u1", role: "user", text: "My mother is 62" },
  { ...newAssistant("a1"), streaming: false, activity: null, text: "Does she have a BPL card?" },
];

describe("useChat: sending", () => {
  it("streams a reply, stores the session and persists the settled conversation", async () => {
    fetchMock.mockResolvedValueOnce(okResponse(sse("session", { session_id: "s1" }), sse("answer", { content: "Hello" }), DONE));
    const { result } = renderHook(() => useChat());
    act(() => void result.current.send("  hi  "));
    await waitFor(() => expect(result.current.state.busy).toBe(false));
    expect(result.current.state.sessionId).toBe("s1");
    expect(asst(result.current.state)).toMatchObject({ text: "Hello", streaming: false, error: null });
    expect(bodies(fetchMock)[0]).toEqual({ message: "hi" });
    await waitFor(() => expect(JSON.parse(sessionStorage.getItem(STORAGE_KEY)!)).toMatchObject({ v: 1, sessionId: "s1" }));
  });

  it("ignores a second send while one is in flight", async () => {
    const live = liveStream();
    fetchMock.mockResolvedValueOnce(live.response);
    const { result } = renderHook(() => useChat());
    act(() => void result.current.send("one"));
    let second = true;
    act(() => {
      second = result.current.send("two");
    });
    expect(second).toBe(false);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    live.push(sse("session", { session_id: "s" }), DONE);
    live.close();
    await waitFor(() => expect(result.current.state.busy).toBe(false));
  });
});

describe("useChat: restore", () => {
  const store = (savedAt: number, sessionId: string | null = "old") =>
    sessionStorage.setItem(STORAGE_KEY, serializeStored({ sessionId, messages: history() }, savedAt));

  it("restores a fresh conversation and sends the stored session id", async () => {
    store(Date.now() - 60_000);
    fetchMock.mockResolvedValueOnce(okResponse(sse("session", { session_id: "old" }), sse("answer", { content: "ok" }), DONE));
    const { result } = renderHook(() => useChat());
    await waitFor(() => expect(result.current.state.messages).toHaveLength(2));
    act(() => void result.current.send("haan"));
    await waitFor(() => expect(result.current.state.busy).toBe(false));
    expect(bodies(fetchMock)[0]).toEqual({ session_id: "old", message: "haan" });
    expect(result.current.state.messages.some((m) => m.role === "notice")).toBe(false);
  });

  it("drops a stored conversation older than 25 minutes", async () => {
    store(Date.now() - MAX_AGE_MS - 5_000);
    const { result } = renderHook(() => useChat());
    await waitFor(() => expect(sessionStorage.getItem(STORAGE_KEY)).toBeNull());
    expect(result.current.state).toMatchObject({ sessionId: null, messages: [] });
  });

  it.each([
    ["null entry", JSON.stringify({ v: 1, savedAt: Date.now(), sessionId: "s", messages: [null] })],
    ["old bare array", JSON.stringify(history())],
    ["old assistant shape", JSON.stringify({ v: 1, savedAt: Date.now(), sessionId: "s", messages: [{ id: "a", role: "assistant", text: "x" }] })],
    ["not JSON", "{oops"],
    ["literal null", "null"],
  ])("does not crash on a bad stored value (%s) and starts clean", async (_name, raw) => {
    sessionStorage.setItem(STORAGE_KEY, raw);
    const { result } = renderHook(() => useChat());
    expect(result.current.state.messages).toEqual([]);
    await waitFor(() => expect(sessionStorage.getItem(STORAGE_KEY)).toBeNull());
  });

  it("ignores the unversioned keys of older builds", async () => {
    sessionStorage.setItem("sahayak.session", "legacy");
    sessionStorage.setItem("sahayak.messages", JSON.stringify([null]));
    const { result } = renderHook(() => useChat());
    await waitFor(() => expect(sessionStorage.getItem("sahayak.messages")).toBeNull());
    expect(result.current.state.sessionId).toBeNull();
  });

  it("marks a restored restart: new session id from the server inserts the notice and keeps earlier messages", async () => {
    store(Date.now() - 60_000);
    fetchMock.mockResolvedValueOnce(okResponse(sse("session", { session_id: "brand-new" }), sse("answer", { content: "Who is this for?" }), DONE));
    const { result } = renderHook(() => useChat());
    await waitFor(() => expect(result.current.state.messages).toHaveLength(2));
    act(() => void result.current.send("haan"));
    await waitFor(() => expect(result.current.state.busy).toBe(false));
    expect(result.current.state.sessionId).toBe("brand-new");
    expect(result.current.state.messages.map((m) => m.role)).toEqual(["user", "assistant", "notice", "user", "assistant"]);
    await waitFor(() => expect(JSON.parse(sessionStorage.getItem(STORAGE_KEY)!).sessionId).toBe("brand-new"));
  });
});

describe("useChat: stop and dropped connections", () => {
  it("Stop keeps the partial text, marks it stopped and aborts the request", async () => {
    const live = liveStream();
    fetchMock.mockResolvedValueOnce(live.response);
    const { result } = renderHook(() => useChat());
    act(() => void result.current.send("hi"));
    live.push(sse("session", { session_id: "s1" }), sse("token", { delta: "Part" }));
    await waitFor(() => expect(asst(result.current.state).text).toBe("Part"));
    act(() => result.current.stop());
    expect(result.current.state.busy).toBe(false);
    expect(asst(result.current.state)).toMatchObject({ text: "Part", streaming: false, stopped: true, error: null });
    expect(((fetchMock.mock.calls[0][1] as RequestInit).signal as AbortSignal).aborted).toBe(true);
    // A new message can be sent right away.
    fetchMock.mockResolvedValueOnce(okResponse(sse("session", { session_id: "s1" }), DONE));
    let ok = false;
    act(() => {
      ok = result.current.send("again");
    });
    expect(ok).toBe(true);
    await waitFor(() => expect(result.current.state.busy).toBe(false));
  });

  it("a stream that ends after `answer` but before `done` is a success (no error, no retry needed)", async () => {
    fetchMock.mockResolvedValueOnce(okResponse(sse("session", { session_id: "s1" }), sse("answer", { content: "Full answer" })));
    const { result } = renderHook(() => useChat());
    act(() => void result.current.send("hi"));
    await waitFor(() => expect(result.current.state.busy).toBe(false));
    expect(asst(result.current.state)).toMatchObject({ text: "Full answer", streaming: false, error: null });
    expect(asst(result.current.state).stopped).toBeFalsy();
  });

  it("a network reset after `answer` is also a success", async () => {
    const live = liveStream();
    fetchMock.mockResolvedValueOnce(live.response);
    const { result } = renderHook(() => useChat());
    act(() => void result.current.send("hi"));
    live.push(sse("session", { session_id: "s1" }), sse("answer", { content: "Full answer" }));
    await waitFor(() => expect(asst(result.current.state).text).toBe("Full answer"));
    live.error(new TypeError("network error"));
    await waitFor(() => expect(result.current.state.busy).toBe(false));
    expect(asst(result.current.state)).toMatchObject({ text: "Full answer", error: null, streaming: false });
  });

  it("a stream cut before any answer is an error, and Retry re-sends once without duplicating the turn", async () => {
    fetchMock.mockResolvedValueOnce(okResponse(sse("session", { session_id: "s1" }), sse("token", { delta: "Par" })));
    const { result } = renderHook(() => useChat());
    act(() => void result.current.send("hello"));
    await waitFor(() => expect(result.current.state.busy).toBe(false));
    expect(asst(result.current.state).error).toMatchObject({ code: "network" });

    fetchMock.mockResolvedValueOnce(okResponse(sse("session", { session_id: "s1" }), sse("answer", { content: "Good" }), DONE));
    act(() => result.current.retry());
    await waitFor(() => expect(result.current.state.busy).toBe(false));
    expect(result.current.state.messages.map((m) => m.role)).toEqual(["user", "assistant"]);
    expect(asst(result.current.state)).toMatchObject({ text: "Good", error: null });
    expect(bodies(fetchMock).map((b) => b.message)).toEqual(["hello", "hello"]);
  });

  it("late events after done do not leave the message streaming", async () => {
    fetchMock.mockResolvedValueOnce(okResponse(sse("session", { session_id: "s1" }), sse("answer", { content: "A" }), DONE, sse("token", { delta: "stray" })));
    const { result } = renderHook(() => useChat());
    act(() => void result.current.send("hi"));
    await waitFor(() => expect(result.current.state.busy).toBe(false));
    expect(asst(result.current.state)).toMatchObject({ text: "A", streaming: false, activity: null });
  });

  it("reset aborts the stream, clears state and storage", async () => {
    const live = liveStream();
    fetchMock.mockResolvedValueOnce(live.response); // chat
    fetchMock.mockResolvedValueOnce(new Response("{}")); // /api/session/reset
    const { result } = renderHook(() => useChat());
    act(() => void result.current.send("hi"));
    live.push(sse("session", { session_id: "s1" }));
    await waitFor(() => expect(result.current.state.sessionId).toBe("s1"));
    act(() => result.current.reset());
    expect(result.current.state).toMatchObject({ sessionId: null, messages: [], busy: false });
    await waitFor(() => expect(sessionStorage.getItem(STORAGE_KEY)).toBeNull());
    expect(String(fetchMock.mock.calls[1][0])).toContain("/api/session/reset");
  });
});

describe("useChat: HTTP and server errors", () => {
  it.each([
    [409, "busy", {}, undefined],
    [413, "too_large", {}, undefined],
    [429, "rate_limited", { "Retry-After": "540" }, 540],
    [503, "overloaded", { "Retry-After": "30" }, 30],
    [400, "bad_request", {}, undefined],
    [500, "internal", {}, undefined],
  ] as const)("HTTP %i shows the %s error", async (status, code, headers, retryAfter) => {
    fetchMock.mockResolvedValueOnce(jsonResponse(status, "x", headers));
    const { result } = renderHook(() => useChat());
    act(() => void result.current.send("hi"));
    await waitFor(() => expect(result.current.state.busy).toBe(false));
    expect(asst(result.current.state).error).toMatchObject({ code, retryAfter });
    expect(asst(result.current.state)).toMatchObject({ streaming: false });
  });

  it("recovers from a 503 with Retry: the second attempt succeeds and the transcript has one turn", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(503, "busy", { "Retry-After": "5" }));
    const { result } = renderHook(() => useChat());
    act(() => void result.current.send("hi"));
    await waitFor(() => expect(asst(result.current.state)?.error?.code).toBe("overloaded"));
    fetchMock.mockResolvedValueOnce(okResponse(sse("session", { session_id: "s" }), sse("answer", { content: "ok" }), DONE));
    act(() => result.current.retry());
    await waitFor(() => expect(result.current.state.busy).toBe(false));
    expect(result.current.state.messages).toHaveLength(2);
    expect(asst(result.current.state).error).toBeNull();
  });

  it("a fetch rejection is a network error", async () => {
    fetchMock.mockRejectedValueOnce(new TypeError("Failed to fetch"));
    const { result } = renderHook(() => useChat());
    act(() => void result.current.send("hi"));
    await waitFor(() => expect(result.current.state.busy).toBe(false));
    expect(asst(result.current.state).error?.code).toBe("network");
  });

  it("a per-session message cap error event surfaces as session_limit", async () => {
    fetchMock.mockResolvedValueOnce(
      okResponse(sse("session", { session_id: "s1" }), sse("error", { message: "Please start a new conversation.", code: "session_limit" })),
    );
    const { result } = renderHook(() => useChat());
    act(() => void result.current.send("hi"));
    await waitFor(() => expect(result.current.state.busy).toBe(false));
    expect(asst(result.current.state).error?.code).toBe("session_limit");
  });
});

describe("useChat: cold start (free-tier server waking up)", () => {
  afterEach(() => vi.useRealTimers());

  /** fetch that stays pending until the test resolves it. */
  function pendingFetch() {
    let resolve!: (r: Response) => void;
    fetchMock.mockReturnValueOnce(new Promise<Response>((r) => (resolve = r)));
    return (r: Response) => resolve(r);
  }

  it("shows the waking status only after WAKE_DELAY_MS without a first event", async () => {
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
    const respond = pendingFetch();
    const { result } = renderHook(() => useChat());
    act(() => void result.current.send("hello"));
    expect(asst(result.current.state).activity).toBe("thinking");
    act(() => void vi.advanceTimersByTime(WAKE_DELAY_MS - 1));
    expect(asst(result.current.state).activity).toBe("thinking");
    act(() => void vi.advanceTimersByTime(1));
    expect(asst(result.current.state).activity).toBe("waking");
    expect(DICTS.en.chat.status.waking).toMatch(/Waking up the server.*up to a minute/);

    // the server finally answers: the status clears and the reply renders normally
    const live = liveStream();
    await act(async () => {
      respond(live.response);
      live.push(sse("session", { session_id: "s9" }), sse("answer", { content: "Namaste" }), DONE);
    });
    await vi.waitFor(() => expect(result.current.state.busy).toBe(false));
    expect(asst(result.current.state)).toMatchObject({ text: "Namaste", streaming: false, activity: null, error: null });
  });

  it("never shows it when the first event arrives in time", async () => {
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
    fetchMock.mockResolvedValueOnce(okResponse(sse("session", { session_id: "s1" }), sse("answer", { content: "Hi" }), DONE));
    const { result } = renderHook(() => useChat());
    act(() => void result.current.send("hello"));
    await vi.waitFor(() => expect(result.current.state.busy).toBe(false));
    act(() => void vi.advanceTimersByTime(WAKE_DELAY_MS * 2));
    expect(asst(result.current.state).activity).toBeNull();
    expect(vi.getTimerCount()).toBe(0);
  });

  it("stopping before the timer fires cancels it", async () => {
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
    pendingFetch();
    const { result } = renderHook(() => useChat());
    act(() => void result.current.send("hello"));
    act(() => result.current.stop());
    act(() => void vi.advanceTimersByTime(WAKE_DELAY_MS * 2));
    expect(asst(result.current.state).activity).toBeNull();
  });

  it("has the waking text in all four languages", () => {
    for (const lang of ["en", "hi", "hinglish", "ta"] as const) {
      expect(DICTS[lang].chat.status.waking.length).toBeGreaterThan(10);
    }
  });
});
