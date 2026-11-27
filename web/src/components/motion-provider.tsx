"use client";

import { LazyMotion, MotionConfig, domAnimation } from "motion/react";

/** Loads the small animation feature set once; reducedMotion="user" disables movement for people who ask for it. */
export function MotionProvider({ children }: { children: React.ReactNode }) {
  return (
    <MotionConfig reducedMotion="user">
      <LazyMotion features={domAnimation}>{children}</LazyMotion>
    </MotionConfig>
  );
}
