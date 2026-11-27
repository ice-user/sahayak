"use client";

import { useSearchParams } from "next/navigation";
import { parsePlanIds } from "@/lib/plan";
import { PlanView } from "./plan-view";

export function PlanPage() {
  const params = useSearchParams();
  return <PlanView ids={parsePlanIds(params.get("s"))} />;
}
