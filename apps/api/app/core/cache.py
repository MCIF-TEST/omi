"""Bounded TTL cache.

In-process LRU + per-entry TTL. Thread-safe enough for FastAPI's sync
threadpool (the lock is uncontended in practice).

Phase 9 wires this into a small set of hot endpoints (status,
narratives, graph communities). Phase 9.5 swaps the backend for Redis
behind the same interface when multi-instance scaling makes process-
local cache useless.
"""

from __future__ import annotations

import threading
import time
from collections import OrderedDict
from typing import Any


class _Entry:
    __slots__ = ("value", "expires_at")

    def __init__(self, value: Any, expires_at: float):
        self.value = value
        self.expires_at = expires_at


class TTLCache:
    """Thread-safe LRU + TTL cache. Bounded by ``max_entries``."""

    def __init__(self, max_entries: int = 512):
        self._max = max_entries
        self._lock = threading.Lock()
        self._d: "OrderedDict[str, _Entry]" = OrderedDict()

    def get(self, key: str) -> Any | None:
        now = time.monotonic()
        with self._lock:
            e = self._d.get(key)
            if e is None:
                return None
            if e.expires_at < now:
                # expired
                self._d.pop(key, None)
                return None
            # LRU touch
            self._d.move_to_end(key)
            return e.value

    def set(self, key: str, value: Any, *, ttl_seconds: float) -> None:
        expires = time.monotonic() + ttl_seconds
        with self._lock:
            self._d[key] = _Entry(value, expires)
            self._d.move_to_end(key)
            while len(self._d) > self._max:
                self._d.popitem(last=False)

    def invalidate(self, key: str) -> None:
        with self._lock:
            self._d.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._d.clear()

    def stats(self) -> dict:
        with self._lock:
            return {"size": len(self._d), "max": self._max}


# Process-level singleton used by routes
_cache: TTLCache | None = None


def get_cache() -> TTLCache:
    global _cache
    if _cache is None:
        _cache = TTLCache(max_entries=1024)
    return _cache
