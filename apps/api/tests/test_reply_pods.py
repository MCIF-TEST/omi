"""Tests for the Phase C reply-tree + reply-pod detector and endpoints.

The detector is exercised in isolation (no DB) and end-to-end through
the /v1/content/{platform}/{id}/reply-tree and /reply-pods routes.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.content.service import ContentIntelligenceService
from app.detection.coordination.reply_pods import ReplyEvent, detect_reply_pods
from app.main import app
from app.storage.db import get_session


def _t(offset_sec: float = 0) -> datetime:
    return datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc) + timedelta(seconds=offset_sec)


# ---------------------------------------------------------------------------
# Detector (no DB)
# ---------------------------------------------------------------------------


def test_detect_reply_pods_returns_empty_for_no_replies():
    events = [
        ReplyEvent(comment_id="c1", parent_comment_id=None, author_external_id="alice", posted_at=_t(0)),
        ReplyEvent(comment_id="c2", parent_comment_id=None, author_external_id="bob", posted_at=_t(60)),
    ]
    assert detect_reply_pods(events) == []


def test_detect_reply_pods_finds_mutual_reply_pair():
    """Alice and Bob reply to each other's comments — both are active
    participants, so they form a coordinated pair."""
    events = [
        ReplyEvent(comment_id="x1", parent_comment_id=None, author_external_id="host", posted_at=_t(0)),
        ReplyEvent(comment_id="a1", parent_comment_id="x1", author_external_id="alice", posted_at=_t(10)),
        ReplyEvent(comment_id="b1", parent_comment_id="a1", author_external_id="bob", posted_at=_t(20)),
        ReplyEvent(comment_id="a2", parent_comment_id="b1", author_external_id="alice", posted_at=_t(30)),
        ReplyEvent(comment_id="b2", parent_comment_id="a2", author_external_id="bob", posted_at=_t(40)),
    ]
    pods = detect_reply_pods(events)
    assert len(pods) == 1
    assert set(pods[0].members) == {"alice", "bob"}
    assert pods[0].score > 0


def test_detect_reply_pods_does_not_flag_one_sided_replies():
    """An account piling replies onto someone else's top-level comments is
    NOT coordination — the recipient never engaged back. Should return no pods."""
    events = [
        ReplyEvent(comment_id="a1", parent_comment_id=None, author_external_id="alice", posted_at=_t(0)),
        ReplyEvent(comment_id="a2", parent_comment_id=None, author_external_id="alice", posted_at=_t(100)),
        ReplyEvent(comment_id="b1", parent_comment_id="a1", author_external_id="bob", posted_at=_t(10)),
        ReplyEvent(comment_id="b2", parent_comment_id="a2", author_external_id="bob", posted_at=_t(110)),
    ]
    assert detect_reply_pods(events) == []


def test_detect_reply_pods_finds_co_reply_window():
    """Three accounts all reply to the same parent within seconds. Each pair
    co-replies, giving three weight-2 edges (alice-bob, alice-carol, bob-carol)
    — clears the noise floor and forms a 3-member pod."""
    events = [
        ReplyEvent(comment_id="p1", parent_comment_id=None, author_external_id="parent", posted_at=_t(0)),
        ReplyEvent(comment_id="a1", parent_comment_id="p1", author_external_id="alice", posted_at=_t(10)),
        ReplyEvent(comment_id="b1", parent_comment_id="p1", author_external_id="bob", posted_at=_t(20)),
        ReplyEvent(comment_id="c1", parent_comment_id="p1", author_external_id="carol", posted_at=_t(30)),
        # Second batch of tight co-replies on another parent
        ReplyEvent(comment_id="p2", parent_comment_id=None, author_external_id="parent2", posted_at=_t(1000)),
        ReplyEvent(comment_id="a2", parent_comment_id="p2", author_external_id="alice", posted_at=_t(1005)),
        ReplyEvent(comment_id="b2", parent_comment_id="p2", author_external_id="bob", posted_at=_t(1010)),
        ReplyEvent(comment_id="c2", parent_comment_id="p2", author_external_id="carol", posted_at=_t(1015)),
    ]
    pods = detect_reply_pods(events)
    assert len(pods) == 1
    members = set(pods[0].members)
    # Parent author isn't in the pod — they didn't co-reply with anyone.
    assert {"alice", "bob", "carol"}.issubset(members)


def test_detect_reply_pods_ignores_single_isolated_reply():
    """One reply between two accounts is below the edge threshold."""
    events = [
        ReplyEvent(comment_id="a1", parent_comment_id=None, author_external_id="alice", posted_at=_t(0)),
        ReplyEvent(comment_id="b1", parent_comment_id="a1", author_external_id="bob", posted_at=_t(10)),
    ]
    assert detect_reply_pods(events) == []


def test_detect_reply_pods_skips_self_replies():
    """An account replying to its own comment doesn't create an edge."""
    events = [
        ReplyEvent(comment_id="a1", parent_comment_id=None, author_external_id="alice", posted_at=_t(0)),
        ReplyEvent(comment_id="a2", parent_comment_id="a1", author_external_id="alice", posted_at=_t(10)),
        ReplyEvent(comment_id="a3", parent_comment_id="a1", author_external_id="alice", posted_at=_t(20)),
    ]
    assert detect_reply_pods(events) == []


