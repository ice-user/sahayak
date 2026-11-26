import type { Metadata } from "next";
import { AboutContent } from "@/components/about-content";

export const metadata: Metadata = {
  title: "How it works",
  description:
    "Sahayak uses AI to collect facts and fixed rules to decide eligibility. Sources, privacy and a clear disclaimer: Sahayak is an independent project, not a government service.",
};

export default function AboutPage() {
  return <AboutContent />;
}
