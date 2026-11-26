"""Graph state and shared constants. State holds only JSON-serialisable values so any
LangGraph checkpointer (memory, SQLite) can persist it between an interrupt and a resume."""
from __future__ import annotations

from typing import Any, TypedDict

MAX_ATTEMPTS = 3

# status values (state["status"])
FETCH_FAILED = "fetch_failed"
LLM_FAILED = "llm_failed"
RETRYING = "retrying"
AUDITING = "auditing"
READY = "ready_for_review"
NEEDS_FIX = "needs_human_fix"
APPROVED = "approved"
REJECTED = "rejected"


class Attempt(TypedDict, total=False):
    n: int
    raw: str                 # raw model output
    errors: list[str]        # what the checks said about it (filled by route)


class ResearchState(TypedDict, total=False):
    # input
    source: str                      # URL or local path
    source_url: str                  # URL recorded in the scheme: --source-url, else the fetched FINAL url
    source_url_explicit: bool        # True when the user passed --source-url
    final_url: str                   # URL actually read (after redirects); "" for local files
    local_file: bool                 # source is a local file passed explicitly with --file
    # fetch
    text: str                        # cleaned source text (what the LLM sees and evidence is checked against)
    content_hash: str
    fetched_at: str
    truncated: bool
    # extract / verify / validate
    attempts: list[Attempt]
    errors: list[str]                # blocking problems for the CURRENT candidate
    warnings: list[str]
    fetch_warnings: list[str]        # from fetch (redirects, non-gov domain); carried into every review
    candidate: dict | None           # extract-format record (with evidence)
    scheme_record: dict | None       # database-format record derived from candidate (no evidence)
    evidence_report: list[dict]      # {label, quote, found, score, method}
    is_update: bool
    checks_run: int
    edited: bool                     # a human edited the candidate (no more LLM retries)
    model: str
    # free-text hygiene
    contact_flags: list[dict]        # every URL / phone / e-mail in citizen-facing text, with status
    unapproved_urls: list[str]       # URLs outside the government allowlist (blocking until approved)
    # semantic audit (second agent)
    audit_done: bool                 # the auditor has judged the CURRENT candidate
    audit: dict                      # {status, model, dropped, blocking, warnings, detail}
    auditor_notes: list[str]         # warnings from the auditor, shown at review
    # review / write
    status: str
    decision: dict | None            # {"action": approve|reject|edit|invalid, "record", "reviewer", "note"}
    review_note: str                 # shown on the next review prompt (e.g. why approve was refused)
    fatal: str
    report: dict[str, Any]
