"use client";

import Link from "next/link";
import { ArrowUpRight, CircleHelp, ClipboardList, FileText, Info, ListChecks, XCircle } from "lucide-react";
import { FadeUp } from "@/components/fade-up";
import { Skeleton } from "@/components/ui/skeleton";
import { VerdictChip } from "@/components/verdict-chip";
import { buttonVariants } from "@/components/ui/button";
import { planHref, savePlanProfile } from "@/lib/plan";
import { cn } from "@/lib/utils";
import { Disclosure } from "@/components/disclosure";
import { useLang } from "@/components/lang-provider";
import { splitNeedInfo, type Profile } from "@/lib/need-info";
import { fieldLabel } from "@/lib/rules-text";
import { safeHttpUrl } from "@/lib/safe-url";
import type { EligibilityResult, EligibleItem, NeedInfoItem, NotEligibleItem, Scheme } from "@/lib/types";

type Index = Map<string, Scheme> | null;

export function ExternalLink({ href, children }: { href: string; children: React.ReactNode }) {
  const { t } = useLang();
  const safe = safeHttpUrl(href);
  if (!safe) return null; // never put an unvalidated URL (e.g. javascript:) in an href
  return (
    <a
      href={safe}
      target="_blank"
      rel="noopener noreferrer"
      className="inline-flex min-h-11 items-center gap-1 rounded-lg font-semibold text-ink underline decoration-marigold decoration-2 underline-offset-4"
    >
      {children}
      <ArrowUpRight className="size-4" aria-hidden="true" />
      <span className="sr-only">{t.common.opensNew}</span>
    </a>
  );
}

function EligibleCard({ item, scheme, index = 0 }: { item: EligibleItem; scheme?: Scheme; index?: number }) {
  const { t } = useLang();
  const caveats = item.caveats?.length ? item.caveats : (scheme?.caveats ?? []);
  return (
    <FadeUp as="article" index={index} className="overflow-hidden rounded-card border border-line border-l-[7px] border-l-leaf bg-card shadow-card">
      <div className="space-y-3 p-4 sm:p-5">
        <VerdictChip kind="eligible" />
        <h3 className="display text-[1.3rem] leading-snug sm:text-2xl">{item.scheme_name}</h3>
        <div className="rounded-xl bg-leaf-soft p-3">
          <p className="text-sm font-semibold text-leaf-deep">{t.cards.benefit}</p>
          <p className="text-[1.02rem] font-medium">{item.benefits}</p>
        </div>
        {caveats.length > 0 && (
          <div>
            <p className="mb-1 flex items-center gap-1.5 text-sm font-semibold text-amber-ink">
              <Info className="size-4" aria-hidden="true" />
              {t.cards.goodToKnow}
            </p>
            <ul className="list-disc space-y-1 pl-5 text-[0.98rem] text-ink-soft">
              {caveats.map((c) => (
                <li key={c}>{c}</li>
              ))}
            </ul>
          </div>
        )}
      </div>

      <div className="ticket-tear mx-0 px-4 pb-2 pt-2 sm:px-5">
        {scheme ? (
          <>
            {scheme.documents.length > 0 && (
              <Disclosure title={t.cards.documents} icon={<FileText className="size-5 text-saffron" aria-hidden="true" />}>
                <ul className="list-disc space-y-1 pl-6 text-[0.98rem]">
                  {scheme.documents.map((d) => (
                    <li key={d}>{d}</li>
                  ))}
                </ul>
              </Disclosure>
            )}
            {scheme.how_to_apply && (
              <Disclosure title={t.cards.howToApply} icon={<ListChecks className="size-5 text-saffron" aria-hidden="true" />} className="border-t border-line/70">
                <p className="pl-1 text-[0.98rem]">{scheme.how_to_apply}</p>
              </Disclosure>
            )}
          </>
        ) : (
          <div role="status" className="space-y-2 py-3">
            <span className="sr-only">{t.cards.detailsLoading}</span>
            <Skeleton className="h-4 w-2/3" />
            <Skeleton className="h-4 w-1/2" />
          </div>
        )}
        <div className="flex flex-wrap items-center gap-x-5 border-t border-line/70">
          {safeHttpUrl(item.source_url) && <ExternalLink href={item.source_url}>{t.cards.officialSource}</ExternalLink>}
          <Link href={`/schemes/${item.scheme_id}`} className="inline-flex min-h-11 items-center rounded-lg font-semibold text-ink-soft underline underline-offset-4">
            {t.cards.details}
          </Link>
        </div>
      </div>
    </FadeUp>
  );
}

