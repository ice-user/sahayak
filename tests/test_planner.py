"""Planner unit tests on fixtures (no network, no LLM)."""
from pathlib import Path

import pytest

from sahayak import planner
from sahayak.models import Profile, load_schemes

FIX = Path(__file__).parent / "fixtures"


@pytest.fixture
def tmp_path():
    """Own temp dir (the shared pytest tmp root is cleaned by other processes on this machine)."""
    import tempfile
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        yield Path(d)


@pytest.fixture(autouse=True)
def fixtures(monkeypatch):
    monkeypatch.setattr(planner, "APPLICATIONS_PATH", FIX / "applications_sample.json")
    monkeypatch.setattr(planner, "DOCUMENTS_PATH", FIX / "documents_sample.json")


def plan(ids, profile=None, lang="en"):
    return planner.build_plan(ids, profile, lang, schemes=load_schemes())


def test_checklist_merges_docs_and_sorts_mandatory_then_shared():
    p = plan(["pm_kisan", "pmuy"])
    docs = [c["doc"] for c in p["checklist"]]
    assert len(docs) == len(set(docs)) == 4
    aadhaar = next(c for c in p["checklist"] if c["doc"] == "aadhaar")
    assert aadhaar["needed_for"] == ["pm_kisan", "pmuy"] and aadhaar["mandatory"] is True  # any scheme mandatory
    assert aadhaar["have"] is None and aadhaar["how_to_get"]["source_url"] == "https://uidai.gov.in"
    mand = [c["mandatory"] for c in p["checklist"]]
    assert mand == sorted(mand, reverse=True)
    assert docs[0] == "aadhaar"  # mandatory and shared by two schemes
    assert docs[-1] == "bank_passbook"  # the only optional one


def test_steps_follow_the_recommended_route_only():
    p = plan(["pmuy", "pm_kisan", "ssy"])  # no profile: online preferred where a route exists
    steps = p["steps"]
    assert [s["group_kind"] for s in steps] == ["online", "online", "offline", "offline"]
    online = [s for s in steps if s["group_kind"] == "online"]
    assert [s["n"] for s in online] == [1, 2]  # sorted by n within the scheme
    assert [s["group"] for s in steps if s["group_kind"] == "offline"] == ["Block agriculture office", "Post office"]
    assert p["summary"]["trips"] == 2 and p["summary"]["offices"] == ["Block agriculture office", "Post office"]
    assert set(steps[0]) >= {"scheme_id", "scheme_name", "n", "action", "where", "mode", "source_url"}
    assert steps[0]["scheme_name"].startswith("Pradhan Mantri Kisan")
    # an older user gets PM-KISAN's office route instead: all trips are offline, no online steps at all
    q = plan(["pmuy", "pm_kisan", "ssy"], {"age": 70})
    assert [s["group_kind"] for s in q["steps"]] == ["offline"] * 3
    assert [s["group"] for s in q["steps"]] == ["Block agriculture office", "Block agriculture office", "Post office"]
    assert q["summary"]["trips"] == 2 and q["summary"]["online_steps"] == 0


def test_watch_outs_personal_true_false_unknown():
    prof = Profile(income_tax_payer_last_year=True, household_has_lpg=False)
    w = plan(["pm_kisan", "pmuy"], prof)["watch_outs"]
    by_text = {x["text"]: x["personal"] for x in w}
    assert by_text["Income tax payers are excluded"] is True
    assert by_text["Only one connection per household"] is False
    assert by_text["Aadhaar must be linked to the bank account"] is None  # no condition: kept, not hidden
    assert [x["personal"] for x in w] == [True, None, False]  # applies first


def test_unknown_profile_never_hides_watch_outs():
    for prof in (None, {}, Profile()):
        w = plan(["pm_kisan", "pmuy"], prof)["watch_outs"]
        assert len(w) == 3 and all(x["personal"] is None for x in w)
    assert plan(["pm_kisan"], {"income_tax_payer_last_year": True})["summary"]["personal_watch_outs"] == 1


