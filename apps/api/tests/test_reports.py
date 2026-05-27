"""Tests for the Phase 6 report + sharing surface."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.storage.db import get_session, reset_db_for_tests
from app.storage.models import Investigation, User


@pytest.fixture(autouse=True)
def _fresh_db():
    reset_db_for_tests()
    yield


def _seed_inv(slug: str = "inv_test1234") -> int:
    """Insert a minimal investigation. Returns user_id."""
    with get_session() as session:
        u = User(email="r@x.com", password_hash="x", credits_remaining=3)
        session.add(u)
        session.flush()
        session.add(Investigation(
            user_id=u.id,
            slug=slug,
            label="Video abc",
            input_url="https://youtube.com/watch?v=abc",
            target_id="abc",
            kind="video",
            overall_probability=0.62,
            overall_tier="elevated",
            summary="Test investigation.",
            quota_used=42,
            payload_json={
                "overall_probability": 0.62,
                "overall_tier": "elevated",
                "summary": "Test investigation.",
                "inputs_provided": ["video"],
                "cross_links": [
                    {
                        "kind": "focus_in_cluster",
                        "severity": "elevated",
                        "summary": "Focus in cluster",
                        "evidence": ["3 members tight"],
                        "related_entities": ["X", "Y"],
                        "metadata": {},
                    }
                ],
                "video": {
                    "video_id": "abc",
                    "commenter_count": 2,
                    "fresh_count": 2,
                    "cached_count": 0,
                    "tier_distribution": {"high": 1, "low": 1},
                    "high_suspicion_handles": ["@bot"],
                    "commenters": [
                        {
                            "external_id": "UCb",
                            "handle": "@bot",
                            "tier": "high",
                            "overall_probability": 0.91,
                            "summary": "Looks bad",
                            "intent_label": "Engagement farming",
                            "reasons": ["spam emojis"],
                            "recent_activity": [],
                        },
                        {
                            "external_id": "UCh",
                            "handle": "@human",
                            "tier": "low",
                            "overall_probability": 0.12,
                            "summary": "OK",
                            "reasons": [],
                            "recent_activity": [],
                        },
                    ],
                    "clusters": [],
                    "thread_scan": {"overall_probability": 0.45, "tier": "moderate"},
                    "coordination_score": 0.5,
                    "coordination_tier": "moderate",
                },
            },
        ))
        return u.id


# ---------------------------------------------------------------------------
# Share / revoke
# ---------------------------------------------------------------------------


def test_share_token_minted_then_idempotent():
    _seed_inv()
    with TestClient(app) as tc:
        r1 = tc.post("/v1/investigations/inv_test1234/share")
        assert r1.status_code == 200, r1.text
        token1 = r1.json()["share_token"]
        assert token1.startswith("rpt_")

        # Second call returns same token (idempotent)
        r2 = tc.post("/v1/investigations/inv_test1234/share")
        assert r2.status_code == 200
        assert r2.json()["share_token"] == token1


def test_share_unknown_investigation_404():
    with TestClient(app) as tc:
        r = tc.post("/v1/investigations/inv_does_not_exist/share")
        assert r.status_code == 404


def test_revoke_share_clears_token():
    _seed_inv()
    with TestClient(app) as tc:
        r = tc.post("/v1/investigations/inv_test1234/share")
        token = r.json()["share_token"]

        # Public route works
        pr = tc.get(f"/r/{token}")
        assert pr.status_code == 200

        # Revoke
        rv = tc.delete("/v1/investigations/inv_test1234/share")
        assert rv.status_code == 200

        # Public route 404s after revocation
        pr2 = tc.get(f"/r/{token}")
        assert pr2.status_code == 404


# ---------------------------------------------------------------------------
# Public report view
# ---------------------------------------------------------------------------


def test_public_report_returns_view_payload():
    _seed_inv()
    with TestClient(app) as tc:
        token = tc.post("/v1/investigations/inv_test1234/share").json()["share_token"]
        r = tc.get(f"/r/{token}?template=executive")
        assert r.status_code == 200
        body = r.json()
        view = body["view"]
        assert view["meta"]["slug"] == "inv_test1234"
        assert view["verdict"]["overall_tier"] == "elevated"
        assert view["headline_cross_link"] is not None
        assert len(view["top_flagged"]) == 1
        assert view["top_flagged"][0]["handle"] == "@bot"


def test_public_report_unknown_token_404():
    with TestClient(app) as tc:
        r = tc.get("/r/rpt_doesnotexist")
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# Exports
# ---------------------------------------------------------------------------


def test_markdown_export_returns_markdown():
    _seed_inv()
    with TestClient(app) as tc:
        token = tc.post("/v1/investigations/inv_test1234/share").json()["share_token"]
        r = tc.get(f"/r/{token}/markdown?template=evidence")
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/markdown")
        body = r.text
        assert "# OMISPHERE Report" in body
        assert "## Verdict" in body
        assert "@bot" in body  # appears in the flagged-commenter table


def test_json_export_returns_payload():
    _seed_inv()
    with TestClient(app) as tc:
        token = tc.post("/v1/investigations/inv_test1234/share").json()["share_token"]
        r = tc.get(f"/r/{token}/json")
        assert r.status_code == 200
        body = r.json()
        assert body["investigation"]["slug"] == "inv_test1234"
        assert body["payload"]["overall_tier"] == "elevated"
