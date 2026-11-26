"""Command line: python -m research {run,show,review,batch,merge}."""
from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from . import runner
from .batch import links_from_page, read_sources, render_report, run_batch
from .fetch import FetchError, fetch_url_raw
from .graph import build_graph, sqlite_checkpointer
from .llm import LLM
from .merge import merge_candidates
from .nodes import CANDIDATES_DIR, Deps
from .verifier import verifier_llm_from_env

DEFAULT_DB = Path(__file__).resolve().parent / ".state" / "checkpoints.sqlite"
console = Console()

_STYLE = {"ready_for_review": "green", "needs_human_fix": "yellow", "approved": "green", "rejected": "red",
          "fetch_failed": "red", "llm_failed": "red"}


def _graph(args, *, need_llm: bool = True):
    # RESEARCH_VERIFIER_MODEL selects a different model for the independent auditor (default: the extractor's)
    deps = Deps(llm=LLM(model=getattr(args, "model", None)), verifier_llm=verifier_llm_from_env(),
                candidates_dir=Path(args.candidates_dir))
    return build_graph(deps, sqlite_checkpointer(args.state_db)), deps


def _print_outcome(out: runner.Outcome) -> None:
    style = _STYLE.get(out.status, "white")
    if out.payload:
        console.print(Panel(Text(out.summary), title=f"review: thread {out.thread_id}", border_style=style))
        if out.paused:
            console.print(f"Decide with:  python -m research review {out.thread_id} --approve | --reject | "
                          "--edit file.json")
            console.print(f"Edit template: python -m research show {out.thread_id} --json > edit.json")
    else:
        rep = out.report
        console.print(Panel(Text(json.dumps(rep, indent=2, ensure_ascii=False)),
                            title=f"{out.status}: thread {out.thread_id}", border_style=style))


def cmd_run(args) -> int:
    if bool(args.file) == bool(args.source):
        console.print("give exactly one of: a URL, or --file PATH (local files are only read with --file)")
        return 2
    graph, _ = _graph(args)
    source = args.file or args.source
    out = runner.start(graph, source, source_url=args.source_url, thread_id=args.thread,
                       local_file=bool(args.file))
    if out.status in ("fetch_failed", "llm_failed"):
        console.print(f"[red]{out.status}[/red]: {out.state.get('fatal')}")
        return 2
    _print_outcome(out)
    return 0


def cmd_show(args) -> int:
    graph, _ = _graph(args)
    out = runner.pending(graph, args.thread)
    if not out:
        console.print(f"thread {args.thread} is not waiting for review")
        return 1
    if args.json:
        print(json.dumps(out.payload["candidate"], indent=2, ensure_ascii=False))
    else:
        _print_outcome(out)
    return 0


