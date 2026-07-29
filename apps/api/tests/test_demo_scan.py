"""Tests for the free anonymous pre-login scan (``/v1/scan/demo/*``).

The free scan is the SAME select-then-scan flow the signed-in workspace uses — compile the repliers,
pick who to analyze, then run the real engine on the selection — with three limits:

* X (Twitter) posts only,
* at most 25 repliers,
* TWO full scans per IP address, ever.

A failed attempt must never spend one of those two.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import create_app
from app.routes.scan import set_twitter_client_factory_for_tests
from app.routes.scan_async import DEMO_FREE_SCANS_PER_IP
from app.storage.db import reset_db_for_tests
from tests.fakes import FakeXScanClient


TWEET_URL = "https://x.com/someone/status/1790000000000000000"
OTHER_TWEET_URL = "https://x.com/someone/status/1790000000000000001"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("OMI_TWITTER_API_KEY", "test-key")
    get_settings.cache_clear()
    reset_db_for_tests("sqlite:///:memory:")
    set_twitter_client_factory_for_tests(lambda: FakeXScanClient())
    app = create_app()
    yield TestClient(app)
    set_twitter_client_factory_for_tests(None)
    reset_db_for_tests("sqlite:///:memory:")
    get_settings.cache_clear()


def _compile(client, ip: str, url: str = TWEET_URL):
    return client.post("/v1/scan/demo/commenters", json={"url": url},
                       headers={"x-forwarded-for": ip})


def _score(client, ip: str, selected: list[str], url: str = TWEET_URL):
    return client.post("/v1/scan/demo/score", json={"url": url, "selected": selected},
                       headers={"x-forwarded-for": ip})


def _run_full_scan(client, ip: str, url: str = TWEET_URL):
    """Compile → select everything → analyze, the way the landing page drives it.

    Returns whichever response ends the run: a refusal at the compile step (a spent visitor is turned
    away there) is returned as-is, so callers can assert on the outcome of the whole attempt."""
    listing = _compile(client, ip, url)
    if listing.status_code != 200:
        return listing
    ids = [c["external_id"] for c in listing.json()["commenters"]]
    return _score(client, ip, ids, url)


# --------------------------------------------------------------------------- #
# Compile step
# --------------------------------------------------------------------------- #
def test_compile_lists_repliers_without_auth(client):
    resp = _compile(client, "10.0.0.1")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["platform"] == "x"
    assert len(body["commenters"]) > 0
    # The list carries what the picker renders: who said it, and what they said.
    first = body["commenters"][0]
    assert first["external_id"] and "comment" in first


def test_compile_caps_at_25_repliers(client):
    # The fake serves 40 repliers; the free compile must surface at most 25.
    body = _compile(client, "10.0.0.20").json()
    assert len(body["commenters"]) <= 25
    # And it does not dangle a "there's more" affordance the free tier can't honor.
    assert body["has_more"] is False


def test_compile_rejects_youtube_urls(client):
    resp = client.post("/v1/scan/demo/commenters",
                       json={"url": "https://www.youtube.com/watch?v=jNQXAC9IVRw"},
                       headers={"x-forwarded-for": "10.0.0.5"})
    assert resp.status_code == 400
    assert "x (twitter)" in resp.json()["detail"].lower()


def test_compile_rejects_an_x_profile_url_not_a_post(client):
    resp = _compile(client, "10.0.0.9", "https://x.com/someone")
    assert resp.status_code == 400


def test_compile_rejects_missing_url(client):
    resp = client.post("/v1/scan/demo/commenters", json={},
                       headers={"x-forwarded-for": "10.0.0.6"})
    assert resp.status_code == 400


def test_recompiling_the_same_post_does_not_refetch_from_x(client):
    """The candidate list is cached, so re-opening a post is free — the picker reloads instantly and we
    don't spend a second X call on it."""
    fake = FakeXScanClient()
    set_twitter_client_factory_for_tests(lambda: fake)
    _compile(client, "10.0.0.30")
    calls_after_first = len(fake.calls)
    second = _compile(client, "10.0.0.30")
    assert second.status_code == 200
    assert len(fake.calls) == calls_after_first  # no new upstream traffic


# --------------------------------------------------------------------------- #
# Score step — the real engine on the selection
# --------------------------------------------------------------------------- #
def test_score_analyzes_only_the_selected_repliers(client):
    listing = _compile(client, "10.0.0.2").json()
    picked = [c["external_id"] for c in listing["commenters"]][:3]
    resp = _score(client, "10.0.0.2", picked)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["overall_tier"] in ("low", "moderate", "elevated", "high")
    # Exactly the selection was analyzed — not the whole compiled list.
    assert body["video"]["commenter_count"] == len(picked)
    returned = {c["external_id"] for c in body["video"]["commenters"]}
    assert returned == set(picked)


