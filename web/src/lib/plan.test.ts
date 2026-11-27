import { describe, expect, it } from "vitest";
import { en } from "./i18n/en";
import {
  buildShareText, CHECKLIST_PREFIX, isDocGroup, isReady, loadChecked, orderSteps, orderWatchOuts, parsePlan, phoneOf, pickOption,
  planId, progressOf, saveChecked, toggleChecked, tripsOf, whatsappLink, type PlanDoc, type PlanDocGroup, type PlanStep, type WatchOut,
} from "./plan";
import { mockPlan } from "./mock/mock-plan";

class MemStorage {
  data = new Map<string, string>();
  getItem(k: string) {
    return this.data.get(k) ?? null;
  }
  setItem(k: string, v: string) {
    this.data.set(k, v);
  }
}

const doc = (id: string): PlanDoc => ({ doc: id, name: id, needed_for: ["a"], mandatory: true, how_to_get: null });

describe("checklist persistence", () => {
  it("round-trips ticked documents per plan", () => {
    const st = new MemStorage();
    saveChecked("a,b", ["aadhaar", "photo"], st);
    expect(loadChecked("a,b", st)).toEqual(["aadhaar", "photo"]);
    expect(loadChecked("a,c", st)).toEqual([]); // another plan is untouched
    expect(st.data.has(`${CHECKLIST_PREFIX}a,b`)).toBe(true);
  });

  it("survives bad stored data and missing storage", () => {
    const st = new MemStorage();
    st.setItem(`${CHECKLIST_PREFIX}x`, "{not json");
    expect(loadChecked("x", st)).toEqual([]);
    st.setItem(`${CHECKLIST_PREFIX}x`, JSON.stringify({ a: 1 }));
    expect(loadChecked("x", st)).toEqual([]);
    st.setItem(`${CHECKLIST_PREFIX}x`, JSON.stringify(["a", 3, "a", "b"]));
    expect(loadChecked("x", st)).toEqual(["a", "b"]);
    expect(loadChecked("x", null)).toEqual([]);
    expect(() => saveChecked("x", ["a"], null)).not.toThrow();
  });

  it("toggles and counts progress, ignoring stale ticks", () => {
    let c: string[] = [];
    c = toggleChecked(c, "a");
    c = toggleChecked(c, "b");
    expect(c).toEqual(["a", "b"]);
    expect(toggleChecked(c, "a")).toEqual(["b"]);
    const list = [doc("a"), doc("b"), doc("c"), doc("d")];
    expect(progressOf(list, ["a", "gone"])).toEqual({ have: 1, total: 4, ratio: 0.25 });
    expect(progressOf([], [])).toEqual({ have: 0, total: 0, ratio: 0 });
  });

  it("gives the same plan id whatever the order of schemes", () => {
    expect(planId(["pm_kisan", "apy", "apy"])).toBe(planId(["apy", "pm_kisan"]));
  });
});

describe("ordering", () => {
  const w = (text: string, personal: boolean | null): WatchOut => ({ scheme_id: "s", kind: "k", text, quote: null, personal });
  it("puts watch-outs that apply to the user first, then unknown, then general (stable)", () => {
    const out = orderWatchOuts([w("g1", false), w("n1", null), w("p1", true), w("g2", false), w("p2", true), w("n2", null)]);
    expect(out.map((x) => x.text)).toEqual(["p1", "p2", "n1", "n2", "g1", "g2"]);
  });

  it("shows online steps before office visits", () => {
    const s = (action: string, mode: "online" | "offline"): PlanStep => ({ scheme_id: "s", scheme_name: "S", scheme_ids: ["s"], scheme_names: ["S"], n: 1, action, where: "", mode, source_url: null, source_urls: [], group_kind: "", group: "" });
    expect(orderSteps([s("visit", "offline"), s("apply", "online"), s("visit2", "offline"), s("pay", "online")]).map((x) => x.action)).toEqual([
      "apply", "pay", "visit", "visit2",
    ]);
  });
});

