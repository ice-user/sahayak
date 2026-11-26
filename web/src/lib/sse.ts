import type { ChatEvent, ErrorCode } from "./types";
import { normalizeErrorCode } from "./chat-state";

/** A raw Server-Sent Event: `event:` name plus joined `data:` payload. */
export interface RawSSE {
  event: string;
  data: string;
}

/**
 * Incremental SSE parser. Feed it text chunks of any size (chunks may split
 * lines, CRLF pairs or UTF-8 sequences once decoded) and it returns the
 * complete events found so far. Follows the WHATWG EventSource framing rules
 * that matter for us: `event:`, multi-line `data:`, comments (`:`), blank-line
 * dispatch, optional single leading space after the colon, LF/CRLF/CR.
 */
export class SSEParser {
  private buffer = "";
  private event = "";
  private data: string[] = [];
  private pendingCR = false;

  feed(chunk: string): RawSSE[] {
    let text = chunk;
    if (this.pendingCR) {
      this.pendingCR = false;
      if (text.startsWith("\n")) text = text.slice(1);
    }
    this.buffer += text;
    const out: RawSSE[] = [];
    let i = 0;
    const b = this.buffer;
    while (i < b.length) {
      let j = i;
      while (j < b.length && b[j] !== "\n" && b[j] !== "\r") j++;
      if (j >= b.length) break; // incomplete line: wait for more
      const line = b.slice(i, j);
      if (b[j] === "\r") {
        if (j + 1 < b.length) {
          i = b[j + 1] === "\n" ? j + 2 : j + 1;
        } else {
          // lone CR at chunk end: could be CRLF split across chunks
          i = j + 1;
          this.pendingCR = true;
        }
      } else {
        i = j + 1;
      }
      const ev = this.handleLine(line);
      if (ev) out.push(ev);
    }
    this.buffer = b.slice(i);
    return out;
  }

  /** Call when the stream ends; flushes a final event missing its blank line. */
  flush(): RawSSE[] {
    const out: RawSSE[] = [];
    if (this.buffer) {
      const ev = this.handleLine(this.buffer);
      if (ev) out.push(ev);
      this.buffer = "";
    }
    const last = this.dispatch();
    if (last) out.push(last);
    return out;
  }

  private handleLine(line: string): RawSSE | null {
    if (line === "") return this.dispatch();
    if (line.startsWith(":")) return null;
    const idx = line.indexOf(":");
    const field = idx === -1 ? line : line.slice(0, idx);
    let value = idx === -1 ? "" : line.slice(idx + 1);
    if (value.startsWith(" ")) value = value.slice(1);
    if (field === "event") this.event = value;
    else if (field === "data") this.data.push(value);
    return null;
  }

  private dispatch(): RawSSE | null {
    if (this.data.length === 0) {
      this.event = "";
      return null;
    }
    const ev = { event: this.event || "message", data: this.data.join("\n") };
    this.event = "";
    this.data = [];
    return ev;
  }
}


const isRecord = (v: unknown): v is Record<string, unknown> =>
  typeof v === "object" && v !== null && !Array.isArray(v);

/** Converts a raw event to a typed ChatEvent; unknown/malformed events -> null. */
export function toChatEvent(raw: RawSSE): ChatEvent | null {
  let d: unknown;
  try {
    d = JSON.parse(raw.data);
  } catch {
    return null;
  }
  if (!isRecord(d)) return null;
  switch (raw.event) {
    case "session":
      return typeof d.session_id === "string" ? { type: "session", session_id: d.session_id } : null;
    case "tool_call":
      return typeof d.name === "string"
        ? {
            type: "tool_call",
            id: String(d.id ?? ""),
            name: d.name,
            arguments: isRecord(d.arguments) ? d.arguments : {},
          }
        : null;
    case "tool_result":
      return typeof d.name === "string"
        ? { type: "tool_result", id: String(d.id ?? ""), name: d.name, result: d.result }
        : null;
    case "token":
      return typeof d.delta === "string" ? { type: "token", delta: d.delta } : null;
    case "answer":
      return typeof d.content === "string" ? { type: "answer", content: d.content } : null;
    case "suggestions":
      return Array.isArray(d.options)
        ? { type: "suggestions", options: d.options.filter((o): o is string => typeof o === "string").slice(0, 4) }
        : null;
    case "done":
      return {
        type: "done",
        latency_s: Number(d.latency_s ?? 0),
        llm_calls: Number(d.llm_calls ?? 0),
        tokens: Number(d.tokens ?? 0),
      };
    case "error": {
      const code = normalizeErrorCode(d.code, typeof d.message === "string" ? d.message : "") as ErrorCode;
      return { type: "error", message: typeof d.message === "string" ? d.message : "", code };
    }
    default:
      return null;
  }
}

/** Reads a fetch Response body (SSE) and yields typed events. */
export async function* readChatEvents(body: ReadableStream<Uint8Array>): AsyncGenerator<ChatEvent> {
  const reader = body.getReader();
  const decoder = new TextDecoder("utf-8");
  const parser = new SSEParser();
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      for (const raw of parser.feed(decoder.decode(value, { stream: true }))) {
        const ev = toChatEvent(raw);
        if (ev) yield ev;
      }
    }
    for (const raw of [...parser.feed(decoder.decode()), ...parser.flush()]) {
      const ev = toChatEvent(raw);
      if (ev) yield ev;
    }
  } finally {
    reader.releaseLock();
  }
}
