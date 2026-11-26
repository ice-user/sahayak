"""Profile validation, check_eligibility hardening, not_eligible caveats, split tax fields, tool error hygiene."""
import json

import pytest
from pydantic import ValidationError

from sahayak.models import Child, Profile, load_schemes
from sahayak.rules import check_all
from sahayak.tools import TOOL_SCHEMAS, Toolbox

TB = Toolbox(search_mode="bm25")
SCHEMES = load_schemes()


def verdicts(**profile):
    return {r.scheme_id: r.verdict for r in check_all(Profile(**profile), SCHEMES)}


# ---- item 1: not_eligible must not hide "you may still qualify" caveats
def test_pmuy_not_blocked_by_bpl_false():
    v = verdicts(gender="female", age=30, household_has_lpg=False, bpl=False)
    assert v["pmuy"] == "eligible"  # SC/ST, PMAY-G, AAY households qualify without a BPL card
    assert not any(r["field"] == "bpl" for r in SCHEMES["pmuy"].rules)
    assert any("poor" in c.lower() or "deprived" in c.lower() for c in SCHEMES["pmuy"].caveats)


def test_not_eligible_items_carry_name_and_caveats():
    out = TB.check_eligibility({"age": 65})
    item = next(i for i in out["not_eligible"] if i["scheme_id"] == "pmjay_senior")
    assert item["scheme_name"] == SCHEMES["pmjay_senior"].name
    assert any("regular PM-JAY" in c for c in item["caveats"])
    assert item["reasons"]
    for i in out["not_eligible"]:
        assert set(i) == {"scheme_id", "scheme_name", "reasons", "caveats"}


def test_system_prompt_tells_model_to_mention_not_eligible_caveats():
    from sahayak.agent import SYSTEM_PROMPT
    assert "not_eligible" in SYSTEM_PROMPT and "caveats" in SYSTEM_PROMPT
    assert "may still" in SYSTEM_PROMPT


# ---- item 2: strict profile
@pytest.mark.parametrize("bad", [
    {"income": 5, "age": 65, "bpl": True},          # unknown key
    {"age": True},                                   # bool is not an int
    {"age": 62.5}, {"age": "62"}, {"age": -1}, {"age": 121},
    {"annual_income": -5}, {"annual_income": 10**9 + 1},
    {"monthly_pension": -5}, {"monthly_pension": 10**9 + 1},
    {"bpl": "yes"}, {"bpl": 1},
    {"children": [{"age": -1, "gender": "female"}]},
    {"children": [{"age": 121}]},
    {"children": [{"age": 3, "colour": "red"}]},
    {"children": [{"age": 3}] * 16},
    {"state": 5},
])
def test_profile_rejects_bad_input(bad):
    with pytest.raises(ValidationError):
        Profile(**bad)


def test_profile_boundaries_accepted():
    Profile(age=0, annual_income=0, monthly_pension=10**9, children=[{"age": 120}] * 15)
    Child(age=0, gender="other")


@pytest.mark.parametrize("profile", [
    {"income": 5, "age": 65, "bpl": True},
    {"children": [{"age": -1, "gender": "female"}]},
    {"monthly_pension": -5, "owns_cultivable_land": True},
    {"age": True},
])
def test_bad_profile_is_tool_error_the_model_can_recover_from(profile):
    out = json.loads(TB.call("check_eligibility", json.dumps({"profile": profile})))
    assert "error" in out and "eligible" not in out
    assert out.get("details"), out
    assert all(set(d) >= {"field", "problem"} for d in out["details"])


def test_unknown_profile_key_names_the_key_and_lists_valid_fields():
    out = json.loads(TB.call("check_eligibility", json.dumps({"profile": {"income": 5}})))
    assert "income" in json.dumps(out) and "annual_income" in out["valid_fields"]


def test_tool_schema_forbids_extra_and_has_bounds():
    schema = next(t for t in TOOL_SCHEMAS if t["function"]["name"] == "check_eligibility")["function"]["parameters"]
    prof = schema["properties"]["profile"]
    assert prof["additionalProperties"] is False
    assert prof["properties"]["age"]["minimum"] == 0 and prof["properties"]["age"]["maximum"] == 120
    assert prof["properties"]["children"]["maxItems"] == 15
    assert schema["properties"]["scheme_ids"]["maxItems"] >= len(SCHEMES)
    top_k = next(t for t in TOOL_SCHEMAS if t["function"]["name"] == "search_schemes")["function"]["parameters"]["properties"]["top_k"]
    assert top_k["minimum"] == 1 and top_k["maximum"] == 10


