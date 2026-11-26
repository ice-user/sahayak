"""In-memory conversation store: session_id -> Agent, with idle expiry and a size cap."""
from __future__ import annotations

import secrets
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Callable

from sahayak.agent import Agent


class StoreFull(Exception):
    """Every slot is held by an in-flight request."""


@dataclass
class Session:
    id: str
    agent: Agent
    last_used: float
    busy: bool = False
    run: object | None = None   # the AgentRun currently holding the session
    language: str = "en"


class SessionStore:
    def __init__(self, factory: Callable[[], Agent], ttl_s: float = 1800, max_sessions: int = 1000,
                 clock: Callable[[], float] = time.monotonic):
        self._factory = factory
        self._ttl = ttl_s
        self._max = max_sessions
        self._clock = clock
        self._sessions: OrderedDict[str, Session] = OrderedDict()  # least recently used first

    def __len__(self) -> int:
        self._expire()
        return len(self._sessions)

    def get_or_create(self, session_id: str | None) -> Session:
        """Return the live session for `session_id`, or start a new one (unknown/expired ids get a fresh id)."""
        self._expire()
        session = self._sessions.get(session_id) if session_id else None
        if session is None:
            self._make_room()
            session = Session(id=secrets.token_urlsafe(9), agent=self._factory(), last_used=self._clock())
            self._sessions[session.id] = session
        self.touch(session)
        return session

    def touch(self, session: Session) -> None:
        session.last_used = self._clock()
        if session.id in self._sessions:
            self._sessions.move_to_end(session.id)

    def reset(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)

    def _expire(self) -> None:
        now = self._clock()
        for sid, s in list(self._sessions.items()):
            if now - s.last_used < self._ttl:
                break
            if not s.busy:
                del self._sessions[sid]

    def _make_room(self) -> None:
        while len(self._sessions) >= self._max:
            victim = next((sid for sid, s in self._sessions.items() if not s.busy), None)
            if victim is None:
                raise StoreFull("too many conversations in progress")
            del self._sessions[victim]
