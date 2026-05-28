"""Alert delivery — email + webhook.

Called from the background pool whenever a new Alert row is created. Both
channels are best-effort: a delivery failure is logged onto the Alert row
(via delivery_status + delivery_error) but never raised back to the caller.

Email goes through SMTP using stdlib smtplib so we don't need an extra
dependency. Webhook is a simple POST with a JSON payload. Both can be
mocked in tests via the module-level overrides set with set_*_for_tests.
"""

from __future__ import annotations

import json
import logging
import smtplib
from datetime import datetime, timezone
from email.message import EmailMessage
from typing import Callable
from urllib import error as urlerror, request as urlrequest

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.storage.db import get_session
from app.storage.models import Alert, User, Watchlist

_log = logging.getLogger("omi.notifications")

# Test hooks — assigned by tests to intercept delivery without real I/O.
_email_sender_for_tests: Callable[[dict], None] | None = None
_webhook_sender_for_tests: Callable[[str, dict], None] | None = None


def set_email_sender_for_tests(fn: Callable[[dict], None] | None) -> None:
    global _email_sender_for_tests
    _email_sender_for_tests = fn


def set_webhook_sender_for_tests(fn: Callable[[str, dict], None] | None) -> None:
    global _webhook_sender_for_tests
    _webhook_sender_for_tests = fn


# ---------------------------------------------------------------------------
# Public entry point — call from background pool
# ---------------------------------------------------------------------------


def deliver_pending_alerts(max_alerts: int = 50) -> int:
    """Find recently-created alerts that haven't been delivered yet and ship
    them. Idempotent + robust against commit timing — safe to call from a
    background trigger after any alert-creating operation.

    Returns the number of alerts processed.
    """
    from datetime import timedelta
    from sqlalchemy import select

    settings = get_settings()
    # Only look at recent alerts so we don't try to back-deliver ancient ones
    # if the workers were down for days.
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)

    try:
        with get_session() as session:
            ids = list(session.execute(
                select(Alert.id)
                .where(Alert.delivered_at.is_(None))
                .where(Alert.created_at >= cutoff)
                .order_by(Alert.created_at.desc())
                .limit(max_alerts)
            ).scalars().all())
    except Exception as e:  # noqa: BLE001
        _log.warning("deliver_pending_alerts: could not enumerate: %s", e)
        return 0

    processed = 0
    for aid in ids:
        try:
            deliver_alert(aid)
            processed += 1
        except Exception as e:  # noqa: BLE001
            _log.warning("deliver_pending_alerts: alert %s failed: %s", aid, e)
    return processed


def deliver_alert(alert_id: int) -> None:
    """Look up the alert + its user + watchlist preferences, deliver to the
    configured channels, mark delivered. Idempotent: an already-delivered
    alert is skipped.

    Run inside the background thread; opens its own DB session.
    """
    settings = get_settings()
    try:
        with get_session() as session:
            alert = session.get(Alert, alert_id)
            if alert is None:
                _log.warning("deliver_alert: no alert with id=%s", alert_id)
                return
            if alert.delivered_at is not None:
                return   # already delivered
            if alert.user_id is None:
                # Broadcast alert — no per-user preferences to consult.
                alert.delivered_at = datetime.now(timezone.utc)
                alert.delivery_status = "broadcast_no_delivery"
                session.commit()
                return

            user = session.get(User, alert.user_id)
            if user is None:
                _log.warning("deliver_alert: user %s missing for alert %s", alert.user_id, alert_id)
                return

            watchlist: Watchlist | None = (
                session.get(Watchlist, alert.watchlist_id) if alert.watchlist_id else None
            )

            channels: list[str] = []
            errors: list[str] = []

            if bool(user.notify_alerts_email):
                ok, err = _send_email(settings, user, alert, watchlist)
                channels.append(f"email:{'ok' if ok else 'fail'}")
                if err:
                    errors.append(f"email:{err}")

            if bool(user.notify_alerts_webhook) and user.webhook_url:
                ok, err = _send_webhook(settings, user.webhook_url, alert, watchlist)
                channels.append(f"webhook:{'ok' if ok else 'fail'}")
                if err:
                    errors.append(f"webhook:{err}")

            alert.delivered_at = datetime.now(timezone.utc)
            alert.delivery_status = ",".join(channels) if channels else "no_channels_configured"
            alert.delivery_error = "; ".join(errors)[:480] if errors else None
            session.commit()
            _log.info(
                "alert %s delivered: %s%s",
                alert_id,
                alert.delivery_status,
                f" (errors: {alert.delivery_error})" if alert.delivery_error else "",
            )
    except Exception as e:  # noqa: BLE001
        _log.exception("alert %s delivery crashed: %s", alert_id, e)


