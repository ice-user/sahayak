"""Offline unit tests: evidence matcher, fetching/cleaning, validator, merge, report."""
import json
import shutil

import httpx
import pytest

from research import validate as V
from research.evidence import find_quote, normalize
from research.fetch import FetchError, fetch_file, fetch_url, html_to_text, pdf_to_text
from research.llm import LLMOutputError, parse_json_object
from research.batch import links_from_page, read_sources, render_report, BatchItem
from research.schema import ExtractedScheme, to_scheme_dict
from sahayak.models import DATA_PATH, Profile, Scheme, load_schemes
from sahayak.rules import check_scheme

from tests.test_research_support import (GIRL_TXT, SENIOR, YOUTH, build_pdf, good_girl, good_senior, good_youth,
                                         variant)

TEXT = ("The applicant’s household must be Below Poverty Line (BPL).\n"
        "Age limit – between 18 and 35 years.  Income  not more than   Rs 3,00,000.\n"
        "आवेदक की आयु साठ वर्ष या उससे अधिक होनी चाहिए।")


# ------------------------------------------------------------------ evidence
@pytest.mark.parametrize("quote", [
    "household must be below poverty line (bpl)",            # case
    "applicant's household must be Below Poverty Line",       # straight apostrophe vs smart
    "Age limit - between 18 and 35 years",                    # hyphen vs en dash
    "Income not more than Rs 3,00,000",                       # whitespace runs / NBSP
    "“Below Poverty Line (BPL)”",                   # smart double quotes around
])
def test_evidence_accepts_normalisation_differences(quote):
    assert find_quote(quote, TEXT)


def test_evidence_devanagari_and_zero_width():
    assert find_quote("आवेदक की आयु साठ वर्ष या उससे अधिक होनी चाहिए", TEXT)
    assert find_quote("आवेदक  की‍ आयु साठ वर्ष", TEXT)          # extra space + ZWJ
    assert not find_quote("आवेदक की आयु पचास वर्ष या उससे अधिक", TEXT)  # different number word


def test_evidence_rejects_hallucination_and_short_quotes():
    assert not find_quote("applicant must be 65 years of age or above and a farmer", TEXT)
    assert find_quote("zzzzzzzz", TEXT).method == "missing"
    assert find_quote("BPL", TEXT).method == "too_short"
    assert find_quote("   ", TEXT).method == "empty"


def test_evidence_fuzzy_tolerates_tiny_typo_but_not_a_changed_number():
    ok = find_quote("household must be Below Poverty Line (BPL)s", TEXT)      # stray char
    assert ok and ok.method in ("exact", "fuzzy")
    assert find_quote("between 18 and 35 years", TEXT)
    assert not find_quote("Age limit - between 18 and 45 years of age ok", TEXT)


def test_evidence_ellipsis_fragments():
    assert find_quote("household must be ... Below Poverty Line (BPL)", TEXT)
    assert find_quote("household must be … Below Poverty Line", TEXT)
    assert not find_quote("household must be ... a completely invented clause", TEXT)


def test_normalize_idempotent():
    assert normalize(normalize(TEXT)) == normalize(TEXT)


# ------------------------------------------------------------------ fetch
def test_html_cleaning_drops_chrome_and_keeps_content():
    t = fetch_file(SENIOR).text
    assert "The applicant must be 60 years of age or above." in t
    assert "Skip to main content" not in t and "tracking" not in t and "Copyright" not in t
    assert "आयु साठ वर्ष" in t
    assert "Rs 800 is paid directly" in t    # &nbsp; and double space normalised


def test_content_hash_is_stable():
    assert fetch_file(SENIOR).content_hash == fetch_file(SENIOR).content_hash
    assert fetch_file(SENIOR).content_hash != fetch_file(YOUTH).content_hash


