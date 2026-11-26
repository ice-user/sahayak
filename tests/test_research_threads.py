"""Regression: a transient failure must not poison the deterministic thread id."""
from research import runner
from research.fetch import FetchError, fetch_file
from research.graph import build_graph, sqlite_checkpointer
from tests.test_research_support import SENIOR, SENIOR_URL, good_senior, make_deps


def _flaky(tmp_path, script, fail_first=True):
    deps, client = make_deps(tmp_path, script)
    calls = {"n": 0}

    def fetcher(src):
        calls["n"] += 1
        if fail_first and calls["n"] == 1:
            raise FetchError("HTTP 503 (transient)")
        return fetch_file(SENIOR, allowed_dirs=[SENIOR.parent])

    deps.fetcher = fetcher
    return deps, client


def test_transient_fetch_failure_does_not_poison_the_thread(tmp_path):
    deps, client = _flaky(tmp_path, [good_senior()])
    graph = build_graph(deps, sqlite_checkpointer(str(tmp_path / "ck.sqlite")))
    first = runner.start(graph, "https://example.org/s", source_url=None, thread_id="same")
    assert first.status == "fetch_failed" and not client.sent
    second = runner.start(graph, "https://example.org/s", thread_id="same")
    assert second.status == "ready_for_review" and second.paused and len(client.sent) == 1
    assert second.state.get("fatal") in (None, "")
    assert second.report == {} or second.report.get("outcome") != "failed"


def test_transient_llm_failure_does_not_poison_the_thread(tmp_path):
    deps, client = make_deps(tmp_path, [TimeoutError("api down"), good_senior()])
    deps.fetcher = lambda src: fetch_file(SENIOR, allowed_dirs=[SENIOR.parent])
    graph = build_graph(deps, sqlite_checkpointer(str(tmp_path / "ck.sqlite")))
    assert runner.start(graph, "https://example.org/s", thread_id="same").status == "llm_failed"
    again = runner.start(graph, "https://example.org/s", thread_id="same")
    assert again.status == "ready_for_review" and len(client.sent) == 2


def test_rerun_after_terminal_state_starts_clean(tmp_path):
    deps, client = _flaky(tmp_path, [good_senior()], fail_first=False)
    graph = build_graph(deps)
    runner.start(graph, "https://example.org/s", source_url=SENIOR_URL, thread_id="same")
    done = runner.resume(graph, "same", {"action": "reject", "reviewer": "t"})
    assert done.status == "rejected"
    redo = runner.start(graph, "https://example.org/s", source_url=SENIOR_URL, thread_id="same")
    assert redo.paused and redo.status == "ready_for_review" and redo.state.get("decision") in (None, {})
    assert redo.report == {} and redo.state["attempts"][0]["n"] == 1 and len(redo.state["attempts"]) == 1
