"""Thinking-off defaults for Nemotron, classifier extras, and remembering models that reject streaming."""
import json
from types import SimpleNamespace as NS

import pytest

from sahayak import llm
from sahayak.agent import Agent
from sahayak.llm_options import THINKING_OFF, model_extra_body
from sahayak.topic_guard import classify


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for k in ("LLM_EXTRA_BODY", "LLM_THINKING"):
        monkeypatch.delenv(k, raising=False)


def test_nemotron_gets_thinking_off_by_default():
    assert model_extra_body("nvidia/nemotron-3.5-super-vl-120b-a12b") == THINKING_OFF
    assert model_extra_body("nvidia/Nemotron-3-Nano-30B-A3B") == THINKING_OFF


def test_other_models_get_nothing():
    assert model_extra_body("meta/llama-3.3-70b-instruct") is None
    assert model_extra_body(None) is None


def test_llm_thinking_opt_in_keeps_reasoning(monkeypatch):
    monkeypatch.setenv("LLM_THINKING", "1")
    assert model_extra_body("nvidia/nemotron-3-super-120b-a12b") is None


def test_explicit_extra_body_wins(monkeypatch):
    monkeypatch.setenv("LLM_EXTRA_BODY", json.dumps({"reasoning_budget": 128}))
    assert model_extra_body("nvidia/nemotron-3-super-120b-a12b") == {"reasoning_budget": 128}


def test_returned_dict_is_a_copy():
    a = model_extra_body("nvidia/nemotron-x")
    a["chat_template_kwargs"]["enable_thinking"] = True
    assert model_extra_body("nvidia/nemotron-x") == THINKING_OFF


class _Rec:
    def __init__(self, reply="on_topic"):
        self.kwargs = []
        self.reply = reply
        self.chat = NS(completions=NS(create=self._create))

    def _create(self, **kw):
        self.kwargs.append(kw)
        content = json.dumps({"verdict": self.reply, "reason": "x"})
        return NS(choices=[NS(message=NS(content=content, tool_calls=None))], usage=None)


def test_agent_sends_thinking_off_for_nemotron():
    rec = _Rec()
    rec._create = lambda **kw: (rec.kwargs.append(kw), NS(choices=[NS(message=NS(content="Hello.", tool_calls=None))], usage=None))[1]
    rec.chat = NS(completions=NS(create=rec._create))
    Agent(client=rec, model="nvidia/nemotron-3.5-super-vl-120b-a12b").chat("hi")
    assert rec.kwargs[0]["extra_body"] == THINKING_OFF


def test_topic_classifier_sends_thinking_off_for_nemotron():
    rec = _Rec()
    classify(rec, "nvidia/nemotron-3-nano-30b-a3b", "what is the capital of France?", None, timeout_s=2)
    assert rec.kwargs[0]["extra_body"] == THINKING_OFF


def test_topic_classifier_sends_no_extra_for_other_models():
    rec = _Rec()
    classify(rec, "meta/llama-x", "hello there", None, timeout_s=2)
    assert "extra_body" not in rec.kwargs[0]


class _StreamRejector:
    """Rejects stream=True with a 400 (like some providers), answers normally otherwise."""
    def __init__(self):
        self.calls = []
        self.chat = NS(completions=NS(create=self._create))

    def _create(self, **kw):
        self.calls.append(bool(kw.get("stream")))
        if kw.get("stream"):
            err = Exception("stream_options not supported")
            err.status_code = 400
            raise err
        return NS(choices=[NS(message=NS(content="ok", tool_calls=None))], usage=None)


def test_model_that_rejects_streaming_is_remembered():
    client = _StreamRejector()
    kwargs = {"model": "nvidia/some-model", "messages": [{"role": "user", "content": "x"}]}
    llm.complete(client, dict(kwargs), stream=True, on_text=lambda t: None, delays=())
    assert client.calls == [True, False]          # first call: failed stream, then fallback
    llm.complete(client, dict(kwargs), stream=True, on_text=lambda t: None, delays=())
    assert client.calls == [True, False, False]   # second call skips the doomed stream attempt
