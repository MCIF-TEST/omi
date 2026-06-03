"""Typed Twitter/X ingestion errors.

Mirrors ``youtube_errors`` so the route layer can handle upstream failures the
same way regardless of platform. The third-party data provider (twitterapi.io)
signals failure two ways — via HTTP status *and* via an in-body
``{"status": "error", "msg": ...}`` envelope — so :func:`translate_status` looks
at both.

* :class:`TwitterRateLimitError` — provider rate limit hit (HTTP 429). Refund
  the user's credit and ask them to retry shortly.
* :class:`TwitterAuthError` — API key missing/invalid/revoked (HTTP 401/403).
  Service-level problem, not the user's fault. Refund and surface to admins.
* :class:`TwitterAccessError` — the account exists but its data isn't fetchable
  (protected/suspended). The user's input is fine; do NOT refund (lookup ran).
* :class:`TwitterNotFoundError` — the handle doesn't resolve to an account.
* :class:`TwitterClientError` — anything else.

All inherit from :class:`TwitterClientError`.
"""

from __future__ import annotations


class TwitterClientError(Exception):
    """Base class for all typed Twitter ingestion errors.

    ``user_message`` is safe to surface to the end user; ``admin_detail`` carries
    the raw provider response — log it, never show it.
    """

    def __init__(self, user_message: str, *, admin_detail: str | None = None) -> None:
        super().__init__(user_message)
        self.user_message = user_message
        self.admin_detail = admin_detail or user_message

    def __str__(self) -> str:
        return self.user_message


class TwitterRateLimitError(TwitterClientError):
    """The provider rate limit is exhausted. Surface as 503 + Retry-After."""


class TwitterAuthError(TwitterClientError):
    """The Twitter data API key is missing, invalid, or revoked."""


class TwitterAccessError(TwitterClientError):
    """The account is protected or suspended — input is valid but data isn't
    fetchable. Do not refund."""

    def __init__(self, user_message: str, *, admin_detail: str | None = None,
                 is_suspension: bool = False) -> None:
        super().__init__(user_message, admin_detail=admin_detail)
        self.is_suspension = is_suspension


class TwitterNotFoundError(TwitterClientError):
    """The handle doesn't resolve to an account."""


_NOT_FOUND_HINTS = ("not found", "could not be found", "does not exist", "no user")
_SUSPENDED_HINTS = ("suspend",)
_PROTECTED_HINTS = ("protected", "private")


def translate_status(status_code: int, body_text: str = "") -> TwitterClientError:
    """Map an HTTP status (and optional body text) to a typed error."""
    detail = body_text[:500]
    low = body_text.lower()

    if status_code == 429:
        return TwitterRateLimitError(
            "The Twitter data provider is rate-limited right now. Please retry in a minute.",
            admin_detail=f"429 {detail}",
        )
    if status_code in (401, 403):
        # 403 can also be a protected account depending on the provider; prefer
        # the access reading only when the body hints at it.
        if any(h in low for h in _PROTECTED_HINTS + _SUSPENDED_HINTS):
            return TwitterAccessError(
                "This account is protected or suspended, so its activity can't be analyzed.",
                admin_detail=f"{status_code} {detail}",
                is_suspension=any(h in low for h in _SUSPENDED_HINTS),
            )
        return TwitterAuthError(
            "The Twitter integration is misconfigured (auth rejected).",
            admin_detail=f"{status_code} {detail}",
        )
    if status_code == 404:
        return TwitterNotFoundError(
            "No Twitter/X account matched that handle.",
            admin_detail=f"404 {detail}",
        )
    return TwitterClientError(
        "The Twitter data provider returned an unexpected error.",
        admin_detail=f"{status_code} {detail}",
    )


def translate_body_status(msg: str) -> TwitterClientError:
    """Map an in-body ``status=error`` envelope (HTTP 200 with msg) to a typed
    error, since twitterapi.io often returns 200 for 'user not found'."""
    low = (msg or "").lower()
    if any(h in low for h in _SUSPENDED_HINTS):
        return TwitterAccessError(
            "This account appears to be suspended, so its activity can't be analyzed.",
            admin_detail=msg, is_suspension=True,
        )
    if any(h in low for h in _PROTECTED_HINTS):
        return TwitterAccessError(
            "This account is protected, so its activity can't be analyzed.",
            admin_detail=msg,
        )
    if any(h in low for h in _NOT_FOUND_HINTS):
        return TwitterNotFoundError(
            "No Twitter/X account matched that handle.",
            admin_detail=msg,
        )
    return TwitterClientError(
        "The Twitter data provider returned an error.",
        admin_detail=msg or "unknown provider error",
    )
