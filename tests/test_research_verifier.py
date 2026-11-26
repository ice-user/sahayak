"""The independent auditor agent: scripted fakes for both the extractor and the auditor."""
import json

import pytest

from research import runner
from research.llm import LLM
from research.verifier import AuditReport, candidate_view, run_audit, verifier_llm_from_env
from tests.test_research_support import (NO_ISSUES, YOUTH, FakeClient, good_senior, good_youth, make_graph,
                                         start_file, variant)

YOUTH_URL = "https://example.org/youth"
AGE_QUOTE = "between 18 and 35 years of age"


def youth_without_upper_bound():
    c = good_youth()
    c["rules"] = [r for r in c["rules"] if not (r["field"] == "age" and r["op"] == "lte")]
    return c


def issue(**kw):
    return {"rule_index": None, "field": None, "severity": "blocking", "problem": "problem found here",
            "supporting_quote": AGE_QUOTE, **kw}


MISSING_UPPER = {"issues": [], "missing_criteria": [
    {"criterion": "Applicant must be at most 35 years old (upper age limit)", "supporting_quote": AGE_QUOTE,
     "severity": "blocking"}]}


def run_youth(graph, **kw):
    return start_file(graph, YOUTH, source_url=YOUTH_URL, thread_id=kw.pop("thread", "v1"))


def auditor_client(deps):
    return deps.verifier_llm.client


def test_auditor_catches_missing_upper_bound_and_extractor_fixes_it(tmp_path):
    graph, deps, ext = make_graph(tmp_path, [youth_without_upper_bound(), good_youth()],
                                  auditor=[MISSING_UPPER, NO_ISSUES])
    out = run_youth(graph)
    assert out.status == "ready_for_review" and out.paused
    assert len(ext.sent) == 2 and len(auditor_client(deps).sent) == 2           # extract, audit, extract, audit
    feedback = ext.sent[1]["messages"][-1]["content"]
    assert "auditor:" in feedback and "upper age limit" in feedback and AGE_QUOTE in feedback
    assert "independent auditor" in feedback
    assert ext.sent[1]["messages"][-2]["role"] == "assistant"                    # the earlier attempt is replayed
    rules = {(r["field"], r["op"], r["value"]) for r in out.payload["scheme_record"]["rules"]}
    assert ("age", "lte", 35) in rules and ("age", "gte", 18) in rules
    assert len(out.state["attempts"]) == 2                                       # the audit retry counted
    assert any(e.startswith("auditor:") for e in out.state["attempts"][0]["errors"])
    assert out.payload["audit"]["status"] == "ok" and out.payload["errors"] == []


def test_auditor_hallucinated_quote_is_dropped(tmp_path):
    fake = {"issues": [issue(rule_index=0, problem="age limit is actually 21",
                             supporting_quote="applicants must be at most 21 years old per the annexure")],
            "missing_criteria": [{"criterion": "must own a motorcycle", "supporting_quote": "must own a motorcycle",
                                  "severity": "blocking"}]}
    graph, deps, ext = make_graph(tmp_path, [good_youth()], auditor=[fake])
    out = run_youth(graph)
    assert out.status == "ready_for_review" and len(ext.sent) == 1                # no retry caused by lies
    assert out.payload["errors"] == [] and out.payload["auditor_notes"] == []
    assert len(out.payload["audit"]["dropped"]) == 2
    assert any("dropped" in w for w in out.payload["warnings"])


def test_auditor_quote_with_a_changed_number_is_dropped(tmp_path):
    fake = {"issues": [issue(rule_index=2, problem="the income cap is different",
                             supporting_quote="annual family income is not more than Rs 5,00,000")],
            "missing_criteria": []}
    graph, deps, ext = make_graph(tmp_path, [good_youth()], auditor=[fake])
    out = run_youth(graph)
    assert out.status == "ready_for_review" and len(ext.sent) == 1 and len(out.payload["audit"]["dropped"]) == 1


