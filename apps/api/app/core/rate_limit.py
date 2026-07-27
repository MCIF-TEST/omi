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
import weakref
from collections import deque

from fastapi import HTTPException, Request, status

# Every limiter ever constructed, so the test suite can reset all of them in one call — including
# ones it has no reference to. That is not hypothetical bookkeeping: GlobalRateLimitMiddleware builds
# its OWN limiter as an instance attribute (not one of the module singletons below), the middleware
# hangs off the app object, and `app.main` exposes a module-level `app = create_app()` that most test
# files import and share. So that limiter quietly accumulated every request made by the whole test
# session against TestClient's single default IP, and once past 120 in 60s it answered ~everything
# with 429 for the rest of the run. Fixtures were clearing SIGNUP_LIMITER/LOGIN_LIMITER and had no
# way to reach the one actually doing the damage.
#
# Weak, so registration never keeps a dead app's middleware (or its limiter) alive.
_ALL_LIMITERS: weakref.WeakSet = weakref.WeakSet()


class SlidingWindowLimiter:
    """One limiter per key. ``hit()`` returns False if over budget."""

    def __init__(self, max_hits: int, per_seconds: float):
        self.max_hits = max_hits
        self.per_seconds = per_seconds
        self._lock = threading.Lock()
        self._windows: dict[str, deque[float]] = {}
        _ALL_LIMITERS.add(self)

    def reset(self) -> None:
        """Forget every recorded hit. Thread-safe."""
        with self._lock:
            self._windows.clear()

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


def reset_all_limiters_for_tests() -> None:
    """Clear EVERY limiter's window, including per-app-instance ones the caller can't name.

    Tests only. The suite shares one app (and therefore one GlobalRateLimitMiddleware limiter) across
    files, so without a per-test reset the throttle is cumulative over the whole session and turns
    into mass 429s that surface as unrelated-looking fixture errors. Called from the autouse fixture
    in ``tests/conftest.py``; production never calls this.
    """
    for limiter in list(_ALL_LIMITERS):
        limiter.reset()


# Pre-instantiated limiters used across the app
LOGIN_LIMITER = SlidingWindowLimiter(max_hits=10, per_seconds=60)
SIGNUP_LIMITER = SlidingWindowLimiter(max_hits=5, per_seconds=3600)
# Password reset requests — tight, to slow token-mining + email bombing.
RESET_LIMITER = SlidingWindowLimiter(max_hits=5, per_seconds=3600)
# Public report routes (/r/*, /rc/*) — unauthenticated and uncached. Generous
# so a genuinely viral report from many viewers is never throttled, but a
# single scraper hammering one IP is capped (and can't flood the EventLog).
PUBLIC_REPORT_LIMITER = SlidingWindowLimiter(max_hits=60, per_seconds=60)


def public_report_rate_limit(request: Request) -> None:
    """FastAPI dependency: per-IP throttle for the public report routers.

    Applied at the router level so it covers the view + markdown + json
    sub-routes in one place. Keyed on the client IP (never stored).
    """
    from app.core.ip import client_ip

    ip = client_ip(request)
    if not PUBLIC_REPORT_LIMITER.hit(ip):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests — please try again shortly.",
            headers={"Retry-After": str(int(PUBLIC_REPORT_LIMITER.retry_after(ip)) + 1)},
        )
