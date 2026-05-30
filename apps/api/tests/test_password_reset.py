"""Password reset flow — request a token by email, then set a new password.

Covers the happy path (reset → login with new password), single-use tokens,
expiry, anti-enumeration (same response for unknown emails), wrong-token
rejection, and that the reset email is actually dispatched with a link.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app
from app.notifications.delivery import set_email_sender_for_tests
from app.storage.db import reset_db_for_tests


@pytest.fixture
def captured_emails():
    sent: list[dict] = []
    set_email_sender_for_tests(lambda payload: sent.append(payload))
    yield sent
    set_email_sender_for_tests(None)


@pytest.fixture
def auth_client(monkeypatch, captured_emails):
    monkeypatch.setenv("OMI_REQUIRE_AUTH", "true")
    monkeypatch.setenv("OMI_SESSION_SECRET", "x" * 64)
    monkeypatch.setenv("OMI_PUBLIC_BASE_URL", "https://omisphere.test")
    get_settings.cache_clear()
    reset_db_for_tests("sqlite:///:memory:")
    from app.core.rate_limit import SIGNUP_LIMITER, LOGIN_LIMITER, RESET_LIMITER
    SIGNUP_LIMITER._windows.clear()
    LOGIN_LIMITER._windows.clear()
    RESET_LIMITER._windows.clear()
    with TestClient(app) as tc:
        tc.post("/v1/auth/signup", json={"email": "u@x.com", "password": "originalpass"})
        # Drop the session cookie so reset/login are tested in isolation.
        tc.cookies.clear()
        yield tc
    reset_db_for_tests("sqlite:///:memory:")
    get_settings.cache_clear()


def _request_reset_and_get_token(tc, captured_emails, email="u@x.com") -> str:
    r = tc.post("/v1/auth/forgot-password", json={"email": email})
    assert r.status_code == 200, r.text
    assert captured_emails, "expected a reset email to be dispatched"
    link = captured_emails[-1]["text"]
    # Extract the token from the reset link.
    marker = "token="
    idx = link.find(marker)
    assert idx != -1, f"no token in email: {link}"
    return link[idx + len(marker):].split()[0].strip()


def test_full_reset_flow_then_login(auth_client, captured_emails):
    token = _request_reset_and_get_token(auth_client, captured_emails)

    r = auth_client.post(
        "/v1/auth/reset-password", json={"token": token, "password": "brandnewpass"}
    )
    assert r.status_code == 200, r.text
    assert r.json()["email"] == "u@x.com"

    # Old password no longer works…
    auth_client.cookies.clear()
    bad = auth_client.post("/v1/auth/login", json={"email": "u@x.com", "password": "originalpass"})
    assert bad.status_code == 401
    # …new one does.
    good = auth_client.post("/v1/auth/login", json={"email": "u@x.com", "password": "brandnewpass"})
    assert good.status_code == 200, good.text


def test_reset_email_contains_public_base_link(auth_client, captured_emails):
    auth_client.post("/v1/auth/forgot-password", json={"email": "u@x.com"})
    assert captured_emails
    body = captured_emails[-1]["text"]
    assert "https://omisphere.test/reset-password?token=" in body
    assert captured_emails[-1]["subject"].startswith("[OMISPHERE]")


def test_token_is_single_use(auth_client, captured_emails):
    token = _request_reset_and_get_token(auth_client, captured_emails)
    first = auth_client.post(
        "/v1/auth/reset-password", json={"token": token, "password": "newpass123"}
    )
    assert first.status_code == 200
    auth_client.cookies.clear()
    second = auth_client.post(
        "/v1/auth/reset-password", json={"token": token, "password": "anotherpass"}
    )
    assert second.status_code == 400


def test_unknown_email_returns_generic_ok_and_sends_nothing(auth_client, captured_emails):
    r = auth_client.post("/v1/auth/forgot-password", json={"email": "nobody@x.com"})
    assert r.status_code == 200
    assert r.json()["ok"] is True
    # Anti-enumeration: no email dispatched for a non-existent account.
    assert captured_emails == []


def test_invalid_token_rejected(auth_client):
    r = auth_client.post(
        "/v1/auth/reset-password", json={"token": "not-a-real-token-xxxx", "password": "whatever12"}
    )
    assert r.status_code == 400


def test_expired_token_rejected(auth_client, captured_emails, monkeypatch):
    from datetime import datetime, timedelta, timezone
    from app.storage.db import get_session
    from app.storage.models import User

    token = _request_reset_and_get_token(auth_client, captured_emails)
    # Force the stored expiry into the past.
    with get_session() as session:
        u = session.query(User).filter(User.email == "u@x.com").first()
        u.reset_token_expires = datetime.now(timezone.utc) - timedelta(minutes=1)
        session.commit()

    r = auth_client.post(
        "/v1/auth/reset-password", json={"token": token, "password": "newpass123"}
    )
    assert r.status_code == 400
