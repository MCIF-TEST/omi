"""Background scheduler — FastAPI lifespan integration.

Runs one anomaly pass + a bounded number of watchlist re-checks every
``OMI_MONITORING_INTERVAL_SECONDS`` (default 5 min). Disabled by
default; flip ``OMI_ENABLE_MONITORING=true`` to turn on in production.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager, contextmanager
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI
from sqlalchemy import select

from app.core.config import get_settings
from app.monitoring.service import MonitoringService
from app.storage.db import get_session
from app.storage.models import Watchlist

logger = logging.getLogger("omi.monitoring")


@asynccontextmanager
async def lifespan_monitoring(app: FastAPI):
    """Start/stop the background monitoring task with FastAPI lifecycle."""
    settings = get_settings()
    task: asyncio.Task | None = None
    if settings.enable_monitoring:
        task = asyncio.create_task(_loop())
        logger.info("monitoring loop started (interval=%ss)", settings.monitoring_interval_seconds)
    try:
        yield
    finally:
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass


# Arbitrary but fixed key identifying the monitoring pass to Postgres' advisory-lock namespace.
# Must not change between deploys, or two versions would each think they hold the lock.
_MONITORING_LOCK_KEY = 918_273_645


@contextmanager
def _leader_lock():
    """Yield True only to the ONE instance that should run this pass.

    Every instance runs this loop in its own lifespan, so without mutual exclusion N instances mean N
    anomaly passes and N watchlist rescans per interval: duplicated customer-facing alerts and N times
    the upstream spend. Staggering the start (which is all this used to do) spreads that out, it does not
    prevent it.

    Uses a Postgres advisory lock, which is the right primitive here for two reasons: it needs no table
    or migration, and it is tied to the database session, so if the instance holding it crashes the lock
    is released automatically. A lease row in a table would need expiry handling to avoid a dead leader
    wedging monitoring permanently.

    On SQLite (local dev) there is no advisory lock and no second instance either, so it yields True.
    Any failure yields True rather than False: skipping monitoring silently is worse than occasionally
    duplicating a pass.
    """
    from sqlalchemy import text

    with get_session() as session:
        bind = session.get_bind()
        if bind.dialect.name != "postgresql":
            yield True
            return
        acquired = False
        try:
            acquired = bool(session.execute(
                text("SELECT pg_try_advisory_lock(:k)"), {"k": _MONITORING_LOCK_KEY},
            ).scalar())
        except Exception:  # noqa: BLE001 — never let lock trouble stop monitoring entirely
            logger.warning("could not acquire the monitoring leader lock; running anyway",
                           exc_info=True)
            yield True
            return
        try:
            yield acquired
        finally:
            if acquired:
                try:
                    session.execute(text("SELECT pg_advisory_unlock(:k)"),
                                    {"k": _MONITORING_LOCK_KEY})
                except Exception:  # noqa: BLE001 — the lock also frees when the session closes
                    pass


async def _loop() -> None:
    settings = get_settings()
    # Stagger start so multiple replicas don't all fire at once.
    await asyncio.sleep(5)
    while True:
        try:
            await asyncio.to_thread(_run_one_pass_if_leader)
        except Exception:  # noqa: BLE001
            logger.exception("monitoring pass failed")
        await asyncio.sleep(settings.monitoring_interval_seconds)


def _run_one_pass_if_leader() -> dict | None:
    """Run the pass only if this instance wins the leader lock for it."""
    with _leader_lock() as is_leader:
        if not is_leader:
            logger.debug("monitoring pass skipped — another instance holds the leader lock")
            return None
        return run_one_pass()


def run_one_pass() -> dict:
    """Run anomaly detection + watchlist auto-rescan once. Returns a small
    diagnostic dict suitable for logging or admin-route inspection."""
    out: dict = {"anomalies": None, "watchlist_rescans": 0, "formation_phases": 0}
    with get_session() as session:
        svc = MonitoringService(session)
        report = svc.run_anomaly_pass()
        out["anomalies"] = {
            "found": report.anomalies_found,
            "written": report.alerts_written,
        }
    rescans = _auto_rescan_due_watchlists()
    out["watchlist_rescans"] = rescans
    out["formation_phases"] = _refresh_formation_phases()
    return out


def _refresh_formation_phases() -> int:
    """Age the formation catalogue.

    DORMANCY IS THE ABSENCE OF AN EVENT, which nothing else in this codebase has to deal with.
    Every other state change in `app/netdetect` is driven by something happening: a finding is
    recorded, an operator judges it, an account is placed. A formation that simply STOPPED posting
    emits nothing to notice, so without a sweep it stays `active` forever and the catalogue slowly
    fills with operations that ended months ago, all presenting as live.

    `registry.refresh_phases` was written for this and had nothing calling it. Running it here
    rather than on a scheduler of its own is deliberate: this loop already holds a Postgres
    advisory lock, so N instances do not each age the catalogue N times.

    Best-effort and never raises. A phase is a label on a lead an operator reads; failing the
    monitoring pass over one would take the anomaly detection and the watchlist rescans down with
    it, which are the things customers actually depend on.
    """
    try:
        from app.netdetect import registry

        with get_session() as session:
            changed = registry.refresh_phases(session)
            session.commit()
        if changed:
            logger.info("netdetect: %d formation phases refreshed", changed)
        return changed
    except Exception:  # noqa: BLE001
        logger.warning("netdetect: could not refresh formation phases", exc_info=True)
        return 0


def _auto_rescan_due_watchlists() -> int:
    """Rescan a bounded number of channel watchlists due for re-check.

    Reuses the cached scan path so accounts seen recently return instantly.
    Falls back silently when YouTube isn't configured.
    """
    settings = get_settings()
    if not (settings.youtube_api_key or "").strip():
        return 0
    cutoff = datetime.now(timezone.utc) - timedelta(hours=settings.watchlist_recheck_hours)
    with get_session() as session:
        due = list(session.execute(
            select(Watchlist)
            .where(Watchlist.kind == "channel")
            # This re-scan loop uses the YouTube client only; X (and any future
            # platform) watchlists are routed/displayed correctly but re-scanned
            # via their own scan flow, not here. Backfilled rows are "youtube".
            .where(Watchlist.platform == "youtube")
            .where(
                (Watchlist.last_checked_at.is_(None))
                | (Watchlist.last_checked_at < cutoff)
            )
            .limit(settings.watchlist_max_per_tick)
        ).scalars())
    if not due:
        return 0

    # Lazy imports keep the scheduler optional in environments without YT deps
    try:
        from app.integrations.youtube import (
            FetchStats, build_default_client, fetch_channel_profile,
            fetch_channel_recent_comments, resolve_channel_id,
        )
        from app.monitoring.service import MonitoringService
        from app.orchestrator import scan_account_with_memory
    except Exception:
        return 0

    try:
        client = build_default_client(settings.youtube_api_key)
    except Exception:
        return 0

    rescans = 0
    for w in due:
        try:
            stats = FetchStats()
            channel_id = resolve_channel_id(client, w.target_id, stats=stats)
            if not channel_id:
                with get_session() as s:
                    row = s.get(Watchlist, w.id)
                    if row is not None:
                        row.last_checked_at = datetime.now(timezone.utc)
                continue
            profile = fetch_channel_profile(client, channel_id, stats=stats)
            if profile is None:
                continue
            history = fetch_channel_recent_comments(
                client, channel_id,
                max_comments=settings.scan_max_history_per_commenter,
                stats=stats,
            )
            with get_session() as s:
                orch = scan_account_with_memory(
                    s, platform="youtube",
                    external_id=channel_id, profile=profile, posts=history,
                    force_refresh=False,
                )
                MonitoringService(s).note_observation(
                    kind="channel",
                    target_id=w.target_id,
                    current_tier=orch.result.tier.value,
                    current_probability=orch.result.overall_probability,
                    platform=w.platform or "youtube",
                )
            rescans += 1
        except Exception:  # noqa: BLE001 — per-watchlist failures don't abort the loop
            logger.exception("watchlist rescan failed for %s", w.target_id)
    return rescans
