import type { Metadata } from "next";
import { SchemeDetail } from "@/components/schemes/scheme-detail";
import raw from "@/data/schemes.json";

/** Pre-render every known scheme (also required for the static demo export). */
export function generateStaticParams() {
  return (raw as { schemes: { id: string }[] }).schemes.map((s) => ({ id: s.id }));
}

export const metadata: Metadata = {
  title: "Scheme details",
  description: "Benefits, who can get it, documents to carry and how to apply, with the official source.",
};

export default async function SchemeDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <SchemeDetail id={id} />;
}
