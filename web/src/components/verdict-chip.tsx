"use client";

import * as m from "motion/react-m";
import { BadgeCheck, CircleHelp, XCircle } from "lucide-react";
import { useLang } from "@/components/lang-provider";
import { cn } from "@/lib/utils";

const KINDS = {
  eligible: { Icon: BadgeCheck, cls: "bg-leaf text-white" },
  needInfo: { Icon: CircleHelp, cls: "bg-amber-soft text-amber-ink ring-1 ring-marigold/60" },
  notEligible: { Icon: XCircle, cls: "bg-brick-soft text-brick ring-1 ring-brick/30" },
} as const;

/** Verdict as icon + words + colour, so it never relies on colour alone. */
export function VerdictChip({ kind, className }: { kind: keyof typeof KINDS; className?: string }) {
  const { t } = useLang();
  const { Icon, cls } = KINDS[kind];
  return (
    <m.span
      initial={{ opacity: 0, scale: 0.8 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ type: "spring", stiffness: 420, damping: 20, delay: 0.12 }}
      className={cn("inline-flex items-center gap-1.5 rounded-full px-3 py-0.5 text-sm font-semibold", cls, className)}
    >
      <Icon className="size-4" aria-hidden="true" />
      {t.verdict[kind]}
    </m.span>
  );
}
