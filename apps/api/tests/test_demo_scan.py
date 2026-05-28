"""Tests for the anonymous demo scan endpoint."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.routes.scan import set_client_factory_for_tests
from tests.test_coordination import (
    FakeYouTubeClient,
    _channel_profile,
    _make_human_history,
)


VID = "aaaaaaaaaaa"   # 11-char valid format


def _fake_client_with_n_commenters(n: int) -> FakeYouTubeClient:
    items = []
    for i in range(n):
        items.append({
            "snippet": {
                "topLevelComment": {
                    "id": f"c{i}",
                    "snippet": {
                        "authorChannelId": {"value": f"UC_u_{i}"},
                        "authorDisplayName": f"user_{i}",
                        "authorProfileImageUrl": f"https://x/{i}",
                        "textDisplay": f"comment number {i}",
                        "publishedAt": f"2025-05-01T12:{i:02d}:00Z",
                    },
                },
            },
        })
    return FakeYouTubeClient(
        video_pages={VID: [{"items": items}]},
        channel_profiles={
            f"UC_u_{i}": _channel_profile(
                f"UC_u_{i}", title=f"u{i}", sub_count=100,
                created_at="2020-01-01T00:00:00Z",
            )
            for i in range(n)
        },
        channel_history={f"UC_u_{i}": _make_human_history(f"UC_u_{i}") for i in range(n)},
    )


@pytest.fixture
def client():
    fake = _fake_client_with_n_commenters(15)
    set_client_factory_for_tests(lambda: fake)
    app = create_app()
    yield TestClient(app)
    set_client_factory_for_tests(None)


def test_demo_scan_returns_200_for_first_request_per_ip(client):
    resp = client.post(
        "/v1/scan/demo",
        json={"url": f"https://www.youtube.com/watch?v={VID}"},
        headers={"x-forwarded-for": "10.0.0.1"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["overall_tier"] in ("low", "moderate", "elevated", "high")
    # Demo caps at 10 commenters regardless of how many are available
    assert body["video"]["commenter_count"] <= 10


def test_demo_scan_rate_limits_second_call_from_same_ip(client):
    headers = {"x-forwarded-for": "10.0.0.2"}
    r1 = client.post("/v1/scan/demo", json={"url": f"https://www.youtube.com/watch?v={VID}"}, headers=headers)
    assert r1.status_code == 200
    r2 = client.post("/v1/scan/demo", json={"url": f"https://www.youtube.com/watch?v={VID}"}, headers=headers)
    assert r2.status_code == 429
    # Error mentions signup so the UI can detect and surface the upgrade CTA.
    assert "sign up" in r2.json()["detail"].lower()


def test_demo_scan_different_ips_are_independent(client):
    r1 = client.post(
        "/v1/scan/demo",
        json={"url": f"https://www.youtube.com/watch?v={VID}"},
        headers={"x-forwarded-for": "10.0.0.3"},
    )
    r2 = client.post(
        "/v1/scan/demo",
        json={"url": f"https://www.youtube.com/watch?v={VID}"},
        headers={"x-forwarded-for": "10.0.0.4"},
    )
    assert r1.status_code == 200
    assert r2.status_code == 200


def test_demo_scan_rejects_non_video_urls(client):
    resp = client.post(
        "/v1/scan/demo",
        json={"url": "https://youtube.com/@somechannel"},
        headers={"x-forwarded-for": "10.0.0.5"},
    )
    assert resp.status_code == 400
    assert "video" in resp.json()["detail"].lower()


def test_demo_scan_rejects_missing_url(client):
    resp = client.post(
        "/v1/scan/demo",
        json={},
        headers={"x-forwarded-for": "10.0.0.6"},
    )
    assert resp.status_code == 400


def test_demo_scan_does_not_require_auth(client):
    """Sanity check — no Authorization header, no cookie, should still work."""
    resp = client.post(
        "/v1/scan/demo",
        json={"url": f"https://www.youtube.com/watch?v={VID}"},
        headers={"x-forwarded-for": "10.0.0.7"},
    )
    assert resp.status_code == 200


def test_demo_scan_failed_attempt_does_not_consume_the_daily_quota(client):
    """If the demo scan fails (e.g., bad URL), the rate-limit row is logged
    with success=0 — but the rate-limit check only counts success=1 rows,
    so a user can retry with a valid URL."""
    headers = {"x-forwarded-for": "10.0.0.8"}
    r1 = client.post("/v1/scan/demo", json={"url": "not a url"}, headers=headers)
    assert r1.status_code == 400
    # Should still be able to run a real demo
    r2 = client.post(
        "/v1/scan/demo",
        json={"url": f"https://www.youtube.com/watch?v={VID}"},
        headers=headers,
    )
    assert r2.status_code == 200
