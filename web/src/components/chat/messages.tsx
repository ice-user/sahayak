"use client";

import { AlertCircle, CircleSlash, History, RotateCcw, RotateCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useLang } from "@/components/lang-provider";
import { Markdown } from "@/components/markdown";
import type { AssistantMessage, ChatMessage, NoticeMessage, UserMessage } from "@/lib/chat-state";
import type { Profile } from "@/lib/need-info";
import type { Scheme } from "@/lib/types";
import { SchemeResults } from "./scheme-results";
import { Trace } from "./trace";

export function UserBubble({ message }: { message: UserMessage }) {
  const { t } = useLang();
  return (
    <div className="flex justify-end">
      <p className="max-w-[88%] whitespace-pre-wrap break-words rounded-2xl rounded-br-md bg-ink px-4 py-3 text-[1.02rem] text-paper">
        <span className="sr-only">{t.chat.youSaid}: </span>
        {message.text}
      </p>
    </div>
  );
}

function StatusLine({ message }: { message: AssistantMessage }) {
  const { t } = useLang();
  const label = t.chat.status[message.activity ?? "thinking"];
  return (
    <div className="flex items-center gap-3 py-1 text-ink-soft" role="status">
      <span className="flex gap-1" aria-hidden="true">
        <span className="lamp-dot size-2 rounded-full bg-marigold" />
        <span className="lamp-dot size-2 rounded-full bg-marigold" />
        <span className="lamp-dot size-2 rounded-full bg-marigold" />
      </span>
      <span className="font-medium">{label}</span>
    </div>
  );
}

const RETRY_AFTER_CODES = new Set(["rate_limited", "overloaded"]);

function ErrorBox({
  message,
  onRetry,
  onNewChat,
  disabled,
}: {
  message: AssistantMessage;
  onRetry: () => void;
  onNewChat: () => void;
  disabled: boolean;
}) {
  const { t } = useLang();
  const err = message.error!;
  const friendly = t.chat.errors[err.code];
  // Retrying cannot help when the conversation is full (start a new one) or the text is too long (edit it).
  const action = err.code === "session_limit" ? "new" : err.code === "too_large" ? null : "retry";
  return (
    <div role="alert" className="space-y-3 rounded-xl border border-brick/30 bg-brick-soft p-4 text-brick">
      <p className="flex items-start gap-2 font-semibold">
        <AlertCircle className="mt-1 size-5 shrink-0" aria-hidden="true" />
        <span>
          {friendly}
          {RETRY_AFTER_CODES.has(err.code) && err.retryAfter ? ` ${t.chat.retryIn(err.retryAfter)}` : ""}
        </span>
      </p>
      {action === "retry" && (
        <Button variant="outline" size="sm" onClick={onRetry} disabled={disabled} className="border-brick/40 text-brick">
          <RotateCw aria-hidden="true" />
          {t.chat.retry}
        </Button>
      )}
      {action === "new" && (
        <Button variant="outline" size="sm" onClick={onNewChat} className="border-brick/40 text-brick">
          <RotateCcw aria-hidden="true" />
          {t.chat.startNew}
        </Button>
      )}
    </div>
  );
}

export function RestartNotice({ message }: { message: NoticeMessage }) {
  const { t } = useLang();
  void message;
  return (
    <div role="note" className="my-2 rounded-xl border-2 border-dashed border-marigold bg-amber-soft p-4 text-amber-ink">
      <p className="flex items-start gap-2 font-semibold">
        <History className="mt-1 size-5 shrink-0" aria-hidden="true" />
        <span>{t.chat.restarted}</span>
      </p>
    </div>
  );
}

interface AssistantProps {
  message: AssistantMessage;
  index: Map<string, Scheme> | null;
  isLast: boolean;
  busy: boolean;
  onSuggest: (text: string) => void;
  onRetry: () => void;
  onNewChat: () => void;
  profile?: Profile;
  userText?: string;
}

