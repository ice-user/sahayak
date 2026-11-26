import type { Dict } from "./i18n/types";
import type { Rule } from "./types";

const isNum = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v);

/** Friendly label for a profile field name (falls back to a de-snaked name). */
export function fieldLabel(dict: Dict, field: string): string {
  return dict.fields[field] ?? field.replace(/[._]/g, " ");
}

/** Human-readable value for a fact, e.g. true -> "Yes", "widowed" -> "Widowed". */
export function formatFactValue(dict: Dict, field: string, value: unknown): string {
  if (typeof value === "boolean") return value ? dict.values.yes : dict.values.no;
  if (field === "gender" && typeof value === "string") {
    return value === "female" ? dict.values.female : value === "male" ? dict.values.male : dict.values.other;
  }
  if (field === "marital_status" && typeof value === "string") return dict.values.marital[value] ?? value;
  if (field === "monthly_pension" && isNum(value)) return value === 0 ? dict.values.no : dict.values.rupees(value);
  if (field === "annual_income" && isNum(value)) return dict.values.rupees(value);
  if (field === "age" && isNum(value)) return String(value);
  if (field === "children" && Array.isArray(value)) {
    return value
      .map((c) => {
        const k = c as { gender?: string; age?: number };
        const g = k.gender === "female" ? dict.values.female : k.gender === "male" ? dict.values.male : "";
        return [g, isNum(k.age) ? String(k.age) : ""].filter(Boolean).join(", ");
      })
      .join("; ");
  }
  if (Array.isArray(value)) return value.map((v) => String(v)).join(", ");
  return String(value);
}

function describeChildRule(dict: Dict, subs: Rule[]): string {
  const isDaughter = subs.some((s) => s.field === "gender" && s.op === "eq" && s.value === "female");
  const ageMax = subs.find((s) => s.field === "age" && s.op === "lte" && isNum(s.value));
  const ageText = ageMax && isNum(ageMax.value) ? dict.rules.childAgeMax(ageMax.value + 1) : null;
  if (isDaughter) return dict.rules.daughter(ageText);
  return ageText ? `${fieldLabel(dict, "children")}: ${ageText}` : fieldLabel(dict, "children");
}

function describeOne(dict: Dict, r: Rule): string {
  const R = dict.rules;
  if (r.field === "gender" && r.op === "eq") {
    if (r.value === "female") return R.female;
    if (r.value === "male") return R.male;
  }
  if (r.field === "marital_status" && r.op === "eq" && r.value === "widowed") return R.widow;
  if (r.field === "monthly_pension" && r.op === "lte" && isNum(r.value)) return R.pensionBelow(dict.values.rupees(r.value + 1));
  if (r.op === "eq" && typeof r.value === "boolean" && R.bool[r.field]) {
    return r.value ? R.bool[r.field].yes : R.bool[r.field].no;
  }
  if (r.op === "any_child" && Array.isArray(r.value)) return describeChildRule(dict, r.value as Rule[]);
  if (r.field === "age" && isNum(r.value)) {
    if (r.op === "gte") return R.ageMin(r.value);
    if (r.op === "lte") return R.ageMax(r.value);
  }
  return R.fallback(fieldLabel(dict, r.field), r.op, formatFactValue(dict, r.field, r.value));
}

/**
 * Turns machine rules into plain-language conditions in the chosen language.
 * A top-level age minimum + maximum are merged into one line ("Age 18 to 40").
 */
export function describeRules(dict: Dict, rules: Rule[]): string[] {
  const min = rules.find((r) => r.field === "age" && r.op === "gte" && isNum(r.value));
  const max = rules.find((r) => r.field === "age" && r.op === "lte" && isNum(r.value));
  const lines: string[] = [];
  let ageDone = false;
  for (const r of rules) {
    if (r === min || r === max) {
      if (ageDone) continue;
      ageDone = true;
      if (min && max && isNum(min.value) && isNum(max.value)) lines.push(dict.rules.ageBetween(min.value, max.value));
      else lines.push(describeOne(dict, (min ?? max) as Rule));
      continue;
    }
    lines.push(describeOne(dict, r));
  }
  return lines;
}
