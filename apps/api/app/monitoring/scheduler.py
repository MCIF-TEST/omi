"""Background scheduler — FastAPI lifespan integration.

Runs one anomaly pass + a bounded number of watchlist re-checks every
``OMI_MONITORING_INTERVAL_SECONDS`` (default 5 min). Disabled by
default; flip ``OMI_ENABLE_MONITORING=true`` to turn on in production.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
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


async def _loop() -> None:
    settings = get_settings()
    # Stagger start so multiple replicas don't all fire at once.
    await asyncio.sleep(5)
    while True:
        try:
            await asyncio.to_thread(run_one_pass)
        except Exception:  # noqa: BLE001
            logger.exception("monitoring pass failed")
        await asyncio.sleep(settings.monitoring_interval_seconds)


def run_one_pass() -> dict:
    """Run anomaly detection + watchlist auto-rescan once. Returns a small
    diagnostic dict suitable for logging or admin-route inspection."""
    out: dict = {"anomalies": None, "watchlist_rescans": 0}
    with get_session() as session:
        svc = MonitoringService(session)
        report = svc.run_anomaly_pass()
        out["anomalies"] = {
            "found": report.anomalies_found,
            "written": report.alerts_written,
        }
    rescans = _auto_rescan_due_watchlists()
    out["watchlist_rescans"] = rescans
    return out


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
                )
            rescans += 1
        except Exception:  # noqa: BLE001 — per-watchlist failures don't abort the loop
            logger.exception("watchlist rescan failed for %s", w.target_id)
    return rescans
