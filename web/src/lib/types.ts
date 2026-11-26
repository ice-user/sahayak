/** Types mirroring docs/API.md (v1). */

export type LangCode = "en" | "hi" | "hinglish" | "ta";

export interface Rule {
  field: string;
  op: string;
  value: unknown;
  reason: string;
}

export interface Scheme {
  id: string;
  name: string;
  ministry?: string;
  category: string;
  summary: string;
  benefits: string;
  documents: string[];
  how_to_apply: string;
  source_url: string;
  tags: string[];
  aliases?: string[];
  caveats: string[];
  /** Only present on GET /api/schemes/{id}. */
  rules?: Rule[];
}

export interface EligibleItem {
  scheme_id: string;
  scheme_name: string;
  verdict: string;
  failed_reasons: string[];
  missing_fields: string[];
  caveats: string[];
  benefits: string;
  source_url: string;
}
export interface NeedInfoItem {
  scheme_id: string;
  scheme_name: string;
  missing_fields: string[];
}
export interface NotEligibleItem {
  scheme_id: string;
  /** Present from the newer backend; older servers send only scheme_id + reasons. */
  scheme_name?: string;
  reasons: string[];
  /** Present from the newer backend, e.g. "you may still be covered by regular PM-JAY". */
  caveats?: string[];
}
export interface EligibilityResult {
  eligible: EligibleItem[];
  need_info: NeedInfoItem[];
  not_eligible: NotEligibleItem[];
}
export interface SearchHit {
  scheme_id: string;
  name: string;
  summary: string;
  score: number;
}

export type ErrorCode = "rate_limited" | "bad_request" | "llm_error" | "internal" | "session_limit";

/**
 * Server codes plus failures detected client-side. "busy" = HTTP 409 (same session still streaming),
 * "too_large" = HTTP 413, "overloaded" = HTTP 503.
 */
export type UiErrorCode = ErrorCode | "busy" | "network" | "too_large" | "overloaded";

/** Events yielded by the SSE client, one per `event:` in the stream. */
export type ChatEvent =
  | { type: "session"; session_id: string }
  | { type: "tool_call"; id: string; name: string; arguments: Record<string, unknown> }
  | { type: "tool_result"; id: string; name: string; result: unknown }
  | { type: "token"; delta: string }
  | { type: "answer"; content: string }
  | { type: "suggestions"; options: string[] }
  | { type: "done"; latency_s: number; llm_calls: number; tokens: number }
  | { type: "error"; message: string; code: ErrorCode };