function NeedInfoCard({ item, index = 0 }: { item: NeedInfoItem; index?: number }) {
  const { t } = useLang();
  return (
    <FadeUp as="li" index={index} className="rounded-xl border border-marigold/40 bg-amber-soft p-3.5">
      <VerdictChip kind="needInfo" className="mb-2" />
      <p className="flex items-start gap-2 font-semibold text-ink">
        <CircleHelp className="mt-1 size-4 shrink-0 text-amber-ink" aria-hidden="true" />
        {item.scheme_name}
      </p>
      <p className="mt-1.5 flex flex-wrap items-center gap-1.5 text-[0.95rem] text-amber-ink">
        <span className="font-semibold">{t.cards.need}:</span>
        {item.missing_fields.map((f) => (
          <span key={f} className="rounded-full bg-white/70 px-2.5 py-0.5 font-medium">
            {fieldLabel(t, f)}
          </span>
        ))}
      </p>
    </FadeUp>
  );
}

function NotEligibleList({ items, index }: { items: NotEligibleItem[]; index: Index }) {
  const { t } = useLang();
  return (
    <Disclosure
      title={t.cards.notEligibleHeading(items.length)}
      icon={<XCircle className="size-5 text-ink-soft" aria-hidden="true" />}
      className="rounded-xl border border-line bg-card/60 px-3"
    >
      <ul className="space-y-3 pb-2">
        {items.map((n) => (
          <li key={n.scheme_id}>
            <VerdictChip kind="notEligible" className="mb-1" />
            <p className="font-semibold">{n.scheme_name ?? index?.get(n.scheme_id)?.name ?? n.scheme_id}</p>
            <ul className="list-disc pl-5 text-[0.95rem] text-ink-soft">
              {n.reasons.map((r) => (
                <li key={r}>{r}</li>
              ))}
            </ul>
            {n.caveats && n.caveats.length > 0 && (
              <ul className="mt-1.5 space-y-1">
                {n.caveats.map((c) => (
                  <li key={c} className="flex items-start gap-2 rounded-lg bg-amber-soft px-2.5 py-1.5 text-[0.95rem] text-amber-ink">
                    <Info className="mt-1 size-4 shrink-0" aria-hidden="true" />
                    {c}
                  </li>
                ))}
              </ul>
            )}
          </li>
        ))}
      </ul>
    </Disclosure>
  );
}

function NeedInfoList({ items }: { items: NeedInfoItem[] }) {
  return (
    <ul className="space-y-2">
      {items.map((n, i) => (
        <NeedInfoCard key={n.scheme_id} item={n} index={i} />
      ))}
    </ul>
  );
}

interface ResultsProps {
  result: EligibilityResult;
  index: Index;
  /** Facts the assistant used for this check (drives which "might get" schemes are shown prominently). */
  profile?: Profile;
  /** What the user has typed so far in this conversation. */
  userText?: string;
}

export function SchemeResults({ result, index, profile = {}, userText = "" }: ResultsProps) {
  const { t, lang } = useLang();
  const { eligible, need_info, not_eligible } = result;
  const { primary, other } = splitNeedInfo(need_info, profile, userText);
  if (!eligible.length && !need_info.length && !not_eligible.length) return null;
  const planIds = [...eligible.map((e) => e.scheme_id), ...primary.map((n) => n.scheme_id)];
  return (
    <div className="space-y-4">
      {eligible.length > 0 && (
        <section aria-label={t.cards.eligibleHeading(eligible.length)} className="space-y-3">
          <h3 className="text-lg font-bold text-leaf-deep">{t.cards.eligibleHeading(eligible.length)}</h3>
          {eligible.map((e, i) => (
            <EligibleCard key={e.scheme_id} item={e} scheme={index?.get(e.scheme_id)} index={i} />
          ))}
          {lang !== "en" && <p className="text-sm text-ink-soft">{t.cards.englishNote}</p>}
        </section>
      )}
      {primary.length > 0 && (
        <section aria-label={t.cards.needHeading(primary.length)} className="space-y-2">
          <h3 className="text-lg font-bold text-amber-ink">{t.cards.needHeading(primary.length)}</h3>
          <NeedInfoList items={primary} />
        </section>
      )}
      {other.length > 0 && (
        <Disclosure
          title={t.cards.otherHeading(other.length)}
          icon={<CircleHelp className="size-5 text-ink-soft" aria-hidden="true" />}
          className="rounded-xl border border-line bg-card/60 px-3"
        >
          <div className="space-y-2 pb-2">
            <p className="text-sm text-ink-soft">{t.cards.otherHint}</p>
            <NeedInfoList items={other} />
          </div>
        </Disclosure>
      )}
      {not_eligible.length > 0 && <NotEligibleList items={not_eligible} index={index} />}
      {planIds.length > 0 && (
        <FadeUp index={eligible.length + 1} className="rounded-card border-2 border-ink/15 bg-card p-4 shadow-card">
          <p className="mb-3 flex items-start gap-2 text-[0.98rem] text-ink-soft">
            <ClipboardList className="mt-1 size-5 shrink-0 text-saffron" aria-hidden="true" />
            {t.plan.makeHint}
          </p>
          <Link href={planHref(planIds)} onClick={() => savePlanProfile(profile)} className={cn(buttonVariants({ variant: "primary" }), "w-full sm:w-auto")}>
            <ClipboardList aria-hidden="true" />
            {t.plan.make}
          </Link>
        </FadeUp>
      )}
    </div>
  );
}