def cmd_review(args) -> int:
    graph, _ = _graph(args)
    decision: dict = {"reviewer": args.reviewer, "note": args.note or "", "allow_urls": args.allow_url or []}
    if args.approve:
        decision["action"] = "approve"
    elif args.reject:
        decision["action"] = "reject"
    else:
        try:
            decision.update(action="edit", record=json.loads(Path(args.edit).read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError) as e:
            console.print(f"[red]cannot read edit file[/red]: {e}")
            return 2
    try:
        out = runner.resume(graph, args.thread, decision)
    except LookupError as e:
        console.print(f"[red]{e}[/red]")
        return 1
    _print_outcome(out)
    if out.status == "approved":
        console.print(f"[green]written[/green] {out.report['candidate_path']}\n"
                      "Merge into data/schemes.json with:  python -m research merge")
    return 0


def cmd_batch(args) -> int:
    graph, _ = _graph(args)
    if args.from_page:
        try:
            html = fetch_url_raw(args.from_page)
        except FetchError as e:
            console.print(f"[red]cannot fetch {args.from_page}[/red]: {e}")
            return 2
        sources = links_from_page(html, args.from_page, args.link_pattern)
        console.print(f"discovered {len(sources)} link(s) on {args.from_page}")
    else:
        sources = read_sources(args.file)
    if args.limit:
        sources = sources[: args.limit]
    with console.status(f"researching {len(sources)} source(s) with {args.workers} worker(s)..."):
        items = run_batch(graph, sources, workers=args.workers)
    report = render_report(items)
    out_path = Path(args.report) if args.report else Path(args.candidates_dir) / "reports" / "latest-batch.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report, encoding="utf-8")
    console.print(Text(report))
    console.print(f"report saved to {out_path}")
    return 0


def cmd_merge(args) -> int:
    res = merge_candidates(Path(args.candidates_dir), ids=args.ids or None, allow_update=args.allow_update,
                           dry_run=args.dry_run, run_tests=args.run_tests,
                           allow_unverified=args.allow_unverified)
    for m in res.skipped:
        console.print(f"[yellow]skip[/yellow] {m}")
    for e in res.errors:
        console.print(Text(f"ERROR {e}", style="red"))
    if res.ok:
        verb = "would merge" if res.dry_run else "merged"
        console.print(f"[green]{verb}[/green]: new={res.merged or '-'} updated={res.updated or '-'}")
    else:
        console.print("[red]nothing was written[/red]")
    return 0 if res.ok else 1


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="python -m research", description="Scheme-research agent")
    ap.add_argument("--state-db", default=os.environ.get("RESEARCH_STATE_DB", str(DEFAULT_DB)),
                    help="SQLite checkpoint file (lets reviews resume later)")
    ap.add_argument("--candidates-dir", default=os.environ.get("RESEARCH_CANDIDATES_DIR", str(CANDIDATES_DIR)))
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("run", help="research one URL (or a local file via --file); pauses at human review")
    p.add_argument("source", nargs="?", help="public http(s) URL")
    p.add_argument("--file", metavar="PATH", help="local .html/.pdf/.txt (must be under RESEARCH_ALLOWED_DIRS; "
                   "default: the repo's data/ and tests/fixtures/); also pass --source-url")
    p.add_argument("--source-url", help="public URL to record when SOURCE is a local file")
    p.add_argument("--thread", help="thread id (default: derived from the source)")
    p.add_argument("--model", help="override LLM_MODEL")
    p.set_defaults(fn=cmd_run)

    p = sub.add_parser("show", help="print the pending review for a thread")
    p.add_argument("thread")
    p.add_argument("--json", action="store_true", help="print the candidate JSON (template for --edit)")
    p.set_defaults(fn=cmd_show)

    p = sub.add_parser("review", help="approve / reject / edit a paused thread")
    p.add_argument("thread")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--approve", action="store_true")
    g.add_argument("--reject", action="store_true")
    g.add_argument("--edit", metavar="FILE", help="JSON candidate (same format as `show --json`)")
    p.add_argument("--allow-url", action="append", metavar="URL",
                   help="explicitly approve a URL in free text that is outside the government allowlist (repeatable)")
    p.add_argument("--reviewer", default=getpass.getuser())
    p.add_argument("--note")
    p.set_defaults(fn=cmd_review)

    p = sub.add_parser("batch", help="run many sources (file of URLs, or links found on a page)")
    p.add_argument("file", nargs="?")
    p.add_argument("--from-page", help="listing/search-results URL to harvest links from")
    p.add_argument("--link-pattern", help="regex a harvested link must match")
    p.add_argument("--workers", type=int, default=3)
    p.add_argument("--limit", type=int)
    p.add_argument("--report", help="markdown report path")
    p.add_argument("--model")
    p.set_defaults(fn=cmd_batch)

    p = sub.add_parser("merge", help="merge approved candidates into data/schemes.json")
    p.add_argument("ids", nargs="*", help="candidate ids (default: all)")
    p.add_argument("--allow-update", action="store_true", help="allow replacing an existing scheme id")
    p.add_argument("--allow-unverified", action="store_true",
                   help="merge candidates that have no source snapshot (evidence cannot be re-verified)")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--run-tests", action="store_true", help="also run the full pytest suite and roll back on failure")
    p.set_defaults(fn=cmd_merge)
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.cmd == "batch" and not (args.file or args.from_page):
        console.print("batch needs a urls file or --from-page")
        return 2
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
