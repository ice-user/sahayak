import type {
  ChatEvent,
  EligibilityResult,
  UiErrorCode,
  SearchHit,
} from "./types";

/** What the assistant is doing right now; the UI maps this to a status line. */
export type Activity = "thinking" | "searching" | "checking" | "reading" | "writing" | "waking";

export interface ToolStep {
  id: string;
  name: string;
  args: Record<string, unknown>;
  /** undefined until the matching tool_result arrives. */
  result?: unknown;
  /** true when result is {error: ...}. */
  failed?: boolean;
}

export interface UserMessage {
  id: string;
  role: "user";
  text: string;
}

export interface AssistantMessage {
  id: string;
  role: "assistant";
  text: string;
  streaming: boolean;
  activity: Activity | null;
  steps: ToolStep[];
  /** Latest check_eligibility result of this turn (drives the scheme cards). */
  eligibility: EligibilityResult | null;
  suggestions: string[];
  stats: { latency_s: number; llm_calls: number; tokens: number } | null;
  error: { message: string; code: UiErrorCode; retryAfter?: number } | null;
  /** The user pressed Stop: the server rolls this turn back, so it is not remembered. */
  stopped?: boolean;
}

/** Inline divider inserted when the server no longer knows the conversation (session id changed). */
export interface NoticeMessage {
  id: string;
  role: "notice";
  kind: "restarted";
}

export type ChatMessage = UserMessage | AssistantMessage | NoticeMessage;

export interface ChatState {
  sessionId: string | null;
  messages: ChatMessage[];
  /** True from send until done/error/abort. */
  busy: boolean;
}

export const initialChatState: ChatState = { sessionId: null, messages: [], busy: false };

export type ChatAction =
  | { type: "send"; text: string; userId: string; assistantId: string }
  | { type: "event"; event: ChatEvent }
  /** No first event after WAKE_DELAY_MS: the (free-tier) server is probably starting up. Ignored once anything arrived. */
  | { type: "waking" }
  /** Network/parse failure outside of an SSE `error` event. */
  | { type: "fail"; message: string; code: UiErrorCode; retryAfter?: number }
  /** Stream ended without done/error (stopped = the user pressed Stop). */
  | { type: "end"; stopped?: boolean }
  /** Drop the trailing failed assistant message (before a retry). */
  | { type: "discard_error" }
  | { type: "reset" }
  | { type: "restore"; sessionId: string | null; messages: ChatMessage[] };

export function newAssistant(id: string): AssistantMessage {
  return {
    id,
    role: "assistant",
    text: "",
    streaming: true,
    activity: "thinking",
    steps: [],
    eligibility: null,
    suggestions: [],
    stats: null,
    error: null,
  };
}

const TOOL_ACTIVITY: Record<string, Activity> = {
  search_schemes: "searching",
  check_eligibility: "checking",
  get_scheme_details: "reading",
};

const isRecord = (v: unknown): v is Record<string, unknown> =>
  typeof v === "object" && v !== null && !Array.isArray(v);

const strings = (v: unknown): string[] => (Array.isArray(v) ? v.filter((x): x is string => typeof x === "string") : []);

/**
 * Shape-checks a check_eligibility result. Malformed items are dropped and optional arrays
 * normalised, so rendering never has to guard against null entries.
 */
export function parseEligibility(v: unknown): EligibilityResult | null {
  if (!isRecord(v) || !Array.isArray(v.eligible) || !Array.isArray(v.need_info) || !Array.isArray(v.not_eligible)) {
    return null;
  }
  const hasId = (x: unknown): x is Record<string, unknown> => isRecord(x) && typeof x.scheme_id === "string";
  return {
    eligible: v.eligible.filter(hasId).map((e) => ({
      scheme_id: e.scheme_id as string,
      scheme_name: typeof e.scheme_name === "string" ? e.scheme_name : (e.scheme_id as string),
      verdict: typeof e.verdict === "string" ? e.verdict : "eligible",
      failed_reasons: strings(e.failed_reasons),
      missing_fields: strings(e.missing_fields),
      caveats: strings(e.caveats),
      benefits: typeof e.benefits === "string" ? e.benefits : "",
      source_url: typeof e.source_url === "string" ? e.source_url : "",
    })),
    need_info: v.need_info.filter(hasId).map((n) => ({
      scheme_id: n.scheme_id as string,
      scheme_name: typeof n.scheme_name === "string" ? n.scheme_name : (n.scheme_id as string),
      missing_fields: strings(n.missing_fields),
    })),
    not_eligible: v.not_eligible.filter(hasId).map((n) => ({
      scheme_id: n.scheme_id as string,
      ...(typeof n.scheme_name === "string" ? { scheme_name: n.scheme_name } : {}),
      reasons: strings(n.reasons),
      ...(Array.isArray(n.caveats) ? { caveats: strings(n.caveats) } : {}),
    })),
  };
}

/** Maps a server `error` code to the UI's set; unknown codes fall back to "internal". */
export function normalizeErrorCode(code: unknown, message = ""): UiErrorCode {
  const known = ["rate_limited", "bad_request", "llm_error", "internal", "session_limit"] as const;
  if (typeof code === "string" && (known as readonly string[]).includes(code)) return code as UiErrorCode;
  if (typeof code === "string" && /session|conversation|message_?(limit|cap)|too_many_messages/.test(code)) return "session_limit";
  if (/new conversation/i.test(message)) return "session_limit";
  return "internal";
}

