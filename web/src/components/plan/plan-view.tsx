"use client";

import { useEffect, useMemo, useReducer, useState } from "react";
import Link from "next/link";
import {
  AlertTriangle, ArrowLeft, Building, CheckCircle2, ClipboardList, FileText, Globe, Home, Hospital, Landmark,
  LifeBuoy, Mail, MapPin, MessageCircle, Phone, Printer, RotateCw, ShieldQuestion, Store, UserRound, type LucideIcon,
} from "lucide-react";
import { Button, buttonVariants } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Disclosure } from "@/components/disclosure";
import { FadeUp } from "@/components/fade-up";
import { useLang } from "@/components/lang-provider";
import { ExternalLink } from "@/components/chat/scheme-results";
import { ApiError, fetchPlan } from "@/lib/api";
import {
  buildShareText, isDocGroup, isReady, loadChecked, loadPlanProfile, orderSteps, orderWatchOuts, phoneOf, pickOption, planId,
  progressOf, saveChecked, toggleChecked, tripsOf, whatsappLink, type PlanDoc, type PlanDocGroup, type PlanResponse,
  type PlanScheme, type TripKey,
} from "@/lib/plan";
import { safeHttpUrl } from "@/lib/safe-url";
import { cn } from "@/lib/utils";

// ---------- data loading ----------

type Load = { key: string; plan: PlanResponse | null; error: ApiError | null };

function useLoadedPlan(ids: string[], attempt: number) {
  const { lang } = useLang();
  const key = `${ids.join(",")}|${lang}|${attempt}`;
  const [state, set] = useReducer((_: Load, next: Load) => next, { key: "", plan: null, error: null });
  useEffect(() => {
    const list = key.split("|")[0].split(",").filter(Boolean);
    if (!list.length) return;
    const ctl = new AbortController();
    fetchPlan(list, loadPlanProfile(), lang, ctl.signal).then(
      (plan) => set({ key, plan, error: null }),
      (e: unknown) => {
        if (e instanceof DOMException && e.name === "AbortError") return;
        set({ key, plan: null, error: e instanceof ApiError ? e : new ApiError("Network error", "network") });
      },
    );
    return () => ctl.abort();
  }, [key, lang]);
  // Loading = the latest result is not for the current request.
  return state.key === key ? state : null;
}

// ---------- small pieces ----------

function PlanSkeleton() {
  const { t } = useLang();
  return (
    <div role="status" className="space-y-5">
      <span className="sr-only">{t.plan.loading}</span>
      <Skeleton className="h-8 w-2/3" />
      <div className="flex items-center gap-4">
        <Skeleton className="size-24 rounded-full" />
        <div className="flex-1 space-y-2">
          <Skeleton className="h-5 w-1/2" />
          <Skeleton className="h-4 w-3/4" />
        </div>
      </div>
      {[0, 1, 2].map((i) => (
        <Skeleton key={i} className="h-16 w-full" />
      ))}
      <Skeleton className="h-40 w-full" />
    </div>
  );
}

function Notice({ icon, title, body, children }: { icon: React.ReactNode; title: string; body: string; children?: React.ReactNode }) {
  return (
    <FadeUp className="rounded-card border border-line bg-card p-6 text-center shadow-card">
      <div className="mx-auto mb-3 grid size-14 place-items-center rounded-full bg-marigold-soft text-saffron" aria-hidden="true">
        {icon}
      </div>
      <h2 className="display text-xl">{title}</h2>
      <p className="mx-auto mt-2 max-w-md text-ink-soft">{body}</p>
      <div className="mt-4 flex justify-center">{children}</div>
    </FadeUp>
  );
}

function Section({ icon, title, hint, children, className }: { icon: React.ReactNode; title: string; hint?: string; children: React.ReactNode; className?: string }) {
  return (
    <section className={cn("space-y-3", className)} aria-label={title}>
      <div>
        <h2 className="display flex items-center gap-2 text-[1.35rem]">
          <span className="text-saffron" aria-hidden="true">
            {icon}
          </span>
          {title}
        </h2>
        {hint && <p className="mt-1 text-[0.98rem] text-ink-soft">{hint}</p>}
      </div>
      {children}
    </section>
  );
}

