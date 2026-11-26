import json

import pytest

from sahayak.tools import Toolbox

TB = Toolbox(search_mode="bm25")  # deterministic, no model download


@pytest.mark.parametrize("query,expected", [
    ("widow pension", "ignwps"),
    ("pension for old age elderly", "ignoaps"),
    ("health insurance hospital treatment senior", "pmjay_senior"),
    ("savings for my daughter", "ssy"),
    ("free LPG gas connection", "pmuy"),
    ("farmer income support", "pm_kisan"),
    ("accident insurance", "pmsby"),
    ("pregnant woman maternity money", "pmmvy"),
])
def test_search_top3(query, expected):
    ids = [h["scheme_id"] for h in TB.search_schemes(query, top_k=3)]
    assert expected in ids, f"{query!r} -> {ids}"


def test_call_returns_json_on_bad_tool():
    assert "error" in json.loads(TB.call("nope", "{}"))


def test_call_returns_json_on_bad_args():
    assert "error" in json.loads(TB.call("check_eligibility", '{"profile": {"age": "old"}}'))


def test_call_handles_malformed_json():
    assert "error" in json.loads(TB.call("search_schemes", "{not json"))


def test_unknown_scheme_details():
    out = TB.get_scheme_details("does_not_exist")
    assert "error" in out and "valid_ids" in out