def test_localisation_with_fallback_to_en():
    hi = {c["doc"]: c["name"] for c in plan(["pm_kisan", "pmuy"], lang="hi")["checklist"]}
    assert hi["aadhaar"] == "आधार कार्ड" and hi["land_record"] == "भूमि रिकॉर्ड"
    assert hi["bpl_card"] == "BPL card"  # no hi name: falls back to en
    assert hi["bank_passbook"] == "Bank passbook"  # no documents.json entry: as_written
    assert plan(["pmuy"], lang="xx")["lang"] == "en"


def test_where_to_go_per_scheme_and_grouped_enrol_points():
    p = plan(["pm_kisan", "pmuy", "ssy"])
    w = {x["scheme_id"]: x for x in p["where_to_go"]}
    assert w["pm_kisan"]["grievance"]["url_or_number"] == "pmkisan-ict@gov.in"
    assert w["pm_kisan"]["helpline"] == "155261" and w["pm_kisan"]["portal_url"] == "https://pmkisan.gov.in"
    assert w["pmuy"]["grievance"] is None and w["pmuy"]["office"] == "Block agriculture office"
    assert w["ssy"]["enrol_points"] == []  # optional fields absent: safe empty values
    g = p["enrol_groups"]
    assert g[0]["type"] == "Common Service Centre" and g[0]["scheme_ids"] == ["pm_kisan", "pmuy"]
    assert len(g[0]["points"]) == 1  # same point merged
    assert g[0]["points"][0]["locator_url"] == "https://locator.csccloud.in"  # first non-null locator kept
    assert g[0]["points"][0]["scheme_ids"] == ["pm_kisan", "pmuy"]
    assert [x["type"] for x in g] == ["Common Service Centre", "LPG distributor"]


def test_missing_and_unknown_schemes_degrade():
    p = plan(["pmuy", "ignoaps", "nope", "pmuy"])  # ignoaps: known scheme without application data
    assert p["summary"]["schemes"] == 1
    assert p["summary"]["missing_application_data"] == ["ignoaps"]
    assert p["summary"]["unknown_schemes"] == ["nope"]
    assert p["sources"] == ["https://pmuy.gov.in"]


def test_no_data_files_gives_empty_plan(monkeypatch, tmp_path):
    monkeypatch.setattr(planner, "APPLICATIONS_PATH", tmp_path / "missing.json")
    monkeypatch.setattr(planner, "DOCUMENTS_PATH", tmp_path / "missing2.json")
    p = plan(["pm_kisan"])
    assert p["checklist"] == p["steps"] == p["watch_outs"] == p["where_to_go"] == p["enrol_groups"] == []
    assert p["summary"]["data_available"] is False and p["summary"]["missing_application_data"] == ["pm_kisan"]
    assert planner.get_application("pm_kisan") is None


def test_corrupt_data_file_is_ignored(monkeypatch, tmp_path):
    bad = tmp_path / "a.json"
    bad.write_text("{not json", encoding="utf-8")
    monkeypatch.setattr(planner, "APPLICATIONS_PATH", bad)
    assert plan(["pm_kisan"])["summary"]["data_available"] is False


def test_get_application():
    assert planner.get_application("ssy")["office"] == "Post office"
    assert planner.get_application("zzz") is None


def _generic_app(office, portal, specific, source):
    return {
        "mode": "online", "portal_url": portal, "office": office, "helpline": None, "fees": None,
        "steps": [
            {"n": 1, "action": "Keep the documents ready", "where": "At home", "mode": "online", "quote": "q"},
            {"n": 2, "action": "Start the application on the official portal", "where": "Official portal", "mode": "online", "quote": "q"},
            {"n": 3, "action": specific, "where": "Bank branch", "mode": "offline", "quote": "q"},
        ],
        "documents": [], "watch_outs": [], "faq": [], "source_url": source, "verified_at": "2026-11-27",
    }


