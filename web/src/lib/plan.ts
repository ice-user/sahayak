import type { Dict } from "./i18n/types";
import { safeHttpUrl } from "./safe-url";

/** Types for POST /api/plan, plus pure helpers (checklist persistence, ordering, sharing). */

export interface HowToGet {
  text: string;
  source_url: string | null;
}
export interface PlanDoc {
  doc: string;
  name: string;
  needed_for: string[];
  mandatory: boolean;
  how_to_get: HowToGet | null;
}
/** "Any one of" documents: satisfied when one option is ticked. */
export interface PlanDocGroup {
  doc_group: string;
  label: string;
  options: PlanDoc[];
  needed_for: string[];
  mandatory: boolean;
}
export type PlanChecklistItem = PlanDoc | PlanDocGroup;
export const isDocGroup = (d: PlanChecklistItem): d is PlanDocGroup => "doc_group" in d;

export interface RouteStep {
  n: number;
  action: string;
  where: string;
  mode: "online" | "offline";
  source_url: string | null;
}
export interface PlanRoute {
  mode: "online" | "offline";
  summary: string;
  where: string | null;
  recommended: boolean;
  steps: RouteStep[];
}
/** One scheme with its alternative ways to apply (exactly one route is recommended). */
export interface PlanScheme {
  scheme_id: string;
  scheme_name: string;
  source_url: string | null;
  /** False when the data comes from a non-government site: the UI says to verify at the post office or bank. */
  source_official: boolean;
  recommended_mode: "online" | "offline" | null;
  routes: PlanRoute[];
}
export interface PlanStep {
  /** First scheme (kept for compatibility); a merged step lists every scheme in `scheme_ids` / `scheme_names`. */
  scheme_id: string;
  scheme_name: string;
  scheme_ids: string[];
  scheme_names: string[];
  n: number;
  action: string;
  where: string;
  mode: "online" | "offline";
  source_url: string | null;
  source_urls: string[];
  group_kind: string;
  group: string;
}
export interface WatchOut {
  scheme_id: string;
  /** Every scheme that has this (merged) warning. */
  scheme_ids?: string[];
  kind: string;
  text: string;
  quote: string | null;
  personal: boolean | null;
}
export interface EnrolPoint {
  type: string;
  name: string;
  locator_url: string | null;
  quote: string | null;
}
export interface Grievance {
  text: string;
  url_or_number: string;
  quote: string | null;
}
export interface WhereToGo {
  scheme_id: string;
  scheme_name: string;
  enrol_points: EnrolPoint[];
  grievance: Grievance | null;
  helpline: string | null;
  portal_url: string | null;
  office: string | null;
}
export interface EnrolGroup {
  type: string;
  scheme_ids: string[];
  points: { name: string; locator_url: string | null; scheme_ids: string[] }[];
}
export interface PlanResponse {
  lang: string;
  checklist: PlanChecklistItem[];
  schemes: PlanScheme[];
  steps: PlanStep[];
  watch_outs: WatchOut[];
  where_to_go: WhereToGo[];
  enrol_groups: EnrolGroup[];
  summary: Record<string, unknown>;
  sources: unknown[];
}

const isRecord = (v: unknown): v is Record<string, unknown> => typeof v === "object" && v !== null && !Array.isArray(v);
const str = (v: unknown): string => (typeof v === "string" ? v : "");
const strOrNull = (v: unknown): string | null => (typeof v === "string" && v.trim() ? v : null);
const arr = (v: unknown): unknown[] => (Array.isArray(v) ? v : []);

