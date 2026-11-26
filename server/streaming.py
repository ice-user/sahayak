"""Bridge a blocking Agent turn (worker thread) to async consumers."""
from __future__ import annotations

import asyncio
import threading
from typing import Any, AsyncIterator, Callable

from sahayak.agent import Agent, Trace
from sahayak.llm import TurnCancelled

PING = "ping"
FINISHED = "finished"


class Cancelled(TurnCancelled):
    """Raised inside the worker when the consumer went away; aborts the turn and rolls back history."""


class AgentRun:
    """Runs `agent.chat(message)` in a daemon thread and exposes its events as an async iterator.

    `events()` yields (kind, data) pairs: the agent's tool_call / tool_result / answer events, then
    (FINISHED, Trace). If the agent raises, `events()` re-raises that exception. While waiting longer than
    `keepalive_s` it yields (PING, {}). `on_finished` is called once on the event loop: when the terminal event
    is about to be delivered, or when the thread ends (even after cancel) if nobody is listening.
    That is when the session may accept its next message.
    """

    def __init__(self, agent: Agent, message: str, on_finished: Callable[[], None], keepalive_s: float = 15.0):
        self._agent = agent
        self._message = message
        self._on_finished = on_finished
        self._keepalive_s = keepalive_s
        self._loop = asyncio.get_running_loop()
        self._queue: asyncio.Queue[tuple[str, Any]] = asyncio.Queue()
        self._cancelled = threading.Event()
        self._released = False

    def release(self) -> None:
        """Run `on_finished` exactly once. Event-loop thread only. `events()` calls it BEFORE handing out the
        terminal event, so a client that retries the instant it sees `done`/`error` finds the session free."""
        if not self._released:
            self._released = True
            self._on_finished()

    def start(self) -> "AgentRun":
        threading.Thread(target=self._work, name="agent-turn", daemon=True).start()
        return self

    def cancel(self) -> None:
        self._cancelled.set()

    def _post(self, item: tuple[str, Any]) -> None:
        try:
            self._loop.call_soon_threadsafe(self._queue.put_nowait, item)
        except RuntimeError:  # loop already closed (server shutdown)
            pass

    def _emit(self, kind: str, data: dict) -> None:
        if self._cancelled.is_set():
            raise Cancelled()
        self._post((kind, data))

    def _work(self) -> None:
        try:
            _, trace = self._agent.chat(self._message, on_event=self._emit, cancelled=self._cancelled.is_set)
            self._post((FINISHED, trace))
        except BaseException as exc:  # delivered to the consumer, never lost in the thread
            self._post(("error", exc))
        finally:
            try:
                self._loop.call_soon_threadsafe(self.release)
            except RuntimeError:
                pass

    async def events(self) -> AsyncIterator[tuple[str, Any]]:
        while True:
            try:
                kind, data = await asyncio.wait_for(self._queue.get(), self._keepalive_s)
            except asyncio.TimeoutError:
                yield PING, {}
                continue
            if kind == "error":
                self.release()
                raise data
            if kind == FINISHED:
                self.release()
                yield kind, data
                return
            yield kind, data


def trace_stats(trace: Trace) -> tuple[int, int]:
    """(llm_calls, total_tokens) for a finished turn."""
    llm = trace.llm_steps()
    return len(llm), sum(s.get("tokens") or 0 for s in llm)