def test_pdf_text_extraction(tmp_path):
    p = tmp_path / "s.pdf"
    lines = ["SYNTHETIC TEST FIXTURE (not official)", "Sample Girl Savings (fiction) Scheme",
             "A girl child who is not older than 10 years may open an account."]
    p.write_bytes(build_pdf(lines))
    f = fetch_file(p, allowed_dirs=[tmp_path])
    assert f.kind == "pdf" and "not older than 10 years" in f.text and "(fiction)" in f.text


def test_pdf_without_text_is_a_clear_error():
    with pytest.raises(FetchError, match="no extractable text|could not read"):
        pdf_to_text(build_pdf([""]))
    with pytest.raises(FetchError):
        pdf_to_text(b"%PDF-1.4 garbage")


def test_plain_text_and_missing_file(tmp_path):
    assert fetch_file(GIRL_TXT).kind == "text"
    with pytest.raises(FetchError):
        fetch_file(tmp_path / "nope.html", allowed_dirs=[tmp_path])


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


PUBLIC_DNS = lambda host, port: ["93.184.216.34"]          # no real DNS in tests


def test_fetch_url_html_and_errors():
    html = SENIOR.read_bytes()
    ok = lambda req: httpx.Response(200, content=html, headers={"content-type": "text/html; charset=utf-8"})
    f = fetch_url("https://example.org/x", client=_client(ok), resolver=PUBLIC_DNS)
    assert f.kind == "html" and "60 years of age" in f.text
    with pytest.raises(FetchError, match="HTTP 404"):
        fetch_url("https://example.org/x", client=_client(lambda r: httpx.Response(404)), resolver=PUBLIC_DNS)
    big = lambda req: httpx.Response(200, content=b"x" * 5000, headers={"content-type": "text/plain"})
    with pytest.raises(FetchError, match="limit"):
        fetch_url("https://example.org/x", client=_client(big), resolver=PUBLIC_DNS, max_bytes=1000)

    def boom(req):
        raise httpx.ConnectError("blocked")
    with pytest.raises(FetchError, match="network error"):
        fetch_url("https://example.org/x", client=_client(boom), resolver=PUBLIC_DNS)


def test_fetch_url_pdf_by_content_type():
    pdf = build_pdf(["A fictional pension document for tests only.", "Applicant must be 60 years of age or above."])
    h = lambda req: httpx.Response(200, content=pdf, headers={"content-type": "application/pdf"})
    assert "60 years" in fetch_url("https://example.org/a.pdf", client=_client(h), resolver=PUBLIC_DNS).text


def test_spa_page_falls_back_to_next_data():
    data = {"props": {"pageProps": {"scheme": {"eligibility": "<p>Applicant must be 60 years or above</p>",
                                               "benefit": "Rs 500 per month for eligible persons"}}}}
    html = (f'<html><body><div id="__next"></div><script id="__NEXT_DATA__" type="application/json">'
            f'{json.dumps(data)}</script></body></html>')
    t = html_to_text(html)
    assert "Applicant must be 60 years or above" in t and "<p>" not in t


def test_too_little_text_is_an_error(tmp_path):
    p = tmp_path / "e.html"
    p.write_text("<html><body><script>app()</script></body></html>")
    with pytest.raises(FetchError, match="script-rendered"):
        fetch_file(p, allowed_dirs=[tmp_path])


def test_truncation_flag(tmp_path):
    p = tmp_path / "long.txt"
    p.write_text("word " * 500)
    f = fetch_file(p, max_chars=100, allowed_dirs=[tmp_path])
    assert f.truncated and len(f.text) == 100


# ------------------------------------------------------------------ llm json parsing
def test_parse_json_variants():
    assert parse_json_object('```json\n{"a": 1}\n```') == {"a": 1}
    assert parse_json_object('<think>hmm {x}</think>Sure! {"a": {"b": "}"}} done') == {"a": {"b": "}"}}
    for bad in ["no json here", '{"a": 1', "{'a': 1}"]:
        with pytest.raises(LLMOutputError):
            parse_json_object(bad)


# ------------------------------------------------------------------ validation
EXISTING = load_schemes()


