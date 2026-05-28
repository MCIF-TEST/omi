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


@router.post("/test-alert")
def send_test_alert(
    current: CurrentUser = Depends(require_user),
) -> dict:
    """Send a self-targeted test alert through whichever channels are
    configured for the current admin. Returns the delivery status of each
    channel so the operator can see exactly which side of the SMTP /
    webhook config is working.

    Doesn't persist anything to the alerts table — it builds a synthetic
    Alert object in memory, runs it through the same _send_email /
    _send_webhook helpers production uses, and reports the verdict.
    """
    if not current.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Admin only.")

    from datetime import datetime, timezone
    from app.core.config import get_settings
    from app.notifications import delivery as _delivery
    from app.storage.models import User as UserModel

    settings = get_settings()

    with get_session() as session:
        user = session.get(UserModel, current.id)
        if user is None:
            raise HTTPException(status_code=404, detail="User not found.")

        # Synthesize a minimal Alert (not persisted) so we can run the
        # same payload builders production uses.
        fake_alert = Alert(
            id=-1,  # marker so the email subject says "[TEST]"
            user_id=user.id,
            kind="test",
            severity="moderate",
            message=(
                "OMISPHERE — alert delivery test. This is a manual delivery "
                "test triggered from /v1/monitoring/test-alert. If you can "
                "read this, the channel that delivered it is working."
            ),
            payload_json={"diagnostic": True},
            created_at=datetime.now(timezone.utc),
        )

        email_status: dict = {"requested": False}
        if user.notify_alerts_email:
            email_status["requested"] = True
            ok, err = _delivery._send_email(settings, user, fake_alert, None)
            email_status["delivered"] = ok
            email_status["error"] = err
            email_status["smtp_host"] = settings.smtp_host or None
        else:
            email_status["reason"] = "notify_alerts_email is False for this user"

        webhook_status: dict = {"requested": False}
        if user.notify_alerts_webhook:
            webhook_status["requested"] = True
            if not user.webhook_url:
                webhook_status["delivered"] = False
                webhook_status["error"] = "no webhook_url set on user"
            else:
                ok, err = _delivery._send_webhook(
                    settings, user.webhook_url, fake_alert, None,
                )
                webhook_status["delivered"] = ok
                webhook_status["error"] = err
                webhook_status["url"] = user.webhook_url
        else:
            webhook_status["reason"] = "notify_alerts_webhook is False for this user"

        return {
            "user_email": user.email,
            "email": email_status,
            "webhook": webhook_status,
            "smtp_configured": bool(settings.smtp_host),
        }
