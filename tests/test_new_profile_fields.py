"""Profile fields added for the support / housing schemes: occupation, category, disability, land, income period,
house type, breadwinner, ration card ... Three-valued rules, period conversion, the validator's period check,
question ranking, and plain answers in four languages."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from research.schema import ExtractedScheme
from research.validate import period_problems, quote_period, validate_candidate
from sahayak.answers import map_answer, normalise_enums
from sahayak.models import Profile, Scheme
from sahayak.rules import check_scheme
from sahayak.tools import FIELD_PRIORITY, Toolbox, annotate_questions, profile_skip_fields, rank_missing_fields


def scheme(*rules) -> Scheme:
    return Scheme(id="t", name="T", ministry="M", category="other", summary="s", benefits="b",
                  rules=[{**r, "reason": "because"} for r in rules], source_url="https://x.gov.in/t")


def verdict(profile: dict, *rules) -> str:
    return check_scheme(Profile(**profile), scheme(*rules)).verdict


def R(field, op, value):
    return {"field": field, "op": op, "value": value}


# field, op, value, passing profile value, failing profile value
CASES = [
    ("occupation", "eq", "street_vendor", "street_vendor", "farmer"),
    ("occupation", "in", ["fisherman", "coir_worker"], "coir_worker", "student"),
    ("is_unorganised_worker", "eq", True, True, False),
    ("is_epfo_esic_nps_member", "eq", False, False, True),
    ("is_current_income_tax_payer", "eq", False, False, True),
    ("disability_percentage", "gte", 80, 80, 79),
    ("land_holding_hectares", "lte", 2, 2.0, 2.5),
    ("social_category", "in", ["sc", "st"], "st", "general"),
    ("ration_card_type", "in", ["aay", "phh"], "aay", "apl"),
    ("monthly_income", "lte", 15000, 15000, 15001),
    ("household_size", "gte", 4, 4, 3),
    ("breadwinner_deceased", "eq", True, True, False),
    ("breadwinner_age_at_death", "lte", 59, 59, 60),
    ("house_type", "eq", "kutcha", "kutcha", "pucca"),
    ("has_pucca_house", "eq", False, False, True),
    ("has_bank_account", "eq", False, False, True),
]


@pytest.mark.parametrize("field,op,value,good,bad", CASES, ids=[c[0] + "-" + c[1] for c in CASES])
def test_new_field_is_true_false_or_unknown(field, op, value, good, bad):
    rule = R(field, op, value)
    assert verdict({field: good}, rule) == "eligible"
    assert verdict({field: bad}, rule) == "not_eligible"
    res = check_scheme(Profile(), scheme(rule))
    assert res.verdict == "need_info" and res.missing_fields == [field]   # never silently true or false


def test_unknown_does_not_hide_a_failure():
    assert verdict({"social_category": "general"}, R("social_category", "in", ["sc", "st"]),
                   R("occupation", "eq", "farmer")) == "not_eligible"


# ----------------------------------------------------------------------------- income period

def test_monthly_converts_to_annual_and_back_only_when_the_other_is_unknown():
    annual_rule, monthly_rule = R("annual_income", "lte", 180000), R("monthly_income", "lte", 15000)
    assert verdict({"monthly_income": 15000}, annual_rule) == "eligible"
    assert verdict({"monthly_income": 15001}, annual_rule) == "not_eligible"
    assert verdict({"annual_income": 180000}, monthly_rule) == "eligible"
    assert verdict({"annual_income": 180012}, monthly_rule) == "not_eligible"
    # a stated value is never overwritten by the conversion of the other
    assert verdict({"monthly_income": 1000, "annual_income": 999999}, annual_rule) == "not_eligible"
    assert verdict({"monthly_income": 1000, "annual_income": 999999}, monthly_rule) == "eligible"


def test_per_capita_monthly_income_needs_household_size():
    rule = R("per_capita_monthly_income", "lte", 2500)
    assert verdict({"monthly_income": 10000, "household_size": 4}, rule) == "eligible"
    assert verdict({"monthly_income": 10000, "household_size": 3}, rule) == "not_eligible"
    assert verdict({"annual_income": 120000, "household_size": 4}, rule) == "eligible"
    only_income = check_scheme(Profile(monthly_income=10000), scheme(rule))
    assert only_income.verdict == "need_info" and only_income.missing_fields == ["household_size"]
    nothing = check_scheme(Profile(), scheme(rule))
    assert nothing.verdict == "need_info" and nothing.missing_fields == ["household_size", "monthly_income"]


# ----------------------------------------------------------------------------- derived facts and consistency

def test_three_income_tax_fields_stay_separate():
    cur = R("is_current_income_tax_payer", "eq", False)
    assert verdict({"income_tax_payer_last_year": False}, cur) == "need_info"     # not inferred from last year
    assert verdict({"ever_income_tax_payer": False}, cur) == "eligible"           # never paid, so not paying now
    assert verdict({"ever_income_tax_payer": True}, cur) == "need_info"
    assert verdict({"is_current_income_tax_payer": True}, R("ever_income_tax_payer", "eq", True)) == "eligible"
    with pytest.raises(ValidationError):
        Profile(is_current_income_tax_payer=True, ever_income_tax_payer=False)


def test_house_and_land_derivations_and_contradictions():
    assert verdict({"house_type": "pucca"}, R("has_pucca_house", "eq", True)) == "eligible"
    assert verdict({"house_type": "none_homeless"}, R("has_pucca_house", "eq", False)) == "eligible"
    assert verdict({"has_pucca_house": False}, R("house_type", "eq", "kutcha")) == "need_info"
    with pytest.raises(ValidationError):
        Profile(house_type="kutcha", has_pucca_house=True)
    assert verdict({"owns_cultivable_land": False}, R("land_holding_hectares", "lte", 2)) == "eligible"
    assert verdict({"owns_cultivable_land": True}, R("land_holding_hectares", "lte", 2)) == "need_info"


@pytest.mark.parametrize("bad", [{"occupation": "astronaut"}, {"social_category": "brahmin"}, {"disability_percentage": 101},
                                 {"disability_percentage": True}, {"land_holding_hectares": -1},
                                 {"land_holding_hectares": "2"}, {"household_size": 0}, {"ration_card_type": "bpl"},
                                 {"house_type": "flat"}, {"monthly_income": -5}, {"monthly_income": 1.5}])
def test_new_fields_are_validated(bad):
    with pytest.raises(ValidationError):
        Profile(**bad)


def test_unknown_stays_none():
    p = Profile()
    for f in ("occupation", "is_unorganised_worker", "disability_percentage", "land_holding_hectares", "social_category",
              "ration_card_type", "monthly_income", "household_size", "breadwinner_deceased", "house_type"):
        assert getattr(p, f) is None


# ----------------------------------------------------------------------------- validator: period and unit

def cand(rules: list[dict]) -> ExtractedScheme:
    from tests.test_research_support import good_senior
    d = good_senior()
    d["rules"] = rules
    return ExtractedScheme(**d)


def rule(field, op, value, evidence):
    return {"field": field, "op": op, "value": value, "reason": "limit", "evidence": evidence}


@pytest.mark.parametrize("quote,period", [
    ("Income must not exceed Rs 15,000 per month", "monthly"), ("monthly income up to 15000", "monthly"),
    ("आय प्रति माह 15000 से अधिक नहीं", "monthly"), ("Rs 2,00,000 per annum", "annual"), ("annual family income", "annual"),
    ("income below Rs 3 lakh", None), ("Rs 15,000 per month, Rs 1,80,000 per year", None)])
def test_quote_period(quote, period):
    assert quote_period(quote) == period


def test_validator_rejects_a_period_that_does_not_match_its_quote():
    # the exact error the auditor caught on PMAY-G: a monthly limit written on the annual field
    bad = cand([rule("annual_income", "lte", 120000, "Any member earning more than Rs.10,000 per month")])
    errs = period_problems(bad)
    assert len(errs) == 1 and "period mismatch" in errs[0] and "monthly_income" in errs[0]
    assert period_problems(cand([rule("monthly_income", "lte", 10000, "earning more than Rs.10,000 per month")])) == []
    assert period_problems(cand([rule("annual_income", "lte", 200000, "income up to Rs 2,00,000 per annum")])) == []
    flip = period_problems(cand([rule("monthly_income", "lte", 200000, "income up to Rs 2,00,000 per annum")]))
    assert flip and "annual_income" in flip[0]
    assert period_problems(cand([rule("per_capita_monthly_income", "lte", 2000, "Rs 2,000 per annum per head")]))


def test_period_mismatch_is_a_blocking_error_in_validate_candidate():
    c = cand([rule("annual_income", "lte", 15000, "Income must not exceed Rs 15,000 per month")]).model_dump()
    v = validate_candidate(c, source_url="https://www.myscheme.gov.in/schemes/x")
    assert any("period mismatch" in e for e in v.errors)


def test_land_unit_must_be_hectares():
    errs = period_problems(cand([rule("land_holding_hectares", "lte", 5, "land up to 5 acres")]))
    assert errs and "hectares" in errs[0]
    assert not period_problems(cand([rule("land_holding_hectares", "lte", 2, "up to 2 hectares of land")]))


def test_float_field_boundaries_in_behavioural_checks():
    from research.validate import validate_record
    rec = {"id": "land_t", "name": "Land T", "ministry": "M", "category": "agriculture", "summary": "s",
           "benefits": "b", "source_url": "https://x.gov.in/t",
           "rules": [{**R("land_holding_hectares", "lte", 2), "reason": "up to 2 ha"},
                     {**R("per_capita_monthly_income", "lte", 2500), "reason": "per head"},
                     {**R("occupation", "eq", "farmer"), "reason": "farmers"}]}
    v = validate_record(rec)
    assert not v.errors and v.checks_run > 0


def test_unknown_field_is_still_rejected_and_derived_field_is_rule_only():
    with pytest.raises(ValidationError):
        Profile(per_capita_monthly_income=100)


# ----------------------------------------------------------------------------- ranking and do_not_ask

def test_new_fields_are_ranked_and_deterministic():
    assert set(FIELD_PRIORITY) <= set(Profile.model_fields)
    for f in ("occupation", "social_category", "disability_percentage", "monthly_income", "house_type"):
        assert f in FIELD_PRIORITY
    need = [{"scheme_id": "a", "missing_fields": ["occupation", "social_category"]},
            {"scheme_id": "b", "missing_fields": ["occupation"]},
            {"scheme_id": "c", "missing_fields": ["disability_percentage"]}]
    # occupation settles scheme b alone; disability settles c alone; occupation also appears twice
    assert rank_missing_fields(need) == ["occupation", "disability_percentage"]
    assert rank_missing_fields(need, exclude={"occupation"}) == ["social_category", "disability_percentage"]


def test_homeless_users_are_not_asked_household_or_lpg_questions():
    assert profile_skip_fields(Profile(house_type="none_homeless")) == {"household_has_lpg", "household_size",
                                                                        "has_pucca_house"}
    assert profile_skip_fields(Profile(house_type="kutcha")) == frozenset()
    tb = Toolbox(search_mode="bm25")
    out = tb.check_eligibility({"house_type": "none_homeless", "age": 40})
    assert {"household_has_lpg", "household_size", "has_pucca_house"} <= set(out["do_not_ask"])
    assert not {"household_has_lpg", "household_size"} & set(out["ask_first"])
    # an agent-side skip is added to, not replacing, the profile-based one
    again = annotate_questions(out, {"children"})
    assert {"household_has_lpg", "children"} <= set(again["do_not_ask"])


def test_no_breadwinner_death_question_for_age_when_no_death():
    assert "breadwinner_age_at_death" in profile_skip_fields(Profile(breadwinner_deceased=False))
    assert "land_holding_hectares" in profile_skip_fields(Profile(owns_cultivable_land=False))


def test_check_eligibility_accepts_the_new_fields_and_a_tool_schema_lists_them():
    from sahayak.tools import TOOL_SCHEMAS
    props = next(t for t in TOOL_SCHEMAS if t["function"]["name"] == "check_eligibility")["function"][
        "parameters"]["properties"]["profile"]["properties"]
    assert set(props) == set(Profile.model_fields)           # the agent can ask for and send every field
    assert props["occupation"]["enum"][0] == "street_vendor"
    assert "NOW" in props["is_current_income_tax_payer"]["description"]
    out = Toolbox(search_mode="bm25").check_eligibility(
        {"occupation": "street_vendor", "social_category": "sc", "disability_percentage": 0, "monthly_income": 9000})
    assert "error" not in out


# ----------------------------------------------------------------------------- plain answers, four languages

@pytest.mark.parametrize("field,text,want", [
    ("occupation", "sabzi bechti hai", "street_vendor"),            # Hinglish
    ("occupation", "main thela lagata hoon", "street_vendor"),
    ("occupation", "मैं सब्ज़ी बेचती हूँ", "street_vendor"),             # Hindi
    ("occupation", "நான் தெருவோரம் காய்கறி விற்கிறேன்", "street_vendor"),   # Tamil
    ("occupation", "I sell vegetables on the street", "street_vendor"),
    ("occupation", "khet mein mazdoori karta hu", "agricultural_labourer"),
    ("occupation", "मैं खेती करता हूँ", "farmer"),
    ("occupation", "naariyal ke resh ka kaam", None),
    ("occupation", "மீனவர்", "fisherman"),
    ("occupation", "ghar ghar kaam karti hu", "domestic_worker"),
    ("occupation", "mera apna dukan hai", "small_trader_shopkeeper"),
    ("occupation", "sarkari naukri nahi hai", None),                   # a negation is not the occupation
    ("occupation", "berozgar", "unemployed"),
    ("occupation", "tailor", "artisan_craftsperson"),
    ("occupation", "street_vendor", "street_vendor"),
    ("social_category", "anusuchit jati", "sc"),
    ("social_category", "अनुसूचित जनजाति", "st"),
    ("social_category", "Other Backward Class", "obc"),
    ("ration_card_type", "antyodaya card", "aay"),
    ("ration_card_type", "BPL card hai", "phh"),
    ("ration_card_type", "ration card nahi hai", "none"),
    ("ration_card_type", "राशन कार्ड नहीं है", "none"),
    ("house_type", "kachcha ghar", "kutcha"),
    ("house_type", "झोपड़ी में रहते हैं", "kutcha"),
    ("house_type", "pakka makaan", "pucca"),
    ("house_type", "ghar nahi hai, footpath par", "none_homeless"),
    ("house_type", "நான் வீடற்றவர்", "none_homeless"),
    ("house_type", "something odd", None),
])
def test_map_answer(field, text, want):
    assert map_answer(field, text) == want


def test_check_eligibility_maps_free_text_before_validating():
    assert normalise_enums({"occupation": "sabzi bechti hai", "age": 33})["occupation"] == "street_vendor"
    assert normalise_enums({"occupation": "farmer"})["occupation"] == "farmer"
    assert normalise_enums({"occupation": "???"})["occupation"] == "???"           # not guessed
    tb = Toolbox(search_mode="bm25")
    ok = tb.check_eligibility({"occupation": "sabzi bechti hai", "house_type": "jhopdi"})
    assert "error" not in ok
    bad = tb.check_eligibility({"occupation": "???"})
    assert "error" in bad
