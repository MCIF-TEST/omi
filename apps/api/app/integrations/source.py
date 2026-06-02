"""Source layer — the single platform boundary for Omi's intelligence engine.

A :class:`Source` is the ONLY platform-specific surface the orchestrator needs:
it fetches raw platform data and hands back the neutral :class:`~app.schemas.Profile`
/ :class:`~app.schemas.Post` schemas. Everything downstream — detectors,
decorrelation, memory, coordination, narrative, OmiScore, persistence, reporting —
is platform-agnostic and consumes those normalized objects unchanged.

Adding a platform means adding a ``Source`` (a thin fetch+normalize adapter),
never a parallel intelligence pipeline. YouTube is the first implementation
(:class:`YouTubeSource`, a behaviour-preserving delegating wrapper over
``app.integrations.youtube``); Twitter/X follows.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from app.schemas import Post, Profile


@runtime_checkable
class Source(Protocol):
    """Platform data-source contract.

    Implementations live in ``app/integrations/<platform>.py`` and map raw API
    data onto the shared ``Profile`` / ``Post`` schemas. They own their own fetch
    accounting (quota/calls) so the orchestrator stays platform-agnostic.
    """

    #: Stable platform key used for storage + the ``Profile.platform`` field.
    platform: str

    @property
    def quota_used(self) -> int:
        """Cumulative API cost (units/calls) this source has spent so far."""
        ...

    @property
    def stats(self) -> Any:
        """Opaque per-source fetch-stats object, threaded through the scan
        (the orchestrator treats it as a pass-through token)."""
        ...

    def parse_content_id(self, url_or_id: str) -> str | None:
        """Extract the platform content id (e.g. a video / tweet id) from a URL."""
        ...

    def resolve_account_id(self, handle_or_url: str) -> str | None:
        """Resolve a handle / URL to the platform's stable account id."""
        ...

    def fetch_account_profile(self, account_id: str) -> Profile | None:
        """Fetch + normalize one account's profile."""
        ...

    def fetch_account_posts(self, account_id: str, max_posts: int) -> list[Post]:
        """Fetch + normalize an account's recent posts (newest first)."""
        ...

    def fetch_content_engagers(
        self,
        content_id: str,
        *,
        max_commenters: int,
        max_comments: int,
        start_page_token: str | None = None,
    ) -> tuple[list[dict], list[dict], str | None]:
        """Fetch the accounts engaging with a piece of content (commenters /
        repliers) plus the raw interaction items — the cross-account coordination
        batch. Returns ``(commenters_meta, all_items, next_cursor)``.
        """
        ...


class YouTubeSource:
    """YouTube data source — a thin, behaviour-preserving adapter over
    ``app.integrations.youtube``.

    Every method delegates to the exact function the orchestrator called before
    the Source refactor, sharing one ``FetchStats`` so quota accounting is
    byte-for-byte unchanged. The wrapped ``client`` is whatever the route's
    client factory produced (the real API client in production, a fake in tests).
    """

    platform = "youtube"

    def __init__(self, client: Any) -> None:
        from app.integrations.youtube import FetchStats

        self._client = client
        self._stats = FetchStats()

    @property
    def quota_used(self) -> int:
        return self._stats.quota_used

    @property
    def stats(self) -> Any:
        return self._stats

    def parse_content_id(self, url_or_id: str) -> str | None:
        from app.integrations.youtube import parse_video_id

        return parse_video_id(url_or_id)

    def resolve_account_id(self, handle_or_url: str) -> str | None:
        from app.integrations.youtube import resolve_channel_id

        return resolve_channel_id(self._client, handle_or_url, stats=self._stats)

    def fetch_account_profile(self, account_id: str) -> Profile | None:
        from app.integrations.youtube import fetch_channel_profile

        return fetch_channel_profile(self._client, account_id, stats=self._stats)

    def fetch_account_posts(self, account_id: str, max_posts: int) -> list[Post]:
        from app.integrations.youtube import fetch_channel_recent_comments

        return fetch_channel_recent_comments(
            self._client, account_id, max_comments=max_posts, stats=self._stats
        )

    def fetch_content_engagers(
        self,
        content_id: str,
        *,
        max_commenters: int,
        max_comments: int,
        start_page_token: str | None = None,
    ) -> tuple[list[dict], list[dict], str | None]:
        from app.integrations.youtube import fetch_video_full

        return fetch_video_full(
            self._client,
            content_id,
            max_commenters=max_commenters,
            max_comments=max_comments,
            stats=self._stats,
            start_page_token=start_page_token,
        )


class TwitterSource:
    """Twitter/X data source — a thin adapter over ``app.integrations.twitter``.

    Normalizes to the same ``Profile`` / ``Post`` schemas as YouTube, so the
    identical detector / coordination / memory / OmiScore stack scores Twitter
    accounts and a tweet's repliers. ``fetch_content_engagers`` pulls a tweet's
    replies as the cross-account batch (the Twitter analog of a video's
    commenters).
    """

    platform = "x"

    def __init__(self, client: Any) -> None:
        from app.integrations.twitter import FetchStats

        self._client = client
        self._stats = FetchStats()

    @property
    def quota_used(self) -> int:
        # twitterapi.io bills per call; surface call count as the cost proxy.
        return self._stats.api_calls

    @property
    def stats(self) -> Any:
        return self._stats

    def parse_content_id(self, url_or_id: str) -> str | None:
        from app.integrations.twitter import parse_tweet_id

        return parse_tweet_id(url_or_id)

    def resolve_account_id(self, handle_or_url: str) -> str | None:
        from app.integrations.twitter import normalize_handle

        return normalize_handle(handle_or_url)

    def fetch_account_profile(self, account_id: str) -> Profile | None:
        from app.integrations.twitter import fetch_user_profile

        return fetch_user_profile(self._client, account_id, stats=self._stats)

    def fetch_account_posts(self, account_id: str, max_posts: int) -> list[Post]:
        from app.integrations.twitter import fetch_user_recent_tweets

        return fetch_user_recent_tweets(
            self._client, account_id, max_tweets=max_posts, stats=self._stats
        )

    def fetch_content_engagers(
        self,
        content_id: str,
        *,
        max_commenters: int,
        max_comments: int,
        start_page_token: str | None = None,
    ) -> tuple[list[dict], list[dict], str | None]:
        from app.integrations.twitter import fetch_tweet_engagers

        return fetch_tweet_engagers(
            self._client, content_id,
            max_commenters=max_commenters, max_comments=max_comments,
            stats=self._stats,
        )


def classify_link(url: str) -> dict:
    """Unified, platform-agnostic URL / handle classifier for the single-input
    investigation entry.

    Tries each platform's classifier; the first that recognizes the input wins.
    Always returns at least ``{"platform", "kind"}`` (``"unknown"`` for both when
    nothing matches). This is the dispatcher the unified ``/scan/link`` flow will
    use to route any URL to the right :class:`Source` (wired in T1).
    """
    from app.integrations.youtube import classify_url

    yt = classify_url(url)
    if yt.get("platform") and yt["platform"] != "unknown":
        return yt

    from app.integrations.twitter import classify_twitter_url

    tw = classify_twitter_url(url)
    if tw.get("platform") and tw["platform"] != "unknown":
        return tw

    return {"platform": "unknown", "kind": "unknown"}