def _rec(**kw):
    rec = to_scheme_dict(good_senior())
    rec["source_url"] = "https://example.org/s"
    rec.update(kw)
    return rec


def _errs(rec):
    return V.validate_record(rec, EXISTING).errors


def test_every_existing_scheme_passes_validation():
    for sid, s in EXISTING.items():
        r = V.validate_record(s.model_dump(), EXISTING)
        assert not r.errors, (sid, r.errors)
        assert r.is_update and r.checks_run > 0


def test_good_candidate_is_clean():
    r = V.validate_record(_rec(), EXISTING)
    assert r.errors == [] and not r.is_update and r.checks_run >= 5


def test_unknown_field_and_op_and_types():
    bad = _rec(rules=[{"field": "caste", "op": "eq", "value": "sc", "reason": "caste rule here"}])
    assert any("does not exist on Profile" in e for e in _errs(bad))
    cases = [
        ({"field": "age", "op": "gt", "value": 5}, "unknown op"),
        ({"field": "bpl", "op": "eq", "value": "yes"}, "true/false"),
        ({"field": "age", "op": "gte", "value": "sixty"}, "integer"),
        ({"field": "age", "op": "gte", "value": 60.5}, "integer"),
        ({"field": "age", "op": "lte", "value": 200}, "0..120"),
        ({"field": "gender", "op": "eq", "value": "woman"}, "one of"),
        ({"field": "bpl", "op": "gte", "value": 1}, "numeric field"),
        ({"field": "gender", "op": "in", "value": []}, "non-empty list"),
        ({"field": "gender", "op": "in", "value": ["female", "x"]}, "one of"),
        ({"field": "children", "op": "eq", "value": 1}, "any_child"),
        ({"field": "age", "op": "any_child", "value": []}, "only valid on field 'children'"),
        ({"field": "children", "op": "any_child", "value": [{"field": "bpl", "op": "eq", "value": True}]}, "Child"),
        ({"field": "annual_income", "op": "lte", "value": -5}, "within 0.."),
    ]
    for cond, expect in cases:
        errs = _errs(_rec(rules=[{**cond, "reason": "some reason"}]))
        assert any(expect in e for e in errs), (cond, errs)


def test_missing_reason_is_error():
    assert any("reason" in e for e in _errs(_rec(rules=[{"field": "age", "op": "gte", "value": 60}])))


def test_contradictory_rules():
    r = lambda f, o, v: {"field": f, "op": o, "value": v, "reason": "some reason"}
    assert any("contradictory" in e for e in _errs(_rec(rules=[r("age", "gte", 60), r("age", "lte", 40)])))
    assert any("contradictory" in e for e in _errs(_rec(rules=[r("gender", "eq", "female"), r("gender", "eq", "male")])))
    assert any("contradictory" in e for e in _errs(_rec(rules=[r("gender", "eq", "female"), r("gender", "ne", "female")])))
    assert any("contradictory" in e for e in _errs(_rec(rules=[r("age", "eq", 20), r("age", "gte", 30)])))
    dup = V.validate_record(_rec(rules=[r("age", "gte", 60), r("age", "gte", 60)]), EXISTING)
    assert not dup.errors and any("duplicate" in w for w in dup.warnings)


def test_id_and_source_url_checks():
    assert any("snake_case" in e for e in _errs(_rec(id="Sample-Scheme")))
    assert any("snake_case" in e for e in _errs(_rec(id="1abc")))
    assert any("source_url" in e for e in _errs(_rec(source_url="")))
    assert any("source_url" in e for e in _errs(_rec(source_url="ftp://x")))
    upd = V.validate_record(_rec(id="ignoaps"), EXISTING)
    assert upd.is_update and any("UPDATE" in w for w in upd.warnings)
    dup = V.validate_record(_rec(name=EXISTING["apy"].name), EXISTING)
    assert any("duplicate of existing scheme 'apy'" in w for w in dup.warnings)