const R = 38;
const C = 2 * Math.PI * R;

function ProgressRing({ have, total, ratio }: { have: number; total: number; ratio: number }) {
  const { t } = useLang();
  return (
    <div
      role="progressbar"
      aria-valuemin={0}
      aria-valuemax={total}
      aria-valuenow={have}
      aria-label={t.plan.progress(have, total)}
      className="relative grid size-24 shrink-0 place-items-center"
    >
      <svg viewBox="0 0 100 100" className="size-24 -rotate-90" aria-hidden="true">
        <circle cx="50" cy="50" r={R} fill="none" strokeWidth="10" className="stroke-ink/10" />
        <circle
          cx="50"
          cy="50"
          r={R}
          fill="none"
          strokeWidth="10"
          strokeLinecap="round"
          className={cn("ring-progress", ratio >= 1 ? "stroke-leaf" : "stroke-marigold")}
          strokeDasharray={C}
          strokeDashoffset={C * (1 - ratio)}
        />
      </svg>
      <span className="absolute text-lg font-extrabold tabular-nums" aria-hidden="true">
        {have}/{total}
      </span>
    </div>
  );
}

// ---------- checklist ----------

function Checklist({
  plan,
  id,
  nameOf,
  checked,
  setChecked,
}: {
  plan: PlanResponse;
  id: string;
  nameOf: (s: string) => string;
  checked: string[];
  setChecked: (c: string[]) => void;
}) {
  const { t } = useLang();
  const { have, total, ratio } = progressOf(plan.checklist, checked);
  const set = new Set(checked);
  const save = (next: string[]) => {
    setChecked(next);
    saveChecked(id, next);
  };
  const toggle = (doc: string) => save(toggleChecked(checked, doc));
  return (
    <Section icon={<FileText className="size-6" />} title={t.plan.docsTitle} hint={t.plan.docsHint}>
      <div className="plan-card flex items-center gap-4 rounded-card border border-line bg-card p-4 shadow-card">
        <ProgressRing have={have} total={total} ratio={ratio} />
        <p role="status" className="flex-1 text-lg font-bold">
          {ratio >= 1 && total > 0 ? (
            <span className="flex items-start gap-2 text-leaf-deep">
              <CheckCircle2 className="mt-1 size-5 shrink-0" aria-hidden="true" />
              {t.plan.allDone}
            </span>
          ) : (
            t.plan.progress(have, total)
          )}
        </p>
      </div>
      <ul className="space-y-2.5">
        {plan.checklist.map((d, i) => {
          const on = isReady(d, checked);
          const badges = (
            <span className="mt-1 flex flex-wrap items-center gap-1.5">
              <span className="inline-flex items-center rounded-full bg-ink/10 px-2.5 py-0.5 text-sm font-semibold text-ink" title={d.needed_for.map(nameOf).join(", ")}>
                {t.plan.neededFor(d.needed_for.length)}
              </span>
              <span className={cn("rounded-full px-2.5 py-0.5 text-sm font-semibold", d.mandatory ? "bg-brick-soft text-brick" : "bg-paper-2 text-ink-soft")}>
                {d.mandatory ? t.plan.mandatory : t.plan.optional}
              </span>
            </span>
          );
          const card = cn("plan-card print-avoid-break rounded-xl border bg-card p-3.5 transition-colors", on ? "border-leaf/50 bg-leaf-soft/60" : "border-line");
          if (isDocGroup(d)) {
            return (
              <FadeUp as="li" key={d.doc_group} index={i} className={card}>
                <GroupRow group={d} on={on} set={set} onPick={(doc) => save(pickOption(checked, d, doc))} badges={badges} />
              </FadeUp>
            );
          }
          return (
            <FadeUp as="li" key={d.doc} index={i} className={card}>
              <label className="flex min-h-11 cursor-pointer items-start gap-3">
                <input
                  type="checkbox"
                  checked={on}
                  onChange={() => toggle(d.doc)}
                  aria-label={t.plan.tick(d.name)}
                  className="mt-0.5 size-7 shrink-0 cursor-pointer accent-[#1b7a4b]"
                />
                <span className="min-w-0 flex-1">
                  <span className={cn("block text-[1.05rem] font-semibold", on && "text-leaf-deep")}>{d.name}</span>
                  {badges}
                </span>
              </label>
              <HowToGet doc={d} hide={on} />
            </FadeUp>
          );
        })}
      </ul>
    </Section>
  );
}

