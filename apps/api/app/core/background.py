"""Bounded background task executor.

Sized for "fire and forget" work that mustn't block HTTP responses:
narrative ingestion, alert fan-out, cache warming. Bounded so a flood
of work can't OOM the process.

Phase 9.5 swap target: Dramatiq + Redis once we have multi-instance
deploys. The interface (``submit(callable, *args)``) stays.
"""

from __future__ import annotations

import logging
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any, Callable

logger = logging.getLogger("omi.background")

_executor: ThreadPoolExecutor | None = None
_lock = threading.Lock()


def _get() -> ThreadPoolExecutor:
    global _executor
    if _executor is None:
        with _lock:
            if _executor is None:
                # Each scan submits up to 4 background tasks: narrative
                # ingestion, delivery, content intelligence, investigation
                # persistence. With 12 workers, 3 concurrent scans can each
                # have all their tasks running simultaneously without queuing.
                # Investigation persistence retries (up to 3 × 3s sleep) must
                # not starve other tasks, so keep headroom above 4×concurrency.
                _executor = ThreadPoolExecutor(
                    max_workers=12, thread_name_prefix="omi-bg",
                )
    return _executor


def submit(fn: Callable[..., Any], *args, **kwargs) -> Future | None:
    """Fire-and-forget submit. Exceptions are logged, never raised."""
    try:
        fut = _get().submit(_wrap, fn, args, kwargs)
        return fut
    except Exception:  # noqa: BLE001 — executor down → drop silently
        logger.exception("background.submit failed")
        return None


def _wrap(fn: Callable[..., Any], args: tuple, kwargs: dict) -> None:
    try:
        fn(*args, **kwargs)
    except Exception:  # noqa: BLE001
        logger.exception("background task failed: %s", getattr(fn, "__name__", fn))


def shutdown(wait_seconds: float = 5.0) -> None:
    """Drain in-flight tasks. Called from FastAPI lifespan."""
    global _executor
    if _executor is None:
        return
    try:
        _executor.shutdown(wait=True, cancel_futures=False)
    finally:
        _executor = None
