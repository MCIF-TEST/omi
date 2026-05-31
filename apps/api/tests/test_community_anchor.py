"""Unit tests for the community-anchor detector (GAP-07).

Pins the detector's contract:
* downward-only — probability is always at or below the prior, never above;
* age-gated — a young high-follower account does NOT anchor (bought-audience
  guard), protecting the exact region where audience-fabrication operates;
* follower-gated — an old account with no audience does NOT anchor;
* bounded — confidence is capped so the dampener can pull ~one tier, not
  collapse a blatant bot to clean;
* silent when weak — ordinary/unremarkable accounts produce zero confidence and
  contribute nothing to the aggregate.
And the integration property: anchoring reduces (never increases) a borderline
account's suspicion.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.core.config import Settings
from app.detection.community import analyze_community
from app.detection.engine import analyze_account
from app.schemas import Post, Profile


def _profile(
    handle: str = "established_acct",
    followers: int | None = 20_000,
    following: int | None = 800,
    age_days: int | None = 1500,
    verified: bool = False,
    bio: str = "A real account with a real audience.",
) -> Profile:
    created = (
        datetime.now(timezone.utc) - timedelta(days=age_days)
        if age_days is not None
        else None
    )
    return Profile(
        handle=handle,
        follower_count=followers,
        following_count=following,
        created_at=created,
        verified=verified,
        bio=bio,
    )


# ---------------------------------------------------------------------------
# Core anchoring behaviour
# ---------------------------------------------------------------------------

def test_established_account_anchors_downward():
    """Large, old follower base → fires with a sub-prior probability."""
    result = analyze_community(_profile(followers=25_000, age_days=1500))
    assert result.confidence > 0.0
    assert result.probability < 0.15  # below the 0.15 prior → subtracts suspicion


def test_anchor_probability_never_exceeds_prior():
    """Downward-only contract: across a wide sweep of inputs, probability is
    never above the prior (so it can never *add* suspicion)."""
    for followers in (0, 50, 300, 1_000, 9_000, 100_000, 5_000_000):
        for age in (0, 100, 400, 800, 1_500, 4_000):
            r = analyze_community(_profile(followers=followers, age_days=age))
            if r.confidence > 0:
                assert r.probability <= 0.15, (followers, age, r.probability)


def test_young_high_follower_account_does_not_anchor():
    """Bought-audience guard: 50k followers on a 3-month-old account must NOT
    anchor — this is exactly the audience-fabrication profile."""
    result = analyze_community(_profile(followers=50_000, age_days=90))
    assert result.confidence == 0.0


def test_old_account_without_audience_does_not_anchor():
    """An old but audience-less ghost account is not community-anchored."""
    result = analyze_community(_profile(followers=40, age_days=3000))
    assert result.confidence == 0.0


def test_verified_account_anchors_even_with_modest_counts():
    """Platform verification is its own anchor floor."""
    result = analyze_community(
        _profile(followers=1_200, following=400, age_days=900, verified=True)
    )
    assert result.confidence > 0.0
    assert result.probability < 0.15


def test_no_data_is_silent():
    """No followers and not verified → no opinion."""
    result = analyze_community(
        Profile(handle="ghost", follower_count=None, verified=None, created_at=None)
    )
    assert result.confidence == 0.0
    assert result.probability == pytest.approx(0.5)


def test_mass_follow_pattern_is_discounted():
    """The 'follows thousands, followed by few' farm shape suppresses the
    anchor relative to a reciprocal account with the same follower count."""
    farm = analyze_community(
        _profile(followers=2_000, following=40_000, age_days=1500)
    )
    reciprocal = analyze_community(
        _profile(followers=2_000, following=1_500, age_days=1500)
    )
    # Same follower count + age, but the lopsided ratio anchors less (lower
    # confidence, or silent entirely).
    assert farm.confidence <= reciprocal.confidence


def test_confidence_is_bounded():
    """Even a maximal account (millions of followers, verified, ancient) stays
    within the bounded confidence envelope — anchoring is evidence, not an
    override."""
    result = analyze_community(
        _profile(followers=10_000_000, following=500, age_days=6000, verified=True)
    )
    assert result.confidence <= 0.70 + 1e-9


def test_anchor_strength_increases_with_followers():
    small = analyze_community(_profile(followers=1_000, age_days=1500))
    big = analyze_community(_profile(followers=200_000, age_days=1500))
    assert big.confidence >= small.confidence


# ---------------------------------------------------------------------------
# Integration: anchoring lowers (never raises) a borderline verdict
# ---------------------------------------------------------------------------

def _impersonal_posts(n: int = 12) -> list[Post]:
    """Broadcast-style posts that trip the voice/temporal detectors — the kind
    of behavior an established brand/news account legitimately exhibits."""
    base = datetime(2024, 1, 1, 9, 0, 0, tzinfo=timezone.utc)
    texts = [
        "Markets closed higher today as tech shares rallied across the board.",
        "Severe weather warning issued for the northern region through Friday.",
        "New episode is now available. Highlights from this week's discussion.",
        "Quarterly results exceeded analyst expectations in most segments.",
        "Road closures expected downtown during the weekend festival.",
        "Temperatures will drop sharply overnight with clear skies expected.",
        "The latest report outlines three priorities for the coming year.",
        "Service updates have been applied. No action required from users.",
        "Attendance figures rose compared with the same period last year.",
        "A brief summary of today's top developments follows below.",
        "The schedule for next week has been published on the main site.",
        "Conditions are expected to improve gradually over the next few days.",
    ]
    return [
        Post(id=f"p{i}", author_handle="acct", text=texts[i % len(texts)],
             created_at=base + timedelta(hours=i * 6))
        for i in range(n)
    ]


def test_established_account_scored_no_higher_than_anonymous_peer():
    """Two identical posting histories; the one on an established account must
    score no higher than the one on a brand-new no-audience account. Community
    anchoring can only pull down."""
    posts = _impersonal_posts()
    established = _profile(handle="bigbrand", followers=80_000, following=300, age_days=2000)
    fresh = Profile(
        handle="bigbrand",
        follower_count=5,
        following_count=900,
        created_at=datetime.now(timezone.utc) - timedelta(days=20),
        verified=False,
        bio="",
    )
    r_estab = analyze_account(established, posts)
    r_fresh = analyze_account(fresh, posts)
    assert r_estab.overall_probability <= r_fresh.overall_probability


def test_community_signal_present_in_engine_output():
    """The engine wires the community detector into every account scan."""
    result = analyze_account(_profile(), _impersonal_posts())
    names = {s.name for s in result.signals}
    assert "community" in names