def test_generic_steps_collapse_across_schemes(monkeypatch, tmp_path):
    import json
    apps = {
        "apy": _generic_app("Bank branch", "https://a.in", "Enrol at your bank branch for APY", "https://a.in/src"),
        "pmjjby": _generic_app("Bank branch", "https://b.in", "Enrol at your bank branch for PMJJBY", "https://b.in/src"),
        "pmsby": _generic_app("Bank  branch", "https://c.in", "Enrol at your bank branch for PMSBY", "https://c.in/src"),
        "ssy": _generic_app("Bank branch", "https://d.in", "Open an SSY account at a post office counter", "https://a.in/src"),
    }
    f = tmp_path / "apps.json"
    f.write_text(json.dumps(apps), encoding="utf-8")
    monkeypatch.setattr(planner, "APPLICATIONS_PATH", f)
    p = plan(["apy", "pmjjby", "pmsby", "ssy"], {"age": 70})  # offline preferred: routes with an office
    steps = p["steps"]
    assert [s["group_kind"] for s in steps][0] == "prepare"
    assert sum(s["group_kind"] == "prepare" for s in steps) == 1
    prep = steps[0]
    assert prep["scheme_ids"] == ["apy", "pmjjby", "pmsby", "ssy"] and prep["scheme_id"] == "apy"
    assert len(prep["scheme_names"]) == 4 and prep["source_urls"] == ["https://a.in/src", "https://b.in/src", "https://c.in/src"]
    assert not [s for s in steps if s["action"].startswith("Start the application")]  # online route not recommended
    online = plan(["apy", "pmjjby", "pmsby", "ssy"])
    portal = [s for s in online["steps"] if s["action"].startswith("Start the application")]
    assert len(portal) == 1 and len(portal[0]["scheme_ids"]) == 4 and online["summary"]["trips"] == 0
    # distinct enrolment texts: APY/PMJJBY/PMSBY differ only by one token (merged), SSY stays separate
    offline = [s for s in steps if s["group_kind"] == "offline"]
    assert len(offline) == 2 and offline[0]["scheme_ids"] == ["apy", "pmjjby", "pmsby"]
    assert len(steps) == 3  # 1 prepare + 2 offline
    assert [s["group_kind"] for s in steps] == ["prepare", "offline", "offline"]
    assert p["summary"]["trips"] == 1 and online["summary"]["portals"] == ["https://a.in", "https://b.in", "https://c.in", "https://d.in"]
    assert p["summary"]["prepare_steps"] == 1


def test_steps_have_scheme_lists_even_when_not_merged():
    s = plan(["ssy"])["steps"][0]
    assert s["scheme_ids"] == ["ssy"] and s["scheme_names"] == [s["scheme_name"]] and s["source_urls"] == [s["source_url"]]


# ---------------------------------------------------------------- routes, groups, dedupe, source quality
def _rec(steps, documents=(), watch=(), source="https://www.myscheme.gov.in/schemes/x", **kw):
    return {"mode": "both", "portal_url": "https://x.gov.in", "office": "Block office", "helpline": None, "fees": None,
            "steps": steps, "documents": list(documents), "watch_outs": list(watch), "faq": [], "source_url": source,
            "verified_at": "2026-11-28", **kw}


def _st(n, action, mode, where=None):
    return {"n": n, "action": action, "where": where, "mode": mode, "quote": "q"}


def _use(monkeypatch, tmp_path, apps, docs=None):
    import json
    a, d = tmp_path / "apps.json", tmp_path / "docs.json"
    a.write_text(json.dumps(apps), encoding="utf-8")
    d.write_text(json.dumps(docs or {}), encoding="utf-8")
    monkeypatch.setattr(planner, "APPLICATIONS_PATH", a)
    monkeypatch.setattr(planner, "DOCUMENTS_PATH", d)


TWO_ROUTES = _rec([_st(1, "Open the app", "online"), _st(2, "Log in with OTP", "online"), _st(3, "Submit the form", "online"),
                   _st(4, "Go to the block office", "offline", "Block office")])


def test_derive_routes_splits_by_mode_and_attaches_support_steps():
    r = planner.derive_routes(TWO_ROUTES["steps"], "https://x.gov.in", "Block office")
    assert [x["mode"] for x in r] == ["online", "offline"]
    assert [s["n"] for s in r[0]["steps"]] == [1, 2, 3] and r[0]["where"] == "https://x.gov.in"
    assert r[1]["where"] == "Block office" and r[1]["summary"] == "Go to the block office"
    # a download-the-form step belongs to the office route that follows; a status check never makes an online route
    steps = [_st(1, "Download and print the form", "online"), _st(2, "Submit it at the bank", "offline", "Bank"),
             _st(3, "Check your status on the portal", "online")]
    only = planner.derive_routes(steps)
    assert [(x["mode"], [s["n"] for s in x["steps"]]) for x in only] == [("offline", [1, 2, 3])]
    assert planner.derive_routes([]) == []


