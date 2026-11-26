"use client";

import { useState } from "react";
import { ChevronDown } from "lucide-react";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { cn } from "@/lib/utils";

interface Props {
  title: React.ReactNode;
  icon?: React.ReactNode;
  children: React.ReactNode;
  defaultOpen?: boolean;
  className?: string;
  triggerClassName?: string;
}

/** Accessible expandable section (Radix Collapsible) with a 44px+ trigger. */
export function Disclosure({ title, icon, children, defaultOpen = false, className, triggerClassName }: Props) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <Collapsible open={open} onOpenChange={setOpen} className={className}>
      <CollapsibleTrigger
        className={cn(
          "group flex min-h-11 w-full items-center gap-2 rounded-lg py-1.5 text-left text-base font-semibold",
          triggerClassName,
        )}
      >
        {icon}
        <span className="flex-1">{title}</span>
        <ChevronDown className={cn("size-5 shrink-0 transition-transform", open && "rotate-180")} aria-hidden="true" />
      </CollapsibleTrigger>
      <CollapsibleContent className="pb-2 pt-1">{children}</CollapsibleContent>
    </Collapsible>
  );
}