def test_score_caps_the_selection_at_25(client):
    listing = _compile(client, "10.0.0.21").json()
    ids = [c["external_id"] for c in listing["commenters"]]
    # Even if a client posts more ids than the cap allows, at most 25 are analyzed.
    resp = _score(client, "10.0.0.21", ids + [f"extra_{i}" for i in range(40)])
    assert resp.status_code == 200, resp.text
    assert resp.json()["video"]["commenter_count"] <= 25


def test_score_requires_compiling_first(client):
    resp = _score(client, "10.0.0.22", ["replier_0"])
    assert resp.status_code == 400
    assert "compile" in resp.json()["detail"].lower()


def test_score_requires_a_selection(client):
    _compile(client, "10.0.0.23")
    resp = _score(client, "10.0.0.23", [])
    assert resp.status_code == 400


def test_score_rejects_ids_that_are_not_in_the_list(client):
    _compile(client, "10.0.0.24")
    resp = _score(client, "10.0.0.24", ["not_a_real_replier"])
    assert resp.status_code == 400


# --------------------------------------------------------------------------- #
# The free-scan budget: two per IP, ever
# --------------------------------------------------------------------------- #
def test_one_free_scan_per_ip_then_429(client):
    ip = "10.0.0.3"
    assert _run_full_scan(client, ip).status_code == 200

    second = _run_full_scan(client, ip, OTHER_TWEET_URL)
    assert second.status_code == 429
    # The message points at signup so the UI can surface the upgrade CTA.
    assert "account" in second.json()["detail"].lower()


def test_the_budget_is_one(client):
    """Pins the advertised number: the landing page copy and this constant must agree."""
    assert DEMO_FREE_SCANS_PER_IP == 1


def test_compile_is_refused_once_the_budget_is_spent(client):
    """A spent visitor is turned away at the FIRST step, not after compiling a list they can't analyze."""
    ip = "10.0.0.31"
    # Assert the setup: a scan that silently failed would leave the budget unspent and make the real
    # assertion below fail for a reason that has nothing to do with what this test is about.
    first = _run_full_scan(client, ip)
    assert first.status_code == 200, first.text

    resp = _compile(client, ip)
    assert resp.status_code == 429


def test_an_in_flight_scan_holds_its_place_in_the_budget(client):
    """The limit must count scans that are RUNNING, not just finished ones.

    A demo scan takes minutes. If the budget only counted completed scans, firing several requests at
    once from one IP would let every one of them pass the check before any had written a row, a free
    unlimited scan for anyone willing to open two tabs."""
    from app.routes import scan_async as SA
    from app.storage.db import get_session

    ip_hash = SA.scan_mod._hash_ip("10.0.0.60")
    with get_session() as session:
        assert SA._demo_scans_used(session, ip_hash) == 0

    # ONE scan in flight (reserved, not yet finished) is the whole budget.
    r1 = SA._reserve_demo_scan(ip_hash, "111", "ua")
    with get_session() as session:
        assert SA._demo_scans_used(session, ip_hash) == 1

    # A second request from that IP is refused while the first is still running.
    assert _compile(client, "10.0.0.60").status_code == 429

    # It fails: its place is handed back and the visitor can scan again.
    SA._release_demo_scan(r1)
    with get_session() as session:
        assert SA._demo_scans_used(session, ip_hash) == 0
    assert _compile(client, "10.0.0.60").status_code == 200

    # The retry succeeds: permanently spent, and the budget is now closed.
    r2 = SA._reserve_demo_scan(ip_hash, "222", "ua")
    SA._confirm_demo_scan(r2)
    with get_session() as session:
        assert SA._demo_scans_used(session, ip_hash) == 1
    assert _compile(client, "10.0.0.60").status_code == 429


def test_a_reservation_orphaned_by_a_crash_expires(client):
    """A process killed mid-scan leaves a reservation behind. It must age out instead of locking that
    visitor out of the product forever."""
    from datetime import datetime, timedelta, timezone

    from app.routes import scan_async as SA
    from app.storage.db import get_session
    from app.storage.models import DemoScanLog

    ip_hash = SA.scan_mod._hash_ip("10.0.0.61")
    row_id = SA._reserve_demo_scan(ip_hash, "333", "ua")
    with get_session() as session:
        row = session.get(DemoScanLog, row_id)
        row.created_at = datetime.now(timezone.utc) - SA.DEMO_RESERVATION_TTL - timedelta(minutes=1)
        session.commit()
    with get_session() as session:
        assert SA._demo_scans_used(session, ip_hash) == 0


def test_different_ips_have_independent_budgets(client):
    assert _run_full_scan(client, "10.0.0.4").status_code == 200
    assert _run_full_scan(client, "10.0.0.41").status_code == 200


def test_a_failed_analyze_does_not_spend_a_free_scan(client):
    """Only a SUCCESSFUL analyze burns the budget: a bad selection must not cost the visitor."""
    ip = "10.0.0.8"
    _compile(client, ip)
    assert _score(client, ip, ["not_a_real_replier"]).status_code == 400
    # The free scan is still available.
    assert _run_full_scan(client, ip).status_code == 200