/** Defensive normaliser for the backend response; returns null when it is not plan-shaped at all. */
export function parsePlan(raw: unknown): PlanResponse | null {
  if (!isRecord(raw) || !Array.isArray(raw.checklist) || !Array.isArray(raw.steps)) return null;
  const strs = (v: unknown) => arr(v).filter((x): x is string => typeof x === "string" && x !== "");
  const parseDoc = (d: unknown): PlanDoc | null => {
    if (!isRecord(d) || !str(d.doc)) return null;
    const h = isRecord(d.how_to_get) ? d.how_to_get : null;
    return {
      doc: str(d.doc),
      name: str(d.name) || str(d.doc),
      needed_for: strs(d.needed_for),
      mandatory: d.mandatory !== false,
      how_to_get: h && str(h.text) ? { text: str(h.text), source_url: strOrNull(h.source_url) } : null,
    };
  };
  const checklist: PlanChecklistItem[] = [];
  for (const d of raw.checklist) {
    if (isRecord(d) && str(d.doc_group)) {
      const options = arr(d.options).map(parseDoc).filter((o): o is PlanDoc => o !== null);
      if (!options.length) continue;
      checklist.push({
        doc_group: str(d.doc_group),
        label: str(d.label) || options.map((o) => o.name).join(" / "),
        options,
        needed_for: strs(d.needed_for),
        mandatory: d.mandatory !== false,
      });
      continue;
    }
    const doc = parseDoc(d);
    if (doc) checklist.push(doc);
  }
  const schemes: PlanScheme[] = [];
  for (const c of arr(raw.schemes)) {
    if (!isRecord(c) || !str(c.scheme_id)) continue;
    const routes: PlanRoute[] = [];
    for (const r of arr(c.routes)) {
      if (!isRecord(r)) continue;
      const rsteps: RouteStep[] = [];
      for (const st of arr(r.steps)) {
        if (!isRecord(st) || !str(st.action)) continue;
        rsteps.push({
          n: typeof st.n === "number" ? st.n : rsteps.length + 1,
          action: str(st.action),
          where: str(st.where),
          mode: st.mode === "online" ? "online" : "offline",
          source_url: strOrNull(st.source_url),
        });
      }
      if (!rsteps.length) continue;
      const mode = r.mode === "online" ? "online" : "offline";
      routes.push({ mode, summary: str(r.summary) || rsteps[0].action, where: strOrNull(r.where), recommended: r.recommended === true, steps: rsteps });
    }
    // Exactly one recommended route: keep the backend's choice, else the first (online first).
    if (routes.length && routes.filter((r) => r.recommended).length !== 1) routes.forEach((r, i) => (r.recommended = i === 0));
    schemes.push({
      scheme_id: str(c.scheme_id),
      scheme_name: str(c.scheme_name) || str(c.scheme_id),
      source_url: strOrNull(c.source_url),
      source_official: c.source_official !== false,
      recommended_mode: routes.find((r) => r.recommended)?.mode ?? null,
      routes,
    });
  }
  const steps: PlanStep[] = [];
  for (const s of raw.steps) {
    if (!isRecord(s) || !str(s.action)) continue;
    const scheme_ids = strs(s.scheme_ids);
    const scheme_names = strs(s.scheme_names);
    if (!scheme_ids.length && str(s.scheme_id)) scheme_ids.push(str(s.scheme_id));
    if (!scheme_names.length && str(s.scheme_name)) scheme_names.push(str(s.scheme_name));
    const source_urls = strs(s.source_urls);
    if (!source_urls.length && strOrNull(s.source_url)) source_urls.push(str(s.source_url));
    steps.push({
      scheme_id: str(s.scheme_id) || scheme_ids[0] || "",
      scheme_name: str(s.scheme_name) || scheme_names[0] || "",
      scheme_ids,
      scheme_names,
      n: typeof s.n === "number" ? s.n : steps.length + 1,
      action: str(s.action),
      where: str(s.where),
      mode: s.mode === "online" ? "online" : "offline",
      source_url: strOrNull(s.source_url),
      source_urls,
      group_kind: str(s.group_kind),
      group: str(s.group),
    });
  }
  const enrol_groups: EnrolGroup[] = [];
  for (const g of arr(raw.enrol_groups)) {
    if (!isRecord(g)) continue;
    const ids = (v: unknown) => arr(v).filter((x): x is string => typeof x === "string");
    enrol_groups.push({
      type: str(g.type),
      scheme_ids: ids(g.scheme_ids),
      points: arr(g.points)
        .filter(isRecord)
        .map((p) => ({ name: str(p.name), locator_url: strOrNull(p.locator_url), scheme_ids: ids(p.scheme_ids) })),
    });
  }
  const watch_outs: WatchOut[] = [];
  for (const w of arr(raw.watch_outs)) {
    if (!isRecord(w) || !str(w.text)) continue;
    watch_outs.push({
      scheme_id: str(w.scheme_id),
      scheme_ids: strs(w.scheme_ids).length ? strs(w.scheme_ids) : str(w.scheme_id) ? [str(w.scheme_id)] : [],
      kind: str(w.kind),
      text: str(w.text),
      quote: strOrNull(w.quote),
      personal: typeof w.personal === "boolean" ? w.personal : null,
    });
  }
  const where_to_go: WhereToGo[] = [];
  for (const w of arr(raw.where_to_go)) {
    if (!isRecord(w)) continue;
    const g = isRecord(w.grievance) && str(w.grievance.text) ? w.grievance : null;
    where_to_go.push({
      scheme_id: str(w.scheme_id),
      scheme_name: str(w.scheme_name) || str(w.scheme_id),
      enrol_points: arr(w.enrol_points)
        .filter(isRecord)
        .map((p) => ({ type: str(p.type), name: str(p.name), locator_url: strOrNull(p.locator_url), quote: strOrNull(p.quote) })),
      grievance: g ? { text: str(g.text), url_or_number: str(g.url_or_number), quote: strOrNull(g.quote) } : null,
      helpline: strOrNull(w.helpline),
      portal_url: strOrNull(w.portal_url),
      office: strOrNull(w.office),
    });
  }
  return {
    lang: str(raw.lang),
    checklist,
    schemes,
    steps,
    watch_outs,
    where_to_go,
    enrol_groups,
    summary: isRecord(raw.summary) ? raw.summary : {},
    sources: arr(raw.sources),
  };
}

