"""The daily ceiling on paid upstream API spend.

One route spends real money with no billing control behind it: the compile step
(``POST /v1/scan/link/commenters``) requires auth, charges no credits, and calls the X API, which
bills per read. Credits cannot guard it because there is nothing to spend, and its only ceiling was
an in-process 30/minute limiter that bounds a burst rather than a day, is per instance, resets on
every deploy, and recorded nothing at all. Thirty a minute sustained is roughly 43,000 provider calls
per user per day, and the first signal would have been the invoice.

What this file pins:

* the budget is checked BEFORE the upstream fetch, so a refusal costs nothing;
* every path that spends is recorded, including the demo and the paid scan, or the deployment total
  is not a total;
* recording can never break a request a customer is waiting on;
* admins, and a zeroed budget, are exempt.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.upstream_budget import (
    GLOBAL_SCOPE,
    USER_SCOPE,
    calls_today,
    enforce_daily_budget,
    record_calls,
    today_utc,
    usage_snapshot,
)
from app.main import app
from app.storage.db import get_session, reset_db_for_tests
from app.storage.models import UpstreamUsage, User


@pytest.fixture(autouse=True)
def _fresh(monkeypatch):
    monkeypatch.setenv("OMI_REQUIRE_AUTH", "true")
    monkeypatch.setenv("OMI_SESSION_SECRET", "x" * 64)
    get_settings.cache_clear()
    reset_db_for_tests()
    yield
    get_settings.cache_clear()


def _signup(tc: TestClient, email: str = "u@t.com") -> int:
    r = tc.post("/v1/auth/signup", json={"email": email, "password": "password12345"})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _make_admin(user_id: int) -> None:
    with get_session() as s:
        s.get(User, user_id).is_admin = 1


# --------------------------------------------------------------------------- #
# The ledger
# --------------------------------------------------------------------------- #
def test_a_call_is_charged_to_the_user_and_to_the_deployment():
    """Two rows, not one. The per-user row enforces fairness; the global row is the one that answers
    "is the API budget on fire right now", and it has no user to hang off."""
    with get_session() as s:
        record_calls(s, user_id=7, platform="x", api_calls=12)
        assert calls_today(s, scope=USER_SCOPE, scope_id="7") == 12
        assert calls_today(s, scope=GLOBAL_SCOPE) == 12


def test_repeat_calls_accumulate_into_one_row_per_day():
    with get_session() as s:
        for _ in range(5):
            record_calls(s, user_id=7, platform="x", api_calls=3)
        rows = s.query(UpstreamUsage).filter(
            UpstreamUsage.scope == USER_SCOPE, UpstreamUsage.scope_id == "7",
        ).all()
        assert len(rows) == 1, "a day should be one counter row, not an event log"
        assert rows[0].api_calls == 15
        assert rows[0].requests == 5, "requests counts our calls, api_calls counts the provider's"


def test_platforms_are_counted_separately():
    """They bill differently and are worth reading apart, but both roll into the same daily total."""
    with get_session() as s:
        record_calls(s, user_id=7, platform="x", api_calls=10)
        record_calls(s, user_id=7, platform="youtube", api_calls=4)
        assert calls_today(s, scope=USER_SCOPE, scope_id="7") == 14
        assert s.query(UpstreamUsage).filter(UpstreamUsage.scope == USER_SCOPE).count() == 2


def test_users_do_not_share_a_bucket():
    with get_session() as s:
        record_calls(s, user_id=1, platform="x", api_calls=100)
        record_calls(s, user_id=2, platform="x", api_calls=5)
        assert calls_today(s, scope=USER_SCOPE, scope_id="1") == 100
        assert calls_today(s, scope=USER_SCOPE, scope_id="2") == 5
        assert calls_today(s, scope=GLOBAL_SCOPE) == 105


def test_anonymous_calls_land_in_their_own_bucket_and_the_global_total():
    """The demo has no user. Its spend still has to reach the deployment total, or the number an
    operator reads leaves out the free front page, which is the highest-traffic surface there is."""
    with get_session() as s:
        record_calls(s, user_id=None, platform="x", api_calls=25)
        assert calls_today(s, scope=USER_SCOPE, scope_id="anon") == 25
        assert calls_today(s, scope=GLOBAL_SCOPE) == 25


def test_a_zero_call_fetch_records_nothing():
    """A cached compile makes no provider call. Writing a row for it would make `requests` lie about
    how much traffic actually reached the provider."""
    with get_session() as s:
        record_calls(s, user_id=7, platform="x", api_calls=0)
        assert s.query(UpstreamUsage).count() == 0


def test_recording_never_raises(monkeypatch):
    """Book-keeping running beside work a customer is waiting on. A ledger that can fail a scan is
    worse than a ledger with a gap in it."""
    import app.core.upstream_budget as ub

    def _boom(*a, **kw):
        raise RuntimeError("table is gone")

    monkeypatch.setattr(ub, "_bump", _boom)
    with get_session() as s:
        record_calls(s, user_id=7, platform="x", api_calls=5)  # must not raise


def test_a_recording_failure_reaches_the_error_tracker(monkeypatch):
    """Otherwise a persistent gap in the ledger is silent, and the ledger's whole job is visibility."""
    import app.core.observability as obs
    import app.core.upstream_budget as ub

    seen: list[BaseException] = []
    monkeypatch.setattr(obs, "capture_exception", seen.append)
    monkeypatch.setattr(ub, "_bump", lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("nope")))
    with get_session() as s:
        record_calls(s, user_id=7, platform="x", api_calls=5)
    assert len(seen) == 1 and isinstance(seen[0], RuntimeError)


