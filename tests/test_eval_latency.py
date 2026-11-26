"""Eval runner metrics (latency, TTFT, LLM calls, tokens), error-vs-fail separation, retry, and the latency benchmark."""
import json

import pytest

from evals import bench_latency
from evals.run_agent_evals import load_cases, passed, percentile, run_case, summarize
from sahayak.agent import Agent
from sahayak.tools import Toolbox
from tests.llm_fakes import FakeLLM, StatusError, text_msg, text_stream, tool_msg, tool_stream

TB = Toolbox(search_mode="bm25")
CASE = {"id": "en_widow_mother", "lang": "en", "query": "My mother is 62, a widow, BPL card holder",
        "expect_eligible": ["ignwps", "ignoaps"], "expect_tool": "check_eligibility"}
WIDOW = {"profile": {"age": 62, "gender": "female", "marital_status": "widowed", "bpl": True}}
GOOD = "IGNWPS: widow pension. IGNOAPS: old age pension. Do you have a bank account?"


def factory(script, **kw):
    client = FakeLLM(script)
    kw.setdefault("retry_delays", (0, 0))
    return client, (lambda: Agent(client=client, model="fake", toolbox=TB, answer_style="brief", **kw))


def test_percentile():
    assert percentile([], 50) is None and percentile([4.0], 90) == 4.0
    assert percentile([1, 2, 3, 4, 5], 50) == 3 and percentile([1, 2, 3, 4, 5], 90) == 4.6
    assert percentile([5, 1, 3], 0) == 1 and percentile([5, 1, 3], 100) == 5


def test_row_records_latency_ttft_calls_tokens_when_streaming():
    client, make = factory([tool_stream("check_eligibility", WIDOW, usage=50), text_stream(GOOD, usage=70)], stream=True)
    row = run_case(CASE, make)
    assert row["llm_calls"] == 2 and row["tokens"] == 120 and row["tools"] == ["check_eligibility"]
    assert row["ttft_s"] is not None and 0 <= row["ttft_s"] <= row["latency_s"] + 0.01
    assert row["used_tool"] is True and row["recall"] == 1.0 and row["attempts"] == 1 and "error" not in row
    assert passed(row) is True


def test_ttft_is_empty_without_streaming():
    client, make = factory([tool_msg("check_eligibility", WIDOW), text_msg(GOOD)], stream=False)
    row = run_case(CASE, make)
    assert row["ttft_s"] is None and row["llm_calls"] == 2 and row["tokens"] == 200


def test_transient_error_is_retried_once_and_not_an_error_row():
    calls = []
    client = FakeLLM([StatusError(503, "temporarily unavailable")] * 3 + [tool_msg("check_eligibility", WIDOW),
                                                                          text_msg(GOOD)])
    make = lambda: Agent(client=client, model="fake", toolbox=TB, stream=False, retry_delays=(0, 0))  # noqa: E731
    row = run_case(CASE, make, sleep=calls.append)          # attempt 1 exhausts the agent's 3 tries, attempt 2 succeeds
    assert row["attempts"] == 2 and "error" not in row and calls == [2.0] and passed(row) is True


def test_persistent_error_is_an_error_row_not_a_quality_failure():
    _, make = factory([StatusError(503, "temporarily unavailable")] * 6)
    row = run_case(CASE, make, sleep=lambda s: None)
    assert row["error"].startswith("StatusError") and row["attempts"] == 2
    assert passed(row) is None and not any(k in row for k in ("used_tool", "recall", "llm_calls"))


def test_non_transient_error_is_not_retried():
    client, make = factory([StatusError(401, "bad key"), text_msg("unused")])
    row = run_case(CASE, make, sleep=lambda s: None)
    assert row["attempts"] == 1 and "401" not in row["answer"] and row["error"] and len(client.sent) == 1


def test_quality_failure_is_a_fail_not_an_error():
    _, make = factory([text_msg("Sorry, I cannot help with that.")], stream=False)
    row = run_case(CASE, make)
    assert "error" not in row and row["used_tool"] is False and passed(row) is False


