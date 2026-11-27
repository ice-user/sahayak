"""Thin LLM layer: build messages, call an OpenAI-compatible client, parse JSON robustly."""
from __future__ import annotations

import json
import re
import threading
from dataclasses import dataclass
from typing import Any

_THINK = re.compile(r"<think>.*?</think>", re.S)
_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.I)


STATS = {"calls": 0, "tokens": 0}      # process-wide counters, read by the batch report
_STATS_LOCK = threading.Lock()


class LLMOutputError(ValueError):
    """The model answered, but not with a JSON object."""


def parse_json_object(raw: str) -> dict:
    """Extract the first balanced JSON object from model text (handles <think>, fences, chatter)."""
    text = _FENCE.sub("", _THINK.sub("", raw or "").strip()).strip()
    start = text.find("{")
    if start < 0:
        raise LLMOutputError("response contains no JSON object")
    depth, in_str, esc = 0, False, False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        elif ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    obj = json.loads(text[start:i + 1])
                except json.JSONDecodeError as e:
                    raise LLMOutputError(f"invalid JSON: {e}") from e
                if not isinstance(obj, dict):
                    raise LLMOutputError("JSON is not an object")
                return obj
    raise LLMOutputError("JSON object is not closed (output truncated?)")


@dataclass
class LLM:
    """Holds a client (lazily created via sahayak.agent.make_client) and the model name."""
    client: Any = None
    model: str | None = None
    temperature: float = 0.0
    max_tokens: int = 8192      # long scheme pages need room for every rule + its verbatim quote

    def _ensure(self):
        if self.client is None:
            from sahayak.agent import make_client
            self.client = make_client()
        if self.model is None:
            from sahayak.agent import resolve_config
            self.model = resolve_config()[2]

    def complete(self, messages: list[dict]) -> str:
        self._ensure()
        from sahayak.llm_options import model_extra_body
        kwargs: dict[str, Any] = {}
        extra = model_extra_body(self.model)   # Nemotron thinks by default: thinking would eat the JSON budget
        if extra:
            kwargs["extra_body"] = extra
        if "qwen3" in (self.model or "").lower() and messages:   # Qwen3 thinks unless told not to (soft switch)
            messages = [*messages[:-1], {**messages[-1], "content": f"{messages[-1]['content']}\n/no_think"}]
        resp = self.client.chat.completions.create(
            model=self.model, messages=messages, temperature=self.temperature, max_tokens=self.max_tokens, **kwargs)
        with _STATS_LOCK:
            STATS["calls"] += 1
            STATS["tokens"] += int(getattr(getattr(resp, "usage", None), "total_tokens", 0) or 0)
        return resp.choices[0].message.content or ""