# --------------------------------------------------------------------------- #
# The budget
# --------------------------------------------------------------------------- #
def test_under_budget_passes():
    with get_session() as s:
        record_calls(s, user_id=7, platform="x", api_calls=10)
        enforce_daily_budget(s, user_id=7, is_admin=False, what="test")  # no raise


def test_over_budget_is_refused_with_a_retry_after(monkeypatch):
    monkeypatch.setenv("OMI_UPSTREAM_DAILY_CALLS_PER_USER", "50")
    get_settings.cache_clear()
    from fastapi import HTTPException

    with get_session() as s:
        record_calls(s, user_id=7, platform="x", api_calls=50)
        with pytest.raises(HTTPException) as exc:
            enforce_daily_budget(s, user_id=7, is_admin=False, what="test")
    assert exc.value.status_code == 429
    assert "Retry-After" in (exc.value.headers or {})
    assert "midnight UTC" in exc.value.detail


def test_one_users_spend_does_not_refuse_another(monkeypatch):
    monkeypatch.setenv("OMI_UPSTREAM_DAILY_CALLS_PER_USER", "50")
    monkeypatch.setenv("OMI_UPSTREAM_DAILY_CALLS_GLOBAL", "0")
    get_settings.cache_clear()
    with get_session() as s:
        record_calls(s, user_id=1, platform="x", api_calls=500)
        enforce_daily_budget(s, user_id=2, is_admin=False, what="test")  # no raise


def test_admins_are_exempt(monkeypatch):
    """Matching how they skip credit consumption and every other limiter."""
    monkeypatch.setenv("OMI_UPSTREAM_DAILY_CALLS_PER_USER", "1")
    get_settings.cache_clear()
    with get_session() as s:
        record_calls(s, user_id=7, platform="x", api_calls=9999)
        enforce_daily_budget(s, user_id=7, is_admin=True, what="test")  # no raise


def test_a_zero_budget_disables_the_check(monkeypatch):
    """The escape hatch. An operator absorbing a spike must be able to turn this off without a deploy."""
    monkeypatch.setenv("OMI_UPSTREAM_DAILY_CALLS_PER_USER", "0")
    monkeypatch.setenv("OMI_UPSTREAM_DAILY_CALLS_GLOBAL", "0")
    get_settings.cache_clear()
    with get_session() as s:
        record_calls(s, user_id=7, platform="x", api_calls=10_000_000)
        enforce_daily_budget(s, user_id=7, is_admin=False, what="test")  # no raise


