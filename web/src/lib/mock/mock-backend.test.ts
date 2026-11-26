import { describe, expect, it } from "vitest";
import { chatReducer, initialChatState, type AssistantMessage, type ChatState } from "../chat-state";
import { readChatEvents } from "../sse";
import type { ChatEvent } from "../types";
import { detectLang, extractFacts, mockChatResponse, mockGetScheme, mockListSchemes } from "./mock-backend";
import { checkAll } from "./rules";

async function turn(message: string, sessionId: string | null) {
  const res = await mockChatResponse(message, sessionId);
  const events: ChatEvent[] = [];
  for await (const e of readChatEvents(res.body!)) events.push(e);
  return { res, events };
}

describe("mock backend", () => {
  it("serves schemes without rules in the list and with rules in the detail", () => {
    expect(mockListSchemes()).toHaveLength(10);
    expect("rules" in mockListSchemes()[0]).toBe(false);
    expect(mockGetScheme("apy")?.rules?.length).toBeGreaterThan(0);
    expect(mockGetScheme("nope")).toBeUndefined();
  });

  it("rule port: empty profile is never eligible", () => {
    const r = checkAll({}, mockListSchemes().map((s) => mockGetScheme(s.id)!));
    expect(r.eligible).toHaveLength(0);
  });

  it("detects languages and extracts facts", () => {
    expect(detectLang("मेरी माँ 62 साल की विधवा हैं", "en")).toBe("hi");
    expect(detectLang("என் அம்மாவுக்கு 62 வயது", "en")).toBe("ta");
    expect(detectLang("meri maa 62 saal ki widow hain", "en")).toBe("hinglish");
    const s = { facts: {}, asked: null, skipped: new Set<string>(), lang: "en" as const, history: [] };
    expect(extractFacts("My mother is 62, a widow, with a BPL card", s).facts).toMatchObject({ age: 62, gender: "female", marital_status: "widowed", bpl: true });
  });

  it(
    "streams every event type for a widow query and the reducer builds cards",
    async () => {
      const { events } = await turn("My mother is 62, a widow, and has a BPL card. What can she get?", null);
      const types = new Set(events.map((e) => e.type));
      for (const t of ["session", "tool_call", "tool_result", "token", "answer", "suggestions", "done"]) expect(types.has(t as ChatEvent["type"])).toBe(true);
      expect(events[0].type).toBe("session");
      expect(events.at(-1)?.type).toBe("done");
      const idxSugg = events.findIndex((e) => e.type === "suggestions");
      expect(idxSugg).toBeLessThan(events.length - 1);

      let s: ChatState = chatReducer(initialChatState, { type: "send", text: "q", userId: "u", assistantId: "a" });
      for (const event of events) s = chatReducer(s, { type: "event", event });
      const m = s.messages[1] as AssistantMessage;
      expect(m.eligibility?.eligible.map((e) => e.scheme_id)).toEqual(expect.arrayContaining(["ignwps", "ignoaps"]));
      expect(m.eligibility?.need_info.length).toBeGreaterThan(0);
      expect(m.eligibility?.not_eligible.length).toBeGreaterThan(0);
      expect(m.suggestions.length).toBeGreaterThan(0);
      expect(s.busy).toBe(false);
    },
    20000,
  );

  it(
    "emits an error once for mock:error, then succeeds on retry; 429 carries Retry-After",
    async () => {
      const first = await turn("mock:error my father is 72", null);
      expect(first.events.at(-1)).toMatchObject({ type: "error", code: "llm_error" });
      const second = await turn("mock:error my father is 72", null);
      expect(second.events.at(-1)?.type).toBe("done");

      const rl = await mockChatResponse("mock:ratelimit hello", null);
      expect(rl.status).toBe(429);
      expect(rl.headers.get("Retry-After")).toBe("540");
      const busy = await mockChatResponse("mock:busy hello", null);
      expect(busy.status).toBe(409);
    },
    30000,
  );
});