def test_summary_excludes_errors_from_quality_and_latency():
    good = {"id": "a", "lang": "en", "latency_s": 10.0, "ttft_s": 2.0, "llm_calls": 2, "tokens": 1000, "used_tool": True,
            "recall": 1.0, "answer": "x"}
    bad = {**good, "id": "b", "latency_s": 30.0, "ttft_s": None, "llm_calls": 4, "tokens": 3000, "recall": 0.5}
    err = {"id": "c", "lang": "ta", "latency_s": 99.0, "error": "StatusError: 503", "answer": ""}
    s = summarize([good, bad, err])
    assert s["runs"] == 3 and s["errors"] == 1
    assert s["pass_rate"] == 0.5 and s["recall"] == 0.75 and s["used_tool"] == 1.0
    assert s["latency_p50"] == 20.0 and s["latency_mean"] == 20.0 and s["ttft_p50"] == 2.0
    assert s["llm_calls_mean"] == 3.0 and s["tokens_mean"] == 2000.0
    assert summarize([err])["pass_rate"] is None and summarize([])["runs"] == 0


def test_load_cases_filters_by_comma_separated_fragments():
    assert len(load_cases("")) == 10
    assert [c["id"] for c in load_cases("hinglish,ta_")] == ["ta_widow_mother", "hinglish_grandfather_health"]
    assert len(load_cases("zzz")) == 0


# ---- bench_latency
def fake_factory_for(clients):
    def make_for(model):
        return lambda: Agent(client=clients[model], model=model, toolbox=TB, stream=True, retry_delays=(0, 0),
                             answer_style="brief")
    return make_for


def test_bench_prints_table_and_saves_json(tmp_path, capsys):
    fast = FakeLLM([tool_stream("check_eligibility", WIDOW, usage=100), text_stream(GOOD, usage=100)] * 2)
    slow = FakeLLM([tool_msg("search_schemes", {"query": "widow"}), tool_msg("check_eligibility", WIDOW, "c2"),
                    tool_msg("get_scheme_details", {"scheme_id": "ignwps"}, "c3"), text_msg(GOOD)] * 2)
    broken = FakeLLM([StatusError(404, "model not found")] * 2)
    out = tmp_path / "res" / "bench.json"
    report = bench_latency.main(["--models", "fast-8b,slow-120b,typo-model", "--only", "en_widow", "--repeat", "2",
                                 "--out", str(out)],
                                make_agent_for=fake_factory_for({"fast-8b": fast, "slow-120b": slow, "typo-model": broken}))
    text = capsys.readouterr().out
    for model in ("fast-8b", "slow-120b", "typo-model"):
        assert model in text
    for header in ("p50 s", "p90 s", "ttft50", "calls", "tokens", "pass"):
        assert header in text
    assert report["fast-8b"]["summary"]["llm_calls_mean"] == 2.0 and report["slow-120b"]["summary"]["llm_calls_mean"] == 4.0
    assert report["fast-8b"]["summary"]["ttft_p50"] is not None and report["slow-120b"]["summary"]["ttft_p50"] is None
    assert report["typo-model"]["summary"]["errors"] == 2 and report["typo-model"]["summary"]["pass_rate"] is None
    assert "errors (provider/network failures" in text and "404" in text
    saved = json.loads(out.read_text(encoding="utf-8"))
    assert saved["meta"]["models"] == ["fast-8b", "slow-120b", "typo-model"] and saved["meta"]["repeat"] == 2
    assert len(saved["models"]["fast-8b"]["rows"]) == 2 and saved["models"]["fast-8b"]["rows"][1]["repeat"] == 2


def test_bench_rejects_empty_selection(capsys):
    with pytest.raises(SystemExit):
        bench_latency.main(["--models", "m", "--only", "no_such_case"], make_agent_for=lambda m: None)


def test_default_results_dir_is_gitignored_location():
    assert str(bench_latency.HERE).endswith("evals")
