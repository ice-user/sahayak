from server.phrases import PHRASES
from server.suggestions import detect_language, missing_fields, suggestions_for

REQUIRED = ["bpl", "has_bank_account", "ever_income_tax_payer", "income_tax_payer_last_year",
            "owns_cultivable_land", "household_has_lpg",
            "pregnant_or_lactating", "is_govt_employee", "marital_status", "gender"]


def test_detect_language():
    assert detect_language("मेरी उम्र 60 है") == "hi"
    assert detect_language("என் வயது 60") == "ta"
    assert detect_language("Mera naam Ram hai, meri umar 60 saal") == "hinglish"
    assert detect_language("My father is 60 years old") == "en"
    assert detect_language("hello, I need a pension scheme") == "en"


def test_phrase_table_is_complete():
    for name in REQUIRED:
        assert set(PHRASES[name]) == {"en", "hi", "hinglish", "ta"}, name
        sizes = {len(v) for v in PHRASES[name].values()}
        assert len(sizes) == 1, name


def test_documented_bpl_examples():
    assert suggestions_for(["bpl"], "en") == ["Yes, we have a BPL card", "No BPL card", "Not sure"]
    assert suggestions_for(["bpl"], "hi") == ["हाँ, बीपीएल कार्ड है", "बीपीएल कार्ड नहीं है", "पता नहीं"]


def test_numeric_and_unknown_fields_give_no_chips():
    for name in ("age", "monthly_pension", "annual_income", "children"):
        assert suggestions_for([name, "bpl"], "en") == []
    assert suggestions_for([], "en") == []


def test_at_most_two_fields_and_four_options():
    assert len(suggestions_for(["has_bank_account", "is_govt_employee", "bpl"], "en")) == 4
    assert suggestions_for(["bpl", "has_bank_account"], "en") == PHRASES["bpl"]["en"]
    assert len(suggestions_for(["marital_status"], "en")) == 4


def test_missing_fields_dedupes_in_order():
    result = {"need_info": [{"missing_fields": ["bpl", "age"]}, {"missing_fields": ["bpl", "gender"]}]}
    assert missing_fields(result) == ["bpl", "age", "gender"]
    assert missing_fields({"error": "x"}) == [] and missing_fields(None) == []
