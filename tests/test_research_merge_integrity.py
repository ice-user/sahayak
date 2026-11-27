"""Merge integrity (atomic write, snapshot containment, backups, frontend copy) and free-text / source_url checks."""
import json
import os
import re
import shutil

import pytest

from research import runner
from research.merge import merge_candidates
from sahayak.models import load_schemes
from tests.test_research_graph import CASES
from tests.test_research_support import (SENIOR, SENIOR_URL, good_senior, make_graph, start_file, variant)
from tests.conftest import requires_symlinks


def approved(tmp_path, cand=None, url=SENIOR_URL, tid="m1", **resume):
    graph, deps, _ = make_graph(tmp_path, [cand or good_senior()])
    start_file(graph, SENIOR, source_url=url, thread_id=tid)
    out = runner.resume(graph, tid, {"action": "approve", "reviewer": "tester", **resume})
    return deps, out


def cand_path(deps, sid="sample_senior_support"):
    return deps.candidates_dir / f"{sid}.json"


def merge(deps, **kw):
    kw.setdefault("cases_path", CASES)
    kw.setdefault("web_copy", None)
    return merge_candidates(deps.candidates_dir, deps.schemes_path, **kw)


# ------------------------------------------------------------------ snapshot required / contained
def test_missing_snapshot_is_blocking_unless_allowed(tmp_path):
    deps, _ = approved(tmp_path)
    p = cand_path(deps)
    doc = json.loads(p.read_text())
    del doc["provenance"]["source_snapshot"]
    p.write_text(json.dumps(doc))
    before = deps.schemes_path.read_bytes()
    res = merge(deps)
    assert not res.ok and any("snapshot" in e for e in res.errors) and deps.schemes_path.read_bytes() == before
    res = merge(deps, allow_unverified=True)
    assert res.ok and res.merged == ["sample_senior_support"]
    assert any("NOT re-verified" in s for s in res.skipped)


def test_snapshot_file_deleted_is_blocking(tmp_path):
    deps, _ = approved(tmp_path)
    (deps.candidates_dir / "sources" / "sample_senior_support.txt").unlink()
    res = merge(deps)
    assert not res.ok and any("snapshot" in e for e in res.errors)


@pytest.mark.parametrize("evil", ["../outside.txt", "sources/../../outside.txt", "ABS"])
def test_snapshot_path_traversal_is_rejected(tmp_path, evil):
    deps, _ = approved(tmp_path)
    outside = tmp_path / "outside.txt"
    shutil.copy(deps.candidates_dir / "sources" / "sample_senior_support.txt", outside)
    evil = str(outside) if evil == "ABS" else evil
    p = cand_path(deps)
    doc = json.loads(p.read_text())
    doc["provenance"]["source_snapshot"] = evil
    p.write_text(json.dumps(doc))
    res = merge(deps, allow_unverified=False)
    assert not res.ok and any("outside the candidates directory" in e for e in res.errors)
    # even with --allow-unverified a traversal is an error, not a skip
    res = merge(deps, allow_unverified=True)
    assert not res.ok and any("outside the candidates directory" in e for e in res.errors)


@requires_symlinks
def test_snapshot_symlink_escape_is_rejected(tmp_path):
    deps, _ = approved(tmp_path)
    snap = deps.candidates_dir / "sources" / "sample_senior_support.txt"
    target = tmp_path / "elsewhere.txt"
    shutil.copy(snap, target)
    snap.unlink()
    snap.symlink_to(target)
    res = merge(deps)
    assert not res.ok and any("outside the candidates directory" in e for e in res.errors)


def test_scheme_must_match_the_evidenced_candidate(tmp_path):
    deps, _ = approved(tmp_path)
    p = cand_path(deps)
    doc = json.loads(p.read_text())
    doc["scheme"]["benefits"] = "Rs 8,00,000 lump sum"          # evidence says Rs 800 a month
    p.write_text(json.dumps(doc))
    res = merge(deps)
    assert not res.ok and any("does not match" in e for e in res.errors)


# ------------------------------------------------------------------ atomic write, backups, frontend copy
def test_write_is_atomic_and_leaves_no_temp_files(tmp_path, monkeypatch):
    deps, _ = approved(tmp_path)
    calls = []
    real_replace = os.replace
    monkeypatch.setattr(os, "replace", lambda a, b: (calls.append((str(a), str(b))), real_replace(a, b))[1])
    real_fsync = os.fsync
    synced = []
    monkeypatch.setattr(os, "fsync", lambda fd: (synced.append(fd), real_fsync(fd))[1])
    assert merge(deps).ok
    assert any(b == str(deps.schemes_path) and a != b for a, b in calls) and synced
    assert [p.name for p in tmp_path.iterdir() if p.name.endswith(".tmp") or p.name.startswith(".schemes")] == []


