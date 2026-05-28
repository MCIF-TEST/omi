"""Tests for the Universal Content Intelligence Database (Phase 10)."""

from __future__ import annotations

import pytest
from datetime import datetime, timedelta, timezone

from app.content.service import ContentIntelligenceService
from app.storage.db import get_session


def _t(offset_minutes: float = 0) -> datetime:
    return datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc) + timedelta(minutes=offset_minutes)


def _comment(comment_id: str, author: str, text: str = "hello", offset_min: float = 0) -> dict:
    return {
        "comment_id": comment_id,
        "author_external_id": author,
        "text": text,
        "created_at": _t(offset_min),
    }


# ---------------------------------------------------------------------------
# Entity creation
# ---------------------------------------------------------------------------


def test_get_or_create_entity_is_idempotent():
    """Calling get_or_create twice with the same key returns the same row."""
    with get_session() as s:
        svc = ContentIntelligenceService(s)
        e1 = svc.get_or_create_entity(platform="youtube", content_id="vid_a", title="First title")
        s.commit()
        e1_id = e1.id

    with get_session() as s:
        svc = ContentIntelligenceService(s)
        e2 = svc.get_or_create_entity(platform="youtube", content_id="vid_a")
        s.commit()
        assert e2.id == e1_id


def test_get_or_create_entity_keyed_on_platform_and_id():
    """Same content_id on different platforms is two distinct entities."""
    with get_session() as s:
        svc = ContentIntelligenceService(s)
        yt = svc.get_or_create_entity(platform="youtube", content_id="123")
        x = svc.get_or_create_entity(platform="x", content_id="123")
        s.commit()
        assert yt.id != x.id


def test_get_or_create_entity_fills_metadata_opportunistically():
    """First scan has no title; later scan fills it without overwriting later ones."""
    with get_session() as s:
        svc = ContentIntelligenceService(s)
        svc.get_or_create_entity(platform="youtube", content_id="v1")    # no title
        s.commit()

    with get_session() as s:
        svc = ContentIntelligenceService(s)
        e = svc.get_or_create_entity(platform="youtube", content_id="v1", title="Now I have one")
        s.commit()
        assert e.title == "Now I have one"

    # A third call with a different title should NOT overwrite a populated one
    with get_session() as s:
        svc = ContentIntelligenceService(s)
        e = svc.get_or_create_entity(platform="youtube", content_id="v1", title="Different")
        s.commit()
        assert e.title == "Now I have one"


# ---------------------------------------------------------------------------
# Batch recording
# ---------------------------------------------------------------------------


def test_record_batch_creates_comments_and_counters():
    with get_session() as s:
        svc = ContentIntelligenceService(s)
        e = svc.get_or_create_entity(platform="youtube", content_id="v1")
        s.commit()
        eid = e.id

    with get_session() as s:
        svc = ContentIntelligenceService(s)
        e = svc.get_entity_by_platform_id("youtube", "v1")
        batch = svc.record_batch(
            entity=e,
            user_id=1,
            comments=[
                _comment("c1", "alice", "hello world"),
                _comment("c2", "bob", "another comment"),
                _comment("c3", "alice", "alice again"),
            ],
            handle_map={"alice": "Alice", "bob": "Bob"},
            coordination_score=0.42,
            risk_tier="moderate",
            tier_distribution={"low": 1, "moderate": 2},
        )
        s.commit()

        assert batch.comments_fetched == 3
        assert batch.new_comments == 3
        assert batch.duplicates == 0
        assert batch.distinct_authors == 2     # alice and bob
        assert batch.new_authors == 2

    # Reload entity, verify cumulative counters
    with get_session() as s:
        svc = ContentIntelligenceService(s)
        e = svc.get_entity_by_platform_id("youtube", "v1")
        assert e.total_batches == 1
        assert e.total_comments_collected == 3
        assert e.total_distinct_authors == 2
        assert e.contributor_count == 1
        assert e.latest_coordination_score == 0.42
        assert e.latest_risk_tier == "moderate"
        assert e.latest_tier_distribution == {"low": 1, "moderate": 2}


