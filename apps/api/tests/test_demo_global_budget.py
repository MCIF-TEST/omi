"""The free demo needs a site-wide spend ceiling, not just a per-visitor one.

``DEMO_FREE_SCANS_PER_IP = 1`` is a fairness control: it stops one visitor monopolising the demo. It is
not a spend control, because IPs rotate cheaply through VPNs and mobile carriers. Every free scan is a
real model call plus 25 upstream account fetches, so with per-IP alone the total cost of the free tier
is unbounded — and paid traffic is exactly the condition that makes abusing it worth someone's time.

The ceiling is a database count rather than an in-process counter, for the same reason the per-IP guard
uses reservations: it has to stay correct across instances and survive restarts. An in-memory counter
would reset on every deploy and multiply by the instance count, which is no ceiling at all.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import create_app
from app.routes.scan import set_twitter_client_factory_for_tests
from app.storage.db import get_session, reset_db_for_tests
from app.storage.models import DemoScanLog
from tests.fakes import FakeXScanClient

TWEET_URL = "https://x.com/someone/status/1790000000000000000"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("OMI_TWITTER_API_KEY", "test-key")
    monkeypatch.setenv("OMI_DEMO_GLOBAL_DAILY_MAX", "3")
    get_settings.cache_clear()
    reset_db_for_tests("sqlite:///:memory:")
    set_twitter_client_factory_for_tests(lambda: FakeXScanClient())
    app = create_app()
    with TestClient(app) as tc:
        yield tc
    set_twitter_client_factory_for_tests(None)
    reset_db_for_tests("sqlite:///:memory:")
    get_settings.cache_clear()


def _seed_scans(n: int, *, age_hours: float = 0.0) -> None:
    """Record n demo scans from unrelated IPs, as if by other visitors."""
    when = datetime.now(timezone.utc) - timedelta(hours=age_hours)
    with get_session() as s:
        for i in range(n):
            s.add(DemoScanLog(ip_hash=f"other_visitor_{i}", video_id="v", success=1,
                              user_agent_snippet="ua", created_at=when))
        s.flush()


def _compile(client, ip: str):
    return client.post("/v1/scan/demo/commenters", json={"url": TWEET_URL},
                       headers={"x-forwarded-for": ip})


def test_a_fresh_visitor_is_served_while_budget_remains(client):
    _seed_scans(1)
    assert _compile(client, "10.1.0.1").status_code == 200


def test_a_fresh_visitor_is_refused_once_the_global_budget_is_spent(client):
    """The core case: this IP has used nothing, but the site has no budget left."""
    _seed_scans(3)  # == OMI_DEMO_GLOBAL_DAILY_MAX
    r = _compile(client, "10.1.0.2")
    assert r.status_code == 429, f"expected 429, got {r.status_code}: {r.text[:200]}"
    body = r.json()["detail"].lower()
    assert "free" in body and ("account" in body or "tomorrow" in body), (
        f"the refusal should point at the way forward, got: {body!r}"
    )


def test_the_score_step_is_capped_too(client):
    """Both demo entry points spend money, so both must respect the ceiling."""
    listing = _compile(client, "10.1.0.3")
    assert listing.status_code == 200, listing.text
    ids = [c["external_id"] for c in listing.json()["commenters"]]

    _seed_scans(3)
    r = client.post("/v1/scan/demo/score", json={"url": TWEET_URL, "selected": ids},
                    headers={"x-forwarded-for": "10.1.0.3"})
    assert r.status_code == 429, f"expected the analyze step to be capped, got {r.status_code}"


def test_the_budget_is_a_rolling_window_not_a_permanent_cap(client):
    """Scans older than 24h must not count, or the demo dies permanently after one busy day."""
    _seed_scans(5, age_hours=30)
    assert _compile(client, "10.1.0.4").status_code == 200


def test_a_zero_limit_disables_the_cap(monkeypatch):
    """Operators need an escape hatch that is clearly off, not a magic large number."""
    monkeypatch.setenv("OMI_TWITTER_API_KEY", "test-key")
    monkeypatch.setenv("OMI_DEMO_GLOBAL_DAILY_MAX", "0")
    get_settings.cache_clear()
    reset_db_for_tests("sqlite:///:memory:")
    set_twitter_client_factory_for_tests(lambda: FakeXScanClient())
    try:
        _seed_scans(50)
        with TestClient(create_app()) as tc:
            assert _compile(tc, "10.1.0.6").status_code == 200
    finally:
        set_twitter_client_factory_for_tests(None)
        reset_db_for_tests("sqlite:///:memory:")
        get_settings.cache_clear()


def test_the_default_ceiling_is_set_and_finite():
    """A default of 0 would ship the unbounded behaviour this fix exists to remove."""
    get_settings.cache_clear()
    assert get_settings().demo_global_daily_max > 0, (
        "the free demo must ship with a finite daily ceiling; 0 means unbounded spend"
    )
