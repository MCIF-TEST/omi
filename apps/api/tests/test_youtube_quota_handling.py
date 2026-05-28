"""End-to-end test: when YouTube returns a quota-exceeded error mid-scan,
the user gets a clean 503 with Retry-After AND the credit they spent is
refunded. This is the contract: we never charge for a failed scan.

Also exercises the credit-refund helper and the /v1/status quota meter.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.core.auth import refund_credits
from app.core.config import get_settings
from app.main import app
from app.routes.scan import set_client_factory_for_tests
from app.storage.db import get_session, reset_db_for_tests
from app.storage.models import ScanLog, User, VideoScan


# ---------------------------------------------------------------------------
# Helpers — fake YouTube client that raises an HttpError-like exception
# ---------------------------------------------------------------------------


class _FakeResp:
    def __init__(self, status: int):
        self.status = status


class _FakeHttpError(Exception):
    """Quacks like googleapiclient.errors.HttpError."""

    def __init__(self, status: int, body: dict):
        super().__init__("FakeHttpError")
        self.resp = _FakeResp(status)
        self.content = json.dumps(body).encode("utf-8")


def _quota_exhausted_body() -> dict:
    return {
        "error": {
            "code": 403,
            "message": "The request cannot be completed because you have exceeded your quota.",
            "errors": [{
                "reason": "quotaExceeded",
                "message": "The request cannot be completed because you have exceeded your quota.",
            }],
        },
    }


class _DeadCommentThreads:
    """Every API call instantly raises a quota-exceeded HttpError."""

    def list(self, **_params):
        class _DeadRequest:
            def execute(self):
                raise _FakeHttpError(403, _quota_exhausted_body())
        return _DeadRequest()


class _DeadChannels:
    """Every API call instantly raises a quota-exceeded HttpError."""

    def list(self, **_params):
        class _DeadRequest:
            def execute(self):
                raise _FakeHttpError(403, _quota_exhausted_body())
        return _DeadRequest()


class QuotaExhaustedClient:
    def commentThreads(self):
        return _DeadCommentThreads()

    def channels(self):
        return _DeadChannels()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def auth_client(monkeypatch):
    """A TestClient with auth enabled and a real session cookie."""
    monkeypatch.setenv("OMI_REQUIRE_AUTH", "true")
    monkeypatch.setenv("OMI_SESSION_SECRET", "x" * 64)
    monkeypatch.setenv("OMI_YOUTUBE_API_KEY", "test-key")
    get_settings.cache_clear()
    reset_db_for_tests("sqlite:///:memory:")
    # The signup limiter is process-global. Reset it so back-to-back tests
    # in this file can each sign up without tripping the 5-per-hour cap.
    from app.core.rate_limit import SIGNUP_LIMITER, LOGIN_LIMITER
    SIGNUP_LIMITER._windows.clear()
    LOGIN_LIMITER._windows.clear()
    with TestClient(app) as tc:
        # Sign up + login
        tc.post("/v1/auth/signup", json={"email": "x@x.com", "password": "12345678"})
        yield tc
    set_client_factory_for_tests(None)
    reset_db_for_tests("sqlite:///:memory:")
    get_settings.cache_clear()


# ---------------------------------------------------------------------------
# Route behaviour under quota exhaustion
# ---------------------------------------------------------------------------


def test_quota_exhausted_returns_503_with_retry_after(auth_client):
    set_client_factory_for_tests(lambda: QuotaExhaustedClient())

    # Snapshot the starting credit balance.
    me = auth_client.get("/v1/auth/me").json()
    starting_credits = me["credits_remaining"]
    assert starting_credits > 0, "Free-trial credits must be granted on signup"

    r = auth_client.post(
        "/v1/scan/youtube/video",
        json={"video_url_or_id": "abcdefghijk", "max_commenters": 5},
    )

    assert r.status_code == 503
    assert "Retry-After" in r.headers
    body = r.json()
    assert "quota" in body["detail"].lower() or "rate-limited" in body["detail"].lower()
    assert "credit has been refunded" in body["detail"]


def test_quota_exhausted_refunds_the_credit(auth_client):
    set_client_factory_for_tests(lambda: QuotaExhaustedClient())

    starting = auth_client.get("/v1/auth/me").json()["credits_remaining"]
    auth_client.post(
        "/v1/scan/youtube/video",
        json={"video_url_or_id": "abcdefghijk", "max_commenters": 5},
    )
    ending = auth_client.get("/v1/auth/me").json()["credits_remaining"]

    assert ending == starting, (
        f"Credit must be refunded after a quota failure "
        f"(was {starting}, now {ending})"
    )


def test_quota_failure_marks_scanlog_as_failed(auth_client):
    set_client_factory_for_tests(lambda: QuotaExhaustedClient())

    auth_client.post(
        "/v1/scan/youtube/video",
        json={"video_url_or_id": "abcdefghijk", "max_commenters": 5},
    )

    with get_session() as session:
        rows = session.query(ScanLog).all()

    # Should have at least one row, all marked unsuccessful with a REFUND tag.
    assert len(rows) >= 1
    latest = max(rows, key=lambda r: r.id)
    assert latest.success == 0
    assert "REFUND" in (latest.target_input or "")


def test_account_scan_quota_failure_refunds(auth_client):
    """The /youtube/account endpoint must have the same refund behaviour
    as /youtube/video — same helper, same guarantee."""
    set_client_factory_for_tests(lambda: QuotaExhaustedClient())

    starting = auth_client.get("/v1/auth/me").json()["credits_remaining"]
    r = auth_client.post(
        "/v1/scan/youtube/account",
        json={"account_url_or_handle": "@somechannel"},
    )

    # 503 because resolve_channel_id raises quota immediately.
    assert r.status_code == 503
    assert "Retry-After" in r.headers
    ending = auth_client.get("/v1/auth/me").json()["credits_remaining"]
    assert ending == starting


# ---------------------------------------------------------------------------
# refund_credits helper, directly
# ---------------------------------------------------------------------------


def test_refund_credits_increments_balance(auth_client):
    # Set up a user with a known balance.
    with get_session() as session:
        u = session.query(User).first()
        starting = u.credits_remaining
        uid = u.id

    new_balance = refund_credits(uid, 2, reason="test")
    assert new_balance == starting + 2


def test_refund_credits_noop_when_auth_disabled(monkeypatch):
    monkeypatch.setenv("OMI_REQUIRE_AUTH", "false")
    get_settings.cache_clear()
    try:
        # No DB row needed; refund returns sentinel.
        assert refund_credits(123, 5, reason="test") == 999999
    finally:
        get_settings.cache_clear()


def test_refund_credits_handles_missing_user(auth_client):
    # A user_id that doesn't exist must not crash.
    assert refund_credits(99999, 1, reason="test") == 0


def test_refund_credits_zero_is_a_noop(auth_client):
    with get_session() as session:
        u = session.query(User).first()
        starting = u.credits_remaining
        uid = u.id

    new_balance = refund_credits(uid, 0, reason="test")
    # 0 credits → no-op; balance unchanged.
    assert new_balance == 999999  # the require_auth-off sentinel path? No — let me re-read.
    # Actually the helper returns 999999 immediately when credits <= 0.
    with get_session() as session:
        u = session.query(User).filter(User.id == uid).first()
        assert u.credits_remaining == starting


# ---------------------------------------------------------------------------
# /v1/status quota reporting
# ---------------------------------------------------------------------------


def test_status_reports_zero_quota_when_no_scans(auth_client):
    r = auth_client.get("/v1/status").json()
    assert r["youtube_quota_used_today"] == 0
    assert r["youtube_quota_daily_limit"] == 10000


def test_status_aggregates_quota_from_recent_video_scans(auth_client):
    # Plant a few VideoScan rows in the last 24h.
    with get_session() as session:
        session.add(VideoScan(
            platform="youtube", video_id="aaaa", quota_used=12,
            scanned_at=datetime.now(timezone.utc) - timedelta(hours=1),
        ))
        session.add(VideoScan(
            platform="youtube", video_id="bbbb", quota_used=8,
            scanned_at=datetime.now(timezone.utc) - timedelta(hours=2),
        ))
        # One row OUTSIDE the 24h window — must NOT count.
        session.add(VideoScan(
            platform="youtube", video_id="cccc", quota_used=500,
            scanned_at=datetime.now(timezone.utc) - timedelta(hours=30),
        ))

    # /v1/status is cached for 5s; bust it by hitting a fresh path.
    from app.core.cache import get_cache
    get_cache().invalidate("v1.status")

    r = auth_client.get("/v1/status").json()
    assert r["youtube_quota_used_today"] == 20  # 12 + 8, not 520
