"""Section splitter and document alias mapping for myscheme snapshots."""
from research.application import (body_lines, line_is_mandatory, map_document_line, mode_lines, split_sections,
                                  strip_header)

DOCS = {
    "aadhaar": {"aliases": ["aadhaar", "aadhar"]},
    "bank_passbook": {"aliases": ["bank passbook", "passbook", "bank details"]},
    "ration_card": {"aliases": ["ration card"]},
}

SNAP = """Source URL: https://www.myscheme.gov.in/schemes/x

Details
Benefits
Eligibility
Exclusions
Application Process
Documents Required
Frequently Asked Questions
Sources And References
Feedback

Details
A pension scheme.
Benefits
Rs 200 per month.
Eligibility
Age 60 or more.
Exclusions
Income tax payers.
Application Process
Online
Offline
Visit the Gram Panchayat.
Documents Required
Aadhaar Card
Bank Passbook
Frequently Asked Questions

Who can apply?

Anyone aged 60.
Sources And References
Scheme Guidelines
Was this helpful?
News and Updates
"""


def test_split_takes_second_occurrence_not_menu():
    s = split_sections(SNAP)
    assert s["Benefits"] == "Rs 200 per month."
    assert s["Eligibility"] == "Age 60 or more."
    assert s["Exclusions"] == "Income tax payers."
    assert body_lines(s["Documents Required"]) == ["Aadhaar Card", "Bank Passbook"]


def test_split_last_section_stops_at_footer():
    s = split_sections(SNAP)
    assert s["Sources And References"] == "Scheme Guidelines"
    assert "Was this helpful" not in "".join(s.values())


def test_heading_seen_only_once_is_absent():
    text = "Benefits\nEligibility\nBenefits\nSome benefit\n"
    s = split_sections(text)
    assert "Eligibility" not in s and s["Benefits"] == "Some benefit"


def test_mode_lines_and_header():
    s = split_sections(SNAP)
    assert mode_lines(s["Application Process"]) == ["online", "offline"]
    assert strip_header(SNAP).startswith("\nDetails")


def test_empty_text():
    assert split_sections("") == {}


def test_map_document_line_by_alias():
    assert map_document_line("Aadhar Number", DOCS) == ["aadhaar"]
    assert map_document_line("Bank Passbook", DOCS) == ["bank_passbook"]      # longest alias, not twice
    assert map_document_line("Ration card or Aadhaar", DOCS) == ["ration_card", "aadhaar"]
    assert map_document_line("Marriage photo", DOCS) == []
    assert map_document_line("Aadhaarcard1", DOCS) == []                      # word-bounded


def test_mandatory_flag():
    assert line_is_mandatory("Aadhaar Card")
    assert line_is_mandatory("Aadhaar (not mandatory for Assam and Meghalaya)")
    assert not line_is_mandatory("Ration card or voter id")
    assert not line_is_mandatory("Passport photo (optional)")


# ---------------------------------------------------------------- alternative documents, route derivation
def _d(doc, quote, mandatory=True):
    return {"doc": doc, "as_written": quote, "mandatory": mandatory, "quote": quote}


def test_assign_alternatives_groups_lines_that_offer_a_choice():
    from research.application import assign_alternatives
    addr = "Residential Proof (Voter card/ Electricity Bill/Aadhar Card)"
    docs = [_d("residence_proof", addr, False), _d("voter_id", addr, False), _d("electricity_bill", addr, False),
            _d("aadhaar", addr, False), _d("aadhaar", "Aadhar Number"), _d("bank_passbook", "Bank Passbook")]
    out = assign_alternatives(docs)
    assert [d.get("alternatives_group") for d in out] == ["address_proof"] * 4 + [None, None]
    assert all(d["mandatory"] for d in out[:4])  # one of the group is needed, so each option counts as required
    assert "alternatives_group" not in docs[0]  # input untouched


def test_assign_alternatives_continuation_line_joins_the_previous_group():
    from research.application import assign_alternatives
    age = "Age Proof - the birth certificate or school certificate may be relied on."
    cont = "In their absence ration card and EPIC may be considered."
    out = assign_alternatives([_d("age_proof", age), _d("birth_certificate", age), _d("school_certificate", age),
                               _d("ration_card", cont), _d("voter_id", cont),
                               _d("age_proof", "If there is no valid document, a Medical Officer may issue the age certificate.")])
    assert [d["alternatives_group"] for d in out] == ["age_proof"] * 6


def test_assign_alternatives_ignores_lines_without_a_cue_or_a_known_group():
    from research.application import assign_alternatives
    out = assign_alternatives([_d("aadhaar", "Aadhaar Card"), _d("ration_card", "Ration Card"),
                               _d("kyc_documents", "KYC details are fetched from Bank/Post Office Savings account."),
                               _d("savings_account", "KYC details are fetched from Bank/Post Office Savings account."),
                               _d("ration_card", "Women holder of BPL ration Card.", False)])
    assert not any("alternatives_group" in d for d in out)
    opt = assign_alternatives([_d("aadhaar", "Aadhaar or voter card (optional)", False), _d("voter_id", "Aadhaar or voter card (optional)", False)])
    assert [d["alternatives_group"] for d in opt] == ["id_proof", "id_proof"] and not any(d["mandatory"] for d in opt)


def test_derive_routes_one_route_per_mode_with_where_and_summary():
    from research.application import derive_routes
    steps = [{"n": 2, "action": "Log in", "where": None, "mode": "online", "quote": "q"},
             {"n": 1, "action": "Open the app", "where": None, "mode": "online", "quote": "q"},
             {"n": 3, "action": "Visit the bank", "where": "Bank", "mode": "offline", "quote": "q"}]
    on, off = derive_routes(steps, "https://x.gov.in", "Some office")
    assert (on["mode"], on["where"], on["summary"], [s["n"] for s in on["steps"]]) == ("online", "https://x.gov.in", "Open the app", [1, 2])
    assert (off["mode"], off["where"], off["summary"]) == ("offline", "Bank", "Visit the bank")
    assert derive_routes([{**steps[2], "where": None}], None, "Some office")[0]["where"] == "Some office"


def test_data_file_routes_are_consistent_with_steps():
    import json
    from pathlib import Path
    data = json.loads((Path(__file__).parent.parent / "data" / "applications.json").read_text(encoding="utf-8"))
    for sid, rec in data.items():
        assert isinstance(rec["source_official"], bool) and rec["routes"], sid
        assert len({r["mode"] for r in rec["routes"]}) == len(rec["routes"])
        steps = {s["n"]: s for s in rec["steps"]}
        for r in rec["routes"]:
            assert r["summary"] and r["steps"] and all(steps[s["n"]] == s for s in r["steps"]), sid
        for d in rec["documents"]:
            if "alternatives_group" in d:
                assert d["alternatives_group"] in ("id_proof", "address_proof", "age_proof", "family_proof")
    assert data["ssy"]["source_official"] is False and data["ignoaps"]["source_official"] is True