def test_record_batch_deduplicates_existing_comments():
    """A second batch with overlapping comment_ids reports them as duplicates,
    not new — and the total_comments_collected on the entity reflects this."""
    with get_session() as s:
        svc = ContentIntelligenceService(s)
        e = svc.get_or_create_entity(platform="youtube", content_id="v1")
        svc.record_batch(
            entity=e, user_id=1,
            comments=[_comment("c1", "a"), _comment("c2", "b")],
            handle_map={},
        )
        s.commit()

    with get_session() as s:
        svc = ContentIntelligenceService(s)
        e = svc.get_entity_by_platform_id("youtube", "v1")
        batch = svc.record_batch(
            entity=e, user_id=1,
            comments=[
                _comment("c1", "a"),    # dup
                _comment("c2", "b"),    # dup
                _comment("c3", "c"),    # new
            ],
            handle_map={},
        )
        s.commit()
        assert batch.comments_fetched == 3
        assert batch.new_comments == 1
        assert batch.duplicates == 2
        assert batch.distinct_authors == 3
        assert batch.new_authors == 1

    # Entity cumulative: only 3 unique comments overall (c1, c2, c3)
    with get_session() as s:
        svc = ContentIntelligenceService(s)
        e = svc.get_entity_by_platform_id("youtube", "v1")
        assert e.total_batches == 2
        assert e.total_comments_collected == 3   # 2 + 1 new
        assert e.total_distinct_authors == 3


def test_contributor_count_increments_only_for_new_users():
    with get_session() as s:
        svc = ContentIntelligenceService(s)
        e = svc.get_or_create_entity(platform="youtube", content_id="v1")
        svc.record_batch(entity=e, user_id=1, comments=[_comment("c1", "a")], handle_map={})
        s.commit()

    with get_session() as s:
        svc = ContentIntelligenceService(s)
        e = svc.get_entity_by_platform_id("youtube", "v1")
        # Same user re-scanning → contributor_count stays at 1
        svc.record_batch(entity=e, user_id=1, comments=[_comment("c2", "a")], handle_map={})
        s.commit()
        assert e.contributor_count == 1

    with get_session() as s:
        svc = ContentIntelligenceService(s)
        e = svc.get_entity_by_platform_id("youtube", "v1")
        # Different user scanning → contributor_count goes to 2
        svc.record_batch(entity=e, user_id=2, comments=[_comment("c3", "a")], handle_map={})
        s.commit()
        assert e.contributor_count == 2


def test_record_batch_stores_continuation_token():
    with get_session() as s:
        svc = ContentIntelligenceService(s)
        e = svc.get_or_create_entity(platform="youtube", content_id="v1")
        batch = svc.record_batch(
            entity=e, user_id=1, comments=[_comment("c1", "a")],
            handle_map={}, next_page_token="cursor-abc",
        )
        s.commit()
        assert batch.next_page_token == "cursor-abc"


def test_latest_next_page_token_picks_most_recent_non_null():
    """The newest batch with a non-null cursor is what a rescan should resume from."""
    with get_session() as s:
        svc = ContentIntelligenceService(s)
        e = svc.get_or_create_entity(platform="youtube", content_id="v1")
        eid = e.id
        svc.record_batch(entity=e, user_id=1, comments=[_comment("c1", "a")],
                         handle_map={}, next_page_token="old")
        s.commit()

    with get_session() as s:
        svc = ContentIntelligenceService(s)
        e = svc.get_entity_by_platform_id("youtube", "v1")
        svc.record_batch(entity=e, user_id=1, comments=[_comment("c2", "a")],
                         handle_map={}, next_page_token="newer")
        s.commit()
        assert svc.latest_next_page_token(eid) == "newer"

    # A later batch with NULL token (exhausted) should not override the latest valid one
    with get_session() as s:
        svc = ContentIntelligenceService(s)
        e = svc.get_entity_by_platform_id("youtube", "v1")
        svc.record_batch(entity=e, user_id=1, comments=[_comment("c3", "a")],
                         handle_map={}, next_page_token=None)
        s.commit()
        # Newer non-null wins; the NULL batch is ignored.
        assert svc.latest_next_page_token(eid) == "newer"


