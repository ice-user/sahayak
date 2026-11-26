import type { LangCode } from "../types";

export type { LangCode };

export interface RulePhrases {
  ageMin: (n: number) => string;
  ageMax: (n: number) => string;
  ageBetween: (a: number, b: number) => string;
  childAgeMax: (n: number) => string;
  daughter: (ageText: string | null) => string;
  female: string;
  male: string;
  widow: string;
  pensionBelow: (n: string) => string;
  /** Per boolean field: phrase for "must be true" / "must be false". */
  bool: Record<string, { yes: string; no: string }>;
  fallback: (label: string, op: string, value: string) => string;
}

export interface Dict {
  meta: { title: string; description: string };
  brand: { name: string; tagline: string };
  nav: { ask: string; schemes: string; about: string; menu: string; language: string; skip: string };
  hero: { title: string; subtitle: string; tryAsking: string; examples: string[] };
  chat: {
    placeholder: string;
    send: string;
    newChat: string;
    inputLabel: string;
    emptyHint: string;
    status: Record<"thinking" | "searching" | "checking" | "reading" | "writing" | "waking", string>;
    retry: string;
    stop: string;
    errors: Record<"rate_limited" | "bad_request" | "llm_error" | "internal" | "busy" | "network" | "too_large" | "overloaded" | "session_limit", string>;
    retryIn: (seconds: number) => string;
    quickReplies: string;
    youSaid: string;
    assistantSaid: string;
    working: string;
    privacy: string;
    stopped: string;
    startNew: string;
    restarted: string;
    earlier: string;
  };
  cards: {
    eligibleHeading: (n: number) => string;
    qualifies: string;
    benefit: string;
    goodToKnow: string;
    documents: string;
    howToApply: string;
    officialSource: string;
    details: string;
    needHeading: (n: number) => string;
    need: string;
    notEligibleHeading: (n: number) => string;
    detailsLoading: string;
    englishNote: string;
    otherHeading: (n: number) => string;
    otherHint: string;
  };
  trace: {
    title: string;
    intro: string;
    searched: (q: string) => string;
    checked: string;
    lookedUp: (name: string) => string;
    factsUsed: string;
    noFacts: string;
    outcome: (e: number, n: number, x: number) => string;
    eligible: string;
    needInfo: string;
    notEligible: string;
    rulesNote: string;
    best: string;
    raw: string;
    failed: string;
    stats: (s: number, calls: number, tokens: number) => string;
    unknownTool: string;
  };
  fields: Record<string, string>;
  values: { yes: string; no: string; female: string; male: string; other: string; marital: Record<string, string>; rupees: (n: number) => string };
  rules: RulePhrases;
  categories: Record<string, string>;
  schemes: {
    title: string;
    subtitle: string;
    searchLabel: string;
    searchPlaceholder: string;
    all: string;
    count: (n: number) => string;
    none: string;
    clear: string;
    loadError: string;
    retry: string;
    viewDetails: string;
  };
  detail: {
    back: string;
    benefits: string;
    whoCanGet: string;
    whoNote: string;
    documents: string;
    documentsHint: string;
    howToApply: string;
    caveats: string;
    source: string;
    ask: string;
    notFound: string;
    ministry: string;
  };
  about: {
    title: string;
    lead: string;
    stepsTitle: string;
    steps: { title: string; body: string }[];
    whyTitle: string;
    whyBody: string[];
    whyTable: { verdict: string; meaning: string }[];
    dataTitle: string;
    dataBody: string[];
    verified: (d: string) => string;
    privacyTitle: string;
    privacyBody: string[];
    disclaimerTitle: string;
    disclaimer: string;
    tryIt: string;
  };
  footer: { disclaimer: string; verified: (d: string) => string; made: string };
  common: { loading: string; officialSourceLabel: string; opensNew: string };
}
