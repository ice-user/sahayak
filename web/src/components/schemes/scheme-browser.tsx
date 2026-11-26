"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { ArrowRight, Search, X } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useLang } from "@/components/lang-provider";
import { useSchemes } from "@/hooks/use-schemes";
import { cn } from "@/lib/utils";
import type { Scheme } from "@/lib/types";

function haystack(s: Scheme): string {
  return [s.name, s.summary, s.benefits, s.category, ...(s.tags ?? []), ...(s.aliases ?? [])].join(" ").toLowerCase();
}

export function SchemeBrowser() {
  const { t } = useLang();
  const { schemes, error, retry } = useSchemes();
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState<string>("all");

  const categories = useMemo(() => Array.from(new Set((schemes ?? []).map((s) => s.category))), [schemes]);
  const shown = useMemo(() => {
    const q = query.trim().toLowerCase();
    return (schemes ?? []).filter((s) => (category === "all" || s.category === category) && (!q || q.split(/\s+/).every((w) => haystack(s).includes(w))));
  }, [schemes, query, category]);

  const catLabel = (c: string) => t.categories[c] ?? c;

  return (
    <div className="mx-auto max-w-5xl px-4 py-10 sm:py-14">
      <h1 className="display text-4xl sm:text-5xl">{t.schemes.title}</h1>
      <p className="mt-3 max-w-2xl text-lg text-ink-soft">{t.schemes.subtitle}</p>

      <div className="mt-8 space-y-4">
        <div className="relative max-w-xl">
          <label htmlFor="scheme-search" className="sr-only">
            {t.schemes.searchLabel}
          </label>
          <Search className="pointer-events-none absolute left-4 top-1/2 size-5 -translate-y-1/2 text-ink-soft" aria-hidden="true" />
          <input
            id="scheme-search"
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={t.schemes.searchPlaceholder}
            className="min-h-12 w-full rounded-full border-2 border-ink/25 bg-card py-2 pl-12 pr-12 text-[1.05rem] placeholder:text-ink-soft/70 focus:border-ink focus:outline-none"
          />
          {query && (
            <button type="button" onClick={() => setQuery("")} aria-label={t.schemes.clear} className="absolute right-1.5 top-1/2 grid size-11 -translate-y-1/2 place-items-center rounded-full text-ink-soft hover:bg-ink/5">
              <X className="size-5" aria-hidden="true" />
            </button>
          )}
        </div>

        <div role="group" aria-label={t.schemes.title} className="flex flex-wrap gap-2">
          {["all", ...categories].map((c) => {
            const active = c === category;
            return (
              <button
                key={c}
                type="button"
                aria-pressed={active}
                onClick={() => setCategory(c)}
                className={cn(
                  "min-h-11 rounded-full border-2 px-4 text-base font-semibold transition-colors",
                  active ? "border-ink bg-ink text-paper" : "border-ink/20 bg-card hover:border-ink/50",
                )}
              >
                {c === "all" ? t.schemes.all : catLabel(c)}
              </button>
            );
          })}
        </div>
      </div>

      <div className="mt-6" aria-live="polite">
        {error ? (
          <div className="rounded-xl border border-brick/30 bg-brick-soft p-5 text-brick" role="alert">
            <p className="font-semibold">{t.schemes.loadError}</p>
            <Button variant="outline" size="sm" className="mt-3 border-brick/40 text-brick" onClick={retry}>
              {t.schemes.retry}
            </Button>
          </div>
        ) : !schemes ? (
          <ul className="grid gap-4 sm:grid-cols-2" aria-busy="true" aria-label={t.common.loading}>
            {[0, 1, 2, 3].map((i) => (
              <li key={i} className="h-44 animate-pulse rounded-card bg-paper-2" />
            ))}
          </ul>
        ) : (
          <>
            <p className="mb-3 text-sm font-semibold text-ink-soft">{t.schemes.count(shown.length)}</p>
            {shown.length === 0 ? (
              <div className="rounded-xl border border-line bg-card p-6">
                <p className="font-semibold">{t.schemes.none}</p>
                <Button
                  variant="outline"
                  size="sm"
                  className="mt-3"
                  onClick={() => {
                    setQuery("");
                    setCategory("all");
                  }}
                >
                  {t.schemes.clear}
                </Button>
              </div>
            ) : (
              <ul className="grid gap-4 sm:grid-cols-2">
                {shown.map((s) => (
                  <li key={s.id} className="flex">
                    <article className="relative flex w-full flex-col gap-2 rounded-card border border-line bg-card p-5 shadow-card transition-colors focus-within:border-ink hover:border-marigold">
                      <Badge tone="amber" className="self-start">
                        {catLabel(s.category)}
                      </Badge>
                      <h2 className="text-xl font-bold leading-snug">
                        <Link href={`/schemes/${s.id}`} className="after:absolute after:inset-0 after:content-[''] focus-visible:after:rounded-card">
                          {s.name}
                        </Link>
                      </h2>
                      <p className="text-[0.98rem] text-ink-soft">{s.summary}</p>
                      <p className="mt-auto flex items-center gap-1 pt-2 font-semibold text-saffron">
                        {t.schemes.viewDetails}
                        <ArrowRight className="size-4" aria-hidden="true" />
                      </p>
                    </article>
                  </li>
                ))}
              </ul>
            )}
          </>
        )}
      </div>
    </div>
  );
}
