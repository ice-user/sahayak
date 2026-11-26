import { describe, expect, it } from "vitest";
import {
  chatReducer,
  initialChatState,
  lastUserText,
  normalizeErrorCode,
  parseEligibility,
  type AssistantMessage,
  type ChatAction,
  type ChatState,
} from "./chat-state";
import type { ChatEvent, EligibilityResult } from "./types";

const send = (s: ChatState, text = "hello", n = 1): ChatState =>
  chatReducer(s, { type: "send", text, userId: `u${n}`, assistantId: `a${n}` });
const ev = (s: ChatState, event: ChatEvent): ChatState => chatReducer(s, { type: "event", event });
const last = (s: ChatState) => s.messages[s.messages.length - 1] as AssistantMessage;

const eligibility: EligibilityResult = {
  eligible: [{ scheme_id: "ignwps", scheme_name: "IGNWPS", verdict: "eligible", failed_reasons: [], missing_fields: [], caveats: [], benefits: "Rs 300", source_url: "https://x" }],
  need_info: [{ scheme_id: "apy", scheme_name: "APY", missing_fields: ["has_bank_account"] }],
  not_eligible: [{ scheme_id: "pm_kisan", reasons: ["Family must own cultivable land"] }],
};

describe("chatReducer", () => {
  it("send adds the user message and a streaming assistant placeholder, and marks busy", () => {
    const s = send(initialChatState);
    expect(s.busy).toBe(true);
    expect(s.messages.map((m) => m.role)).toEqual(["user", "assistant"]);
    expect(last(s)).toMatchObject({ streaming: true, activity: "thinking", text: "" });
  });

  it("stores the session id from the session event, overwriting an old one", () => {
    let s = chatReducer(initialChatState, { type: "restore", sessionId: "old", messages: [] });
    s = send(s);
    s = ev(s, { type: "session", session_id: "new" });
    expect(s.sessionId).toBe("new");
  });

  it("tool_call sets the activity and records the step; tool_result attaches the result", () => {
    let s = send(initialChatState);
    s = ev(s, { type: "tool_call", id: "c1", name: "search_schemes", arguments: { query: "widow" } });
    expect(last(s).activity).toBe("searching");
    s = ev(s, { type: "tool_call", id: "c2", name: "check_eligibility", arguments: { profile: { age: 62 } } });
    expect(last(s).activity).toBe("checking");
    s = ev(s, { type: "tool_result", id: "c1", name: "search_schemes", result: [] });
    expect(last(s).steps[0]).toMatchObject({ id: "c1", result: [], failed: false });
    expect(last(s).steps[1].result).toBeUndefined();
  });

  it("keeps check_eligibility output for the cards; later calls replace earlier ones", () => {
    let s = send(initialChatState);
    s = ev(s, { type: "tool_call", id: "c1", name: "check_eligibility", arguments: {} });
    s = ev(s, { type: "tool_result", id: "c1", name: "check_eligibility", result: eligibility });
    expect(last(s).eligibility).toEqual(eligibility);
    const second: EligibilityResult = { eligible: [], need_info: [], not_eligible: [] };
    s = ev(s, { type: "tool_call", id: "c2", name: "check_eligibility", arguments: {} });
    s = ev(s, { type: "tool_result", id: "c2", name: "check_eligibility", result: second });
    expect(last(s).eligibility).toEqual(second);
  });

  it("ignores tool errors for cards but flags the step as failed", () => {
    let s = send(initialChatState);
    s = ev(s, { type: "tool_call", id: "c1", name: "check_eligibility", arguments: {} });
    s = ev(s, { type: "tool_result", id: "c1", name: "check_eligibility", result: { error: "Invalid profile" } });
    expect(last(s).eligibility).toBeNull();
    expect(last(s).steps[0].failed).toBe(true);
  });

  it("accumulates token deltas, then the answer replaces them", () => {
    let s = send(initialChatState);
    s = ev(s, { type: "token", delta: "Hel" });
    s = ev(s, { type: "token", delta: "lo" });
    expect(last(s)).toMatchObject({ text: "Hello", activity: "writing" });
    s = ev(s, { type: "answer", content: "Hello, **final**" });
    expect(last(s).text).toBe("Hello, **final**");
  });

  it("works when no token events arrive (answer only), as the real backend does today", () => {
    let s = send(initialChatState);
    s = ev(s, { type: "session", session_id: "s1" });
    s = ev(s, { type: "tool_call", id: "c1", name: "search_schemes", arguments: {} });
    expect(last(s).text).toBe("");
    expect(last(s).streaming).toBe(true);
    s = ev(s, { type: "answer", content: "Whole answer" });
    expect(last(s).text).toBe("Whole answer");
  });

  it("handles suggestions followed by done (done arrives last)", () => {
    let s = send(initialChatState);
    s = ev(s, { type: "answer", content: "Q?" });
    s = ev(s, { type: "suggestions", options: ["Yes", "No", "Not sure", "a", "b"] });
    expect(last(s).suggestions).toEqual(["Yes", "No", "Not sure", "a"]);
    expect(s.busy).toBe(true);
    s = ev(s, { type: "done", latency_s: 3.2, llm_calls: 2, tokens: 1450 });
    expect(s.busy).toBe(false);
    expect(last(s)).toMatchObject({ streaming: false, activity: null, stats: { latency_s: 3.2, llm_calls: 2, tokens: 1450 } });
    expect(last(s).suggestions).toHaveLength(4);
  });

  it("an LLM-not-configured stream (session then error) ends in an error state", () => {
    let s = send(initialChatState);
    s = ev(s, { type: "session", session_id: "s1" });
    s = ev(s, { type: "error", message: "Provider not configured", code: "llm_error" });
    expect(s.busy).toBe(false);
    expect(last(s)).toMatchObject({ streaming: false, error: { code: "llm_error" } });
    expect(s.sessionId).toBe("s1");
  });

  it("fail covers HTTP errors: 409 busy and 429 with Retry-After", () => {
    let s = send(initialChatState);
    s = chatReducer(s, { type: "fail", message: "already running", code: "busy" });
    expect(last(s).error).toMatchObject({ code: "busy" });
    expect(s.busy).toBe(false);
    s = send(chatReducer(s, { type: "discard_error" }), "again", 2);
    s = chatReducer(s, { type: "fail", message: "slow down", code: "rate_limited", retryAfter: 120 });
    expect(last(s).error).toEqual({ message: "slow down", code: "rate_limited", retryAfter: 120 });
  });

  it("discard_error removes the failed turn so a retry does not duplicate the question", () => {
    let s = send(initialChatState, "my question");
    s = ev(s, { type: "error", message: "x", code: "internal" });
    expect(lastUserText(s)).toBe("my question");
    s = chatReducer(s, { type: "discard_error" });
    expect(s.messages).toHaveLength(0);
    s = send(s, "my question", 2);
    expect(s.messages.filter((m) => m.role === "user")).toHaveLength(1);
  });

  it("discard_error leaves a successful turn alone", () => {
    let s = send(initialChatState);
    s = ev(s, { type: "done", latency_s: 1, llm_calls: 1, tokens: 1 });
    expect(chatReducer(s, { type: "discard_error" })).toBe(s);
  });

  it("end stops a dangling stream (abort or dropped connection) without marking an error", () => {
    let s = send(initialChatState);
    s = ev(s, { type: "token", delta: "partial" });
    s = chatReducer(s, { type: "end" });
    expect(s.busy).toBe(false);
    expect(last(s)).toMatchObject({ streaming: false, activity: null, text: "partial", error: null });
  });

  it("reset clears everything, including the session id", () => {
    let s = send(initialChatState);
    s = ev(s, { type: "session", session_id: "s1" });
    expect(chatReducer(s, { type: "reset" })).toEqual(initialChatState);
  });

  it("only updates the latest assistant message across multiple turns", () => {
    let s = send(initialChatState, "one", 1);
    s = ev(s, { type: "answer", content: "A1" });
    s = ev(s, { type: "done", latency_s: 1, llm_calls: 1, tokens: 1 });
    s = send(s, "two", 2);
    s = ev(s, { type: "answer", content: "A2" });
    expect((s.messages[1] as AssistantMessage).text).toBe("A1");
    expect((s.messages[3] as AssistantMessage).text).toBe("A2");
  });

  it("ignores events when there is no assistant message (stale stream after reset)", () => {
    const action: ChatAction = { type: "event", event: { type: "token", delta: "x" } };
    expect(chatReducer(initialChatState, action)).toEqual(initialChatState);
  });
});

