"""T0 — the Source layer: the single platform seam the orchestrator depends on.

These tests pin the cross-platform architecture invariant: the intelligence
engine (scan_comprehensive → analyze_account → memory → persistence) is
platform-agnostic and reaches a platform only through a ``Source``. A non-YouTube
fake Source must drive a full comprehensive scan — proof no YouTube coupling
remains in the orchestrator.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.integrations.source import Source, YouTubeSource, classify_link
from app.schemas import Post, Profile
from app.storage.db import get_session
from app.storage.repository import AccountRepository


# ---------------------------------------------------------------------------
# Unified URL/handle classification
# ---------------------------------------------------------------------------

def test_classify_link_routes_youtube():
    info = classify_link("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    assert info["platform"] == "youtube"


def test_classify_link_routes_twitter_url():
    # An unambiguous x.com / twitter.com URL routes to the Twitter source.
    # (A bare "@handle" is intentionally ambiguous across platforms; the
    # dispatcher resolves those YouTube-first, so we only assert URL forms.)
    for u in ("https://x.com/jack", "https://twitter.com/jack"):
        info = classify_link(u)
        assert info["platform"] == "x" and info["kind"] == "account" and info["handle"] == "jack"


def test_classify_link_unknown():
    assert classify_link("https://example.com/foo")["platform"] == "unknown"


# ---------------------------------------------------------------------------
# YouTubeSource is a faithful, behaviour-preserving delegating adapter
# ---------------------------------------------------------------------------

def test_youtube_source_satisfies_protocol_and_delegates(monkeypatch):
    import app.integrations.youtube as yt

    src = YouTubeSource(client="CLIENT")
    assert isinstance(src, Source)
    assert src.platform == "youtube"

    calls: dict = {}

    def fake_resolve(client, handle, *, stats):
        calls["resolve"] = (client, handle); stats.quota_used += 1; return "UC123"

    def fake_profile(client, cid, *, stats):
        calls["profile"] = (client, cid); stats.quota_used += 1
        return Profile(platform="youtube", handle="chan")

    def fake_history(client, cid, *, max_comments, stats):
        calls["history"] = (client, cid, max_comments); stats.quota_used += 1; return []

    def fake_video_full(client, vid, *, max_commenters, max_comments, stats, start_page_token=None):
        calls["video"] = (client, vid, max_commenters, start_page_token); stats.quota_used += 5
        return ([], [], None)

    monkeypatch.setattr(yt, "resolve_channel_id", fake_resolve)
    monkeypatch.setattr(yt, "fetch_channel_profile", fake_profile)
    monkeypatch.setattr(yt, "fetch_channel_recent_comments", fake_history)
    monkeypatch.setattr(yt, "fetch_video_full", fake_video_full)

    assert src.resolve_account_id("@chan") == "UC123"
    assert src.fetch_account_profile("UC123").handle == "chan"
    assert src.fetch_account_posts("UC123", 50) == []
    assert src.fetch_content_engagers("vid", max_commenters=10, max_comments=30) == ([], [], None)

    assert calls["resolve"] == ("CLIENT", "@chan")
    assert calls["history"] == ("CLIENT", "UC123", 50)
    assert calls["video"][:3] == ("CLIENT", "vid", 10)
    # All four calls shared one FetchStats → quota accounting is unchanged.
    assert src.quota_used == 8


# ---------------------------------------------------------------------------
# Architectural proof: the orchestrator is platform-agnostic
# ---------------------------------------------------------------------------

class _FakeSource:
    """A minimal non-YouTube Source returning canned normalized objects."""

    platform = "reddit"

    def __init__(self) -> None:
        self._q = 0

    @property
    def quota_used(self) -> int:
        return self._q

    @property
    def stats(self):
        return None

    def parse_content_id(self, url_or_id: str):
        return None

    def resolve_account_id(self, handle_or_url: str):
        self._q += 1
        return "acct-1"

    def fetch_account_profile(self, account_id: str):
        return Profile(
            platform="reddit", handle="suspect",
            follower_count=10, following_count=9000,
            created_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        )

    def fetch_account_posts(self, account_id: str, max_posts: int):
        base = datetime(2024, 6, 1, tzinfo=timezone.utc)
        return [
            Post(id=f"p{i}", author_handle="suspect",
                 text="great video!!! link in bio", created_at=base)
            for i in range(6)
        ]

    def fetch_content_engagers(self, content_id, *, max_commenters, max_comments, start_page_token=None):
        return ([], [], None)


def test_scan_comprehensive_runs_on_a_non_youtube_source():
    """scan_comprehensive must complete an account scan via a fake 'reddit'
    Source and persist the account under THAT platform — no youtube coupling."""
    from app.orchestrator import scan_comprehensive

    with get_session() as session:
        out = scan_comprehensive(
            session,
            account_url_or_handle="suspect",
            video_url_or_id=None,
            comments_text=None,
            max_commenters=10,
            force_refresh=False,
            source=_FakeSource(),
        )

    assert out.focus_account is not None
    assert out.focus_account["external_id"] == "acct-1"
    assert "account" in out.inputs_provided

    # Persisted under the source's platform, proving platform flows from the
    # Source rather than a hardcoded "youtube".
    with get_session() as session:
        acc = AccountRepository(session).get("reddit", "acct-1")
        assert acc is not None, "account must be persisted under the Source's platform"