def test_children_and_in_rules_validate_and_behave():
    girl = to_scheme_dict(good_girl())
    girl["source_url"] = "https://example.org/g"
    r = V.validate_record(girl, EXISTING)
    assert r.errors == [] and r.checks_run >= 4
    multi = _rec(rules=[
        {"field": "state", "op": "in", "value": ["Kerala", "Goa"], "reason": "Only in Kerala or Goa"},
        {"field": "marital_status", "op": "ne", "value": "single", "reason": "Must not be single"},
        {"field": "age", "op": "gte", "value": 0, "reason": "age floor zero"}])
    assert V.validate_record(multi, EXISTING).errors == []


def test_behavioural_tests_catch_an_engine_disagreement(monkeypatch):
    """If the engine misbehaves at a boundary (here: off-by-one on gte), the sanity tests must notice."""
    from sahayak import rules as R

    real = R._compare
    monkeypatch.setattr(R, "_compare", lambda a, op, e: a > e if op == "gte" else real(a, op, e))
    errs = V.validate_record(_rec(), EXISTING).errors
    assert any("behavioural test" in e and "threshold" in e for e in errs)


def test_candidate_validation_flags_missing_rules_and_value_not_in_evidence():
    c = good_senior()
    c["rules"][0]["evidence"] = "The applicant must be sixty years of age or above."   # words are numbers too
    r = V.validate_candidate(c, EXISTING, source_url="https://example.org/s")
    assert not r.errors
    c["rules"][0]["evidence"] = "The applicant must be an adult of age or above."
    r = V.validate_candidate(c, EXISTING, source_url="https://example.org/s")
    assert any("not present in its own evidence quote" in e for e in r.errors)
    r2 = V.validate_candidate(variant(good_senior(), rules=[], unmapped_criteria=[]), EXISTING,
                              source_url="https://example.org/s")
    assert any("no eligibility criteria" in w for w in r2.warnings)


def test_candidate_schema_errors_and_extra_keys():
    bad = good_senior()
    bad["invented_key"] = 1
    del bad["benefits"]
    errs = V.validate_candidate(bad, EXISTING).errors
    assert any("benefits" in e for e in errs) and any("invented_key" in e for e in errs)


def test_scheme_dict_strips_evidence_and_adds_unmapped_to_caveats():
    rec = to_scheme_dict(ExtractedScheme(**good_senior()))
    assert all(set(r) == {"field", "op", "value", "reason"} for r in rec["rules"])
    assert rec["documents"] == ["Aadhaar card", "Age proof", "BPL card"]
    assert "Must have lived in the state for at least three years" in rec["caveats"]
    Scheme(**{**rec, "source_url": "https://example.org"})


# ------------------------------------------------------------------ batch helpers
def test_read_sources_and_links(tmp_path):
    f = tmp_path / "u.txt"
    f.write_text("# header\nhttps://a.example/x#frag\n\nhttps://a.example/y  # note\nhttps://a.example/x#frag\nlocal.pdf\n")
    assert read_sources(f) == ["https://a.example/x#frag", "https://a.example/y", "local.pdf"]
    html = ('<a href="/schemes/one">1</a><a href="https://other.example/schemes/two">2</a>'
            '<a href="/about">3</a><a href="/schemes/one#top">dup</a>')
    assert links_from_page(html, "https://a.example/list", r"/schemes/") == ["https://a.example/schemes/one"]
    assert len(links_from_page(html, "https://a.example/list", r"/schemes/", same_host=False)) == 2


def test_render_report_groups():
    md = render_report([BatchItem("s1", "t1", "ready_for_review", "A", "a"),
                        BatchItem("s2", "t2", "needs_human_fix", "B", "b", "bad | pipe"),
                        BatchItem("s3", "t3", "failed", detail="HTTP 404")])
    assert "Ready for review (all automatic checks passed): 1" in md
    assert "Needs human fix" in md and "Failed" in md and "bad \\| pipe" in md
