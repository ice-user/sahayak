"""research.application_check: quote, domain, doc-id, applies_if and number checks."""
import copy

from research.application_check import check_documents_file, check_record, is_official_url

SRC = """Source URL: https://www.myscheme.gov.in/schemes/x
Application Process
Visit the bank branch where you hold a savings account and submit the form.
Raise a grievance at https://pgportal.gov.in or call 1800-110-069 toll free.
Visit website https://enps.nsdl.com/eNPS/NationalPensionSystem.html to register.
Exclusions
Any citizen who paid Income Tax shall not be eligible.
Pension stops after the age of 80 years.
Documents Required
Aadhaar Card
FAQ
Who can join?
Anyone between 18 and 40 years.
"""
DOCS = {"aadhaar": {"name": {}, "aliases": [], "how_to_get": None}}


def base():
    return {
        "mode": "both", "portal_url": "https://enps.nsdl.com/eNPS/NationalPensionSystem.html",
        "office": "Bank branch", "helpline": "1800-110-069", "fees": None,
        "steps": [{"n": 1, "action": "Go to your bank branch.", "where": "bank", "mode": "offline",
                   "quote": "Visit the bank branch where you hold a savings account"}],
        "documents": [{"doc": "aadhaar", "as_written": "Aadhaar Card", "mandatory": True, "quote": "Aadhaar Card"}],
        "watch_outs": [{"kind": "exclusion", "text": "Income tax payers are not eligible.",
                        "quote": "Any citizen who paid Income Tax shall not be eligible.",
                        "applies_if": {"field": "ever_income_tax_payer", "op": "eq", "value": True}}],
        "faq": [{"q": "Who can join?", "a": "Anyone between 18 and 40 years.",
                 "quote": "Anyone between 18 and 40 years."}],
        "enrol_points": [{"type": "bank", "name": "Your bank branch.", "locator_url": None,
                          "quote": "Visit the bank branch where you hold a savings account"}],
        "grievance": {"text": "Call 1800-110-069.", "url_or_number": "1800-110-069",
                      "quote": "call 1800-110-069 toll free"},
        "source_url": "https://www.myscheme.gov.in/schemes/x", "verified_at": "2026-11-28"}


def run(rec, **kw):
    return check_record(rec, SRC, DOCS, **kw)


def test_good_record_passes_unchanged():
    clean, log = run(base())
    step = base()["steps"][0]
    routes = [{"mode": "offline", "summary": step["action"], "where": "bank", "steps": [step]}]
    assert log == [] and clean == {**base(), "routes": routes, "source_official": True}


def test_quote_not_in_source_is_dropped():
    r = base()
    r["steps"][0]["quote"] = "Go to the nearest bank and ask the clerk"
    clean, log = run(r)
    assert clean["steps"] == [] and any("steps[0]" in ln and "verbatim" in ln for ln in log)


def test_number_in_text_must_be_in_quote():
    r = base()
    r["watch_outs"].append({"kind": "benefit_stops", "text": "Pension stops at age 80.",
                            "quote": "Pension stops after the age of 80 years.", "applies_if": None})
    r["watch_outs"].append({"kind": "benefit_stops", "text": "Pension stops at age 75.",
                            "quote": "Pension stops after the age of 80 years.", "applies_if": None})
    clean, log = run(r)
    assert len(clean["watch_outs"]) == 2 and any("75" in ln for ln in log)


def test_unknown_doc_id_dropped():
    r = base()
    r["documents"][0]["doc"] = "passport"
    clean, log = run(r)
    assert clean["documents"] == [] and any("documents.json" in ln for ln in log)


def test_applies_if_field_and_op_validated():
    r = base()
    r["watch_outs"][0]["applies_if"] = {"field": "shoe_size", "op": "eq", "value": 9}
    clean, log = run(r)
    assert clean["watch_outs"] == [] and log
    r = base()
    r["watch_outs"][0]["applies_if"] = {"field": "age", "op": "between", "value": 9}
    assert run(r)[0]["watch_outs"] == []


