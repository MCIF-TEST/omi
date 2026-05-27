"""Tests for the multi-signal narrative coordination layer."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.narrative.coordination import (
    MembershipRecord,
    amplification_bursts,
    display_tier,
    is_qualifying_tier,
    origin_window,
    propagation_timeline,
    score_narrative,
    text_fingerprint,
)


def _t(offset_hours: float) -> datetime:
    return datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc) + timedelta(hours=offset_hours)


def test_tier_eligibility_filters_low_and_unscored():
    assert not is_qualifying_tier(None)
    assert not is_qualifying_tier("low")
    assert is_qualifying_tier("moderate")
    assert is_qualifying_tier("elevated")
    assert is_qualifying_tier("high")


def test_display_tier_maps_internal_to_public_vocabulary():
    assert display_tier("low") == "low"
    assert display_tier("moderate") == "moderate"
    assert display_tier("elevated") == "high"
    assert display_tier("high") == "extreme"
    assert display_tier(None) == "unscored"


def test_text_fingerprint_normalises_punctuation_and_case():
    a = text_fingerprint("Hello, world!")
    b = text_fingerprint("hello world")
    c = text_fingerprint("HELLO   WORLD")
    assert a == b == c
    # Different text → different hash
    assert text_fingerprint("goodbye") != a


def test_organic_cluster_scores_low_and_labels_organic():
    """A cluster of all-low-tier authors should not trigger coordination signals."""
    members = [
        MembershipRecord(
            account_external_id=f"user_{i}",
            platform="youtube",
            parent_id=f"video_{i % 3}",
            observed_at=_t(i * 3),
            text_hash=text_fingerprint(f"organic comment {i}"),
            tier="low",
        )
        for i in range(20)
    ]
    scores = score_narrative(
        members=members,
        first_seen_at=_t(0),
        last_seen_at=_t(60),
    )
    assert scores.coordination_label == "organic"
    assert scores.risk_tier == "low"
    assert scores.coordination_score < 0.1
    assert scores.qualifying_member_count == 0


def test_coordinated_cluster_with_bursty_reposts_scores_high():
    """A tight burst of identical text from suspicious accounts should fire
    multiple signals: temporal burst, repost overlap, timing entropy."""
    members = []
    # 8 suspicious accounts all posting near-identical text in a 2-hour window
    for i in range(8):
        members.append(MembershipRecord(
            account_external_id=f"susp_{i}",
            platform="youtube",
            parent_id="video_target",
            observed_at=_t(i * 0.2),   # all within 2 hours
            text_hash=text_fingerprint("Wake up sheeple this is rigged"),
            tier="elevated",
        ))
    # A couple of low-tier organic mentions
    for i in range(3):
        members.append(MembershipRecord(
            account_external_id=f"organic_{i}",
            platform="youtube",
            parent_id="video_target",
            observed_at=_t(40 + i * 20),
            text_hash=text_fingerprint(f"interesting point organic {i}"),
            tier="low",
        ))
    scores = score_narrative(
        members=members,
        first_seen_at=_t(0),
        last_seen_at=_t(80),
    )
    assert scores.qualifying_author_count == 8
    assert scores.repost_overlap > 0.5     # all 8 share text-hash
    assert scores.inauthenticity_fraction > 0.5
    # Aggregate must escape low-risk band.
    assert scores.coordination_score > 0.35
    assert scores.risk_tier in ("moderate", "high", "extreme")
    assert scores.coordination_label in ("suspicious", "coordinated", "manipulation_network")
    assert scores.cluster_confidence >= 2


def test_cross_target_spread_signal_fires_when_authors_active_on_many_videos():
    """Multi-video activity from the same suspicious accounts is a hallmark
    of a campaign."""
    members = []
    # 5 suspicious authors, each commenting on 3 different videos
    for author_i in range(5):
        for vid_i in range(3):
            members.append(MembershipRecord(
                account_external_id=f"campaign_{author_i}",
                platform="youtube",
                parent_id=f"video_{vid_i}",
                observed_at=_t(author_i * 0.5 + vid_i * 5),
                text_hash=text_fingerprint(f"talking point variation {author_i}_{vid_i}"),
                tier="elevated",
            ))
    scores = score_narrative(
        members=members,
        first_seen_at=_t(0),
        last_seen_at=_t(60),
    )
    assert scores.cross_parent_spread >= 0.8   # all 5 authors on >=2 videos
    assert scores.qualifying_author_count == 5


def test_only_moderate_and_above_count_as_qualifying():
    """The MOST IMPORTANT RULE: low-tier and unscanned accounts must not
    enter qualifying counts even if they're cluster members."""
    members = [
        MembershipRecord("a", "youtube", "v1", _t(0), text_fingerprint("x"), "low"),
        MembershipRecord("b", "youtube", "v1", _t(1), text_fingerprint("y"), None),
        MembershipRecord("c", "youtube", "v1", _t(2), text_fingerprint("z"), "moderate"),
        MembershipRecord("d", "youtube", "v1", _t(3), text_fingerprint("w"), "elevated"),
    ]
    scores = score_narrative(
        members=members, first_seen_at=_t(0), last_seen_at=_t(3),
    )
    assert scores.qualifying_author_count == 2   # only c and d