def test_crash_during_write_keeps_the_original_intact(tmp_path, monkeypatch):
    deps, _ = approved(tmp_path)
    before = deps.schemes_path.read_bytes()

    def boom(a, b):
        raise OSError("disk full")
    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError):
        merge(deps)
    assert deps.schemes_path.read_bytes() == before
    assert [p for p in tmp_path.iterdir() if p.name.endswith(".tmp")] == []


def test_timestamped_backups_are_never_overwritten(tmp_path):
    deps, _ = approved(tmp_path)
    original = deps.schemes_path.read_bytes()
    assert merge(deps).ok
    baks = list(tmp_path.glob("schemes.json.*.bak"))
    assert len(baks) == 1 and baks[0].read_bytes() == original
    first_bak = baks[0]
    # a second merge (same second is fine: names carry microseconds plus a counter) keeps the first backup
    shutil.move(deps.candidates_dir / "merged" / "sample_senior_support.json", cand_path(deps))
    after_first = deps.schemes_path.read_bytes()
    assert merge(deps, allow_update=True).ok
    baks = list(tmp_path.glob("schemes.json.*.bak"))
    assert len(baks) == 2 and first_bak.read_bytes() == original
    assert after_first in [b.read_bytes() for b in baks]


def test_frontend_copy_is_byte_identical_when_directory_exists(tmp_path):
    deps, _ = approved(tmp_path)
    web = tmp_path / "web" / "src" / "data"
    web.mkdir(parents=True)
    (web / "schemes.json").write_text("{}")
    assert merge(deps, web_copy=web / "schemes.json").ok
    assert (web / "schemes.json").read_bytes() == deps.schemes_path.read_bytes()
    assert "sample_senior_support" in (web / "schemes.json").read_text()


def test_frontend_copy_skipped_when_directory_missing_and_not_written_on_dry_run(tmp_path):
    deps, _ = approved(tmp_path)
    missing = tmp_path / "nope" / "schemes.json"
    assert merge(deps, web_copy=missing).ok and not missing.parent.exists()
    web = tmp_path / "w"
    web.mkdir()
    assert merge(deps, dry_run=True, web_copy=web / "schemes.json").ok and not (web / "schemes.json").exists()


def test_failed_frontend_copy_rolls_everything_back(tmp_path, monkeypatch):
    deps, _ = approved(tmp_path)
    before = deps.schemes_path.read_bytes()
    web = tmp_path / "web"
    web.mkdir()
    import research.merge as M
    monkeypatch.setattr(M, "_copy_atomic", lambda src, dst: (_ for _ in ()).throw(OSError("read-only")))
    res = merge(deps, web_copy=web / "schemes.json")
    assert not res.ok and any("frontend" in e for e in res.errors) and res.merged == []
    assert deps.schemes_path.read_bytes() == before and cand_path(deps).exists()


def test_default_web_copy_never_touches_the_real_frontend_for_temp_databases(tmp_path):
    from research.merge import resolve_web_copy
    deps, _ = approved(tmp_path)
    assert resolve_web_copy(deps.schemes_path) is None


# ------------------------------------------------------------------ free text, source_url
def with_free_text(**changes):
    return variant(good_senior(), **changes)


def start_with(tmp_path, cand, **kw):
    graph, deps, _ = make_graph(tmp_path, [cand])
    out = start_file(graph, SENIOR, source_url=kw.pop("url", SENIOR_URL), thread_id="f1")
    return graph, deps, out


def test_url_outside_allowlist_is_blocking_and_flagged(tmp_path):
    c = with_free_text(how_to_apply="Submit the form at https://pm-kisan-help.example.com/apply or call 9876543210.")
    graph, deps, out = start_with(tmp_path, c)
    errs = " ".join(out.payload["errors"])
    assert "pm-kisan-help.example.com" in errs
    flags = {(f["kind"], f["status"]) for f in out.payload["contact_flags"]}
    assert ("url", "blocked") in flags and ("phone", "verify") in flags
    assert "Contact details in free text" in out.summary and "BLOCKED" in out.summary
    assert "approve" in out.payload["allowed_actions"]        # URL-only errors can be approved explicitly
    refused = runner.resume(graph, "f1", {"action": "approve", "reviewer": "t"})
    assert refused.paused and "approve refused" in refused.payload["note"]


