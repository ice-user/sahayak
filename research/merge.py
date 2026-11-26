"""Merge approved candidates (data/candidates/*.json) into data/schemes.json, all-or-nothing.

Before anything is written the merge re-runs: record validation + behavioural boundary tests, the
evidence check (when the stored source snapshot still matches its hash), and the existing
eligibility regression cases against the merged database. ``--run-tests`` additionally runs the
repo's full pytest suite against the real file.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from sahayak.models import DATA_PATH, Profile, Scheme
from sahayak.rules import check_all

from .evidence import verify_all
from .freetext import host_of, scan_free_text, blocked_urls
from .schema import ExtractedScheme, evidence_items, to_scheme_dict
from .validate import rule_value_problems, validate_record

ROOT = DATA_PATH.parent.parent
CASES_PATH = ROOT / "evals" / "eligibility_cases.json"
WEB_COPY_PATH = ROOT / "web" / "src" / "data" / "schemes.json"   # the frontend ships its own copy
AUTO = object()


@dataclass
class MergeResult:
    merged: list[str] = field(default_factory=list)
    updated: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)      # human-readable reasons
    errors: list[str] = field(default_factory=list)
    dry_run: bool = False

    @property
    def ok(self) -> bool:
        return not self.errors


def _atomic_write(path: Path, data: bytes) -> None:
    """Write ``data`` to ``path`` so a crash leaves either the old or the new file, never a partial one:
    temp file in the same directory, flush + fsync, os.replace, then fsync the directory."""
    path = Path(path)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with open(tmp, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    try:
        dfd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(dfd)
        finally:
            os.close(dfd)
    except OSError:  # directory fsync is not supported everywhere (e.g. Windows)
        pass


def _copy_atomic(src: Path, dst: Path) -> None:
    _atomic_write(dst, Path(src).read_bytes())


def _backup(path: Path) -> Path:
    """Timestamped copy (never overwrites an earlier backup): schemes.json.20260101T120000123456Z.bak"""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    bak = path.with_name(f"{path.name}.{stamp}.bak")
    n = 0
    while bak.exists():
        n += 1
        bak = path.with_name(f"{path.name}.{stamp}-{n}.bak")
    shutil.copy2(path, bak)
    return bak


def resolve_web_copy(schemes_path: Path) -> Path | None:
    """The frontend copy to refresh after a merge: only for the real data/schemes.json, and only when
    web/src/data exists. Temp databases (tests, dry experiments) never touch the repo's frontend."""
    if Path(schemes_path).resolve() != DATA_PATH.resolve():
        return None
    return WEB_COPY_PATH if WEB_COPY_PATH.parent.is_dir() else None


def _check_candidate(path: Path, doc: dict, existing: dict[str, Scheme], allow_update: bool,
                     res: MergeResult, candidates_dir: Path, allow_unverified: bool = False) -> dict | None:
    rec = doc.get("scheme")
    prov = doc.get("provenance", {})
    name = path.name
    if not isinstance(rec, dict):
        res.errors.append(f"{name}: no 'scheme' object")
        return None
    if prov.get("review", {}).get("decision") != "approve":
        res.errors.append(f"{name}: not approved by a human reviewer (provenance.review.decision)")
        return None
    v = validate_record(rec, existing)
    if v.errors:
        res.errors += [f"{name}: {e}" for e in v.errors]
        return None
    if v.is_update and not allow_update:
        res.skipped.append(f"{name}: id {rec['id']!r} already exists; re-run with --allow-update to replace it")
        return None

    # source_url: must be the one the pipeline recorded, and either the fetched final URL or explicit
    if prov.get("source_url") != rec.get("source_url"):
        res.errors.append(f"{name}: scheme.source_url does not match provenance.source_url")
        return None
    if not prov.get("source_url_explicit") and prov.get("final_url") != rec.get("source_url"):
        res.errors.append(f"{name}: source_url {rec.get('source_url')!r} is neither the fetched final URL "
                          f"({prov.get('final_url')!r}) nor an explicit --source-url")
        return None

    # the evidenced candidate must be exactly what the scheme was built from
    cand = None
    try:
        cand = ExtractedScheme(**doc["evidence"]["candidate"])
    except Exception as e:
        res.errors.append(f"{name}: stored evidence is unreadable: {e}")
        return None
    derived = to_scheme_dict(cand)
    derived["source_url"] = rec.get("source_url", "")
    if derived != rec:
        res.errors.append(f"{name}: scheme does not match the evidenced candidate it was built from "
                          "(edited after approval?)")
        return None
    problems = rule_value_problems(cand)
    if problems:
        res.errors += [f"{name}: {p}" for p in problems]
        return None

    # free text: URLs outside the government/source allowlist need an explicit, recorded reviewer approval
    flags = scan_free_text(rec, source_hosts=[host_of(rec.get("source_url", "")), host_of(prov.get("final_url", ""))],
                           approved_urls=prov.get("review", {}).get("approved_urls", []))
    bad = blocked_urls(flags)
    if bad:
        res.errors.append(f"{name}: free text contains URL(s) outside the government allowlist without a recorded "
                          f"reviewer approval: {', '.join(bad)}")
        return None

    # source snapshot: required (evidence is re-verified against it); must live inside the candidates dir
    snap_name = prov.get("source_snapshot")
    cdir = Path(candidates_dir).resolve()
    snap = None
    if snap_name:
        snap = (path.parent / snap_name).resolve()
        if snap != cdir and cdir not in snap.parents:
            res.errors.append(f"{name}: source_snapshot {snap_name!r} resolves outside the candidates directory")
            return None
    if snap is None or not snap.is_file():
        if not allow_unverified:
            res.errors.append(f"{name}: source snapshot is missing, so the evidence cannot be re-verified "
                              "(re-run the research, or pass --allow-unverified to merge it anyway)")
            return None
        res.skipped.append(f"{name}: (note) no source snapshot, evidence was NOT re-verified (--allow-unverified)")
        return rec
    text = snap.read_text(encoding="utf-8")
    if hashlib.sha256(text.encode("utf-8")).hexdigest() != prov.get("content_sha256"):
        res.errors.append(f"{name}: source snapshot no longer matches its recorded hash")
        return None
    bad_ev = [(lbl, q) for lbl, q, m in verify_all(evidence_items(cand), text) if not m.found]
    if bad_ev:
        res.errors += [f"{name}: evidence for {lbl} not found in source snapshot" for lbl, _ in bad_ev]
        return None
    return rec


