"""Tests for the watchlist alert delivery system."""

from __future__ import annotations

import pytest
from datetime import datetime, timezone

from app.monitoring.service import MonitoringService
from app.notifications import delivery as nd
from app.storage.db import get_session
from app.storage.models import Alert, User, Watchlist


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_user(email: str = "alice@example.com", **kwargs) -> int:
    with get_session() as s:
        u = User(email=email, password_hash="x")
        for k, v in kwargs.items():
            setattr(u, k, v)
        s.add(u)
        s.flush()
        return u.id


def _make_watchlist(user_id: int, target_id: str = "UC_target") -> int:
    with get_session() as s:
        w = Watchlist(
            user_id=user_id, kind="channel",
            target_id=target_id, label="Test target",
            alert_threshold_tier="moderate",
        )
        s.add(w)
        s.flush()
        return w.id


@pytest.fixture(autouse=True)
def _clear_test_hooks():
    yield
    nd.set_email_sender_for_tests(None)
    nd.set_webhook_sender_for_tests(None)


# ---------------------------------------------------------------------------
# Email delivery
# ---------------------------------------------------------------------------


def test_email_delivery_routes_to_test_hook_when_enabled():
    received: list[dict] = []
    nd.set_email_sender_for_tests(lambda p: received.append(p))

    user_id = _make_user("bob@example.com", notify_alerts_email=1)
    wid = _make_watchlist(user_id)

    with get_session() as s:
        a = Alert(
            user_id=user_id, watchlist_id=wid,
            kind="tier_change", severity="high",
            message="Target moved LOW → HIGH (82%).",
            payload_json={"target_id": "UC_target", "previous_tier": "low", "current_tier": "high"},
        )
        s.add(a)
        s.flush()
        alert_id = a.id

    nd.deliver_alert(alert_id)

    assert len(received) == 1
    msg = received[0]
    assert msg["to"] == "bob@example.com"
    assert "[OMISPHERE]" in msg["subject"]
    assert "HIGH" in msg["subject"]
    assert "Test target" in msg["subject"]
    assert "Target moved LOW" in msg["text"]


def test_email_skipped_when_user_opts_out():
    received: list[dict] = []
    nd.set_email_sender_for_tests(lambda p: received.append(p))

    user_id = _make_user("optout@example.com", notify_alerts_email=0)
    wid = _make_watchlist(user_id)

    with get_session() as s:
        a = Alert(
            user_id=user_id, watchlist_id=wid,
            kind="tier_change", severity="moderate",
            message="anything", payload_json={},
        )
        s.add(a)
        s.flush()
        alert_id = a.id

    nd.deliver_alert(alert_id)

    assert len(received) == 0
    # Alert is still marked delivered (with 'no_channels_configured') so we
    # don't keep retrying.
    with get_session() as s:
        a = s.get(Alert, alert_id)
        assert a.delivered_at is not None
        assert a.delivery_status == "no_channels_configured"


# ---------------------------------------------------------------------------
# Webhook delivery
# ---------------------------------------------------------------------------


def test_webhook_delivery_posts_structured_payload():
    received: list[tuple[str, dict]] = []
    nd.set_webhook_sender_for_tests(lambda url, payload: received.append((url, payload)))

    user_id = _make_user(
        "wh@example.com",
        notify_alerts_email=0,
        notify_alerts_webhook=1,
        webhook_url="https://example.com/omi-hook",
    )
    wid = _make_watchlist(user_id)

    with get_session() as s:
        a = Alert(
            user_id=user_id, watchlist_id=wid,
            kind="tier_change", severity="elevated",
            message="Tier elevated.",
            payload_json={"target_id": "UC_target", "current_tier": "elevated"},
        )
        s.add(a)
        s.flush()
        alert_id = a.id

    nd.deliver_alert(alert_id)

    assert len(received) == 1
    url, payload = received[0]
    assert url == "https://example.com/omi-hook"
    assert payload["version"] == "1"
    assert payload["kind"] == "tier_change"
    assert payload["severity"] == "elevated"
    assert payload["watchlist"]["target_id"] == "UC_target"
    assert payload["watchlist"]["kind"] == "channel"


