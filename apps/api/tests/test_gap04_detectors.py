"""Unit tests for GAP-04 detector improvements.

Covers:
* narrative detector — astroturf language fires; clean accounts don't
* voice detector — broadcast exception fires when first-person rate is zero
  over a sufficient corpus
* profile detector — fresh-account compound signal catches sockpuppet setup
* temporal detector — strength-aware confidence boosts for machine-precision
  scheduling (CoV < 0.05)
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.detection.narrative import analyze_narrative
from app.detection.profile import analyze_profile
from app.detection.temporal import analyze_temporal, MIN_POSTS_FOR_TEMPORAL
from app.detection.voice import analyze_voice, MIN_WORDS_FOR_VOICE
from app.schemas import Post, Profile


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _post(text: str, offset_hours: int = 0, idx: int = 0) -> Post:
    return Post(
        id=f"p{idx}",
        author_handle="testuser",
        text=text,
        created_at=datetime(2024, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
        + timedelta(hours=offset_hours),
    )


def _posts_with_texts(texts: list[str]) -> list[Post]:
    return [_post(t, i * 2, i) for i, t in enumerate(texts)]


def _profile(
    handle: str = "realuser",
    created_at: datetime | None = None,
    followers: int | None = 500,
    following: int | None = 300,
    bio: str | None = "Regular person who likes stuff.",
    verified: bool = False,
) -> Profile:
    return Profile(
        handle=handle,
        created_at=created_at,
        follower_count=followers,
        following_count=following,
        bio=bio,
        verified=verified,
    )


def _fresh(days_old: int = 10, handle: str = "user12345", followers: int = 2,
           following: int = 3, bio: str | None = None) -> Profile:
    created = datetime.now(timezone.utc) - timedelta(days=days_old)
    return Profile(
        handle=handle,
        created_at=created,
        follower_count=followers,
        following_count=following,
        bio=bio,
        verified=False,
    )


def _mechanical_posts(n: int = 10, interval_seconds: int = 3600) -> list[Post]:
    """Posts at exactly equal intervals — CoV = 0 (machine-precision)."""
    base = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
    return [
        Post(
            id=f"m{i}",
            author_handle="bot",
            text=f"Scheduled post {i}",
            created_at=base + timedelta(seconds=i * interval_seconds),
        )
        for i in range(n)
    ]


def _human_posts(n: int = 20) -> list[Post]:
    """Posts at irregular, human-like intervals (CoV >> 0.5)."""
    intervals = [3600, 7200, 1800, 14400, 900, 5400, 3000, 10800, 2700, 4500,
                 6300, 1200, 8100, 3300, 7800, 2100, 5700, 4200, 9000, 6600]
    base = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
    posts: list[Post] = []
    ts = base
    for i in range(n):
        posts.append(Post(id=f"h{i}", author_handle="human",
                          text=f"Post {i}", created_at=ts))
        ts += timedelta(seconds=intervals[i % len(intervals)])
    return posts


def _jittered_posts(n: int = 20, base_interval: int = 3600,
                    jitter_fraction: float = 0.20) -> list[Post]:
    """Posts with alternating ±jitter_fraction around base_interval.

    CoV = jitter_fraction (with alternating pattern), which at 20% is well
    above the 0.05 mechanical threshold — representing a bot with light
    scheduling jitter, NOT machine-precision.
    """
    base = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
    posts: list[Post] = []
    ts = base
    for i in range(n):
        posts.append(Post(id=f"j{i}", author_handle="sched_bot",
                          text=f"Post {i}", created_at=ts))
        # Alternate between slightly short and slightly long intervals
        delta = base_interval * jitter_fraction * (1 if i % 2 == 0 else -1)
        ts += timedelta(seconds=int(base_interval + delta))
    return posts


# ---------------------------------------------------------------------------
# Narrative detector
# ---------------------------------------------------------------------------

ASTROTURF_POSTS = [
    "The mainstream media doesn't want you to see this. Wake up people.",
    "They don't want the hidden truth to come out. Deep state is real.",
    "Share this everywhere before they delete it! Fake news media is lying.",
    "They're trying to silence anyone who does their own research.",
    "The corrupt media narrative is falling apart. Wake up America!",
    "Globalist agenda exposed — spread this to everyone before it's gone.",
    "The real story they're hiding won't be on the news. Wake up world.",
    "Shadow banned for posting about the suppressed facts again.",
    "They don't want you to know. New world order is exposed.",
    "The establishment is panicking because people are waking up.",
]

CLEAN_POSTS = [
    "Just got back from the gym, feeling great today!",
    "Trying out a new recipe tonight — pasta with homemade sauce.",
    "My cat knocked over my coffee again. Classic Monday.",
    "Really enjoying this book series so far, highly recommend.",
    "Weather has been amazing this week. Love spring.",
    "Had a great meeting with the team today. Big things coming.",
    "Anyone else watch the game last night? Incredible match.",
    "Finally finished painting the bedroom. Looks fantastic.",
    "First hike of the season done. Legs are dead.",
    "Local farmers market was packed today. So much good food.",
]


def test_narrative_astroturf_fires():
    posts = _posts_with_texts(ASTROTURF_POSTS)
    result = analyze_narrative(posts)
    assert result.probability > 0.55
    assert result.confidence > 0.0


def test_narrative_high_rate_gives_high_probability():
    """When the majority of posts contain markers the probability should be clearly elevated."""
    # 8/10 posts with markers → marker_rate=0.8 → logistic well above 0.5
    posts = _posts_with_texts(ASTROTURF_POSTS[:8] + CLEAN_POSTS[:2])
    result = analyze_narrative(posts)
    assert result.probability > 0.80


def test_narrative_clean_account_low_confidence():
    """Clean posts with no astroturf markers should return zero confidence."""
    posts = _posts_with_texts(CLEAN_POSTS)
    result = analyze_narrative(posts)
    assert result.confidence == 0.0


def test_narrative_clean_account_neutral_probability():
    """With no markers, probability should be exactly 0.5 (the no-signal neutral)."""
    posts = _posts_with_texts(CLEAN_POSTS)
    result = analyze_narrative(posts)
    assert result.probability == pytest.approx(0.5)


def test_narrative_insufficient_posts():
    """Fewer than MIN_POSTS triggers low-data return."""
    posts = _posts_with_texts(ASTROTURF_POSTS[:2])
    result = analyze_narrative(posts)
    assert result.confidence == 0.0
    assert result.probability == pytest.approx(0.5)


def test_narrative_mixed_moderate_rate():
    """2 out of 10 posts (20%) should produce below-neutral probability."""
    posts = _posts_with_texts(ASTROTURF_POSTS[:2] + CLEAN_POSTS[:8])
    result = analyze_narrative(posts)
    # rate=0.2 → logistic((0.2-0.3)*14) < 0.5
    assert result.probability < 0.5


def test_narrative_confidence_scales_with_corpus_size():
    """More posts → higher confidence (corpus_conf component)."""
    small = _posts_with_texts(ASTROTURF_POSTS[:4])  # 4 posts, with markers
    big = _posts_with_texts(ASTROTURF_POSTS)         # 10 posts, all with markers
    r_small = analyze_narrative(small)
    r_big = analyze_narrative(big)
    assert r_big.confidence >= r_small.confidence


def test_narrative_single_post_does_not_inflate_confidence():
    """A single flagged post out of 3 should produce low confidence."""
    posts = _posts_with_texts([ASTROTURF_POSTS[0]] + CLEAN_POSTS[:2])
    result = analyze_narrative(posts)
    # abs_conf = 1/4 = 0.25; corpus_conf = 3/8 = 0.375; confidence = 0.09375
    assert result.confidence < 0.15


def test_narrative_evidence_contains_snippet():
    """When markers fire, the evidence should reference the post count and rate."""
    posts = _posts_with_texts(ASTROTURF_POSTS)
    result = analyze_narrative(posts)
    assert any("of" in e and "posts" in e for e in result.evidence)


# ---------------------------------------------------------------------------
# Voice detector — broadcast exception
# ---------------------------------------------------------------------------

def _broadcast_posts(n: int = 12) -> list[Post]:
    """Pure third-person news-brief style — no first-person at all."""
    templates = [
        "Breaking: researchers confirm new study on climate impact in coastal regions.",
        "The committee approved the new infrastructure plan with bipartisan support.",
        "Officials announced a review of the policy after mounting public pressure.",
        "The report highlights significant gaps in current emergency preparedness.",
        "Scientists observed unusual patterns in migration data this season.",
        "Analysis shows that the proposal has broad support across demographics.",
        "The organization confirmed that funding for the program will continue.",
        "Authorities issued new guidelines following the incident last week.",
        "The statement comes amid growing speculation about future direction.",
        "Experts say the findings could have implications for future policy.",
        "Results indicate an improvement in key performance metrics this quarter.",
        "The conference concluded with an agreement on three major points.",
    ]
    return [_post(templates[i % len(templates)], i * 4, i) for i in range(n)]


def test_voice_broadcast_zero_first_person_fires():
    """Broadcast-style zero-pronoun posts get elevated confidence via the broadcast exception."""
    posts = _broadcast_posts(n=14)
    result = analyze_voice(posts)
    # rate < 0.005 → dist=1.0 → prob=0.80
    assert result.probability >= 0.75
    # Broadcast exception should provide meaningful confidence
    assert result.confidence > 0.30


def test_voice_broadcast_exception_requires_min_words():
    """The broadcast exception is irrelevant when the whole corpus is below MIN_WORDS_FOR_VOICE."""
    # Short posts that won't reach MIN_WORDS_FOR_VOICE total
    posts = [_post("Brief. No pronouns here.", i * 2, i) for i in range(4)]
    result = analyze_voice(posts)
    # Below word threshold → confidence = 0.0 (returns early)
    assert result.confidence == 0.0


def test_voice_broadcast_confidence_grows_with_corpus():
    """More broadcast posts → higher confidence (broadcast_conf formula scales with words)."""
    small = _broadcast_posts(n=7)
    big = _broadcast_posts(n=20)
    r_small = analyze_voice(small)
    r_big = analyze_voice(big)
    assert r_big.confidence >= r_small.confidence


def test_voice_normal_human_low_probability():
    """Normal first-person-rich human posts should not look suspicious."""
    texts = [
        "I really enjoyed this video, I think it makes some great points about my experience.",
        "My favorite part was when they showed the behind-the-scenes. I laughed so hard.",
        "I've been following this channel for years and I love the content they make.",
        "This really resonated with me. I feel like I've been through similar experiences.",
        "I shared this with my family. We all felt the same way about it.",
    ]
    posts = _posts_with_texts(texts * 4)  # repeat to get enough words
    result = analyze_voice(posts)
    # dist=0.0 → prob=0.35; should be low-probability
    assert result.probability <= 0.40


# ---------------------------------------------------------------------------
# Profile detector — fresh account compound signal
# ---------------------------------------------------------------------------

def test_profile_fresh_sockpuppet_fires():
    """< 90 days, auto-handle, sparse graph, no bio → compound evidence fires."""
    p = _fresh(days_old=7, handle="user938271", followers=1, following=2, bio=None)
    result = analyze_profile(p, post_count=50)
    # The compound fresh-account signal should appear in sub_signals
    assert "fresh_account_suspicion" in (result.sub_signals or {})
    # Probability is above the neutral 0.5 baseline
    assert result.probability > 0.50
    # Evidence should mention the fresh-account pattern
    assert any("new account" in e.lower() or "cluster" in e.lower() for e in result.evidence)


def test_profile_fresh_two_attributes_required():
    """A new account with only ONE suspicious attribute should not trigger the compound signal."""
    # Only auto-handle; bio and graph are normal
    p = _fresh(days_old=14, handle="user12345678", followers=150, following=140,
               bio="Regular person who likes technology and coffee.")
    result = analyze_profile(p)
    # No compound signal in sub_signals
    assert "fresh_account_suspicion" not in (result.sub_signals or {})


def test_profile_fresh_all_three_attributes_elevated():
    """All three attributes present → elevated compound suspicion."""
    p = _fresh(days_old=5, handle="xjqr29281", followers=0, following=0, bio="")
    result = analyze_profile(p)
    # The averaging over all sub-signals means even 0.90 fresh_suspicion is
    # diluted; the result should still be materially above 0.5 baseline.
    assert result.probability > 0.60
    assert "fresh_account_suspicion" in (result.sub_signals or {})


def test_profile_old_account_skips_fresh_signal():
    """Accounts older than 90 days are not evaluated by the fresh-account signal."""
    p = Profile(
        handle="user12345",
        created_at=datetime.now(timezone.utc) - timedelta(days=200),
        follower_count=3,
        following_count=4,
        bio=None,
        verified=False,
    )
    result = analyze_profile(p)
    # The fresh_account sub_signal should not appear
    assert "fresh_account_suspicion" not in (result.sub_signals or {})


def test_profile_fresh_verified_account_dampened():
    """Verified status should dampen the fresh-account suspicion."""
    base_kwargs = dict(
        created_at=datetime.now(timezone.utc) - timedelta(days=10),
        follower_count=2,
        following_count=3,
        bio=None,
    )
    p_verified = Profile(handle="user77341", verified=True, **base_kwargs)
    p_unverified = Profile(handle="user77341", verified=False, **base_kwargs)
    r_v = analyze_profile(p_verified)
    r_u = analyze_profile(p_unverified)
    assert r_v.probability < r_u.probability


# ---------------------------------------------------------------------------
# Temporal detector — strength-aware confidence for mechanical scheduling
# ---------------------------------------------------------------------------

def test_temporal_mechanical_scheduling_boosts_confidence():
    """Perfectly regular intervals (CoV = 0) should receive a confidence boost
    beyond what the post count alone would give."""
    posts = _mechanical_posts(n=MIN_POSTS_FOR_TEMPORAL + 2)
    result = analyze_temporal(posts)
    # With 10 posts, data-volume confidence alone = 10/200 = 0.05.
    # Strength-aware boost should raise it significantly above that.
    assert result.confidence > 0.20
    assert result.probability > 0.70


def test_temporal_mechanical_probability_high():
    """Machine-precision scheduling across a multi-day span should produce a
    high synthetic probability. 35 posts at 1-hour intervals span >30 hours,
    activating the sleep-gap signal and driving the blended score above 0.80."""
    posts = _mechanical_posts(n=35)
    result = analyze_temporal(posts)
    assert result.probability > 0.80


def test_temporal_human_irregular_not_boosted():
    """Irregular human-like posting should not trigger the strength-aware boost."""
    posts = _human_posts(n=20)
    result = analyze_temporal(posts)
    # Confidence should remain data-volume-limited (20/200 = 0.10)
    assert result.confidence <= 0.15


def test_temporal_moderate_automation_no_boost():
    """Scheduled bot with 20% jitter (CoV ≈ 0.20) must NOT receive the
    mechanical-scheduling confidence boost — that boost is only for true
    machine-precision scheduling (CoV < 0.05)."""
    posts = _jittered_posts(n=20, base_interval=3600, jitter_fraction=0.20)
    result = analyze_temporal(posts)
    # With 20 posts, data-volume confidence = 20/200 = 0.10.
    # Boost should NOT fire (CoV ≈ 0.20 >> 0.05).
    assert result.confidence <= 0.15


def test_temporal_insufficient_posts_returns_neutral():
    """Fewer than MIN_POSTS_FOR_TEMPORAL posts returns the no-data result."""
    posts = _mechanical_posts(n=MIN_POSTS_FOR_TEMPORAL - 1)
    result = analyze_temporal(posts)
    assert result.confidence == 0.0
    assert result.probability == pytest.approx(0.5)
