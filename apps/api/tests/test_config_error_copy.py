"""Config-failure errors must be user-facing — never leak env vars/internals.

An OSINT researcher or journalist who sees "Set OMI_YOUTUBE_API_KEY" or an
internal endpoint path in a scan error reads the product as unfinished. The
admin-actionable cause belongs in the logs; the HTTP detail belongs to the
user. Pins both platforms' client resolvers so neither regresses.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.core.config import Settings


def _detail(exc_info) -> str:
    assert exc_info.value.status_code == 503
    return str(exc_info.value.detail)


def _assert_user_facing(detail: str) -> None:
    # No env-var names, no internal API paths, no developer instructions.
    assert "OMI_" not in detail, detail
    assert "/v1/" not in detail, detail
    assert "API key" not in detail, detail
    assert "env" not in detail.lower(), detail


def test_youtube_missing_key_503_is_user_facing():
    from app.routes.scan import _resolve_client

    with pytest.raises(HTTPException) as ei:
        _resolve_client(Settings(youtube_api_key=""))
    _assert_user_facing(_detail(ei))


def test_twitter_missing_key_503_is_user_facing():
    from app.routes.scan import _resolve_twitter_client

    with pytest.raises(HTTPException) as ei:
        _resolve_twitter_client(Settings(twitter_api_key=""))
    _assert_user_facing(_detail(ei))
