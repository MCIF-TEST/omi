"""Tests for Phase 8 monitoring + watchlists."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.monitoring.anomalies import detect_high_tier_surge, detect_narrative_spikes
from app.monitoring.service import MonitoringService
from app.storage.db import get_session, reset_db_for_tests
from app.storage.models import (
    Alert, Investigation, Narrative, NarrativeMembership, User, Watchlist,
)


@pytest.fixture(autouse=True)
def _fresh_db():
    reset_db_for_tests()
    yield


def _user(email: str = "u@x.com") -> int:
    with get_session() as session:
        u = User(email=email, password_hash="x", credits_remaining=3)
        session.add(u); session.flush()
        return u.id


# ---------------------------------------------------------------------------
# Anomaly detectors
# ---------------------------------------------------------------------------


def test_narrative_spike_detected_when_growth_exceeds_threshold():
    now = datetime.now(timezone.utc)
    narrative_id: int | None = None
    with get_session() as session:
        n = Narrative(label="vaccines are safe", centroid_json=[0.1, 0.0],
                      dimensions=2, member_count=10, distinct_authors=5,
                      first_seen_at=now - timedelta(days=1), last_seen_at=now)
        session.add(n); session.flush()
        narrative_id = n.id
        # 7 in last hour at minutes 5..35 (well inside the hour boundary)
        for i, mins in enumerate([5, 10, 15, 20, 25, 30, 35]):
            session.add(NarrativeMembership(
                narrative_id=narrative_id, platform="youtube",
                account_external_id=f"A{i}", comment_text="x",
                observed_at=now - timedelta(minutes=mins),
            ))
        # 2 in prior hour, well clear of the 1h boundary
        for i, mins in enumerate([75, 90]):
            session.add(NarrativeMembership(
                narrative_id=narrative_id, platform="youtube",
                account_external_id=f"B{i}", comment_text="x",
                observed_at=now - timedelta(minutes=mins),
            ))

    with get_session() as session:
        hits = detect_narrative_spikes(session)

    assert len(hits) == 1
    assert hits[0].kind == "narrative_spike"
    assert hits[0].payload["narrative_id"] == narrative_id
    assert hits[0].payload["recent_members"] == 7
    assert hits[0].payload["prior_members"] == 2


def test_narrative_spike_not_triggered_when_below_min_recent():
    now = datetime.now(timezone.utc)
    with get_session() as session:
        n = Narrative(label="x", centroid_json=[1.0], dimensions=1,
                      member_count=4, distinct_authors=2,
                      first_seen_at=now, last_seen_at=now)
        session.add(n); session.flush()
        # 3 in last hour < min_recent (5) — should NOT fire even though prior=0
        for i in range(3):
            session.add(NarrativeMembership(
                narrative_id=n.id, platform="youtube",
                account_external_id=f"A{i}", comment_text="x",
                observed_at=now - timedelta(minutes=10),
            ))
    with get_session() as session:
        assert detect_narrative_spikes(session) == []


def test_high_tier_surge_detected():
    now = datetime.now(timezone.utc)
    uid = _user()
    with get_session() as session:
        # 5 high-tier investigations in the last hour
        for i in range(5):
            session.add(Investigation(
                user_id=uid, slug=f"inv_h{i}", label="x", input_url="x",
                kind="video", overall_probability=0.85, overall_tier="high",
                summary="x", payload_json={},
                created_at=now - timedelta(minutes=10 * (i + 1)),
            ))
    with get_session() as session:
        hits = detect_high_tier_surge(session)
    assert len(hits) == 1
    assert hits[0].payload["last_hour"] == 5


def test_high_tier_surge_quiet_when_baseline_normal():
    now = datetime.now(timezone.utc)
    uid = _user()
    # 1 in last hour, 24 spread over the day = baseline 1/h → not a surge
    with get_session() as session:
        for i in range(24):
            session.add(Investigation(
                user_id=uid, slug=f"inv_norm{i}", label="x", input_url="x",
                kind="video", overall_probability=0.7, overall_tier="elevated",
                summary="x", payload_json={},
                created_at=now - timedelta(hours=i + 1),
            ))
        session.add(Investigation(
            user_id=uid, slug="inv_recent", label="x", input_url="x",
            kind="video", overall_probability=0.75, overall_tier="elevated",
            summary="x", payload_json={},
            created_at=now - timedelta(minutes=20),
        ))
    with get_session() as session:
        assert detect_high_tier_surge(session) == []


# ---------------------------------------------------------------------------
# Service-level anomaly pass with dedup
# ---------------------------------------------------------------------------


def test_anomaly_pass_writes_alerts_and_dedupes():
    now = datetime.now(timezone.utc)
    uid = _user()
    with get_session() as session:
        for i in range(6):
            session.add(Investigation(
                user_id=uid, slug=f"inv_s{i}", label="x", input_url="x",
                kind="video", overall_probability=0.85, overall_tier="high",
                summary="x", payload_json={},
                created_at=now - timedelta(minutes=5 * (i + 1)),
            ))

    with get_session() as session:
        r1 = MonitoringService(session).run_anomaly_pass()
    assert r1.alerts_written >= 1

    # Re-run immediately — dedup kicks in
    with get_session() as session:
        r2 = MonitoringService(session).run_anomaly_pass()
    assert r2.alerts_written == 0


# ---------------------------------------------------------------------------
# Watchlists CRUD + note_observation
# ---------------------------------------------------------------------------


def test_watchlist_add_is_idempotent():
    uid = _user()
    with get_session() as session:
        svc = MonitoringService(session)
        w1 = svc.add_watchlist(user_id=uid, kind="channel", target_id="UCabc", label="@abc")
        w2 = svc.add_watchlist(user_id=uid, kind="channel", target_id="UCabc", label="@abc")
        assert w1.id == w2.id


def test_note_observation_fires_alert_on_tier_change():
    uid = _user()
    with get_session() as session:
        svc = MonitoringService(session)
        svc.add_watchlist(user_id=uid, kind="channel", target_id="UC1",
                          label="@one", alert_threshold_tier="moderate")
        # First observation at HIGH — crosses threshold → alert
        n1 = svc.note_observation(kind="channel", target_id="UC1",
                                  current_tier="high", current_probability=0.9)
        assert n1 == 1
        # Same tier next time — no alert
        n2 = svc.note_observation(kind="channel", target_id="UC1",
                                  current_tier="high", current_probability=0.92)
        assert n2 == 0
        # Drop back to LOW — that's a tier change, but LOW < threshold (moderate) → no alert
        n3 = svc.note_observation(kind="channel", target_id="UC1",
                                  current_tier="low", current_probability=0.15)
        assert n3 == 0


# ---------------------------------------------------------------------------
# HTTP routes
# ---------------------------------------------------------------------------


def test_feed_endpoint_returns_alerts():
    uid = _user()
    with get_session() as session:
        session.add(Alert(user_id=None, kind="narrative_spike",
                          severity="moderate", message="test spike",
                          payload_json={"narrative_id": 1}))
    with TestClient(app) as tc:
        r = tc.get("/v1/monitoring/feed")
        assert r.status_code == 200, r.text
        body = r.json()
        assert "items" in body
        assert any(item["kind"] == "narrative_spike" for item in body["items"])


def test_watchlist_crud_via_http():
    with TestClient(app) as tc:
        # Local-mode user has id 0 — endpoint refuses for safety
        r = tc.post("/v1/watchlists", json={
            "kind": "channel", "target_id": "UCxxx", "label": "@x",
        })
        # require_auth=False default → id=0 — endpoint returns 400
        assert r.status_code == 400


def test_mark_alert_read():
    uid = _user()
    with get_session() as session:
        # User-specific alert
        a = Alert(user_id=uid, kind="tier_change", severity="moderate",
                  message="x", payload_json={})
        session.add(a); session.flush()
        alert_id = a.id

    # In local mode the require_user returns id=0 — mark_read shouldn't fire
    # because alert.user_id is set. So this should 404 in local mode.
    with TestClient(app) as tc:
        r = tc.post(f"/v1/monitoring/alerts/{alert_id}/read")
        assert r.status_code == 404
