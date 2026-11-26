import type { Metadata } from "next";
import { SchemeBrowser } from "@/components/schemes/scheme-browser";

export const metadata: Metadata = {
  title: "All schemes",
  description: "Browse central government welfare schemes: pensions, insurance, health, farming, savings and more.",
};

export default function SchemesPage() {
  return <SchemeBrowser />;
}