describe("plan parsing, trips and sharing", () => {
  it("parses the mock plan and groups one bank trip across schemes", () => {
    const plan = parsePlan(mockPlan(["apy", "pmjjby", "pmsby", "pm_kisan"]))!;
    expect(plan).not.toBeNull();
    const bank = tripsOf(plan).find((t) => t.key === "bank")!;
    expect(bank.schemes.map((s) => s.id)).toEqual(expect.arrayContaining(["apy", "pmjjby", "pmsby"]));
    // Aadhaar is merged across the four schemes into one checklist row.
    expect(plan.checklist.find((d) => !isDocGroup(d) && d.doc === "aadhaar")!.needed_for).toHaveLength(4);
    // personal-first ordering is already applied by the backend and mock.
    const ranks = plan.watch_outs.map((x) => (x.personal === true ? 0 : x.personal === null ? 1 : 2));
    expect(ranks).toEqual([...ranks].sort());
  });

  it("rejects garbage and reads phone numbers", () => {
    expect(parsePlan(null)).toBeNull();
    expect(parsePlan({ steps: [] })).toBeNull();
    expect(phoneOf("1800-180-1111")).toBe("18001801111");
    expect(phoneOf("155261")).toBe("155261");
    expect(phoneOf("https://pgportal.gov.in/")).toBeNull();
    expect(phoneOf(null)).toBeNull();
  });

  it("builds a short WhatsApp text with ticks", () => {
    const plan = parsePlan(mockPlan(["apy", "pm_kisan"]))!;
    const text = buildShareText(plan, en, ["aadhaar"]);
    expect(text).toContain("✅ Aadhaar card");
    expect(text).toContain("⬜");
    expect(text.length).toBeLessThanOrEqual(1400);
    expect(whatsappLink("a b")).toBe("https://wa.me/?text=a%20b");
  });
});

describe("merged steps", () => {
  it("collapses generic steps across schemes and lists every scheme", () => {
    const plan = parsePlan(mockPlan(["apy", "pmjjby", "pmsby", "pm_kisan"]))!;
    const prepare = plan.steps.filter((s) => s.group_kind === "prepare");
    expect(prepare).toHaveLength(1);
    expect(prepare[0].scheme_ids).toHaveLength(4);
    expect(prepare[0].scheme_names).toHaveLength(4);
    expect(orderSteps(plan.steps)[0].group_kind).toBe("prepare");
  });
  it("falls back to the single scheme for old responses", () => {
    const plan = parsePlan({ checklist: [], steps: [{ action: "x", scheme_id: "a", scheme_name: "A", source_url: "https://x.in" }] })!;
    expect(plan.steps[0].scheme_ids).toEqual(["a"]);
    expect(plan.steps[0].scheme_names).toEqual(["A"]);
    expect(plan.steps[0].source_urls).toEqual(["https://x.in"]);
  });
});

const group = (): PlanDocGroup => ({
  doc_group: "address_proof",
  label: "Any one address proof",
  options: [doc("voter_id"), doc("electricity_bill"), doc("aadhaar")],
  needed_for: ["a"],
  mandatory: true,
});

describe("alternative documents", () => {
  it("is satisfied when any one option is ticked and counts as one row", () => {
    const list = [doc("bank"), group()];
    expect(progressOf(list, [])).toEqual({ have: 0, total: 2, ratio: 0 });
    expect(progressOf(list, ["electricity_bill"])).toEqual({ have: 1, total: 2, ratio: 0.5 });
    expect(progressOf(list, ["electricity_bill", "bank"]).ratio).toBe(1);
    expect(isReady(group(), ["stale"])).toBe(false);
  });

  it("works like a radio group: picking one clears the others, picking it again clears it", () => {
    const g = group();
    let c = pickOption(["bank"], g, "voter_id");
    expect(c).toEqual(["bank", "voter_id"]);
    c = pickOption(c, g, "aadhaar");
    expect(c).toEqual(["bank", "aadhaar"]);
    expect(pickOption(c, g, "aadhaar")).toEqual(["bank"]);
  });

  it("parses groups and plain documents together and drops empty groups", () => {
    const plan = parsePlan({
      checklist: [
        { doc: "bank", name: "Bank passbook", needed_for: ["a"], mandatory: true },
        { doc_group: "age_proof", label: "Any one age proof", needed_for: ["a", "b"], mandatory: true, options: [{ doc: "birth", name: "Birth certificate" }, { nope: 1 }] },
        { doc_group: "empty", label: "x", options: [] },
      ],
      steps: [],
    })!;
    expect(plan.checklist).toHaveLength(2);
    const g = plan.checklist[1];
    expect(isDocGroup(g) && g.options.map((o) => o.doc)).toEqual(["birth"]);
    expect(isDocGroup(g) && g.label).toBe("Any one age proof");
  });

  it("shows a group in the WhatsApp text with its tick state", () => {
    const plan = parsePlan({ checklist: [group()], steps: [] })!;
    const none = buildShareText(plan, en, []);
    expect(none).toContain("⬜ Any one address proof: voter_id / electricity_bill / aadhaar");
    expect(buildShareText(plan, en, ["aadhaar"])).toContain("✅ Any one address proof");
  });
});

