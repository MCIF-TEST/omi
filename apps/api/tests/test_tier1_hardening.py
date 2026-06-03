"""Tier-1 foundation hardening regressions.

Covers the data-integrity + reliability fixes that complete Tier 1:
- Schema index gap-fill: an index added to the model AFTER a table already
  exists is created on the next boot (create_all only indexes NEW tables).
- Background drain is time-bounded: shutdown() honours its wait_seconds budget
  and can't block a redeploy on a hung best-effort task.
"""

from __future__ import annotations

import threading
import time

from sqlalchemy import inspect, text

from app.storage.db import _ensure_indexes, init_db


# ---------------------------------------------------------------------------
# Schema: missing-index gap-fill (Weakness #15 / data-access integrity)
# ---------------------------------------------------------------------------

def test_ensure_indexes_recreates_index_missing_on_existing_table():
    """Simulates a long-lived production DB whose table predates a later-added
    index: create_all leaves it untouched, so the gap-fill pass must add it."""
    engine = init_db()  # conftest already built a fresh in-memory DB
    insp = inspect(engine)
    baseline = {ix["name"] for ix in insp.get_indexes("investigations")}
    assert "ix_inv_user_created" in baseline, f"expected baseline index; got {baseline}"

    # Drop it to mimic a table created before the index existed.
    with engine.begin() as conn:
        conn.execute(text("DROP INDEX ix_inv_user_created"))
    after_drop = {ix["name"] for ix in inspect(engine).get_indexes("investigations")}
    assert "ix_inv_user_created" not in after_drop

    # The gap-fill pass recreates it — and is idempotent on a second run.
    _ensure_indexes(engine)
    _ensure_indexes(engine)
    healed = {ix["name"] for ix in inspect(engine).get_indexes("investigations")}
    assert "ix_inv_user_created" in healed, "index gap-fill did not recreate the index"


def test_init_db_runs_index_gap_fill_without_error():
    """init_db() wires in the index pass; a second call is a clean no-op."""
    engine = init_db()
    # Re-running must not raise even though every index already exists.
    _ensure_indexes(engine)
    names = {ix["name"] for ix in inspect(engine).get_indexes("scans")}
    # Phase-9 composite index on the hot scan-history query.
    assert any("account" in (n or "") for n in names), f"scan indexes: {names}"


# ---------------------------------------------------------------------------
# Background: bounded shutdown (Tier-1 recovery / clean redeploys)
# ---------------------------------------------------------------------------

def test_background_shutdown_honours_time_budget():
    """A hung best-effort task must not make shutdown() block past its budget.
    Previously shutdown() passed wait=True and ignored wait_seconds entirely."""
    from app.core import background

    started = threading.Event()
    release = threading.Event()

    def _slow():
        started.set()
        release.wait(timeout=10)  # would block shutdown for 10s if unbounded

    background.submit(_slow)
    assert started.wait(timeout=3), "background task should have started"

    t0 = time.monotonic()
    background.shutdown(wait_seconds=0.5)
    elapsed = time.monotonic() - t0
    release.set()  # let the worker finish cleanly (before any assert)

    assert elapsed < 5.0, f"shutdown ignored its 0.5s budget; blocked for {elapsed:.1f}s"
