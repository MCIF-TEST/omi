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

# Module-level on purpose (see CLAUDE.md, "A bug class worth knowing"): a function-level import here
# would not be visible to anything nested, and this module is all about running other people's
# closures. `observability` imports nothing but `logging` and `os` until a DSN is configured.
from app.core.observability import capture_exception

logger = logging.getLogger("omi.background")

_executor: ThreadPoolExecutor | None = None
_slow_executor: ThreadPoolExecutor | None = None
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


def _get_slow() -> ThreadPoolExecutor:
    """The pool for MINUTES-LONG work — currently the analyst's batched generation.

    Kept separate from the general pool on purpose. Analyst generation holds its worker for the whole
    run: batches are issued one at a time (so the first accounts land as early as possible), so a
    100-account investigation occupies one thread for four sequential model calls. Sharing the general
    pool meant a handful of concurrent investigations could hold every worker, and the *scan* jobs
    queued behind them — the user-visible "everything is taking forever", caused by AI work that was
    never on the scan's critical path. Isolating it means a saturated analyst queue slows only the AI
    assessment, never a scan.
    """
    global _slow_executor
    if _slow_executor is None:
        with _lock:
            if _slow_executor is None:
                _slow_executor = ThreadPoolExecutor(
                    max_workers=4, thread_name_prefix="omi-slow",
                )
    return _slow_executor


def submit(fn: Callable[..., Any], *args, **kwargs) -> Future | None:
    """Fire-and-forget submit. Exceptions are logged, never raised."""
    return _submit_to(_get(), fn, args, kwargs)


def submit_slow(fn: Callable[..., Any], *args, **kwargs) -> Future | None:
    """Fire-and-forget submit for long-running work, on a pool of its own so it can never starve the
    short tasks (scan jobs, persistence, delivery) that share ``submit``."""
    return _submit_to(_get_slow(), fn, args, kwargs)


def _submit_to(ex: ThreadPoolExecutor, fn: Callable[..., Any], args: tuple, kwargs: dict) -> Future | None:
    try:
        fut = ex.submit(_wrap, fn, args, kwargs)
        with _lock:
            _pending.add(fut)
        fut.add_done_callback(_discard)
        return fut
    except Exception as exc:  # noqa: BLE001 — executor down → drop the work, never the request
        logger.exception("background.submit failed")
        capture_exception(exc)
        return None


def _discard(fut: Future) -> None:
    with _lock:
        _pending.discard(fut)


def _wrap(fn: Callable[..., Any], args: tuple, kwargs: dict) -> None:
    """Run the task, absorbing any failure.

    This is the single most important place in the codebase to report an exception from. Nothing here
    ever raises into a request, so a background failure has no user-visible signature at all: the scan
    or the analyst run simply never finishes, and the only trace is one line in an ephemeral log
    stream. That is exactly how the `NameError` in the analyst's persist closure hid long enough to
    mean no investigation over 25 accounts ever produced an assessment.
    """
    try:
        fn(*args, **kwargs)
    except Exception as exc:  # noqa: BLE001
        logger.exception("background task failed: %s", getattr(fn, "__name__", fn))
        capture_exception(exc)


def shutdown(wait_seconds: float = 5.0) -> None:
    """Drain in-flight tasks within a BOUNDED budget. Called from FastAPI
    lifespan. Previously this passed ``wait=True`` and ignored ``wait_seconds``,
    so a single hung best-effort task could block a redeploy indefinitely."""
    global _executor, _slow_executor
    pools = [p for p in (_executor, _slow_executor) if p is not None]
    if not pools:
        return
    _executor = None
    _slow_executor = None
    # Stop accepting new work and drop anything still queued; let running tasks
    # finish within the grace period.
    for ex in pools:
        ex.shutdown(wait=False, cancel_futures=True)
    with _lock:
        pending = list(_pending)
    if pending and wait_seconds > 0:
        from concurrent.futures import wait as _wait
        _wait(pending, timeout=wait_seconds)
