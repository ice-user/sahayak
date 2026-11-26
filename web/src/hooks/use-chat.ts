"use client";

import { useCallback, useEffect, useReducer, useRef } from "react";
import { ApiError, chatStream, resetSession } from "@/lib/api";
import {
  chatReducer,
  initialChatState,
  lastUserText,
  type ChatState,
} from "@/lib/chat-state";
import { parseStored, serializeStored, STORAGE_KEY, type StoredChat } from "@/lib/storage";

const MAX_LEN = 2000;
/** If the first stream event takes longer than this, tell the user the server is waking up. */
export const WAKE_DELAY_MS = 8000;
const LEGACY_KEYS = ["sahayak.session", "sahayak.messages"];

function readStorage(): StoredChat | null {
  try {
    for (const k of LEGACY_KEYS) sessionStorage.removeItem(k); // pre-versioned entries: never trusted
    const raw = sessionStorage.getItem(STORAGE_KEY);
    const parsed = parseStored(raw);
    if (raw && !parsed) sessionStorage.removeItem(STORAGE_KEY); // stale, old shape or corrupt
    return parsed;
  } catch {
    return null;
  }
}

function writeStorage(state: ChatState) {
  try {
    if (state.busy) return; // persist only settled conversations
    if (state.messages.length || state.sessionId) {
      sessionStorage.setItem(STORAGE_KEY, serializeStored({ sessionId: state.sessionId, messages: state.messages }));
    } else sessionStorage.removeItem(STORAGE_KEY);
  } catch {
    /* private mode / quota: the chat still works, it just will not survive a reload */
  }
}

let idCounter = 0;
const nextId = () => `${Date.now().toString(36)}-${(idCounter++).toString(36)}`;

export function useChat() {
  const [state, dispatch] = useReducer(chatReducer, initialChatState);
  const stateRef = useRef(state);
  useEffect(() => {
    stateRef.current = state;
  });
  const abortRef = useRef<AbortController | null>(null);
  const hydrated = useRef(false);
  const inFlight = useRef(false); // synchronous guard against double taps

  useEffect(() => {
    const saved = readStorage();
    if (saved) {
      // A message left mid-stream by a reload can never finish (the server rolls it back): mark it stopped.
      const messages = saved.messages.map((m) =>
        m.role === "assistant" && m.streaming ? { ...m, streaming: false, activity: null, stopped: true } : m,
      );
      dispatch({ type: "restore", sessionId: saved.sessionId, messages });
    }
    hydrated.current = true;
    return () => abortRef.current?.abort();
  }, []);

  useEffect(() => {
    if (hydrated.current) writeStorage(state);
  }, [state]);

  const run = useCallback(async (text: string) => {
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    inFlight.current = true;
    dispatch({ type: "send", text, userId: nextId(), assistantId: nextId() });
    let finished = false;
    let answered = false; // a complete answer arrived: a later drop is not a failure
    let wakeTimer: ReturnType<typeof setTimeout> | undefined = setTimeout(() => {
      if (!ctrl.signal.aborted) dispatch({ type: "waking" });
    }, WAKE_DELAY_MS);
    const clearWake = () => {
      if (wakeTimer !== undefined) clearTimeout(wakeTimer);
      wakeTimer = undefined;
    };
    try {
      for await (const event of chatStream(text, stateRef.current.sessionId, ctrl.signal)) {
        clearWake();
        if (ctrl.signal.aborted) return;
        if (event.type === "answer") answered = true;
        if (event.type === "done" || event.type === "error") finished = true;
        dispatch({ type: "event", event });
        if (finished) break;
      }
      if (!finished && !ctrl.signal.aborted) {
        if (answered) dispatch({ type: "end" });
        else dispatch({ type: "fail", message: "Connection closed early", code: "network" });
      }
    } catch (e) {
      if (ctrl.signal.aborted) return;
      if (answered && !(e instanceof ApiError)) {
        dispatch({ type: "end" });
        return;
      }
      if (e instanceof ApiError) dispatch({ type: "fail", message: e.message, code: e.code, retryAfter: e.retryAfter });
      else dispatch({ type: "fail", message: e instanceof Error ? e.message : "Unknown error", code: "network" });
    } finally {
      clearWake();
      if (abortRef.current === ctrl) inFlight.current = false;
    }
  }, []);

  const send = useCallback(
    (raw: string): boolean => {
      const text = raw.trim().slice(0, MAX_LEN);
      if (!text || inFlight.current) return false;
      void run(text);
      return true;
    },
    [run],
  );

  const retry = useCallback(() => {
    const s = stateRef.current;
    if (inFlight.current) return;
    const text = lastUserText(s);
    if (!text) return;
    dispatch({ type: "discard_error" });
    void run(text);
  }, [run]);

  const stop = useCallback(() => {
    abortRef.current?.abort();
    inFlight.current = false;
    dispatch({ type: "end", stopped: true });
  }, []);

  const reset = useCallback(() => {
    abortRef.current?.abort();
    inFlight.current = false;
    const sid = stateRef.current.sessionId;
    dispatch({ type: "reset" });
    if (sid) void resetSession(sid);
  }, []);

  return { state, send, retry, stop, reset };
}
