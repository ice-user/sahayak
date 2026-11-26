import type { EligibilityResult, Rule, Scheme } from "../types";

export type Facts = Record<string, unknown>;
type Status = "pass" | "fail" | "unknown";

/** TypeScript port of sahayak/rules.py, used ONLY by the mock backend. */
function evalCond(data: Facts, cond: { field: string; op: string; value: unknown }): { status: Status; missing: string[] } {
  const { field, op, value } = cond;
  const actual = data[field];
  if (op === "any_child") {
    if (actual === undefined || actual === null) return { status: "unknown", missing: [field] };
    const kids = Array.isArray(actual) ? (actual as Facts[]) : [];
    if (kids.length === 0) return { status: "fail", missing: [] };
    let sawUnknown = false;
    for (const kid of kids) {
      const statuses = (value as Rule[]).map((sub) => evalCond(kid, sub).status);
      if (statuses.every((s) => s === "pass")) return { status: "pass", missing: [] };
      if (!statuses.includes("fail")) sawUnknown = true;
    }
    return sawUnknown ? { status: "unknown", missing: [`${field}.age/gender`] } : { status: "fail", missing: [] };
  }
  if (actual === undefined || actual === null) return { status: "unknown", missing: [field] };
  let ok: boolean;
  switch (op) {
    case "eq": ok = actual === value; break;
    case "ne": ok = actual !== value; break;
    case "gte": ok = (actual as number) >= (value as number); break;
    case "lte": ok = (actual as number) <= (value as number); break;
    case "in": ok = (value as unknown[]).includes(actual); break;
    default: ok = false;
  }
  return { status: ok ? "pass" : "fail", missing: [] };
}

/** Mirrors the newer backend, which attaches hints to some not-eligible schemes. */
const NOT_ELIGIBLE_CAVEATS: Record<string, string[]> = {
  pmjay_senior: ["You don't qualify for the 70+ card, but you may still be covered by regular PM-JAY if your household is eligible."],
};

export function checkAll(facts: Facts, schemes: Scheme[]): EligibilityResult {
  const out: EligibilityResult = { eligible: [], need_info: [], not_eligible: [] };
  for (const s of schemes) {
    const failed: string[] = [];
    const missing = new Set<string>();
    for (const r of s.rules ?? []) {
      const { status, missing: m } = evalCond(facts, r);
      if (status === "fail") failed.push(r.reason);
      else if (status === "unknown") m.forEach((x) => missing.add(x));
    }
    if (failed.length) out.not_eligible.push({ scheme_id: s.id, scheme_name: s.name, reasons: failed, caveats: NOT_ELIGIBLE_CAVEATS[s.id] ?? [] });
    else if (missing.size) out.need_info.push({ scheme_id: s.id, scheme_name: s.name, missing_fields: [...missing].sort() });
    else
      out.eligible.push({
        scheme_id: s.id,
        scheme_name: s.name,
        verdict: "eligible",
        failed_reasons: [],
        missing_fields: [],
        caveats: s.caveats,
        benefits: s.benefits,
        source_url: s.source_url,
      });
  }
  return out;
}
