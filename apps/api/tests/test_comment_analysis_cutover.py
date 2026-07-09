"""P3.1.6 — Comment Analysis production cutover (integration).

Proves the AI-native Comment Analysis stage EXECUTES in the real investigation path: a comprehensive
scan (``/v1/scan/link``, the same entry YouTube and X share) runs Comment Analysis through the AI
Investigation Runtime, and the response the frontend consumes carries the compatibility output at
``video.comment_analysis``. Enabled-gated + backward compatible: with the flag OFF the deterministic
``thread_scan`` is unchanged and ``comment_analysis`` is absent. The compat number ECHOES the engine's
deterministic thread number (never recomputed by the model).
"""
from __future__ import annotations

import pytest
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


def test_enabled_comprehensive_scan_invokes_comment_analysis(monkeypatch):
    """CRITICAL #1 + #2 — a real comprehensive investigation invokes Comment Analysis and its compat
    output reaches the response the frontend renders."""
    tc = _client(monkeypatch, comment_ai=True)
    try:
        r = tc.post("/v1/scan/link", json={"url": _TWEET_URL, "max_commenters": 10})
        assert r.status_code == 200, r.text
        video = r.json()["video"]
        assert video is not None
        ca = video.get("comment_analysis")
        assert ca is not None, "production comprehensive scan must invoke Comment Analysis when enabled"
        # exactly the compatibility output the UI consumes
        assert set(ca) >= {"overall_probability", "tier", "comment_count", "provider", "model_backed"}
        # the number ECHOES the deterministic engine thread number — never recomputed by the model
        assert ca["overall_probability"] == pytest.approx(video["thread_scan"]["overall_probability"])
        # no live endpoint in the test env -> deterministic Floor (still Governor-validated upstream)
        assert ca["model_backed"] is False and ca["provider"] == "deterministic-analyst-v1"
    finally:
        _teardown(tc)


def test_disabled_is_backward_compatible(monkeypatch):
    """With the flag OFF the response is byte-identical to before — no comment_analysis, the
    deterministic thread_scan remains the thread surface."""
    tc = _client(monkeypatch, comment_ai=False)
    try:
        r = tc.post("/v1/scan/link", json={"url": _TWEET_URL, "max_commenters": 10})
        assert r.status_code == 200, r.text
        video = r.json()["video"]
        assert video.get("comment_analysis") is None
        assert video["thread_scan"]["overall_probability"] >= 0.0  # deterministic surface intact
    finally:
        _teardown(tc)