def test_record_batch_skips_blank_comment_id_and_text():
    """Garbage from a flaky integration shouldn't pollute the database."""
    with get_session() as s:
        svc = ContentIntelligenceService(s)
        e = svc.get_or_create_entity(platform="youtube", content_id="v1")
        batch = svc.record_batch(
            entity=e, user_id=1,
            comments=[
                _comment("c1", "a", "real"),
                {"comment_id": "", "author_external_id": "a", "text": "no id"},
                {"comment_id": "c2", "author_external_id": "a", "text": ""},
                _comment("c3", "b", "also real"),
            ],
            handle_map={},
        )
        s.commit()
        assert batch.new_comments == 2   # only c1 and c3 survive


# ---------------------------------------------------------------------------
# List / query
# ---------------------------------------------------------------------------


def test_list_entities_filters_by_platform_risk_and_search():
    with get_session() as s:
        svc = ContentIntelligenceService(s)
        for cid, plat, tier, title in [
            ("v1", "youtube", "low", "Cooking with Cats"),
            ("v2", "youtube", "elevated", "Election Fraud Conspiracy"),
            ("v3", "youtube", "high", "Vaccine Misinformation Hub"),
            ("x1", "x", "moderate", "Tweet about cats"),
        ]:
            e = svc.get_or_create_entity(platform=plat, content_id=cid, title=title)
            e.latest_risk_tier = tier
            e.latest_coordination_score = {"low": 0.05, "moderate": 0.3, "elevated": 0.6, "high": 0.85}[tier]
        s.commit()

    with get_session() as s:
        svc = ContentIntelligenceService(s)

        # No filters — everything
        total, rows = svc.list_entities()
        assert total == 4

        # Platform filter
        total, rows = svc.list_entities(platform="x")
        assert total == 1
        assert rows[0].content_id == "x1"

        # Risk filter: moderate+
        total, rows = svc.list_entities(min_risk_tier="moderate")
        assert total == 3   # excludes the low one

        # Risk filter: high (= internal "elevated")
        total, rows = svc.list_entities(min_risk_tier="elevated")
        assert total == 2

        # Search title
        total, rows = svc.list_entities(search="cats")
        assert total == 2   # "Cooking with Cats" + "Tweet about cats"

        # Combined: platform + search
        total, rows = svc.list_entities(platform="youtube", search="cats")
        assert total == 1
        assert rows[0].content_id == "v1"

        # Search by content_id
        total, rows = svc.list_entities(search="v2")
        assert total == 1


def test_get_batches_and_get_comments_paginate():
    with get_session() as s:
        svc = ContentIntelligenceService(s)
        e = svc.get_or_create_entity(platform="youtube", content_id="v1")
        eid = e.id
        for i in range(5):
            svc.record_batch(
                entity=e, user_id=1,
                comments=[_comment(f"b{i}_c{j}", f"user_{j}", offset_min=i * 60 + j) for j in range(3)],
                handle_map={},
            )
        s.commit()

    with get_session() as s:
        svc = ContentIntelligenceService(s)
        batches = svc.get_batches(eid, limit=10)
        assert len(batches) == 5
        # Should be newest-first
        assert batches[0].fetched_at >= batches[-1].fetched_at

        total, comments = svc.get_comments(eid, limit=5)
        assert total == 15   # 5 batches × 3 comments
        assert len(comments) == 5


# ---------------------------------------------------------------------------
# Author presence
# ---------------------------------------------------------------------------