def test_reviewer_can_approve_an_off_list_url_explicitly(tmp_path):
    c = with_free_text(how_to_apply="Also see https://csc.example.com/apply for help.")
    graph, deps, out = start_with(tmp_path, c)
    assert out.payload["errors"] and "approve" in out.payload["allowed_actions"]
    wrong = runner.resume(graph, "f1", {"action": "approve", "reviewer": "t", "allow_urls": ["https://other.example"]})
    assert wrong.paused
    done = runner.resume(graph, "f1", {"action": "approve", "reviewer": "t", "allow_urls": ["https://csc.example.com/apply"]})
    assert done.status == "approved"
    doc = json.loads(cand_path(deps).read_text())
    assert doc["provenance"]["review"]["approved_urls"] == ["https://csc.example.com/apply"]
    # merge accepts it only because the approval is recorded...
    assert merge(deps).ok
    # ...and rejects the same file if the approval is removed
    (tmp_path / "x").mkdir()
    deps2, _ = approved(tmp_path / "x", variant(good_senior(), how_to_apply="x"), tid="z")
    p = cand_path(deps2)
    d = json.loads(p.read_text())
    d["scheme"]["how_to_apply"] = "See https://evil.example.org/pay now"
    d["evidence"]["candidate"]["how_to_apply"] = d["scheme"]["how_to_apply"]
    p.write_text(json.dumps(d))
    res = merge(deps2)
    assert not res.ok and any("evil.example.org" in e for e in res.errors)


def test_gov_and_source_domain_urls_are_allowed_but_still_listed(tmp_path):
    c = with_free_text(how_to_apply="Apply at https://www.myscheme.gov.in/schemes/x or https://example.org/fixtures/help "
                                    "or www.nic.in. Helpline: 1800-111-555.")
    _, _, out = start_with(tmp_path, c)
    assert not any("allowlist" in e for e in out.payload["errors"])
    kinds = {(f["kind"], f["status"]) for f in out.payload["contact_flags"]}
    assert ("url", "ok") in kinds and ("phone", "verify") in kinds
    assert not any(f["status"] == "blocked" for f in out.payload["contact_flags"])


@pytest.mark.parametrize("text", [
    "Visit evil.com for details", "Pay at HTTP://EVIL.IN/x", "go to www.free-money.org", "mail help@evil.com",
])
def test_scanner_finds_bare_domains_and_uppercase(text):
    from research.freetext import scan_free_text
    flags = scan_free_text({"how_to_apply": text}, source_hosts=["example.org"])
    assert flags and (any(f["status"] == "blocked" for f in flags) or any(f["kind"] == "email" for f in flags))


def test_scanner_ignores_ordinary_numbers_and_prose():
    from research.freetext import scan_free_text
    txt = "Income up to Rs 2,00,000 per year; age 60 to 79; e.g. approved in 2023-24. Sample.Applicants may apply."
    assert scan_free_text({"benefits": txt, "summary": txt}) == []


def test_unmapped_criteria_text_is_scanned_via_caveats(tmp_path):
    c = good_senior()
    c["caveats"] = ["Report fraud at http://scam.example.net/report"]
    _, _, out = start_with(tmp_path, c)
    assert any("scam.example.net" in e for e in out.payload["errors"])


def test_source_url_must_equal_final_url_or_be_explicit(tmp_path):
    # URL source with redirect: the recorded url is the FINAL url
    from research.fetch import fetch_file
    from research.graph import build_graph
    from tests.test_research_support import make_deps
    deps, _ = make_deps(tmp_path, [good_senior()])
    def fetcher(src):
        f = fetch_file(SENIOR, allowed_dirs=[SENIOR.parent])
        f.final_url = "https://www.gov.in/final"
        f.warnings = ["redirected: https://short.example/x -> https://www.gov.in/final"]
        return f
    deps.fetcher = fetcher
    g = build_graph(deps)
    out = runner.start(g, "https://short.example/x", thread_id="r1")
    assert out.payload["scheme_record"]["source_url"] == "https://www.gov.in/final"
    assert out.state["final_url"] == "https://www.gov.in/final" and not out.state["source_url_explicit"]
    assert any("redirected" in w for w in out.payload["warnings"])
    # explicit --source-url wins and is marked explicit
    out = runner.start(g, "https://short.example/x", source_url="https://official.gov.in/page", thread_id="r2")
    assert out.payload["scheme_record"]["source_url"] == "https://official.gov.in/page"
    assert out.state["source_url_explicit"] is True


def test_merge_rejects_source_url_that_is_neither_final_nor_explicit(tmp_path):
    deps, _ = approved(tmp_path)
    p = cand_path(deps)
    d = json.loads(p.read_text())
    d["provenance"]["source_url_explicit"] = False
    d["provenance"]["final_url"] = "https://www.gov.in/real"
    p.write_text(json.dumps(d))
    res = merge(deps)
    assert not res.ok and any("final URL" in e for e in res.errors)
    d["scheme"]["source_url"] = "https://www.gov.in/real"
    d["provenance"]["source_url"] = "https://www.gov.in/real"
    p.write_text(json.dumps(d))
    assert merge(deps).ok
    assert load_schemes(deps.schemes_path)["sample_senior_support"].source_url == "https://www.gov.in/real"


def test_merge_requires_provenance_source_url_to_match_the_record(tmp_path):
    deps, _ = approved(tmp_path)
    p = cand_path(deps)
    d = json.loads(p.read_text())
    d["scheme"]["source_url"] = "https://attacker.example/phish"
    p.write_text(json.dumps(d))
    assert not merge(deps).ok
