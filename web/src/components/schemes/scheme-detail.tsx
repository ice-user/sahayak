"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { ArrowLeft, Check, Info, MessageCircleQuestion } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ExternalLink } from "@/components/chat/scheme-results";
import { useLang } from "@/components/lang-provider";
import { ApiError, fetchScheme } from "@/lib/api";
import { safeHttpUrl } from "@/lib/safe-url";
import { describeRules } from "@/lib/rules-text";
import { cn } from "@/lib/utils";
import type { Scheme } from "@/lib/types";

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="space-y-3 border-t border-line pt-6">
      <h2 className="text-2xl font-bold">{title}</h2>
      {children}
    </section>
  );
}

function Checklist({ items, hint }: { items: string[]; hint: string }) {
  const [done, setDone] = useState<Set<string>>(new Set());
  const toggle = (d: string) =>
    setDone((prev) => {
      const next = new Set(prev);
      if (next.has(d)) next.delete(d);
      else next.add(d);
      return next;
    });
  return (
    <div>
      <p className="mb-2 text-sm text-ink-soft">{hint}</p>
      <ul className="space-y-1.5">
        {items.map((d, i) => {
          const id = `doc-${i}`;
          const on = done.has(d);
          return (
            <li key={d}>
              <label htmlFor={id} className="flex min-h-11 cursor-pointer items-center gap-3 rounded-xl border border-line bg-card px-3 py-2 has-[:focus-visible]:outline has-[:focus-visible]:outline-[3px] has-[:focus-visible]:outline-ink">
                <input id={id} type="checkbox" checked={on} onChange={() => toggle(d)} className="peer sr-only" />
                <span className={cn("grid size-6 shrink-0 place-items-center rounded-md border-2", on ? "border-leaf bg-leaf text-white" : "border-ink/30 bg-paper")} aria-hidden="true">
                  {on && <Check className="size-4" />}
                </span>
                <span className={cn("text-[1.02rem]", on && "text-ink-soft line-through decoration-ink/30")}>{d}</span>
              </label>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

export function SchemeDetail({ id }: { id: string }) {
  const { t } = useLang();
  const [scheme, setScheme] = useState<Scheme | null>(null);
  const [status, setStatus] = useState<"loading" | "ok" | "notfound" | "error">("loading");

  const [attempt, setAttempt] = useState(0);
  const load = useCallback(() => {
    setStatus("loading");
    setAttempt((n) => n + 1);
  }, []);

  useEffect(() => {
    let alive = true;
    fetchScheme(id).then(
      (s) => {
        if (!alive) return;
        setScheme(s);
        setStatus("ok");
      },
      (e: unknown) => alive && setStatus(e instanceof ApiError && e.status === 404 ? "notfound" : "error"),
    );
    return () => {
      alive = false;
    };
  }, [id, attempt]);

  const back = (
    <Link href="/schemes" className="inline-flex min-h-11 items-center gap-1.5 rounded-lg font-semibold text-ink-soft hover:text-ink">
      <ArrowLeft className="size-4" aria-hidden="true" />
      {t.detail.back}
    </Link>
  );

  if (status === "loading") {
    return (
      <div className="mx-auto max-w-3xl px-4 py-10" aria-busy="true">
        {back}
        <div className="mt-6 space-y-4">
          <div className="h-10 w-3/4 animate-pulse rounded-lg bg-paper-2" />
          <div className="h-24 animate-pulse rounded-lg bg-paper-2" />
          <div className="h-40 animate-pulse rounded-lg bg-paper-2" />
        </div>
      </div>
    );
  }
  if (status !== "ok" || !scheme) {
    return (
      <div className="mx-auto max-w-3xl px-4 py-10">
        {back}
        <div role="alert" className="mt-6 rounded-xl border border-brick/30 bg-brick-soft p-5 text-brick">
          <p className="font-semibold">{status === "notfound" ? t.detail.notFound : t.schemes.loadError}</p>
          {status === "error" && (
            <Button variant="outline" size="sm" className="mt-3 border-brick/40 text-brick" onClick={load}>
              {t.schemes.retry}
            </Button>
          )}
        </div>
      </div>
    );
  }

  const conditions = describeRules(t, scheme.rules ?? []);
  const sourceUrl = safeHttpUrl(scheme.source_url);
  return (
    <article className="mx-auto max-w-3xl space-y-8 px-4 py-8 sm:py-12">
      {back}
      <header className="space-y-3">
        <Badge tone="amber">{t.categories[scheme.category] ?? scheme.category}</Badge>
        <h1 className="display text-3xl sm:text-4xl">{scheme.name}</h1>
        <p className="text-lg text-ink-soft">{scheme.summary}</p>
        {scheme.ministry && (
          <p className="text-sm text-ink-soft">
            {t.detail.ministry}: {scheme.ministry}
          </p>
        )}
        <Button asChild variant="accent" className="mt-2">
          <Link href="/">
            <MessageCircleQuestion aria-hidden="true" />
            {t.detail.ask}
          </Link>
        </Button>
      </header>

      <section className="space-y-2 rounded-card border border-line border-l-[7px] border-l-leaf bg-leaf-soft/60 p-5">
        <h2 className="text-xl font-bold text-leaf-deep">{t.detail.benefits}</h2>
        <p className="text-[1.08rem] font-medium">{scheme.benefits}</p>
      </section>

      {conditions.length > 0 && (
        <Section title={t.detail.whoCanGet}>
          <ul className="space-y-2">
            {conditions.map((c) => (
              <li key={c} className="flex items-start gap-3 text-[1.05rem]">
                <span className="mt-1 grid size-6 shrink-0 place-items-center rounded-full bg-leaf text-white" aria-hidden="true">
                  <Check className="size-4" />
                </span>
                {c}
              </li>
            ))}
          </ul>
          <p className="text-sm text-ink-soft">{t.detail.whoNote}</p>
        </Section>
      )}

      {scheme.documents.length > 0 && (
        <Section title={t.detail.documents}>
          <Checklist items={scheme.documents} hint={t.detail.documentsHint} />
        </Section>
      )}

      {scheme.how_to_apply && (
        <Section title={t.detail.howToApply}>
          <p className="text-[1.05rem]">{scheme.how_to_apply}</p>
        </Section>
      )}

      {scheme.caveats.length > 0 && (
        <Section title={t.detail.caveats}>
          <ul className="space-y-2">
            {scheme.caveats.map((c) => (
              <li key={c} className="flex items-start gap-3 rounded-xl bg-amber-soft p-3 text-amber-ink">
                <Info className="mt-1 size-5 shrink-0" aria-hidden="true" />
                {c}
              </li>
            ))}
          </ul>
        </Section>
      )}

      {sourceUrl && (
        <Section title={t.detail.source}>
          <ExternalLink href={sourceUrl}>{sourceUrl.replace(/^https?:\/\//, "")}</ExternalLink>
        </Section>
      )}
    </article>
  );
}
