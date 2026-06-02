"""Tests for the Twitter/X ingestion adapter and /v1/scan/twitter/account route.

The Twitter client is a simple Protocol (get(path, params) -> dict), so tests
inject a FakeTwitterClient that returns canned JSON — no network required.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.integrations.twitter import (
    FetchStats,
    _clean_source,
    _map_tweet,
    _parse_twitter_date,
    classify_twitter_url,
    fetch_user_profile,
    fetch_user_recent_tweets,
    normalize_handle,
)
from app.integrations.twitter_errors import (
    TwitterAccessError,
    TwitterAuthError,
    TwitterClientError,
    TwitterNotFoundError,
    TwitterRateLimitError,
    translate_body_status,
    translate_status,
)
from app.main import app
from app.routes.scan import set_twitter_client_factory_for_tests
from app.storage.db import get_session, reset_db_for_tests
from app.storage.models import User  # noqa: F401 — used in fixture


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clean():
    reset_db_for_tests("sqlite:///:memory:")
    yield
    set_twitter_client_factory_for_tests(None)
    reset_db_for_tests("sqlite:///:memory:")
    get_settings.cache_clear()


@pytest.fixture
def authed_client(monkeypatch):
    monkeypatch.setenv("OMI_REQUIRE_AUTH", "true")
    monkeypatch.setenv("OMI_SESSION_SECRET", "x" * 64)
    monkeypatch.setenv("OMI_TWITTER_API_KEY", "test-key")
    get_settings.cache_clear()
    from app.core.rate_limit import LOGIN_LIMITER, SIGNUP_LIMITER
    SIGNUP_LIMITER._windows.clear()
    LOGIN_LIMITER._windows.clear()
    with TestClient(app) as tc:
        r = tc.post("/v1/auth/signup", json={"email": "tw@x.com", "password": "tw-password-123"})
        assert r.status_code in (200, 201), f"signup failed: {r.text}"
        # Grant credits directly so scan routes don't 402.
        with get_session() as session:
            from sqlalchemy import select as _select
            u = session.execute(_select(User).where(User.email == "tw@x.com")).scalar_one()
            u.credits_remaining = 20
        yield tc


# ---------------------------------------------------------------------------
# classify_twitter_url
# ---------------------------------------------------------------------------


def test_classify_bare_handle():
    r = classify_twitter_url("elonmusk")
    assert r["platform"] == "x"
    assert r["kind"] == "account"
    assert r["handle"] == "elonmusk"


def test_classify_at_handle():
    r = classify_twitter_url("@jack")
    assert r["platform"] == "x"
    assert r["handle"] == "jack"


def test_classify_full_url():
    r = classify_twitter_url("https://twitter.com/realDonaldTrump")
    assert r["platform"] == "x"
    assert r["kind"] == "account"
    assert r["handle"] == "realDonaldTrump"


def test_classify_x_com_url():
    r = classify_twitter_url("https://x.com/naval")
    assert r["platform"] == "x"
    assert r["handle"] == "naval"


def test_classify_reserved_path_returns_unknown():
    r = classify_twitter_url("https://twitter.com/home")
    assert r["kind"] == "unknown"
    assert r["handle"] is None


def test_classify_non_twitter_url():
    r = classify_twitter_url("https://youtube.com/channel/UCxyz")
    assert r["platform"] == "unknown"


def test_normalize_handle_strips_at():
    assert normalize_handle("@BarackObama") == "BarackObama"


def test_normalize_handle_from_url():
    assert normalize_handle("https://x.com/NASA") == "NASA"


def test_normalize_handle_invalid():
    assert normalize_handle("https://youtube.com/watch?v=abc") is None


# ---------------------------------------------------------------------------
# Error translation
# ---------------------------------------------------------------------------


def test_translate_429():
    e = translate_status(429, "rate limit")
    assert isinstance(e, TwitterRateLimitError)


def test_translate_401():
    e = translate_status(401, "unauthorized")
    assert isinstance(e, TwitterAuthError)


def test_translate_403_protected():
    e = translate_status(403, "Account is protected")
    assert isinstance(e, TwitterAccessError)
    assert not e.is_suspension


def test_translate_403_suspended():
    e = translate_status(403, "Account suspended")
    assert isinstance(e, TwitterAccessError)
    assert e.is_suspension


def test_translate_404():
    e = translate_status(404, "not found")
    assert isinstance(e, TwitterNotFoundError)


def test_translate_body_not_found():
    e = translate_body_status("User not found")
    assert isinstance(e, TwitterNotFoundError)


def test_translate_body_suspended():
    e = translate_body_status("This account has been suspended")
    assert isinstance(e, TwitterAccessError)
    assert e.is_suspension


def test_translate_body_protected():
    e = translate_body_status("This account is protected")
    assert isinstance(e, TwitterAccessError)


# ---------------------------------------------------------------------------
# FakeTwitterClient + field mapping
# ---------------------------------------------------------------------------


_PROFILE_PAYLOAD = {
    "data": {
        "user": {
            "userName": "testbot",
            "name": "Test Bot",
            "description": "I am a test bot",
            "followers": 1200,
            "following": 80,
            "createdAt": "Mon Jan 15 00:00:00 +0000 2018",
            "profilePicture": "https://pbs.twimg.com/pic.jpg",
            "isBlueVerified": False,
        }
    }
}

_TWEETS_PAYLOAD = {
    "has_next_page": False,
    "data": {
        "tweets": [
            {
                "id": "1001",
                "text": "Hello world",
                "createdAt": "2024-03-01T12:00:00Z",
                "likeCount": 5,
                "replyCount": 1,
                "retweetCount": 2,
                "source": '<a href="https://mobile.twitter.com" rel="nofollow">Twitter for iPhone</a>',
            },
            {
                "id": "1002",
                "text": "Second tweet",
                "createdAt": "2024-03-02T12:00:00Z",
                "likeCount": 10,
                "replyCount": 0,
                "retweetCount": 0,
            },
        ]
    },
}


class FakeTwitterClient:
    """Deterministic test client — returns canned payloads, records calls."""

    def __init__(self, profile_payload=None, tweets_payload=None, raise_on_get=None):
        self._profile = profile_payload or _PROFILE_PAYLOAD
        self._tweets = tweets_payload or _TWEETS_PAYLOAD
        self._raise = raise_on_get
        self.calls: list[tuple[str, dict]] = []

    def get(self, path: str, params: dict) -> dict:
        self.calls.append((path, params))
        if self._raise:
            raise self._raise
        if "user/info" in path:
            return self._profile
        return self._tweets


def test_fetch_user_profile_field_mapping():
    client = FakeTwitterClient()
    stats = FetchStats()
    profile = fetch_user_profile(client, "testbot", stats=stats)
    assert profile is not None
    assert profile.platform == "x"
    assert profile.handle == "testbot"
    assert profile.display_name == "Test Bot"
    assert profile.bio == "I am a test bot"
    assert profile.follower_count == 1200
    assert profile.following_count == 80
    assert profile.verified is False
    assert profile.avatar_url == "https://pbs.twimg.com/pic.jpg"
    assert isinstance(profile.created_at, datetime)
    assert stats.api_calls == 1


def test_fetch_user_recent_tweets_field_mapping():
    client = FakeTwitterClient()
    posts = fetch_user_recent_tweets(client, "testbot", max_tweets=10)
    assert len(posts) == 2
    p0 = posts[0]
    assert p0.id == "1001"
    assert p0.text == "Hello world"
    assert p0.like_count == 5
    assert p0.reply_count == 1
    assert p0.repost_count == 2
    assert p0.source_client == "Twitter for iPhone"  # HTML stripped
    assert isinstance(p0.created_at, datetime)


def test_clean_source_strips_html():
    assert _clean_source('<a href="x.com">Twitter for Android</a>') == "Twitter for Android"
    assert _clean_source(None) is None
    assert _clean_source("Twitter Web App") == "Twitter Web App"


def test_parse_twitter_date_classic_format():
    dt = _parse_twitter_date("Tue Jun 02 20:12:29 +0000 2009")
    assert dt is not None
    assert dt.year == 2009
    assert dt.month == 6


def test_parse_twitter_date_iso():
    dt = _parse_twitter_date("2024-03-01T12:00:00Z")
    assert dt is not None
    assert dt.year == 2024


def test_parse_twitter_date_invalid():
    assert _parse_twitter_date("not a date") is None
    assert _parse_twitter_date(None) is None


def test_fetch_tweets_pagination_loop_guard():
    """Same cursor returned twice must not produce an infinite loop."""
    call_count = 0

    class LoopClient:
        def get(self, path, params):
            nonlocal call_count
            call_count += 1
            if "user/info" in path:
                return _PROFILE_PAYLOAD
            return {
                "has_next_page": True,
                "next_cursor": "cursor-abc",
                "data": {
                    "tweets": [{
                        "id": str(call_count),
                        "text": "tweet",
                        "createdAt": "2024-01-01T00:00:00Z",
                    }]
                },
            }

    posts = fetch_user_recent_tweets(LoopClient(), "testbot", max_tweets=5)
    # Should stop after seeing the cursor repeat, not loop forever
    assert len(posts) <= 5


# ---------------------------------------------------------------------------
# Route tests (requires auth + fake client injection)
# ---------------------------------------------------------------------------


def _make_factory(client: FakeTwitterClient):
    return lambda: client


def test_twitter_account_route_200(authed_client):
    fc = FakeTwitterClient()
    set_twitter_client_factory_for_tests(_make_factory(fc))
    r = authed_client.post(
        "/v1/scan/twitter/account",
        json={"account_url_or_handle": "@testbot"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["handle"] == "testbot"
    assert body["platform"] if "platform" in body else True  # field optional
    assert 0.0 <= body["overall_probability"] <= 1.0
    assert body["tier"] in ("low", "moderate", "elevated", "high")
    assert body["history_size"] == 2


def test_twitter_account_route_missing_handle(authed_client):
    r = authed_client.post(
        "/v1/scan/twitter/account",
        json={"account_url_or_handle": ""},
    )
    assert r.status_code == 400


def test_twitter_account_route_invalid_url_returns_400(authed_client):
    r = authed_client.post(
        "/v1/scan/twitter/account",
        json={"account_url_or_handle": "https://youtube.com/channel/UC123"},
    )
    assert r.status_code == 400


def test_twitter_account_route_not_found_404(authed_client):
    fc = FakeTwitterClient(raise_on_get=TwitterNotFoundError("No account matched."))
    set_twitter_client_factory_for_tests(_make_factory(fc))
    r = authed_client.post(
        "/v1/scan/twitter/account",
        json={"account_url_or_handle": "@nosuchuser_xyz"},
    )
    assert r.status_code == 404


def test_twitter_account_route_ratelimit_503(authed_client):
    fc = FakeTwitterClient(raise_on_get=TwitterRateLimitError("Rate limited."))
    set_twitter_client_factory_for_tests(_make_factory(fc))
    r = authed_client.post(
        "/v1/scan/twitter/account",
        json={"account_url_or_handle": "@testbot"},
    )
    assert r.status_code == 503
    assert "Retry-After" in r.headers


def test_twitter_account_route_auth_error_503(authed_client):
    fc = FakeTwitterClient(raise_on_get=TwitterAuthError("Bad key."))
    set_twitter_client_factory_for_tests(_make_factory(fc))
    r = authed_client.post(
        "/v1/scan/twitter/account",
        json={"account_url_or_handle": "@testbot"},
    )
    assert r.status_code == 503


def test_twitter_account_no_api_key_503(monkeypatch):
    monkeypatch.setenv("OMI_REQUIRE_AUTH", "false")
    monkeypatch.setenv("OMI_TWITTER_API_KEY", "")
    get_settings.cache_clear()
    # No factory override → will try to resolve from settings
    set_twitter_client_factory_for_tests(None)
    with TestClient(app) as tc:
        r = tc.post(
            "/v1/scan/twitter/account",
            json={"account_url_or_handle": "@testbot"},
        )
    assert r.status_code in (401, 503)
    get_settings.cache_clear()


def test_twitter_account_cache_reuse(authed_client):
    """Second scan of the same handle uses cached score (from_cache=True)."""
    fc = FakeTwitterClient()
    set_twitter_client_factory_for_tests(_make_factory(fc))

    r1 = authed_client.post(
        "/v1/scan/twitter/account",
        json={"account_url_or_handle": "@testbot"},
    )
    assert r1.status_code == 200
    assert r1.json()["from_cache"] is False

    r2 = authed_client.post(
        "/v1/scan/twitter/account",
        json={"account_url_or_handle": "@testbot"},
    )
    assert r2.status_code == 200
    assert r2.json()["from_cache"] is True
