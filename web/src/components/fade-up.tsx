"use client";

import * as m from "motion/react-m";

interface Props extends React.HTMLAttributes<HTMLDivElement> {
  /** Position in a list: later items start a little later (staggered entrance). */
  index?: number;
  as?: "div" | "li" | "section" | "article";
}

/** Fade + slide in once. Under prefers-reduced-motion only the fade remains (MotionConfig). */
export function FadeUp({ index = 0, as = "div", children, ...rest }: Props) {
  const Comp = m[as];
  return (
    <Comp
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.32, ease: "easeOut", delay: Math.min(index, 8) * 0.07 }}
      {...(rest as object)}
    >
      {children}
    </Comp>
  );
}
