import { API_URL, MOCK } from "./config";
import { readChatEvents } from "./sse";
import type { ChatEvent, LangCode, Scheme, UiErrorCode } from "./types";
import { parsePlan, type PlanResponse } from "./plan";
import { mockPlan } from "./mock/mock-plan";
import { mockChatResponse, mockGetScheme, mockListSchemes, mockResetSession } from "./mock/mock-backend";

export class ApiError extends Error {
  constructor(
    message: string,
    public code: UiErrorCode,
    public status?: number,
    public retryAfter?: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

/** HTTP status of a pre-stream failure -> UI error code. */
export function codeForStatus(status: number): UiErrorCode {
  if (status === 429) return "rate_limited"; // per-IP or global budget
  if (status === 409) return "busy"; // same session still streaming
  if (status === 413) return "too_large";
  if (status === 503) return "overloaded"; // server busy / global limit, usually with Retry-After
  if (status === 400 || status === 422) return "bad_request";
  return "internal";
}

export async function errorFromResponse(res: Response): Promise<ApiError> {
  let detail = "";
  try {
    const j: unknown = await res.json();
    if (typeof j === "object" && j !== null && "detail" in j) {
      const d = (j as { detail: unknown }).detail;
      detail = typeof d === "string" ? d : JSON.stringify(d);
    }
  } catch {
    /* body not JSON */
  }
  const code = codeForStatus(res.status);
  const ra = Number(res.headers.get("Retry-After"));
  return new ApiError(detail || `HTTP ${res.status}`, code, res.status, Number.isFinite(ra) && ra > 0 ? ra : undefined);
}

/** POST /api/chat and stream typed events. Throws ApiError on pre-stream failures. */
export async function* chatStream(
  message: string,
  sessionId: string | null,
  signal?: AbortSignal,
): AsyncGenerator<ChatEvent> {
  let res: Response;
  if (MOCK) {
    res = await mockChatResponse(message, sessionId, signal);
  } else {
    try {
      res = await fetch(`${API_URL}/api/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
        body: JSON.stringify(sessionId ? { session_id: sessionId, message } : { message }),
        signal,
      });
    } catch (e) {
      if (e instanceof DOMException && e.name === "AbortError") throw e;
      throw new ApiError("Network error", "network");
    }
  }
  if (!res.ok) throw await errorFromResponse(res);
  if (!res.body) throw new ApiError("Empty response", "internal");
  yield* readChatEvents(res.body);
}

async function getJson<T>(path: string): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, { headers: { Accept: "application/json" } });
  } catch {
    throw new ApiError("Network error", "network");
  }
  if (!res.ok) throw await errorFromResponse(res);
  return (await res.json()) as T;
}

export async function fetchSchemes(): Promise<Scheme[]> {
  return MOCK ? mockListSchemes() : getJson<Scheme[]>("/api/schemes");
}

export async function fetchScheme(id: string): Promise<Scheme> {
  if (MOCK) {
    const s = mockGetScheme(id);
    if (!s) throw new ApiError("Unknown scheme", "bad_request", 404);
    return s;
  }
  return getJson<Scheme>(`/api/schemes/${encodeURIComponent(id)}`);
}

let wakePinged = false;
/**
 * Free-tier hosts put idle servers to sleep (first request ~50 s). Called once per page load so the server is
 * already starting by the time the user types. Best effort: the result is ignored, errors are swallowed.
 */
export function wakeServer(): Promise<void> {
  if (MOCK || wakePinged) return Promise.resolve();
  wakePinged = true;
  return fetch(`${API_URL}/api/health`, { cache: "no-store" }).then(
    () => undefined,
    () => undefined,
  );
}

/** Test hook: allow wakeServer to fire again. */
export function _resetWakeServerForTests(): void {
  wakePinged = false;
}

/** Best effort; failures are ignored (the server expires sessions anyway). */
export async function resetSession(sessionId: string): Promise<void> {
  if (MOCK) return mockResetSession(sessionId);
  try {
    await fetch(`${API_URL}/api/session/reset`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: sessionId }),
    });
  } catch {
    /* ignore */
  }
}

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

/** POST /api/plan: documents, steps, warnings and where to go for the chosen schemes. */
export async function fetchPlan(
  schemeIds: string[],
  profile: Record<string, unknown> | undefined,
  lang: LangCode,
  signal?: AbortSignal,
): Promise<PlanResponse> {
  if (MOCK) {
    await sleep(700);
    if (signal?.aborted) throw new DOMException("Aborted", "AbortError");
    return mockPlan(schemeIds);
  }
  let res: Response;
  try {
    res = await fetch(`${API_URL}/api/plan`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify(profile && Object.keys(profile).length ? { scheme_ids: schemeIds, profile, lang } : { scheme_ids: schemeIds, lang }),
      signal,
    });
  } catch (e) {
    if (e instanceof DOMException && e.name === "AbortError") throw e;
    throw new ApiError("Network error", "network");
  }
  if (!res.ok) throw await errorFromResponse(res);
  const plan = parsePlan(await res.json());
  if (!plan) throw new ApiError("Unexpected plan response", "internal");
  return plan;
}

/** GET /api/schemes/{id}/apply: the raw apply record for one scheme. */
export async function fetchApplyRecord(id: string): Promise<unknown> {
  if (MOCK) {
    const s = mockGetScheme(id);
    if (!s) throw new ApiError("Unknown scheme", "bad_request", 404);
    return s;
  }
  return getJson<unknown>(`/api/schemes/${encodeURIComponent(id)}/apply`);
}
