"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { LANGS, isLang } from "@/lib/i18n";
import { cn } from "@/lib/utils";
import { useLang } from "./lang-provider";
import { LogoMark } from "./logo";
import { Languages } from "lucide-react";

export function Header() {
  const { lang, setLang, t } = useLang();
  const path = usePathname();
  const links = [
    { href: "/", label: t.nav.ask, active: path === "/" },
    { href: "/schemes", label: t.nav.schemes, active: path.startsWith("/schemes") },
    { href: "/about", label: t.nav.about, active: path.startsWith("/about") },
  ];
  return (
    <header className="border-b border-line bg-paper/90 backdrop-blur">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:left-3 focus:top-3 focus:z-50 focus:rounded-lg focus:bg-ink focus:px-4 focus:py-2 focus:text-paper">
        {t.nav.skip}
      </a>
      <div className="mx-auto flex max-w-5xl flex-wrap items-center gap-x-6 gap-y-1 px-4 pt-3 sm:flex-nowrap sm:py-3">
        <Link href="/" className="flex min-h-11 items-center gap-2.5 rounded-lg">
          <LogoMark />
          <span className="leading-tight">
            <span className="display block text-xl">{t.brand.name}</span>
          </span>
        </Link>

        <label className="relative order-2 ml-auto flex min-h-11 items-center sm:order-3">
          <span className="sr-only">{t.nav.language}</span>
          <Languages className="pointer-events-none absolute left-3 size-4 text-ink-soft" aria-hidden="true" />
          <select
            value={lang}
            onChange={(e) => isLang(e.target.value) && setLang(e.target.value)}
            className="min-h-11 appearance-none rounded-full border-2 border-ink/20 bg-card py-1 pl-9 pr-8 text-base font-semibold text-ink"
          >
            {LANGS.map((l) => (
              <option key={l.code} value={l.code} lang={l.htmlLang}>
                {l.label}
              </option>
            ))}
          </select>
          <span className="pointer-events-none absolute right-3 text-xs text-ink-soft" aria-hidden="true">▾</span>
        </label>

        <nav aria-label={t.nav.menu} className="order-3 -mx-1 flex w-full gap-1 overflow-x-auto pb-1 sm:order-2 sm:w-auto sm:flex-1 sm:pb-0">
          {links.map((l) => (
            <Link
              key={l.href}
              href={l.href}
              aria-current={l.active ? "page" : undefined}
              className={cn(
                "flex min-h-11 items-center whitespace-nowrap rounded-full px-4 text-base font-semibold",
                l.active ? "bg-marigold-soft text-ink" : "text-ink-soft hover:bg-ink/5 hover:text-ink",
              )}
            >
              {l.label}
            </Link>
          ))}
        </nav>
      </div>
    </header>
  );
}
