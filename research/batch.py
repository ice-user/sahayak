"""Discover + batch: run the graph over many sources with bounded concurrency and write a report."""
from __future__ import annotations

import re
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

from . import runner
from .state import NEEDS_FIX, READY


@dataclass
class BatchItem:
    source: str
    thread_id: str
    status: str                 # ready_for_review | needs_human_fix | failed | approved | rejected | error
    name: str = ""
    scheme_id: str = ""
    detail: str = ""
    resumed: bool = False       # an earlier paused review was reused, no LLM call made
    seconds: float = 0.0        # wall time for this source
    attempts: int = 0           # extractor attempts (each retry is one more LLM call; the auditor adds more)


def read_sources(path: str | Path) -> list[str]:
    """One URL/path per line; blank lines and '#' comments ignored; duplicates removed."""
    out: list[str] = []
    for ln in Path(path).read_text(encoding="utf-8").splitlines():
        ln = re.split(r"\s+#", ln.strip())[0].strip()
        if ln and not ln.startswith("#") and ln not in out:
            out.append(ln)
    return out


def links_from_page(html: str, base_url: str, pattern: str | None = None, same_host: bool = True) -> list[str]:
    """Discover scheme links on a listing/search-results page."""
    from bs4 import BeautifulSoup

    host = urlparse(base_url).netloc
    rx = re.compile(pattern) if pattern else None
    found: list[str] = []
    for a in BeautifulSoup(html, "html.parser").find_all("a", href=True):
        url = urljoin(base_url, a["href"]).split("#")[0]
        u = urlparse(url)
        if u.scheme not in ("http", "https") or (same_host and u.netloc != host):
            continue
        if rx and not rx.search(url):
            continue
        if url not in found:
            found.append(url)
    return found


def snapshot_path(source: str, snapshot_dir: str | Path | None) -> Path | None:
    """``<snapshot_dir>/<last URL segment>.txt`` if it exists: a pre-rendered copy of a JS-only page (see
    scripts/collect_myscheme.py). The URL stays the recorded source; the file is the text that is read."""
    if not snapshot_dir:
        return None
    slug = urlparse(source).path.rstrip("/").rsplit("/", 1)[-1]
    p = Path(snapshot_dir) / f"{slug}.txt"
    return p if slug and p.is_file() else None


def _run_one(graph, source: str, snapshot_dir: str | Path | None = None) -> BatchItem:
    tid = runner.thread_id_for(source)
    t0 = time.monotonic()
    try:
        prior = runner.pending(graph, tid)
        snap = snapshot_path(source, snapshot_dir)
        if prior:
            out = prior
        elif snap:
            out = runner.start(graph, str(snap), source_url=source, thread_id=tid, local_file=True)
        else:
            out = runner.start(graph, source, thread_id=tid)
    except Exception as e:  # one bad source must not sink the batch
        return BatchItem(source, tid, "error", detail=f"{type(e).__name__}: {e}", seconds=time.monotonic() - t0)
    secs, tries = time.monotonic() - t0, len(out.state.get("attempts") or [])
    cand = (out.payload or {}).get("candidate") or {}
    if out.paused:
        detail = "; ".join((out.payload or {}).get("errors", [])[:3])
        return BatchItem(source, tid, out.status, cand.get("name", ""), cand.get("id", ""), detail,
                         resumed=prior is not None, seconds=secs, attempts=tries)
    rep = out.report
    status = "failed" if rep.get("outcome") == "failed" else out.status
    return BatchItem(source, tid, status, rep.get("name") or "", rep.get("id") or "",
                     rep.get("error", "") or out.state.get("fatal", ""), seconds=secs, attempts=tries)


def run_batch(graph, sources: list[str], *, workers: int = 3,
              snapshot_dir: str | Path | None = None) -> list[BatchItem]:
    """Run every source through the graph (max ``workers`` at once). Stops at human review."""
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        return list(pool.map(lambda s: _run_one(graph, s, snapshot_dir), sources))


def render_report(items: list[BatchItem], *, wall_seconds: float | None = None, llm_calls: int | None = None,
                  llm_tokens: int | None = None) -> str:
    """Markdown summary: ready for review / needs fix / failed (+ already decided)."""
    groups = [
        ("Ready for review (all automatic checks passed)", [i for i in items if i.status == READY]),
        ("Needs human fix (checks still failing after retries)", [i for i in items if i.status == NEEDS_FIX]),
        ("Failed (fetch / LLM / unexpected error)", [i for i in items if i.status in ("failed", "fetch_failed", "llm_failed", "error")]),
        ("Already decided", [i for i in items if i.status in ("approved", "rejected")]),
    ]
    lines = ["# Scheme research batch report", "",
             f"Generated {datetime.now(timezone.utc).isoformat(timespec='seconds')}; {len(items)} source(s).",
             "Nothing is added to the database by this run: approve each thread with "
             "`python -m research review <thread> --approve`, then `python -m research merge`.", ""]
    if wall_seconds is not None:
        n = max(1, len(items))
        lines += [f"Wall time {wall_seconds:.0f}s ({wall_seconds / n:.1f}s per source); "
                  f"sum of per-source times {sum(i.seconds for i in items):.0f}s; "
                  f"extractor attempts {sum(i.attempts for i in items)}"
                  + (f"; LLM calls {llm_calls} ({llm_calls / n:.1f} per source, extractor + auditor)"
                     if llm_calls is not None else "")
                  + (f"; tokens {llm_tokens}" if llm_tokens else "") + ".", ""]
    for title, rows in groups:
        lines += [f"## {title}: {len(rows)}", ""]
        if rows:
            lines += ["| Source | Scheme | Thread | Secs / tries | Notes |", "|---|---|---|---|---|"]
            for i in rows:
                note = (i.detail or "").replace("|", "\\|").replace("\n", " ")[:200]
                if i.resumed:
                    note = ("(reused pending review) " + note).strip()
                lines.append(f"| {i.source} | {i.name or '-'} {('`' + i.scheme_id + '`') if i.scheme_id else ''} "
                             f"| `{i.thread_id}` | {i.seconds:.0f}s / {i.attempts} | {note} |")
            lines.append("")
    return "\n".join(lines)