export function parseSearchHits(v: unknown): SearchHit[] {
  return Array.isArray(v) ? (v.filter((h) => isRecord(h) && typeof h.scheme_id === "string") as unknown as SearchHit[]) : [];
}

function updateLast(state: ChatState, fn: (m: AssistantMessage) => AssistantMessage): ChatState {
  const idx = state.messages.length - 1;
  const last = state.messages[idx];
  if (!last || last.role !== "assistant") return state;
  const messages = state.messages.slice();
  messages[idx] = fn(last);
  return { ...state, messages };
}

function applyEvent(m: AssistantMessage, ev: ChatEvent): AssistantMessage {
  switch (ev.type) {
    case "tool_call":
      return {
        ...m,
        activity: TOOL_ACTIVITY[ev.name] ?? "thinking",
        steps: [...m.steps, { id: ev.id, name: ev.name, args: ev.arguments }],
      };
    case "tool_result": {
      const failed = isRecord(ev.result) && typeof ev.result.error === "string";
      // Ids can repeat: resolve the first step with this id that has no result yet.
      const at = m.steps.findIndex((s) => s.id === ev.id && !("result" in s));
      const steps = m.steps.slice();
      if (at >= 0) steps[at] = { ...steps[at], result: ev.result, failed };
      // Result without a matching call (shouldn't happen): keep it visible anyway.
      else steps.push({ id: ev.id, name: ev.name, args: {}, result: ev.result, failed });
      const elig = ev.name === "check_eligibility" && !failed ? parseEligibility(ev.result) : null;
      return { ...m, steps, eligibility: elig ?? m.eligibility, activity: "thinking" };
    }
    case "token":
      return { ...m, text: m.text + ev.delta, activity: "writing" };
    case "answer":
      // The full answer is authoritative: it replaces whatever tokens built up.
      return { ...m, text: ev.content, activity: "writing" };
    case "suggestions":
      return { ...m, suggestions: ev.options.slice(0, 4) };
    case "done":
      return {
        ...m,
        streaming: false,
        activity: null,
        stats: { latency_s: ev.latency_s, llm_calls: ev.llm_calls, tokens: ev.tokens },
      };
    case "error":
      return { ...m, streaming: false, activity: null, error: { message: ev.message, code: normalizeErrorCode(ev.code, ev.message) } };
    default:
      return m;
  }
}

export function chatReducer(state: ChatState, action: ChatAction): ChatState {
  switch (action.type) {
    case "send":
      return {
        ...state,
        busy: true,
        messages: [
          ...state.messages,
          { id: action.userId, role: "user", text: action.text },
          newAssistant(action.assistantId),
        ],
      };
    case "event": {
      // Events for a message that is no longer streaming (late tokens after done, etc.) are ignored.
      const tail = state.messages[state.messages.length - 1];
      if (!tail || tail.role !== "assistant" || !tail.streaming) return state;
      if (action.event.type === "session") {
        const id = action.event.session_id;
        const n = state.messages.length;
        // The server answered with a different id than the one we sent: it forgot the conversation.
        const restarted = state.sessionId !== null && state.sessionId !== id && n > 2 && state.messages[n - 3].role !== "notice";
        // The first event ends the "waking up" status (the server is awake now).
        const awake = updateLast(state, (m) => (m.activity === "waking" ? { ...m, activity: "thinking" } : m));
        if (!restarted) return { ...awake, sessionId: id };
        const notice: NoticeMessage = { id: `notice-${tail.id}`, role: "notice", kind: "restarted" };
        return { ...awake, sessionId: id, messages: [...awake.messages.slice(0, n - 2), notice, ...awake.messages.slice(n - 2)] };
      }
      const next = updateLast(state, (m) => applyEvent(m, action.event));
      const finished = action.event.type === "done" || action.event.type === "error";
      return finished ? { ...next, busy: false } : next;
    }
    case "waking":
      return updateLast(state, (m) =>
        m.streaming && m.activity === "thinking" && !m.text && m.steps.length === 0 ? { ...m, activity: "waking" } : m,
      );
    case "fail": {
      const t = state.messages[state.messages.length - 1];
      if (!t || t.role !== "assistant" || !t.streaming) return { ...state, busy: false };
      return {
        ...updateLast(state, (m) => ({
          ...m,
          streaming: false,
          activity: null,
          error: { message: action.message, code: action.code, retryAfter: action.retryAfter },
        })),
        busy: false,
      };
    }
    case "end":
      return {
        ...updateLast(state, (m) =>
          m.streaming
            ? { ...m, streaming: false, activity: null, ...(action.stopped ? { stopped: true, suggestions: [] } : {}) }
            : m,
        ),
        busy: false,
      };
    case "discard_error": {
      const last = state.messages[state.messages.length - 1];
      if (!last || last.role !== "assistant" || !last.error) return state;
      // Remove the failed assistant message AND its user message so a retry re-adds both.
      return { ...state, messages: state.messages.slice(0, -2) };
    }
    case "reset":
      return initialChatState;
    case "restore":
      return { sessionId: action.sessionId, messages: action.messages, busy: false };
  }
}

/** Text of the last user message, for retry. */
export function lastUserText(state: ChatState): string | null {
  for (let i = state.messages.length - 1; i >= 0; i--) {
    const m = state.messages[i];
    if (m.role === "user") return m.text;
  }
  return null;
}