def test_the_deployment_ceiling_answers_503_not_429(monkeypatch):
    """A different status because it is a different fact. 429 tells the customer they did too much;
    when the whole deployment is out of budget, they did nothing wrong and the message says so."""
    monkeypatch.setenv("OMI_UPSTREAM_DAILY_CALLS_PER_USER", "0")
    monkeypatch.setenv("OMI_UPSTREAM_DAILY_CALLS_GLOBAL", "100")
    get_settings.cache_clear()
    from fastapi import HTTPException

    with get_session() as s:
        record_calls(s, user_id=1, platform="x", api_calls=100)
        with pytest.raises(HTTPException) as exc:
            enforce_daily_budget(s, user_id=2, is_admin=False, what="test")
    assert exc.value.status_code == 503
    assert "on us, not you" in exc.value.detail


def test_yesterdays_spend_does_not_count_against_today():
    """The budget is a day, not a rolling window. A row keyed on a different date is a different day."""
    with get_session() as s:
        s.add(UpstreamUsage(
            scope=USER_SCOPE, scope_id="7", usage_date="2000-01-01",
            platform="x", api_calls=999_999, requests=1,
        ))
        s.flush()
        assert calls_today(s, scope=USER_SCOPE, scope_id="7") == 0


# --------------------------------------------------------------------------- #
# The compile route: refuse BEFORE spending
# --------------------------------------------------------------------------- #
def test_compile_over_budget_is_refused_before_any_upstream_call(monkeypatch):
    """The property that makes the ceiling worth having: a refusal must not itself cost money.
    Mirrors test_compile_is_capped_per_user_and_stops_upstream_calls for the rate limiter."""
    monkeypatch.setenv("OMI_UPSTREAM_DAILY_CALLS_PER_USER", "10")
    get_settings.cache_clear()

    import app.routes.scan_async as sa

    calls: list[str] = []
    monkeypatch.setattr(
        sa, "_source_for_platform",
        lambda *a, **kw: calls.append("built") or (_ for _ in ()).throw(AssertionError("fetched")),
    )

    with TestClient(app) as tc:
        uid = _signup(tc)
        with get_session() as s:
            record_calls(s, user_id=uid, platform="x", api_calls=10)

        r = tc.post("/v1/scan/link/commenters", json={"url": "https://x.com/a/status/123"})

    assert r.status_code == 429, r.text
    assert calls == [], "the upstream source was built despite the budget being spent"


def test_compile_under_budget_still_works(monkeypatch):
    """The guard must not break the ordinary path."""
    monkeypatch.setenv("OMI_UPSTREAM_DAILY_CALLS_PER_USER", "1000")
    get_settings.cache_clear()

    import app.routes.scan_async as sa

    class _Source:
        platform = "x"
        quota_used = 3

        def fetch_content_title(self, _cid):
            return "A post"

        def fetch_content_engagers(self, _cid, **kw):
            return ([{"handle": "alice", "channel_id": "a1"}], [], None)

    monkeypatch.setattr(sa, "_source_for_platform", lambda *a, **kw: _Source())

    with TestClient(app) as tc:
        uid = _signup(tc)
        r = tc.post("/v1/scan/link/commenters", json={"url": "https://x.com/a/status/123"})
        assert r.status_code == 200, r.text
        assert r.json()["total"] == 1

    with get_session() as s:
        assert calls_today(s, scope=USER_SCOPE, scope_id=str(uid)) == 3, (
            "the compile's provider calls were not ledgered"
        )
        assert calls_today(s, scope=GLOBAL_SCOPE) == 3


