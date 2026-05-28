"""Tests for the /v1/channels/{platform}/{external_id}/intelligence endpoint.

Covers channel-level aggregation: audience composition, top repeat commenters,
engagement velocity, returning-commenter ratio, and the 404/empty cases.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.content.service import ContentIntelligenceService
from app.main import app
from app.schemas import Profile, ScanResult, SignalResult, Tier
from app.storage.db import get_session
from app.storage.repository import AccountRepository


CHANNEL_ID = "UC" + "C" * 22


def _t(offset_min: float = 0) -> datetime:
    return datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc) + timedelta(minutes=offset_min)


def _comment(comment_id: str, author: str, text: str = "hi", offset_min: float = 0) -> dict:
    return {
        "comment_id": comment_id,
        "author_external_id": author,
        "text": text,
        "created_at": _t(offset_min),
    }


def _seed_account(external_id: str, *, handle: str, tier: Tier, probability: float) -> None:
    with get_session() as session:
        repo = AccountRepository(session)
        repo.upsert_with_scan(
            platform="youtube",
            external_id=external_id,
            profile=Profile(platform="youtube", handle=handle, display_name=handle),
            scan=ScanResult(
                overall_probability=probability,
                confidence=0.7,
                tier=tier,
                signals=[SignalResult(name="temporal", probability=probability, confidence=0.5)],
                summary=f"{handle} scan",
            ),
            fingerprint=[0.1] * 19,
        )


def _seed_video(content_id: str, *, coordination: float, risk_tier: str,
                tier_distribution: dict[str, int], commenters: list[str],
                title: str = "Video title") -> None:
    """Create a ContentEntity owned by CHANNEL_ID and a batch with the given
    commenters. Also records CommenterEngagement edges so the top-commenters
    query can find them."""
    with get_session() as session:
        svc = ContentIntelligenceService(session)
        entity = svc.get_or_create_entity(
            platform="youtube",
            content_id=content_id,
            title=title,
            author_external_id=CHANNEL_ID,
            author_handle="@TestChannel",
        )
        session.commit()

    with get_session() as session:
        svc = ContentIntelligenceService(session)
        entity = svc.get_entity_by_platform_id("youtube", content_id)
        svc.record_batch(
            entity=entity,
            user_id=1,
            comments=[_comment(f"{content_id}_c{i}", commenter) for i, commenter in enumerate(commenters)],
            handle_map={c: c for c in commenters},
            coordination_score=coordination,
            risk_tier=risk_tier,
            tier_distribution=tier_distribution,
        )
        session.commit()

    # Record CommenterEngagement edges so top-commenter aggregation works.
    with get_session() as session:
        repo = AccountRepository(session)
        for commenter in set(commenters):
            repo.record_engagement_edges(
                platform="youtube",
                account_external_id=commenter,
                parent_ids=[content_id],
            )
        session.commit()


# ---------------------------------------------------------------------------
# 404 case
# ---------------------------------------------------------------------------


def test_channel_intelligence_returns_404_when_no_data():
    with TestClient(app) as tc:
        r = tc.get(f"/v1/channels/youtube/{CHANNEL_ID}/intelligence")
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# Basic shape + audience composition
# ---------------------------------------------------------------------------


def test_channel_intelligence_aggregates_audience_composition():
    _seed_video(
        "vid_a", coordination=0.3, risk_tier="moderate",
        tier_distribution={"low": 10, "moderate": 5, "elevated": 2, "high": 1},
        commenters=["alice", "bob", "carol"],
    )
    _seed_video(
        "vid_b", coordination=0.6, risk_tier="elevated",
        tier_distribution={"low": 4, "moderate": 8, "elevated": 6, "high": 3},
        commenters=["alice", "dave"],
    )

    with TestClient(app) as tc:
        r = tc.get(f"/v1/channels/youtube/{CHANNEL_ID}/intelligence")
        assert r.status_code == 200, r.text
        body = r.json()

        assert body["platform"] == "youtube"
        assert body["external_id"] == CHANNEL_ID
        assert body["video_count"] == 2

        comp = body["audience_composition"]
        assert comp["low"] == 14
        assert comp["moderate"] == 13
        assert comp["elevated"] == 8
        assert comp["high"] == 4
        assert comp["total_commenters"] == 39

        # Videos sorted by coordination score descending
        videos = body["videos"]
        assert len(videos) == 2
        assert videos[0]["content_id"] == "vid_b"
        assert videos[0]["latest_tier_distribution"]["high"] == 3
        assert videos[1]["content_id"] == "vid_a"


# ---------------------------------------------------------------------------
# Top repeat commenters across videos
# ---------------------------------------------------------------------------


def test_top_commenters_ranked_by_video_count():
    # alice appears on all 3 videos; bob on 2; carol on 1
    _seed_video("vid_1", coordination=0.4, risk_tier="moderate",
                tier_distribution={"low": 2}, commenters=["alice", "bob", "carol"])
    _seed_video("vid_2", coordination=0.5, risk_tier="moderate",
                tier_distribution={"low": 2}, commenters=["alice", "bob"])
    _seed_video("vid_3", coordination=0.6, risk_tier="elevated",
                tier_distribution={"low": 2}, commenters=["alice"])

    # Give alice a scan so we can verify the tier comes through
    _seed_account("alice", handle="@AliceBot", tier=Tier.HIGH, probability=0.9)

    with TestClient(app) as tc:
        r = tc.get(f"/v1/channels/youtube/{CHANNEL_ID}/intelligence")
        assert r.status_code == 200, r.text
        body = r.json()

        top = body["top_commenters"]
        assert len(top) == 3
        assert top[0]["external_id"] == "alice"
        assert top[0]["video_count"] == 3
        assert top[0]["tier"] == "high"
        assert top[0]["overall_probability"] == pytest.approx(0.9)
        assert top[0]["handle"] == "@AliceBot"

        assert top[1]["external_id"] == "bob"
        assert top[1]["video_count"] == 2
        # bob never got a standalone scan; fallback handle = external_id
        assert top[1]["tier"] is None


# ---------------------------------------------------------------------------
# Engagement velocity + returning-commenter ratio
# ---------------------------------------------------------------------------


def test_engagement_velocity_and_returning_ratio():
    # 2 videos, 3 + 5 = 8 comments → avg 4.0
    # 4 distinct commenters (alice, bob, carol, dave); alice + bob on both → 2/4 = 0.5
    _seed_video("vid_x", coordination=0.2, risk_tier="low",
                tier_distribution={"low": 3}, commenters=["alice", "bob", "carol"])
    _seed_video("vid_y", coordination=0.4, risk_tier="moderate",
                tier_distribution={"low": 5}, commenters=["alice", "bob", "dave", "eve", "frank"])

    with TestClient(app) as tc:
        r = tc.get(f"/v1/channels/youtube/{CHANNEL_ID}/intelligence")
        assert r.status_code == 200, r.text
        body = r.json()

        assert body["avg_comments_per_video"] == pytest.approx(4.0)
        # 2 returning (alice, bob) out of 6 distinct = 0.333...
        assert body["returning_commenter_ratio"] == pytest.approx(2 / 6, rel=1e-3)


# ---------------------------------------------------------------------------
# Risk trend reflects batch chronology
# ---------------------------------------------------------------------------


def test_risk_trend_returns_batch_chronology():
    _seed_video("vid_t", coordination=0.7, risk_tier="elevated",
                tier_distribution={"low": 1}, commenters=["x"])

    with TestClient(app) as tc:
        r = tc.get(f"/v1/channels/youtube/{CHANNEL_ID}/intelligence")
        body = r.json()
        trend = body["risk_trend"]
        assert len(trend) == 1
        assert trend[0]["content_id"] == "vid_t"
        assert trend[0]["coordination_score"] == pytest.approx(0.7)
        assert trend[0]["risk_tier"] == "elevated"
