import type { NextConfig } from "next";

const isDev = process.env.NODE_ENV === "development";

/** Origin of the backend the browser may call, mirroring src/lib/config.ts. Empty in mock mode. */
function apiOrigin(): string {
  const raw = (process.env.NEXT_PUBLIC_API_URL ?? "").trim().replace(/\/+$/, "");
  const mock = process.env.NEXT_PUBLIC_MOCK === "1" || (isDev && raw === "" && process.env.NEXT_PUBLIC_MOCK !== "0");
  if (mock) return "";
  try {
    return new URL(raw || "http://localhost:8000").origin;
  } catch {
    return "";
  }
}

/**
 * Content-Security-Policy.
 *
 * script-src keeps 'unsafe-inline': the App Router streams inline <script> tags (hydration data), and
 * nonces would need a proxy that renders every page dynamically, which this mostly-static app avoids.
 * The remaining directives still stop data exfiltration and framing: no remote images or fonts, fetch only
 * to this origin and the API origin, no plugins, no <base>/form hijacking. React escapes text and the chat
 * markdown renderer drops raw HTML and images, so there is no injection sink for inline script anyway.
 * 'unsafe-eval' and websockets are added in `next dev` only (React dev tooling and HMR).
 * Upgrade path: nonces via a Next proxy file, or `experimental.sri` once Turbopack supports it.
 */
function buildCsp(api: string, dev: boolean): string {
  const connect = ["'self'", api, ...(dev ? ["ws://localhost:*", "ws://127.0.0.1:*"] : [])].filter(Boolean);
  return [
    "default-src 'self'",
    `script-src 'self' 'unsafe-inline'${dev ? " 'unsafe-eval'" : ""}`,
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data:",
    "font-src 'self'",
    `connect-src ${connect.join(" ")}`,
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
  ].join("; ");
}

/** STATIC_EXPORT=1 builds a static demo site (use with NEXT_PUBLIC_MOCK=1); headers are then set by the host. */
const staticExport = process.env.STATIC_EXPORT === "1";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  ...(staticExport ? { output: "export" as const, trailingSlash: true, images: { unoptimized: true } } : {}),
  ...(staticExport ? {} : { headers: securityHeaders }),
};

async function securityHeaders() {
    // A production build without NEXT_PUBLIC_API_URL silently points the browser at http://localhost:8000 (and the CSP
    // allows only that). Say so in the log; on Vercel set the variable BEFORE the first build.
    if (!isDev && process.env.NEXT_PUBLIC_MOCK !== "1" && !(process.env.NEXT_PUBLIC_API_URL ?? "").trim()) {
      console.warn("[sahayak] WARNING: NEXT_PUBLIC_API_URL is not set; this build will call http://localhost:8000. Set it and rebuild.");
    }
    return [
      {
        source: "/:path*",
        headers: [
          { key: "Content-Security-Policy", value: buildCsp(apiOrigin(), isDev) },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
        ],
      },
    ];
}

export default nextConfig;
