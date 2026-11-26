import raw from "@/data/schemes.json";
import type { LangCode, Scheme } from "../types";
import { checkAll, type Facts } from "./rules";
import * as T from "./mock-text";
import { splitNeedInfo } from "../need-info";

/**
 * In-browser fake of the Sahayak backend, used when MOCK is on. It produces a
 * real SSE byte stream (split at arbitrary byte offsets) so the same parser
 * and reducer run as against the real server. Eligibility is computed by a
 * TypeScript port of the rule engine, so results are internally consistent.
 */

const ALL: Scheme[] = (raw as { schemes: Scheme[] }).schemes;

export function mockListSchemes(): Scheme[] {
  return ALL.map((s) => {
    const { rules, ...rest } = s;
    void rules;
    return rest as Scheme;
  });
}
export function mockGetScheme(id: string): Scheme | undefined {
  return ALL.find((s) => s.id === id);
}

interface MockSession {
  facts: Facts;
  asked: string | null;
  skipped: Set<string>;
  lang: LangCode;
  /** User messages so far (for the relevance filter). */
  history: string[];
}
const sessions = new Map<string, MockSession>();
const failedOnce = new Set<string>();

export function mockResetSession(id: string): void {
  sessions.delete(id);
}

// ---------- language + fact extraction ----------

export function detectLang(text: string, fallback: LangCode): LangCode {
  if (/[஀-௿]/.test(text)) return "ta";
  if (/[ऀ-ॿ]/.test(text)) return "hi";
  if (/\b(mujhe|meri|mere|mera|hai|hain|kya|nahi|nhi|chahiye|milegi|milega|saal|umar|beti|maa|mummy|ghar|haan|aur|kaise|bahut)\b/i.test(text)) return "hinglish";
  if (/[a-z]{3,}/i.test(text) && !/^(yes|no|not sure|\d+)$/i.test(text.trim())) return "en";
  return fallback;
}

const NEG = /\b(no|not|nahi|nhi|don'?t|doesn'?t|without|never)\b|नहीं|नही|இல்லை|இல்ல/i;
const YES_RE = /^\s*(yes|yeah|yep|haan|han|ha|ji)\b|^\s*(हाँ|हां|ஆம்)|\byes\b|हाँ,|हां,|ஆம்,/i;
const NO_RE = /^\s*(no|nope|nahi|nhi)\b|^\s*(नहीं|नही|இல்லை)|\bno\b/i;
const UNSURE = /not sure|don'?t know|pata nahi|पता नहीं|தெரியாது|தெரியலை/i;

const BOOL_FIELDS = [
  "bpl", "has_bank_account", "ever_income_tax_payer", "income_tax_payer_last_year", "owns_cultivable_land",
  "is_govt_employee", "household_has_lpg", "pregnant_or_lactating", "in_regular_govt_employment",
];

