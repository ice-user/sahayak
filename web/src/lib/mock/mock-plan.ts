import raw from "@/data/schemes.json";
import type { Scheme } from "../types";
import { tripKey, type PlanResponse, type PlanScheme, type PlanChecklistItem, type PlanRoute, type EnrolPoint, type EnrolGroup } from "../plan";

const ALL: Scheme[] = (raw as { schemes: Scheme[] }).schemes;

const slug = (s: string) =>
  s
    .toLowerCase()
    .replace(/\(.*?\)/g, "")
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "");

/** Documents that appear under different names across schemes are merged by this key. */
function docKey(name: string): string {
  const n = name.toLowerCase();
  if (n.includes("aadhaar") && !n.includes("pan") && !n.includes("mobile")) return "aadhaar";
  if (n.includes("bank") || n.includes("savings account")) return "bank_account";
  if (n.includes("bpl") || n.includes("ration")) return "bpl_ration_card";
  if (n.includes("photo")) return "photo";
  return slug(name);
}

const HOW_TO_GET: Record<string, { text: string; source_url: string }> = {
  aadhaar: { text: "Enrol or update at an Aadhaar Seva Kendra. Download e-Aadhaar from the UIDAI site if you already have one.", source_url: "https://uidai.gov.in/" },
  bank_account: { text: "Open a free Jan Dhan account at any bank branch with your Aadhaar.", source_url: "https://pmjdy.gov.in/" },
  bpl_ration_card: { text: "Get the ration or BPL card from the block / ward office or your state food department portal.", source_url: "https://nfsa.gov.in/" },
};

function enrolPoints(s: Scheme): EnrolPoint[] {
  const h = s.how_to_apply.toLowerCase();
  const pts: EnrolPoint[] = [];
  const add = (type: string, name: string, locator: string | null) =>
    pts.push({ type, name, locator_url: locator, quote: s.how_to_apply });
  if (h.includes("bank")) add("bank", "Your bank branch", "https://www.google.com/maps/search/bank+near+me");
  if (h.includes("post office")) add("post_office", "Post office", "https://www.indiapost.gov.in/vas/pages/findapostoffice.aspx");
  if (h.includes("common service centre")) add("csc", "Common Service Centre", "https://findmycsc.nic.in/");
  if (h.includes("panchayat")) add("panchayat", "Gram Panchayat / municipal office", null);
  if (h.includes("hospital") || h.includes("health facility")) add("hospital", "Empanelled hospital / health facility", "https://hospitals.pmjay.gov.in/");
  if (h.includes("anganwadi")) add("other", "Anganwadi centre", null);
  if (h.includes("lpg distributor")) add("other", "LPG distributor", null);
  if (/\.gov\.in|portal|app|net banking/.test(h)) add("online", "Official portal", null);
  if (!pts.length) add("office", "Local government office", null);
  return pts;
}