def test_applies_if_number_must_be_in_quote():
    r = base()
    r["watch_outs"][0]["applies_if"] = {"field": "age", "op": "gte", "value": 90}
    clean, log = run(r)
    assert clean["watch_outs"] == [] and any("not in the quote" in ln for ln in log)
    r["watch_outs"][0]["applies_if"] = {"field": "age", "op": "gte", "value": 80}
    r["watch_outs"][0]["quote"] = "Pension stops after the age of 80 years."
    r["watch_outs"][0]["text"] = "Pension stops after age 80."
    assert len(run(r)[0]["watch_outs"]) == 1


def test_portal_must_be_official_and_in_source():
    r = base()
    r["portal_url"] = "https://apply-now.example.com/"
    assert run(r)[0]["portal_url"] is None
    r["portal_url"] = "https://invented.gov.in/"            # official domain but not stated anywhere
    assert run(r)[0]["portal_url"] is None
    assert run(r, known_portals=["https://invented.gov.in/"])[0]["portal_url"] == "https://invented.gov.in/"


def test_helpline_digits_must_be_in_source():
    r = base()
    r["helpline"] = "1800-999-999"
    assert run(r)[0]["helpline"] is None


def test_faq_capped_at_six():
    r = base()
    r["faq"] = [copy.deepcopy(r["faq"][0]) for _ in range(8)]
    clean, log = run(r)
    assert len(clean["faq"]) == 6 and any("more than 6" in ln for ln in log)


def test_enrol_point_locator_must_be_official_and_live():
    r = base()
    r["enrol_points"][0]["locator_url"] = "https://findmycsc.nic.in/"
    assert run(r)[0]["enrol_points"][0]["locator_url"] == "https://findmycsc.nic.in/"              # live not checked
    assert run(r, live_urls=[])[0]["enrol_points"][0]["locator_url"] is None                       # not confirmed
    assert run(r, live_urls=["https://findmycsc.nic.in"])[0]["enrol_points"][0]["locator_url"]    # confirmed
    r["enrol_points"][0]["locator_url"] = "https://csc-locator.com/"
    assert run(r, live_urls=["https://csc-locator.com/"])[0]["enrol_points"][0]["locator_url"] is None


def test_enrol_point_bad_type_or_quote_dropped():
    r = base()
    r["enrol_points"][0]["type"] = "railway"
    r["enrol_points"].append({"type": "csc", "name": "A CSC.", "locator_url": None, "quote": "go to a CSC kiosk"})
    clean, log = run(r)
    assert clean["enrol_points"] == [] and len(log) == 2


def test_grievance_checks():
    r = base()
    r["grievance"]["url_or_number"] = "1800-000-000"
    assert run(r)[0]["grievance"] is None
    r = base()
    r["grievance"] = {"text": "Use the grievance portal.", "url_or_number": "https://pgportal.gov.in",
                      "quote": "Raise a grievance at https://pgportal.gov.in"}
    assert run(r)[0]["grievance"] is not None
    r["grievance"]["url_or_number"] = "https://complaints.example.com"
    assert run(r)[0]["grievance"] is None


def test_structural_failures():
    r = base()
    r["mode"] = "sometimes"
    assert run(r)[0] is None
    r = base()
    r["verified_at"] = "28/11/2026"
    assert run(r)[0] is None
    assert run("x")[0] is None


def test_steps_are_renumbered_after_drops():
    r = base()
    r["steps"] = [{"n": 1, "action": "Bogus.", "where": None, "mode": "online", "quote": "not in source anywhere"},
                  {"n": 2, "action": "Go to bank.", "where": None, "mode": "offline",
                   "quote": "Visit the bank branch where you hold a savings account"}]
    clean, _ = run(r)
    assert [s["n"] for s in clean["steps"]] == [1]


def test_official_url_rule():
    assert is_official_url("https://pmuy.gov.in/") and is_official_url("web.umang.gov.in/x")
    assert is_official_url("https://enps.nsdl.com/eNPS/") and is_official_url("https://pmkisan.nic.in")
    assert not is_official_url("https://gov.in.evil.com/") and not is_official_url("https://angelone.in")
    assert not is_official_url("ftp://x.gov.in") and not is_official_url(None)


