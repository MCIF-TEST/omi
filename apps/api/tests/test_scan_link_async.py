"""The async link-scan job path the Investigate workspace + re-scan button use.

``POST /v1/scan/link/start`` runs the whole comprehensive scan on the
background pool and hands back a job id + investigation slug immediately;
``GET /v1/scan/link/status/{job_id}`` is polled to completion. This moves the
scan off the request thread so a slow scan can't trip an upstream proxy timeout
(the "reaches the last step then shows no result" failure). These tests pin the
contract: immediate job + slug, the worker persists the investigation, and a
failed scan is fully refunded.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app
from app.routes.scan import set_client_factory_for_tests
from app.storage.db import reset_db_for_tests
from tests.test_demo_scan import _fake_client_with_n_commenters, VID


@pytest.fixture
def auth_client(monkeypatch):
    monkeypatch.setenv("OMI_REQUIRE_AUTH", "true")
    monkeypatch.setenv("OMI_SESSION_SECRET", "x" * 64)
    monkeypatch.setenv("OMI_FREE_TRIAL_CREDITS", "5")
    get_settings.cache_clear()
    reset_db_for_tests("sqlite:///:memory:")
    from app.core.rate_limit import SIGNUP_LIMITER, LOGIN_LIMITER
    SIGNUP_LIMITER._windows.clear()
    LOGIN_LIMITER._windows.clear()
    set_client_factory_for_tests(lambda: _fake_client_with_n_commenters(12))
    with TestClient(app) as tc:
        tc.post("/v1/auth/signup", json={"email": "async@t.com", "password": "password12345"})
        yield tc
    set_client_factory_for_tests(None)
    reset_db_for_tests("sqlite:///:memory:")
    get_settings.cache_clear()


def test_scan_link_start_returns_job_and_slug_immediately(auth_client):
    r = auth_client.post(
        "/v1/scan/link/start",
        json={"url": f"https://www.youtube.com/watch?v={VID}", "max_commenters": 8},
    )
    assert r.status_code == 202, r.text
    body = r.json()
    # The client needs the job id (to poll) and the slug (to load the result)
    # the instant the scan is accepted — before any work has happened.
    assert body["job_id"].startswith("link_")
    assert body["investigation_slug"].startswith("inv_")
    assert body["status"] == "queued"
    assert body["platform"] == "youtube"


def test_scan_link_async_completes_and_persists(auth_client):
    start = auth_client.post(
        "/v1/scan/link/start",
        json={"url": f"https://www.youtube.com/watch?v={VID}", "max_commenters": 8},
    ).json()
    job_id, slug = start["job_id"], start["investigation_slug"]

    # Drain the background pool so the worker runs to completion.
    from app.core import background
    background.shutdown(wait_seconds=15.0)

    status = auth_client.get(f"/v1/scan/link/status/{job_id}")
    assert status.status_code == 200, status.text
    sbody = status.json()
    assert sbody["status"] == "done", sbody
    assert sbody["investigation_slug"] == slug
    assert sbody["tier"] in ("low", "moderate", "elevated", "high")

    # The investigation the slug points at must actually exist + be renderable.
    detail = auth_client.get(f"/v1/investigations/{slug}")
    assert detail.status_code == 200, detail.text
    assert detail.json()["payload"]["video"]["commenter_count"] == 8

    listing = auth_client.get("/v1/investigations").json()["investigations"]
    assert any(i["slug"] == slug for i in listing), listing


def test_scan_link_start_rejects_unknown_link(auth_client):
    r = auth_client.post(
        "/v1/scan/link/start",
        json={"url": "https://example.com/not-a-social-link", "max_commenters": 8},
    )
    assert r.status_code == 400, r.text


def test_scan_link_status_404_for_unknown_job(auth_client):
    r = auth_client.get("/v1/scan/link/status/link_does_not_exist")
    assert r.status_code == 404, r.text


def test_scan_link_async_refunds_credit_on_failure(auth_client):
    """A failed async scan must mark the job 'failed' AND refund the credit —
    the whole point of charging up front is that a failure costs nothing."""
    from app.core import background
    from app.integrations.youtube_errors import YouTubeQuotaExceededError

    class _BoomClient:
        def commentThreads(self):
            raise YouTubeQuotaExceededError("quota exceeded (test)")

        def channels(self):
            raise YouTubeQuotaExceededError("quota exceeded (test)")

    before = auth_client.get("/v1/auth/me").json()["credits_remaining"]
    set_client_factory_for_tests(lambda: _BoomClient())

    start = auth_client.post(
        "/v1/scan/link/start",
        json={"url": f"https://www.youtube.com/watch?v={VID}", "max_commenters": 8},
    )
    assert start.status_code == 202, start.text
    job_id = start.json()["job_id"]

    background.shutdown(wait_seconds=15.0)

    sbody = auth_client.get(f"/v1/scan/link/status/{job_id}").json()
    assert sbody["status"] == "failed", sbody
    assert sbody["error"]
    after = auth_client.get("/v1/auth/me").json()["credits_remaining"]
    assert after == before, f"credit not refunded: {before} -> {after}"
