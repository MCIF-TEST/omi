"""Select-then-scan, end-to-end evidence path — the PAID step must score EXACTLY the picked
commenters and no one else.

The user's intended flow: compile the commenter list (free), pick who to scan, then a SECOND provider
call pulls each picked account's profile + history, the evidence compiler scores them, and only those
accounts reach the Omi Analyst. These pin the orchestrator half of that: given ``injected_commenters``
(the selection), ``scan_comprehensive`` fetches per-account evidence for the selection and does NOT
re-fetch the content's commenter list.
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.orchestrator import scan_comprehensive
from app.schemas import Post, Profile
from app.storage.db import get_session


class _SelectionSource:
    """A YouTube-shaped Source that serves per-account profile/history but FAILS if the commenter list
    is re-fetched — proving the scored set comes from the selection, not a fresh fetch."""

    platform = "youtube"
    fetch_concurrency = 1

    class _Stats:
        quota_used = 0

    def __init__(self) -> None:
        self.profile_calls: list[str] = []
        self.history_calls: list[str] = []
        self._stats = self._Stats()

    @property
    def quota_used(self) -> int:
        return len(self.profile_calls)

    @property
    def stats(self):
        return self._stats

    def parse_content_id(self, url_or_id: str):
        return "vid-123"

    def fetch_account_profile(self, account_id: str):
        self.profile_calls.append(account_id)
        return Profile(
            platform="youtube", handle=account_id,
            follower_count=3, following_count=8000,
            created_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        )

    def fetch_account_posts(self, account_id: str, max_posts: int):
        self.history_calls.append(account_id)
        base = datetime(2024, 6, 1, tzinfo=timezone.utc)
        return [
            Post(id=f"{account_id}-p{i}", author_handle=account_id,
                 text="first!! check my channel", created_at=base)
            for i in range(5)
        ]

    def fetch_content_engagers(self, *a, **k):
        raise AssertionError("injected scan must NOT re-fetch the commenter list")


def test_injected_scan_scores_exactly_the_selection():
    selection = [
        {"channel_id": "alice", "handle": "alice"},
        {"channel_id": "bob", "handle": "bob"},
    ]
    # created_at is an ISO string here, exactly as the fixed compile cache round-trips it back
    # (source emits a datetime -> _dumps() writes ISO-8601 -> json.loads() -> str).
    comments = [
        {"comment_id": "c1", "author_external_id": "alice", "text": "first!!",
         "created_at": "2024-06-01T00:00:00+00:00"},
        {"comment_id": "c2", "author_external_id": "bob", "text": "check my channel",
         "created_at": "2024-06-01T00:05:00+00:00"},
    ]
    src = _SelectionSource()

    with get_session() as session:
        out = scan_comprehensive(
            session,
            account_url_or_handle=None,
            video_url_or_id="vid-123",
            comments_text=None,
            max_commenters=5,
            force_refresh=False,
            source=src,
            injected_commenters=selection,
            injected_comments=comments,
        )

    # The video scan ran on the injected selection ...
    assert out.video_output is not None
    scored = {r.external_id for r in out.video_output.commenter_records}
    assert scored == {"alice", "bob"}, "must score exactly the two picked commenters"

    # ... via a genuine per-account fetch (the "second API call"), for each selected account ...
    assert sorted(src.profile_calls) == ["alice", "bob"]
    assert sorted(src.history_calls) == ["alice", "bob"]

    # ... and every scored account carries real evidence for the Omi Analyst to read.
    for rec in out.video_output.commenter_records:
        assert rec.profile is not None
        assert rec.posts, "each selected account must have fetched history as evidence"
        assert rec.error is None
