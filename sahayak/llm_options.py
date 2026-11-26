"""Per-request provider options shared by the agent, the topic classifier and check_llm.

Nemotron 3 / 3.5 models on NVIDIA's API think before answering by default
(chat_template_kwargs.enable_thinking). With a short answer budget the thinking
eats the whole budget and the visible answer comes back empty or cut off, which
is exactly what the first real eval run showed. So Nemotron models get thinking
turned OFF unless you opt back in with LLM_THINKING=1.
"""
from __future__ import annotations

import copy
import json
import logging
import os

log = logging.getLogger(__name__)

THINKING_OFF = {"chat_template_kwargs": {"enable_thinking": False}}
_TRUE = ("1", "true", "on", "yes")


def env_extra_body() -> dict | None:
    """LLM_EXTRA_BODY: a JSON object passed to chat.completions.create(extra_body=...). Invalid values are ignored
    with a warning (a typo must not take the service down)."""
    raw = os.environ.get("LLM_EXTRA_BODY", "").strip()
    if not raw:
        return None
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        value = None
    if not isinstance(value, dict):
        log.warning("LLM_EXTRA_BODY is not a JSON object; ignoring it")
        return None
    return value


def is_reasoning_default_model(model: str | None) -> bool:
    """Models known to think by default on NVIDIA's API (enable_thinking defaults to true)."""
    return "nemotron" in (model or "").lower()


def model_extra_body(model: str | None) -> dict | None:
    """extra_body for one request to `model`. LLM_EXTRA_BODY always wins; otherwise Nemotron models get thinking off
    (unless LLM_THINKING=1); other models get nothing."""
    explicit = env_extra_body()
    if explicit is not None:
        return explicit
    if is_reasoning_default_model(model) and os.environ.get("LLM_THINKING", "0").strip().lower() not in _TRUE:
        return copy.deepcopy(THINKING_OFF)
    return None
