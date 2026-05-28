"""Typed YouTube errors.

The Google client raises ``googleapiclient.errors.HttpError`` for everything
from quota exhaustion to a private channel. The error body carries the real
reason, and the right user-facing response is wildly different depending on
which one it is. This module narrows ``HttpError`` into a small set of
typed exceptions so the route layer can handle each cleanly:

* :class:`YouTubeQuotaExceededError` — daily quota for our API key is gone.
  Refund the user's credit and ask them to retry tomorrow.
* :class:`YouTubeAuthError` — API key is missing, revoked, or restricted.
  Service-level problem; not the user's fault. Refund and surface to
  admins.
* :class:`YouTubeAccessError` — channel is private / comments disabled /
  region-blocked. The user's input is fine but the data isn't fetchable.
  Tell them clearly; do not refund (the lookup actually ran).
* :class:`YouTubeNotFoundError` — video / channel doesn't exist.
* :class:`YouTubeClientError` — anything else.

All five inherit from :class:`YouTubeClientError` so callers can catch the
base if they want broad handling.
"""

from __future__ import annotations

from typing import Any


class YouTubeClientError(Exception):
    """Base class for all typed YouTube ingestion errors.

    ``user_message`` is safe to surface to the end user. ``admin_detail``
    has the raw API response — never show it to users, but log it.
    """

    def __init__(self, user_message: str, *, admin_detail: str | None = None) -> None:
        super().__init__(user_message)
        self.user_message = user_message
        self.admin_detail = admin_detail or user_message

    def __str__(self) -> str:
        return self.user_message


class YouTubeQuotaExceededError(YouTubeClientError):
    """The shared YouTube API key has burned through its daily quota.

    The quota window resets at midnight Pacific Time (Google's billing
    window). Until then, no scans can run. Surface as 503 with a
    Retry-After header.
    """


class YouTubeAuthError(YouTubeClientError):
    """The API key is missing, invalid, revoked, or has restrictions that
    prevent it from being used for the requested operation. Admin needs
    to fix the deployment config."""


class YouTubeAccessError(YouTubeClientError):
    """The target exists but isn't readable: comments disabled, private
    channel, geo-blocked, age-restricted, suspended, etc. Distinguish from
    NotFound so the user gets accurate copy.

    ``is_suspension`` is True when the cause is a YouTube moderation action
    (channelSuspended / channelClosed). That's a strong ground-truth signal:
    YouTube itself decided the account violated policy. The label
    auto-generator uses it to seed ``source=youtube_suspension`` rows.
    """

    def __init__(self, user_message: str, *, admin_detail: str | None = None,
                 is_suspension: bool = False) -> None:
        super().__init__(user_message, admin_detail=admin_detail)
        self.is_suspension = is_suspension


class YouTubeNotFoundError(YouTubeClientError):
    """The target video / channel doesn't exist."""


# YouTube Data API v3 error "reason" codes we actually care about. Pulled
# from https://developers.google.com/youtube/v3/docs/errors and observed
# in production logs.
_QUOTA_REASONS = frozenset({
    "quotaExceeded",
    "dailyLimitExceeded",
    "rateLimitExceeded",
    "userRateLimitExceeded",
})
_AUTH_REASONS = frozenset({
    "keyInvalid",
    "keyExpired",
    "ipRefererBlocked",
    "accessNotConfigured",
    "forbidden",
})
_ACCESS_REASONS = frozenset({
    "commentsDisabled",
    "videoNotFound",  # treated as NotFound below; included here for completeness
    "channelClosed",
    "channelSuspended",
    "commentForbidden",
    "processingFailure",
})


def translate_http_error(err: Any) -> YouTubeClientError:
    """Convert a ``googleapiclient.errors.HttpError`` into a typed OMI error.

    ``Any`` typing rather than the real class keeps this importable even
    when the optional ``[youtube]`` extra isn't installed (tests).
    """
    status_code = getattr(err, "resp", None)
    status_code = getattr(status_code, "status", None) if status_code else None
    try:
        status_code = int(status_code) if status_code is not None else None
    except (TypeError, ValueError):
        status_code = None

    # Pull the structured error reason — varies by client version, so try a
    # couple of paths.
    reason: str | None = None
    message: str | None = None
    try:
        import json
        body = getattr(err, "content", None)
        if isinstance(body, bytes):
            body = body.decode("utf-8", errors="replace")
        if isinstance(body, str) and body:
            parsed = json.loads(body)
            errs = (parsed.get("error") or {}).get("errors") or []
            if errs:
                reason = errs[0].get("reason")
                message = errs[0].get("message")
            if not message:
                message = (parsed.get("error") or {}).get("message")
    except Exception:
        pass

    admin_detail = f"HTTP {status_code or '?'} reason={reason or '?'} msg={message or str(err)!r}"

    # --- Quota --------------------------------------------------------------
    if reason in _QUOTA_REASONS or (status_code == 403 and reason and "quota" in reason.lower()):
        return YouTubeQuotaExceededError(
            "YouTube has rate-limited us — the daily quota is exhausted. "
            "Try again after midnight Pacific Time. Your credit has been refunded.",
            admin_detail=admin_detail,
        )

    # --- Auth / config ------------------------------------------------------
    if reason in _AUTH_REASONS or status_code == 401:
        return YouTubeAuthError(
            "Our YouTube credentials were rejected by Google. The team has "
            "been notified — please try again later. Your credit has been refunded.",
            admin_detail=admin_detail,
        )

    # --- Not found ----------------------------------------------------------
    if status_code == 404 or reason in {"videoNotFound", "channelNotFound"}:
        return YouTubeNotFoundError(
            "YouTube returned no result for that URL. The video or channel "
            "may have been deleted, renamed, or made private.",
            admin_detail=admin_detail,
        )

    # --- Access (private, disabled, blocked, SUSPENDED) ---------------------
    if reason in _ACCESS_REASONS or status_code == 403:
        is_suspension = reason in {"channelSuspended", "channelClosed"}
        if is_suspension:
            return YouTubeAccessError(
                "YouTube has suspended or closed this channel. The account "
                "is no longer reachable.",
                admin_detail=admin_detail,
                is_suspension=True,
            )
        return YouTubeAccessError(
            "YouTube refused to return data for that target. It may be "
            "private, have comments disabled, or be geo-restricted.",
            admin_detail=admin_detail,
        )

    # --- Anything else ------------------------------------------------------
    return YouTubeClientError(
        "YouTube returned an unexpected error. Please try again — if it "
        "persists, the team has been notified. Your credit has been refunded.",
        admin_detail=admin_detail,
    )


def wrap_youtube_call(fn, *args, **kwargs):
    """Call ``fn(*args, **kwargs)`` and translate any HttpError into the
    typed-error hierarchy. Other exceptions pass through unchanged.

    Used to wrap individual ``client.commentThreads().list().execute()``
    calls without sprinkling try/except all over the ingestion code.
    """
    try:
        return fn(*args, **kwargs)
    except Exception as e:
        # Detect HttpError by class name to avoid a hard dependency on
        # googleapiclient at import time.
        cls_path = f"{type(e).__module__}.{type(e).__name__}"
        if cls_path.startswith("googleapiclient.errors.") or hasattr(e, "resp"):
            raise translate_http_error(e) from e
        raise
