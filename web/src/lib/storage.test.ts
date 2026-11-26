import { describe, expect, it } from "vitest";
import { newAssistant, type ChatMessage } from "./chat-state";
import { MAX_AGE_MS, parseStored, serializeStored, STORAGE_VERSION } from "./storage";

const NOW = 1_700_000_000_000;
const msgs = (): ChatMessage[] => [
  { id: "u1", role: "user", text: "hi" },
  { ...newAssistant("a1"), streaming: false, text: "hello" },
];

describe("parseStored", () => {
  it("round-trips a fresh conversation", () => {
    const raw = serializeStored({ sessionId: "s1", messages: msgs() }, NOW);
    expect(parseStored(raw, NOW + 1000)).toEqual({ sessionId: "s1", messages: msgs() });
  });

  it("drops entries older than 25 minutes but keeps ones just inside", () => {
    const raw = serializeStored({ sessionId: "s1", messages: msgs() }, NOW);
    expect(parseStored(raw, NOW + MAX_AGE_MS - 1000)).not.toBeNull();
    expect(parseStored(raw, NOW + MAX_AGE_MS + 1000)).toBeNull();
  });

  it("drops null, garbage, wrong version and missing timestamp", () => {
    expect(parseStored(null, NOW)).toBeNull();
    expect(parseStored("", NOW)).toBeNull();
    expect(parseStored("{not json", NOW)).toBeNull();
    expect(parseStored("null", NOW)).toBeNull();
    expect(parseStored("[]", NOW)).toBeNull();
    expect(parseStored(JSON.stringify({ v: STORAGE_VERSION + 1, savedAt: NOW, sessionId: "s", messages: msgs() }), NOW)).toBeNull();
    expect(parseStored(JSON.stringify({ v: STORAGE_VERSION, sessionId: "s", messages: msgs() }), NOW)).toBeNull();
  });

  it("drops a legacy bare array and null entries inside messages", () => {
    expect(parseStored(JSON.stringify(msgs()), NOW)).toBeNull();
    const bad = JSON.stringify({ v: STORAGE_VERSION, savedAt: NOW, sessionId: "s", messages: [null] });
    expect(parseStored(bad, NOW)).toBeNull();
  });

  it("drops old-shape assistant messages (missing steps) and bad eligibility", () => {
    const old = { id: "a", role: "assistant", text: "x", streaming: false };
    const raw = (m: unknown) => JSON.stringify({ v: STORAGE_VERSION, savedAt: NOW, sessionId: "s", messages: [m] });
    expect(parseStored(raw(old), NOW)).toBeNull();
    expect(parseStored(raw({ ...newAssistant("a"), eligibility: { eligible: [null] } }), NOW)).toBeNull();
    expect(parseStored(raw({ ...newAssistant("a"), error: { message: 1 } }), NOW)).toBeNull();
  });

  it("normalises eligibility so null items cannot reach the renderer", () => {
    const m = { ...newAssistant("a"), streaming: false, eligibility: { eligible: [null, { scheme_id: "x" }], need_info: [], not_eligible: [] } };
    const raw = JSON.stringify({ v: STORAGE_VERSION, savedAt: NOW, sessionId: "s", messages: [m] });
    // `null` items fail strict parsing only at the container level; the container is valid so they are filtered.
    const out = parseStored(raw, NOW);
    const a = out?.messages[0];
    expect(a && a.role === "assistant" && a.eligibility?.eligible.map((e) => e.scheme_id)).toEqual(["x"]);
  });

  it("keeps notice messages", () => {
    const m: ChatMessage[] = [...msgs(), { id: "n", role: "notice", kind: "restarted" }];
    expect(parseStored(serializeStored({ sessionId: "s", messages: m }, NOW), NOW)?.messages).toHaveLength(3);
  });
});
