import { parseEligibility, type ChatMessage } from "./chat-state";

/** Bump when the stored message shape changes; mismatching entries are dropped. */
export const STORAGE_VERSION = 1;
export const STORAGE_KEY = "sahayak.chat";
/** The server drops sessions after 30 minutes idle; stay well inside that. */
export const MAX_AGE_MS = 25 * 60 * 1000;

export interface StoredChat {
  sessionId: string | null;
  messages: ChatMessage[];
}

const isRecord = (v: unknown): v is Record<string, unknown> => typeof v === "object" && v !== null && !Array.isArray(v);
const isStr = (v: unknown): v is string => typeof v === "string";
const isStrArray = (v: unknown): v is string[] => Array.isArray(v) && v.every(isStr);

function validMessage(m: unknown): m is ChatMessage {
  if (!isRecord(m) || !isStr(m.id)) return false;
  if (m.role === "user") return isStr(m.text);
  if (m.role === "notice") return m.kind === "restarted";
  if (m.role !== "assistant") return false;
  if (!isStr(m.text) || typeof m.streaming !== "boolean" || !isStrArray(m.suggestions)) return false;
  if (!(m.activity === null || isStr(m.activity))) return false;
  if (!Array.isArray(m.steps) || !m.steps.every((s) => isRecord(s) && isStr(s.id) && isStr(s.name) && isRecord(s.args))) return false;
  if (m.eligibility !== null && parseEligibility(m.eligibility) === null) return false;
  if (m.error !== null && !(isRecord(m.error) && isStr(m.error.message) && isStr(m.error.code))) return false;
  if (m.stats !== null && !(isRecord(m.stats) && typeof m.stats.latency_s === "number")) return false;
  return true;
}

/**
 * Parses a stored conversation. Returns null (drop it) on any mismatch: bad JSON, other version,
 * wrong shape, or older than MAX_AGE_MS. Eligibility results are re-normalised on the way in.
 */
export function parseStored(raw: string | null, now: number = Date.now()): StoredChat | null {
  if (!raw) return null;
  let v: unknown;
  try {
    v = JSON.parse(raw);
  } catch {
    return null;
  }
  if (!isRecord(v) || v.v !== STORAGE_VERSION) return null;
  if (typeof v.savedAt !== "number" || now - v.savedAt > MAX_AGE_MS || v.savedAt > now + 60_000) return null;
  if (!(v.sessionId === null || isStr(v.sessionId))) return null;
  if (!Array.isArray(v.messages) || !v.messages.every(validMessage)) return null;
  const messages = (v.messages as ChatMessage[]).map((m) =>
    m.role === "assistant" && m.eligibility ? { ...m, eligibility: parseEligibility(m.eligibility) } : m,
  );
  if (!v.sessionId && messages.length === 0) return null;
  return { sessionId: v.sessionId as string | null, messages };
}

export function serializeStored(chat: StoredChat, now: number = Date.now()): string {
  return JSON.stringify({ v: STORAGE_VERSION, savedAt: now, sessionId: chat.sessionId, messages: chat.messages });
}
