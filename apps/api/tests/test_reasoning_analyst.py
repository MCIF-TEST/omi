"""Integration tests for the Omi Analyst production wiring (OMI_ANALYST_PRODUCTION_WIRING_V1).

Covers: OFF by default, feature-flagged route (503), the enabled path running the REAL
completed implementation (ml/analyst/omi_analyst), async (background) + cached behavior,
SAVEPOINT-isolated persistence, and that nothing here touches detection/scoring/OmiScore.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core import background
from app.main import app
from app.reasoning import analyst
from app.storage.db import get_session, reset_db_for_tests
from app.storage.models import Investigation, User

REQUIRED_ELEMENTS = ("evidence_for", "evidence_against", "confidence_band",
                     "confidence_rationale", "uncertainty", "what_would_change_this")


@pytest.fixture(autouse=True)
def _fresh():
    reset_db_for_tests("sqlite:///:memory:")
    yield


def _payload() -> dict:
    return {
        "overall_probability": 0.72,
        "overall_tier": "elevated",
        "confidence": 0.6,
        "summary": "Elevated suspicion across multiple signals.",
        "cross_links": [{"kind": "focus_in_cluster", "summary": "Focus in cluster"}],
        "video": {
            "commenters": [
                {"handle": "@bot1", "tier": "high", "overall_probability": 0.91,
                 "intent_label": "Engagement farming", "summary": "Spam"},
                {"handle": "@bot2", "tier": "elevated", "overall_probability": 0.7,
                 "intent_label": "Amplification", "summary": "Repetitive praise"},
            ],
            "clusters": [{"method": "co_engagement", "members": ["A", "B", "C"]}],
        },
    }


def _seed(slug: str = "inv_analyst") -> None:
    with get_session() as session:
        u = User(email="a@x.com", password_hash="x", credits_remaining=3)
        session.add(u); session.flush()
        session.add(Investigation(
            user_id=u.id, slug=slug, label="Video xyz",
            input_url="https://youtube.com/watch?v=xyz", kind="video",
            overall_probability=0.72, overall_tier="elevated",
            summary="Elevated suspicion.", payload_json=_payload(),
        ))


def _enable(monkeypatch):
    monkeypatch.setattr(analyst, "analyst_enabled", lambda settings=None: True)


# --- OFF by default --------------------------------------------------------- #
def test_disabled_by_default():
    assert analyst.analyst_enabled() is False
    assert analyst.available() is False  # never imports omi_analyst when off
    assert analyst.assess_payload(_payload(), ref="sub_x") is None


def test_route_503_when_disabled():
    _seed()
    with TestClient(app) as tc:
        r = tc.post("/v1/investigations/inv_analyst/analyst")
        assert r.status_code == 503
        assert "disabled" in r.json()["detail"].lower()


# --- enabled path runs the REAL completed implementation -------------------- #
def test_assess_payload_runs_real_impl_and_is_schema_valid(monkeypatch):
    _enable(monkeypatch)
    assert analyst.available() is True  # omi_analyst imported lazily
    out = analyst.assess_payload(_payload(), ref="sub_x", platform="youtube")
    assert out is not None
    assert out["subject"]["grain"] == "comment_section"
    assert out["analyst_version"] == "v1"
    for el in REQUIRED_ELEMENTS:
        assert el in out and out[el] not in (None, ""), el
    # co_engagement is discriminative -> corroboration carries it
    assert "co_engagement" in out["corroboration"]["discriminative_methods"]
    # the flagged commenters were folded in as supporting evidence
    assert any("assessment" in e["signal"] for e in out["evidence_for"])


def test_route_async_202_then_cached_200(monkeypatch):
    _enable(monkeypatch)
    _seed()
    captured: list = []
    monkeypatch.setattr(background, "submit", lambda fn, *a, **k: captured.append((fn, a)))

    with TestClient(app) as tc:
        r1 = tc.post("/v1/investigations/inv_analyst/analyst")
        assert r1.status_code == 202, r1.text
        b1 = r1.json()
        assert b1["status"] == "generating" and b1["cached"] is False and b1["assessment"] is None
        assert captured and captured[0][0] is analyst.generate_and_persist

        # Run the background job synchronously (its own session), then poll -> 200.
        analyst.generate_and_persist(*captured[0][1])
        r2 = tc.post("/v1/investigations/inv_analyst/analyst")
        assert r2.status_code == 200, r2.text
        b2 = r2.json()
        assert b2["status"] == "ready" and b2["cached"] is True
        assert b2["assessment"]["subject"]["grain"] == "comment_section"
        for el in REQUIRED_ELEMENTS:
            assert el in b2["assessment"]


def test_generate_and_persist_caches_savepoint_isolated(monkeypatch):
    _enable(monkeypatch)
    _seed()
    entry = analyst.generate_and_persist("inv_analyst", None, False)
    assert entry and entry["assessment"]
    # cached inside payload_json under CACHE_KEY, survives a reload
    with get_session() as session:
        inv = session.query(Investigation).filter_by(slug="inv_analyst").one()
        cached = analyst.cached_assessment(inv)
        assert cached is not None
        assert cached["assessment"]["verdict"] in (
            "confirmed_bot_ring", "likely_inauthentic", "mixed",
            "likely_authentic", "inconclusive",
        )
        # original engine fields are untouched (no scoring mutation)
        assert inv.payload_json["overall_probability"] == 0.72


def test_route_404_unknown_slug_when_enabled(monkeypatch):
    _enable(monkeypatch)
    monkeypatch.setattr(background, "submit", lambda fn, *a, **k: None)
    with TestClient(app) as tc:
        r = tc.post("/v1/investigations/inv_nope/analyst")
        assert r.status_code == 404


def test_refresh_triggers_regeneration(monkeypatch):
    _enable(monkeypatch)
    _seed()
    analyst.generate_and_persist("inv_analyst", None, False)
    captured: list = []
    monkeypatch.setattr(background, "submit", lambda fn, *a, **k: captured.append((fn, a)))
    with TestClient(app) as tc:
        # refresh=true bypasses the cache -> 202 (regenerate), not a cached 200
        r = tc.post("/v1/investigations/inv_analyst/analyst?refresh=true")
        assert r.status_code == 202
        assert captured  # a regeneration job was submitted


# --- guardrail: disabled assess never raises / never touches scoring -------- #
def test_assess_payload_never_raises_on_garbage(monkeypatch):
    _enable(monkeypatch)
    # Malformed payload must degrade to None or a valid assessment, never raise.
    out = analyst.assess_payload({"nonsense": True}, ref="sub_x")
    assert out is None or out["subject"]["grain"] == "comment_section"
