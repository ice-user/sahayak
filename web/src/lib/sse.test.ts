import { describe, expect, it } from "vitest";
import { readChatEvents, SSEParser, toChatEvent } from "./sse";
import type { ChatEvent } from "./types";

const stream = `event: session\ndata: {"session_id":"abc"}\n\nevent: token\ndata: {"delta":"नमस्ते "}\n\nevent: done\ndata: {"latency_s":1.5,"llm_calls":2,"tokens":10}\n\n`;

function bodyFrom(chunks: Uint8Array[]): ReadableStream<Uint8Array> {
  return new ReadableStream({
    start(c) {
      chunks.forEach((x) => c.enqueue(x));
      c.close();
    },
  });
}
async function collect(body: ReadableStream<Uint8Array>): Promise<ChatEvent[]> {
  const out: ChatEvent[] = [];
  for await (const e of readChatEvents(body)) out.push(e);
  return out;
}

describe("SSEParser", () => {
  it("parses complete events", () => {
    const p = new SSEParser();
    const evs = p.feed(stream);
    expect(evs.map((e) => e.event)).toEqual(["session", "token", "done"]);
    expect(JSON.parse(evs[0].data)).toEqual({ session_id: "abc" });
  });

  it("is chunk-size independent (feeds one character at a time)", () => {
    const p = new SSEParser();
    const evs = [...stream].flatMap((ch) => p.feed(ch));
    expect(evs.map((e) => e.event)).toEqual(["session", "token", "done"]);
  });

  it("handles CRLF, including a CR/LF pair split across chunks", () => {
    const p = new SSEParser();
    const a = p.feed("event: token\r\ndata: {\"delta\":\"x\"}\r");
    const b = p.feed("\n\r\n");
    expect([...a, ...b]).toEqual([{ event: "token", data: '{"delta":"x"}' }]);
  });

  it("joins multi-line data and ignores comments and unknown fields", () => {
    const p = new SSEParser();
    const evs = p.feed(": keep-alive\nid: 7\nevent: answer\ndata: line1\ndata: line2\n\n");
    expect(evs).toEqual([{ event: "answer", data: "line1\nline2" }]);
  });

  it("defaults the event name to 'message' and tolerates no space after the colon", () => {
    expect(new SSEParser().feed("data:{\"a\":1}\n\n")).toEqual([{ event: "message", data: '{"a":1}' }]);
  });

  it("does not dispatch events without data, and flushes a trailing event", () => {
    const p = new SSEParser();
    expect(p.feed("event: ping\n\n")).toEqual([]);
    expect(p.feed("event: done\ndata: {}")).toEqual([]);
    expect(p.flush()).toEqual([{ event: "done", data: "{}" }]);
  });
});

describe("toChatEvent", () => {
  it("maps every documented event", () => {
    const cases: [string, unknown, ChatEvent["type"]][] = [
      ["session", { session_id: "s" }, "session"],
      ["tool_call", { id: "c1", name: "search_schemes", arguments: { query: "q" } }, "tool_call"],
      ["tool_result", { id: "c1", name: "search_schemes", result: [] }, "tool_result"],
      ["token", { delta: "a" }, "token"],
      ["answer", { content: "full" }, "answer"],
      ["suggestions", { options: ["a", "b"] }, "suggestions"],
      ["done", { latency_s: 1, llm_calls: 1, tokens: 1 }, "done"],
      ["error", { message: "m", code: "rate_limited" }, "error"],
    ];
    for (const [event, data, type] of cases) {
      expect(toChatEvent({ event, data: JSON.stringify(data) })?.type).toBe(type);
    }
  });

  it("drops malformed JSON and unknown events instead of throwing", () => {
    expect(toChatEvent({ event: "token", data: "{oops" })).toBeNull();
    expect(toChatEvent({ event: "mystery", data: "{}" })).toBeNull();
    expect(toChatEvent({ event: "token", data: "[]" })).toBeNull();
    expect(toChatEvent({ event: "token", data: '{"delta":3}' })).toBeNull();
  });

  it("caps suggestions at 4 and normalises unknown error codes", () => {
    const s = toChatEvent({ event: "suggestions", data: JSON.stringify({ options: ["1", "2", "3", "4", "5", 6] }) });
    expect(s).toEqual({ type: "suggestions", options: ["1", "2", "3", "4"] });
    expect(toChatEvent({ event: "error", data: '{"message":"x","code":"weird"}' })).toEqual({ type: "error", message: "x", code: "internal" });
  });
});

describe("readChatEvents", () => {
  it("decodes a byte stream split mid UTF-8 character", async () => {
    const bytes = new TextEncoder().encode(stream);
    const at = stream.indexOf("नमस्ते") + 1; // character index; find a byte offset inside the first Devanagari char
    const byteAt = new TextEncoder().encode(stream.slice(0, at)).length + 1;
    const events = await collect(bodyFrom([bytes.slice(0, byteAt), bytes.slice(byteAt)]));
    expect(events.map((e) => e.type)).toEqual(["session", "token", "done"]);
    expect(events[1]).toEqual({ type: "token", delta: "नमस्ते " });
  });

  it("flushes a final event that lacks the closing blank line", async () => {
    const bytes = new TextEncoder().encode('event: answer\ndata: {"content":"hi"}\n');
    expect(await collect(bodyFrom([bytes]))).toEqual([{ type: "answer", content: "hi" }]);
  });
});