describe("chatReducer: review fixes", () => {
  const settled = (): ChatState => {
    let s = send(initialChatState, "first", 1);
    s = ev(s, { type: "session", session_id: "old" });
    s = ev(s, { type: "answer", content: "A1" });
    return ev(s, { type: "done", latency_s: 1, llm_calls: 1, tokens: 1 });
  };

  it("duplicate tool_call ids: each result resolves the first unresolved step with that id", () => {
    let s = send(initialChatState);
    s = ev(s, { type: "tool_call", id: "call_1", name: "search_schemes", arguments: { query: "a" } });
    s = ev(s, { type: "tool_call", id: "call_1", name: "search_schemes", arguments: { query: "b" } });
    s = ev(s, { type: "tool_result", id: "call_1", name: "search_schemes", result: ["first"] });
    s = ev(s, { type: "tool_result", id: "call_1", name: "search_schemes", result: ["second"] });
    expect(last(s).steps.map((x) => x.result)).toEqual([["first"], ["second"]]);
    expect(last(s).steps.map((x) => x.args.query)).toEqual(["a", "b"]);
  });

  it("ignores late events after done (no stuck spinner, text unchanged)", () => {
    let s = settled();
    s = send(s, "second", 2);
    s = ev(s, { type: "answer", content: "A2" });
    s = ev(s, { type: "done", latency_s: 1, llm_calls: 1, tokens: 1 });
    const before = s;
    for (const event of [
      { type: "token", delta: "stray" },
      { type: "tool_call", id: "x", name: "search_schemes", arguments: {} },
      { type: "suggestions", options: ["late"] },
      { type: "session", session_id: "zzz" },
    ] as ChatEvent[]) {
      s = ev(s, event);
    }
    expect(s).toBe(before);
    expect(last(s)).toMatchObject({ streaming: false, activity: null, text: "A2" });
    expect(s.sessionId).toBe("old");
  });

  it("ignores events after an error event too", () => {
    let s = send(initialChatState);
    s = ev(s, { type: "error", message: "x", code: "llm_error" });
    const before = s;
    expect(ev(s, { type: "token", delta: "late" })).toBe(before);
  });

  it("a session event with a different id inserts a restart notice before the new turn", () => {
    let s = settled();
    s = send(s, "haan", 2);
    s = ev(s, { type: "session", session_id: "new" });
    expect(s.sessionId).toBe("new");
    expect(s.messages.map((m) => m.role)).toEqual(["user", "assistant", "notice", "user", "assistant"]);
    // a retry after an error does not add a second notice
    s = ev(s, { type: "error", message: "x", code: "llm_error" });
    s = chatReducer(s, { type: "discard_error" });
    s = send(s, "haan", 3);
    s = ev(s, { type: "session", session_id: "new" });
    expect(s.messages.filter((m) => m.role === "notice")).toHaveLength(1);
  });

  it("no notice for the first message, or when the server keeps the same id", () => {
    let s = send(initialChatState);
    s = ev(s, { type: "session", session_id: "s1" });
    expect(s.messages.some((m) => m.role === "notice")).toBe(false);
    s = ev(s, { type: "done", latency_s: 1, llm_calls: 1, tokens: 1 });
    s = send(s, "more", 2);
    s = ev(s, { type: "session", session_id: "s1" });
    expect(s.messages.some((m) => m.role === "notice")).toBe(false);
  });

  it("a restored conversation whose server session is gone gets the notice", () => {
    const msgs = settled().messages;
    let s = chatReducer(initialChatState, { type: "restore", sessionId: "old", messages: msgs });
    s = send(s, "62", 2);
    s = ev(s, { type: "session", session_id: "fresh" });
    expect(s.messages[2].role).toBe("notice");
  });

  it("end with stopped marks the partial message stopped and drops suggestions", () => {
    let s = send(initialChatState);
    s = ev(s, { type: "token", delta: "part" });
    s = chatReducer(s, { type: "end", stopped: true });
    expect(last(s)).toMatchObject({ stopped: true, streaming: false, text: "part" });
    expect(chatReducer(settled(), { type: "end", stopped: true }).messages.some((m) => m.role === "assistant" && m.stopped)).toBe(false);
  });

  it("maps server error codes, including a per-session message cap", () => {
    expect(normalizeErrorCode("session_limit")).toBe("session_limit");
    expect(normalizeErrorCode("message_limit")).toBe("session_limit");
    expect(normalizeErrorCode("weird", "Please start a new conversation.")).toBe("session_limit");
    expect(normalizeErrorCode("weird")).toBe("internal");
    let s = send(initialChatState);
    s = ev(s, { type: "error", message: "m", code: "session_limit" });
    expect(last(s).error?.code).toBe("session_limit");
  });

  it("parseEligibility accepts the old and new not_eligible shapes and drops junk items", () => {
    const r = parseEligibility({
      eligible: [null],
      need_info: [{ scheme_id: "a", missing_fields: ["bpl"] }],
      not_eligible: [
        { scheme_id: "old", reasons: ["r"] },
        { scheme_id: "new", scheme_name: "New", reasons: ["r"], caveats: ["may still be covered"] },
        7,
      ],
    });
    expect(r?.eligible).toEqual([]);
    expect(r?.not_eligible.map((n) => [n.scheme_id, n.scheme_name, n.caveats])).toEqual([
      ["old", undefined, undefined],
      ["new", "New", ["may still be covered"]],
    ]);
  });
});

describe("waking status (cold start)", () => {
  const sent = chatReducer(initialChatState, { type: "send", text: "hi", userId: "u", assistantId: "a" });
  const last = (s: ChatState) => s.messages[s.messages.length - 1] as AssistantMessage;

  it("switches the activity to waking while nothing has arrived", () => {
    expect(last(chatReducer(sent, { type: "waking" })).activity).toBe("waking");
  });

  it("the first event (session) clears it again", () => {
    const waking = chatReducer(sent, { type: "waking" });
    const next = chatReducer(waking, { type: "event", event: { type: "session", session_id: "s1" } });
    expect(last(next).activity).toBe("thinking");
    expect(next.sessionId).toBe("s1");
  });

  it("is ignored once text, a tool step or an error is present", () => {
    const withToken = chatReducer(sent, { type: "event", event: { type: "token", delta: "Hi" } });
    expect(last(chatReducer(withToken, { type: "waking" })).activity).toBe("writing");
    const failed = chatReducer(sent, { type: "fail", message: "x", code: "network" });
    expect(last(chatReducer(failed, { type: "waking" })).activity).toBeNull();
  });
});
