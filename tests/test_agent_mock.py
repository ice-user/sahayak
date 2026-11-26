"""Tests the agent loop without a real LLM, using a scripted fake client."""
import json
from types import SimpleNamespace as NS

from sahayak.agent import Agent


def _tool_msg(name, args, call_id="c1"):
    return NS(content="", tool_calls=[NS(id=call_id, function=NS(name=name, arguments=json.dumps(args)))])


def _text_msg(text):
    return NS(content=text, tool_calls=None)


class FakeClient:
    """Returns pre-scripted messages and records what the agent sent."""
    def __init__(self, script):
        self.script = list(script)
        self.sent = []
        self.chat = NS(completions=NS(create=self._create))

    def _create(self, **kwargs):
        self.sent.append({**kwargs, "messages": list(kwargs["messages"])})  # snapshot
        msg = self.script.pop(0)
        return NS(choices=[NS(message=msg)], usage=NS(total_tokens=100))


def test_agent_runs_tool_then_answers():
    client = FakeClient([
        _tool_msg("check_eligibility", {"profile": {"age": 62, "gender": "female",
                                                    "marital_status": "widowed", "bpl": True}}),
        _text_msg("Your mother can get the widow pension (IGNWPS)."),
    ])
    agent = Agent(client=client, model="fake")
    answer, trace = agent.chat("My mother is 62, a widow, BPL card holder")

    assert "IGNWPS" in answer
    calls = trace.tool_calls()
    assert len(calls) == 1 and calls[0]["name"] == "check_eligibility"
    result = json.loads(calls[0]["result"])
    assert {r["scheme_id"] for r in result["eligible"]} >= {"ignwps", "ignoaps"}
    # the tool result was fed back to the model on the second call
    assert client.sent[1]["messages"][-1]["role"] == "tool"


def test_agent_stops_at_max_steps():
    client = FakeClient([_tool_msg("search_schemes", {"query": "pension"}, f"c{i}") for i in range(3)])
    agent = Agent(client=client, model="fake", max_steps=3)
    answer, trace = agent.chat("loop forever")
    assert trace.steps[-1].get("stopped") == "max_steps"


def test_agent_recovers_from_bad_tool_args():
    client = FakeClient([
        _tool_msg("check_eligibility", {"profile": {"age": "sixty"}}),
        _text_msg("Could you tell me the exact age?"),
    ])
    agent = Agent(client=client, model="fake")
    answer, trace = agent.chat("my father is old")
    assert "error" in json.loads(trace.tool_calls()[0]["result"])
    assert answer.endswith("?")
