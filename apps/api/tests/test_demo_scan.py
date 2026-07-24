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
def test_two_free_scans_per_ip_then_429(client):
    ip = "10.0.0.3"
    assert _run_full_scan(client, ip).status_code == 200
    assert _run_full_scan(client, ip, OTHER_TWEET_URL).status_code == 200

    third = _run_full_scan(client, ip)
    assert third.status_code == 429
    # The message points at signup so the UI can surface the upgrade CTA.
    assert "account" in third.json()["detail"].lower()


def test_the_budget_is_two(client):
    """Pins the advertised number — the landing page copy and this constant must agree."""
    assert DEMO_FREE_SCANS_PER_IP == 2


def test_compile_is_refused_once_the_budget_is_spent(client):
    """A spent visitor is turned away at the FIRST step, not after compiling a list they can't analyze."""
    ip = "10.0.0.31"
    _run_full_scan(client, ip)
    _run_full_scan(client, ip, OTHER_TWEET_URL)
    resp = _compile(client, ip)
    assert resp.status_code == 429


def test_different_ips_have_independent_budgets(client):
    assert _run_full_scan(client, "10.0.0.4").status_code == 200
    assert _run_full_scan(client, "10.0.0.41").status_code == 200


def test_a_failed_analyze_does_not_spend_a_free_scan(client):
    """Only a SUCCESSFUL analyze burns one of the two — a bad selection must not cost the visitor."""
    ip = "10.0.0.8"
    _compile(client, ip)
    assert _score(client, ip, ["not_a_real_replier"]).status_code == 400
    # Both free scans are still available.
    assert _run_full_scan(client, ip).status_code == 200
    assert _run_full_scan(client, ip, OTHER_TWEET_URL).status_code == 200


def test_compiling_does_not_spend_a_free_scan(client):
    """Browsing is free: only the analyze step counts against the budget."""
    ip = "10.0.0.42"
    for _ in range(3):
        assert _compile(client, ip).status_code == 200
    assert _run_full_scan(client, ip).status_code == 200
