"""Tests for the cross-account coordination detectors and the unified
``/v1/scan/youtube/full`` endpoint."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.detection.coordination import (
    detect_age_cohorts,
    detect_co_engagement,
    detect_fingerprint_clusters,
    detect_style_matches,
    detect_temporal_semantic_cliques,
)
from app.detection.coordination.cohort import CohortEntry
from app.detection.coordination.co_engagement import EngagementEntry
from app.detection.coordination.fingerprint_cluster import FingerprintEntry
from app.detection.coordination.style_match import StyleEntry
from app.detection.coordination.temporal_semantic import CommentEntry
from app.detection.voice import analyze_voice
from app.main import app
from app.memory.fingerprint import FINGERPRINT_DIM
from app.routes.scan import set_client_factory_for_tests
from app.schemas import Post
from app.storage.db import reset_db_for_tests
from tests.test_youtube_integration import (
    FakeYouTubeClient,
    _channel_profile,
    _history_item,
    _make_bot_history,
    _make_human_history,
    _video_comment_item,
)


# ---------------------------------------------------------------------------
# Temporal-semantic cliques
# ---------------------------------------------------------------------------


def test_temporal_semantic_flags_coordinated_burst():
    base = datetime(2025, 1, 1, 12, 0, tzinfo=timezone.utc)
    text = "Big news today! Don't miss this. Share to spread the truth!"
    comments = [
        CommentEntry(
            comment_id=f"c{i}", author_external_id=f"UC_bot_{i}",
            text=text, created_at=base + timedelta(seconds=15 * i),
        )
        for i in range(5)
    ]
    # Plus three unrelated human comments far apart in time.
    comments += [
        CommentEntry(
            comment_id="h1", author_external_id="UC_h1",
            text="great editing on this one, what software?",
            created_at=base + timedelta(hours=4),
        ),
        CommentEntry(
            comment_id="h2", author_external_id="UC_h2",
            text="the cat at the end is a vibe",
            created_at=base + timedelta(hours=6),
        ),
        CommentEntry(
            comment_id="h3", author_external_id="UC_h3",
            text="agree with everything you said about the camera",
            created_at=base + timedelta(hours=8),
        ),
    ]
    finding = detect_temporal_semantic_cliques(comments)
    assert finding.clusters
    cluster = finding.clusters[0]
    assert len(cluster.members) >= 3
    assert all(m.startswith("UC_bot_") for m in cluster.members)
    assert finding.overall_score > 0.5


def test_temporal_semantic_clean_thread_returns_no_cluster():
    base = datetime(2025, 1, 1, 12, 0, tzinfo=timezone.utc)
    diverse_texts = [
        "great editing, what software did you use",
        "the dog in the b-roll absolutely stole the show",
        "respectfully disagree with the conclusion but loved the data",
        "any chance you'll do a deeper dive on point 3",
        "the audio mix is so much better in this one",
        "is the playlist linked anywhere",
        "first time hearing about this — going to look it up",
    ]
    comments = [
        CommentEntry(
            comment_id=f"c{i}", author_external_id=f"UC_h{i}",
            text=diverse_texts[i % len(diverse_texts)],
            created_at=base + timedelta(minutes=30 * i),  # spread over hours
        )
        for i in range(7)
    ]
    finding = detect_temporal_semantic_cliques(comments)
    assert finding.clusters == []


# ---------------------------------------------------------------------------
# Fingerprint clustering
# ---------------------------------------------------------------------------


def test_fingerprint_cluster_flags_bot_family():
    # 4 accounts with very similar high-suspicion fingerprints, plus 2 random.
    bot_fp = [0.9] * FINGERPRINT_DIM
    entries = [
        FingerprintEntry(
            external_id=f"UC_bot_{i}", handle=f"bot_{i}",
            fingerprint=bot_fp, individual_probability=0.8,
        )
        for i in range(4)
    ] + [
        FingerprintEntry(
            external_id="UC_h1", handle="h1",
            fingerprint=[0.2] * FINGERPRINT_DIM, individual_probability=0.15,
        ),
        FingerprintEntry(
            external_id="UC_h2", handle="h2",
            fingerprint=[0.3] * FINGERPRINT_DIM, individual_probability=0.20,
        ),
    ]
    finding = detect_fingerprint_clusters(entries)
    assert len(finding.clusters) == 1
    cluster = finding.clusters[0]
    assert set(cluster.members) == {f"UC_bot_{i}" for i in range(4)}
    assert cluster.score > 0.5


def test_fingerprint_cluster_ignores_low_probability_clusters():
    # 4 accounts with similar fingerprints BUT low individual probability —
    # not actually suspicious, just normal users who happen to look alike.
    fp = [0.2] * FINGERPRINT_DIM
    entries = [
        FingerprintEntry(
            external_id=f"UC_{i}", handle=f"u_{i}",
            fingerprint=fp, individual_probability=0.10,
        )
        for i in range(4)
    ]
    finding = detect_fingerprint_clusters(entries)
    assert finding.clusters == []


# ---------------------------------------------------------------------------
# Account-age cohort
# ---------------------------------------------------------------------------


def test_cohort_flags_narrow_creation_window():
    # 10 commenters: 7 created in early Jan 2025, 3 spread across years.
    narrow = datetime(2025, 1, 5, tzinfo=timezone.utc)
    entries = [
        CohortEntry(external_id=f"UC_bot_{i}", handle=f"bot_{i}",
                    created_at=narrow + timedelta(days=i))
        for i in range(7)
    ] + [
        CohortEntry(external_id="UC_h1", handle="h1",
                    created_at=datetime(2014, 6, 1, tzinfo=timezone.utc)),
        CohortEntry(external_id="UC_h2", handle="h2",
                    created_at=datetime(2018, 3, 15, tzinfo=timezone.utc)),
        CohortEntry(external_id="UC_h3", handle="h3",
                    created_at=datetime(2022, 11, 1, tzinfo=timezone.utc)),
    ]
    finding = detect_age_cohorts(entries)
    assert finding.clusters
    cluster = finding.clusters[0]
    assert len(cluster.members) >= 5
    assert finding.overall_score > 0.6


def test_cohort_does_not_flag_spread_distribution():
    entries = [
        CohortEntry(
            external_id=f"UC_{i}", handle=f"u_{i}",
            created_at=datetime(2015 + i, 6, 1, tzinfo=timezone.utc),
        )
        for i in range(8)
    ]
    finding = detect_age_cohorts(entries)
    assert finding.clusters == []


# ---------------------------------------------------------------------------
# Linguistic style match
# ---------------------------------------------------------------------------


def test_style_match_flags_same_writer_across_accounts():
    # Three accounts all writing in the same heavy-AI-tells style.
    ai_template = [
        "It's worth noting — moreover, in today's fast-paced world — that "
        "this tapestry of considerations underscores the multifaceted nature "
        "of the discussion. Furthermore, navigating the realm requires nuance.",
        "Additionally, it's important to delve into the ever-evolving "
        "landscape. Moreover, in conclusion, vigilance underscores success.",
    ]
    entries = [
        StyleEntry(external_id=f"UC_sock_{i}", handle=f"sock_{i}", texts=ai_template)
        for i in range(3)
    ]
    # Plus a human-voice account.
    human_text = [
        "ok i don't normally rant about this but the bus driver this morning "
        "literally drove past me lol. it's gonna be one of those days.",
        "the new album is fine, just fine, that's the review. moving on.",
    ]
    entries.append(StyleEntry(external_id="UC_h", handle="h", texts=human_text))
    finding = detect_style_matches(entries)
    assert any(set(c.members) == {f"UC_sock_{i}" for i in range(3)} for c in finding.clusters)


# ---------------------------------------------------------------------------
# Co-engagement / fellow travelers
# ---------------------------------------------------------------------------


def test_co_engagement_flags_overlapping_video_history():
    # 3 bots who have all appeared on the same 5 other videos.
    shared = {f"vid_{i}" for i in range(5)}
    entries = [
        EngagementEntry(
            external_id=f"UC_bot_{i}", handle=f"bot_{i}",
            engaged_video_ids=shared | {f"unique_{i}"},
        )
        for i in range(3)
    ]
    # Plus 2 randoms whose video histories don't overlap with each other.
    entries.append(EngagementEntry(
        external_id="UC_h1", handle="h1",
        engaged_video_ids={"some_video", "other_video"},
    ))
    entries.append(EngagementEntry(
        external_id="UC_h2", handle="h2",
        engaged_video_ids={"random_a", "random_b", "random_c"},
    ))
    finding = detect_co_engagement(entries, min_shared_videos=3)
    assert len(finding.clusters) == 1
    cluster = finding.clusters[0]
    assert set(cluster.members) == {f"UC_bot_{i}" for i in range(3)}
    assert finding.overall_score > 0.5


def test_co_engagement_returns_nothing_for_independent_users():
    entries = [
        EngagementEntry(external_id=f"UC_{i}", handle=f"u_{i}",
                        engaged_video_ids={f"unique_to_{i}_{j}" for j in range(5)})
        for i in range(5)
    ]
    finding = detect_co_engagement(entries)
    assert finding.clusters == []


# ---------------------------------------------------------------------------
# Voice detector
# ---------------------------------------------------------------------------


def test_voice_neutral_on_human_youtube_comments():
    base = datetime(2025, 1, 1, tzinfo=timezone.utc)
    text = (
        "I just rewatched this and I have to say, it hits even harder the "
        "second time. I felt the same way about the ending — we don't get "
        "many channels that take that kind of risk. My only nitpick is the "
        "audio mix at the 12-minute mark, but honestly we're spoiled."
    )
    posts = [Post(id=str(i), author_handle="h", text=text,
                  created_at=base + timedelta(days=i)) for i in range(10)]
    sig = analyze_voice(posts)
    assert sig.probability < 0.5


def test_voice_flags_impersonal_long_form():
    base = datetime(2025, 1, 1, tzinfo=timezone.utc)
    # Long-form impersonal text with zero first-person pronouns.
    text = (
        "The video raises important considerations regarding the current "
        "landscape. The arguments presented warrant careful examination. "
        "Many readers will find the conclusions broadly applicable to a "
        "range of contemporary scenarios. The presentation deserves wider "
        "circulation given how clearly it lays out the underlying patterns. "
        "Anyone interested in this domain should consider sharing this work."
    )
    posts = [Post(id=str(i), author_handle="b", text=text,
                  created_at=base + timedelta(days=i)) for i in range(8)]
    sig = analyze_voice(posts)
    assert sig.confidence > 0.2
    assert sig.probability > 0.5


# ---------------------------------------------------------------------------
# /v1/scan/youtube/full — unified endpoint, end-to-end
# ---------------------------------------------------------------------------


@pytest.fixture
def client_with_db():
    get_settings.cache_clear()
    reset_db_for_tests("sqlite:///:memory:")
    with TestClient(app) as tc:
        yield tc
    set_client_factory_for_tests(None)
    reset_db_for_tests("sqlite:///:memory:")


def test_full_scan_returns_coordination_signal_for_botted_video(client_with_db):
    # Set up a video where 4 bot accounts all post nearly-identical comments
    # within 30 seconds of each other, plus one human commenter who's clean.
    bot_ids = [f"UC_burst_bot_{i}" for i in range(4)]
    human_id = "UC_normal_aaa"
    base = "2025-05-01T12:00:00Z"

    # The video's comment thread: all bot comments arrive in the same minute,
    # the human's comment 6 hours later.
    burst_comment_items = []
    for i, bid in enumerate(bot_ids):
        burst_comment_items.append({
            "snippet": {
                "topLevelComment": {
                    "id": f"comment_burst_{i}",
                    "snippet": {
                        "authorChannelId": {"value": bid},
                        "authorDisplayName": f"burst_{i}",
                        "authorProfileImageUrl": "https://x/" + bid,
                        "textDisplay": (
                            "Big news today! Share to spread the truth! "
                            "Follow for more!"
                        ),
                        "publishedAt": f"2025-05-01T12:00:{i*10:02d}Z",
                    }
                }
            }
        })
    burst_comment_items.append({
        "snippet": {
            "topLevelComment": {
                "id": "comment_human",
                "snippet": {
                    "authorChannelId": {"value": human_id},
                    "authorDisplayName": "normal_person",
                    "authorProfileImageUrl": "https://x/" + human_id,
                    "textDisplay": "great editing in this one, what software?",
                    "publishedAt": "2025-05-01T18:00:00Z",
                }
            }
        }
    })

    video_pages = {"videoBurst1": [{"items": burst_comment_items}]}
    channel_profiles = {
        bid: _channel_profile(
            bid, title=f"burst{i}", sub_count=1, created_at="2025-04-25T00:00:00Z"
        )
        for i, bid in enumerate(bot_ids)
    }
    channel_profiles[human_id] = _channel_profile(
        human_id, title="normal", sub_count=420, created_at="2018-03-15T00:00:00Z"
    )
    channel_history = {bid: _make_bot_history(bid) for bid in bot_ids}
    channel_history[human_id] = _make_human_history(human_id)

    fake = FakeYouTubeClient(
        video_pages=video_pages,
        channel_profiles=channel_profiles,
        channel_history=channel_history,
    )
    set_client_factory_for_tests(lambda: fake)

    resp = client_with_db.post(
        "/v1/scan/youtube/full",
        json={"video_url_or_id": "videoBurst1", "max_commenters": 10},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["commenter_count"] == 5
    assert body["coordination_score"] > 0.3
    assert body["coordination_tier"] in ("moderate", "elevated", "high")

    # At least one coordination cluster should catch the bot burst.
    assert body["clusters"]
    methods = {c["method"] for c in body["clusters"]}
    assert "temporal_semantic_clique" in methods or "age_cohort" in methods

    # Each bot commenter should carry coordination evidence + an adjusted
    # probability that's >= their standalone probability.
    by_id = {c["external_id"]: c for c in body["commenters"]}
    for bid in bot_ids:
        c = by_id[bid]
        if c.get("coordination_adjusted_probability") is not None:
            assert c["coordination_adjusted_probability"] >= c["overall_probability"] - 0.01

    # Thread-level scan should reflect the heavy repetition in comments.
    # 5 short comments is a small corpus; we just want it lifted above prior.
    assert body["thread_scan"]["overall_probability"] > 0.2

    # Human commenter shouldn't be lifted by coordination.
    assert by_id[human_id]["coordination_adjusted_probability"] in (None, by_id[human_id]["overall_probability"])

    assert "probabilistic" in body["summary"].lower()


def test_full_scan_persists_engagement_edges_for_future_scans(client_with_db):
    # Run a scan, then verify the persistent engagement table got rows so
    # the co-engagement detector has data on future runs.
    bot_id = "UC_engagement_test"
    video_pages = {
        "videoEngTs1": [
            {"items": [_video_comment_item(bot_id, "hi")]}
        ]
    }
    channel_profiles = {
        bot_id: _channel_profile(
            bot_id, title="ettest", sub_count=1, created_at="2025-05-01T00:00:00Z"
        )
    }
    # History across 4 different videos.
    base = datetime(2025, 4, 1, tzinfo=timezone.utc)
    channel_history = {
        bot_id: [
            {
                "snippet": {
                    "topLevelComment": {
                        "id": f"h{i}",
                        "snippet": {
                            "authorChannelId": {"value": bot_id},
                            "authorDisplayName": "ettest",
                            "textDisplay": f"comment #{i} on a video",
                            "publishedAt": (base + timedelta(days=i)).isoformat(),
                            "videoId": f"otherVid{i:03d}",
                        }
                    }
                }
            }
            for i in range(4)
        ]
    }
    fake = FakeYouTubeClient(
        video_pages=video_pages,
        channel_profiles=channel_profiles,
        channel_history=channel_history,
    )
    set_client_factory_for_tests(lambda: fake)

    resp = client_with_db.post(
        "/v1/scan/youtube/full", json={"video_url_or_id": "videoEngTs1"}
    )
    assert resp.status_code == 200

    # Reach into the DB and confirm engagement edges were recorded.
    from app.storage.db import get_session
    from app.storage.repository import AccountRepository
    with get_session() as s:
        edges = AccountRepository(s).load_engagement_sets(
            platform="youtube", account_external_ids=[bot_id]
        )
    assert bot_id in edges
    assert len(edges[bot_id]) >= 3  # the 4 history videos


def test_full_scan_focus_account_returns_spotlight(client_with_db):
    target = "UC_focus_target"
    video_pages = {
        "videoFocus1": [
            {"items": [
                _video_comment_item(target, "first comment"),
                _video_comment_item("UC_other_xyz", "second comment"),
            ]}
        ]
    }
    channel_profiles = {
        target: _channel_profile(
            target, title="focus", sub_count=10, created_at="2024-01-01T00:00:00Z"
        ),
        "UC_other_xyz": _channel_profile(
            "UC_other_xyz", title="other", sub_count=10, created_at="2024-01-01T00:00:00Z"
        ),
    }
    channel_history = {
        target: _make_human_history(target),
        "UC_other_xyz": _make_human_history("UC_other_xyz"),
    }
    fake = FakeYouTubeClient(
        video_pages=video_pages,
        channel_profiles=channel_profiles,
        channel_history=channel_history,
    )
    set_client_factory_for_tests(lambda: fake)

    resp = client_with_db.post(
        "/v1/scan/youtube/full",
        json={"video_url_or_id": "videoFocus1", "focus_account_external_id": target},
    )
    body = resp.json()
    assert body["focus_account"] is not None
    assert body["focus_account"]["external_id"] == target
