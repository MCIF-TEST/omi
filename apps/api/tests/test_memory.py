"""Tests for the fingerprint extraction, the memory prior signal, and the
orchestrator that ties them together with persistence."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.core.config import get_settings
from app.memory.fingerprint import FINGERPRINT_DIM, euclidean, extract_fingerprint
from app.memory.prior import compute_memory_signal
from app.orchestrator import scan_account_with_memory
from app.schemas import Profile, Tier
from app.storage.db import get_session, reset_db_for_tests
from app.storage.models import Account
from app.storage.repository import AccountRepository
from tests.test_detection import make_human_posts, make_mechanical_posts


@pytest.fixture(autouse=True)
def _fresh_db():
    get_settings.cache_clear()
    reset_db_for_tests("sqlite:///:memory:")
    yield
    reset_db_for_tests("sqlite:///:memory:")


# ---------------------------------------------------------------------------
# Fingerprint extraction
# ---------------------------------------------------------------------------


def _scan(posts, profile):
    from app.detection.engine import analyze_account

    return analyze_account(profile, posts)


def test_fingerprint_has_stable_dimension():
    profile = Profile(platform="youtube", handle="someone")
    fp = extract_fingerprint(_scan(make_human_posts(), profile))
    assert len(fp) == FINGERPRINT_DIM
    assert all(0.0 <= v <= 1.0 for v in fp), "all features must be normalized to [0,1]"


def test_fingerprints_distinguish_bot_from_human():
    bot_profile = Profile(
        platform="youtube",
        handle="zk8n3q_4488",
        created_at=datetime.now(timezone.utc) - timedelta(days=10),
        follower_count=2,
        following_count=4900,
    )
    human_profile = Profile(
        platform="youtube",
        handle="hannah_writes",
        created_at=datetime(2017, 3, 1, tzinfo=timezone.utc),
        follower_count=2400,
        following_count=900,
    )
    bot_fp = extract_fingerprint(_scan(make_mechanical_posts(), bot_profile))
    human_fp = extract_fingerprint(_scan(make_human_posts(), human_profile))
    d = euclidean(bot_fp, human_fp)
    assert d > 0.4, f"bot and human fingerprints should be well-separated, got d={d:.2f}"


# ---------------------------------------------------------------------------
# Memory prior signal
# ---------------------------------------------------------------------------


def test_memory_signal_neutral_when_db_empty():
    fp = [0.5] * FINGERPRINT_DIM
    sig = compute_memory_signal(fp, [])
    assert sig.confidence == 0.0
    assert sig.probability == 0.5
    assert "No prior fingerprints" in sig.evidence[0]


def test_memory_signal_fires_on_close_neighbors():
    # Three previously-flagged accounts, all with identical fingerprints to
    # the one we're about to scan.
    fp = [0.9] * FINGERPRINT_DIM
    neighbors = [
        Account(
            platform="youtube",
            external_id=f"neighbor_{i}",
            handle=f"neighbor_{i}",
            last_score=0.9,
            last_confidence=0.8,
            last_tier="high",
            fingerprint_json=fp,
        )
        for i in range(3)
    ]
    sig = compute_memory_signal(fp, neighbors, k=5)
    assert sig.confidence > 0.4
    assert sig.probability > 0.7
    assert any("previously-scored" in e for e in sig.evidence)
    assert sig.sub_signals["close_neighbors"] == 3


def test_memory_signal_ignores_distant_neighbors():
    near_fp = [0.9] * FINGERPRINT_DIM
    far_fp = [0.1] * FINGERPRINT_DIM
    neighbors = [
        Account(
            platform="youtube",
            external_id="far",
            handle="far",
            last_score=0.95,
            last_confidence=0.9,
            last_tier="high",
            fingerprint_json=far_fp,
        )
    ]
    sig = compute_memory_signal(near_fp, neighbors, k=5, distance_threshold=0.35)
    assert sig.confidence == 0.0
    assert sig.sub_signals["close_neighbors"] == 0


def test_memory_signal_excludes_self():
    fp = [0.9] * FINGERPRINT_DIM
    neighbors = [
        Account(
            platform="youtube",
            external_id="me",
            handle="me",
            last_score=0.95,
            last_confidence=0.9,
            last_tier="high",
            fingerprint_json=fp,
        )
    ]
    sig = compute_memory_signal(fp, neighbors, exclude_external_id="me")
    assert sig.confidence == 0.0  # the only neighbor was excluded


# ---------------------------------------------------------------------------
# Orchestrator: end-to-end self-improving flow
# ---------------------------------------------------------------------------


def test_orchestrator_persists_and_returns_cached_on_replay():
    profile = Profile(
        platform="youtube",
        handle="bot_alpha",
        created_at=datetime.now(timezone.utc) - timedelta(days=20),
        follower_count=3,
        following_count=4000,
    )
    posts = make_mechanical_posts()
    with get_session() as s:
        first = scan_account_with_memory(
            s, platform="youtube", external_id="UC_alpha", profile=profile, posts=posts
        )
    assert first.from_cache is False
    assert first.result.tier in {Tier.ELEVATED, Tier.HIGH}

    with get_session() as s:
        second = scan_account_with_memory(
            s, platform="youtube", external_id="UC_alpha", profile=profile, posts=posts
        )
    assert second.from_cache is True
    assert second.result.overall_probability == first.result.overall_probability


def test_orchestrator_prior_lifts_score_for_similar_new_account():
    # Step 1: scan three obvious bots → DB now contains three high-suspicion
    # fingerprints clustered together.
    bot_template_profile = Profile(
        platform="youtube",
        handle="seed",
        created_at=datetime.now(timezone.utc) - timedelta(days=15),
        follower_count=1,
        following_count=4500,
    )
    posts = make_mechanical_posts()
    for i in range(3):
        with get_session() as s:
            scan_account_with_memory(
                s,
                platform="youtube",
                external_id=f"UC_seed_{i}",
                profile=Profile(**{**bot_template_profile.model_dump(), "handle": f"seed_{i}"}),
                posts=posts,
            )

    # Step 2: scan a *new* account whose behavior is also mechanical → memory
    # signal should fire because the DB has matching priors.
    with get_session() as s:
        new_scan = scan_account_with_memory(
            s,
            platform="youtube",
            external_id="UC_new",
            profile=Profile(**{**bot_template_profile.model_dump(), "handle": "new_one"}),
            posts=posts,
        )
    memory_sig = next((s for s in new_scan.result.signals if s.name == "memory"), None)
    assert memory_sig is not None
    assert memory_sig.confidence > 0
    assert memory_sig.probability > 0.5
    assert new_scan.matched_neighbors >= 1


def test_orchestrator_repository_round_trip():
    profile = Profile(platform="youtube", handle="round_trip")
    with get_session() as s:
        scan_account_with_memory(
            s,
            platform="youtube",
            external_id="UC_rt",
            profile=profile,
            posts=make_mechanical_posts(),
        )
        repo = AccountRepository(s)
        acc = repo.get("youtube", "UC_rt")
        assert acc is not None
        assert acc.handle == "round_trip"
        assert acc.fingerprint_json is not None
        assert len(acc.fingerprint_json) == FINGERPRINT_DIM
        assert acc.last_score is not None
        assert len(acc.scans) == 1
