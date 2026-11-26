import { describe, expect, it } from "vitest";
import { checkAll } from "./mock/rules";
import { isPlausible, splitNeedInfo } from "./need-info";
import raw from "@/data/schemes.json";
import type { NeedInfoItem, Scheme } from "./types";

const item = (id: string, missing: string[]): NeedInfoItem => ({ scheme_id: id, scheme_name: id, missing_fields: missing });
const ids = (xs: NeedInfoItem[]) => xs.map((x) => x.scheme_id);

describe("splitNeedInfo", () => {
  it("shows schemes missing at most 2 facts prominently and collapses the rest", () => {
    const { primary, other } = splitNeedInfo([item("a", ["bpl"]), item("b", ["bpl", "age"]), item("c", ["bpl", "age", "gender"])], {}, "");
    expect(ids(primary)).toEqual(["a", "b"]);
    expect(ids(other)).toEqual(["c"]);
  });

  it("skips pregnancy-based schemes for a man or for someone over 50", () => {
    const preg = item("pmmvy", ["pregnant_or_lactating"]);
    expect(isPlausible(preg, { gender: "male" }, "")).toBe(false);
    expect(isPlausible(preg, { age: 51 }, "")).toBe(false);
    expect(isPlausible(preg, { age: 50 }, "")).toBe(true);
    expect(isPlausible(preg, { age: 28, gender: "female" }, "")).toBe(true);
    expect(isPlausible(preg, {}, "")).toBe(true); // nothing known: keep
  });

  it("skips farmer schemes unless land or farming was mentioned", () => {
    const farm = item("pm_kisan", ["owns_cultivable_land"]);
    expect(isPlausible(farm, {}, "My mother is 62, a widow")).toBe(false);
    expect(isPlausible(farm, {}, "we have 2 acres")).toBe(true);
    expect(isPlausible(farm, {}, "main kisan hoon")).toBe(true);
    expect(isPlausible(farm, {}, "मेरे पास खेत है")).toBe(true);
    expect(isPlausible(farm, { owns_cultivable_land: true }, "")).toBe(true);
  });

  it("skips daughter schemes unless a child was mentioned", () => {
    const girl = item("ssy", ["children.age/gender"]);
    expect(isPlausible(girl, {}, "I am 40")).toBe(false);
    expect(isPlausible(girl, {}, "my 5 year old daughter")).toBe(true);
    expect(isPlausible(girl, { children: [{ gender: "female", age: 5 }] }, "")).toBe(true);
  });

  it("62-year-old BPL widow: no pregnancy, farming or daughter schemes up front, at most 2 missing", () => {
    const profile = { age: 62, gender: "female", marital_status: "widowed", bpl: true };
    const res = checkAll(profile, (raw as { schemes: Scheme[] }).schemes);
    const { primary, other } = splitNeedInfo(res.need_info, profile, "My mother is 62, a widow, and has a BPL card. What can she get?");
    expect(primary.length).toBeLessThanOrEqual(2);
    for (const hidden of ["pmmvy", "pm_kisan", "ssy"]) {
      expect(ids(primary)).not.toContain(hidden);
    }
    expect(ids(other)).toContain("pm_kisan");
    expect(primary.length + other.length).toBe(res.need_info.length);
  });
});
