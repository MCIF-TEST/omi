"""POST /v1/monitoring/test-alert — admin-facing SMTP/webhook diagnostic.

Verifies the endpoint reports per-channel delivery status accurately,
including the case where the admin has email enabled but SMTP isn't
configured (the most common production gotcha — a Phase-8-claimed-done
feature that silently does nothing).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app
from app.storage.db import get_session, reset_db_for_tests
from app.storage.models import User


@pytest.fixture
def admin_client(monkeypatch):
    monkeypatch.setenv("OMI_REQUIRE_AUTH", "true")
    monkeypatch.setenv("OMI_SESSION_SECRET", "x" * 64)
    monkeypatch.setenv("OMI_YOUTUBE_API_KEY", "test-key")
    monkeypatch.setenv("OMI_SUPER_ADMIN_EMAILS", "admin@x.com")
    get_settings.cache_clear()
    reset_db_for_tests("sqlite:///:memory:")
    from app.core.rate_limit import SIGNUP_LIMITER, LOGIN_LIMITER
    SIGNUP_LIMITER._windows.clear()
    LOGIN_LIMITER._windows.clear()
    with TestClient(app) as tc:
        tc.post("/v1/auth/signup",
                json={"email": "admin@x.com", "password": "12345678"})
        yield tc
    reset_db_for_tests("sqlite:///:memory:")
    get_settings.cache_clear()


def test_test_alert_requires_admin(monkeypatch):
    monkeypatch.setenv("OMI_REQUIRE_AUTH", "true")
    monkeypatch.setenv("OMI_SESSION_SECRET", "x" * 64)
    monkeypatch.setenv("OMI_YOUTUBE_API_KEY", "test-key")
    get_settings.cache_clear()
    reset_db_for_tests("sqlite:///:memory:")
    from app.core.rate_limit import SIGNUP_LIMITER, LOGIN_LIMITER
    SIGNUP_LIMITER._windows.clear()
    LOGIN_LIMITER._windows.clear()
    with TestClient(app) as tc:
        tc.post("/v1/auth/signup",
                json={"email": "regular@x.com", "password": "12345678"})
        r = tc.post("/v1/monitoring/test-alert")
    assert r.status_code == 403
    reset_db_for_tests("sqlite:///:memory:")
    get_settings.cache_clear()


def test_test_alert_reports_smtp_off_when_not_configured(admin_client):
    """The common case: email enabled on the user, SMTP not configured on
    the service. The endpoint must say so clearly."""
    r = admin_client.post("/v1/monitoring/test-alert")
    assert r.status_code == 200
    body = r.json()
    assert body["smtp_configured"] is False
    # Email was requested (default notify_alerts_email=1 from the schema).
    assert body["email"]["requested"] is True
    assert body["email"]["delivered"] is False
    assert body["email"]["error"] == "smtp_not_configured"
    # No webhook URL set on the user by default.
    assert body["webhook"]["requested"] is False


def test_test_alert_reports_email_via_test_sender(admin_client):
    """When the test-time email sender is installed, the endpoint should
    report a successful delivery."""
    from app.notifications.delivery import set_email_sender_for_tests
    captured: list[dict] = []
    set_email_sender_for_tests(lambda payload: captured.append(payload))
    try:
        r = admin_client.post("/v1/monitoring/test-alert").json()
        assert r["email"]["delivered"] is True
        assert r["email"]["error"] is None
        # The synthetic alert went through the real payload builder.
        assert len(captured) == 1
        assert "OMISPHERE" in captured[0]["subject"]
        assert "delivery test" in captured[0]["text"].lower()
    finally:
        set_email_sender_for_tests(None)


def test_test_alert_reports_webhook_when_user_has_url(admin_client):
    """When the user has a webhook_url, the test endpoint runs through
    the webhook channel too."""
    from app.notifications.delivery import set_webhook_sender_for_tests
    delivered: list[tuple[str, dict]] = []
    set_webhook_sender_for_tests(lambda url, payload: delivered.append((url, payload)))
    # Toggle the user's webhook channel on.
    with get_session() as session:
        u = session.query(User).filter(User.email == "admin@x.com").first()
        u.notify_alerts_webhook = 1
        u.webhook_url = "https://hooks.example.com/test"
    try:
        r = admin_client.post("/v1/monitoring/test-alert").json()
        assert r["webhook"]["requested"] is True
        assert r["webhook"]["delivered"] is True
        assert delivered[0][0] == "https://hooks.example.com/test"
        assert delivered[0][1]["kind"] == "test"
    finally:
        set_webhook_sender_for_tests(None)
