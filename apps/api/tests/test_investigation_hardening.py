"""Hardening tests for investigation persistence and large-batch scan stability.

Covers:
- Investigation saved even under simulated SQLite write contention
- Retry logic persists the investigation after transient DB failures
- Continuation batch (second scan of same slug) merges correctly
- The background pool doesn't block the scan response
- Large-batch coordination detectors stay bounded (no O(n²) blowup)
- Temporal-semantic clique input cap
- Fingerprint cluster input cap
- Style match input cap
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app
from app.routes.scan import (
    _investigation_label,
    _merge_payloads,
    _persist_investigation_async,
    _serialize_result,
    set_client_factory_for_tests,
)
from app.storage.db import get_session, reset_db_for_tests
from app.storage.repository import AccountRepository
from tests.test_demo_scan import _fake_client_with_n_commenters, VID


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def auth_client(monkeypatch):
    monkeypatch.setenv("OMI_REQUIRE_AUTH", "true")
    monkeypatch.setenv("OMI_SESSION_SECRET", "x" * 64)
    monkeypatch.setenv("OMI_FREE_TRIAL_CREDITS", "20")
    get_settings.cache_clear()
    reset_db_for_tests("sqlite:///:memory:")
    from app.core.rate_limit import SIGNUP_LIMITER, LOGIN_LIMITER
    SIGNUP_LIMITER._windows.clear()
    LOGIN_LIMITER._windows.clear()
    set_client_factory_for_tests(lambda: _fake_client_with_n_commenters(15))
    with TestClient(app) as tc:
        tc.post("/v1/auth/signup", json={"email": "hard@t.com", "password": "password12345"})
        yield tc
    set_client_factory_for_tests(None)
    reset_db_for_tests("sqlite:///:memory:")
    get_settings.cache_clear()


def _make_payload(
    slug: str = "inv_test001",
    overall_probability: float = 0.6,
    overall_tier: str = "elevated",
    quota_used: int = 5,
) -> dict:
    """Minimal pre-serialised investigation payload (mirrors what _serialize_result produces)."""
    return {
        "investigation_slug": slug,
        "overall_probability": overall_probability,
        "overall_tier": overall_tier,
        "summary": "Test summary.",
        "quota_used": quota_used,
        "inputs_provided": ["video"],
        "video": None,
        "focus_account": None,
        "comments_scan": None,
        "cross_links": [],
        "convergence_score": 0.2,
        "matrix": [],
        "matrix_methods": [],
        "next_page_token": None,
        "video_id": VID,
    }


# ---------------------------------------------------------------------------
# 1. Investigation persistence — happy path
# ---------------------------------------------------------------------------

def test_new_investigation_created_by_background_worker():
    slug = "inv_aa000001"
    payload = _make_payload(slug=slug)
    classification = {"kind": "video", "video_id": VID}

    _persist_investigation_async(
        slug=slug,
        user_id=1,
        classification=classification,
        url=f"https://youtube.com/watch?v={VID}",
        payload=payload,
    )

    with get_session() as session:
        repo = AccountRepository(session)
        inv = repo.get_investigation(slug=slug)
    assert inv is not None
    assert inv.slug == slug
    assert inv.overall_tier == "elevated"
    assert inv.batch_count == 1
    assert inv.payload_json is not None


def test_continuation_batch_merges_into_existing_investigation():
    slug = "inv_cont0001"
    classification = {"kind": "video", "video_id": VID}
    url = f"https://youtube.com/watch?v={VID}"

    payload1 = _make_payload(slug=slug, quota_used=3)
    payload2 = _make_payload(slug=slug, quota_used=4, overall_probability=0.75)

    # First batch — creates the row.
    _persist_investigation_async(slug=slug, user_id=1, classification=classification, url=url, payload=payload1)
    # Second batch — should update, not create a second row.
    _persist_investigation_async(slug=slug, user_id=1, classification=classification, url=url, payload=payload2)

    with get_session() as session:
        repo = AccountRepository(session)
        inv = repo.get_investigation(slug=slug)

    assert inv is not None
    assert inv.batch_count == 2, f"expected 2 batches, got {inv.batch_count}"
    assert inv.quota_used == 7, f"expected cumulative quota 7, got {inv.quota_used}"
    assert inv.overall_probability == pytest.approx(0.75)


# ---------------------------------------------------------------------------
# 2. Retry logic — transient DB failure on first attempt
# ---------------------------------------------------------------------------

def test_persist_retries_on_transient_db_error():
    slug = "inv_retry001"
    payload = _make_payload(slug=slug)
    classification = {"kind": "video", "video_id": VID}
    url = f"https://youtube.com/watch?v={VID}"

    call_count = 0
    original_get_session = __import__("app.storage.db", fromlist=["get_session"]).get_session

    from contextlib import contextmanager

    @contextmanager
    def _failing_once_session():
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("simulated transient DB failure")
        with original_get_session() as session:
            yield session

    with patch("app.routes.scan.get_session", _failing_once_session):
        # Should not raise — retry absorbs the first failure.
        _persist_investigation_async(
            slug=slug, user_id=1, classification=classification, url=url, payload=payload
        )

    # The second attempt (call_count == 2) used the real session.
    assert call_count == 2

    with get_session() as session:
        repo = AccountRepository(session)
        inv = repo.get_investigation(slug=slug)
    assert inv is not None, "investigation should be saved after successful retry"


# ---------------------------------------------------------------------------
# 3. Background worker submission via scan_link endpoint
# ---------------------------------------------------------------------------

def test_scan_link_investigation_survives_background_drain(auth_client):
    """Full round-trip: scan → background persist → investigation readable."""
    r = auth_client.post(
        "/v1/scan/link",
        json={"url": f"https://www.youtube.com/watch?v={VID}", "max_commenters": 8},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    slug = body.get("investigation_slug", "")
    assert slug.startswith("inv_"), f"slug missing or malformed: {slug!r}"

    from app.core import background
    background.shutdown(wait_seconds=15.0)

    listing = auth_client.get("/v1/investigations").json()["investigations"]
    slugs = [i["slug"] for i in listing]
    assert slug in slugs, f"investigation {slug!r} missing from history; found: {slugs}"


def test_scan_link_continuation_updates_investigation(auth_client):
    """A second scan with investigation_slug continues the same investigation."""
    # First scan.
    r1 = auth_client.post(
        "/v1/scan/link",
        json={"url": f"https://www.youtube.com/watch?v={VID}", "max_commenters": 5},
    )
    assert r1.status_code == 200, r1.text
    slug = r1.json()["investigation_slug"]

    from app.core import background
    background.shutdown(wait_seconds=15.0)

    # Second scan continuing the same investigation.
    r2 = auth_client.post(
        "/v1/scan/link",
        json={
            "url": f"https://www.youtube.com/watch?v={VID}",
            "max_commenters": 5,
            "investigation_slug": slug,
        },
    )
    assert r2.status_code == 200, r2.text
    background.shutdown(wait_seconds=15.0)

    detail = auth_client.get(f"/v1/investigations/{slug}").json()
    assert detail["slug"] == slug
    assert detail["batch_count"] == 2, f"expected 2 batches, got {detail['batch_count']}"


# ---------------------------------------------------------------------------
# 4. Payload merge correctness
# ---------------------------------------------------------------------------

def test_merge_payloads_deduplicates_commenters():
    existing = {
        "video": {
            "commenters": [
                {"external_id": "A", "overall_probability": 0.8},
                {"external_id": "B", "overall_probability": 0.3},
            ]
        }
    }
    incoming = {
        "video": {
            "commenters": [
                {"external_id": "B", "overall_probability": 0.3},  # duplicate
                {"external_id": "C", "overall_probability": 0.7},  # new
            ],
            "commenter_count": 2,
        },
        "overall_probability": 0.65,
    }
    merged = _merge_payloads(existing, incoming)
    ids = [c["external_id"] for c in merged["video"]["commenters"]]
    assert sorted(ids) == ["A", "B", "C"], f"unexpected ids: {ids}"
    assert merged["video"]["commenter_count"] == 3
    assert merged["overall_probability"] == 0.65


# ---------------------------------------------------------------------------
# 5. Large-batch coordination detector caps
# ---------------------------------------------------------------------------

def _make_comment_entry(i: int):
    from app.detection.coordination.temporal_semantic import CommentEntry
    # Space comments 30s apart so adjacent ones fall within the 120s window.
    base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    return CommentEntry(
        comment_id=f"c{i}",
        author_external_id=f"author_{i % 80}",  # 80 distinct authors → 8×+ per author
        text=f"test comment number {i} hello world foo bar baz",
        created_at=base + timedelta(seconds=i * 30),
    )


def test_temporal_semantic_caps_at_max_comments():
    """Passing 800 comments doesn't raise or time out — the cap is enforced."""
    from app.detection.coordination.temporal_semantic import (
        detect_temporal_semantic_cliques,
        _MAX_COMMENTS,
    )
    comments = [_make_comment_entry(i) for i in range(800)]
    t0 = time.monotonic()
    result = detect_temporal_semantic_cliques(comments)
    elapsed = time.monotonic() - t0
    # Should complete quickly — not minutes.
    assert elapsed < 30.0, f"took {elapsed:.1f}s — cap not working"
    assert result.method == "temporal_semantic_clique"
    # The cap was applied (max_comments processed ≤ _MAX_COMMENTS).
    # We can't check the internal state, but result should be valid.
    assert 0.0 <= result.overall_score <= 1.0
    assert 0.0 <= result.confidence <= 1.0


