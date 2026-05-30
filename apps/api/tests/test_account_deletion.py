"""Account deletion — the data-subject right promised in the Privacy Policy.

Deleting an account hard-removes the user's personal rows (graphs,
investigations, watchlists, scan logs) and anonymizes the rows we keep
(labels), then logs them out. Requires a matching email confirmation.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app
from app.storage.db import get_session, reset_db_for_tests
from app.storage.models import Investigation, User, UserGraph


@pytest.fixture
def auth_client(monkeypatch):
    monkeypatch.setenv("OMI_REQUIRE_AUTH", "true")
    monkeypatch.setenv("OMI_SESSION_SECRET", "x" * 64)
    get_settings.cache_clear()
    reset_db_for_tests("sqlite:///:memory:")
    from app.core.rate_limit import SIGNUP_LIMITER, LOGIN_LIMITER
    SIGNUP_LIMITER._windows.clear()
    LOGIN_LIMITER._windows.clear()
    with TestClient(app) as tc:
        tc.post("/v1/auth/signup", json={"email": "del@x.com", "password": "password123"})
        yield tc
    reset_db_for_tests("sqlite:///:memory:")
    get_settings.cache_clear()


def _uid(email="del@x.com") -> int:
    with get_session() as s:
        return s.query(User).filter(User.email == email).first().id


def test_delete_removes_user_and_owned_rows(auth_client):
    uid = _uid()
    # Give the account a graph + an investigation row to prove cascade-delete.
    auth_client.post("/v1/graphs", json={"name": "doomed", "platform": "youtube"})
    with get_session() as s:
        s.add(Investigation(
            user_id=uid, slug="inv_del_1", label="x", input_url="u",
            kind="comprehensive", overall_tier="low",
        ))
        s.commit()

    r = auth_client.request(
        "DELETE", "/v1/auth/account", json={"confirm_email": "del@x.com"}
    )
    assert r.status_code == 200, r.text

    with get_session() as s:
        assert s.query(User).filter(User.id == uid).first() is None
        assert s.query(UserGraph).filter(UserGraph.user_id == uid).count() == 0
        assert s.query(Investigation).filter(Investigation.user_id == uid).count() == 0


def test_delete_logs_user_out(auth_client):
    auth_client.request("DELETE", "/v1/auth/account", json={"confirm_email": "del@x.com"})
    # Session cleared → /me returns null.
    me = auth_client.get("/v1/auth/me")
    assert me.status_code == 200
    assert me.json() is None


def test_delete_requires_matching_email(auth_client):
    r = auth_client.request(
        "DELETE", "/v1/auth/account", json={"confirm_email": "wrong@x.com"}
    )
    assert r.status_code == 400
    # Account still exists.
    assert _uid() is not None


def test_delete_requires_auth(monkeypatch):
    monkeypatch.setenv("OMI_REQUIRE_AUTH", "true")
    monkeypatch.setenv("OMI_SESSION_SECRET", "x" * 64)
    get_settings.cache_clear()
    reset_db_for_tests("sqlite:///:memory:")
    with TestClient(app) as tc:
        r = tc.request("DELETE", "/v1/auth/account", json={"confirm_email": "anyone@x.com"})
        assert r.status_code == 401
    reset_db_for_tests("sqlite:///:memory:")
    get_settings.cache_clear()


def test_referrer_deletion_nulls_referee_backref(auth_client):
    """Deleting a referrer must not delete the people they referred — only
    null the back-reference."""
    referrer_uid = _uid()
    with get_session() as s:
        referrer = s.get(User, referrer_uid)
        code = referrer.referral_code
    # Second user signs up referred by the first.
    auth_client.cookies.clear()
    auth_client.post(
        "/v1/auth/signup",
        json={"email": "referee@x.com", "password": "password123", "referral_code": code},
    )
    auth_client.cookies.clear()
    # Log back in as the referrer and delete.
    auth_client.post("/v1/auth/login", json={"email": "del@x.com", "password": "password123"})
    auth_client.request("DELETE", "/v1/auth/account", json={"confirm_email": "del@x.com"})

    with get_session() as s:
        referee = s.query(User).filter(User.email == "referee@x.com").first()
        assert referee is not None  # survived
        assert referee.referred_by_user_id is None  # back-ref nulled
