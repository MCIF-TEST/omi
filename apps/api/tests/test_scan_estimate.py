"""F1+F2: pre-scan estimate must equal the real charge and the real commenter cap.

The estimate endpoint exists so the UI can show cost + effective commenter count
BEFORE a scan. It must mirror /link/start exactly (classify_link -> clamp ->
compute_scan_credits), or it becomes a lie. These pin that equivalence and the
verified ground truth that, in the live path, an X link scan costs the SAME as
YouTube (the 10x rate keys on platform=="twitter"; the link route passes "x").
"""

from __future__ import annotations

import math

import pytest
from fastapi.testclient import TestClient

from app.core.auth import compute_scan_credits
from app.core.config import get_settings
from app.main import app
from app.storage.db import reset_db_for_tests


@pytest.fixture(autouse=True)
def _fresh(monkeypatch):
    monkeypatch.setenv("OMI_REQUIRE_AUTH", "false")  # local mode: user id 0
    get_settings.cache_clear()
    reset_db_for_tests()
    yield
    get_settings.cache_clear()


def _estimate(tc: TestClient, url: str, n: int) -> dict:
    r = tc.post("/v1/scan/estimate", json={"url": url, "max_commenters": n})
    assert r.status_code == 200, r.text
    return r.json()


def test_estimate_matches_compute_scan_credits_youtube():
    s = get_settings()
    with TestClient(app) as tc:
        e = _estimate(tc, "https://www.youtube.com/watch?v=dQw4w9WgXcQ", 120)
    assert e["platform"] == "youtube" and e["recognized"]
    eff = min(120, s.scan_max_commenters)
    assert e["effective_max_commenters"] == eff
    assert e["credits"] == compute_scan_credits("youtube", eff, s)


def test_estimate_matches_real_charge_for_x_link():
    """Ground-truth: the live link path charges compute_scan_credits('x', n),
    which falls to the YouTube rate — so X == YouTube cost today. The estimate
    must reflect that real charge, not the unreachable 10x 'twitter' rate."""
    s = get_settings()
    with TestClient(app) as tc:
        e = _estimate(tc, "https://x.com/jack", 50)
    assert e["platform"] == "x" and e["recognized"]
    assert e["credits"] == compute_scan_credits("x", min(50, s.scan_max_commenters), s)
    # And that real charge equals the YouTube rate for the same size.
    assert e["credits"] == compute_scan_credits("youtube", min(50, s.scan_max_commenters), s)


def test_estimate_caps_match_backend_and_drive_f2():
    """The cap the UI bounds its slider with is the real server cap, and the
    effective count never exceeds it (the 500-vs-150 mismatch source)."""
    s = get_settings()
    with TestClient(app) as tc:
        e = _estimate(tc, "https://www.youtube.com/watch?v=abc12345678", 500)
    assert e["max_commenters_cap"] == s.scan_max_commenters
    assert e["effective_max_commenters"] == s.scan_max_commenters
    assert e["effective_max_commenters"] <= e["requested_max_commenters"]


def test_estimate_unrecognized_link_has_no_cost_but_keeps_cap():
    s = get_settings()
    with TestClient(app) as tc:
        e = _estimate(tc, "not a link", 25)
    assert e["recognized"] is False
    assert e["credits"] is None
    assert e["max_commenters_cap"] == s.scan_max_commenters