/** Same set of schemes -> same plan, whatever order they were passed in. */
export function planId(schemeIds: string[]): string {
  return [...new Set(schemeIds)].sort().join(",");
}

// ---------- checklist persistence (localStorage, per plan) ----------

export const CHECKLIST_PREFIX = "sahayak.plan.docs.v1:";

type StorageLike = Pick<Storage, "getItem" | "setItem">;

function defaultStorage(): StorageLike | null {
  try {
    return typeof localStorage === "undefined" ? null : localStorage;
  } catch {
    return null;
  }
}

/** Ticked document ids for a plan. Bad or missing data gives an empty list. */
export function loadChecked(id: string, storage: StorageLike | null = defaultStorage()): string[] {
  if (!storage) return [];
  try {
    const v: unknown = JSON.parse(storage.getItem(CHECKLIST_PREFIX + id) ?? "null");
    return Array.isArray(v) ? [...new Set(v.filter((x): x is string => typeof x === "string"))] : [];
  } catch {
    return [];
  }
}

export function saveChecked(id: string, checked: string[], storage: StorageLike | null = defaultStorage()): void {
  if (!storage) return;
  try {
    storage.setItem(CHECKLIST_PREFIX + id, JSON.stringify(checked));
  } catch {
    /* storage full or blocked: the checklist still works for this visit */
  }
}

export function toggleChecked(checked: string[], doc: string): string[] {
  return checked.includes(doc) ? checked.filter((d) => d !== doc) : [...checked, doc];
}

/** Radio-style choice inside an "any one of" group: picking an option clears the others; picking it again clears it. */
export function pickOption(checked: string[], group: PlanDocGroup, doc: string): string[] {
  const others = new Set(group.options.map((o) => o.doc).filter((d) => d !== doc));
  const rest = checked.filter((d) => !others.has(d));
  return rest.includes(doc) ? rest.filter((d) => d !== doc) : [...rest, doc];
}

