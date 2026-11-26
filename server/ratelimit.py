"""Sliding-window per-key rate limiter (in memory, single process)."""
from __future__ import annotations

import time
from collections import deque
from typing import Callable

WINDOW_S = 600.0
_PRUNE_AT = 10_000


class RateLimiter:
    def __init__(self, limit: int, window_s: float = WINDOW_S, clock: Callable[[], float] = time.monotonic):
        self.limit = limit
        self.window_s = window_s
        self._clock = clock
        self._hits: dict[str, deque[float]] = {}
        self._last_prune = clock()

    def size(self) -> int:
        return len(self._hits)

    def check(self, key: str) -> float | None:
        """Record a hit. Returns None if allowed, else seconds until the key may retry."""
        now = self._clock()
        if len(self._hits) > _PRUNE_AT or now - self._last_prune >= max(1.0, self.window_s / 4):
            self._prune(now)
        hits = self._hits.setdefault(key, deque())
        while hits and now - hits[0] >= self.window_s:
            hits.popleft()
        if len(hits) >= self.limit:
            return max(1.0, self.window_s - (now - hits[0]))
        hits.append(now)
        return None

    def _prune(self, now: float) -> None:
        """Drop keys whose newest hit has left the window (bounds memory under many distinct clients)."""
        self._last_prune = now
        self._hits = {k: h for k, h in self._hits.items() if h and now - h[-1] < self.window_s}