export function extractFacts(text: string, session: MockSession): { facts: Facts; unsure: boolean } {
  const f: Facts = {};
  const t = text.toLowerCase();

  const ageM =
    t.match(/(?:age|aged|umar|उम्र|வயது|வயசு)\D{0,6}(\d{1,3})/) ||
    t.match(/\b(?:i am|i'm|is|am|are)\s+(\d{1,3})\b(?!\s*(?:acres?|rs|rupees))/) ||
    t.match(/(\d{1,3})\s*(?:-|\s)?(?:years?|yrs?|yo|saal|sal|साल|वर्ष|वर्षीय|வயது|வயசு)(?!\w*\s*(?:old\s*)?(?:daughter|beti|बेटी|மகள்))/);
  const daughter =
    t.match(/(\d{1,2})\s*(?:-|\s)?(?:years?|yrs?|saal|साल|वर्ष|வயது)?\s*(?:-|\s)?(?:old\s*)?(?:daughter|beti|बेटी|மகள்)/) ||
    t.match(/(?:daughter|beti|बेटी|மகள்)\D{0,15}(\d{1,2})/);
  if (daughter) f.children = [{ gender: "female", age: Number(daughter[1]) }];
  if (ageM && !(daughter && ageM[1] === daughter[1])) f.age = Number(ageM[1]);
  if (session.asked === "age" && /^\s*\d{1,3}\s*$/.test(t)) f.age = Number(t);
  if (session.asked === "children.age/gender" && /^\s*\d{1,2}\s*$/.test(t)) f.children = [{ gender: "female", age: Number(t) }];

  if (/\b(widow|widowed|vidhwa)\b|विधवा|விதவை/.test(t)) {
    f.marital_status = "widowed";
    f.gender = "female";
  } else if (/\bmarried\b|विवाहित|திருமணமான/.test(t)) f.marital_status = "married";
  else if (/\bsingle\b|अविवाहित/.test(t)) f.marital_status = "single";

  if (/\b(mother|mom|mummy|wife|woman|women|she|her|lady|mahila|maa|beti|daughter)\b|महिला|माँ|मां|पत्नी|பெண்|அம்மா|மனைவி/.test(t)) f.gender ??= "female";
  else if (/\b(father|dad|man|male|husband|he|his|purush|papa)\b|पुरुष|पिता|पापा|ஆண்|அப்பா/.test(t)) f.gender ??= "male";
  if (session.asked === "gender") {
    if (/woman|mahila|महिला|பெண்/.test(t)) f.gender = "female";
    else if (/\bman\b|purush|पुरुष|ஆண்/.test(t)) f.gender = "male";
  }

  if (/pregnan|lactating|breastfeed|garbhvati|गर्भवती|கர்ப்ப/.test(t)) {
    f.pregnant_or_lactating = true;
    f.gender = "female";
  }
  if (/\bbpl\b|बीपीएल|பிபிஎல்|below poverty/.test(t)) f.bpl = !NEG.test(t.replace(/not sure/, ""));
  if (/bank account|post office account|बैंक|खाता|வங்கி|account/.test(t)) f.has_bank_account = !NEG.test(t);
  if (/income tax|tax ?payer|आयकर|வருமான வரி/.test(t)) {
    f.ever_income_tax_payer = !NEG.test(t);
    f.income_tax_payer_last_year = !NEG.test(t);
  }
  if (/farmer|kisan|farmland|farm land|cultivable|किसान|खेत|ज़मीन|विवसाय|விவசாய|நிலம்/.test(t)) f.owns_cultivable_land = !NEG.test(t);
  if (/\blpg\b|gas connection|एलपीजी|எல்பிஜி/.test(t)) f.household_has_lpg = !NEG.test(t);

  // Reply to the question we asked last: plain yes / no.
  const unsure = UNSURE.test(t);
  if (session.asked && BOOL_FIELDS.includes(session.asked) && !(session.asked in f) && !unsure) {
    if (NO_RE.test(t) && !YES_RE.test(t)) f[session.asked] = false;
    else if (YES_RE.test(t)) f[session.asked] = true;
  }
  if (session.asked === "monthly_pension") {
    const n = t.match(/(\d[\d,]*)/);
    if (n) f.monthly_pension = Number(n[1].replace(/,/g, ""));
    else if (NO_RE.test(t) || /less than|below|कम|குறைவு/.test(t)) f.monthly_pension = /less than|below|कम|குறைவு/.test(t) ? 5000 : 0;
  }
  // "no tax / no govt job" style answers for govt-employee questions
  return { facts: f, unsure };
}

// ---------- fake search ----------

const INTENTS: { re: RegExp; ids: string[]; q: string }[] = [
  { re: /widow|vidhwa|विधवा|விதவை/, ids: ["ignwps"], q: "widow pension" },
  { re: /pension|पेंशन|ஓய்வூதிய|vridha|budhapa|old age|elderly|बुजुर्ग|वृद्ध|முதியோர்/, ids: ["ignoaps", "ignwps", "apy"], q: "old age pension" },
  { re: /farmer|kisan|किसान|விவசாய|kheti|खेती/, ids: ["pm_kisan"], q: "farmer income support" },
  { re: /\blpg\b|\bgas\b|cylinder|गैस|சிலிண்டர்|எரிவாயு/, ids: ["pmuy"], q: "free LPG connection" },
  { re: /daughter|beti|बेटी|मகள்|மகள்|girl/, ids: ["ssy"], q: "girl child savings" },
  { re: /pregnan|garbhvati|गर्भवती|கர்ப்ப|maternity/, ids: ["pmmvy"], q: "maternity benefit" },
  { re: /insurance|bima|बीमा|காப்பீடு/, ids: ["pmjjby", "pmsby"], q: "life and accident insurance" },
  { re: /health|hospital|ayushman|इलाज|अस्पताल|आयुष्मान|மருத்துவ|சிகிச்சை/, ids: ["pmjay_senior"], q: "health cover for elderly" },
];

function fakeSearch(text: string, facts: Facts) {
  const t = text.toLowerCase();
  const hits = new Map<string, number>();
  const queries: string[] = [];
  for (const it of INTENTS) {
    if (it.re.test(t)) {
      queries.push(it.q);
      it.ids.forEach((id, i) => hits.set(id, Math.max(hits.get(id) ?? 0, 0.92 - i * 0.12)));
    }
  }
  if (hits.size === 0 && typeof facts.age === "number") {
    const a = facts.age as number;
    queries.push("schemes for senior citizens");
    if (a >= 60) ["ignoaps", "pmjay_senior"].forEach((id, i) => hits.set(id, 0.8 - i * 0.1));
    else ["apy", "pmsby"].forEach((id, i) => hits.set(id, 0.7 - i * 0.1));
  }
  const results = [...hits.entries()]
    .sort((a, b) => b[1] - a[1])
    .slice(0, 5)
    .map(([id, score]) => {
      const s = ALL.find((x) => x.id === id)!;
      return { scheme_id: id, name: s.name, summary: s.summary, score: Math.round(score * 100) / 100 };
    });
  return { query: queries[0] ?? text.slice(0, 60), results };
}

// ---------- answer + suggestions ----------

const FIELD_PRIORITY = ["age", "gender", "marital_status", "bpl", "pregnant_or_lactating", "has_bank_account",
  "owns_cultivable_land", "household_has_lpg", "income_tax_payer_last_year", "ever_income_tax_payer", "is_govt_employee",
  "in_regular_govt_employment", "monthly_pension", "children.age/gender", "children"];

function suggestionsFor(field: string, lang: LangCode): string[] {
  if (field === "bpl") return [T.BPL_YES[lang], T.BPL_NO[lang], T.NOT_SURE[lang]];
  if (field === "gender") return T.GENDER_OPTS.map((o) => o[lang]);
  if (field === "marital_status") return T.MARITAL_OPTS.map((o) => o[lang]);
  if (BOOL_FIELDS.includes(field)) return [T.YES[lang], T.NO[lang], T.NOT_SURE[lang]];
  if (field === "monthly_pension") return [T.NO[lang] + " pension".replace(" pension", lang === "en" ? " pension" : ""), T.NOT_SURE[lang]];
  return [];
}

const firstSentence = (s: string) => s.split(/(?<=[.])\s/)[0];

// ---------- SSE helpers ----------

const sleep = (ms: number, signal?: AbortSignal) =>
  new Promise<void>((resolve) => {
    if (signal?.aborted) return resolve();
    const id = setTimeout(resolve, ms);
    signal?.addEventListener("abort", () => { clearTimeout(id); resolve(); }, { once: true });
  });

const sse = (event: string, data: unknown) => `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;

/** Split an encoded event at an arbitrary byte offset to exercise the parser. */
function splitBytes(bytes: Uint8Array, at: number): Uint8Array[] {
  const cut = Math.max(1, Math.min(bytes.length - 1, at));
  return bytes.length < 4 ? [bytes] : [bytes.slice(0, cut), bytes.slice(cut)];
}

let counter = 0;

export async function mockChatResponse(message: string, sessionId: string | null, signal?: AbortSignal): Promise<Response> {
  await sleep(250, signal);
  const lower = message.toLowerCase();

  if (lower.includes("mock:ratelimit") && !failedOnce.has(message)) {
    failedOnce.add(message);
    return new Response(JSON.stringify({ detail: "Rate limit exceeded: 20 requests per 10 minutes." }), {
      status: 429,
      headers: { "Content-Type": "application/json", "Retry-After": "540" },
    });
  }

  if (lower.includes("mock:busy") && !failedOnce.has(message)) {
    failedOnce.add(message);
    return new Response(JSON.stringify({ detail: "A reply is already being generated for this session." }), {
      status: 409,
      headers: { "Content-Type": "application/json" },
    });
  }

  if (lower.includes("mock:toolarge") && !failedOnce.has(message)) {
    failedOnce.add(message);
    return new Response(JSON.stringify({ detail: "Request body too large." }), { status: 413, headers: { "Content-Type": "application/json" } });
  }

  if (lower.includes("mock:overloaded") && !failedOnce.has(message)) {
    failedOnce.add(message);
    return new Response(JSON.stringify({ detail: "Server is busy. Please try again shortly." }), {
      status: 503,
      headers: { "Content-Type": "application/json", "Retry-After": "30" },
    });
  }

  // Simulates the server having forgotten the conversation (expiry or restart): the id is unknown, so a new one is made.
  if (lower.includes("mock:expire") && sessionId) sessions.delete(sessionId);

  const sid = sessionId && sessions.has(sessionId) ? sessionId : `mock${(++counter).toString(36)}${Math.random().toString(36).slice(2, 8)}`;
  if (!sessions.has(sid)) sessions.set(sid, { facts: {}, asked: null, skipped: new Set(), lang: "en", history: [] });
  const session = sessions.get(sid)!;
  const failNow = lower.includes("mock:error") && !failedOnce.has(message);
  if (failNow) failedOnce.add(message);

  const sessionLimit = lower.includes("mock:sessionlimit");
  const clean = message.replace(/mock:(error|ratelimit|busy|toolarge|overloaded|expire|sessionlimit)/gi, "").trim() || message;
  const lang = detectLang(clean, session.lang);
  session.lang = lang;
  session.history.push(clean);
  const history = session.history;
  const { facts, unsure } = extractFacts(clean, session);
  if (unsure && session.asked) session.skipped.add(session.asked);
  session.facts = { ...session.facts, ...facts };
  const asked = session.asked;
  void asked;

  const enc = new TextEncoder();
  let cancelled = false;
  signal?.addEventListener("abort", () => { cancelled = true; }, { once: true });

  const stream = new ReadableStream<Uint8Array>({
    async start(controller) {
      const t0 = Date.now();
      const push = async (event: string, data: unknown, delay = 0) => {
        if (delay) await sleep(delay, signal);
        if (cancelled) return;
        const bytes = enc.encode(sse(event, data));
        for (const part of splitBytes(bytes, Math.floor(bytes.length * 0.6))) controller.enqueue(part);
      };
      try {
        await push("session", { session_id: sid });
        if (sessionLimit) {
          await push("error", { message: "This conversation has reached its message limit. Please start a new conversation.", code: "session_limit" }, 200);
          controller.close();
          return;
        }

        const hasFacts = Object.keys(session.facts).length > 0;
        let calls = 0;

        if (!hasFacts) {
          const q = fakeSearch(clean, session.facts);
          await push("tool_call", { id: "call_1", name: "search_schemes", arguments: { query: q.query, top_k: 5 } }, 400);
          await push("tool_result", { id: "call_1", name: "search_schemes", result: q.results }, 700);
          calls = 2;
          if (failNow) { await push("error", { message: T.TEXT.errorLlm.en, code: "llm_error" }, 300); controller.close(); return; }
          session.asked = "age";
          await streamAnswer(T.TEXT.askFirst[lang], [], push, signal, () => cancelled);
          await push("done", { latency_s: (Date.now() - t0) / 1000, llm_calls: calls, tokens: 420 });
          controller.close();
          return;
        }

        const search = fakeSearch(clean, session.facts);
        await push("tool_call", { id: "call_1", name: "search_schemes", arguments: { query: search.query, top_k: 5 } }, 450);
        await push("tool_result", { id: "call_1", name: "search_schemes", result: search.results }, 650);
        if (failNow) { await push("error", { message: T.TEXT.errorLlm.en, code: "llm_error" }, 400); controller.close(); return; }

        await push("tool_call", { id: "call_2", name: "check_eligibility", arguments: { profile: session.facts } }, 350);
        const result = checkAll(session.facts, ALL);
        await push("tool_result", { id: "call_2", name: "check_eligibility", result }, 800);
        calls = 3;

        // Next question: highest-priority missing field not yet skipped.
        // Ask about the plausible schemes first (same filter as the UI), so a 62-year-old is not asked about pregnancy.
        const askable = splitNeedInfo(result.need_info, session.facts, history.join(" ")).primary;
        const missing = new Set(askable.flatMap((n) => n.missing_fields));
        const next = FIELD_PRIORITY.find((f) => missing.has(f) && !session.skipped.has(f)) ?? null;
        session.asked = next;

        const parts: string[] = [];
        if (result.eligible.length) {
          parts.push(T.TEXT.eligibleHead[lang].replace("{n}", String(result.eligible.length)));
          parts.push(result.eligible.map((e) => `- **${e.scheme_name}**: ${firstSentence(e.benefits)}`).join("\n"));
        } else parts.push(T.TEXT.noneYet[lang]);
        if (result.need_info.length && next) {
          parts.push(T.TEXT.needMore[lang].replace("{n}", String(result.need_info.length)).replace("{q}", (T.QUESTIONS[next] ?? T.QUESTIONS.age)[lang]));
        }
        if (result.not_eligible.length) parts.push(T.TEXT.notEligible[lang].replace("{n}", String(result.not_eligible.length)));
        parts.push(T.TEXT.closing[lang]);

        await streamAnswer(parts.join("\n\n"), next ? suggestionsFor(next, lang) : [], push, signal, () => cancelled);
        await push("done", { latency_s: Math.round((Date.now() - t0) / 100) / 10, llm_calls: calls - 1, tokens: 1200 + Math.floor(Math.random() * 600) });
        controller.close();
      } catch {
        try { controller.close(); } catch { /* already closed */ }
      }
    },
    cancel() { cancelled = true; },
  });

  return new Response(stream, { status: 200, headers: { "Content-Type": "text/event-stream" } });
}

async function streamAnswer(
  text: string,
  suggestions: string[],
  push: (e: string, d: unknown, delay?: number) => Promise<void>,
  signal: AbortSignal | undefined,
  isCancelled: () => boolean,
) {
  // Token deltas split on spaces; the final `answer` event repeats the full text.
  const chunks = text.match(/\S+\s*|\n+/g) ?? [text];
  let i = 0;
  while (i < chunks.length && !isCancelled()) {
    const take = Math.min(2, chunks.length - i);
    await push("token", { delta: chunks.slice(i, i + take).join("") }, 28);
    i += take;
  }
  await push("answer", { content: text }, 60);
  if (suggestions.length) await push("suggestions", { options: suggestions.slice(0, 4) }, 80);
  void signal;
}