/** Plan fixture built from the bundled scheme data; shape matches POST /api/plan. */
export function mockPlan(schemeIds: string[]): PlanResponse {
  const schemes = schemeIds.map((id) => ALL.find((s) => s.id === id)).filter((s): s is Scheme => !!s);
  const docs = new Map<string, Extract<PlanResponse["checklist"][number], { doc: string }>>();
  for (const s of schemes) {
    for (const name of s.documents) {
      const key = docKey(name);
      const d = docs.get(key) ?? {
        doc: key,
        name,
        needed_for: [],
        mandatory: !/optional|if available/i.test(name),
        how_to_get: HOW_TO_GET[key] ?? null,
      };
      if (!d.needed_for.includes(s.id)) d.needed_for.push(s.id);
      docs.set(key, d);
    }
  }
  const plain = [...docs.values()].sort((a, b) => b.needed_for.length - a.needed_for.length);
  // Address-proof style documents become one "any one of" group, like the backend does from the quotes.
  const isAddress = (d: PlanResponse["checklist"][number]) => "doc" in d && /address|residence/i.test(d.name);
  const addr = plain.filter(isAddress);
  const checklist: PlanChecklistItem[] = plain.filter((d) => !isAddress(d));
  if (addr.length) {
    const extra = (doc: string, name: string): (typeof plain)[number] => ({ doc, name, needed_for: addr[0].needed_for, mandatory: true, how_to_get: null });
    checklist.push({
      doc_group: "address_proof",
      label: "Any one address proof",
      options: [extra("voter_id", "Voter ID (EPIC)"), extra("electricity_bill", "Electricity bill"), ...addr],
      needed_for: [...new Set(addr.flatMap((d) => d.needed_for))],
      mandatory: true,
    });
  }

  const steps: PlanResponse["steps"] = [];
  const watch_outs: PlanResponse["watch_outs"] = [];
  const where_to_go: PlanResponse["where_to_go"] = [];
  // Generic steps are shared: one merged step per kind, listing every scheme it applies to (like the backend).
  const mkStep = (list: Scheme[], n: number, action: string, where: string, mode: "online" | "offline", group_kind: string, group: string): PlanResponse["steps"][number] => ({
    scheme_id: list[0].id,
    scheme_name: list[0].name,
    scheme_ids: list.map((x) => x.id),
    scheme_names: list.map((x) => x.name),
    n,
    action,
    where,
    mode,
    source_url: list[0].source_url,
    source_urls: [...new Set(list.map((x) => x.source_url))],
    group_kind,
    group,
  });
  if (schemes.length) steps.push(mkStep(schemes, 1, "Keep the documents on your checklist ready (originals and one copy each).", "At home", "online", "prepare", "prepare"));
  const onlineSchemes = schemes.filter((s) => /portal|\.gov\.in|app|net banking/i.test(s.how_to_apply));
  if (onlineSchemes.length) steps.push(mkStep(onlineSchemes, 2, "Start the application on the official portal or app.", "Official portal", "online", "online", "Online"));
  const scheme_cards: PlanScheme[] = [];
  for (const s of schemes) {
    const first = enrolPoints(s)[0];
    const isOnline = onlineSchemes.includes(s);
    // Routes are alternatives: online when the scheme has a portal or app, and always an in-person route.
    const routes: PlanRoute[] = [];
    if (isOnline) {
      routes.push({ mode: "online", summary: "Start the application on the official portal or app.", where: "Official portal", recommended: true,
        steps: [{ n: 1, action: "Start the application on the official portal or app.", where: "Official portal", mode: "online", source_url: s.source_url }] });
    }
    routes.push({ mode: "offline", summary: s.how_to_apply, where: first.name, recommended: !isOnline,
      steps: [{ n: 1, action: s.how_to_apply, where: first.name, mode: "offline", source_url: s.source_url }] });
    scheme_cards.push({ scheme_id: s.id, scheme_name: s.name, source_url: s.source_url, source_official: /\.(gov|nic)\.in/.test(s.source_url), recommended_mode: isOnline ? "online" : "offline", routes });
    if (!isOnline) steps.push(mkStep([s], 3, s.how_to_apply, first.name, "offline", tripKey(first.type), first.name));

    s.caveats.forEach((c, i) =>
      watch_outs.push({ scheme_id: s.id, kind: "caveat", text: c, quote: s.how_to_apply, personal: i === 0 ? true : i === 1 ? null : false }),
    );
    watch_outs.push({
      scheme_id: s.id,
      kind: "scam",
      text: "Applying is free. Do not pay an agent or share your OTP with anyone.",
      quote: "No fee is charged for application under this scheme.",
      personal: false,
    });

    where_to_go.push({
      scheme_id: s.id,
      scheme_name: s.name,
      enrol_points: enrolPoints(s),
      grievance: { text: "Raise a complaint on the national grievance portal.", url_or_number: "https://pgportal.gov.in/", quote: "Grievances can be lodged at CPGRAMS." },
      helpline: s.id === "pm_kisan" ? "155261" : s.id.startsWith("pmj") || s.id === "apy" ? "1800-180-1111" : "1800-11-1555",
      portal_url: s.source_url,
      office: null,
    });
  }
  const groups = new Map<string, EnrolGroup>();
  for (const w of where_to_go) {
    for (const p of w.enrol_points) {
      const g = groups.get(p.type) ?? { type: p.type, scheme_ids: [], points: [] };
      groups.set(p.type, g);
      if (!g.scheme_ids.includes(w.scheme_id)) g.scheme_ids.push(w.scheme_id);
      const pt = g.points.find((x) => x.name === p.name) ?? { name: p.name, locator_url: p.locator_url, scheme_ids: [] };
      if (!g.points.includes(pt)) g.points.push(pt);
      if (!pt.scheme_ids.includes(w.scheme_id)) pt.scheme_ids.push(w.scheme_id);
    }
  }
  const enrol_groups = [...groups.values()].sort((a, b) => b.scheme_ids.length - a.scheme_ids.length);
  const order = (p: boolean | null) => (p === true ? 0 : p === null ? 1 : 2);
  watch_outs.sort((a, b) => order(a.personal) - order(b.personal));
  return {
    lang: "en",
    checklist,
    schemes: scheme_cards,
    steps,
    watch_outs,
    where_to_go,
    enrol_groups,
    summary: { schemes: schemes.length, trips: enrol_groups.length, unknown_schemes: [], missing_application_data: [], data_available: schemes.length > 0, mock: true },
    sources: schemes.map((s) => s.source_url),
  };
}