def _regression(schemes: dict[str, Scheme], cases_path: Path) -> list[str]:
    errs: list[str] = []
    if any(r.verdict == "eligible" for r in check_all(Profile(), schemes)):
        errs.append("regression: an empty profile became eligible for some scheme")
    if cases_path.is_file():
        for case in json.loads(cases_path.read_text(encoding="utf-8")):
            try:
                results = {r.scheme_id: r for r in check_all(Profile(**case["profile"]), schemes)}
            except Exception as e:  # a case written for an older Profile must not crash the merge
                errs.append(f"regression case {case.get('id')}: profile is not valid for the current Profile: {e}")
                continue
            for verdict, ids in case["expect"].items():
                for sid in ids:
                    if sid in results and results[sid].verdict != verdict:
                        errs.append(f"regression case {case['id']}: {sid} expected {verdict}, "
                                    f"got {results[sid].verdict}")
    return errs


def merge_candidates(candidates_dir: Path, schemes_path: Path = DATA_PATH, *, ids: list[str] | None = None,
                     allow_update: bool = False, dry_run: bool = False, run_tests: bool = False,
                     cases_path: Path | None = None, allow_unverified: bool = False,
                     web_copy=AUTO) -> MergeResult:
    """Validate and merge every approved candidate; writes nothing unless all checks pass.

    The write is atomic (temp file + fsync + os.replace) with a timestamped backup; afterwards the merged file
    is copied byte-identically to the frontend's copy (``web_copy``; default: web/src/data/schemes.json for the
    real database when that directory exists)."""
    res = MergeResult(dry_run=dry_run)
    cases_path = cases_path or CASES_PATH
    raw = json.loads(Path(schemes_path).read_text(encoding="utf-8"))
    by_id = {s["id"]: s for s in raw["schemes"]}
    existing = {i: Scheme(**s) for i, s in by_id.items()}
    files = sorted(p for p in Path(candidates_dir).glob("*.json") if not ids or p.stem in ids)
    if not files:
        res.skipped.append("no candidate files found")
        return res
    accepted: list[tuple[Path, dict]] = []
    for p in files:
        try:
            doc = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            res.errors.append(f"{p.name}: invalid JSON: {e}")
            continue
        rec = _check_candidate(p, doc, existing, allow_update, res, Path(candidates_dir), allow_unverified)
        if rec is None:
            continue
        if rec["id"] in by_id:
            res.updated.append(rec["id"])
        else:
            res.merged.append(rec["id"])
        by_id[rec["id"]] = rec
        existing[rec["id"]] = Scheme(**rec)
        accepted.append((p, rec))
    if res.errors:
        res.merged, res.updated = [], []
        return res
    res.errors += _regression(existing, cases_path)
    if res.errors or dry_run or not accepted:
        return res

    raw["schemes"] = list(by_id.values())
    sp = Path(schemes_path)
    web = resolve_web_copy(sp) if web_copy is AUTO else (Path(web_copy) if web_copy else None)
    if web is not None and not web.parent.is_dir():
        web = None
    bak = _backup(sp)
    web_bak = None
    if web is not None and web.exists():
        web_bak = web.with_name(web.name + ".premerge")
        shutil.copy2(web, web_bak)

    def rollback(msg: str) -> MergeResult:
        _atomic_write(sp, bak.read_bytes())
        if web is not None:
            if web_bak is not None:
                _atomic_write(web, web_bak.read_bytes())
            else:
                web.unlink(missing_ok=True)
        res.errors.append(msg)
        res.merged, res.updated = [], []
        return res

    try:
        _atomic_write(sp, (json.dumps(raw, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))
        if web is not None:
            _copy_atomic(sp, web)
    except OSError as e:
        return rollback(f"frontend copy / write failed ({e}); schemes.json restored from {bak.name}"
                        if web is not None else f"write failed ({e}); restored from {bak.name}")
    finally:
        if web_bak is not None:
            web_bak.unlink(missing_ok=True)
    if run_tests:
        proc = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"], cwd=ROOT,
                              capture_output=True, text=True)
        if proc.returncode != 0:
            return rollback("pytest failed after merge; schemes.json (and the frontend copy) were restored from "
                            "backup:\n" + proc.stdout[-1500:])
    done = Path(candidates_dir) / "merged"
    done.mkdir(exist_ok=True)
    for p, _ in accepted:
        shutil.move(str(p), done / p.name)
    return res
