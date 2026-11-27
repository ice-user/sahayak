import { cn } from "@/lib/utils";

/** Pulsing placeholder block. Decorative: pair it with a role="status" label for screen readers. */
export function Skeleton({ className }: { className?: string }) {
  return <div aria-hidden="true" className={cn("skeleton rounded-xl bg-ink/10", className)} />;
}
