"""Signup correctness + the edge cases that used to error.

Covers the auth-on path end to end: a clean signup logs in, a long passphrase
no longer 500s (bcrypt's 72-byte limit), duplicate / invalid emails return
friendly statuses, and a configured super-admin email is promoted on signup.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app
from app.storage.db import reset_db_for_tests


@pytest.fixture
def auth_client(monkeypatch):
    monkeypatch.setenv("OMI_REQUIRE_AUTH", "true")
    monkeypatch.setenv("OMI_SESSION_SECRET", "x" * 64)
    monkeypatch.setenv("OMI_FREE_TRIAL_CREDITS", "3")
    monkeypatch.setenv("OMI_SUPER_ADMIN_EMAILS", "boss@omi.app, Landon@Example.com")
    get_settings.cache_clear()
    reset_db_for_tests("sqlite:///:memory:")
    from app.core.rate_limit import SIGNUP_LIMITER, LOGIN_LIMITER
    SIGNUP_LIMITER._windows.clear()
    LOGIN_LIMITER._windows.clear()
    with TestClient(app) as tc:
        yield tc
    reset_db_for_tests("sqlite:///:memory:")
    get_settings.cache_clear()


def test_signup_then_login_roundtrip(auth_client):
    r = auth_client.post(
        "/v1/auth/signup", json={"email": "user@x.com", "password": "password123"}
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["email"] == "user@x.com"
    assert body["is_admin"] is False
    assert body["referral_code"]

    r2 = auth_client.post(
        "/v1/auth/login", json={"email": "user@x.com", "password": "password123"}
    )
    assert r2.status_code == 200, r2.text
    assert r2.json()["id"] == body["id"]


def test_long_passphrase_signup_and_login(auth_client):
    """A passphrase over bcrypt's 72-byte limit must not 500 on signup, and
    the same passphrase must still authenticate on login."""
    pw = "correct horse battery staple " * 5  # ~150 chars, well over 72 bytes
    r = auth_client.post(
        "/v1/auth/signup", json={"email": "long@x.com", "password": pw}
    )
    assert r.status_code == 200, r.text

    r2 = auth_client.post(
        "/v1/auth/login", json={"email": "long@x.com", "password": pw}
    )
    assert r2.status_code == 200, r2.text


def test_email_is_case_insensitive(auth_client):
    auth_client.post(
        "/v1/auth/signup", json={"email": "Mixed@Case.com", "password": "password123"}
    )
    # Same address, different casing — login should match the stored lowercase.
    r = auth_client.post(
        "/v1/auth/login", json={"email": "mixed@case.com", "password": "password123"}
    )
    assert r.status_code == 200, r.text


def test_duplicate_email_returns_409(auth_client):
    auth_client.post(
        "/v1/auth/signup", json={"email": "dup@x.com", "password": "password123"}
    )
    r = auth_client.post(
        "/v1/auth/signup", json={"email": "dup@x.com", "password": "password123"}
    )
    assert r.status_code == 409
    assert "already exists" in r.json()["detail"].lower()


def test_invalid_email_returns_400(auth_client):
    r = auth_client.post(
        "/v1/auth/signup", json={"email": "not-an-email", "password": "password123"}
    )
    assert r.status_code == 400
    assert "valid email" in r.json()["detail"].lower()


def test_wrong_password_returns_401(auth_client):
    auth_client.post(
        "/v1/auth/signup", json={"email": "pw@x.com", "password": "password123"}
    )
    r = auth_client.post(
        "/v1/auth/login", json={"email": "pw@x.com", "password": "wrongpassword"}
    )
    assert r.status_code == 401


def test_super_admin_email_is_promoted_on_signup(auth_client):
    """Configured super-admin emails (matched case-insensitively) get admin
    rights and unlimited credits — the path the cousin's email rides on."""
    r = auth_client.post(
        "/v1/auth/signup", json={"email": "landon@example.com", "password": "password123"}
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["is_admin"] is True
    assert body["credits_remaining"] >= 999999
