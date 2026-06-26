"""Durable storage for shadow evaluations (Sprint 007).

Persists each ``ShadowReport`` inside ``Investigation.payload_json`` under
``shadow_evaluation_v1`` — the same additive, owner-scoped place the analyst assessment lives,
so every investigation becomes **replayable** from its own row. Writes are SAVEPOINT-isolated
(Platform Guardian §4) so an evaluation write can never corrupt the surrounding transaction.
The block is engineering-only and is never surfaced on a user-facing response.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select

from app.storage.models import Investigation

logger = logging.getLogger("omi.reasoning.shadow")

SHADOW_KEY = "shadow_evaluation_v1"


def cached_report(inv: Any) -> dict | None:
    entry = (inv.payload_json or {}).get(SHADOW_KEY)
    return entry if isinstance(entry, dict) and entry.get("comparison") else None


def persist_report(session: Any, inv: Any, report: dict) -> dict:
    """Cache a shadow report on the investigation row. Best-effort + SAVEPOINT-isolated."""
    entry = {**report, "stored_at": datetime.now(timezone.utc).isoformat()}
    try:
        with session.begin_nested():
            inv.payload_json = {**(inv.payload_json or {}), SHADOW_KEY: entry}
            session.add(inv)
    except Exception:  # noqa: BLE001 — persistence is best-effort, never breaks the caller
        logger.exception("failed to persist shadow report for inv=%s", getattr(inv, "slug", "?"))
    return entry


def all_reports(session: Any) -> list[dict]:
    """Every persisted shadow report across investigations — the corpus the stats endpoint
    aggregates."""
    invs = session.execute(select(Investigation)).scalars().all()
    out: list[dict] = []
    for inv in invs:
        entry = (inv.payload_json or {}).get(SHADOW_KEY)
        if isinstance(entry, dict) and entry.get("comparison"):
            out.append(entry)
    return out
