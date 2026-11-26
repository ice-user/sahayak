"use client";

import raw from "@/data/schemes.json";
import { useLang } from "./lang-provider";

const verified = (raw as { _meta: { last_verified: string } })._meta.last_verified;

export function formatDate(iso: string, locale: string): string {
  const d = new Date(iso + "T00:00:00Z");
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString(locale, { day: "numeric", month: "long", year: "numeric", timeZone: "UTC" });
}

export const LAST_VERIFIED = verified;

export function Footer() {
  const { t, lang } = useLang();
  const locale = lang === "hi" ? "hi-IN" : lang === "ta" ? "ta-IN" : "en-IN";
  return (
    <footer className="mt-16 border-t border-line bg-paper-2">
      <div className="mx-auto max-w-5xl space-y-2 px-4 py-8 text-[0.95rem] text-ink-soft">
        <p className="max-w-2xl font-semibold text-ink">{t.footer.disclaimer}</p>
        <p>
          {t.footer.verified(formatDate(verified, locale))} {t.footer.made}
        </p>
      </div>
    </footer>
  );
}