/** A plain document is ready when ticked; a group when any one of its options is. */
export function isReady(item: PlanChecklistItem, checked: string[]): boolean {
  const set = new Set(checked);
  return isDocGroup(item) ? item.options.some((o) => set.has(o.doc)) : set.has(item.doc);
}

/** Progress counts checklist rows (a group is one row); stale ticks are ignored. */
export function progressOf(checklist: PlanChecklistItem[], checked: string[]): { have: number; total: number; ratio: number } {
  const total = checklist.length;
  const have = checklist.filter((d) => isReady(d, checked)).length;
  return { have, total, ratio: total === 0 ? 0 : have / total };
}

// ---------- ordering ----------

const personalRank = (p: boolean | null) => (p === true ? 0 : p === null ? 1 : 2);

/** Watch-outs that apply to the user first, then unknown, then general. Stable inside each group. */
export function orderWatchOuts(items: WatchOut[]): WatchOut[] {
  return items
    .map((w, i) => ({ w, i }))
    .sort((a, b) => personalRank(a.w.personal) - personalRank(b.w.personal) || a.i - b.i)
    .map((x) => x.w);
}

const stepRank = (s: PlanStep) => (s.group_kind === "prepare" ? 0 : s.mode === "offline" ? 2 : 1);

/** Preparation first, then online steps, then office visits; original order kept inside each group. */
export function orderSteps(steps: PlanStep[]): PlanStep[] {
  return steps
    .map((s, i) => ({ s, i }))
    .sort((a, b) => stepRank(a.s) - stepRank(b.s) || a.i - b.i)
    .map((x) => x.s);
}

// ---------- where to go ----------

export type TripKey = "bank" | "post_office" | "csc" | "panchayat" | "hospital" | "online" | "office" | "other";

export function tripKey(type: string): TripKey {
  const t = type.toLowerCase();
  if (/post/.test(t)) return "post_office";
  if (/bank/.test(t)) return "bank";
  if (/\bcsc\b|common service|jan seva/.test(t)) return "csc";
  if (/panchayat|gram/.test(t)) return "panchayat";
  if (/hospital|health|clinic|phc/.test(t)) return "hospital";
  if (/online|portal|web|app|digital/.test(t)) return "online";
  if (/office|block|tehsil|collectorate|department/.test(t)) return "office";
  return "other";
}

export interface Trip {
  key: TripKey;
  schemes: { id: string; name: string }[];
  /** Places to go; each may have its own "find nearest" link. */
  points: { name: string; locatorUrl: string | null }[];
}

/**
 * One trip per place type, covering every scheme that can be done there. Uses the backend's `enrol_groups`
 * (largest first) and falls back to grouping `where_to_go` locally when they are absent.
 */
export function tripsOf(plan: Pick<PlanResponse, "where_to_go" | "enrol_groups" | "steps">): Trip[] {
  const names = new Map<string, string>();
  for (const w of plan.where_to_go) names.set(w.scheme_id, w.scheme_name);
  for (const s of plan.steps) s.scheme_ids.forEach((id, i) => { if (!names.has(id) && s.scheme_names[i]) names.set(id, s.scheme_names[i]); });
  const nameOf = (id: string) => names.get(id) ?? id;

  if (plan.enrol_groups.length) {
    return plan.enrol_groups.map((g) => ({
      key: tripKey(g.type),
      schemes: g.scheme_ids.map((id) => ({ id, name: nameOf(id) })),
      points: g.points.map((p) => ({ name: p.name, locatorUrl: safeHttpUrl(p.locator_url) })),
    }));
  }
  const map = new Map<TripKey, Trip>();
  for (const w of plan.where_to_go) {
    for (const p of w.enrol_points) {
      const key = tripKey(p.type || p.name);
      const trip = map.get(key) ?? { key, schemes: [], points: [] };
      map.set(key, trip);
      if (!trip.schemes.some((x) => x.id === w.scheme_id)) trip.schemes.push({ id: w.scheme_id, name: w.scheme_name });
      if (p.name && !trip.points.some((x) => x.name === p.name)) trip.points.push({ name: p.name, locatorUrl: safeHttpUrl(p.locator_url) });
    }
  }
  return [...map.values()].sort((a, b) => b.schemes.length - a.schemes.length);
}

