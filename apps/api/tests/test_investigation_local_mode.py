"""Local-mode investigation persistence (OMI_REQUIRE_AUTH=false).

Regression for: "scans don't save to investigations." On a solo / local install
(the default, ``require_auth=false``) every request runs as a synthetic user
with ``id=0``. The persistence path used to skip ``id=0`` entirely and the list
endpoint hard-coded an empty response — so local scans were never saved and the
history was always empty. These tests pin that local scans now persist under a
stable local-user row and show up in the history.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app
from app.routes.scan import set_client_factory_for_tests
from app.storage.db import get_session, reset_db_for_tests
from app.storage.repository import AccountRepository, LOCAL_USER_EMAIL
from tests.test_demo_scan import _fake_client_with_n_commenters, VID


@pytest.fixture
def local_client(monkeypatch):
    # Local mode: no auth required. This is the default for solo installs.
    monkeypatch.setenv("OMI_REQUIRE_AUTH", "false")
    get_settings.cache_clear()
    reset_db_for_tests("sqlite:///:memory:")
    set_client_factory_for_tests(lambda: _fake_client_with_n_commenters(10))
    with TestClient(app) as tc:
        yield tc
    set_client_factory_for_tests(None)
    reset_db_for_tests("sqlite:///:memory:")
    get_settings.cache_clear()


def _drain():
    from app.core import background
    background.shutdown(wait_seconds=15.0)


def test_local_scan_persists_and_appears_in_history(local_client):
    # Before any scan, history is empty (no local user yet).
    listing = local_client.get("/v1/investigations").json()["investigations"]
    assert listing == []

    r = local_client.post(
        "/v1/scan/link",
        json={"url": f"https://www.youtube.com/watch?v={VID}", "max_commenters": 8},
    )
    assert r.status_code == 200, r.text
    slug = r.json().get("investigation_slug", "")
    assert slug.startswith("inv_"), f"no slug stamped: {slug!r}"

    _drain()

    listing = local_client.get("/v1/investigations").json()["investigations"]
    slugs = [i["slug"] for i in listing]
    assert slug in slugs, f"local scan {slug!r} not in history: {slugs}"


def test_local_investigation_is_retrievable_by_slug(local_client):
    r = local_client.post(
        "/v1/scan/link",
        json={"url": f"https://www.youtube.com/watch?v={VID}", "max_commenters": 6},
    )
    slug = r.json()["investigation_slug"]
    _drain()

    detail = local_client.get(f"/v1/investigations/{slug}")
    assert detail.status_code == 200, detail.text
    body = detail.json()
    assert body["slug"] == slug
    assert body["payload"]  # full result payload persisted


def test_local_continuation_updates_same_investigation(local_client):
    r1 = local_client.post(
        "/v1/scan/link",
        json={"url": f"https://www.youtube.com/watch?v={VID}", "max_commenters": 5},
    )
    slug = r1.json()["investigation_slug"]
    _drain()

    r2 = local_client.post(
        "/v1/scan/link",
        json={
            "url": f"https://www.youtube.com/watch?v={VID}",
            "max_commenters": 5,
            "investigation_slug": slug,
        },
    )
    assert r2.status_code == 200
    _drain()

    detail = local_client.get(f"/v1/investigations/{slug}").json()
    assert detail["batch_count"] == 2, f"expected 2 batches, got {detail['batch_count']}"

    # Exactly one local user owns it — continuation didn't fork a second row.
    listing = local_client.get("/v1/investigations").json()["investigations"]
    assert sum(1 for i in listing if i["slug"] == slug) == 1


def test_local_user_row_is_created_once(local_client):
    """Multiple local scans must resolve to a single stable local-user row."""
    for _ in range(2):
        local_client.post(
            "/v1/scan/link",
            json={"url": f"https://www.youtube.com/watch?v={VID}", "max_commenters": 5},
        )
        _drain()

    with get_session() as session:
        from sqlalchemy import select
        from app.storage.models import User
        rows = session.execute(
            select(User).where(User.email == LOCAL_USER_EMAIL)
        ).scalars().all()
    assert len(rows) == 1, f"expected exactly one local user, got {len(rows)}"


def test_ensure_local_user_id_is_idempotent():
    reset_db_for_tests("sqlite:///:memory:")
    with get_session() as session:
        repo = AccountRepository(session)
        first = repo.ensure_local_user_id()
        second = repo.ensure_local_user_id()
    assert first == second
    with get_session() as session:
        repo = AccountRepository(session)
        assert repo.local_user_id() == first
