"""Unified /scan/link Twitter/X flow.

Proves Twitter rides the SAME pipeline as YouTube via the Source layer (T0):
classify -> TwitterSource -> scan_comprehensive -> shared engine -> persisted
investigation. No parallel system. The Twitter client is a tiny Protocol, so a
fake serves canned JSON (no network / no API key needed).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.integrations.source import classify_link
from app.integrations.twitter import fetch_tweet_engagers
from app.main import app
from app.routes.scan import set_twitter_client_factory_for_tests
from app.storage.db import get_session
from app.storage.models import User


class FakeTwitterScanClient:
    """Serves user/info (echoes the requested handle), tweet/replies (3 distinct
    repliers), and last_tweets (account history)."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def get(self, path: str, params: dict) -> dict:
        self.calls.append((path, dict(params)))
        if "user/info" in path:
            uname = params.get("userName") or "user"
            return {"data": {"user": {
                "userName": uname, "name": uname.title(),
                "followers": 100, "following": 50,
                "createdAt": "Mon Jan 15 00:00:00 +0000 2018",
            }}}
        if "tweet/replies" in path:
            return {"has_next_page": False, "data": {"tweets": [
                {"id": "r1", "text": "great tweet!! so true", "createdAt": "2024-03-01T12:00:00Z",
                 "author": {"userName": "replier_a", "profilePicture": "u"}},
                {"id": "r2", "text": "great tweet!! so true", "createdAt": "2024-03-01T12:00:30Z",
                 "author": {"userName": "replier_b"}},
                {"id": "r3", "text": "agree, link in bio", "createdAt": "2024-03-01T12:01:00Z",
                 "author": {"userName": "replier_c"}},
            ]}}
        # last_tweets (per-account history)
        return {"has_next_page": False, "data": {"tweets": [
            {"id": "t1", "text": "a normal tweet about my day", "createdAt": "2024-02-01T00:00:00Z"},
        ]}}


@pytest.fixture
def authed(monkeypatch):
    monkeypatch.setenv("OMI_REQUIRE_AUTH", "true")
    monkeypatch.setenv("OMI_SESSION_SECRET", "x" * 64)
    monkeypatch.setenv("OMI_TWITTER_API_KEY", "test-key")
    get_settings.cache_clear()
    from app.core.rate_limit import LOGIN_LIMITER, SIGNUP_LIMITER
    SIGNUP_LIMITER._windows.clear()
    LOGIN_LIMITER._windows.clear()
    set_twitter_client_factory_for_tests(lambda: FakeTwitterScanClient())
    with TestClient(app) as tc:
        tc.post("/v1/auth/signup", json={"email": "twl@x.com", "password": "tw-password-123"})
        with get_session() as s:
            from sqlalchemy import select
            u = s.execute(select(User).where(User.email == "twl@x.com")).scalar_one()
            u.credits_remaining = 50
        yield tc
    set_twitter_client_factory_for_tests(None)
    get_settings.cache_clear()


# --- classification + replies fetch shape ---

def test_classify_link_tweet_url():
    info = classify_link("https://x.com/jack/status/123456789")
    assert info["platform"] == "x" and info["kind"] == "tweet"
    assert info["tweet_id"] == "123456789" and info["handle"] == "jack"


def test_fetch_tweet_engagers_shape():
    commenters, comments, _cursor = fetch_tweet_engagers(
        FakeTwitterScanClient(), "123", max_commenters=10
    )
    assert {c["handle"] for c in commenters} == {"replier_a", "replier_b", "replier_c"}
    assert all(c["channel_id"] == c["handle"] for c in commenters)  # handle is the id
    assert len(comments) == 3
    assert all(set(c) >= {"comment_id", "author_external_id", "text", "created_at"} for c in comments)


# --- unified /scan/link, the user-facing entry ---

def test_scan_link_twitter_profile_persists_investigation(authed):
    r = authed.post("/v1/scan/link", json={"url": "https://x.com/someprofile"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("investigation_slug", "").startswith("inv_")
    assert body.get("focus_account") is not None
    assert body["focus_account"]["handle"] == "someprofile"
    # Persisted through the SAME investigation flow as YouTube — resolves now.
    slug = body["investigation_slug"]
    detail = authed.get(f"/v1/investigations/{slug}")
    assert detail.status_code == 200
    assert detail.json()["payload"]


def test_scan_link_twitter_tweet_scans_repliers(authed):
    r = authed.post(
        "/v1/scan/link",
        json={"url": "https://x.com/author/status/1788888888888", "max_commenters": 10},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("investigation_slug", "").startswith("inv_")
    assert body.get("video") is not None, "a tweet scan must produce a repliers batch"
    assert body["video"]["commenter_count"] >= 1


def test_scan_link_rejects_unknown_link(authed):
    r = authed.post("/v1/scan/link", json={"url": "https://example.com/foo"})
    assert r.status_code == 400
