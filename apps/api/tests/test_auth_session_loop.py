"""Stale-session self-healing — the backend half of the login↔dashboard redirect-loop fix.

Production failure: a browser holds a signed 30-day ``omi_session`` cookie, but the session no
longer resolves server-side (the sqlite user table was reset on an ephemeral-disk redeploy, or the
session secret was rotated). The web middleware used to bounce ``/login -> /dashboard`` on mere
cookie EXISTENCE while the app layout bounced ``/dashboard -> /login`` on failed VALIDATION —
an infinite 307 loop (``ERR_TOO_MANY_REDIRECTS``) that locked users out of the login form.

The frontend half of the fix (middleware bounces only toward /login; the login/signup pages
redirect only on a validated session) is verified in the browser. This file pins the backend
half: ``/v1/auth/me`` must CLEAR a presented-but-unresolvable cookie (self-heal) and must never
clear a valid one.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from itsdangerous import URLSafeTimedSerializer

from app.core.auth import SESSION_COOKIE_NAME
from app.core.config import get_settings
from app.main import app
from app.storage.db import get_session, reset_db_for_tests
from app.storage.models import User

SECRET = "x" * 64


@pytest.fixture
def auth_client(monkeypatch):
    monkeypatch.setenv("OMI_REQUIRE_AUTH", "true")
    monkeypatch.setenv("OMI_SESSION_SECRET", SECRET)
    get_settings.cache_clear()
    reset_db_for_tests("sqlite:///:memory:")
    from app.core.rate_limit import LOGIN_LIMITER, SIGNUP_LIMITER
    SIGNUP_LIMITER._windows.clear()
    LOGIN_LIMITER._windows.clear()
    with TestClient(app) as tc:
        yield tc
    reset_db_for_tests("sqlite:///:memory:")
    get_settings.cache_clear()


def _signup(tc: TestClient, email="loop@x.com") -> str:
    r = tc.post("/v1/auth/signup", json={"email": email, "password": "password123"})
    assert r.status_code == 200
    token = tc.cookies.get(SESSION_COOKIE_NAME)
    assert token
    return token


def _clears_cookie(response) -> bool:
    sc = response.headers.get("set-cookie", "")
    return SESSION_COOKIE_NAME in sc and ('Max-Age=0' in sc or 'max-age=0' in sc.lower())


def test_me_clears_cookie_when_user_row_is_gone(auth_client):
    """The ephemeral-disk redeploy scenario: cookie signed + unexpired, user table reset."""
    token = _signup(auth_client)
    with get_session() as s:
        s.query(User).delete()
    auth_client.cookies.set(SESSION_COOKIE_NAME, token)
    r = auth_client.get("/v1/auth/me")
    assert r.status_code == 200 and r.json() is None
    assert _clears_cookie(r), f"stale cookie must be cleared, got set-cookie={r.headers.get('set-cookie')!r}"


def test_me_clears_cookie_on_rotated_secret(auth_client):
    """The secret-rotation scenario: cookie signed by a PREVIOUS secret."""
    old = URLSafeTimedSerializer("previous-secret-" + "y" * 48, salt="omi-session-v1").dumps({"uid": 1})
    auth_client.cookies.set(SESSION_COOKIE_NAME, old)
    r = auth_client.get("/v1/auth/me")
    assert r.status_code == 200 and r.json() is None
    assert _clears_cookie(r)


def test_me_keeps_a_valid_session(auth_client):
    _signup(auth_client, email="ok@x.com")
    r = auth_client.get("/v1/auth/me")
    assert r.status_code == 200
    assert r.json()["email"] == "ok@x.com"
    assert not _clears_cookie(r)


def test_me_without_cookie_sets_nothing(auth_client):
    auth_client.cookies.clear()
    r = auth_client.get("/v1/auth/me")
    assert r.status_code == 200 and r.json() is None
    assert SESSION_COOKIE_NAME not in r.headers.get("set-cookie", "")


def test_relogin_replaces_the_stale_cookie(auth_client):
    """The full recovery: stale cookie -> /me null+clear -> login succeeds -> /me resolves."""
    token = _signup(auth_client, email="back@x.com")
    with get_session() as s:
        s.query(User).delete()
    auth_client.cookies.set(SESSION_COOKIE_NAME, token)
    assert auth_client.get("/v1/auth/me").json() is None
    # user signs up / logs in again on the recovered deployment
    r = auth_client.post("/v1/auth/signup", json={"email": "back@x.com", "password": "password123"})
    assert r.status_code == 200
    me = auth_client.get("/v1/auth/me")
    assert me.json() is not None and me.json()["email"] == "back@x.com"
