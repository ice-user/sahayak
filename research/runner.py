"""Start / resume / inspect graph runs. Shared by the CLI, the batch runner and the tests."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any

from langgraph.types import Command

from .review import format_review
from .state import NEEDS_FIX, READY


def thread_id_for(source: str) -> str:
    """Deterministic thread id so re-running the same source finds its pending review."""
    return "r-" + hashlib.sha1(source.strip().encode("utf-8")).hexdigest()[:10]


@dataclass
class Outcome:
    thread_id: str
    status: str                       # ready_for_review | needs_human_fix | approved | rejected | fetch_failed | llm_failed
    paused: bool
    payload: dict | None = None       # review payload when paused
    report: dict = field(default_factory=dict)
    state: dict = field(default_factory=dict)

    @property
    def summary(self) -> str:
        return format_review(self.payload) if self.payload else ""


def _collect(graph, config: dict) -> Outcome:
    snap = graph.get_state(config)
    values = dict(snap.values)
    payload = None
    for t in snap.tasks:
        for i in getattr(t, "interrupts", ()):
            payload = i.value
    paused = bool(snap.next)
    return Outcome(config["configurable"]["thread_id"], values.get("status", ""), paused, payload,
                   values.get("report", {}), values)


def start(graph, source: str, *, source_url: str | None = None, thread_id: str | None = None,
          local_file: bool = False) -> Outcome:
    """Run from the beginning until the human-review interrupt (or a terminal failure).

    Thread ids are deterministic and checkpoints persist, so a thread can already hold a previous run's state
    (a transient fetch/LLM failure, a rejected or approved candidate). The ``fetch`` node therefore resets every
    per-run field on entry: starting a source again always begins from a clean slate. (Choice: reset in the
    graph, not delete the thread, so the checkpoint history of earlier runs stays available for audit.)
    ``source_url`` is always written (empty when not given) so a stale value is never mistaken for an explicit
    one; ``local_file`` must be True for a local path to be read at all (CLI: ``--file``)."""
    config = {"configurable": {"thread_id": thread_id or thread_id_for(source)}}
    init: dict[str, Any] = {"source": source, "source_url": source_url or "", "local_file": bool(local_file)}
    graph.invoke(init, config)
    return _collect(graph, config)


def pending(graph, thread_id: str) -> Outcome | None:
    """Outcome of a thread that is waiting for review, else None."""
    config = {"configurable": {"thread_id": thread_id}}
    out = _collect(graph, config)
    return out if out.paused else None


def resume(graph, thread_id: str, decision: dict) -> Outcome:
    """Send the human's decision ({'action': approve|reject|edit, ...}) and run to the next stop."""
    config = {"configurable": {"thread_id": thread_id}}
    if not _collect(graph, config).paused:
        raise LookupError(f"thread {thread_id!r} is not waiting for review (unknown or already finished)")
    graph.invoke(Command(resume=decision), config)
    return _collect(graph, config)


def exists(graph, thread_id: str) -> bool:
    return bool(graph.get_state({"configurable": {"thread_id": thread_id}}).values)


__all__ = ["Outcome", "start", "resume", "pending", "thread_id_for", "exists", "READY", "NEEDS_FIX"]
