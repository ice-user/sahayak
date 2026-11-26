"use client";

import { useEffect } from "react";
import { wakeServer } from "@/lib/api";

/** Renders nothing; on first load pings the backend so a sleeping free-tier instance starts early. */
export function WakeUp() {
  useEffect(() => {
    void wakeServer();
  }, []);
  return null;
}