def test_auditor_all_good_proceeds_to_review(tmp_path):
    graph, deps, ext = make_graph(tmp_path, [good_youth()], auditor=[NO_ISSUES])
    out = run_youth(graph)
    assert out.status == "ready_for_review" and len(ext.sent) == 1 and len(auditor_client(deps).sent) == 1
    assert out.payload["audit"] == {"status": "ok", "model": "fake-auditor", "dropped": [], "blocking": 0,
                                    "warnings": 0, "detail": ""}
    assert "Auditor (fake-auditor): 0 blocking" in out.summary


def test_auditor_warnings_are_shown_as_auditor_notes_and_do_not_block(tmp_path):
    warn = {"issues": [issue(severity="warning", rule_index=2, problem="income might be household income",
                             supporting_quote="annual family income is not more than Rs 3,00,000")],
            "missing_criteria": []}
    graph, deps, ext = make_graph(tmp_path, [good_youth()], auditor=[warn])
    out = run_youth(graph)
    assert out.status == "ready_for_review" and len(ext.sent) == 1 and out.payload["errors"] == []
    assert len(out.payload["auditor_notes"]) == 1 and "household income" in out.payload["auditor_notes"][0]
    assert "Auditor notes" in out.summary and "household income" in out.summary
    assert "approve" in out.payload["allowed_actions"]
    runner.resume(graph, "v1", {"action": "approve", "reviewer": "t"})
    prov = json.loads((deps.candidates_dir / "sample_youth_apprentice.json").read_text())["provenance"]
    assert prov["audit"]["status"] == "ok" and "household income" in prov["audit"]["notes"][0]


def test_persistent_auditor_objection_counts_toward_the_three_attempt_cap(tmp_path):
    graph, deps, ext = make_graph(tmp_path, [youth_without_upper_bound()], auditor=[MISSING_UPPER])
    out = run_youth(graph)
    assert len(ext.sent) == 3 and len(auditor_client(deps).sent) == 3
    assert out.status == "needs_human_fix" and out.payload["allowed_actions"] == ["reject", "edit"]
    assert any(e.startswith("auditor:") for e in out.payload["errors"])
    # a human edit supplies the bound; deterministic checks pass and the auditor is not re-run
    out = runner.resume(graph, "v1", {"action": "edit", "record": good_youth(), "reviewer": "t"})
    assert out.status == "ready_for_review" and len(auditor_client(deps).sent) == 3 and len(ext.sent) == 3
    assert any("auditor was not re-run" in w for w in out.payload["warnings"])


def test_auditor_only_runs_after_deterministic_validation_passes(tmp_path):
    bad = variant(good_youth(), name_evidence="A heading that is not in the page at all")
    graph, deps, ext = make_graph(tmp_path, [bad, good_youth()], auditor=[NO_ISSUES])
    out = run_youth(graph)
    assert out.status == "ready_for_review" and len(ext.sent) == 2
    assert len(auditor_client(deps).sent) == 1                                   # only for the valid candidate


def test_auditor_is_isolated_and_adversarial(tmp_path):
    graph, deps, ext = make_graph(tmp_path, [youth_without_upper_bound(), good_youth()],
                                  auditor=[MISSING_UPPER, NO_ISSUES])
    run_youth(graph)
    aud = auditor_client(deps).sent
    sys_prompt, user = aud[1]["messages"][0]["content"], aud[1]["messages"][1]["content"]
    assert "AUDITOR" in sys_prompt and "find EVERY" in sys_prompt and "upper" in sys_prompt
    assert aud[1]["model"] == "fake-auditor" and ext.sent[0]["model"] == "fake-model"
    assert len(aud[1]["messages"]) == 2                                          # no extractor history at all
    for sent in aud:
        text = json.dumps(sent["messages"])
        assert "rejected by automatic checks" not in text and "auditor:" not in text   # no feedback leakage
        assert "evidence" not in sent["messages"][1]["content"].split("<candidate>")[1]  # quotes not shown
    # the candidate shown is what would ship: indexed rules
    assert '"index": 0' in user and "<document>" in user and "between 18 and 35 years of age" in user