/** Digits (and a leading +) when the text looks like a phone or helpline number, else null. */
export function phoneOf(text: string | null | undefined): string | null {
  if (!text) return null;
  const m = text.trim().match(/^(?:tel:)?(\+?[\d][\d\s\-()]{2,})(?:\s*\(.*\))?$/i);
  if (!m) return null;
  const digits = m[1].replace(/[^\d+]/g, "");
  return digits.replace(/\D/g, "").length >= 3 ? digits : null;
}

// ---------- sharing ----------

const MAX_SHARE = 1400;

/** Short plain-text plan for WhatsApp, in the UI language. */
export function buildShareText(plan: PlanResponse, t: Dict, checked: string[], url?: string): string {
  const names = plan.schemes.length ? plan.schemes.map((c) => c.scheme_name) : [...new Set(plan.steps.flatMap((s) => s.scheme_names).filter(Boolean))];
  const lines: string[] = [t.plan.shareHead(names.length || 1)];
  if (names.length) lines.push(names.map((n) => `• ${n}`).join("\n"));
  if (plan.checklist.length) {
    lines.push("", t.plan.shareDocs);
    for (const d of plan.checklist) {
      const label = isDocGroup(d) ? `${d.label}: ${d.options.map((o) => o.name).join(" / ")}` : d.name;
      lines.push(`${isReady(d, checked) ? "✅" : "⬜"} ${label}`);
    }
  }
  const recommended = plan.schemes.flatMap((c) => {
    const r = c.routes.find((x) => x.recommended);
    return r ? [`${c.scheme_name}: ${r.summary}${r.where ? ` (${r.where})` : ""}`] : [];
  });
  const prepare = plan.steps.filter((s) => s.group_kind === "prepare").map((s) => s.action);
  const steps = recommended.length ? [...prepare, ...recommended] : orderSteps(plan.steps).map((s) => `${s.action}${s.where ? ` (${s.where})` : ""}`);
  if (steps.length) {
    lines.push("", t.plan.shareSteps);
    steps.forEach((x, i) => lines.push(`${i + 1}. ${x}`));
  }
  const careful = orderWatchOuts(plan.watch_outs).slice(0, 3);
  if (careful.length) {
    lines.push("", t.plan.shareCareful);
    for (const w of careful) lines.push(`⚠️ ${w.text}`);
  }
  lines.push("", t.plan.shareFoot);
  if (url) lines.push(url);
  const text = lines.join("\n");
  return text.length <= MAX_SHARE ? text : `${text.slice(0, MAX_SHARE - 1)}…`;
}

export function whatsappLink(text: string): string {
  return `https://wa.me/?text=${encodeURIComponent(text)}`;
}

// ---------- hand-over from chat to the /plan page ----------

const PROFILE_KEY = "sahayak.plan.profile";

/** The facts the chat used, kept for the plan page (tab-scoped, never leaves the browser except in the plan request). */
export function savePlanProfile(profile: Record<string, unknown>): void {
  try {
    sessionStorage.setItem(PROFILE_KEY, JSON.stringify(profile));
  } catch {
    /* ignore */
  }
}

export function loadPlanProfile(): Record<string, unknown> | undefined {
  try {
    const v: unknown = JSON.parse(sessionStorage.getItem(PROFILE_KEY) ?? "null");
    return isRecord(v) ? v : undefined;
  } catch {
    return undefined;
  }
}

export const planHref = (ids: string[]): string => `/plan?s=${ids.map(encodeURIComponent).join(",")}`;
export const parsePlanIds = (param: string | null): string[] =>
  [...new Set((param ?? "").split(",").map((x) => x.trim()).filter((x) => /^[\w-]{1,64}$/.test(x)))].slice(0, 12);
