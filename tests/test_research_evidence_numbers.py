"""Regression tests: the evidence matcher must never accept a quote whose numbers differ from the source."""
import pytest

from research import validate as V
from research.evidence import find_quote, numbers_in, value_in_evidence
from tests.test_research_support import good_senior

SRC = ("Eligibility. Annual family income below Rs 2,00,000 per annum. Applicant must be 60 or older. "
       "Candidates aged 18 to 45 may apply. Pension is paid to persons of 60 years of age. "
       "Income up to Rs 12,00,000 per annum is the ceiling for the premium tier. "
       "A person cannot hold more than 160 years of age proof.")


@pytest.mark.parametrize("quote", [
    "Annual family income below Rs 1,00,000 per annum",     # fuzzy 97.9 before the fix
    "Applicant must be 70 or older",
    "Candidates aged 18 to 40 may apply",
    "Annual family income below Rs 20,00,000 per annum",
])
def test_changed_number_is_never_found(quote):
    assert not find_quote(quote, SRC)


def test_substring_needs_digit_boundaries():
    assert not find_quote("160 years of age proof", "Persons of 1160 years of age proof")
    assert find_quote("60 years of age", SRC)                       # genuine occurrence still found
    only160 = "a person cannot hold more than 160 years of age proof"
    assert not find_quote("60 years of age", only160)
    assert not find_quote("2,00,000 per annum", "ceiling Rs 12,00,000 per annum applies")
    assert not find_quote("Rs 5,000 per month", "Rs 25,000 per month for all")


def test_equivalent_number_forms_are_accepted_when_text_otherwise_matches():
    src = "Family income must be below Rs 1,00,000 per annum for eligibility under this scheme."
    assert find_quote("Family income must be below Rs 1,00,000 per annum", src)
    assert find_quote("Family income must be below Rs 100000 per annum for eligibility", src)   # fuzzy, same value
    assert not find_quote("Family income must be below Rs 10,00,000 per annum for eligibility", src)


def test_numbers_in_handles_indian_grouping_words_and_scripts():
    n = lambda t: set(numbers_in(t))
    assert n("Rs 1,00,000") == n("100000") == n("1 lakh") == n("₹1 lakh") == n("one lakh") == n("Rs.1,00,000/-")
    assert n("2.5 lakh") == n("Rs 250000")
    assert n("1 crore") == n("1,00,00,000")
    assert n("६० वर्ष") == n("60 years")                  # Devanagari digits
    assert n("60 வயது") == n("60 years")                  # Tamil digits
    assert n("sixty years") == n("60 years") and n("twenty-five") == n("25")
    assert n("ages 18,19") == n("18 and 19")                # a comma without grouping is not a number


@pytest.mark.parametrize("value, evidence, ok", [
    (60, "must be 160 years of age", False),
    (60, "must be 60 years of age", True),
    (10000, "income up to Rs 100000", False),
    (100000, "income up to Rs 1,00,000", True),
    (100000, "income up to Rs 1 lakh", True),
    (200000, "income up to Rs 2 lakh", True),
    (60, "must be 6 0 years", False),
    (60, "साठ वर्ष या ६० वर्ष", True),
])
def test_value_in_evidence_digit_boundaries(value, evidence, ok):
    assert value_in_evidence(value, evidence) is ok


def test_value_in_evidence_derived_values_are_restricted():
    # exclusive bounds: "below 18" => lte 17; only with a matching exclusive word and op
    assert value_in_evidence(17, "children below 18 years", op="lte")
    assert not value_in_evidence(17, "children aged 18 years", op="lte")
    assert not value_in_evidence(19, "children below 18 years", op="lte")
    assert value_in_evidence(61, "persons above 60 years", op="gte")
    # a monthly figure is no longer converted to annual: it goes on monthly_income as stated
    assert not value_in_evidence(96000, "income of Rs 8,000 per month", field="annual_income")
    assert value_in_evidence(8000, "income of Rs 8,000 per month", field="monthly_income")


def test_validate_candidate_blocks_value_missing_from_evidence():
    c = good_senior()
    c["rules"][0]["value"] = 65
    r = V.validate_candidate(c, {}, source_url="https://example.org/s")
    assert any("rules[0]" in e and "65" in e and "evidence" in e for e in r.errors)
    c = good_senior()
    c["rules"][0]["evidence"] = "The applicant must be 160 years of age or above."
    r = V.validate_candidate(c, {}, source_url="https://example.org/s")
    assert any("rules[0]" in e for e in r.errors)
    ok = V.validate_candidate(good_senior(), {}, source_url="https://example.org/s")
    assert not ok.errors


def test_validate_candidate_checks_child_sub_values():
    from tests.test_research_support import good_girl
    g = good_girl()
    g["rules"][0]["value"][1]["value"] = 12
    r = V.validate_candidate(g, {}, source_url="https://example.org/s")
    assert any("rules[0]" in e and "12" in e for e in r.errors)
