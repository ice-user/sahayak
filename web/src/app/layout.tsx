import type { Metadata, Viewport } from "next";
import "./globals.css";
import { LangProvider } from "@/components/lang-provider";
import { Header } from "@/components/header";
import { Footer } from "@/components/footer";
import { WakeUp } from "@/components/wake-up";
import { DICTS } from "@/lib/i18n";

const SITE = process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3000";
const en = DICTS.en.meta;

export const metadata: Metadata = {
  metadataBase: new URL(SITE),
  title: { default: en.title, template: "%s | Sahayak" },
  description: en.description,
  applicationName: "Sahayak",
  icons: { icon: "/favicon.svg" },
  openGraph: {
    type: "website",
    siteName: "Sahayak",
    title: en.title,
    description: en.description,
    locale: "en_IN",
    images: [{ url: "/og.png", width: 1200, height: 630, alt: "Sahayak: find government schemes you can get" }],
  },
  twitter: { card: "summary_large_image", title: en.title, description: en.description, images: ["/og.png"] },
};

export const viewport: Viewport = {
  themeColor: "#fbf6ec",
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" data-lang="en">
      <body className="flex min-h-dvh flex-col">
        <WakeUp />
        <LangProvider>
          <Header />
          <main id="main" className="flex-1">
            {children}
          </main>
          <Footer />
        </LangProvider>
      </body>
    </html>
  );
}
