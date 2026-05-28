"""Tests for the typed YouTube error layer + credit refund flow."""

from __future__ import annotations

import json

import pytest

from app.integrations.youtube_errors import (
    YouTubeAccessError,
    YouTubeAuthError,
    YouTubeClientError,
    YouTubeNotFoundError,
    YouTubeQuotaExceededError,
    translate_http_error,
)


class _FakeResp:
    def __init__(self, status: int):
        self.status = status


class _FakeHttpError(Exception):
    """Quacks like googleapiclient.errors.HttpError for translate purposes."""

    def __init__(self, status: int, body: dict):
        super().__init__("FakeHttpError")
        self.resp = _FakeResp(status)
        self.content = json.dumps(body).encode("utf-8")


def _error_body(reason: str, message: str = "test", status_code: int = 403) -> dict:
    return {
        "error": {
            "code": status_code,
            "message": message,
            "errors": [{"reason": reason, "message": message}],
        }
    }


# ---------------------------------------------------------------------------
# translate_http_error
# ---------------------------------------------------------------------------


def test_quota_exceeded_is_recognized():
    err = _FakeHttpError(403, _error_body("quotaExceeded"))
    out = translate_http_error(err)
    assert isinstance(out, YouTubeQuotaExceededError)
    assert "credit has been refunded" in out.user_message
    assert "quotaExceeded" in out.admin_detail


def test_daily_limit_exceeded_is_recognized():
    err = _FakeHttpError(403, _error_body("dailyLimitExceeded"))
    assert isinstance(translate_http_error(err), YouTubeQuotaExceededError)


def test_rate_limit_exceeded_is_recognized():
    err = _FakeHttpError(403, _error_body("userRateLimitExceeded"))
    assert isinstance(translate_http_error(err), YouTubeQuotaExceededError)


def test_key_invalid_is_auth_error():
    err = _FakeHttpError(400, _error_body("keyInvalid", status_code=400))
    out = translate_http_error(err)
    assert isinstance(out, YouTubeAuthError)


def test_401_is_auth_error():
    err = _FakeHttpError(401, _error_body("unauthorized", status_code=401))
    assert isinstance(translate_http_error(err), YouTubeAuthError)


def test_video_not_found_is_not_found_error():
    err = _FakeHttpError(404, _error_body("videoNotFound", status_code=404))
    out = translate_http_error(err)
    assert isinstance(out, YouTubeNotFoundError)


def test_comments_disabled_is_access_error():
    err = _FakeHttpError(403, _error_body("commentsDisabled"))
    out = translate_http_error(err)
    assert isinstance(out, YouTubeAccessError)
    assert "private" in out.user_message or "comments disabled" in out.user_message


def test_unknown_reason_falls_back_to_generic_client_error():
    err = _FakeHttpError(500, _error_body("weirdNewReason", status_code=500))
    out = translate_http_error(err)
    # 500 isn't matched by any specific branch → generic.
    assert isinstance(out, YouTubeClientError)
    assert "credit has been refunded" in out.user_message


def test_403_without_specific_reason_is_access_error():
    """A bare 403 (no reason field) should be treated as access denied,
    not silently swallowed."""
    err = _FakeHttpError(403, {"error": {"code": 403, "message": "Forbidden"}})
    out = translate_http_error(err)
    # Falls through to the 403 status_code branch.
    assert isinstance(out, YouTubeAccessError)


def test_translate_handles_malformed_body():
    """The Google client sometimes returns non-JSON bodies on weird failures.
    The translator must not crash."""
    err = _FakeHttpError(500, {})
    err.content = b"<html>500 internal error</html>"
    out = translate_http_error(err)
    # Falls through to generic.
    assert isinstance(out, YouTubeClientError)


# ---------------------------------------------------------------------------
# wrap_youtube_call
# ---------------------------------------------------------------------------


def test_wrap_youtube_call_passes_through_non_http_errors():
    from app.integrations.youtube_errors import wrap_youtube_call

    def boom():
        raise ValueError("not an HttpError")

    with pytest.raises(ValueError):
        wrap_youtube_call(boom)


def test_wrap_youtube_call_translates_http_errors():
    from app.integrations.youtube_errors import wrap_youtube_call

    err = _FakeHttpError(403, _error_body("quotaExceeded"))

    def boom():
        raise err

    with pytest.raises(YouTubeQuotaExceededError):
        wrap_youtube_call(boom)


def test_wrap_youtube_call_returns_value_on_success():
    from app.integrations.youtube_errors import wrap_youtube_call

    assert wrap_youtube_call(lambda: 42) == 42
