/**
 * Runtime configuration. NEXT_PUBLIC_* values are inlined at build time.
 * Mock mode: NEXT_PUBLIC_MOCK=1, or (in development) NEXT_PUBLIC_API_URL unset.
 */
const apiUrl = (process.env.NEXT_PUBLIC_API_URL ?? "").trim().replace(/\/+$/, "");

export const MOCK: boolean =
  process.env.NEXT_PUBLIC_MOCK === "1" ||
  (process.env.NODE_ENV === "development" && apiUrl === "" && process.env.NEXT_PUBLIC_MOCK !== "0");

export const API_URL: string = apiUrl || "http://localhost:8000";