function HowToGet({ doc, hide }: { doc: PlanDoc; hide: boolean }) {
  const { t } = useLang();
  if (!doc.how_to_get || hide) return null;
  return (
    <Disclosure title={t.plan.howToGet} triggerClassName="text-[0.95rem] text-ink-soft" className="ml-10">
      <p className="text-[0.98rem]">{doc.how_to_get.text}</p>
      {doc.how_to_get.source_url && <ExternalLink href={doc.how_to_get.source_url}>{t.plan.source}</ExternalLink>}
    </Disclosure>
  );
}

/** "Any one of: A / B / C": radio-style options; picking one satisfies the row, picking it again clears it. */
function GroupRow({ group, on, set, onPick, badges }: { group: PlanDocGroup; on: boolean; set: Set<string>; onPick: (doc: string) => void; badges: React.ReactNode }) {
  const { t } = useLang();
  const names = group.options.map((o) => o.name).join(" / ");
  return (
    <fieldset>
      <legend className={cn("block text-[1.05rem] font-semibold", on && "text-leaf-deep")}>{group.label}</legend>
      <p className="text-[0.98rem] text-ink-soft">
        {t.plan.anyOneOf}: {names}
      </p>
      {badges}
      <p className="no-print mt-2 text-sm font-semibold text-ink-soft">{t.plan.pickOne}</p>
      <div role="radiogroup" aria-label={group.label} className="mt-1 space-y-1">
        {group.options.map((o) => {
          const chosen = set.has(o.doc);
          return (
            <div key={o.doc}>
              <label className="flex min-h-11 cursor-pointer items-center gap-3">
                <input
                  type="radio"
                  name={`group-${group.doc_group}`}
                  checked={chosen}
                  onChange={() => undefined}
                  onClick={() => onPick(o.doc)}
                  aria-label={t.plan.tick(o.name)}
                  className="size-6 shrink-0 cursor-pointer accent-[#1b7a4b]"
                />
                <span className={cn("text-[1.02rem] font-medium", chosen && "text-leaf-deep")}>{o.name}</span>
              </label>
              <HowToGet doc={o} hide={on} />
            </div>
          );
        })}
      </div>
    </fieldset>
  );
}

// ---------- steps ----------

function Steps({ plan }: { plan: PlanResponse }) {
  const { t } = useLang();
  const steps = orderSteps(plan.steps);
  if (!steps.length) return null;
  return (
    <Section icon={<ClipboardList className="size-6" />} title={t.plan.stepsTitle} hint={t.plan.stepsHint}>
      <ol className="relative ml-5 space-y-3 border-l-2 border-dashed border-line">
        {steps.map((s, i) => {
          const prepare = s.group_kind === "prepare";
          const online = s.mode === "online";
          return (
            <FadeUp as="li" key={`${s.scheme_ids.join("+")}-${s.n}-${i}`} index={i} className="plan-card print-avoid-break relative ml-7 rounded-xl border border-line bg-card p-3.5 shadow-card">
              <span aria-hidden="true" className="absolute -left-[3.1rem] top-3 grid size-9 place-items-center rounded-full bg-ink text-sm font-bold text-paper ring-4 ring-paper">
                {i + 1}
              </span>
              <p className="mb-1 flex flex-wrap items-center gap-2">
                <span className="sr-only">{t.plan.step(i + 1)}: </span>
                <span className={cn("inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-sm font-semibold", prepare ? "bg-paper-deep text-ink" : online ? "bg-leaf-soft text-leaf-deep" : "bg-amber-soft text-amber-ink")}>
                  {online || prepare ? <Globe className="size-4" aria-hidden="true" /> : <MapPin className="size-4" aria-hidden="true" />}
                  {prepare ? t.plan.prepare : online ? t.plan.online : t.plan.offline}
                </span>
                {s.scheme_names.length > 0 && (
                  <span className="text-sm font-medium text-ink-soft">
                    {t.plan.stepFor} {s.scheme_names.join(", ")}
                  </span>
                )}
              </p>
              <p className="text-[1.05rem] font-semibold">{s.action}</p>
              {(s.where || s.group) && (
                <p className="mt-1 flex items-start gap-1.5 text-[0.98rem] text-ink-soft">
                  <MapPin className="mt-1 size-4 shrink-0" aria-hidden="true" />
                  <span>
                    <span className="font-semibold">{t.plan.where}:</span> {s.where || s.group}
                  </span>
                </p>
              )}
              {(s.source_urls.length ? s.source_urls : s.source_url ? [s.source_url] : []).map((u) => (
                <ExternalLink key={u} href={u}>{t.plan.source}</ExternalLink>
              ))}
            </FadeUp>
          );
        })}
      </ol>
    </Section>
  );
}

