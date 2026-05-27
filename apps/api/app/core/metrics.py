"""Lightweight in-process metrics registry.

Two metric types for Phase 9:

* ``Counter`` — monotonic integer
* ``Histogram`` — bounded ring of recent samples; query yields p50/p95/p99

Surfaced through /v1/metrics (admin only). For Prometheus / OTLP
export, this same registry can be scraped by a Phase 9.5 exporter.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from typing import Any


class Counter:
    __slots__ = ("_v", "_lock")

    def __init__(self) -> None:
        self._v = 0
        self._lock = threading.Lock()

    def inc(self, n: int = 1) -> None:
        with self._lock:
            self._v += n

    @property
    def value(self) -> int:
        return self._v


class Histogram:
    """Bounded ring of recent samples for percentile snapshots."""

    def __init__(self, max_samples: int = 1024):
        self._dq: deque[float] = deque(maxlen=max_samples)
        self._lock = threading.Lock()

    def observe(self, v: float) -> None:
        with self._lock:
            self._dq.append(v)

    def snapshot(self) -> dict[str, float]:
        with self._lock:
            samples = sorted(self._dq)
        n = len(samples)
        if n == 0:
            return {"count": 0, "p50": 0.0, "p95": 0.0, "p99": 0.0, "max": 0.0}
        def q(p: float) -> float:
            i = min(n - 1, max(0, int(p * n)))
            return samples[i]
        return {
            "count": n,
            "p50": q(0.50),
            "p95": q(0.95),
            "p99": q(0.99),
            "max": samples[-1],
        }


class Registry:
    def __init__(self) -> None:
        self.counters: dict[str, Counter] = {}
        self.histograms: dict[str, Histogram] = {}
        self._lock = threading.Lock()

    def counter(self, name: str) -> Counter:
        with self._lock:
            c = self.counters.get(name)
            if c is None:
                c = Counter()
                self.counters[name] = c
            return c

    def histogram(self, name: str) -> Histogram:
        with self._lock:
            h = self.histograms.get(name)
            if h is None:
                h = Histogram()
                self.histograms[name] = h
            return h

    def snapshot(self) -> dict[str, Any]:
        return {
            "counters": {k: c.value for k, c in self.counters.items()},
            "histograms": {k: h.snapshot() for k, h in self.histograms.items()},
            "snapshot_at": time.time(),
        }


_registry: Registry | None = None


def get_registry() -> Registry:
    global _registry
    if _registry is None:
        _registry = Registry()
    return _registry
