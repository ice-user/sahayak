"use client";

import { Calculator, FileSearch, Search, ShieldCheck, TriangleAlert, Wrench } from "lucide-react";
import { Disclosure } from "@/components/disclosure";
import { useLang } from "@/components/lang-provider";
import { parseEligibility, parseSearchHits, type AssistantMessage, type ToolStep } from "@/lib/chat-state";
import { fieldLabel, formatFactValue } from "@/lib/rules-text";
import type { Scheme } from "@/lib/types";

const isRecord = (v: unknown): v is Record<string, unknown> => typeof v === "object" && v !== null && !Array.isArray(v);

function Facts({ profile }: { profile: Record<string, unknown> }) {
  const { t } = useLang();
  const entries = Object.entries(profile).filter(([, v]) => v !== null && v !== undefined);
  if (!entries.length) return <p className="text-sm text-ink-soft">{t.trace.noFacts}</p>;
  return (
    <dl className="flex flex-wrap gap-1.5">
      {entries.map(([k, v]) => (
        <div key={k} className="rounded-full border border-line bg-paper px-3 py-0.5 text-[0.92rem]">
          <dt className="inline text-ink-soft">{fieldLabel(t, k)}: </dt>
          <dd className="inline font-semibold">{formatFactValue(t, k, v)}</dd>
        </div>
      ))}
    </dl>
  );
}

function StepShell({ icon, title, children }: { icon: React.ReactNode; title: string; children?: React.ReactNode }) {
  return (
    <li className="relative pl-10">
      <span className="absolute left-0 top-0 grid size-8 place-items-center rounded-full bg-marigold-soft text-saffron" aria-hidden="true">
        {icon}
      </span>
      <p className="pt-0.5 font-semibold">{title}</p>
      {children && <div className="mt-1.5 space-y-2">{children}</div>}
    </li>
  );
}

function Step({ step, index }: { step: ToolStep; index: Map<string, Scheme> | null }) {
  const { t } = useLang();
  const nameOf = (id: string) => index?.get(id)?.name ?? id;

  if (step.failed) {
    const msg = isRecord(step.result) && typeof step.result.error === "string" ? step.result.error : "";
    return (
      <StepShell icon={<TriangleAlert className="size-4" />} title={`${t.trace.failed}`}>
        {msg && <p className="text-sm text-brick">{msg}</p>}
      </StepShell>
    );
  }

  if (step.name === "search_schemes") {
    const hits = parseSearchHits(step.result);
    const q = typeof step.args.query === "string" ? step.args.query : "";
    return (
      <StepShell icon={<Search className="size-4" />} title={t.trace.searched(q)}>
        {hits.length > 0 && (
          <ul className="space-y-1.5" aria-label={t.trace.best}>
            {hits.slice(0, 4).map((h) => (
              <li key={h.scheme_id} className="flex items-center gap-3 text-[0.95rem]">
                <span className="min-w-0 flex-1 truncate">{h.name}</span>
                <span className="h-2 w-16 shrink-0 overflow-hidden rounded-full bg-ink/10" aria-hidden="true">
                  <span className="block h-full rounded-full bg-marigold" style={{ width: `${Math.round(Math.min(1, Math.max(0, h.score)) * 100)}%` }} />
                </span>
                <span className="w-10 shrink-0 text-right text-sm tabular-nums text-ink-soft">{Math.round(h.score * 100)}%</span>
              </li>
            ))}
          </ul>
        )}
      </StepShell>
    );
  }

  if (step.name === "check_eligibility") {
    const profile = isRecord(step.args.profile) ? step.args.profile : {};
    const res = parseEligibility(step.result);
    return (
      <StepShell icon={<Calculator className="size-4" />} title={t.trace.checked}>
        <div>
          <p className="mb-1 text-sm font-semibold text-ink-soft">{t.trace.factsUsed}</p>
          <Facts profile={profile} />
        </div>
        {res && (
          <div className="space-y-1 text-[0.95rem]">
            <p className="font-semibold">{t.trace.outcome(res.eligible.length, res.need_info.length, res.not_eligible.length)}</p>
            <ul className="space-y-0.5 text-ink-soft">
              {res.eligible.map((e) => (
                <li key={e.scheme_id}>
                  <span className="font-semibold text-leaf-deep">{t.trace.eligible}:</span> {e.scheme_name}
                </li>
              ))}
              {res.need_info.map((n) => (
                <li key={n.scheme_id}>
                  <span className="font-semibold text-amber-ink">{t.trace.needInfo}:</span> {n.scheme_name} ({n.missing_fields.map((f) => fieldLabel(t, f)).join(", ")})
                </li>
              ))}
              {res.not_eligible.map((n) => (
                <li key={n.scheme_id}>
                  <span className="font-semibold text-brick">{t.trace.notEligible}:</span> {n.scheme_name ?? nameOf(n.scheme_id)}: {n.reasons.join("; ")}
                </li>
              ))}
            </ul>
          </div>
        )}
        <p className="flex items-start gap-2 rounded-lg bg-leaf-soft px-3 py-2 text-sm text-leaf-deep">
          <ShieldCheck className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
          {t.trace.rulesNote}
        </p>
      </StepShell>
    );
  }

  if (step.name === "get_scheme_details") {
    const id = typeof step.args.scheme_id === "string" ? step.args.scheme_id : "";
    const name = isRecord(step.result) && typeof step.result.name === "string" ? step.result.name : nameOf(id);
    return <StepShell icon={<FileSearch className="size-4" />} title={t.trace.lookedUp(name)} />;
  }

  return <StepShell icon={<Wrench className="size-4" />} title={`${t.trace.unknownTool}: ${step.name}`} />;
}

export function Trace({ message, index }: { message: AssistantMessage; index: Map<string, Scheme> | null }) {
  const { t } = useLang();
  if (!message.steps.length) return null;
  return (
    <Disclosure
      title={t.trace.title}
      icon={<ShieldCheck className="size-5 text-saffron" aria-hidden="true" />}
      className="rounded-xl border border-line bg-card/70 px-3"
    >
      <div className="space-y-4 pb-2">
        <p className="text-[0.95rem] text-ink-soft">{t.trace.intro}</p>
        <ol className="space-y-4">
          {message.steps.map((s, i) => (
            <Step key={`${s.id}-${i}`} step={s} index={index} />
          ))}
        </ol>
        <Disclosure title={t.trace.raw} className="border-t border-line/70" triggerClassName="text-sm text-ink-soft">
          <pre className="max-h-72 overflow-auto rounded-lg bg-ink p-3 text-xs leading-relaxed text-paper" tabIndex={0}>
            {JSON.stringify(message.steps.map((s) => ({ tool: s.name, arguments: s.args, result: s.result })), null, 2)}
          </pre>
        </Disclosure>
        {message.stats && (
          <p className="text-sm text-ink-soft">{t.trace.stats(message.stats.latency_s, message.stats.llm_calls, message.stats.tokens)}</p>
        )}
      </div>
    </Disclosure>
  );
}
