"""HTTP-level tests for the OmiScore intelligence endpoints."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.main import create_app

client = TestClient(create_app())


def _spammy_payload() -> dict:
    base = datetime.now(timezone.utc) - timedelta(days=2)
    posts = [
        {
            "id": f"c{i}",
            "author_handle": "promo_bot",
            "text": "AMAZING DEAL!!! click here http://spam.example/x subscribe now!!!",
            "created_at": (base + timedelta(minutes=4 * i)).isoformat(),
        }
        for i in range(30)
    ]
    return {
        "profile": {
            "platform": "youtube",
            "handle": "promo_bot",
            "follower_count": 2,
            "following_count": 5000,
            "created_at": base.isoformat(),
        },
        "posts": posts,
    }


def test_score_endpoint_returns_envelope():
    resp = client.post("/v1/intelligence/score", json=_spammy_payload())
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # Phase 4 contract fields all present.
    for field in ("omi_score", "authenticity_score", "coordination_probability",
                  "amplification_probability", "spam_probability",
                  "ai_generation_probability", "risk_level"):
        assert field in body, f"missing {field}"
    assert body["risk_level"] in ("low", "medium", "high")
    assert 0 <= body["omi_score"] <= 100
    # Explainability present.
    assert body["dimensions"]
    assert "headline" in body


def test_comments_endpoint():
    payload = {
        "comments": [
            {"id": f"x{i}", "author_handle": f"u{i}",
             "text": "Check out my channel and subscribe!!! link in bio",
             "created_at": datetime.now(timezone.utc).isoformat()}
            for i in range(12)
        ],
        "context_platform": "youtube",
    }
    resp = client.post("/v1/intelligence/comments", json=payload)
    assert resp.status_code == 200, resp.text
    assert resp.json()["schema_version"] >= 1


def test_account_omiscore_404_when_never_scanned():
    resp = client.get("/v1/intelligence/account/youtube/UC_never_seen")
    assert resp.status_code == 404


def test_account_omiscore_after_scan_roundtrip():
    """Score an account through the analyze path so it's persisted, then read
    its OmiScore from the stored scan."""
    from app.schemas import Post, Profile
    from app.orchestrator import scan_account_with_memory
    from app.storage.db import get_session

    base = datetime.now(timezone.utc) - timedelta(days=1)
    profile = Profile(platform="youtube", handle="stored_bot",
                      follower_count=1, following_count=9000, created_at=base)
    posts = [
        Post(id=f"p{i}", author_handle="stored_bot",
             text="BUY NOW!!! http://x.example/deal subscribe and like!!!",
             created_at=base + timedelta(minutes=3 * i))
        for i in range(30)
    ]
    with get_session() as session:
        scan_account_with_memory(
            session, platform="youtube", external_id="UC_stored_bot",
            profile=profile, posts=posts, force_refresh=True,
        )
        session.commit()

    resp = client.get("/v1/intelligence/account/youtube/UC_stored_bot")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["subject"] == "stored_bot"
    assert 0 <= body["omi_score"] <= 100