def test_get_author_presence_aggregates_across_entities():
    """An author commenting on three different videos shows up with content_count=3."""
    with get_session() as s:
        svc = ContentIntelligenceService(s)
        for cid in ["v1", "v2", "v3"]:
            e = svc.get_or_create_entity(platform="youtube", content_id=cid, title=f"Video {cid}")
            svc.record_batch(
                entity=e, user_id=1,
                comments=[
                    _comment(f"{cid}_a", "alice", f"alice on {cid}", offset_min=0),
                    _comment(f"{cid}_a2", "alice", f"alice again on {cid}", offset_min=10),
                    _comment(f"{cid}_b", "bob", f"bob on {cid}", offset_min=20),
                ],
                handle_map={"alice": "Alice", "bob": "Bob"},
            )
        s.commit()

    with get_session() as s:
        svc = ContentIntelligenceService(s)
        data = svc.get_author_presence("youtube", "alice")
        assert data["content_count"] == 3
        assert data["total_comments"] == 6      # 2 per video × 3 videos
        assert data["author_handle"] == "Alice"
        assert len(data["entities"]) == 3
        # Each entity row has the right count
        for row in data["entities"]:
            assert row["comment_count"] == 2


def test_get_author_comments_returns_every_comment_with_entity():
    """get_author_comments returns the raw comments (not aggregated) with the
    content entity attached. Used by the account page to show real comments."""
    with get_session() as s:
        svc = ContentIntelligenceService(s)
        for cid in ["v1", "v2"]:
            e = svc.get_or_create_entity(platform="youtube", content_id=cid, title=f"Video {cid}")
            svc.record_batch(
                entity=e, user_id=1,
                comments=[
                    _comment(f"{cid}_a1", "alice", f"alice first on {cid}", offset_min=0),
                    _comment(f"{cid}_a2", "alice", f"alice second on {cid}", offset_min=10),
                    _comment(f"{cid}_b1", "bob", f"bob on {cid}", offset_min=20),
                ],
                handle_map={"alice": "Alice"},
            )
        s.commit()

    with get_session() as s:
        svc = ContentIntelligenceService(s)
        total, rows = svc.get_author_comments("youtube", "alice", limit=100)
        assert total == 4  # 2 per video × 2 videos
        assert len(rows) == 4
        # Newest first
        observed = [c.observed_at for c, _e in rows]
        assert observed == sorted(observed, reverse=True)
        # Every row carries its entity
        for c, e in rows:
            assert c.author_external_id == "alice"
            assert e.platform == "youtube"
            assert e.content_id in ("v1", "v2")


def test_get_author_comments_respects_limit():
    with get_session() as s:
        svc = ContentIntelligenceService(s)
        e = svc.get_or_create_entity(platform="youtube", content_id="v1", title="V1")
        svc.record_batch(
            entity=e, user_id=1,
            comments=[_comment(f"c{i}", "alice", f"msg {i}", offset_min=i) for i in range(20)],
            handle_map={"alice": "Alice"},
        )
        s.commit()

    with get_session() as s:
        svc = ContentIntelligenceService(s)
        total, rows = svc.get_author_comments("youtube", "alice", limit=5)
        # Total is unfiltered; rows respects the limit
        assert total == 20
        assert len(rows) == 5


def test_get_author_comments_returns_empty_when_no_matches():
    with get_session() as s:
        svc = ContentIntelligenceService(s)
        total, rows = svc.get_author_comments("youtube", "ghost", limit=10)
        assert total == 0
        assert rows == []


def test_get_author_presence_empty_returns_zero_counts():
    with get_session() as s:
        svc = ContentIntelligenceService(s)
        data = svc.get_author_presence("youtube", "never_commented")
        assert data["total_comments"] == 0
        assert data["content_count"] == 0
        assert data["entities"] == []
        assert data["first_seen"] is None