# ---- item 3
def test_unknown_scheme_ids_return_error_with_valid_ids():
    out = TB.check_eligibility({"age": 30}, ["nope", "ssy"])
    assert "error" in out and "nope" in out["error"] and set(out["valid_ids"]) == set(SCHEMES)
    assert "eligible" not in out and "not_eligible" not in out


def test_scheme_ids_length_capped_and_type_checked():
    assert "error" in TB.check_eligibility({"age": 30}, ["ssy"] * 500)
    assert "error" in TB.check_eligibility({"age": 30}, "ssy")
    assert "error" not in TB.check_eligibility({"age": 30}, ["ssy", "apy"])


def test_scheme_ids_subset_is_respected():
    out = TB.check_eligibility({"age": 30}, ["ssy"])
    got = {i["scheme_id"] for k in ("eligible", "need_info", "not_eligible") for i in out[k]}
    assert got == {"ssy"}


@pytest.mark.parametrize("top_k, expected", [(0, 1), (-3, 1), (500, 10), (3, 3), (10, 10)])
def test_top_k_is_clamped(top_k, expected):
    seen = []

    class Spy:
        def search(self, query, k):
            seen.append(k)
            return []

    tb = Toolbox(index=Spy(), search_mode="bm25")
    tb.search_schemes("pension", top_k)
    assert seen == [expected]


def test_top_k_wrong_type_is_error():
    assert "error" in json.loads(TB.call("search_schemes", json.dumps({"query": "x", "top_k": "five"})))


# ---- item 4: two income-tax fields
def test_old_field_is_gone_and_new_fields_exist():
    assert "is_income_tax_payer" not in Profile.model_fields
    assert {"ever_income_tax_payer", "income_tax_payer_last_year"} <= set(Profile.model_fields)
    fields = {r["field"] for s in SCHEMES.values() for r in s.rules}
    assert "is_income_tax_payer" not in fields
    assert {"field": "ever_income_tax_payer"}.items() <= next(r for r in SCHEMES["apy"].rules if "tax" in r["field"]).items()
    assert next(r for r in SCHEMES["pm_kisan"].rules if "tax" in r["field"])["field"] == "income_tax_payer_last_year"


def test_apy_uses_ever_and_pm_kisan_uses_last_year():
    base = dict(age=30, has_bank_account=True, owns_cultivable_land=True, is_govt_employee=False, monthly_pension=0)
    # paid tax years ago but not last year: APY closed, PM-KISAN open
    v = verdicts(**base, ever_income_tax_payer=True, income_tax_payer_last_year=False)
    assert v["apy"] == "not_eligible" and v["pm_kisan"] == "eligible"
    v = verdicts(**base, ever_income_tax_payer=False, income_tax_payer_last_year=False)
    assert v["apy"] == "eligible" and v["pm_kisan"] == "eligible"
    v = verdicts(**base, income_tax_payer_last_year=True)  # last year implies ever
    assert v["apy"] == "not_eligible" and v["pm_kisan"] == "not_eligible"


def test_last_year_implies_ever_and_contradiction_rejected():
    with pytest.raises(ValidationError):
        Profile(ever_income_tax_payer=False, income_tax_payer_last_year=True)
    # never paid tax means not last year either: PM-KISAN needs no extra question
    v = verdicts(owns_cultivable_land=True, is_govt_employee=False, monthly_pension=0, ever_income_tax_payer=False)
    assert v["pm_kisan"] == "eligible"


# ---- item 13: no internals in tool errors
def test_unexpected_argument_error_has_no_python_internals():
    out = TB.call("check_eligibility", json.dumps({"profile": {}, "foo": 1}))
    for leak in ("TypeError", "Toolbox", "keyword argument", "unexpected"):
        assert leak not in out
    err = json.loads(out)["error"]
    assert "foo" in err and "profile" in err  # tells the model what to fix


def test_missing_argument_error_is_actionable():
    err = json.loads(TB.call("get_scheme_details", "{}"))["error"]
    assert "scheme_id" in err and "Error" not in err and "Toolbox" not in err


def test_non_object_and_bad_json_arguments():
    assert "error" in json.loads(TB.call("search_schemes", "[1,2]"))
    out = TB.call("search_schemes", "{not json")
    assert "JSONDecodeError" not in out and "error" in json.loads(out)


def test_unexpected_exception_is_generic_and_logged(caplog, monkeypatch):
    tb = Toolbox(search_mode="bm25")
    monkeypatch.setattr(tb.index, "search", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("secret /srv/path")))
    tb._fns["search_schemes"] = tb.search_schemes
    with caplog.at_level("ERROR"):
        out = tb.call("search_schemes", json.dumps({"query": "x"}))
    assert "secret" not in out and "RuntimeError" not in out and "error" in json.loads(out)
    assert "secret /srv/path" in caplog.text
