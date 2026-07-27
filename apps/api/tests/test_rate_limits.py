"""Rate limiting: the budgets that protect upstream spend and the ones that must not fire.

Two failure modes matter here and they pull in opposite directions:

* **Too loose** on `/v1/scan/link/commenters`. Compile requires auth but charges NO credits and calls
  the real X / YouTube API (X bills per post read), so credits cannot guard it — there is nothing to
  spend. Without a per-user ceiling an account looping "load all" over large posts spends our upstream
  budget for free.
* **Too tight** globally. One active investigation polls the analyst every few seconds for up to ~9
  minutes on top of monitoring polls and navigation, and everyone behind one office / VPN / mobile-NAT
  IP shares a single key. A limit sized for scrapers turns into an outage for paying customers, and it
  looks like the product is broken rather than like a limit.

Scope note asserted below: these limiters are in-process, so each budget is per instance. That is a
deliberate documented trade-off, not an oversight — cost is guarded by credits and by the demo's
DB-backed per-IP reservations, both of which are correct across instances.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import app.routes.scan_async as scan_async
from app.core.config import get_settings
from app.core.rate_limit import SlidingWindowLimiter, enforce, user_key
from app.main import app, create_app
from app.storage.db import reset_db_for_tests

_URL = "https://x.com/someone/status/t1"


@pytest.fixture(autouse=True)
def _fresh(monkeypatch):
    monkeypatch.setenv("OMI_REQUIRE_AUTH", "false")  # local mode: no auth plumbing needed
    get_settings.cache_clear()
    reset_db_for_tests()
    monkeypatch.setattr(
        scan_async, "classify_link",
        lambda url: {"platform": "x", "kind": "tweet", "tweet_id": "t1"},
    )
    yield
    get_settings.cache_clear()


def _authed_client(monkeypatch, **env):
    """A TestClient signed in as a REAL non-admin user.

    The per-user limits deliberately exempt admins (they already skip credit consumption), and local
    mode's synthetic user is `is_admin=True` — so a local-mode client can never exercise these limits.
    Signing up an ordinary account is the only way to test the path production actually runs.
    """
    monkeypatch.setenv("OMI_REQUIRE_AUTH", "true")
    monkeypatch.setenv("OMI_SESSION_SECRET", "x" * 64)
    monkeypatch.setenv("OMI_SUPER_ADMIN_EMAILS", "")  # ensure our user is NOT an admin
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    get_settings.cache_clear()
    reset_db_for_tests()
    scan_async.reset_scan_limiters_for_tests()

    tc = TestClient(app)
    tc.__enter__()
    r = tc.post("/v1/auth/signup", json={"email": "rl@t.com", "password": "password12345"})
    assert r.status_code == 200, f"test setup failed to create a user: {r.text}"
    assert r.json()["is_admin"] is False, "this user must be non-admin for the limit to apply"
    return tc


class _FakeSource:
    """Counts upstream calls, so a test can prove the limiter actually prevented spend."""

    def __init__(self):
        self.calls = 0

    def fetch_content_engagers(self, content_id, *, max_commenters, max_comments, start_page_token=None):
        self.calls += 1
        return ([{"channel_id": "u1", "handle": "alice"}],
                [{"author_external_id": "u1", "text": "hi",
                  "created_at": "2026-01-01T00:00:00+00:00"}],
                "cursor-next")

    def fetch_content_title(self, content_id):
        return "a post"


# --------------------------------------------------------------------------- #
# The limiter primitive
# --------------------------------------------------------------------------- #
def test_remaining_reports_budget_without_consuming_it():
    lim = SlidingWindowLimiter(max_hits=3, per_seconds=60)
    assert lim.remaining("k") == 3
    assert lim.remaining("k") == 3, "remaining() must be read-only"
    lim.hit("k")
    assert lim.remaining("k") == 2


def test_enforce_raises_429_with_backoff_headers():
    lim = SlidingWindowLimiter(max_hits=1, per_seconds=60)
    enforce(lim, "k", what="test")  # first is allowed

    from fastapi import HTTPException

    with pytest.raises(HTTPException) as ei:
        enforce(lim, "k", what="test")
    exc = ei.value
    assert exc.status_code == 429
    # A client can only back off correctly if we tell it how long to wait.
    assert exc.headers["Retry-After"]
    assert exc.headers["X-RateLimit-Limit"] == "1"
    assert exc.headers["X-RateLimit-Remaining"] == "0"


def test_user_key_prefers_the_authenticated_user_over_ip():
    """Per-user keying is what stops one office NAT from sharing a single budget."""
    assert user_key(42) == "u:42"
    # id 0 is local mode's placeholder, not a real identity, so it must not become one shared bucket.
    assert user_key(0).startswith("ip:")
    assert user_key(None).startswith("ip:")


# --------------------------------------------------------------------------- #
# The free compile step — the endpoint with no credit guard
# --------------------------------------------------------------------------- #
def test_compile_is_capped_per_user_and_stops_upstream_calls(monkeypatch):
    fake = _FakeSource()
    monkeypatch.setattr(scan_async, "_source_for_platform", lambda platform, settings: fake)
    tc = _authed_client(monkeypatch, OMI_RATE_LIMIT_COMPILE_MAX="3")
    try:
        codes = [
            tc.post("/v1/scan/link/commenters", json={"url": _URL, "fetch": 25}).status_code
            for _ in range(6)
        ]
    finally:
        tc.__exit__(None, None, None)

    assert codes[:3] == [200, 200, 200], f"the first 3 should be allowed, got {codes}"
    assert codes[3:] == [429, 429, 429], f"the rest should be refused, got {codes}"
    assert fake.calls == 3, (
        f"the limiter must refuse BEFORE the upstream fetch — got {fake.calls} paid calls for "
        f"6 requests, so a refused request still spent money"
    )


def test_a_refused_compile_tells_the_client_when_to_retry(monkeypatch):
    monkeypatch.setattr(scan_async, "_source_for_platform", lambda platform, settings: _FakeSource())
    tc = _authed_client(monkeypatch, OMI_RATE_LIMIT_COMPILE_MAX="1")
    try:
        assert tc.post("/v1/scan/link/commenters", json={"url": _URL}).status_code == 200
        r = tc.post("/v1/scan/link/commenters", json={"url": _URL})
    finally:
        tc.__exit__(None, None, None)

    assert r.status_code == 429
    assert r.headers.get("Retry-After"), "a 429 without Retry-After leaves clients guessing"
    assert "commenter-list" in r.json()["detail"], "the message should name what was limited"


def test_a_malformed_url_does_not_spend_the_budget(monkeypatch):
    """Validation first: a typo must not cost the user part of their allowance."""
    monkeypatch.setattr(scan_async, "_source_for_platform", lambda platform, settings: _FakeSource())
    monkeypatch.setattr(scan_async, "classify_link",
                        lambda url: {"platform": "unknown", "kind": "unknown"})
    tc = _authed_client(monkeypatch, OMI_RATE_LIMIT_COMPILE_MAX="2")
    try:
        for _ in range(4):
            assert tc.post("/v1/scan/link/commenters", json={"url": "nonsense"}).status_code == 400
    finally:
        tc.__exit__(None, None, None)


def test_admins_and_local_mode_are_exempt(monkeypatch):
    """Deliberate escape hatch, pinned so it can't be removed or introduced by accident.

    Admins already skip credit consumption, and local mode's single-operator install runs as id=0 with
    is_admin=True. Both must stay unthrottled — but ONLY those, which is what the tests above verify
    for an ordinary account.
    """
    monkeypatch.setenv("OMI_RATE_LIMIT_COMPILE_MAX", "1")
    monkeypatch.setenv("OMI_REQUIRE_AUTH", "false")  # local mode -> id=0, is_admin=True
    get_settings.cache_clear()
    scan_async.reset_scan_limiters_for_tests()
    monkeypatch.setattr(scan_async, "_source_for_platform", lambda platform, settings: _FakeSource())

    with TestClient(app) as tc:
        codes = [
            tc.post("/v1/scan/link/commenters", json={"url": _URL}).status_code for _ in range(4)
        ]
    assert all(c == 200 for c in codes), f"local mode/admin must not be throttled, got {codes}"


# --------------------------------------------------------------------------- #
# The global ceiling — sized so real users never meet it
# --------------------------------------------------------------------------- #
def test_the_global_ip_limit_is_configurable_and_not_scraper_tight():
    """A single power user runs ~40 req/min (analyst polling + monitoring + navigation), and an office
    behind one NAT multiplies that. The default must leave room for several such users."""
    s = get_settings()
    assert s.rate_limit_global_max >= 300, (
        f"the global per-IP budget is {s.rate_limit_global_max}/"
        f"{int(s.rate_limit_global_window_seconds)}s; that is low enough to refuse a handful of "
        f"legitimate users sharing one NAT while an investigation is polling"
    )


def test_the_global_limit_advertises_remaining_budget(monkeypatch):
    """Clients can only pace themselves if the response says how much is left."""
    monkeypatch.setenv("OMI_RATE_LIMIT_GLOBAL_MAX", "50")
    get_settings.cache_clear()
    fresh = create_app()  # a fresh app so the middleware picks up the tightened budget
    with TestClient(fresh) as tc:
        r = tc.get("/v1/status")
    assert r.headers.get("X-RateLimit-Limit") == "50"
    assert int(r.headers["X-RateLimit-Remaining"]) < 50


def test_health_is_never_throttled(monkeypatch):
    """Render's load balancer polls /health; throttling it takes the service down."""
    monkeypatch.setenv("OMI_RATE_LIMIT_GLOBAL_MAX", "2")
    get_settings.cache_clear()
    fresh = create_app()
    with TestClient(fresh) as tc:
        codes = [tc.get("/health").status_code for _ in range(8)]
    assert all(c == 200 for c in codes), f"health checks were throttled: {codes}"
