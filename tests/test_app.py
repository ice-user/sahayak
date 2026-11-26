"""Runs the Streamlit app headlessly with a fake LLM client."""
import json
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

APP = str(Path(__file__).resolve().parent.parent / "app.py")


class FakeClient:
    def __init__(self):
        self.script = [
            NS(content="", tool_calls=[NS(id="c1", function=NS(
                name="check_eligibility", arguments=json.dumps({"profile": {"age": 74}})))]),
            NS(content="Your grandfather can get Ayushman Bharat (PM-JAY) cover.", tool_calls=None),
        ]
        self.chat = NS(completions=NS(create=lambda **k: NS(
            choices=[NS(message=self.script.pop(0))], usage=NS(total_tokens=50))))


def test_app_loads():
    at = AppTest.from_file(APP, default_timeout=30).run()
    assert not at.exception
    assert "Sahayak" in at.title[0].value


def test_app_chat_turn_with_fake_llm():
    at = AppTest.from_file(APP, default_timeout=30)
    at.session_state["client_override"] = FakeClient()
    at.run()
    at.chat_input[0].set_value("Mere dadaji 74 saal ke hain").run()
    assert not at.exception
    texts = " ".join(m.value for m in at.markdown)
    assert "Ayushman" in texts
    assert any("tool calls" in e.label for e in at.expander)