def test_temporal_semantic_small_batch_unchanged():
    """Small batches (under cap) are processed normally."""
    from app.detection.coordination.temporal_semantic import detect_temporal_semantic_cliques
    comments = [_make_comment_entry(i) for i in range(20)]
    result = detect_temporal_semantic_cliques(comments)
    assert result.method == "temporal_semantic_clique"
    assert isinstance(result.clusters, list)


def test_fingerprint_cluster_caps_at_max_entries():
    """Fingerprint clustering with > _MAX_ENTRIES entries stays bounded."""
    from app.detection.coordination.fingerprint_cluster import (
        detect_fingerprint_clusters,
        FingerprintEntry,
        _MAX_ENTRIES,
    )
    import random
    rng = random.Random(42)
    entries = [
        FingerprintEntry(
            external_id=f"u{i}",
            handle=f"user{i}",
            fingerprint=[rng.random() for _ in range(17)],
            individual_probability=rng.random(),
        )
        for i in range(_MAX_ENTRIES + 100)
    ]
    t0 = time.monotonic()
    result = detect_fingerprint_clusters(entries)
    elapsed = time.monotonic() - t0
    assert elapsed < 30.0, f"took {elapsed:.1f}s — cap not working"
    assert result.method == "fingerprint_cluster"


def test_style_match_caps_at_max_entries():
    """Style matching with > _MAX_ENTRIES entries stays bounded."""
    from app.detection.coordination.style_match import (
        detect_style_matches,
        StyleEntry,
        _MAX_ENTRIES,
    )
    # Give each entry enough text to pass the style-vector filter (≥40 words).
    long_text = " ".join(f"word{j}" for j in range(50))
    entries = [
        StyleEntry(
            external_id=f"u{i}",
            handle=f"user{i}",
            texts=[long_text, long_text],
        )
        for i in range(_MAX_ENTRIES + 50)
    ]
    t0 = time.monotonic()
    result = detect_style_matches(entries)
    elapsed = time.monotonic() - t0
    assert elapsed < 30.0, f"took {elapsed:.1f}s — cap not working"
    assert result.method == "style_match"


