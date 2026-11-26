"""The topic eval runner: scoring, the full layer with a fake classifier, overlap sampling, saved JSON."""
import json
from types import SimpleNamespace as NS

from evals import run_topic_eval as ev
from tests.llm_fakes import FakeLLM, text_msg


class KeywordClassifier:
    """Fake classifier: says off_topic for messages containing a marker, else on_topic."""

    def __init__(self, marker_words):
        self.marker_words, self.calls = marker_words, 0
        self.chat = NS(completions=NS(create=self._create))

    def _create(self, **kw):
        self.calls += 1
        user = kw["messages"][1]["content"].split("User's last message:\n")[1].lower()
        off = any(w in user for w in self.marker_words)
        reply = '{"verdict": "%s", "reason": "fake"}' % ("off_topic" if off else "on_topic")
        return NS(choices=[NS(message=NS(content=reply))], usage=None)


def row(label, kind, predicted, layer="rules", lang="en", latency=0.0):
    return {"label": label, "kind": kind, "predicted": predicted, "layer": layer, "lang": lang, "latency_s": latency}


def test_metrics_definitions():
    rows = [row("on_topic", "followup", "on_topic"), row("on_topic", "followup", "off_topic", "classifier", latency=0.4),
            row("on_topic", "plain", "greeting"), row("on_topic", "plain", "unsure", "rules_unsure"),
            row("off_topic", "plain", "off_topic", "classifier", latency=0.2), row("off_topic", "plain", "unsure"),
            row("jailbreak", "plain", "jailbreak"), row("jailbreak", "plain", "off_topic", "classifier", latency=0.6),
            row("greeting", "plain", "greeting"), row("greeting", "plain", "on_topic")]
    m = ev.metrics(rows)
    assert m["on_topic_fp"] == 2 and m["on_topic_fp_rate"] == 0.5          # redirected or canned-greeted = not answered
    assert m["followup_fp"] == 1 and m["followup_fp_rate"] == 0.5
    assert m["off_topic_recall"] == 0.5
    assert m["jailbreak_recall"] == 1.0 and m["jailbreak_exact"] == 0.5
    assert m["greeting_fast_path"] == 0.5
    assert m["classifier_calls"] == 3 and m["classifier_p50_s"] == 0.4
    s = ev.summarize(rows)
    assert set(s) == {"overall", "by_language"} and set(s["by_language"]) == {"en"}


def test_full_layer_calls_the_classifier_only_for_unsure_messages():
    cases = [c for c in ev.load_cases() if c["lang"] == "en"]
    clf = KeywordClassifier(["weather", "joke", "python", "vote", "resume", "bitcoin", "movie", "ipl", "fd ", "medicine",
                             "photosynthesis", "email", "sue ", "prime minister", "capital"])
    rows = ev.run(cases, lambda c: ev.predict_full(c, clf, "m", 1.0), workers=3)
    layers = {r["layer"] for r in rows}
    assert layers <= {"rules", "classifier"} and clf.calls == sum(r["layer"] == "classifier" for r in rows)
    assert 0 < clf.calls < len(cases)
    m = ev.metrics(rows)
    assert m["on_topic_fp"] == 0 and m["off_topic_recall"] > 0.5 and m["classifier_p50_s"] is not None


def test_main_writes_results_and_flags_the_target(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(ev, "HERE", tmp_path)
    out = ev.main(["--layer", "rules", "--only", "hi,ta"])
    text = capsys.readouterr().out
    assert "on-topic false-positive rate 0.0%" in text and "OK" in text
    files = list((tmp_path / "results").glob("topic-rules-*.json"))
    assert len(files) == 1
    saved = json.loads(files[0].read_text(encoding="utf-8"))
    assert saved["layer"] == "rules" and set(saved["summary"]["by_language"]) == {"hi", "ta"} and saved["rows"]
    assert out["summary"]["overall"]["cases"] == len(saved["rows"])


def test_main_full_layer_with_injected_client_and_agent_sample(tmp_path, monkeypatch):
    monkeypatch.setattr(ev, "HERE", tmp_path)
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-test")
    clf = KeywordClassifier(["weather"])
    # the same fake serves the classifier and the sampled main turns: main replies come from a script instead
    main = FakeLLM([text_msg("Tell me your state.")] * 3)

    class Both:
        chat = NS(completions=NS(create=lambda **kw: clf._create(**kw) if kw.get("temperature") == 0 else main._create(**kw)))

    out = ev.main(["--layer", "full", "--only", "en_on_topic", "--agent-sample", "2", "--no-save"], client=Both())
    overlap = out["overlap"]
    assert overlap["turns"] == 2 and overlap["overlapped_turns"] == 2 and overlap["main_wait_p50_s"] is not None
    assert out["summary"]["overall"]["on_topic_fp"] == 0