def test_webhook_failure_recorded_on_alert():
    """A webhook that raises gets logged as the delivery_error so operators
    can see what's wrong."""
    def boom(url, payload):
        raise RuntimeError("connection refused")
    nd.set_webhook_sender_for_tests(boom)

    user_id = _make_user(
        "fail@example.com",
        notify_alerts_email=0,
        notify_alerts_webhook=1,
        webhook_url="https://broken.example.com/",
    )
    wid = _make_watchlist(user_id)

    with get_session() as s:
        a = Alert(
            user_id=user_id, watchlist_id=wid,
            kind="tier_change", severity="moderate",
            message="something", payload_json={"target_id": "UC_target"},
        )
        s.add(a)
        s.flush()
        alert_id = a.id

    nd.deliver_alert(alert_id)

    with get_session() as s:
        a = s.get(Alert, alert_id)
        assert a.delivered_at is not None
        assert "webhook:fail" in (a.delivery_status or "")
        assert "connection refused" in (a.delivery_error or "")


# ---------------------------------------------------------------------------
# Pending alert sweeper
# ---------------------------------------------------------------------------


def test_deliver_pending_alerts_picks_up_undelivered_only():
    received: list[dict] = []
    nd.set_email_sender_for_tests(lambda p: received.append(p))

    user_id = _make_user("sweep@example.com", notify_alerts_email=1)
    wid = _make_watchlist(user_id)

    now = datetime.now(timezone.utc)
    with get_session() as s:
        # Already-delivered alert — should be skipped
        s.add(Alert(
            user_id=user_id, watchlist_id=wid,
            kind="tier_change", severity="info",
            message="old", payload_json={},
            delivered_at=now,
        ))
        # Two fresh undelivered
        s.add(Alert(
            user_id=user_id, watchlist_id=wid,
            kind="tier_change", severity="high",
            message="new1", payload_json={},
        ))
        s.add(Alert(
            user_id=user_id, watchlist_id=wid,
            kind="tier_change", severity="moderate",
            message="new2", payload_json={},
        ))

    count = nd.deliver_pending_alerts()
    assert count == 2
    assert len(received) == 2
    subjects = {r["subject"] for r in received}
    assert any("HIGH" in s for s in subjects)
    assert any("MODERATE" in s for s in subjects)


def test_broadcast_alert_is_marked_delivered_without_sending():
    """Alerts with user_id=None are global anomalies (e.g., narrative_spike).
    They have no per-user preferences, so they should just be marked
    delivered with a 'broadcast_no_delivery' status."""
    received: list[dict] = []
    nd.set_email_sender_for_tests(lambda p: received.append(p))

    with get_session() as s:
        a = Alert(
            user_id=None, watchlist_id=None,
            kind="narrative_spike", severity="elevated",
            message="A narrative is spiking.", payload_json={"narrative_id": 42},
        )
        s.add(a)
        s.flush()
        aid = a.id

    nd.deliver_alert(aid)

    assert len(received) == 0
    with get_session() as s:
        a = s.get(Alert, aid)
        assert a.delivered_at is not None
        assert a.delivery_status == "broadcast_no_delivery"


def test_already_delivered_alert_is_not_redelivered():
    received: list[dict] = []
    nd.set_email_sender_for_tests(lambda p: received.append(p))

    user_id = _make_user("twice@example.com", notify_alerts_email=1)
    wid = _make_watchlist(user_id)

    with get_session() as s:
        a = Alert(
            user_id=user_id, watchlist_id=wid,
            kind="tier_change", severity="high",
            message="msg", payload_json={},
        )
        s.add(a); s.flush()
        alert_id = a.id

    nd.deliver_alert(alert_id)
    nd.deliver_alert(alert_id)   # second call

    assert len(received) == 1