describe("routes", () => {
  const raw = (over: Record<string, unknown> = {}) => ({
    checklist: [],
    steps: [],
    schemes: [
      {
        scheme_id: "ssy",
        scheme_name: "Sukanya",
        source_url: "https://angelone.in/x",
        source_official: false,
        routes: [
          { mode: "online", summary: "Apply on the app", where: "https://x.gov.in", recommended: false, steps: [{ n: 1, action: "Open the app", mode: "online" }, { n: 2, action: "Log in", mode: "online" }] },
          { mode: "offline", summary: "Visit the post office", where: "Post office", recommended: true, steps: [{ n: 1, action: "Go", where: "Post office", mode: "offline" }] },
        ],
        ...over,
      },
    ],
  });

  it("keeps the recommended route and the unofficial-source flag", () => {
    const c = parsePlan(raw())!.schemes[0];
    expect(c.source_official).toBe(false);
    expect(c.recommended_mode).toBe("offline");
    expect(c.routes.map((r) => [r.mode, r.recommended, r.steps.length])).toEqual([["online", false, 2], ["offline", true, 1]]);
    expect(c.routes[1].summary).toBe("Visit the post office");
  });

  it("always has exactly one recommended route, and treats a missing flag as official", () => {
    const none = parsePlan(raw({ source_official: undefined, routes: [{ mode: "online", summary: "a", steps: [{ n: 1, action: "x", mode: "online" }] }, { mode: "offline", summary: "b", steps: [{ n: 1, action: "y", mode: "offline" }] }] }))!.schemes[0];
    expect(none.routes.map((r) => r.recommended)).toEqual([true, false]);
    expect(none.source_official).toBe(true);
    const two = parsePlan(raw({ routes: [{ mode: "online", summary: "a", recommended: true, steps: [{ n: 1, action: "x", mode: "online" }] }, { mode: "offline", summary: "b", recommended: true, steps: [{ n: 1, action: "y", mode: "offline" }] }] }))!.schemes[0];
    expect(two.routes.filter((r) => r.recommended)).toHaveLength(1);
  });

  it("old responses without schemes still parse; routes without steps are dropped", () => {
    expect(parsePlan({ checklist: [], steps: [] })!.schemes).toEqual([]);
    expect(parsePlan(raw({ routes: [{ mode: "online", summary: "a", steps: [] }] }))!.schemes[0].routes).toEqual([]);
  });

  it("puts the recommended route first in the WhatsApp steps", () => {
    const text = buildShareText(parsePlan(raw())!, en, []);
    expect(text).toContain("1. Sukanya: Visit the post office (Post office)");
    expect(text).not.toContain("Apply on the app");
  });

  it("mock plan has one recommended route per scheme and ends with an in-person route", () => {
    const plan = parsePlan(mockPlan(["apy", "pmjjby", "pm_kisan", "pmuy"]))!;
    expect(plan.schemes.length).toBeGreaterThan(0);
    for (const c of plan.schemes) {
      expect(c.routes.filter((r) => r.recommended)).toHaveLength(1);
      expect(c.routes.at(-1)!.mode).toBe("offline");
    }
  });
});
