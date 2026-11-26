"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { fetchSchemes } from "@/lib/api";
import type { Scheme } from "@/lib/types";

let cache: Promise<Scheme[]> | null = null;

/** Shared, cached GET /api/schemes (retried on next call if it failed). */
export function loadSchemes(): Promise<Scheme[]> {
  if (!cache) {
    cache = fetchSchemes().catch((e) => {
      cache = null;
      throw e;
    });
  }
  return cache;
}

export function useSchemes() {
  const [schemes, setSchemes] = useState<Scheme[] | null>(null);
  const [error, setError] = useState(false);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let alive = true;
    loadSchemes().then(
      (s) => alive && setSchemes(s),
      () => alive && setError(true),
    );
    return () => {
      alive = false;
    };
  }, [attempt]);

  const retry = useCallback(() => {
    setError(false);
    setAttempt((n) => n + 1);
  }, []);
  return { schemes, error, retry };
}

/** Lookup by id; used to enrich result cards with documents / how to apply. */
export function useSchemeIndex(): Map<string, Scheme> | null {
  const { schemes } = useSchemes();
  return useMemo(() => (schemes ? new Map(schemes.map((s) => [s.id, s])) : null), [schemes]);
}