def test_documents_file_shape():
    ok = {"aadhaar": {"name": {"en": "a", "hi": "b", "ta": "c", "hinglish": "d"}, "aliases": ["aadhaar"],
                      "how_to_get": None}}
    assert check_documents_file(ok) == []
    bad = copy.deepcopy(ok)
    bad["aadhaar"]["name"].pop("ta")
    assert check_documents_file(bad)


def test_real_documents_json_is_valid():
    import json
    from pathlib import Path
    docs = json.loads((Path(__file__).resolve().parent.parent / "data" / "documents.json").read_text("utf-8"))
    assert check_documents_file(docs) == [] and 25 <= len(docs) <= 40


# ---------------------------------------------------------------- routes, alternatives_group, source_official
def _route(rec, summary, where="bank", mode="offline"):
    return {"mode": mode, "summary": summary, "where": where, "steps": [dict(s) for s in rec["steps"]]}


def test_routes_derived_when_absent_and_source_official_computed():
    clean, log = run(base())
    assert log == [] and [r["mode"] for r in clean["routes"]] == ["offline"]
    assert clean["routes"][0]["summary"] == "Go to your bank branch." and clean["routes"][0]["steps"] == clean["steps"]
    r = base()
    r["source_url"] = "https://www.angelone.in/knowledge-center/ssy"
    r["source_official"] = True  # never taken on trust
    assert run(r)[0]["source_official"] is False
    for url, official in (("https://www.myscheme.gov.in/schemes/x", True), ("https://nic.in/x", True),
                          ("https://blog.example.com/gov.in", False)):
        r["source_url"] = url
        assert run(r)[0]["source_official"] is official


def test_route_summary_must_be_a_step_action_or_supported_by_its_quotes():
    r = base()
    r["routes"] = [_route(r, "Visit your bank branch and submit the form")]  # nouns: bank, branch, form? in quote
    clean, log = run(r)
    assert log == [] and clean["routes"][0]["summary"] == "Visit your bank branch and submit the form"
    r["routes"] = [_route(r, "Apply on the UMANG app with your mobile number")]  # umang / mobile not in the quote
    clean, log = run(r)
    assert clean["routes"][0]["summary"] == "Go to your bank branch."  # falls back to the first step
    assert any("routes[0].summary" in ln for ln in log)
    r["routes"] = [_route(r, "Go to your bank branch.")]  # reusing a step action is always fine
    assert run(r)[1] == []


def test_route_steps_and_where_are_checked_against_the_record():
    r = base()
    bad = _route(r, "Visit the bank branch", where="a made up place")
    bad["steps"][0]["action"] = "Something the record does not say"
    r["routes"] = [bad]
    clean, log = run(r)
    assert clean["routes"][0]["steps"] == clean["steps"]  # unmatched step dropped -> derived routes instead
    assert any("no steps that match" in ln for ln in log)
    r["routes"] = [_route(r, "Visit the bank branch", where="a made up place")]
    clean, log = run(r)
    assert clean["routes"][0]["where"] is None and any("routes[0].where" in ln for ln in log)
    r["routes"] = [{"mode": "offline", "summary": "x"}]
    assert any("keys must be exactly" in ln for ln in run(r)[1])


def test_alternatives_group_needs_a_quote_that_offers_alternatives():
    r = base()
    r["documents"][0]["alternatives_group"] = "id_proof"
    clean, log = run(r)
    assert clean["documents"] == [] and any("offers no alternatives" in ln for ln in log)  # quote is just "Aadhaar Card"
    src = SRC + "Voter card or Aadhaar Card\n"
    d = {"doc": "aadhaar", "as_written": "Voter card or Aadhaar Card", "mandatory": True,
         "quote": "Voter card or Aadhaar Card", "alternatives_group": "id_proof"}
    r["documents"] = [d]
    clean, log = check_record(r, src, DOCS)
    assert log == [] and clean["documents"][0]["alternatives_group"] == "id_proof"
    r["documents"] = [{**d, "alternatives_group": "nonsense"}]
    assert any("alternatives_group must be one of" in ln for ln in check_record(r, src, DOCS)[1])
