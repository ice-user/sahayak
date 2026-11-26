"""Fake OpenAI-style clients for tests: whole replies, streamed chunks and scripted errors. No network."""
from __future__ import annotations

import json
from types import SimpleNamespace as NS


class StatusError(Exception):
    """A provider error carrying an HTTP status (like openai.APIStatusError)."""

    def __init__(self, status: int, message: str = "provider error"):
        super().__init__(message)
        self.status_code = status


class APITimeoutError(Exception):
    """Same class name as openai.APITimeoutError."""


def tool_msg(name, args, call_id="c1"):
    return NS(content="", tool_calls=[NS(id=call_id, function=NS(name=name, arguments=json.dumps(args)))])


def text_msg(text):
    return NS(content=text, tool_calls=None)


# ---- stream chunks
def tc_delta(index, id=None, name=None, args=None):
    return NS(index=index, id=id, function=NS(name=name, arguments=args))


def chunk(content=None, tool_calls=None, usage=None, finish=None):
    return NS(choices=[NS(delta=NS(content=content, tool_calls=tool_calls), finish_reason=finish)],
              usage=NS(total_tokens=usage) if usage is not None else None)


def usage_chunk(total):
    """Final chunk some providers send: no choices, only usage."""
    return NS(choices=[], usage=NS(total_tokens=total))


def split(text, size):
    return [text[i:i + size] for i in range(0, len(text), size)] or [""]


def text_stream(text, size=5, usage=None, pieces=None):
    parts = pieces if pieces is not None else split(text, size)
    chunks = [chunk(None)] + [chunk(p) for p in parts] + [chunk(finish="stop")]
    return chunks + ([usage_chunk(usage)] if usage is not None else [])


def tool_stream(name, args, call_id="c1", size=9, index=0, usage=None):
    """One tool call streamed OpenAI-style: id + name (+ empty args) first, then argument fragments."""
    raw = json.dumps(args)
    chunks = [chunk(tool_calls=[tc_delta(index, call_id, name, "")])]
    chunks += [chunk(tool_calls=[tc_delta(index, None, None, p)]) for p in split(raw, size)]
    chunks.append(chunk(finish="tool_calls"))
    return chunks + ([usage_chunk(usage)] if usage is not None else [])


class Broken:
    """A stream that yields `chunks` and then raises `exc` (a connection dying mid-stream)."""

    def __init__(self, chunks, exc):
        self.chunks, self.exc = chunks, exc


class FakeLLM:
    """Replays a script, one item per create() call:
      NS message            whole (non-streamed) reply
      list of chunks        streamed reply (create must be called with stream=True)
      Broken(chunks, exc)   streamed reply that fails part-way
      Exception             raised by create()
    `.sent` records every call's kwargs (messages snapshotted)."""

    def __init__(self, script):
        self.script = list(script)
        self.sent: list[dict] = []
        self.closed = 0
        self.chat = NS(completions=NS(create=self._create))

    def _create(self, **kwargs):
        self.sent.append({**kwargs, "messages": list(kwargs["messages"])})
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        if isinstance(item, (list, Broken)):
            assert kwargs.get("stream"), "streamed reply scripted for a non-streaming call"
            return self._iterate(item)
        return NS(choices=[NS(message=item)], usage=NS(total_tokens=100))

    def _iterate(self, item):
        chunks, exc = (item.chunks, item.exc) if isinstance(item, Broken) else (item, None)
        client = self

        class It:
            def __iter__(self_inner):
                yield from chunks
                if exc is not None:
                    raise exc

            def close(self_inner):
                client.closed += 1

        return It()

    @property
    def streamed_calls(self):
        return [s for s in self.sent if s.get("stream")]


def collect(agent, message):
    """Run a turn, returning (answer, trace, events) with events as (kind, data) in arrival order."""
    events: list[tuple[str, dict]] = []
    answer, trace = agent.chat(message, on_event=lambda k, d: events.append((k, d)))
    return answer, trace, events