// ---------- ways to apply (routes) ----------

function UnofficialNote() {
  const { t } = useLang();
  return (
    <p role="note" className="mt-2 flex items-start gap-2 rounded-lg border border-marigold/60 bg-amber-soft px-3 py-2 text-[0.98rem] font-semibold text-amber-ink">
      <ShieldQuestion className="mt-0.5 size-5 shrink-0" aria-hidden="true" />
      {t.plan.unofficial}
    </p>
  );
}

function SchemeRoutes({ scheme, index }: { scheme: PlanScheme; index: number }) {
  const { t } = useLang();
  const rec = Math.max(0, scheme.routes.findIndex((r) => r.recommended));
  const [picked, setPicked] = useState<number | null>(null);
  const route = scheme.routes[picked ?? rec];
  const uid = `routes-${scheme.scheme_id}`;
  if (!route) return null;
  return (
    <FadeUp as="li" index={index} className="plan-card print-avoid-break rounded-xl border border-line bg-card p-3.5 shadow-card">
      <h3 className="text-lg font-bold">{scheme.scheme_name}</h3>
      {!scheme.source_official && <UnofficialNote />}
      <div role="group" aria-label={`${t.plan.waysToApply}: ${scheme.scheme_name}`} className="no-print mt-2 flex flex-wrap gap-2">
        {scheme.routes.map((r, i) => {
          const on = i === (picked ?? rec);
          return (
            <button
              key={r.mode}
              type="button"
              aria-pressed={on}
              aria-controls={`${uid}-panel`}
              onClick={() => setPicked(i)}
              className={cn(
                "inline-flex min-h-11 flex-col items-start justify-center rounded-xl border-2 px-3.5 py-1.5 text-left font-semibold transition-colors",
                on ? "border-ink bg-ink text-paper" : "border-line bg-card text-ink hover:border-ink/50",
              )}
            >
              <span className="inline-flex items-center gap-1.5">
                {r.mode === "online" ? <Globe className="size-4" aria-hidden="true" /> : <MapPin className="size-4" aria-hidden="true" />}
                {r.mode === "online" ? t.plan.online : t.plan.inPerson}
              </span>
              {r.recommended && (
                <span className={cn("text-sm font-bold", on ? "text-marigold" : "text-leaf-deep")}>
                  <CheckCircle2 className="mr-1 inline size-3.5" aria-hidden="true" />
                  {t.plan.easierForYou}
                </span>
              )}
            </button>
          );
        })}
      </div>
      <div id={`${uid}-panel`} className="mt-3">
        <p className="print-only text-sm font-semibold">{route.mode === "online" ? t.plan.online : t.plan.inPerson}</p>
        <p className="text-[1.05rem] font-semibold">{route.summary}</p>
        {route.where && (
          <p className="mt-1 flex items-start gap-1.5 text-[0.98rem] text-ink-soft">
            <MapPin className="mt-1 size-4 shrink-0" aria-hidden="true" />
            <span>
              <span className="font-semibold">{t.plan.where}:</span> {route.where}
            </span>
          </p>
        )}
        {route.steps.length > 1 && (
          <>
            <Disclosure title={t.plan.showSteps(route.steps.length)} className="no-print" triggerClassName="text-[0.98rem] text-ink">
              <ol className="ml-5 list-decimal space-y-1.5 text-[0.98rem]">
                {route.steps.map((st, i) => (
                  <li key={`${st.n}-${i}`}>{st.action}</li>
                ))}
              </ol>
            </Disclosure>
            <ol className="print-only ml-5 list-decimal text-sm">
              {route.steps.map((st, i) => (
                <li key={`${st.n}-${i}`}>{st.action}</li>
              ))}
            </ol>
          </>
        )}
        {scheme.source_url && <ExternalLink href={scheme.source_url}>{t.plan.source}</ExternalLink>}
      </div>
    </FadeUp>
  );
}

