import { describe, expect, it } from "vitest";
import raw from "@/data/schemes.json";
import { DICTS } from "./i18n";
import { describeRules, fieldLabel, formatFactValue } from "./rules-text";
import type { Rule, Scheme } from "./types";

const schemes = (raw as { schemes: Scheme[] }).schemes;
const rulesOf = (id: string): Rule[] => schemes.find((s) => s.id === id)!.rules!;

describe("describeRules", () => {
  it("merges age min and max into one range line", () => {
    const lines = describeRules(DICTS.en, rulesOf("apy"));
    expect(lines).toContain("Age 18 to 40");
    expect(lines.filter((l) => l.startsWith("Age"))).toHaveLength(1);
  });

  it("renders a widow pension in plain English", () => {
    expect(describeRules(DICTS.en, rulesOf("ignwps"))).toEqual([
      "A woman",
      "A widow (not remarried)",
      "Age 40 to 79",
      "Household is below the poverty line (BPL)",
    ]);
  });

  it("handles negated boolean rules and pension limits", () => {
    const lines = describeRules(DICTS.en, rulesOf("pm_kisan"));
    expect(lines).toContain("Family owns farmland");
    expect(lines).toContain("Nobody in the family paid income tax last year");
    expect(lines).toContain("Monthly pension below ₹10,000");
  });

  it("describes the any_child rule as a daughter under 10", () => {
    expect(describeRules(DICTS.en, rulesOf("ssy"))).toEqual(["Has a daughter under 10 years"]);
  });

  it("localises to Hindi, Hinglish and Tamil", () => {
    expect(describeRules(DICTS.hi, rulesOf("ignoaps"))).toContain("उम्र 60 साल या उससे ज़्यादा");
    expect(describeRules(DICTS.hinglish, rulesOf("ignoaps"))).toContain("Umar 60 saal ya usse zyada");
    expect(describeRules(DICTS.ta, rulesOf("ignoaps"))).toContain("வயது 60 அல்லது அதற்கு மேல்");
  });

  it("has a phrase for every boolean rule in the data, in every language", () => {
    for (const lang of Object.values(DICTS)) {
      for (const s of schemes) {
        for (const line of describeRules(lang, s.rules!)) {
          expect(line).not.toMatch(/: (eq|gte|lte|ne|in|any_child) /);
          expect(line.trim().length).toBeGreaterThan(0);
        }
      }
    }
  });

  it("falls back gracefully for unknown fields", () => {
    const lines = describeRules(DICTS.en, [{ field: "caste_group", op: "in", value: ["a", "b"], reason: "x" }]);
    expect(lines[0]).toBe("caste group: in a, b");
  });
});

describe("labels and values", () => {
  it("gives friendly field labels per language", () => {
    expect(fieldLabel(DICTS.en, "bpl")).toBe("BPL card");
    expect(fieldLabel(DICTS.hi, "bpl")).toBe("बीपीएल कार्ड");
    expect(fieldLabel(DICTS.en, "children.age/gender")).toBe("Daughter's age");
    expect(fieldLabel(DICTS.en, "something_new")).toBe("something new");
  });

  it("formats fact values", () => {
    expect(formatFactValue(DICTS.en, "bpl", true)).toBe("Yes");
    expect(formatFactValue(DICTS.hi, "bpl", false)).toBe("नहीं");
    expect(formatFactValue(DICTS.en, "marital_status", "widowed")).toBe("Widowed");
    expect(formatFactValue(DICTS.en, "gender", "female")).toBe("Female");
    expect(formatFactValue(DICTS.en, "children", [{ gender: "female", age: 5 }])).toBe("Female, 5");
  });

  it("has labels for every field used in the rules", () => {
    const fields = new Set(schemes.flatMap((s) => s.rules!.map((r) => r.field)));
    for (const lang of Object.values(DICTS)) for (const f of fields) expect(lang.fields[f], f).toBeTruthy();
  });
});
