"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { DICTS, LANGS, isLang, type Dict, type LangCode } from "@/lib/i18n";

interface LangContextValue {
  lang: LangCode;
  setLang: (l: LangCode) => void;
  t: Dict;
}

const LangContext = createContext<LangContextValue | null>(null);
const KEY = "sahayak.lang";

function detectInitial(): LangCode {
  try {
    const saved = localStorage.getItem(KEY);
    if (isLang(saved)) return saved;
  } catch {
    /* storage unavailable */
  }
  const nav = typeof navigator !== "undefined" ? navigator.language.toLowerCase() : "en";
  if (nav.startsWith("hi")) return "hi";
  if (nav.startsWith("ta")) return "ta";
  return "en";
}

export function LangProvider({ children }: { children: React.ReactNode }) {
  // Server and first client render use English so hydration matches; we then switch.
  const [lang, setLangState] = useState<LangCode>("en");

  useEffect(() => {
    const initial = detectInitial();
    // Deliberate: read browser-only storage after hydration so server and client markup match.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    if (initial !== "en") setLangState(initial);
  }, []);

  useEffect(() => {
    const meta = LANGS.find((l) => l.code === lang);
    document.documentElement.lang = meta?.htmlLang ?? "en";
    document.documentElement.dataset.lang = lang === "hinglish" ? "en" : lang;
    document.title = DICTS[lang].meta.title;
  }, [lang]);

  const setLang = useCallback((l: LangCode) => {
    setLangState(l);
    try {
      localStorage.setItem(KEY, l);
    } catch {
      /* ignore */
    }
  }, []);

  const value = useMemo(() => ({ lang, setLang, t: DICTS[lang] }), [lang, setLang]);
  return <LangContext.Provider value={value}>{children}</LangContext.Provider>;
}

export function useLang(): LangContextValue {
  const ctx = useContext(LangContext);
  if (!ctx) throw new Error("useLang must be used inside <LangProvider>");
  return ctx;
}