def test_propagation_timeline_buckets_correctly():
    members = [
        MembershipRecord(
            f"u{i}", "youtube", "v1",
            _t(i * 0.5),   # 0, 0.5, 1, 1.5, 2 hours
            text_fingerprint(f"t{i}"),
            tier="elevated" if i % 2 == 0 else "low",
        )
        for i in range(5)
    ]
    timeline = propagation_timeline(members, bucket_hours=1)
    # All within 3 hours → 3 buckets
    assert len(timeline) >= 1
    total = sum(p.count for p in timeline)
    assert total == 5
    susp = sum(p.suspicious_count for p in timeline)
    assert susp == 3   # i=0,2,4 are elevated


def test_amplification_bursts_detect_spikes():
    """Build a timeline with a clear spike at index 3 and verify it's flagged."""
    members = []
    base = _t(0)
    # 1 comment per hour for 4 hours, then 30 comments in hour 5
    for i in range(4):
        members.append(MembershipRecord(
            f"u_baseline_{i}", "youtube", "v1",
            base + timedelta(hours=i),
            text_fingerprint(f"baseline {i}"),
            tier="elevated",
        ))
    for i in range(30):
        members.append(MembershipRecord(
            f"u_spike_{i}", "youtube", "v1",
            base + timedelta(hours=5, minutes=i),
            text_fingerprint(f"spike {i}"),
            tier="elevated",
        ))
    timeline = propagation_timeline(members, bucket_hours=1)
    bursts = amplification_bursts(timeline)
    assert len(bursts) >= 1
    assert bursts[0]["ratio"] >= 2.5


def test_origin_window_computes_lag_between_emergence_and_suspicious_amplification():
    members = [
        # Organic emergence at hour 0
        MembershipRecord("org1", "youtube", "v1", _t(0), text_fingerprint("a"), "low"),
        MembershipRecord("org2", "youtube", "v1", _t(1), text_fingerprint("b"), "low"),
        # Suspicious amplification kicks in at hour 12
        MembershipRecord("susp1", "youtube", "v1", _t(12), text_fingerprint("c"), "elevated"),
        MembershipRecord("susp2", "youtube", "v1", _t(13), text_fingerprint("d"), "high"),
    ]
    origin = origin_window(members)
    assert origin is not None
    assert origin["lag_hours"] == 12.0


def test_empty_input_returns_default_scores():
    scores = score_narrative(members=[], first_seen_at=_t(0), last_seen_at=_t(1))
    assert scores.coordination_score == 0.0
    assert scores.risk_tier == "low"
    assert scores.qualifying_member_count == 0
