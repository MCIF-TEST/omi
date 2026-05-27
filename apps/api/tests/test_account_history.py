"""Tests for the /v1/accounts/{platform}/{external_id}/history endpoint."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.schemas import Profile, ScanResult, SignalResult, Tier
from app.storage.db import reset_db_for_tests
from app.storage.models import Account, Scan
from app.storage.repository import AccountRepository
from app.storage.db import get_session


@pytest.fixture(autouse=True)
def _fresh_db():
    reset_db_for_tests()
    yield


def _seed_account_with_scans(probs: list[float]) -> str:
    external_id = "UC" + "T" * 22
    base_time = datetime.now(timezone.utc) - timedelta(days=len(probs))
    with get_session() as session:
        repo = AccountRepository(session)
        profile = Profile(platform="youtube", handle="@TrendTarget", display_name="Trend Target")
        for i, p in enumerate(probs):
            scan = ScanResult(
                overall_probability=p,
                confidence=0.7,
                tier=Tier.MODERATE if p >= 0.25 else Tier.LOW,
                signals=[SignalResult(name="temporal", probability=p, confidence=0.5)],
                summary=f"Scan #{i+1}",
            )
            repo.upsert_with_scan(
                platform="youtube",
                external_id=external_id,
                profile=profile,
                scan=scan,
                fingerprint=[0.1] * 19,
            )
            # Backdate so each scan has a distinct timestamp
            account = repo.get("youtube", external_id)
            account.scans[0].scanned_at = base_time + timedelta(days=i)
            session.flush()
    return external_id


def test_history_endpoint_returns_404_for_unknown():
    with TestClient(app) as tc:
        r = tc.get("/v1/accounts/youtube/UC_unknown/history")
        assert r.status_code == 404


def test_history_returns_scans_with_trend():
    eid = _seed_account_with_scans([0.20, 0.32, 0.45, 0.60, 0.72])
    with TestClient(app) as tc:
        r = tc.get(f"/v1/accounts/youtube/{eid}/history")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["platform"] == "youtube"
        assert body["external_id"] == eid
        assert body["handle"] == "@TrendTarget"
        assert len(body["scans"]) == 5
        # Newest first
        assert body["scans"][0]["overall_probability"] >= body["scans"][-1]["overall_probability"]
        trend = body["trend"]
        assert trend["direction"] == "rising"
        assert trend["sample_size"] == 5
        assert trend["slope"] > 0


def test_history_handles_single_scan():
    eid = _seed_account_with_scans([0.45])
    with TestClient(app) as tc:
        r = tc.get(f"/v1/accounts/youtube/{eid}/history")
        assert r.status_code == 200
        body = r.json()
        assert body["trend"]["direction"] == "insufficient"
        assert body["trend"]["sample_size"] == 1


def test_history_respects_limit_query():
    eid = _seed_account_with_scans([0.20, 0.30, 0.40, 0.50, 0.60])
    with TestClient(app) as tc:
        r = tc.get(f"/v1/accounts/youtube/{eid}/history?limit=2")
        assert r.status_code == 200
        assert len(r.json()["scans"]) == 2

        r = tc.get(f"/v1/accounts/youtube/{eid}/history?limit=999")
        assert r.status_code == 400


def test_weak_signals_populated_when_data_is_thin():
    """Sanity: scoring.aggregate should now attach weak_signals."""
    from app.detection.engine import analyze_account

    profile = Profile(platform="youtube", handle="@thin", display_name="Thin")
    scan = analyze_account(profile, posts=[])
    assert isinstance(scan.weak_signals, list)
    # With zero posts, several detectors will be weak
    assert len(scan.weak_signals) >= 3
