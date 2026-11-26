"use client";

import { LANGS } from "@/lib/i18n";
import { cn } from "@/lib/utils";
import { useLang } from "./lang-provider";

export function LangChips({ className }: { className?: string }) {
  const { lang, setLang, t } = useLang();
  return (
    <div role="group" aria-label={t.nav.language} className={cn("flex flex-wrap gap-1.5 sm:gap-2", className)}>
      {LANGS.map((l) => {
        const active = l.code === lang;
        return (
          <button
            key={l.code}
            type="button"
            lang={l.htmlLang}
            aria-pressed={active}
            onClick={() => setLang(l.code)}
            className={cn(
              "min-h-11 rounded-full border-2 px-3.5 text-base font-semibold transition-colors sm:px-4",
              active ? "border-ink bg-ink text-paper" : "border-ink/20 bg-card text-ink hover:border-ink/50",
            )}
          >
            {l.label}
          </button>
        );
      })}
    </div>
  );
}