export function AssistantBlock({ message, index, isLast, busy, onSuggest, onRetry, onNewChat, profile, userText }: AssistantProps) {
  const { t } = useLang();
  const showStatus = message.streaming && !message.error;
  return (
    <div className="space-y-4" aria-busy={message.streaming}>
      {message.text && (
        <div className="rounded-2xl rounded-bl-md border border-line bg-card px-4 py-3.5 text-[1.02rem] shadow-card sm:px-5">
          <span className="sr-only">{t.chat.assistantSaid}: </span>
          <Markdown>{message.text}</Markdown>
        </div>
      )}
      {showStatus && <StatusLine message={message} />}
      {message.eligibility && <SchemeResults result={message.eligibility} index={index} profile={profile} userText={userText} />}
      {isLast && !busy && !message.error && message.suggestions.length > 0 && (
        <div role="group" aria-label={t.chat.quickReplies} className="flex flex-wrap gap-2">
          {message.suggestions.map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => onSuggest(s)}
              className="min-h-11 rounded-full border-2 border-marigold bg-marigold-soft/60 px-4 text-base font-semibold text-ink transition-colors hover:bg-marigold-soft"
            >
              {s}
            </button>
          ))}
        </div>
      )}
      {message.stopped && (
        <p role="status" className="flex items-start gap-2 rounded-lg bg-paper-2 px-3 py-2 text-[0.95rem] font-medium text-ink-soft">
          <CircleSlash className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
          {t.chat.stopped}
        </p>
      )}
      {message.error && <ErrorBox message={message} onRetry={onRetry} onNewChat={onNewChat} disabled={busy} />}
      {!message.streaming && <Trace message={message} index={index} />}
    </div>
  );
}

/** The facts the assistant used in this message's latest eligibility check. */
function profileOf(m: AssistantMessage): Profile {
  for (let i = m.steps.length - 1; i >= 0; i--) {
    const s = m.steps[i];
    if (s.name === "check_eligibility" && typeof s.args.profile === "object" && s.args.profile !== null && !Array.isArray(s.args.profile)) {
      return s.args.profile as Profile;
    }
  }
  return {};
}

export function MessageList({
  messages,
  index,
  busy,
  onSuggest,
  onRetry,
  onNewChat,
}: {
  messages: ChatMessage[];
  index: Map<string, Scheme> | null;
  busy: boolean;
  onSuggest: (text: string) => void;
  onRetry: () => void;
  onNewChat: () => void;
}) {
  const { t } = useLang();
  // Everything before the last restart notice belongs to a conversation the server no longer remembers.
  const lastNotice = messages.findLastIndex((m) => m.role === "notice");
  // Cumulative user text before each message (drives which "might get" schemes are relevant).
  const userTexts: string[] = [];
  messages.reduce((acc, m) => {
    const next = m.role === "user" ? `${acc} ${m.text}` : acc;
    userTexts.push(next);
    return next;
  }, "");
  return (
    <div role="log" aria-live="polite" aria-relevant="additions" aria-label={t.chat.inputLabel} className="space-y-5">
      {messages.map((m, i) => {
        if (m.role === "notice") return <RestartNotice key={m.id} message={m} />;
        const stale = i < lastNotice;
        const node =
          m.role === "user" ? (
            <UserBubble message={m} />
          ) : (
            <AssistantBlock
              message={m}
              index={index}
              isLast={i === messages.length - 1}
              busy={busy}
              onSuggest={onSuggest}
              onRetry={onRetry}
              onNewChat={onNewChat}
              profile={profileOf(m)}
              userText={userTexts[i]}
            />
          );
        return (
          <div key={m.id} className={stale ? "opacity-75 saturate-50" : undefined} {...(stale ? { "aria-label": t.chat.earlier, role: "group" } : {})}>
            {node}
          </div>
        );
      })}
    </div>
  );
}