function Routes({ plan }: { plan: PlanResponse }) {
  const { t } = useLang();
  const prepare = plan.steps.filter((s) => s.group_kind === "prepare");
  const schemes = plan.schemes.filter((c) => c.routes.length);
  if (!schemes.length && !prepare.length) return null;
  return (
    <Section icon={<ClipboardList className="size-6" />} title={t.plan.stepsTitle} hint={t.plan.stepsHint}>
      {prepare.map((s, i) => (
        <FadeUp key={`prep-${i}`} index={i} className="plan-card print-avoid-break rounded-xl border border-line bg-paper-deep/60 p-3.5">
          <p className="mb-1 inline-flex items-center gap-1.5 rounded-full bg-paper-deep px-2.5 py-0.5 text-sm font-semibold text-ink">
            <Globe className="size-4" aria-hidden="true" />
            {t.plan.prepare}
          </p>
          <p className="text-[1.05rem] font-semibold">{s.action}</p>
        </FadeUp>
      ))}
      <ul className="space-y-3">
        {schemes.map((c, i) => (
          <SchemeRoutes key={c.scheme_id} scheme={c} index={i} />
        ))}
      </ul>
    </Section>
  );
}

// ---------- where to go ----------

const TRIP_ICON: Record<TripKey, LucideIcon> = {
  bank: Landmark,
  post_office: Mail,
  csc: Store,
  panchayat: Home,
  hospital: Hospital,
  online: Globe,
  office: Building,
  other: MapPin,
};

function CallLink({ num, label }: { num: string; label?: string }) {
  const { t } = useLang();
  return (
    <a
      href={`tel:${num}`}
      className="inline-flex min-h-11 items-center gap-1.5 rounded-lg font-bold text-ink underline decoration-marigold decoration-2 underline-offset-4"
      aria-label={t.plan.call(label ?? num)}
    >
      <Phone className="size-4" aria-hidden="true" />
      {label ?? num}
    </a>
  );
}

