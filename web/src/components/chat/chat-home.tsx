"use client";

import { useEffect, useRef } from "react";
import { MessageCircleQuestion, RotateCcw, ShieldAlert } from "lucide-react";
import { Button } from "@/components/ui/button";
import { LangChips } from "@/components/lang-chips";
import { useLang } from "@/components/lang-provider";
import { useChat } from "@/hooks/use-chat";
import { useSchemeIndex } from "@/hooks/use-schemes";
import { Composer } from "./composer";
import { MessageList } from "./messages";

export function ChatHome() {
  const { t } = useLang();
  const { state, send, retry, stop, reset } = useChat();
  const index = useSchemeIndex();
  const stick = useRef(true);
  const endRef = useRef<HTMLDivElement>(null);
  const started = state.messages.length > 0;

  useEffect(() => {
    const onScroll = () => {
      const dist = document.documentElement.scrollHeight - (window.scrollY + window.innerHeight);
      stick.current = dist < 220;
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  // Keep the newest content in view while streaming, unless the reader scrolled up.
  const last = state.messages[state.messages.length - 1];
  const signature = last ? `${state.messages.length}:${last.role === "assistant" ? last.text.length + last.steps.length + (last.eligibility ? 1 : 0) + last.suggestions.length + (last.error ? 1 : 0) : 0}` : "";
  useEffect(() => {
    if (!started) return;
    if (last?.role === "user") stick.current = true;
    if (!stick.current) return;
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    endRef.current?.scrollIntoView({ block: "end", behavior: reduce ? "auto" : "smooth" });
  }, [signature, started, last?.role]);

  return (
    <div className="mx-auto w-full max-w-3xl px-4">
      {!started ? (
        <section className="relative pb-6 pt-8 sm:pt-14">
          <div className="dots pointer-events-none absolute inset-x-[-1rem] top-0 -z-10 h-72" aria-hidden="true" />
          <h1 className="display max-w-2xl text-[2.15rem] sm:text-5xl">{t.hero.title}</h1>
          <p className="mt-4 max-w-xl text-lg text-ink-soft">{t.hero.subtitle}</p>
          <LangChips className="mt-6" />
          <div className="mt-8">
            <h2 className="mb-3 flex items-center gap-2 text-base font-bold text-ink-soft">
              <MessageCircleQuestion className="size-5 text-saffron" aria-hidden="true" />
              {t.hero.tryAsking}
            </h2>
            <ul className="grid gap-2.5 sm:grid-cols-2">
              {t.hero.examples.map((q) => (
                <li key={q}>
                  <button
                    type="button"
                    onClick={() => send(q)}
                    disabled={state.busy}
                    className="h-full min-h-14 w-full rounded-2xl border-2 border-line bg-card px-4 py-3 text-left text-[1.02rem] font-medium leading-snug shadow-card transition-colors hover:border-marigold hover:bg-amber-soft/50"
                  >
                    {q}
                  </button>
                </li>
              ))}
            </ul>
          </div>
        </section>
      ) : (
        <div className="flex items-center justify-between gap-3 pb-3 pt-5">
          <h1 className="display text-xl">{t.brand.name}</h1>
          <Button variant="outline" size="sm" onClick={reset}>
            <RotateCcw aria-hidden="true" />
            {t.chat.newChat}
          </Button>
        </div>
      )}

      {started && (
        <MessageList messages={state.messages} index={index} busy={state.busy} onSuggest={send} onRetry={retry} onNewChat={reset} />
      )}
      <div ref={endRef} className="h-4" aria-hidden="true" />

      <div className={started ? "sticky bottom-0 z-10 -mx-4 bg-gradient-to-t from-paper from-75% to-transparent px-4 pb-3 pt-4" : "pb-3 pt-2"}>
        <Composer busy={state.busy} onSend={send} onStop={stop} />
        <p className="mt-2 flex items-center gap-1.5 text-[0.85rem] text-ink-soft">
          <ShieldAlert className="size-4 shrink-0" aria-hidden="true" />
          {t.chat.privacy}
        </p>
      </div>
    </div>
  );
}