def test_a_failed_fetch_still_charges_what_it_spent(monkeypatch):
    """A fetch that raised part way still made, and still pays for, the calls it managed. Counting
    only successes makes the ledger optimistic in exactly the situation worth watching."""
    monkeypatch.setenv("OMI_UPSTREAM_DAILY_CALLS_PER_USER", "1000")
    get_settings.cache_clear()

    import app.routes.scan_async as sa

    class _FlakySource:
        platform = "x"
        quota_used = 4

        def fetch_content_title(self, _cid):
            return None

        def fetch_content_engagers(self, _cid, **kw):
            raise RuntimeError("provider blew up after 4 calls")

    monkeypatch.setattr(sa, "_source_for_platform", lambda *a, **kw: _FlakySource())

    with TestClient(app) as tc:
        uid = _signup(tc)
        r = tc.post("/v1/scan/link/commenters", json={"url": "https://x.com/a/status/123"})
        assert r.status_code == 502

    with get_session() as s:
        assert calls_today(s, scope=USER_SCOPE, scope_id=str(uid)) == 4


def test_a_cached_compile_costs_nothing(monkeypatch):
    """Re-opening a post is served from the candidate list. It must not appear in the ledger, or the
    numbers stop describing money."""
    monkeypatch.setenv("OMI_UPSTREAM_DAILY_CALLS_PER_USER", "1000")
    get_settings.cache_clear()

    import app.routes.scan_async as sa

    class _Source:
        platform = "x"
        quota_used = 3

        def fetch_content_title(self, _cid):
            return "A post"

        def fetch_content_engagers(self, _cid, **kw):
            return ([{"handle": "alice", "channel_id": "a1"}], [], None)

    monkeypatch.setattr(sa, "_source_for_platform", lambda *a, **kw: _Source())

    with TestClient(app) as tc:
        uid = _signup(tc)
        tc.post("/v1/scan/link/commenters", json={"url": "https://x.com/a/status/123"})
        tc.post("/v1/scan/link/commenters", json={"url": "https://x.com/a/status/123"})

    with get_session() as s:
        assert calls_today(s, scope=USER_SCOPE, scope_id=str(uid)) == 3, (
            "the second, cached compile was charged"
        )


# --------------------------------------------------------------------------- #
# The readout
# --------------------------------------------------------------------------- #
def test_the_admin_readout_is_admin_only():
    with TestClient(app) as tc:
        _signup(tc)
        assert tc.get("/v1/admin/usage").status_code == 403


def test_the_admin_readout_reports_today_against_the_budget():
    with TestClient(app) as tc:
        uid = _signup(tc, "admin@t.com")
        _make_admin(uid)
        with get_session() as s:
            record_calls(s, user_id=uid, platform="x", api_calls=40)
            record_calls(s, user_id=99, platform="youtube", api_calls=10)

        body = tc.get("/v1/admin/usage").json()

    assert body["date"] == today_utc()
    assert body["today_api_calls"] == 50
    assert body["global_remaining"] == body["global_budget"] - 50
    assert {p["platform"] for p in body["by_platform"]} == {"x", "youtube"}
    assert body["heaviest_users_today"][0]["api_calls"] == 40


def test_the_snapshot_survives_an_empty_ledger():
    """Day one of a deployment, and the most likely moment for an operator to open the page."""
    with get_session() as s:
        snap = usage_snapshot(s)
    assert snap["today_api_calls"] == 0
    assert snap["by_day"] == []
    assert snap["heaviest_users_today"] == []


# --------------------------------------------------------------------------- #
# The readout has a page, and it is gated on the server
# --------------------------------------------------------------------------- #
from pathlib import Path  # noqa: E402 — kept beside the tests that use it

_WEB = Path(__file__).resolve().parents[3] / "apps" / "web"


def test_the_spend_page_exists_and_is_admin_gated():
    """A ceiling with no readout only ever tells you that you were refused, never how close you are.
    The page exposes per-user activity volumes, so the gate is on the server: hiding a link is not
    access control, and TypeScript will not tell anyone if the check is dropped."""
    src = (_WEB / "app" / "(app)" / "settings" / "spend" / "page.tsx").read_text()
    assert "is_admin" in src
    assert "redirect('/settings')" in src
    assert "force-dynamic" in src, "a cached render would serve one user's gate result to another"
