"""Metric functions of scripts/eval_extractors.py and prompt consistency of scripts/finetune_qwen.py."""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ev = _load("eval_extractors")
ft = _load("finetune_qwen")


def R(field, op, value, quote="q"):
    return {"field": field, "op": op, "value": value, "quote": quote}


AGE = R("age", "gte", 18)
INC = R("annual_income", "lte", 249999)


def test_rule_key_normalises_values():
    assert ev.rule_key(R("state", "in", ["Bihar", "Assam"])) == ev.rule_key(R("state", "in", ["assam", "Bihar"]))
    assert ev.rule_key(R("age", "gte", 18.0)) == ev.rule_key(R("age", "gte", 18))
    assert ev.rule_key(R("bpl", "eq", True)) != ev.rule_key(R("bpl", "eq", 1))
    assert ev.rule_key(R("age", "gte", 18, "a")) == ev.rule_key(R("age", "gte", 18, "b"))   # quote ignored


def test_perfect_prediction():
    g = {"rules": [AGE, INC], "unmapped": []}
    s = ev.score_bullet(g, g)
    assert (s["tp"], s["n_gold"], s["n_pred"], s["exact"], s["safety_errors"], s["hallucinated"]) == (2, 2, 2, True, 0, 0)


def test_safety_error_vs_hallucination():
    g = {"rules": [AGE], "unmapped": []}
    wrong_bound = {"rules": [R("age", "gte", 21)], "unmapped": []}
    s = ev.score_bullet(g, wrong_bound)
    assert s["safety_errors"] == 1 and s["hallucinated"] == 0 and s["tp"] == 0 and not s["exact"]
    extra = {"rules": [AGE, R("gender", "eq", "female")], "unmapped": []}
    s = ev.score_bullet(g, extra)
    assert s["hallucinated"] == 1 and s["safety_errors"] == 0 and s["tp"] == 1 and not s["exact"]


def test_both_empty_is_exact_and_missing_pred_is_not():
    assert ev.score_bullet({"rules": [], "unmapped": []}, {"rules": [], "unmapped": []})["exact"]
    assert not ev.score_bullet({"rules": [], "unmapped": []}, None)["exact"]
    assert ev.score_bullet({"rules": [AGE], "unmapped": []}, None)["tp"] == 0


def test_quotes_overlap():
    assert ev.quotes_overlap("belong to the Scheduled Tribe community", "Scheduled Tribe community")
    assert ev.quotes_overlap("should be a farmer", "a farmer")
    assert not ev.quotes_overlap("should be a farmer", "annual income below Rs 2 lakh")
    assert not ev.quotes_overlap("", "x")


def test_unmapped_recall_counts_rule_quotes_too():
    g = {"rules": [], "unmapped": [{"quote": "belong to the Scheduled Tribe community", "reason": "x"},
                                   {"quote": "owns a two wheeler", "reason": "x"}]}
    p = {"rules": [R("age", "gte", 1, "Scheduled Tribe community")], "unmapped": []}
    s = ev.score_bullet(g, p)
    assert (s["um_gold"], s["um_hit"]) == (2, 1)


def test_percentile():
    assert ev.percentile([], 0.5) == 0.0
    assert ev.percentile([1, 2, 3, 4, 5], 0.5) == 3
    assert ev.percentile([1, 2, 3, 4, 5], 0.9) == 4.6


def _rec(gold, pred, valid=True, ok=True, lat=1.0, tokens=10):
    return {"gold": gold, "pred": pred, "valid_json": valid, "check_ok": ok, "latency_s": lat, "tokens": tokens}


def test_summarise():
    g1 = {"rules": [AGE, INC], "unmapped": []}
    g2 = {"rules": [], "unmapped": [{"quote": "a farmer", "reason": "x"}]}
    recs = [_rec(g1, {"rules": [AGE], "unmapped": []}, lat=1.0),
            _rec(g2, None, valid=False, ok=False, lat=3.0, tokens=20)]
    s = ev.summarise(recs)
    assert s["n"] == 2 and s["valid_json_rate"] == 50.0 and s["bullet_check_pass_rate"] == 50.0
    assert s["rule_precision"] == 100.0 and s["rule_recall"] == 50.0 and s["rule_f1"] == 66.7
    assert s["exact_match"] == 0.0 and s["unmapped_recall"] == 0.0
    assert s["latency_p50_s"] == 2.0 and s["tokens_per_bullet"] == 15.0 and s["total_tokens"] == 30


def test_summarise_no_gold_rules():
    s = ev.summarise([_rec({"rules": [], "unmapped": []}, {"rules": [], "unmapped": []})])
    assert s["rule_recall"] == 100.0 and s["rule_precision"] == 100.0 and s["exact_match"] == 100.0
    assert s["unmapped_recall"] is None


def test_short_prompt_covers_every_field_and_state():
    from research.fields import PROFILE_FIELDS
    from sahayak.states import STATES
    for name in PROFILE_FIELDS:
        assert name in ft.INSTRUCTION, name
    for st in STATES:
        assert st in ft.INSTRUCTION, st


def test_build_messages_and_target_text():
    m = ft.build_messages("Applicants must be above 60.")
    assert m[0]["role"] == "system" and m[1]["content"] == "Bullet: Applicants must be above 60."
    t = {"rules": [], "unmapped": []}
    assert ft.target_text(t) == '{"rules":[],"unmapped":[]}'


def test_stratified_subsample_keeps_rare_fields():
    rows = ([{"bullet": f"a{i}", "target": {"rules": [R("age", "gte", 1)], "unmapped": []}} for i in range(50)]
            + [{"bullet": "b", "target": {"rules": [R("bpl", "eq", True)], "unmapped": []}},
               {"bullet": "c", "target": {"rules": [], "unmapped": []}}])
    sub = ft.stratified_subsample(rows, 6)
    assert len(sub) == 6
    assert {"b", "c"} <= {r["bullet"] for r in sub}



def test_ollama_lora_posts_training_messages_and_parses_reply():
    seen = {}

    class FakeResp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"message": {"content": '{"rules":[],"unmapped":[]}'}, "prompt_eval_count": 7, "eval_count": 5}

    def fake_post(url, json=None, timeout=None):
        seen.update(url=url, body=json)
        return FakeResp()

    fn = ev.OllamaLora("sahayak-extractor-0.6b-q8", use_format=True, post=fake_post)
    text, toks = fn("Applicant must be above 18 years.")
    assert text == '{"rules":[],"unmapped":[]}' and toks == 12
    body = seen["body"]
    assert seen["url"].endswith("/api/chat") and body["model"] == "sahayak-extractor-0.6b-q8"
    assert body["messages"] == ft.build_messages("Applicant must be above 18 years.")
    assert body["stream"] is False and body["think"] is False and body["options"]["temperature"] == 0
    assert body["format"]["required"] == ["rules", "unmapped"] and body["keep_alive"]
    fn2 = ev.OllamaLora("m", post=fake_post)
    fn2("x")
    assert "format" not in seen["body"]
