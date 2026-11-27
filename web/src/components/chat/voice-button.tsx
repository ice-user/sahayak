"use client";

import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import { Mic, MicOff } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useLang } from "@/components/lang-provider";
import type { LangCode } from "@/lib/types";

/** Minimal Web Speech API surface (not in lib.dom). */
interface Recognition {
  lang: string;
  interimResults: boolean;
  continuous: boolean;
  onresult: ((e: { results: ArrayLike<ArrayLike<{ transcript: string }> & { isFinal: boolean }> }) => void) | null;
  onerror: ((e: { error: string }) => void) | null;
  onend: (() => void) | null;
  start: () => void;
  stop: () => void;
  abort: () => void;
}
type RecognitionCtor = new () => Recognition;

export const SPEECH_LANG: Record<LangCode, string> = { en: "en-IN", hi: "hi-IN", ta: "ta-IN", hinglish: "en-IN" };

function ctor(): RecognitionCtor | null {
  if (typeof window === "undefined") return null;
  const w = window as unknown as { SpeechRecognition?: RecognitionCtor; webkitSpeechRecognition?: RecognitionCtor };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
}

const noopSubscribe = () => () => {};

interface Props {
  disabled?: boolean;
  /** Called with the full transcript so far (interim and final). */
  onTranscript: (text: string) => void;
  onStatus: (message: string) => void;
}

/** Mic button. Renders nothing when the browser has no speech recognition. */
export function VoiceButton({ disabled, onTranscript, onStatus }: Props) {
  const { t, lang } = useLang();
  const supported = useSyncExternalStore(noopSubscribe, () => ctor() !== null, () => false);
  const [listening, setListening] = useState(false);
  const rec = useRef<Recognition | null>(null);

  useEffect(() => () => rec.current?.abort(), []);

  if (!supported) return null;

  const toggle = () => {
    if (listening) {
      rec.current?.stop();
      return;
    }
    const Ctor = ctor();
    if (!Ctor) return;
    const r = new Ctor();
    r.lang = SPEECH_LANG[lang];
    r.interimResults = true;
    r.continuous = false;
    r.onresult = (e) => {
      let text = "";
      for (let i = 0; i < e.results.length; i++) text += e.results[i][0].transcript;
      onTranscript(text.trim());
    };
    r.onerror = (e) => onStatus(e.error === "not-allowed" || e.error === "service-not-allowed" ? t.voice.denied : e.error === "aborted" ? "" : t.voice.error);
    r.onend = () => {
      setListening(false);
      rec.current = null;
    };
    rec.current = r;
    onStatus(t.voice.listening);
    setListening(true);
    try {
      r.start();
    } catch {
      setListening(false);
      onStatus(t.voice.error);
    }
  };

  const label = listening ? t.voice.stop : t.voice.start;
  return (
    <Button
      type="button"
      variant={listening ? "accent" : "outline"}
      size="icon"
      onClick={toggle}
      disabled={disabled}
      aria-label={label}
      aria-pressed={listening}
      title={label}
      className={listening ? "motion-safe:animate-pulse" : undefined}
    >
      {listening ? <MicOff aria-hidden="true" /> : <Mic aria-hidden="true" />}
    </Button>
  );
}
