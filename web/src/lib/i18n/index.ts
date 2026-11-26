import type { Dict, LangCode } from "./types";
import { en } from "./en";
import { hi } from "./hi";
import { hinglish } from "./hinglish";
import { ta } from "./ta";

export type { Dict, LangCode };

export const DICTS: Record<LangCode, Dict> = { en, hi, hinglish, ta };

export const LANGS: { code: LangCode; label: string; htmlLang: string }[] = [
  { code: "en", label: "English", htmlLang: "en" },
  { code: "hi", label: "हिन्दी", htmlLang: "hi" },
  { code: "hinglish", label: "Hinglish", htmlLang: "hi-Latn" },
  { code: "ta", label: "தமிழ்", htmlLang: "ta" },
];

export const isLang = (v: unknown): v is LangCode => v === "en" || v === "hi" || v === "hinglish" || v === "ta";
