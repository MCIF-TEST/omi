"""Pulling a commenter's comment history — the 'scan history' button path.

The single-account scan that the commenter-detail "Scan history" button calls
must always return the account's recent comments (any tier), so the operator
can see what an account has actually been commenting. The bulk comprehensive
scan also now bundles a comment sample for flagged commenters.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.routes.scan import set_client_factory_for_tests
from tests.test_youtube_integration import (
    FakeYouTubeClient,
    _channel_profile,
    _make_human_history,
)

SOLO_ID = "UC" + "a" * 22  # valid 24-char channel id


@pytest.fixture
def client():
    fake = FakeYouTubeClient(
        video_pages={},
        channel_profiles={
            SOLO_ID: _channel_profile(
                SOLO_ID, title="solo", sub_count=100, created_at="2020-01-01T00:00:00Z"
            )
        },
        channel_history={SOLO_ID: _make_human_history(SOLO_ID)},
    )
    set_client_factory_for_tests(lambda: fake)
    yield TestClient(create_app())
    set_client_factory_for_tests(None)


def test_account_scan_returns_comment_history_even_for_low_tier(client):
    """A normal (low-tier, human) account still returns its pulled comments —
    include_low=True — so the operator can always inspect what it posted."""
    resp = client.post(
        "/v1/scan/youtube/account",
        json={"account_url_or_handle": SOLO_ID},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["tier"] == "low"  # ordinary human account
    # The button's whole point: comments come back regardless of tier.
    assert len(body["recent_activity"]) > 0
    assert body["activity_total"] >= len(body["recent_activity"])
    # Each sample carries the comment text + provenance the UI renders.
    sample = body["recent_activity"][0]
    assert "text" in sample and "created_at" in sample and "parent_id" in sample


def test_account_scan_history_sample_is_capped(client):
    """The deep dive shows more than the bulk view (30) but stays bounded."""
    resp = client.post(
        "/v1/scan/youtube/account",
        json={"account_url_or_handle": SOLO_ID},
    )
    body = resp.json()
    assert len(body["recent_activity"]) <= 30
