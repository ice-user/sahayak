"""Graph nodes. ``make_nodes(deps)`` closes over injected dependencies (LLM, paths, fetcher) so the
state stays JSON-only and every node is testable offline."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from langgraph.types import interrupt
from pydantic import ValidationError

from sahayak.models import DATA_PATH, Scheme, load_schemes

from . import state as S
from .evidence import verify_all
from .fetch import FetchError, Fetched, fetch_file, fetch_url, is_url
from .freetext import URL_ERR_PREFIX, blocked_urls, host_of, scan_free_text, url_errors
from .llm import LLM, LLMOutputError, parse_json_object
from .prompts import SYSTEM_PROMPT, feedback_prompt, user_prompt
from .review import build_review
from .schema import ExtractedScheme, evidence_items, to_scheme_dict
from .validate import validate_candidate
from .verifier import run_audit

CANDIDATES_DIR = DATA_PATH.parent / "candidates"


@dataclass
class Deps:
    """Everything the nodes need from the outside world."""
    llm: LLM = field(default_factory=LLM)
    schemes_path: Path = DATA_PATH
    candidates_dir: Path = CANDIDATES_DIR
    fetcher: Callable[[str], Fetched] = fetch_url          # public http(s) URLs only (SSRF-hardened)
    file_fetcher: Callable[[str], Fetched] | None = None   # local files (only with --file); default below
    allowed_dirs: list | None = None                       # dirs a local file may live in (None: defaults)
    max_attempts: int = S.MAX_ATTEMPTS
    verifier_llm: LLM | None = None                        # auditor model; None = use the extractor's LLM
    audit: bool = True

    def existing(self) -> dict[str, Scheme]:
        return load_schemes(self.schemes_path)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _schema_errors(e: ValidationError) -> list[str]:
    return [f"schema: {'.'.join(map(str, x['loc']))}: {x['msg']}" for x in e.errors()]


def _evidence_checks(cand: ExtractedScheme, text: str) -> tuple[list[dict], list[str]]:
    report, errors = [], []
    for label, quote, m in verify_all(evidence_items(cand), text):
        report.append({"label": label, "quote": quote, "found": m.found, "score": round(m.score, 1),
                       "method": m.method})
        if not m.found:
            why = {"too_short": "quote is too short to prove anything", "empty": "quote is empty"}.get(
                m.method, f"quote not found in the source (best match {m.score:.0f}/100); copy it verbatim or drop the claim")
            errors.append(f"evidence for {label}: {why}: \"{quote[:120]}\"")
    return report, errors


def _source_hosts(state: dict) -> list[str]:
    return [h for h in (host_of(state.get("source_url") or ""), host_of(state.get("final_url") or "")) if h]


def _post_checks(rec: dict | None, state: dict, approved: list[str] | None = None) -> tuple[list[str], list[dict], list[str]]:
    """Checks on the record's provenance and free text: (errors, contact_flags, unapproved_urls)."""
    errors: list[str] = []
    su, final = state.get("source_url") or "", state.get("final_url") or ""
    if final and not state.get("source_url_explicit") and su != final:
        errors.append(f"source_url {su!r} is not the fetched final URL {final!r}; pass --source-url to override "
                      "it explicitly")
    flags: list[dict] = []
    if rec is not None:
        flags = scan_free_text(rec, source_hosts=_source_hosts(state), approved_urls=approved or [],
                               source_text=state.get("text", ""))
        errors += url_errors(flags)
    return errors, flags, blocked_urls(flags)