# ---------------------------------------------------------------------------
# Ingestion stores parent_comment_id + like_count
# ---------------------------------------------------------------------------


def test_record_batch_stores_reply_metadata():
    with get_session() as s:
        svc = ContentIntelligenceService(s)
        entity = svc.get_or_create_entity(platform="youtube", content_id="vidR")
        svc.record_batch(
            entity=entity, user_id=1,
            comments=[
                {"comment_id": "top1", "author_external_id": "alice", "text": "first",
                 "created_at": _t(0), "like_count": 5, "reply_count": 1},
                {"comment_id": "rep1", "parent_comment_id": "top1",
                 "author_external_id": "bob", "text": "reply", "created_at": _t(10),
                 "like_count": 0},
            ],
            handle_map={"alice": "Alice", "bob": "Bob"},
        )
        s.commit()

    with get_session() as s:
        from sqlalchemy import select
        from app.storage.models import ContentComment
        rows = {
            r.external_comment_id: r
            for r in s.execute(select(ContentComment)).scalars().all()
        }
        assert rows["top1"].parent_comment_id is None
        assert rows["top1"].like_count == 5
        assert rows["rep1"].parent_comment_id == "top1"
        assert rows["rep1"].like_count == 0


# ---------------------------------------------------------------------------
# End-to-end through the API
# ---------------------------------------------------------------------------


def _seed_video_with_reply_pod(content_id: str) -> None:
    """Set up a video where alice, bob, carol form a clear reply pod."""
    with get_session() as s:
        svc = ContentIntelligenceService(s)
        entity = svc.get_or_create_entity(platform="youtube", content_id=content_id, title="Test")
        svc.record_batch(
            entity=entity, user_id=1,
            comments=[
                {"comment_id": "p1", "parent_comment_id": None, "author_external_id": "creator",
                 "text": "Welcome to the video", "created_at": _t(0)},
                {"comment_id": "p2", "parent_comment_id": None, "author_external_id": "creator",
                 "text": "Another top comment", "created_at": _t(1000)},
                # Alice + Bob + Carol pile reply support on both top comments.
                {"comment_id": "a1", "parent_comment_id": "p1", "author_external_id": "alice",
                 "text": "Love it", "created_at": _t(5)},
                {"comment_id": "b1", "parent_comment_id": "p1", "author_external_id": "bob",
                 "text": "Agreed", "created_at": _t(15)},
                {"comment_id": "c1", "parent_comment_id": "p1", "author_external_id": "carol",
                 "text": "Same", "created_at": _t(25)},
                {"comment_id": "a2", "parent_comment_id": "p2", "author_external_id": "alice",
                 "text": "Again", "created_at": _t(1005)},
                {"comment_id": "b2", "parent_comment_id": "p2", "author_external_id": "bob",
                 "text": "Yes", "created_at": _t(1010)},
                {"comment_id": "c2", "parent_comment_id": "p2", "author_external_id": "carol",
                 "text": "Right", "created_at": _t(1015)},
            ],
            handle_map={"alice": "Alice", "bob": "Bob", "carol": "Carol", "creator": "Creator"},
        )
        s.commit()


def test_reply_tree_endpoint_returns_threaded_structure():
    _seed_video_with_reply_pod("vidT1")
    with TestClient(app) as tc:
        r = tc.get("/v1/content/youtube/vidT1/reply-tree")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["total_comments"] == 8
        assert body["top_level_count"] == 2
        assert body["reply_count"] == 6
        # Each top-level comment should have 3 nested replies.
        for root in body["roots"]:
            assert len(root["replies"]) == 3


def test_reply_pods_endpoint_finds_alice_bob_carol_pod():
    _seed_video_with_reply_pod("vidT2")
    with TestClient(app) as tc:
        r = tc.get("/v1/content/youtube/vidT2/reply-pods")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["pod_count"] == 1
        pod = body["pods"][0]
        member_ids = {m["external_id"] for m in pod["members"]}
        assert {"alice", "bob", "carol"}.issubset(member_ids)
        assert "creator" not in member_ids
        assert pod["interaction_count"] >= 3
        assert pod["score"] > 0


def test_reply_tree_endpoint_404_for_unknown_video():
    with TestClient(app) as tc:
        r = tc.get("/v1/content/youtube/does_not_exist/reply-tree")
        assert r.status_code == 404


def test_reply_pods_endpoint_returns_empty_when_no_coordination():
    """Plain comments with no replies → no pods, but endpoint still returns 200."""
    with get_session() as s:
        svc = ContentIntelligenceService(s)
        entity = svc.get_or_create_entity(platform="youtube", content_id="vidQuiet")
        svc.record_batch(
            entity=entity, user_id=1,
            comments=[
                {"comment_id": "q1", "author_external_id": "u1", "text": "hi", "created_at": _t(0)},
                {"comment_id": "q2", "author_external_id": "u2", "text": "yo", "created_at": _t(60)},
            ],
            handle_map={},
        )
        s.commit()

    with TestClient(app) as tc:
        r = tc.get("/v1/content/youtube/vidQuiet/reply-pods")
        assert r.status_code == 200
        assert r.json()["pod_count"] == 0
