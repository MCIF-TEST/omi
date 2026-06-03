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
# In-flight futures, tracked so shutdown() can wait on them within a bounded
# budget instead of blocking forever.
_pending: set[Future] = set()


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
        with _lock:
            _pending.add(fut)
        fut.add_done_callback(_discard)
        return fut
    except Exception:  # noqa: BLE001 — executor down → drop silently
        logger.exception("background.submit failed")
        return None


def _discard(fut: Future) -> None:
    with _lock:
        _pending.discard(fut)


def _wrap(fn: Callable[..., Any], args: tuple, kwargs: dict) -> None:
    try:
        fn(*args, **kwargs)
    except Exception:  # noqa: BLE001
        logger.exception("background task failed: %s", getattr(fn, "__name__", fn))


def shutdown(wait_seconds: float = 5.0) -> None:
    """Drain in-flight tasks within a BOUNDED budget. Called from FastAPI
    lifespan. Previously this passed ``wait=True`` and ignored ``wait_seconds``,
    so a single hung best-effort task could block a redeploy indefinitely."""
    global _executor
    ex = _executor
    if ex is None:
        return
    _executor = None
    # Stop accepting new work and drop anything still queued; let running tasks
    # finish within the grace period.
    ex.shutdown(wait=False, cancel_futures=True)
    with _lock:
        pending = list(_pending)
    if pending and wait_seconds > 0:
        from concurrent.futures import wait as _wait
        _wait(pending, timeout=wait_seconds)