# ---------------------------------------------------------------------------
# Email
# ---------------------------------------------------------------------------


def _send_email(
    settings: Settings, user: User, alert: Alert, watchlist: Watchlist | None,
) -> tuple[bool, str | None]:
    payload = _build_email_payload(settings, user, alert, watchlist)

    if _email_sender_for_tests is not None:
        try:
            _email_sender_for_tests(payload)
            return True, None
        except Exception as e:  # noqa: BLE001
            return False, str(e)[:200]

    if not settings.smtp_host:
        # Email channel requested but no SMTP configured — soft-skip.
        return False, "smtp_not_configured"

    try:
        msg = EmailMessage()
        msg["Subject"] = payload["subject"]
        msg["From"] = payload["from"]
        msg["To"] = payload["to"]
        msg.set_content(payload["text"])

        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as s:
            if settings.smtp_use_tls:
                s.starttls()
            if settings.smtp_user and settings.smtp_password:
                s.login(settings.smtp_user, settings.smtp_password)
            s.send_message(msg)
        return True, None
    except Exception as e:  # noqa: BLE001
        return False, type(e).__name__ + ": " + str(e)[:160]


def _build_email_payload(
    settings: Settings, user: User, alert: Alert, watchlist: Watchlist | None,
) -> dict:
    subject = f"[OMISPHERE] {alert.severity.upper()} · {_short_kind(alert.kind)}"
    if watchlist and watchlist.label:
        subject += f" · {watchlist.label[:60]}"

    public_base = (settings.public_base_url or "").rstrip("/")
    permalink = ""
    target_id = (alert.payload_json or {}).get("target_id")
    if watchlist and target_id and watchlist.kind == "channel":
        permalink = f"{public_base}/accounts/{target_id}"
    elif (alert.payload_json or {}).get("narrative_id"):
        permalink = f"{public_base}/narratives/{(alert.payload_json or {}).get('narrative_id')}"

    text_lines = [
        f"OMISPHERE alert · {alert.severity.upper()}",
        "",
        alert.message,
        "",
    ]
    if watchlist:
        text_lines.append(f"Watchlist: {watchlist.label or watchlist.target_id} ({watchlist.kind})")
    text_lines.append(f"Triggered: {alert.created_at.isoformat() if alert.created_at else 'just now'}")
    if permalink:
        text_lines += ["", f"View in OMISPHERE: {permalink}"]
    text_lines += [
        "",
        "—",
        "You're receiving this because notifications are enabled on your OMISPHERE account.",
        f"Manage notifications: {public_base}/settings",
    ]

    return {
        "from": settings.smtp_from,
        "to": user.email,
        "subject": subject,
        "text": "\n".join(text_lines),
    }


# ---------------------------------------------------------------------------
# Webhook
# ---------------------------------------------------------------------------


def _send_webhook(
    settings: Settings, url: str, alert: Alert, watchlist: Watchlist | None,
) -> tuple[bool, str | None]:
    payload = _build_webhook_payload(alert, watchlist)

    if _webhook_sender_for_tests is not None:
        try:
            _webhook_sender_for_tests(url, payload)
            return True, None
        except Exception as e:  # noqa: BLE001
            return False, str(e)[:200]

    try:
        body = json.dumps(payload).encode("utf-8")
        req = urlrequest.Request(
            url,
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "User-Agent": "OMISPHERE-Webhook/1.0",
            },
        )
        with urlrequest.urlopen(req, timeout=settings.alert_webhook_timeout_seconds) as resp:
            status = getattr(resp, "status", 200)
            if status >= 400:
                return False, f"http_{status}"
        return True, None
    except urlerror.HTTPError as e:
        return False, f"http_{e.code}"
    except urlerror.URLError as e:
        return False, f"url_error: {str(e.reason)[:120]}"
    except Exception as e:  # noqa: BLE001
        return False, type(e).__name__ + ": " + str(e)[:120]


def _build_webhook_payload(alert: Alert, watchlist: Watchlist | None) -> dict:
    return {
        "version": "1",
        "alert_id": alert.id,
        "kind": alert.kind,
        "severity": alert.severity,
        "message": alert.message,
        "payload": alert.payload_json or {},
        "created_at": alert.created_at.isoformat() if alert.created_at else None,
        "watchlist": {
            "id": watchlist.id,
            "kind": watchlist.kind,
            "target_id": watchlist.target_id,
            "label": watchlist.label,
        } if watchlist else None,
    }


def _short_kind(kind: str) -> str:
    return {
        "tier_change": "Tier change",
        "narrative_spike": "Narrative spike",
        "high_tier_surge": "High-tier surge",
    }.get(kind, kind.replace("_", " ").title())
