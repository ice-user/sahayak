"use client";

import Link from "next/link";
import { BadgeCheck, CircleHelp, Database, Lock, MessagesSquare, Scale, ScrollText, ShieldAlert, Sparkles, XCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useLang } from "@/components/lang-provider";
import { formatDate, LAST_VERIFIED } from "@/components/footer";

const STEP_ICONS = [MessagesSquare, Sparkles, Scale, ScrollText];

export function AboutContent() {
  const { t, lang } = useLang();
  const a = t.about;
  const locale = lang === "hi" ? "hi-IN" : lang === "ta" ? "ta-IN" : "en-IN";
  const verdictStyle = [
    { icon: BadgeCheck, cls: "border-leaf bg-leaf-soft text-leaf-deep" },
    { icon: XCircle, cls: "border-ink/20 bg-card text-ink" },
    { icon: CircleHelp, cls: "border-marigold bg-amber-soft text-amber-ink" },
  ];

  return (
    <div className="mx-auto max-w-4xl space-y-14 px-4 py-10 sm:py-14">
      <header className="max-w-2xl space-y-4">
        <h1 className="display text-4xl sm:text-5xl">{a.title}</h1>
        <p className="text-xl text-ink-soft">{a.lead}</p>
      </header>

      <section aria-labelledby="steps" className="space-y-5">
        <h2 id="steps" className="text-2xl font-bold">
          {a.stepsTitle}
        </h2>
        <ol className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4 lg:gap-0">
          {a.steps.map((s, i) => {
            const Icon = STEP_ICONS[i];
            const decides = i === 2;
            return (
              <li key={s.title} className="relative flex lg:pr-6">
                <div
                  className={`relative flex w-full flex-col gap-2 rounded-card border p-4 shadow-card ${decides ? "border-leaf bg-leaf-soft" : "border-line bg-card"}`}
                >
                  <div className="flex items-center gap-2.5">
                    <span className={`grid size-9 place-items-center rounded-full ${decides ? "bg-leaf text-white" : "bg-marigold-soft text-saffron"}`}>
                      <Icon className="size-5" aria-hidden="true" />
                    </span>
                    <span className="text-sm font-bold text-ink-soft" aria-hidden="true">
                      {i + 1}
                    </span>
                  </div>
                  <h3 className="text-lg font-bold leading-snug">{s.title}</h3>
                  <p className="text-[0.96rem] text-ink-soft">{s.body}</p>
                </div>
                {i < a.steps.length - 1 && (
                  <span className="absolute -right-0 top-1/2 z-10 hidden h-0.5 w-6 -translate-y-1/2 bg-ink/25 lg:block" aria-hidden="true" />
                )}
              </li>
            );
          })}
        </ol>
      </section>

      <section aria-labelledby="why" className="grid gap-6 lg:grid-cols-5">
        <div className="space-y-3 lg:col-span-2">
          <h2 id="why" className="text-2xl font-bold">
            {a.whyTitle}
          </h2>
          {a.whyBody.map((p) => (
            <p key={p} className="text-[1.05rem]">
              {p}
            </p>
          ))}
        </div>
        <ul className="space-y-3 lg:col-span-3">
          {a.whyTable.map((v, i) => {
            const { icon: Icon, cls } = verdictStyle[i];
            return (
              <li key={v.verdict} className={`flex items-start gap-3 rounded-card border-2 p-4 ${cls}`}>
                <Icon className="mt-1 size-6 shrink-0" aria-hidden="true" />
                <div>
                  <p className="text-lg font-bold">{v.verdict}</p>
                  <p className="text-[1rem]">{v.meaning}</p>
                </div>
              </li>
            );
          })}
        </ul>
      </section>

      <div className="grid gap-10 sm:grid-cols-2">
        <section aria-labelledby="data" className="space-y-3">
          <h2 id="data" className="flex items-center gap-2 text-2xl font-bold">
            <Database className="size-6 text-saffron" aria-hidden="true" />
            {a.dataTitle}
          </h2>
          {a.dataBody.map((p) => (
            <p key={p} className="text-[1.02rem]">
              {p}
            </p>
          ))}
          <p className="rounded-xl bg-paper-2 px-3 py-2 text-[0.98rem] font-semibold">{a.verified(formatDate(LAST_VERIFIED, locale))}</p>
        </section>
        <section aria-labelledby="privacy" className="space-y-3">
          <h2 id="privacy" className="flex items-center gap-2 text-2xl font-bold">
            <Lock className="size-6 text-saffron" aria-hidden="true" />
            {a.privacyTitle}
          </h2>
          {a.privacyBody.map((p) => (
            <p key={p} className="text-[1.02rem]">
              {p}
            </p>
          ))}
        </section>
      </div>

      <section aria-labelledby="disclaimer" className="rounded-card border-2 border-ink bg-card p-5 shadow-card sm:p-6">
        <h2 id="disclaimer" className="flex items-center gap-2 text-xl font-bold">
          <ShieldAlert className="size-6 text-brick" aria-hidden="true" />
          {a.disclaimerTitle}
        </h2>
        <p className="mt-2 text-lg font-semibold">{a.disclaimer}</p>
      </section>

      <Button asChild variant="accent">
        <Link href="/">{a.tryIt}</Link>
      </Button>
    </div>
  );
}
