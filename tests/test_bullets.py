from research.bullets import (bullets_from_file, bullets_from_snapshot, eligibility_lines, snapshot_url,
                              split_bullets)

SNAP = """Source URL: https://www.myscheme.gov.in/schemes/x

Back
Details
Benefits
Eligibility
Application Process
Check Eligibility
Some Scheme
Details
Blurb that mentions Eligibility nowhere.
Benefits
Rs. 5,000 per year.
Eligibility
The applicant should be a resident of Bihar.

The applicant must have land of at least 0.25 acres. Applicant must be registered on the DBT portal.
For Mentor Institute (MI):
Not applicable
- Age should be between 18 and 40 years; must be a woman.
Exclusions
Income tax payers are excluded from this scheme.
Application Process
Online
"""


def test_section_is_second_eligibility_until_next_heading():
    lines = eligibility_lines(SNAP)
    assert lines[0] == "The applicant should be a resident of Bihar."
    assert "Income tax payers" not in " ".join(lines)
    assert "Rs. 5,000" not in " ".join(lines)


def test_no_second_heading_gives_nothing():
    assert eligibility_lines("Eligibility\nfoo bar baz qux\n") == []
    assert bullets_from_snapshot("") == []


def test_split_sentences_prefixes_and_boilerplate():
    b = bullets_from_snapshot(SNAP)
    assert b == [
        "The applicant should be a resident of Bihar.",
        "The applicant must have land of at least 0.25 acres.",
        "Applicant must be registered on the DBT portal.",
        "Age should be between 18 and 40 years; must be a woman.",
    ]
    assert not any("Not applicable" in x or x.endswith("(MI):") for x in b)


def test_abbreviations_do_not_split():
    b = split_bullets(["Annual income should not exceed Rs. 2,50,000 per year. Applicant must be a Govt. employee."])
    assert b == ["Annual income should not exceed Rs. 2,50,000 per year.", "Applicant must be a Govt. employee."]


def test_dedupe_and_short_lines():
    assert split_bullets(["Must be a farmer.", "must be a farmer.", "Yes.", "N/A", "  "]) == ["Must be a farmer."]


def test_group_label_dropped():
    assert split_bullets(["For Mentor Institute(MI):", "The institute should be approved by AICTE."]) == [
        "The institute should be approved by AICTE."]


def test_url_and_file(tmp_path):
    assert snapshot_url(SNAP) == "https://www.myscheme.gov.in/schemes/x"
    p = tmp_path / "x.txt"
    p.write_text(SNAP, encoding="utf-8")
    url, b = bullets_from_file(p)
    assert url.endswith("/x") and b[0].startswith("The applicant should")
