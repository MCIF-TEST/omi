"""What the Omi Analyst is actually shown about each account.

Every per-account verdict is only as good as the evidence that reaches the model, and that evidence
is assembled long before the coverage budgeter (120k tokens, with a disclosed omission manifest) gets
a say. Anything dropped upstream of it is dropped silently and invisibly. These tests pin the three
places that were doing exactly that.
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.routes.scan import ACTIVITY_SAMPLE_LIMIT, _activity_payload, _profile_fields
from app.schemas import Post, Profile, Tier


def _posts(n: int) -> list[Post]:
    return [
        Post(id=f"p{i}", author_handle="@someone", text=f"post number {i}",
             created_at=datetime(2026, 1, 1, tzinfo=timezone.utc))
        for i in range(n)
    ]


# --------------------------------------------------------------------------- #
# History — present whenever it exists
# --------------------------------------------------------------------------- #
def test_a_low_tier_account_keeps_its_history():
    """The analyst is asked whether an account is a real person. Withholding a low-tier account's
    posts removed the evidence that answers that in the account's FAVOUR — for the ~80% of
    commenters who are genuine."""
    samples, total = _activity_payload(_posts(12), Tier.LOW)
    assert len(samples) == 12
    assert total == 12


def test_every_tier_gets_its_history():
    for tier in (Tier.LOW, Tier.MODERATE, Tier.ELEVATED, Tier.HIGH):
        samples, total = _activity_payload(_posts(5), tier)
        assert len(samples) == 5, f"{tier} lost its history"
        assert total == 5


def test_an_empty_history_means_the_account_genuinely_has_no_posts():
    """The contract the model relies on: no samples == nothing to show, never 'withheld'."""
    assert _activity_payload([], Tier.LOW) == ([], 0)
    assert _activity_payload([], Tier.HIGH) == ([], 0)


def test_the_full_pulled_history_survives():
    """We fetch up to scan_max_history_per_commenter posts per account; the sample limit must not
    quietly throw most of them away before the model can read them."""
    from app.core.config import get_settings

    fetched = get_settings().scan_max_history_per_commenter
    assert ACTIVITY_SAMPLE_LIMIT >= fetched, (
        "the carried sample limit must cover the history we actually fetch, or the extra fetching "
        "is wasted API quota that never reaches the model"
    )
    samples, total = _activity_payload(_posts(fetched), Tier.LOW)
    assert len(samples) == fetched and total == fetched


def test_post_text_is_not_cut_below_what_the_evidence_layer_renders():
    """The evidence layer renders up to 600 chars; a tighter cut here silently decided what the
    model could read, and long posts are where the tells live."""
    long_post = Post(id="p", author_handle="@a", text="x" * 900,
                     created_at=datetime(2026, 1, 1, tzinfo=timezone.utc))
    samples, _ = _activity_payload([long_post], Tier.LOW)
    assert len(samples[0]["text"]) > 400


# --------------------------------------------------------------------------- #
# Raw profile metadata — the facts a score cannot encode
# --------------------------------------------------------------------------- #
def test_profile_fields_carry_the_raw_metadata_the_composer_reads():
    """These exact keys are what the evidence composer looks up by name. They were absent from the
    scan result for the whole of its life, so the model was handed None for every one and asked to
    judge authenticity from a pseudonymous ref."""
    created = datetime(2026, 6, 1, tzinfo=timezone.utc)
    fields = _profile_fields(Profile(
        platform="x", handle="@a", bio="crypto enthusiast", follower_count=12,
        following_count=4210, created_at=created, verified=False,
    ))
    assert fields == {
        "follower_count": 12, "following_count": 4210, "account_created_at": created,
        "bio": "crypto enthusiast", "verified": False,
    }


def test_a_missing_profile_is_all_none_not_a_crash():
    """None here is the honest 'the platform didn't give us this', which the prompt treats as low
    confidence rather than as a signal."""
    assert _profile_fields(None) == {
        "follower_count": None, "following_count": None, "account_created_at": None,
        "bio": None, "verified": None,
    }


# --------------------------------------------------------------------------- #
# The cache must save work, not evidence
# --------------------------------------------------------------------------- #
def _cache_hit(*, bio="a real bio", followers=500, following=300):
    """A (Account, Scan) pair shaped like AccountRepository.cached_scan_within returns."""
    from types import SimpleNamespace

    acc = SimpleNamespace(
        handle="@repeat", display_name="Repeat", bio=bio, follower_count=followers,
        following_count=following, account_created_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        fingerprint_json=[0.1, 0.2],
    )
    scan_row = SimpleNamespace(
        overall_probability=0.4, confidence=0.5, tier="moderate",
        signals_json=[], summary="seen before",
    )
    return acc, scan_row


def test_a_cached_account_still_carries_its_history_to_the_model():
    """A cache hit reuses the stored SCORE. It must not also skip the account's posts: with a 7-day
    TTL, the accounts that recur are exactly the repeat offenders the fingerprint memory exists to
    catch, and they were reaching the model with an empty post list — indistinguishable from an
    account that has never posted anything."""
    from app.orchestrator import _cached_commenter_record

    posts = _posts(9)
    rec = _cached_commenter_record(
        _cache_hit(), {"channel_id": "u1", "handle": "@repeat"}, "x",
        profile=Profile(platform="x", handle="@repeat", follower_count=11,
                        following_count=4000, verified=False, bio=""),
        posts=posts,
    )
    assert rec.from_cache is True                    # the score is still reused
    assert len(rec.posts) == 9                       # ...but the evidence is real
    assert rec.profile.following_count == 4000       # and the profile is the fresh one
    assert rec.profile.verified is False


def test_a_cached_account_falls_back_to_stored_metadata_when_the_refetch_fails():
    """A failed refetch must not throw away a scan the user already has — degrade to the stored row,
    including the following_count the old reconstruction silently dropped."""
    from app.orchestrator import _cached_commenter_record

    rec = _cached_commenter_record(_cache_hit(), {"channel_id": "u1", "handle": "@repeat"}, "x")
    assert rec.posts == []
    assert rec.profile.follower_count == 500
    assert rec.profile.following_count == 300, "stored following_count was being dropped"