@pytest.mark.parametrize("profile,mode", [
    (None, "online"), ({"age": 59}, "online"), ({"age": 60}, "offline"), ({"age": 75}, "offline"),
    ({"age": 30, "homeless": True}, "offline"), ({"age": 30, "vulnerability_flags": ["homeless"]}, "offline"),
    ({"age": 30, "vulnerable": True}, "offline"), ({"age": 30, "has_mobile": False}, "offline"),
    ({"age": 30, "has_mobile": True}, "online"),
])
def test_recommended_route_depends_on_digital_access(monkeypatch, tmp_path, profile, mode):
    _use(monkeypatch, tmp_path, {"ssy": TWO_ROUTES})
    card = plan(["ssy"], profile)["schemes"][0]
    assert card["recommended_mode"] == mode
    assert [r["recommended"] for r in card["routes"]] == [r["mode"] == mode for r in card["routes"]]
    assert sum(r["recommended"] for r in card["routes"]) == 1


def test_trips_and_steps_count_only_the_recommended_route(monkeypatch, tmp_path):
    _use(monkeypatch, tmp_path, {"ssy": TWO_ROUTES, "pmuy": _rec([_st(1, "Visit the agency", "offline", "Gas agency")])})
    young, old = plan(["ssy", "pmuy"], {"age": 30}), plan(["ssy", "pmuy"], {"age": 70})
    assert young["summary"]["trips"] == 1 and young["summary"]["offices"] == ["Gas agency"]  # ssy goes online: no trip
    assert young["summary"]["steps"] == 4 and young["summary"]["all_route_steps"] == 5
    assert old["summary"]["trips"] == 2 and old["summary"]["offices"] == ["Block office", "Gas agency"]
    assert old["summary"]["steps"] == 2
    # every route is still listed with its own steps, for the UI
    assert [(r["mode"], len(r["steps"])) for r in young["schemes"][0]["routes"]] == [("online", 3), ("offline", 1)]


def test_stored_routes_are_used_over_derived_ones(monkeypatch, tmp_path):
    stored = {"mode": "offline", "summary": "Apply at the office", "where": "Block office", "steps": [_st(1, "Go", "offline")]}
    _use(monkeypatch, tmp_path, {"ssy": _rec([_st(1, "Go", "offline")], routes=[stored])})
    r = plan(["ssy"])["schemes"][0]["routes"]
    assert r[0]["summary"] == "Apply at the office" and r[0]["where"] == "Block office" and r[0]["recommended"] is True


def _doc(doc, quote, group=None, mandatory=True):
    d = {"doc": doc, "as_written": quote, "mandatory": mandatory, "quote": quote}
    if group:
        d["alternatives_group"] = group
    return d


