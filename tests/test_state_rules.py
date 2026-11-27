"""State-gated schemes: normalisation, the rule engine, research validation and prompts."""
import pytest

from research import validate as V
from research.fields import describe_fields
from research.prompts import SYSTEM_PROMPT
from research.schema import ExtractedScheme
from sahayak.models import Profile, Scheme
from sahayak.rules import check_scheme
from sahayak.states import STATES, normalise_state
from tests.test_research_support import good_senior, variant


def _scheme(**kw) -> Scheme:
    base = dict(id="kerala_x", name="Kerala X", ministry="Govt of Kerala", category="other", summary="s",
                benefits="b", source_url="https://example.org/x",
                rules=[{"field": "state", "op": "eq", "value": "Kerala", "reason": "Only for Kerala residents"}])
    base.update(kw)
    return Scheme(**base)


@pytest.mark.parametrize("raw,want", [
    ("UP", "Uttar Pradesh"), ("u.p.", "Uttar Pradesh"), ("  kerala ", "Kerala"), ("Tamilnadu", "Tamil Nadu"),
    ("Orissa", "Odisha"), ("J&K", "Jammu and Kashmir"), ("Dadra & Nagar Haveli and Daman & Diu",
                                                         "Dadra and Nagar Haveli and Daman and Diu"),
    ("NCT of Delhi", "Delhi"), ("Bombay", None), ("", None), (None, None), (5, None)])
def test_normalise_state(raw, want):
    assert normalise_state(raw) == want


def test_every_canonical_name_normalises_to_itself():
    assert all(normalise_state(s) == s for s in STATES) and len(set(STATES)) == len(STATES) == 36


def test_profile_canonicalises_state_and_keeps_unknown_text():
    assert Profile(state="up").state == "Uttar Pradesh"
    assert Profile(state="Atlantis").state == "Atlantis"
    assert Profile(state="   ").state is None


def test_engine_gates_by_state_with_three_verdicts():
    s = _scheme()
    assert check_scheme(Profile(state="Kerala"), s).verdict == "eligible"
    assert check_scheme(Profile(state="kerela"), s).verdict == "eligible"          # typo alias
    no = check_scheme(Profile(state="Uttar Pradesh"), s)
    assert no.verdict == "not_eligible" and "Kerala" in no.failed_reasons[0]
    unknown = check_scheme(Profile(), s)
    assert unknown.verdict == "need_info" and unknown.missing_fields == ["state"]
    assert check_scheme(Profile(state="Atlantis"), s).verdict == "need_info"      # unrecognised = unknown, never a match


def test_engine_state_in_list_and_other_failures_win():
    s = _scheme(rules=[{"field": "state", "op": "in", "value": ["Kerala", "Goa"], "reason": "Kerala or Goa only"},
                       {"field": "age", "op": "gte", "value": 60, "reason": "60 or older"}])
    assert check_scheme(Profile(state="GOA", age=61), s).verdict == "eligible"
    assert check_scheme(Profile(state="Bihar"), s).verdict == "not_eligible"       # known mismatch beats missing age
    assert check_scheme(Profile(state="Goa"), s).verdict == "need_info"


def _state_candidate(**changes) -> dict:
    rules = good_senior()["rules"] + [
        {"field": "state", "op": "eq", "value": "Kerala", "reason": "Only for residents of Kerala",
         "evidence": "Department of Example Social Welfare, Government of Kerala"}]
    return variant(good_senior(), **{"level": "state", "level_evidence": "Government of Kerala", "rules": rules, **changes})


def _errs(c, text_ok=True):
    return V.validate_candidate(c, {}, source_url="https://example.org/s").errors


def test_state_scheme_with_state_rule_validates():
    assert _errs(_state_candidate()) == []


def test_state_scheme_without_state_rule_is_blocked():
    c = variant(good_senior(), level="state", level_evidence="Government of Kerala")
    assert any("no rule on field 'state'" in e for e in _errs(c))


def test_state_scheme_needs_level_evidence_and_central_must_not_have_state_rule():
    assert any("level_evidence is empty" in e for e in _errs(_state_candidate(level_evidence="")))
    c = _state_candidate(level="central")
    assert any("level is 'central' but a state rule exists" in e for e in _errs(c))


def test_missing_level_is_blocked():
    c = good_senior()
    c.pop("level")
    c.pop("level_evidence")
    assert any("level is missing" in e for e in _errs(c))


def test_state_values_must_be_canonical_and_named_in_quote():
    bad = _state_candidate()
    bad["rules"][-1]["value"] = "UP"
    assert any("Uttar Pradesh" in e and "canonical" in e for e in _errs(bad))
    bad["rules"][-1]["value"] = "Atlantis"
    assert any("not a recognised" in e for e in _errs(bad))
    other = _state_candidate()
    other["rules"][-1]["value"] = "Goa"            # quote still names Kerala only
    assert any("not named in its own evidence quote" in e for e in _errs(other))


def test_state_ne_and_non_string_values_rejected():
    c = _state_candidate()
    c["rules"][-1]["op"] = "ne"
    assert any("state only supports eq or in" in e for e in _errs(c))
    c["rules"][-1].update(op="in", value=[])
    assert any("non-empty list" in e for e in _errs(c))


def test_database_record_with_state_in_list_passes_behavioural_checks():
    rec = {"id": "multi_state", "name": "Multi", "ministry": "m", "category": "other", "summary": "s",
           "benefits": "b", "source_url": "https://example.org/m",
           "rules": [{"field": "state", "op": "in", "value": ["Kerala", "Goa"], "reason": "Kerala or Goa only"}]}
    r = V.validate_record(rec, {})
    assert r.errors == [] and r.checks_run >= 3


def test_extractor_prompt_teaches_levels_and_state_names():
    assert "Uttar Pradesh" in describe_fields() and "level_evidence" in SYSTEM_PROMPT
    ExtractedScheme(**_state_candidate())        # the schema accepts the new fields
