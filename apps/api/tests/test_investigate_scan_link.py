"""The authenticated /v1/scan/link path the Investigate workspace calls.

This is the only place that stamps an ``investigation_slug`` onto the
comprehensive result and offloads persistence to the background pool. It was
the source of the "scan reaches the last step then shows no result" bug:
persistence used to block the response, and the slug stamping round-tripped
the whole 200KB+ payload through model_dump() + model_validate(). These tests
pin the contract: the response carries the slug, and the investigation lands
in the database via the background worker.
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
        tc.post("/v1/auth/signup", json={"email": "inv@t.com", "password": "password12345"})
        yield tc
    set_client_factory_for_tests(None)
    reset_db_for_tests("sqlite:///:memory:")
    get_settings.cache_clear()


def test_scan_link_stamps_slug_and_returns_result(auth_client):
    r = auth_client.post(
        "/v1/scan/link",
        json={"url": f"https://www.youtube.com/watch?v={VID}", "max_commenters": 8},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    # The marquee fields the UI needs to render a result — their absence is
    # exactly the "no result shown" symptom.
    assert body.get("investigation_slug", "").startswith("inv_")
    assert body["overall_tier"] in ("low", "moderate", "elevated", "high")
    assert body["video"]["commenter_count"] == 8


def test_scan_link_persists_investigation_via_background(auth_client):
    r = auth_client.post(
        "/v1/scan/link",
        json={"url": f"https://www.youtube.com/watch?v={VID}", "max_commenters": 6},
    )
    slug = r.json()["investigation_slug"]

    # The `with TestClient(app)` lifespan drains background tasks on exit, but
    # we want to assert persistence within the test — drain explicitly.
    from app.core import background
    background.shutdown(wait_seconds=10.0)

    listing = auth_client.get("/v1/investigations").json()["investigations"]
    assert any(i["slug"] == slug for i in listing), listing
