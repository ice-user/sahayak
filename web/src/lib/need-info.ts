import type { NeedInfoItem } from "./types";

/** More missing facts than this and a scheme is not worth asking about up front. */
export const MAX_MISSING_PROMINENT = 2;

export interface Profile {
  [field: string]: unknown;
}

export interface NeedInfoSplit {
  /** Few missing facts and plausibly relevant: shown prominently. */
  primary: NeedInfoItem[];
  /** Everything else: collapsed under "Other schemes to check". */
  other: NeedInfoItem[];
}

const FARM = /farm|kisan|kheti|khet|crop|cultivat|agricultur|\bland\b|acre|खेत|किसान|खेती|ज़मीन|जमीन|விவசாய|நிலம்|வயல்/i;
const CHILD = /daughter|girl|child|kid|\bbeti\b|bachch|बेटी|बच्च|மகள்|குழந்தை/i;

const num = (v: unknown): number | null => (typeof v === "number" && Number.isFinite(v) ? v : null);

/**
 * Deterministic relevance filter. `profile` is the facts sent to check_eligibility (may be empty) and
 * `userText` everything the user has typed so far. A scheme is dropped only when a missing fact makes it
 * implausible given what we already know:
 *  - pregnancy facts: person known to be male, or older than 50
 *  - farmland facts: no mention of land or farming anywhere in the conversation
 *  - children facts: no mention of a daughter/child and no children in the profile
 */
export function isPlausible(item: NeedInfoItem, profile: Profile, userText: string): boolean {
  const missing = item.missing_fields;
  const age = num(profile.age);
  if (missing.includes("pregnant_or_lactating")) {
    if (profile.gender === "male" || (age !== null && age > 50)) return false;
  }
  if (missing.includes("owns_cultivable_land")) {
    if (profile.owns_cultivable_land !== true && !FARM.test(userText)) return false;
  }
  if (missing.some((f) => f === "children" || f.startsWith("children."))) {
    const kids = Array.isArray(profile.children) && profile.children.length > 0;
    if (!kids && !CHILD.test(userText)) return false;
  }
  return true;
}

export function splitNeedInfo(items: NeedInfoItem[], profile: Profile, userText: string): NeedInfoSplit {
  const primary: NeedInfoItem[] = [];
  const other: NeedInfoItem[] = [];
  for (const it of items) {
    (it.missing_fields.length <= MAX_MISSING_PROMINENT && isPlausible(it, profile, userText) ? primary : other).push(it);
  }
  return { primary, other };
}