def make_nodes(deps: Deps) -> dict[str, Callable[[dict], dict]]:
    """Build all node functions bound to ``deps``."""

    def fetch_node(state: dict) -> dict:
        # Reset EVERY per-run field first. Thread ids are deterministic and checkpoints persist, so without
        # this a transient failure (`fatal` set) would make the source permanently unprocessable.
        fresh: dict[str, Any] = {
            "fatal": "", "status": "", "report": {}, "decision": None, "review_note": "", "candidate": None,
            "scheme_record": None, "evidence_report": [], "errors": [], "warnings": [], "fetch_warnings": [], "attempts": [],
            "edited": False, "is_update": False, "checks_run": 0, "audit_done": False, "audit": {},
            "auditor_notes": [], "contact_flags": [], "unapproved_urls": [], "final_url": "", "text": "",
        }
        src = state["source"]
        explicit = (state.get("source_url") or "").strip()
        try:
            if is_url(src):
                f = deps.fetcher(src)
            elif state.get("local_file"):
                f = (deps.file_fetcher or (lambda p: fetch_file(p, allowed_dirs=deps.allowed_dirs)))(src)
            else:
                raise FetchError(f"{src[:80]!r} is not an http(s) URL; local files are only read when passed "
                                 "explicitly with --file")
        except FetchError as e:
            return {**fresh, "source_url": explicit, "source_url_explicit": bool(explicit),
                    "status": S.FETCH_FAILED, "fatal": str(e)}
        final = (f.final_url or src.strip()) if is_url(src) else ""
        warnings = list(f.warnings)
        if is_url(src) and explicit and explicit != final:
            warnings.append(f"--source-url {explicit} differs from the URL actually fetched ({final}); "
                            "the explicit value is recorded")
        return {**fresh, "text": f.text, "content_hash": f.content_hash, "fetched_at": f.fetched_at,
                "truncated": f.truncated, "source_url": explicit or final, "source_url_explicit": bool(explicit),
                "final_url": final, "fetch_warnings": warnings}

    def extract(state: dict) -> dict:
        attempts = list(state.get("attempts", []))
        messages = [{"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt(state["text"], state.get("source_url"))}]
        for a in attempts:
            messages.append({"role": "assistant", "content": a["raw"]})
            messages.append({"role": "user", "content": feedback_prompt(a.get("errors", []))})
        try:
            raw = deps.llm.complete(messages)
        except Exception as e:  # network/auth/rate limit: retrying with feedback would not help
            return {"status": S.LLM_FAILED, "fatal": f"LLM call failed: {type(e).__name__}: {e}"}
        attempt: dict = {"n": len(attempts) + 1, "raw": raw, "errors": []}
        out: dict[str, Any] = {"model": deps.llm.model or "", "candidate": None, "scheme_record": None,
                               "evidence_report": [], "warnings": [], "audit_done": False, "audit": {},
                               "auditor_notes": [], "contact_flags": [], "unapproved_urls": []}
        try:
            data = parse_json_object(raw)
            data["source_url"] = state.get("source_url", "")  # never trust the model for this
            cand = ExtractedScheme(**data)
            out["candidate"] = cand.model_dump()
            out["errors"] = []
        except LLMOutputError as e:
            out["errors"] = [f"output was not valid JSON: {e}"]
        except ValidationError as e:
            out["errors"] = _schema_errors(e)
        out["attempts"] = attempts + [attempt]
        return out

    def verify_evidence(state: dict) -> dict:
        if not state.get("candidate"):
            return {}
        cand = ExtractedScheme(**state["candidate"])
        report, errs = _evidence_checks(cand, state["text"])
        return {"evidence_report": report, "errors": state.get("errors", []) + errs}

    def validate(state: dict) -> dict:
        if not state.get("candidate"):
            return {}
        existing = deps.existing()
        v = validate_candidate(state["candidate"], existing, source_url=state.get("source_url"))
        warnings = list(state.get("fetch_warnings", [])) + list(v.warnings)
        cand = state["candidate"]
        if (deps.candidates_dir / f"{cand['id']}.json").exists():
            warnings.append(f"a pending candidate file for {cand['id']!r} already exists and will be overwritten")
        if state.get("truncated"):
            warnings.append("source text was truncated; criteria in the cut part were not seen")
        rec = None if any(e.startswith("schema:") for e in v.errors) else to_scheme_dict(cand)
        if rec is not None:
            rec["source_url"] = state.get("source_url", "")
        extra, flags, unapproved = _post_checks(rec, state)
        flagged = [f for f in flags if f["kind"] != "url" or f["status"] != "ok"]
        if flagged:
            warnings.append(f"{len(flagged)} URL/phone/e-mail value(s) in free text: verify each against the "
                            "official source (see 'Contact details' in the review)")
        return {"errors": state.get("errors", []) + v.errors + extra, "warnings": warnings,
                "is_update": v.is_update, "checks_run": v.checks_run, "scheme_record": rec,
                "contact_flags": flags, "unapproved_urls": unapproved}

    def verify_semantics(state: dict) -> dict:
        """Second agent: an adversarial auditor re-reads the source against the candidate (see verifier.py).
        Blocking findings become errors, so route sends the candidate back to extract (counted as an attempt)."""
        auditor = deps.verifier_llm or deps.llm
        cand = state["candidate"]
        res = run_audit(auditor, state["text"], state["scheme_record"], cand.get("unmapped_criteria", []))
        warnings = list(state.get("warnings", []))
        if res["status"] != "ok":
            warnings.append(f"AUDITOR DID NOT RUN ({res['detail']}); the semantic check is missing, so read each "
                            "rule against its quote yourself")
        elif res["dropped"]:
            warnings.append(f"{len(res['dropped'])} auditor finding(s) dropped because their supporting quote is "
                            "not in the source")
        audit = {"status": res["status"], "model": res["model"], "dropped": res["dropped"],
                 "blocking": len(res["blocking"]), "warnings": len(res["warnings"]), "detail": res["detail"]}
        return {"audit_done": True, "audit": audit, "auditor_notes": res["warnings"], "warnings": warnings,
                "errors": state.get("errors", []) + res["blocking"]}

    def route(state: dict) -> dict:
        errors = state.get("errors", [])
        attempts = [dict(a) for a in state.get("attempts", [])]
        if attempts and not state.get("edited"):
            attempts[-1]["errors"] = list(errors)
        if not errors:
            if deps.audit and not state.get("edited") and not state.get("audit_done"):
                return {"status": S.AUDITING, "attempts": attempts}
            return {"status": S.READY, "attempts": attempts}
        if not state.get("edited") and len(attempts) < deps.max_attempts:
            return {"status": S.RETRYING, "attempts": attempts}
        return {"status": S.NEEDS_FIX, "attempts": attempts}

    def human_review(state: dict) -> dict:
        payload = build_review(state, deps.existing())
        decision = interrupt(payload)
        if not isinstance(decision, dict):
            decision = {"action": str(decision)}
        action = decision.get("action")
        note = ""
        if action not in ("approve", "reject", "edit"):
            action, note = "invalid", f"unknown action {decision.get('action')!r}; use approve, reject or edit"
        elif action == "approve" and state.get("errors"):
            url_errs = [e for e in state["errors"] if e.startswith(URL_ERR_PREFIX)]
            others = [e for e in state["errors"] if e not in url_errs]
            allow = {u.strip().rstrip("/").lower() for u in (decision.get("allow_urls") or [])}
            need = state.get("unapproved_urls", [])
            if others:
                action, note = "invalid", "approve refused: the candidate has blocking errors; edit or reject it"
            elif [u for u in need if u.rstrip("/").lower() not in allow]:
                action, note = "invalid", ("approve refused: free-text URL(s) outside the government allowlist: "
                                           + ", ".join(need) + ". Edit them out, or approve explicitly with "
                                           "--allow-url for each one")
            else:
                decision = {**decision, "approved_urls": list(need)}
        elif action == "edit" and not isinstance(decision.get("record"), dict):
            action, note = "invalid", "edit needs a JSON object in 'record'"
        decision = {**decision, "action": action, "decided_at": _now()}
        return {"decision": decision, "review_note": note}

    def apply_edit(state: dict) -> dict:
        """Re-run every deterministic check on a human-edited candidate."""
        record = state["decision"]["record"]
        record = {**record, "source_url": state.get("source_url") or record.get("source_url", "")}
        try:
            cand = ExtractedScheme(**record)
        except ValidationError as e:
            return {"edited": True, "errors": _schema_errors(e), "warnings": [], "decision": None,
                    "review_note": "edit rejected by schema check; fix and try again"}
        report, errs = _evidence_checks(cand, state["text"])
        v = validate_candidate(cand, deps.existing(), source_url=state.get("source_url"))
        rec = None if any(e.startswith("schema:") for e in v.errors) else to_scheme_dict(cand)
        if rec is not None:
            rec["source_url"] = state.get("source_url", "")
        extra, flags, unapproved = _post_checks(rec, state)
        errors = errs + v.errors + extra
        warnings = list(state.get("fetch_warnings", [])) + v.warnings
        if deps.audit:
            warnings.append("human-edited candidate: the semantic auditor was not re-run; the edit is your "
                            "responsibility")
        return {"edited": True, "candidate": cand.model_dump(), "scheme_record": rec, "evidence_report": report,
                "errors": errors, "warnings": warnings, "is_update": v.is_update, "checks_run": v.checks_run,
                "contact_flags": flags, "unapproved_urls": unapproved, "audit_done": True, "auditor_notes": [],
                "decision": None, "review_note": "edited by human; checks re-run"
                + ("" if not errors else " and still failing")}

    def write(state: dict) -> dict:
        base = {"source": state.get("source"), "source_url": state.get("source_url"),
                "attempts": len(state.get("attempts", [])), "warnings": state.get("warnings", [])}
        if state.get("fatal"):
            return {"status": state["status"], "report": {**base, "outcome": "failed", "error": state["fatal"]}}
        dec = state["decision"]
        cand = state.get("candidate") or {}
        if dec["action"] == "reject":
            return {"status": S.REJECTED, "report": {**base, "outcome": "rejected", "id": cand.get("id"),
                                                      "name": cand.get("name"), "note": dec.get("note", ""),
                                                      "reviewer": dec.get("reviewer")}}
        rec = state["scheme_record"]
        deps.candidates_dir.mkdir(parents=True, exist_ok=True)
        path = deps.candidates_dir / f"{rec['id']}.json"
        src_dir = deps.candidates_dir / "sources"
        src_dir.mkdir(exist_ok=True)
        snapshot = src_dir / f"{rec['id']}.txt"
        snapshot.write_text(state["text"], encoding="utf-8")
        doc = {
            "scheme": rec,
            "evidence": {"candidate": cand, "report": state.get("evidence_report", [])},
            "unmapped_criteria": cand.get("unmapped_criteria", []),
            "warnings": state.get("warnings", []),
            "provenance": {
                "source": state.get("source"), "source_url": state.get("source_url"),
                "fetched_at": state.get("fetched_at"), "content_sha256": state.get("content_hash"),
                "final_url": state.get("final_url", ""), "source_url_explicit": bool(state.get("source_url_explicit")),
                "source_snapshot": f"sources/{rec['id']}.txt", "model": state.get("model"),
                "audit": {**(state.get("audit") or {}), "notes": state.get("auditor_notes", [])},
                "contact_flags": state.get("contact_flags", []),
                "llm_attempts": len(state.get("attempts", [])), "edited_by_human": bool(state.get("edited")),
                "is_update": bool(state.get("is_update")),
                "review": {"decision": "approve", "reviewer": dec.get("reviewer"), "note": dec.get("note", ""),
                           "decided_at": dec.get("decided_at"), "approved_urls": dec.get("approved_urls", [])},
            },
        }
        path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return {"status": S.APPROVED, "report": {**base, "outcome": "approved", "id": rec["id"],
                                                  "name": rec["name"], "candidate_path": str(path),
                                                  "reviewer": dec.get("reviewer")}}

    return {"fetch": fetch_node, "extract": extract, "verify_evidence": verify_evidence, "validate": validate,
            "verify_semantics": verify_semantics, "route": route, "human_review": human_review, "apply_edit": apply_edit, "write": write}