# --------------------------------------------------------------------------- #
# The analyst — the free scan is a REAL read, not a canned one
# --------------------------------------------------------------------------- #
def test_the_free_scan_runs_the_real_analyst_and_inlines_its_reading(client, monkeypatch):
    """The free scan must reach the model, like a signed-in one. A signed-in scan generates in the
    background and the client polls /v1/investigations/{slug}/analyst; an anonymous scan has no saved
    investigation to poll, so the assessment rides back on the response."""
    from app.reasoning import analyst as A

    seen: list[dict] = []

    def fake_assess(payload, *, ref, platform, settings=None, capture=None):
        seen.append({"ref": ref, "platform": platform,
                     "accounts": len((payload.get("video") or {}).get("commenters") or [])})
        return {"headline": "Three accounts look bought.", "assessment": "Reasoning here."}

    monkeypatch.setattr(A, "analyst_enabled", lambda *_a, **_k: True)
    monkeypatch.setattr(A, "assess_payload", fake_assess)

    listing = _compile(client, "10.0.0.50").json()
    picked = [c["external_id"] for c in listing["commenters"]][:3]
    body = _score(client, "10.0.0.50", picked).json()

    # The analyst saw the real scan payload for the real platform...
    assert len(seen) == 1, "exactly one model call for a free scan (it is capped at one batch)"
    assert seen[0]["platform"] == "x"
    assert seen[0]["accounts"] == 3
    # ...and its reading came back on the response for the UI to render.
    assert body["analyst_assessment"]["headline"] == "Three accounts look bought."


def test_the_demo_never_ships_the_admin_only_signal_breakdown(client, monkeypatch):
    """A demo visitor is anonymous, so never an admin.

    The eight-dimension breakdown is admin-only while the feature is unfinished, and this is an
    UNAUTHENTICATED route, so `is_admin=True` must not be reachable on it at all. The per-account OMI
    score, tier and written read still come back: that is what the visitor is here to see.
    """
    from app.reasoning import analyst as A

    def fake_assess(payload, *, ref, platform, settings=None, capture=None):
        return {
            "headline": "Two accounts look bought.", "assessment": "Reasoning here.",
            "commenter_assessments": [{
                "ref": "A1", "handle": "@a", "omi_score": 88, "suspicion_tier": "high",
                "confidence": 90, "resolved": True,
                "signals": [{"name": "temporal", "score": 90, "reason": "machine-regular cadence"}],
                "assessment": "Posts on a mechanically regular cadence.", "citations": ["A1"],
            }],
        }

    monkeypatch.setattr(A, "analyst_enabled", lambda *_a, **_k: True)
    monkeypatch.setattr(A, "assess_payload", fake_assess)

    listing = _compile(client, "10.0.0.53").json()
    picked = [c["external_id"] for c in listing["commenters"]][:2]
    body = _score(client, "10.0.0.53", picked).json()

    row = body["analyst_assessment"]["commenter_assessments"][0]
    assert "signals" not in row, "the demo leaked the admin-only signal breakdown"
    assert "confidence" not in row
    # What the visitor IS meant to see is untouched.
    assert row["omi_score"] == 88
    assert row["suspicion_tier"] == "high"
    assert row["assessment"].startswith("Posts on a mechanically regular")


def test_a_failing_analyst_still_returns_the_scan(client, monkeypatch):
    """The assessment is a bonus on top of a finished scan. If the model call fails, the visitor
    still gets every deterministic per-account score — and has still spent only one free scan."""
    from app.reasoning import analyst as A

    monkeypatch.setattr(A, "analyst_enabled", lambda *_a, **_k: True)
    monkeypatch.setattr(A, "assess_payload",
                        lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("openrouter down")))

    listing = _compile(client, "10.0.0.51").json()
    picked = [c["external_id"] for c in listing["commenters"]][:2]
    resp = _score(client, "10.0.0.51", picked)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["analyst_assessment"] is None
    assert body["video"]["commenter_count"] == 2


def test_the_analyst_is_skipped_when_it_is_disabled(client, monkeypatch):
    """The default path (analyst off) must not attempt a model call at all."""
    from app.reasoning import analyst as A

    called = []
    monkeypatch.setattr(A, "analyst_enabled", lambda *_a, **_k: False)
    monkeypatch.setattr(A, "assess_payload", lambda *a, **k: called.append(1))

    listing = _compile(client, "10.0.0.52").json()
    picked = [c["external_id"] for c in listing["commenters"]][:2]
    body = _score(client, "10.0.0.52", picked).json()
    assert called == []
    assert body["analyst_assessment"] is None


def test_compiling_does_not_spend_a_free_scan(client):
    """Browsing is free: only the analyze step counts against the budget."""
    ip = "10.0.0.42"
    for _ in range(3):
        assert _compile(client, ip).status_code == 200
    assert _run_full_scan(client, ip).status_code == 200