def test_diff_batches_no_diff_when_only_one_batch():
    with get_session() as s:
        svc = ContentIntelligenceService(s)
        e = svc.get_or_create_entity(platform="youtube", content_id="v1")
        svc.record_batch(
            entity=e, user_id=1,
            comments=[_comment("c1", "a")],
            handle_map={},
            coordination_score=0.1, risk_tier="low",
            tier_distribution={"low": 1},
        )
        s.commit()
        assert svc.diff_batches(e.id) is None


def test_diff_batches_compares_newest_two_by_default():
    with get_session() as s:
        svc = ContentIntelligenceService(s)
        e = svc.get_or_create_entity(platform="youtube", content_id="v1")
        svc.record_batch(
            entity=e, user_id=1,
            comments=[_comment("c1", "alice"), _comment("c2", "bob")],
            handle_map={},
            coordination_score=0.1, risk_tier="low",
            tier_distribution={"low": 2},
        )
        s.commit()

    with get_session() as s:
        svc = ContentIntelligenceService(s)
        e = svc.get_entity_by_platform_id("youtube", "v1")
        svc.record_batch(
            entity=e, user_id=1,
            comments=[
                _comment("c1", "alice"),    # dup
                _comment("c2", "bob"),      # dup
                _comment("c3", "charlie"),  # NEW comment + NEW author
                _comment("c4", "alice"),    # NEW comment, EXISTING author
            ],
            handle_map={},
            coordination_score=0.45, risk_tier="elevated",
            tier_distribution={"low": 2, "moderate": 1, "elevated": 1},
        )
        s.commit()
        eid = e.id

    with get_session() as s:
        svc = ContentIntelligenceService(s)
        d = svc.diff_batches(eid)
        assert d is not None
        assert d["coordination_score_delta"] == pytest.approx(0.35, abs=1e-6)
        assert d["risk_tier_changed"] is True
        assert d["new_comment_count"] == 2     # c3 + c4
        assert d["new_author_count"] == 1      # only charlie
        assert "charlie" in d["new_authors"]
        # Tier distribution went up in elevated, low stayed
        td = d["tier_distribution_delta"]
        assert td.get("elevated", 0) == 1
        assert td.get("moderate", 0) == 1
        assert td.get("low", 0) == 0


def test_diff_batches_explicit_from_and_to_ids():
    with get_session() as s:
        svc = ContentIntelligenceService(s)
        e = svc.get_or_create_entity(platform="youtube", content_id="v1")
        b1 = svc.record_batch(entity=e, user_id=1, comments=[_comment("c1", "a")], handle_map={})
        b2 = svc.record_batch(entity=e, user_id=1, comments=[_comment("c2", "b")], handle_map={})
        b3 = svc.record_batch(entity=e, user_id=1, comments=[_comment("c3", "c")], handle_map={})
        s.commit()
        eid = e.id
        # Diff b1→b3 (skip b2): should still find the diff
        d = svc.diff_batches(eid, from_batch_id=b1.id, to_batch_id=b3.id)
        assert d is not None
        assert d["from_batch"].id == b1.id
        assert d["to_batch"].id == b3.id


def test_get_author_presence_isolates_by_platform():
    """Same external_id on different platforms shouldn't be merged."""
    with get_session() as s:
        svc = ContentIntelligenceService(s)
        e1 = svc.get_or_create_entity(platform="youtube", content_id="v1")
        e2 = svc.get_or_create_entity(platform="x", content_id="x1")
        svc.record_batch(entity=e1, user_id=1, comments=[_comment("c1", "samename")], handle_map={})
        svc.record_batch(entity=e2, user_id=1, comments=[_comment("c2", "samename")], handle_map={})
        s.commit()

        yt_presence = svc.get_author_presence("youtube", "samename")
        x_presence = svc.get_author_presence("x", "samename")
        assert yt_presence["content_count"] == 1
        assert x_presence["content_count"] == 1
        assert yt_presence["entities"][0]["entity"].platform == "youtube"
        assert x_presence["entities"][0]["entity"].platform == "x"