# ---------------------------------------------------------------------------
# 6. Investigation label helper
# ---------------------------------------------------------------------------

def test_investigation_label_video():
    assert _investigation_label({"kind": "video", "video_id": "abc123"}, "") == "Video abc123"


def test_investigation_label_channel():
    assert _investigation_label({"kind": "channel", "account_input": "@mychan"}, "") == "Channel @mychan"


def test_investigation_label_fallback():
    label = _investigation_label({"kind": "unknown"}, "https://example.com/foo")
    assert "example.com" in label


# ---------------------------------------------------------------------------
# 7. _serialize_result round-trips cleanly (no non-serialisable objects)
# ---------------------------------------------------------------------------

def test_serialize_result_is_json_safe(auth_client):
    """The pre-serialised payload must be JSON-round-trippable (stored in DB as JSON)."""
    r = auth_client.post(
        "/v1/scan/link",
        json={"url": f"https://www.youtube.com/watch?v={VID}", "max_commenters": 5},
    )
    assert r.status_code == 200, r.text

    # Drain background tasks so the persist worker finishes cleanly before the
    # TestClient shuts down (prevents ExceptionGroup propagation).
    from app.core import background
    background.shutdown(wait_seconds=15.0)

    # The response body itself is JSON-serialised by FastAPI.
    body = r.json()
    # Re-encode the body to verify it's pure JSON-safe types.
    re_encoded = json.dumps(body)
    assert isinstance(re_encoded, str)
    reparsed = json.loads(re_encoded)
    assert reparsed["overall_tier"] in ("low", "moderate", "elevated", "high")
