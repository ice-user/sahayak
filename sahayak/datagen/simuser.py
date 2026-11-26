"""A rule-based dummy user that answers the agent's follow-up questions truthfully.

It doesn't need to understand the agent's question: the last check_eligibility
result lists exactly which facts are missing, so the dummy user answers those
(up to 3 at a time) from its hidden profile, in its own language.
"""
from __future__ import annotations

import json
import random

from .phrases import DONT_KNOW, NOTHING_MORE, fact_phrase
from .profiles import Scenario, implied_by


def missing_from_messages(messages: list[dict]) -> list[str]:
    """Missing fields reported by the most recent check_eligibility call."""
    call_ids = {}
    for m in messages:
        for tc in m.get("tool_calls") or []:
            call_ids[tc["id"]] = tc["function"]["name"]
    for m in reversed(messages):
        if m.get("role") == "tool" and call_ids.get(m.get("tool_call_id")) == "check_eligibility":
            try:
                result = json.loads(m["content"])
            except (json.JSONDecodeError, TypeError):
                return []
            fields = []
            for r in result.get("need_info", []):
                for f in r.get("missing_fields", []):
                    f = "children" if f.startswith("children") else f
                    if f not in fields:
                        fields.append(f)
            return fields
    return []


class SimUser:
    def __init__(self, scenario: Scenario, seed: int = 0, dont_know_rate: float = 0.08):
        self.s = scenario
        self.revealed: set[str] = set(scenario.revealed)
        self.dont_know: set[str] = set()
        self.r = random.Random(f"{scenario.id}-{seed}")
        self.dont_know_rate = dont_know_rate
        self.said_nothing_more = False

    def reply(self, messages: list[dict]) -> str | None:
        """Next user message, or None if the conversation should end."""
        last = next((m for m in reversed(messages) if m.get("role") == "assistant" and not m.get("tool_calls")), None)
        if last is None or "?" not in (last.get("content") or ""):
            return None  # the agent gave a final answer

        todo = [f for f in missing_from_messages(messages)
                if f not in self.revealed and f not in self.dont_know and f in self.s.profile][:3]
        if not todo:
            if self.said_nothing_more:
                return None
            self.said_nothing_more = True
            return NOTHING_MORE[self.s.lang]

        lang, parts = self.s.lang, []
        for f in todo:
            if self.r.random() < self.dont_know_rate:
                self.dont_know.add(f)
                parts.append(DONT_KNOW[lang])
                continue
            shown = "is_govt_employee" if f == "in_regular_govt_employment" else f
            phrase = fact_phrase(shown, self.s.profile[shown], lang, self.s.profile["gender"])
            if phrase:
                parts.append(phrase)
                self.revealed.add(f)
                self.revealed.update(implied_by(shown, self.s.profile[shown]))
        end = "।" if lang == "hi" else "."
        parts = [p.rstrip(".।") for p in dict.fromkeys(parts)]
        return ", ".join(parts) + end
