"""LangGraph wiring for the scheme-research agent.

    fetch -> extract -> verify_evidence -> validate -> route --(errors, attempts left)--> extract
                                                         |--(no errors, not yet audited)--> verify_semantics -> route
                                                         |--(ok and audited, or out of attempts)--> human_review
    human_review --approve/reject--> write -> END
                 --edit----------> apply_edit -> route (re-validated; never goes back to the LLM)
                 --invalid-------> human_review
    fetch/extract fatal errors --> write (records a 'failed' report)
"""
from __future__ import annotations

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from .nodes import Deps, make_nodes
from .state import AUDITING, RETRYING, ResearchState


def build_graph(deps: Deps | None = None, checkpointer: BaseCheckpointSaver | None = None):
    """Compile the research graph. A checkpointer is required for human review (interrupt/resume)."""
    deps = deps or Deps()
    n = make_nodes(deps)
    g = StateGraph(ResearchState)
    for name, fn in n.items():
        g.add_node(name, fn)

    g.add_edge(START, "fetch")
    g.add_conditional_edges("fetch", lambda s: "write" if s.get("fatal") else "extract",
                            {"write": "write", "extract": "extract"})
    g.add_conditional_edges("extract", lambda s: "write" if s.get("fatal") else "verify_evidence",
                            {"write": "write", "verify_evidence": "verify_evidence"})
    g.add_edge("verify_evidence", "validate")
    g.add_edge("validate", "route")
    g.add_conditional_edges("route", lambda s: {RETRYING: "extract", AUDITING: "verify_semantics"}.get(
        s["status"], "human_review"),
        {"extract": "extract", "verify_semantics": "verify_semantics", "human_review": "human_review"})
    g.add_edge("verify_semantics", "route")
    g.add_conditional_edges("human_review", lambda s: {"edit": "apply_edit", "invalid": "human_review"}.get(
        s["decision"]["action"], "write"),
        {"apply_edit": "apply_edit", "human_review": "human_review", "write": "write"})
    g.add_edge("apply_edit", "route")
    g.add_edge("write", END)
    return g.compile(checkpointer=checkpointer or MemorySaver())


def sqlite_checkpointer(path: str):
    """Persistent checkpointer so a paused review can be resumed from another process/day.
    Falls back to MemorySaver (with no cross-process resume) if langgraph-checkpoint-sqlite is missing."""
    import sqlite3
    from pathlib import Path

    try:
        from langgraph.checkpoint.sqlite import SqliteSaver
    except ImportError:
        return MemorySaver()
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    return SqliteSaver(sqlite3.connect(path, check_same_thread=False))
