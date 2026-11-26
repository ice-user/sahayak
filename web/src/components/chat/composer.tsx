"use client";

import { useEffect, useRef, useState } from "react";
import { SendHorizontal, Square } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useLang } from "@/components/lang-provider";

interface Props {
  busy: boolean;
  onSend: (text: string) => boolean;
  onStop: () => void;
}

export function Composer({ busy, onSend, onStop }: Props) {
  const { t } = useLang();
  const [value, setValue] = useState("");
  const ref = useRef<HTMLTextAreaElement>(null);
  const wasBusy = useRef(false);

  // Return focus to the field when a reply finishes, so keyboard users can carry on.
  useEffect(() => {
    if (wasBusy.current && !busy) ref.current?.focus({ preventScroll: true });
    wasBusy.current = busy;
  }, [busy]);

  // Auto-grow up to ~5 lines.
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 150)}px`;
  }, [value]);

  const submit = () => {
    if (onSend(value)) setValue("");
  };

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        submit();
      }}
      className="flex items-end gap-2 rounded-[1.6rem] border-2 border-ink/25 bg-card p-2 shadow-card focus-within:border-ink focus-within:ring-4 focus-within:ring-marigold/40"
    >
      <label htmlFor="chat-input" className="sr-only">
        {t.chat.inputLabel}
      </label>
      <textarea
        id="chat-input"
        ref={ref}
        rows={1}
        value={value}
        maxLength={2000}
        disabled={busy}
        placeholder={t.chat.placeholder}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
            e.preventDefault();
            submit();
          }
        }}
        className="max-h-[150px] min-h-11 flex-1 resize-none self-center bg-transparent px-3 py-2 text-[1.05rem] leading-snug text-ink outline-none focus-visible:outline-none placeholder:text-ink-soft/70 disabled:opacity-60"
      />
      {busy ? (
        <Button type="button" variant="outline" size="icon" onClick={onStop} aria-label={t.chat.stop}>
          <Square className="!size-4 fill-current" aria-hidden="true" />
        </Button>
      ) : (
        <Button type="submit" variant="accent" disabled={!value.trim()} className="shrink-0 !px-4 sm:!px-5" aria-label={t.chat.send}>
          <SendHorizontal aria-hidden="true" />
          <span className="hidden sm:inline">{t.chat.send}</span>
        </Button>
      )}
    </form>
  );
}