def test_alternative_documents_collapse_into_one_group(monkeypatch, tmp_path):
    line = "Address proof (Voter card/ Electricity bill/ Aadhaar)"
    a = _rec([_st(1, "Go", "offline")], [_doc("residence_proof", line, "address_proof"), _doc("voter_id", line, "address_proof"),
                                          _doc("electricity_bill", line, "address_proof"), _doc("aadhaar", line, "address_proof"),
                                          _doc("bank_passbook", "Bank passbook")])
    b = _rec([_st(1, "Go", "offline")], [_doc("ration_card", "Ration card or voter card", "address_proof"),
                                          _doc("voter_id", "Ration card or voter card", "address_proof"),
                                          _doc("bank_passbook", "Bank passbook")])
    docs = {"voter_id": {"name": {"en": "Voter ID"}, "aliases": [], "how_to_get": None}}
    _use(monkeypatch, tmp_path, {"a": a, "b": b}, docs)
    p = plan(["a", "b"])
    groups = [c for c in p["checklist"] if "doc_group" in c]
    assert len(groups) == 1 and len(p["checklist"]) == 2  # one group + the shared passbook, not 7 rows
    g = groups[0]
    assert g["doc_group"] == "address_proof" and g["label"] == "Any one address proof" and g["mandatory"] is True
    assert [o["doc"] for o in g["options"]] == ["voter_id", "electricity_bill", "aadhaar", "ration_card"]  # generic head dropped
    assert g["needed_for"] == ["a", "b"] and g["options"][0]["name"] == "Voter ID"
    assert all("doc" not in c for c in groups) and p["summary"]["documents"] == 2 and p["summary"]["mandatory_documents"] == 2
    assert next(c for c in plan(["a"], lang="hi")["checklist"] if "doc_group" in c)["label"] == "कोई एक पते का प्रमाण"
    # a document asked on its own for the same purpose folds into the group instead of a second row
    c = _rec([_st(1, "Go", "offline")], [_doc("residence_proof", "Proof of address")])
    _use(monkeypatch, tmp_path, {"a": a, "c": c}, docs)
    both = plan(["a", "c"])["checklist"]
    assert [x.get("doc_group") for x in both if "doc_group" in x] == ["address_proof"]
    assert not [x for x in both if x.get("doc") == "residence_proof"]


def test_unknown_group_label_lists_the_options(monkeypatch, tmp_path):
    a = _rec([_st(1, "Go", "offline")], [_doc("aadhaar", "Aadhaar / PAN", "custom"), _doc("pan", "Aadhaar / PAN", "custom")])
    _use(monkeypatch, tmp_path, {"a": a}, {"aadhaar": {"name": {"en": "Aadhaar"}}, "pan": {"name": {"en": "PAN card"}}})
    assert plan(["a"])["checklist"][0]["label"] == "Any one of: Aadhaar / PAN card"


def _w(text, kind="exclusion", cond=None):
    return {"kind": kind, "text": text, "quote": "q", "applies_if": cond}


def test_watch_outs_deduped_within_and_across_schemes(monkeypatch, tmp_path):
    a = _rec([_st(1, "Go", "offline")], watch=[_w("Pension stops if the widow remarries."), _w("Pension stops if the widow remarries"),
                                               _w("Only one connection per household", "one_per_family")])
    b = _rec([_st(1, "Go", "offline")], watch=[_w("Pension stops if the widow re-marries."),
                                               _w("Pension stops if the widow remarries.", "benefit_stops"),
                                               _w("Income tax payers are excluded")])
    _use(monkeypatch, tmp_path, {"a": a, "b": b})
    w = plan(["a", "b"])["watch_outs"]
    assert len(w) == 4  # 6 raw: 3 merged into one; the same text with another kind stays separate
    merged = next(x for x in w if x["text"].startswith("Pension stops") and x["kind"] == "exclusion")
    assert merged["scheme_ids"] == ["a", "b"] and len(merged["scheme_names"]) == 2 and merged["scheme_id"] == "a"
    assert sum(x["kind"] == "benefit_stops" for x in w) == 1
    assert plan(["a", "b"])["summary"]["watch_outs"] == 4


def test_source_official_passes_through_and_defaults_from_the_url(monkeypatch, tmp_path):
    ok = _rec([_st(1, "Go", "offline")], source_official=True)
    bad = _rec([_st(1, "Go", "offline")], source="https://www.angelone.in/ssy", source_official=False)
    old = _rec([_st(1, "Go", "offline")], source="https://www.indiapost.gov.in/x")  # record without the field
    old2 = _rec([_st(1, "Go", "offline")], source="https://blog.example.com/x")
    _use(monkeypatch, tmp_path, {"ok": ok, "bad": bad, "old": old, "old2": old2})
    p = plan(["ok", "bad", "old", "old2"])
    assert {c["scheme_id"]: c["source_official"] for c in p["schemes"]} == {"ok": True, "bad": False, "old": True, "old2": False}
    assert p["summary"]["unofficial_sources"] == ["bad", "old2"]
    assert planner.is_official("https://nic.in") and not planner.is_official("https://gov.in.evil.com/") and not planner.is_official(None)
