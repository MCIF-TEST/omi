"""Monitoring + alerts endpoints — Phase 8."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.auth import CurrentUser, require_user
from app.monitoring.service import MonitoringService
from app.schemas import AlertOut, AlertsResponse, FeedResponse
from app.storage.db import get_session
from app.storage.models import Alert


router = APIRouter(prefix="/v1/monitoring", tags=["monitoring"])


def _alert_to_out(a: Alert) -> AlertOut:
    return AlertOut(
        id=a.id,
        user_id=a.user_id,
        watchlist_id=a.watchlist_id,
        kind=a.kind,
        severity=a.severity,
        message=a.message,
        payload=a.payload_json or {},
        created_at=a.created_at,
        read_at=a.read_at,
    )


@router.get("/feed", response_model=FeedResponse)
def feed(
    hours: int = Query(24, ge=1, le=168),
    limit: int = Query(30, ge=1, le=100),
    current: CurrentUser = Depends(require_user),
) -> FeedResponse:
    """Recent global anomalies — visible to all authenticated users."""
    with get_session() as session:
        svc = MonitoringService(session)
        rows = svc.recent_feed(hours=hours, limit=limit)
        # Filter to global (user_id NULL) for the public-style feed
        items = [_alert_to_out(a) for a in rows if a.user_id is None]
        return FeedResponse(items=items)


@router.get("/alerts", response_model=AlertsResponse)
def alerts(
    unread: bool = Query(False),
    limit: int = Query(50, ge=1, le=200),
    current: CurrentUser = Depends(require_user),
) -> AlertsResponse:
    """User's alerts (personal + broadcast). Set ``unread=true`` for unread only."""
    with get_session() as session:
        svc = MonitoringService(session)
        rows = svc.user_alerts(current.id, unread_only=unread, limit=limit)
        unread_n = svc.unread_count(current.id)
        return AlertsResponse(
            alerts=[_alert_to_out(a) for a in rows],
            unread_count=unread_n,
        )


@router.post("/alerts/{alert_id}/read")
def mark_alert_read(
    alert_id: int,
    current: CurrentUser = Depends(require_user),
) -> dict:
    with get_session() as session:
        ok = MonitoringService(session).mark_read(alert_id, current.id)
        if not ok:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                                detail="Alert not found.")
    return {"ok": True}


@router.post("/run-pass")
def trigger_pass(
    current: CurrentUser = Depends(require_user),
) -> dict:
    """Admin-style trigger: run an anomaly pass on demand. Useful for the
    Render dashboard / cron job hook. Only an admin should call this in
    production; we gate by is_admin."""
    if not current.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Admin only.")
    from app.monitoring.scheduler import run_one_pass
    return run_one_pass()
