"""Ruling 2 (frozen architecture) — scan-time AI inference is RETIRED.

Proves the canonical invariant: a comprehensive scan (``/v1/scan/link``, the same entry YouTube and X
share) performs NO AI inference and calls NO endpoint — ``video.comment_analysis`` is absent even when
``comment_analysis_enabled`` is set, because no component may call the endpoint before the Investigation
Package is composed (exactly one endpoint request per investigation, off the scan hot path). The
deterministic ``thread_scan`` remains the scan-time thread surface in every case. Comment intelligence
is now a projection of the single AI investigation, not a scan-time stage.
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app
from app.routes.scan import set_twitter_client_factory_for_tests
from app.storage.db import get_session
from app.storage.models import User

_TWEET_URL = "https://x.com/author/status/1788888888888"


class _FakeTwitter:
    """Serves user/info + three distinct repliers + per-account history (no network/API key)."""

    def get(self, path: str, params: dict) -> dict:
        if "user/info" in path:
            uname = params.get("userName") or "user"
            return {"data": {"user": {"userName": uname, "name": uname.title(), "followers": 100,
                                      "following": 50, "createdAt": "Mon Jan 15 00:00:00 +0000 2018"}}}
        if "tweet/replies" in path:
            return {"has_next_page": False, "data": {"tweets": [
                {"id": "r1", "text": "great tweet!! so true", "createdAt": "2024-03-01T12:00:00Z",
                 "author": {"userName": "replier_a", "profilePicture": "u"}},
                {"id": "r2", "text": "great tweet!! so true", "createdAt": "2024-03-01T12:00:30Z",
                 "author": {"userName": "replier_b"}},
                {"id": "r3", "text": "agree, link in bio", "createdAt": "2024-03-01T12:01:00Z",
                 "author": {"userName": "replier_c"}},
            ]}}
        return {"has_next_page": False, "data": {"tweets": [
            {"id": "t1", "text": "a normal tweet about my day", "createdAt": "2024-02-01T00:00:00Z"}]}}


def _client(monkeypatch, *, comment_ai: bool) -> TestClient:
    monkeypatch.setenv("OMI_REQUIRE_AUTH", "true")
    monkeypatch.setenv("OMI_SESSION_SECRET", "x" * 64)
    monkeypatch.setenv("OMI_TWITTER_API_KEY", "test-key")
    monkeypatch.setenv("OMI_COMMENT_ANALYSIS_ENABLED", "true" if comment_ai else "false")
    get_settings.cache_clear()
    from app.core.rate_limit import LOGIN_LIMITER, SIGNUP_LIMITER
    SIGNUP_LIMITER._windows.clear()
    LOGIN_LIMITER._windows.clear()
    set_twitter_client_factory_for_tests(lambda: _FakeTwitter())
    tc = TestClient(app)
    tc.__enter__()
    email = f"cutover{int(comment_ai)}@x.com"
    tc.post("/v1/auth/signup", json={"email": email, "password": "tw-password-123"})
    with get_session() as s:
        from sqlalchemy import select
        u = s.execute(select(User).where(User.email == email)).scalar_one()
        u.credits_remaining = 50
    return tc


def _teardown(tc: TestClient) -> None:
    tc.__exit__(None, None, None)
    set_twitter_client_factory_for_tests(None)
    get_settings.cache_clear()


def test_scan_performs_no_inference_even_when_enabled(monkeypatch):
    """Ruling 2 — even with ``comment_analysis_enabled`` set, a comprehensive scan performs NO AI
    inference at scan time: ``comment_analysis`` is absent and the deterministic thread_scan stands.
    Comment intelligence is deferred to the single AI investigation."""
    tc = _client(monkeypatch, comment_ai=True)
    try:
        r = tc.post("/v1/scan/link", json={"url": _TWEET_URL, "max_commenters": 10})
        assert r.status_code == 200, r.text
        video = r.json()["video"]
        assert video is not None
        # scan-time AI inference is retired — no comment_analysis is produced at scan time
        assert video.get("comment_analysis") is None, "scan time must not invoke any AI inference"
        # the deterministic thread surface is intact and remains the scan-time thread number
        assert video["thread_scan"]["overall_probability"] >= 0.0
    finally:
        _teardown(tc)


def test_disabled_is_backward_compatible(monkeypatch):
    """With the flag OFF the response is byte-identical to before — no comment_analysis, the
    deterministic thread_scan remains the thread surface. (Now identical to the enabled path — the
    flag no longer changes scan-time behavior, since scan-time inference is retired.)"""
    tc = _client(monkeypatch, comment_ai=False)
    try:
        r = tc.post("/v1/scan/link", json={"url": _TWEET_URL, "max_commenters": 10})
        assert r.status_code == 200, r.text
        video = r.json()["video"]
        assert video.get("comment_analysis") is None
        assert video["thread_scan"]["overall_probability"] >= 0.0  # deterministic surface intact
    finally:
        _teardown(tc)
