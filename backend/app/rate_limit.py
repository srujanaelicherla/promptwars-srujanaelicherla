"""Process-local AI rate limit. Not a distributed quota."""

from __future__ import annotations

import time
from threading import Lock

from app.bookings import BookingError


class RateLimiter:
    def __init__(self, *, limit: int = 20, window_seconds: float = 60.0) -> None:
        self._limit = limit
        self._window = window_seconds
        self._hits: dict[str, list[float]] = {}
        self._lock = Lock()

    def check(self, key: str) -> None:
        now = time.monotonic()
        with self._lock:
            recent = [stamp for stamp in self._hits.get(key, []) if now - stamp < self._window]
            if len(recent) >= self._limit:
                raise BookingError(429, "rate_limited", "Too many AI requests. Try again shortly.")
            recent.append(now)
            self._hits[key] = recent
