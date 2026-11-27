import type { Metadata } from "next";
import { Suspense } from "react";
import { PlanPage } from "@/components/plan/plan-page";

export const metadata: Metadata = {
  title: "Your apply plan",
  description: "Documents to collect, steps to follow and things to watch out for, for the schemes you can get.",
};

export default function Page() {
  return (
    <Suspense>
      <PlanPage />
    </Suspense>
  );
}
