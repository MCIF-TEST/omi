"""Sliding-window rate limiter — in-memory.

Use for:
* Brute-force protection on /v1/auth/login (per-IP)
* Account farming protection on /v1/auth/signup (per-IP)

Scope: single process. For multi-instance deploys, swap behind the
same ``hit()`` interface for a Redis-backed token bucket (Phase 9.5).
"""

from __future__ import annotations

import threading
import time
from collections import deque


class SlidingWindowLimiter:
    """One limiter per key. ``hit()`` returns False if over budget."""

    def __init__(self, max_hits: int, per_seconds: float):
        self.max_hits = max_hits
        self.per_seconds = per_seconds
        self._lock = threading.Lock()
        self._windows: dict[str, deque[float]] = {}

    def hit(self, key: str) -> bool:
        """Record a hit. Returns True if allowed, False if rate-limited."""
        now = time.monotonic()
        cutoff = now - self.per_seconds
        with self._lock:
            dq = self._windows.get(key)
            if dq is None:
                dq = deque()
                self._windows[key] = dq
            # Drop expired
            while dq and dq[0] < cutoff:
                dq.popleft()
            if len(dq) >= self.max_hits:
                return False
            dq.append(now)
        return True

    def retry_after(self, key: str) -> float:
        """Seconds until the oldest hit in the window expires."""
        with self._lock:
            dq = self._windows.get(key)
            if not dq:
                return 0.0
            return max(0.0, self.per_seconds - (time.monotonic() - dq[0]))


# Pre-instantiated limiters used across the app
LOGIN_LIMITER = SlidingWindowLimiter(max_hits=10, per_seconds=60)
SIGNUP_LIMITER = SlidingWindowLimiter(max_hits=5, per_seconds=3600)