def test_auditor_failure_is_visible_not_silent(tmp_path):
    for script in ([TimeoutError("api down")], ["not json at all"], [{"issues": []}], [good_youth()]):
        sub = tmp_path / str(abs(hash(str(script))))
        sub.mkdir()
        graph, deps, ext = make_graph(sub, [good_youth()], auditor=script)
        out = run_youth(graph)
        assert out.status == "ready_for_review" and len(ext.sent) == 1
        assert out.payload["audit"]["status"] == "unavailable"
        assert any("AUDITOR DID NOT RUN" in w for w in out.payload["warnings"])
        assert "DID NOT RUN" in out.summary


def test_wrong_shape_answer_is_never_read_as_all_clear():
    with pytest.raises(Exception):
        AuditReport(**{"id": "x"})
    with pytest.raises(Exception):
        AuditReport(**{"issues": []})
    assert AuditReport(**NO_ISSUES)


def test_auditor_gets_one_reformat_chance():
    client = FakeClient(["Sure! here you go", NO_ISSUES])
    res = run_audit(LLM(client=client, model="m"), "Applicant must be 60 years of age or above.",
                    {"rules": [], "caveats": []})
    assert res["status"] == "ok" and len(client.sent) == 2
    assert "JSON" in client.sent[1]["messages"][-1]["content"]


def test_rule_index_out_of_range_is_dropped():
    client = FakeClient([{"issues": [issue(rule_index=7, supporting_quote="between 18 and 35 years of age")],
                          "missing_criteria": []}])
    res = run_audit(LLM(client=client, model="m"), "Applicants between 18 and 35 years of age may apply.",
                    {"rules": [{"field": "age", "op": "gte", "value": 18, "reason": "r"}]})
    assert res["blocking"] == [] and len(res["dropped"]) == 1


def test_candidate_view_hides_evidence_and_ids():
    view = candidate_view({"id": "x", "source_url": "u", "name": "N", "rules": [
        {"field": "age", "op": "gte", "value": 40, "reason": "r", "evidence": "SECRET"}]}, [{"criterion": "c"}])
    assert "SECRET" not in json.dumps(view) and "source_url" not in view and view["rules"][0]["index"] == 0


def test_separate_model_from_env(monkeypatch):
    monkeypatch.delenv("RESEARCH_VERIFIER_MODEL", raising=False)
    assert verifier_llm_from_env() is None                       # default: the extractor's model is used
    monkeypatch.setenv("RESEARCH_VERIFIER_MODEL", "other/model-70b")
    v = verifier_llm_from_env()
    assert v is not None and v.model == "other/model-70b"


def test_default_auditor_is_the_extractor_llm_when_none_configured(tmp_path):
    from research.graph import build_graph
    graph, deps, ext = make_graph(tmp_path, [good_youth()])
    deps.verifier_llm = None
    g = build_graph(deps)
    out = start_file(g, YOUTH, source_url=YOUTH_URL, thread_id="d1")
    # the extractor's own client answered the audit call (with a non-audit reply => visible "did not run")
    assert len(ext.sent) >= 2 and out.payload["audit"]["model"] == "fake-model"


def test_cli_wires_verifier_model_from_env(tmp_path, monkeypatch):
    from research import cli
    monkeypatch.setenv("RESEARCH_VERIFIER_MODEL", "judge-model")
    args = cli.build_parser().parse_args(["--state-db", str(tmp_path / "s.sqlite"), "--candidates-dir",
                                          str(tmp_path / "c"), "run", "--file", str(YOUTH)])
    _, deps = cli._graph(args)
    assert deps.verifier_llm.model == "judge-model"


def test_graph_diagram_includes_verify_semantics_and_doc_is_current():
    from pathlib import Path
    from research.graph import build_graph
    from research.nodes import Deps
    mermaid = build_graph(Deps()).get_graph().draw_mermaid()
    assert "verify_semantics" in mermaid
    doc = (Path(__file__).resolve().parent.parent / "research" / "GRAPH.md").read_text(encoding="utf-8")
    block = doc.split("```mermaid\n", 1)[1].split("```", 1)[0].strip()
    assert block == mermaid.strip(), "regenerate GRAPH.md from build_graph().get_graph().draw_mermaid()"
