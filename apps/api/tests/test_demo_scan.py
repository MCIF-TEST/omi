"""Tests for the anonymous free X scan endpoint (/v1/scan/demo).

The free pre-login scan is X (Twitter) only, capped at 25 repliers, and allowed
ONCE per IP address for the lifetime of that IP (not per-day). No auth, no credits.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import create_app
from app.routes.scan import set_twitter_client_factory_for_tests


TWEET_URL = "https://x.com/someone/status/1790000000000000000"


class FakeXScanClient:
    """Serves user/info (echoes the handle), tweet/replies (N distinct repliers),
    and last_tweets (per-account history) — enough for a full comprehensive scan."""

    def __init__(self, n_repliers: int = 40) -> None:
        self.n = n_repliers
        self.calls: list[tuple[str, dict]] = []

    def get(self, path: str, params: dict) -> dict:
        self.calls.append((path, dict(params)))
        if "user/info" in path:
            uname = params.get("userName") or "user"
            return {"data": {"user": {
                "userName": uname, "name": uname.title(),
                "followers": 120, "following": 60,
                "createdAt": "Mon Jan 15 00:00:00 +0000 2018",
            }}}
        if "tweet/replies" in path:
            return {"has_next_page": False, "data": {"tweets": [
                {"id": f"r{i}", "text": f"reply number {i}",
                 "createdAt": f"2024-03-01T12:{i:02d}:00Z",
                 "author": {"userName": f"replier_{i}", "profilePicture": "u"}}
                for i in range(self.n)
            ]}}
        # last_tweets (per-account history)
        return {"has_next_page": False, "data": {"tweets": [
            {"id": "t1", "text": "a normal tweet about my day", "createdAt": "2024-02-01T00:00:00Z"},
        ]}}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("OMI_TWITTER_API_KEY", "test-key")
    get_settings.cache_clear()
    set_twitter_client_factory_for_tests(lambda: FakeXScanClient())
    app = create_app()
    yield TestClient(app)
    set_twitter_client_factory_for_tests(None)
    get_settings.cache_clear()


def test_free_scan_returns_200_for_first_request_per_ip(client):
    resp = client.post("/v1/scan/demo", json={"url": TWEET_URL},
                       headers={"x-forwarded-for": "10.0.0.1"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["overall_tier"] in ("low", "moderate", "elevated", "high")


def test_free_scan_caps_at_25_repliers(client):
    # 40 repliers available; the free scan must analyze at most 25.
    resp = client.post("/v1/scan/demo", json={"url": TWEET_URL},
                       headers={"x-forwarded-for": "10.0.0.20"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["video"]["commenter_count"] <= 25


def test_free_scan_is_once_per_ip_lifetime(client):
    headers = {"x-forwarded-for": "10.0.0.2"}
    r1 = client.post("/v1/scan/demo", json={"url": TWEET_URL}, headers=headers)
    assert r1.status_code == 200
    r2 = client.post("/v1/scan/demo", json={"url": TWEET_URL}, headers=headers)
    assert r2.status_code == 429
    # Error points at signup so the UI can surface the upgrade CTA.
    assert "account" in r2.json()["detail"].lower()


def test_free_scan_different_ips_are_independent(client):
    r1 = client.post("/v1/scan/demo", json={"url": TWEET_URL},
                     headers={"x-forwarded-for": "10.0.0.3"})
    r2 = client.post("/v1/scan/demo", json={"url": TWEET_URL},
                     headers={"x-forwarded-for": "10.0.0.4"})
    assert r1.status_code == 200 and r2.status_code == 200


def test_free_scan_rejects_youtube_urls(client):
    resp = client.post("/v1/scan/demo",
                       json={"url": "https://www.youtube.com/watch?v=jNQXAC9IVRw"},
                       headers={"x-forwarded-for": "10.0.0.5"})
    assert resp.status_code == 400
    assert "x (twitter)" in resp.json()["detail"].lower()


def test_free_scan_rejects_an_x_profile_url_not_a_post(client):
    resp = client.post("/v1/scan/demo", json={"url": "https://x.com/someone"},
                       headers={"x-forwarded-for": "10.0.0.9"})
    assert resp.status_code == 400


def test_free_scan_rejects_missing_url(client):
    resp = client.post("/v1/scan/demo", json={}, headers={"x-forwarded-for": "10.0.0.6"})
    assert resp.status_code == 400


def test_free_scan_does_not_require_auth(client):
    resp = client.post("/v1/scan/demo", json={"url": TWEET_URL},
                       headers={"x-forwarded-for": "10.0.0.7"})
    assert resp.status_code == 200


def test_a_failed_attempt_does_not_burn_the_one_free_scan(client):
    """A bad URL logs success=0; the once-per-IP check only counts success=1,
    so the visitor can still run their real free scan afterward."""
    headers = {"x-forwarded-for": "10.0.0.8"}
    r1 = client.post("/v1/scan/demo", json={"url": "not a url"}, headers=headers)
    assert r1.status_code == 400
    r2 = client.post("/v1/scan/demo", json={"url": TWEET_URL}, headers=headers)
    assert r2.status_code == 200