function WhereToGo({ plan }: { plan: PlanResponse }) {
  const { t } = useLang();
  const trips = tripsOf(plan);
  const help = plan.where_to_go.filter((w) => w.grievance || w.helpline);
  if (!trips.length && !help.length) return null;
  return (
    <Section icon={<MapPin className="size-6" />} title={t.plan.wtgTitle} hint={trips.length ? t.plan.wtgHint : undefined}>
      <ul className="grid gap-3 sm:grid-cols-2">
        {trips.map((trip, i) => {
          const Icon = TRIP_ICON[trip.key];
          return (
            <FadeUp as="li" key={`${trip.key}-${i}`} index={i} className="plan-card print-avoid-break flex flex-col rounded-xl border border-line bg-card p-4 shadow-card">
              <h3 className="flex items-center gap-2.5 text-lg font-bold">
                <span className="grid size-10 shrink-0 place-items-center rounded-full bg-marigold-soft text-saffron" aria-hidden="true">
                  <Icon className="size-5" />
                </span>
                {t.plan.trips[trip.key]}
              </h3>
              <p className="mt-2 text-sm font-semibold text-ink-soft">{t.plan.covers}:</p>
              <ul className="mt-1 list-disc space-y-0.5 pl-5 text-[0.98rem]">
                {trip.schemes.map((s) => (
                  <li key={s.id}>{s.name}</li>
                ))}
              </ul>
              <div className="no-print mt-3 flex flex-wrap gap-2">
                {trip.points
                  .filter((p) => p.locatorUrl)
                  .slice(0, 2)
                  .map((p) => (
                    <a key={p.name + p.locatorUrl} href={p.locatorUrl!} target="_blank" rel="noopener noreferrer" className={buttonVariants({ variant: "outline", size: "sm" })}>
                      <MapPin aria-hidden="true" />
                      {t.plan.findNearest}
                      <span className="sr-only">
                        {" "}
                        ({p.name}) {t.common.opensNew}
                      </span>
                    </a>
                  ))}
              </div>
            </FadeUp>
          );
        })}
      </ul>
      {help.length > 0 && (
        <div className="plan-card print-avoid-break rounded-xl border border-line bg-card/70 p-4">
          <h3 className="flex items-center gap-2 text-lg font-bold">
            <LifeBuoy className="size-5 text-saffron" aria-hidden="true" />
            {t.plan.helpTitle}
          </h3>
          <ul className="mt-2 space-y-3">
            {help.map((w) => {
              const gNum = phoneOf(w.grievance?.url_or_number);
              const gUrl = safeHttpUrl(w.grievance?.url_or_number);
              const hNum = phoneOf(w.helpline);
              return (
                <li key={w.scheme_id}>
                  <p className="font-semibold">{w.scheme_name}</p>
                  <div className="flex flex-wrap items-center gap-x-4">
                    {w.grievance && (
                      <span className="flex flex-wrap items-center gap-x-2 text-[0.98rem] text-ink-soft">
                        {t.plan.complaint}: {w.grievance.text}
                        {gUrl && <ExternalLink href={gUrl}>{t.plan.source}</ExternalLink>}
                        {gNum && <CallLink num={gNum} />}
                        {!gUrl && !gNum && w.grievance.url_or_number && <span className="font-semibold text-ink">{w.grievance.url_or_number}</span>}
                      </span>
                    )}
                    {w.helpline && (
                      <span className="flex flex-wrap items-center gap-x-2 text-[0.98rem] text-ink-soft">
                        {t.plan.helpline}: {hNum ? <CallLink num={hNum} label={w.helpline} /> : <span className="font-semibold text-ink">{w.helpline}</span>}
                      </span>
                    )}
                  </div>
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </Section>
  );
}

// ---------- watch-outs ----------

function Careful({ plan, nameOf }: { plan: PlanResponse; nameOf: (s: string) => string }) {
  const { t } = useLang();
  const items = orderWatchOuts(plan.watch_outs);
  return (
    <Section icon={<AlertTriangle className="size-6" />} title={`⚠️ ${t.plan.carefulTitle}`} hint={items.length ? t.plan.carefulHint : t.plan.noWatchOuts}>
      <ul className="space-y-2.5">
        {items.map((w, i) => (
          <FadeUp
            as="li"
            key={`${w.scheme_id}-${i}`}
            index={i}
            className={cn("plan-card print-avoid-break rounded-xl border p-3.5", w.personal === true ? "border-2 border-brick bg-brick-soft" : "border-marigold/50 bg-amber-soft")}
          >
            {w.personal === true && (
              <p className="mb-1.5 inline-flex items-center gap-1.5 rounded-full bg-brick px-2.5 py-0.5 text-sm font-bold text-white">
                <UserRound className="size-4" aria-hidden="true" />
                {t.plan.forYou}
              </p>
            )}
            <p className="flex items-start gap-2 text-[1.02rem] font-semibold text-ink">
              <AlertTriangle className={cn("mt-1 size-5 shrink-0", w.personal === true ? "text-brick" : "text-amber-ink")} aria-hidden="true" />
              <span>{w.text}</span>
            </p>
            {w.scheme_id && <p className="mt-1 pl-7 text-sm text-ink-soft">{nameOf(w.scheme_id)}</p>}
            {w.quote && (
              <>
                <Disclosure title={t.plan.quote} className="no-print pl-5" triggerClassName="text-[0.95rem] text-ink-soft">
                  <blockquote className="border-l-4 border-marigold pl-3 text-[0.98rem] italic">{w.quote}</blockquote>
                </Disclosure>
                <blockquote className="print-only mt-1 border-l-4 border-black pl-3 text-sm italic">{w.quote}</blockquote>
              </>
            )}
          </FadeUp>
        ))}
      </ul>
    </Section>
  );
}

// ---------- the page body ----------

function ShareBar({ plan, checked }: { plan: PlanResponse; checked: string[] }) {
  const { t } = useLang();
  const href = whatsappLink(buildShareText(plan, t, checked));
  return (
    <div className="no-print flex flex-wrap gap-2">
      <a href={href} target="_blank" rel="noopener noreferrer" className={cn(buttonVariants({ variant: "primary" }), "bg-leaf-deep hover:bg-leaf")}>
        <MessageCircle aria-hidden="true" />
        {t.plan.whatsapp}
        <span className="sr-only"> {t.common.opensNew}</span>
      </a>
      <Button variant="outline" onClick={() => window.print()}>
        <Printer aria-hidden="true" />
        {t.plan.print}
      </Button>
    </div>
  );
}

function ReadyPlan({ plan, ids }: { plan: PlanResponse; ids: string[] }) {
  const { t } = useLang();
  const id = planId(ids);
  // Mounted only after the plan arrived (client side), so reading localStorage here cannot cause a hydration mismatch.
  const [checked, setChecked] = useState<string[]>(() => loadChecked(id));
  const nameOf = useMemo(() => {
    const m = new Map<string, string>();
    for (const w of plan.where_to_go) m.set(w.scheme_id, w.scheme_name);
    for (const s of plan.steps) s.scheme_ids.forEach((id, i) => { if (s.scheme_names[i]) m.set(id, s.scheme_names[i]); });
    return (sid: string) => m.get(sid) ?? sid;
  }, [plan]);
  const noData = plan.summary.data_available === false || (!plan.checklist.length && !plan.steps.length);
  if (noData) {
    return (
      <Notice icon={<ClipboardList className="size-7" />} title={t.plan.noDataTitle} body={t.plan.noDataBody}>
        <Link href="/schemes" className={buttonVariants({ variant: "outline" })}>
          {t.nav.schemes}
        </Link>
      </Notice>
    );
  }
  return (
    <div className="space-y-8">
      <ShareBar plan={plan} checked={checked} />
      <Checklist plan={plan} id={id} nameOf={nameOf} checked={checked} setChecked={setChecked} />
      {plan.schemes.length ? <Routes plan={plan} /> : <Steps plan={plan} />}
      <WhereToGo plan={plan} />
      <Careful plan={plan} nameOf={nameOf} />
      <p className="print-only text-sm">{t.plan.printNote}</p>
    </div>
  );
}

export function PlanView({ ids }: { ids: string[] }) {
  const { t } = useLang();
  const [attempt, setAttempt] = useState(0);
  const res = useLoadedPlan(ids, attempt);

  let body: React.ReactNode = null;
  if (!ids.length) {
    body = (
      <Notice icon={<ClipboardList className="size-7" />} title={t.plan.emptyTitle} body={t.plan.emptyBody}>
        <Link href="/" className={buttonVariants({ variant: "accent" })}>
          {t.plan.goAsk}
        </Link>
      </Notice>
    );
  } else if (!res) {
    body = <PlanSkeleton />;
  } else if (res.error) {
    const e = res.error;
    const msg = `${t.chat.errors[e.code] ?? t.plan.errorBody}${e.retryAfter ? ` ${t.chat.retryIn(e.retryAfter)}` : ""}`;
    body = (
      <Notice icon={<AlertTriangle className="size-7" />} title={t.plan.errorTitle} body={msg}>
        <Button variant="primary" onClick={() => setAttempt((a) => a + 1)}>
          <RotateCw aria-hidden="true" />
          {t.plan.retry}
        </Button>
      </Notice>
    );
  } else if (res.plan) {
    body = <ReadyPlan key={res.key} plan={res.plan} ids={ids} />;
  }

  return (
    <div className="mx-auto w-full max-w-3xl px-4 pb-16 pt-6">
      <Link href="/" className="no-print inline-flex min-h-11 items-center gap-1.5 rounded-lg font-semibold text-ink-soft hover:text-ink">
        <ArrowLeft className="size-5" aria-hidden="true" />
        {t.plan.back}
      </Link>
      <h1 className="display mt-2 text-[2rem] sm:text-4xl">{t.plan.title}</h1>
      <p className="mt-2 max-w-xl text-lg text-ink-soft">{t.plan.subtitle}</p>
      {ids.length > 0 && <p className="mt-1 text-sm font-semibold text-ink-soft">{t.plan.forSchemes(ids.length)}</p>}
      <div className="mt-6">{body}</div>
    </div>
  );
}
