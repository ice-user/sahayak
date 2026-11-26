import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const badgeVariants = cva("inline-flex items-center gap-1.5 rounded-full px-3 py-0.5 text-sm font-semibold", {
  variants: {
    tone: {
      leaf: "bg-leaf text-white",
      leafSoft: "bg-leaf-soft text-leaf-deep",
      amber: "bg-amber-soft text-amber-ink",
      neutral: "bg-ink/7 text-ink-soft",
      brick: "bg-brick-soft text-brick",
    },
  },
  defaultVariants: { tone: "neutral" },
});

export function Badge({ className, tone, ...props }: React.HTMLAttributes<HTMLSpanElement> & VariantProps<typeof badgeVariants>) {
  return <span className={cn(badgeVariants({ tone }), className)} {...props} />;
}
