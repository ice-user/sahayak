import copy

from research.bullet_check import check_label, is_valid

B = "The applicant should be a woman aged between 18 and 60 years with annual income below Rs. 2,50,000."


def _good():
    return {"rules": [
        {"field": "gender", "op": "eq", "value": "female", "quote": "should be a woman"},
        {"field": "age", "op": "gte", "value": 18, "quote": "aged between 18 and 60 years"},
        {"field": "age", "op": "lte", "value": 60, "quote": "aged between 18 and 60 years"},
        {"field": "annual_income", "op": "lte", "value": 249999, "quote": "annual income below Rs. 2,50,000"},
    ], "unmapped": []}


def test_good_label_passes():
    assert check_label(_good(), B) == []


def test_empty_label_ok_without_numbers():
    assert is_valid({"rules": [], "unmapped": []}, "Applicants are selected by a committee.")


def test_shape_errors():
    assert check_label([], B)
    assert check_label({"rules": []}, B)
    x = _good(); x["extra"] = 1
    assert check_label(x, B)
    x = _good(); del x["rules"][0]["quote"]
    assert check_label(x, B)
    x = _good(); x["rules"] = "nope"
    assert check_label(x, B)


def test_unknown_field_op_and_value_types():
    for patch in ({"field": "caste"}, {"op": "gt"}, {"value": "female "}, {"value": 1000},):
        x = _good(); x["rules"][0].update(patch)
        assert check_label(x, B), patch
    x = _good(); x["rules"][1]["value"] = "18"
    assert check_label(x, B)
    x = _good(); x["rules"][1]["value"] = True
    assert check_label(x, B)


def test_state_names_must_be_canonical_and_in_quote():
    b = "Only residents of Tamil Nadu can apply to this scheme."
    ok = {"rules": [{"field": "state", "op": "eq", "value": "Tamil Nadu", "quote": "residents of Tamil Nadu"}],
          "unmapped": []}
    assert check_label(ok, b) == []
    bad = copy.deepcopy(ok); bad["rules"][0]["value"] = "TN"
    assert check_label(bad, b)
    bad = copy.deepcopy(ok); bad["rules"][0]["value"] = "Kerala"
    assert any("not named" in e for e in check_label(bad, b))
    bad = copy.deepcopy(ok); bad["rules"][0]["op"] = "ne"
    assert check_label(bad, b)


def test_quote_must_be_verbatim():
    x = _good(); x["rules"][0]["quote"] = "must be a woman"
    assert any("verbatim" in e for e in check_label(x, B))
    x = _good(); x["rules"][0]["quote"] = "SHOULD  be a   WOMAN"      # case/whitespace normalised: fine
    assert check_label(x, B) == []
    x = _good(); x["rules"][0]["quote"] = "should be ... woman"
    assert check_label(x, B)


def test_numbers_must_be_in_quote():
    x = _good(); x["rules"][1]["value"] = 19
    assert any("19" in e for e in check_label(x, B))
    x = _good(); x["rules"][3]["value"] = 250000   # "below" makes 249999 legal, 250000 is the stated number: legal too
    assert check_label(x, B) == []
    x = _good(); x["rules"][3]["value"] = 300000
    assert check_label(x, B)


def test_bullet_numbers_must_be_covered():
    x = _good(); x["rules"] = x["rules"][:3]
    assert any("2,50,000" in e or "250000" in e for e in check_label(x, B))
    x["unmapped"] = [{"quote": "annual income below Rs. 2,50,000", "reason": "no monetary rule written"}]
    assert check_label(x, B) == []


def test_unmapped_shape_and_contradiction():
    x = _good(); x["unmapped"] = [{"quote": "should be a woman", "reason": ""}]
    assert check_label(x, B)
    x = _good(); x["unmapped"] = [{"quote": "not in bullet", "reason": "x"}]
    assert check_label(x, B)
    x = _good(); x["rules"][1]["value"] = 18; x["rules"][2]["value"] = 17
    x["rules"][2]["quote"] = "aged between 18 and 60 years"
    assert check_label(x, B)
