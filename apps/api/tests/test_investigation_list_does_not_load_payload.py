"""The archive list must never load ``payload_json``.

``payload_json`` holds the entire scan result — every commenter's scores, evidence, posts and analyst
sections — and the archive page requests 100 rows at once. The list used to ``select(Investigation)``
(the whole entity) and then read the blob per row just to resolve a platform string and a thumbnail
URL, so rendering a page of cards deserialised megabytes per row. On a 512 MB instance that is an
out-of-memory risk, and it grows with how much a customer has actually used the product — it degrades
worst for the best customers.

The fix denormalises ``platform`` and ``thumbnail_url`` onto the row at write time and adds
``load_only()`` to the list query. Two things can silently undo it, so both are pinned here:

* adding a payload read back into the summary builder — with ``load_only()`` in place that lazy-loads
  the blob one row at a time, which is strictly worse than before (an N+1 instead of one big query);
* forgetting to populate the columns on write, which would make every row fall back to URL heuristics
  and quietly lose YouTube thumbnails.

The blob-free assertion is made against the SQL actually emitted, not by reading the code.
"""

from __future__ import annotations

import pytest
from sqlalchemy import event

from app.storage.db import get_session, reset_db_for_tests
from app.storage.models import Investigation
from app.storage.repository import AccountRepository

_YT_URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
_X_URL = "https://x.com/someone/status/1790000000000000000"


@pytest.fixture(autouse=True)
def _db():
    reset_db_for_tests("sqlite:///:memory:")
    yield
    reset_db_for_tests("sqlite:///:memory:")


def _big_payload(platform: str, **extra) -> dict:
    """A payload with enough bulk that loading it is measurably wrong."""
    return {
        "platform": platform,
        "commenters": [
            {"handle": f"user{i}", "evidence": "x" * 400, "recent_activity": ["post"] * 20}
            for i in range(60)
        ],
        **extra,
    }


def _make(session, *, user_id: int, slug: str, url: str, payload: dict, target_id=None):
    return AccountRepository(session).create_investigation(
        user_id=user_id, slug=slug, label="An investigation", input_url=url,
        target_id=target_id, kind="comprehensive", overall_probability=0.5,
        overall_tier="moderate", summary="s", quota_used=1, payload_json=payload,
    )


# --------------------------------------------------------------------------- #
# Write path: the columns get populated
# --------------------------------------------------------------------------- #
def test_platform_is_persisted_from_the_payload_on_create():
    with get_session() as s:
        _make(s, user_id=1, slug="inv_a", url=_X_URL, payload=_big_payload("x"))
    with get_session() as s:
        inv = s.query(Investigation).filter_by(slug="inv_a").one()
        assert inv.platform == "x"


def test_youtube_thumbnail_is_derived_once_at_write_time():
    with get_session() as s:
        _make(s, user_id=1, slug="inv_b", url=_YT_URL,
              payload=_big_payload("youtube", video_id="dQw4w9WgXcQ"))
    with get_session() as s:
        inv = s.query(Investigation).filter_by(slug="inv_b").one()
        assert inv.platform == "youtube"
        assert inv.thumbnail_url == "https://i.ytimg.com/vi/dQw4w9WgXcQ/hqdefault.jpg"


def test_an_explicit_payload_thumbnail_wins():
    with get_session() as s:
        _make(s, user_id=1, slug="inv_c", url=_YT_URL,
              payload=_big_payload("youtube", video_id="dQw4w9WgXcQ",
                                   thumbnail_url="https://cdn.example.com/real.jpg"))
    with get_session() as s:
        assert s.query(Investigation).filter_by(slug="inv_c").one().thumbnail_url \
            == "https://cdn.example.com/real.jpg"


def test_a_continuation_batch_can_fill_in_a_missing_platform():
    """Later batches replace the merged payload, so the fields are re-derived on every write."""
    with get_session() as s:
        inv = _make(s, user_id=1, slug="inv_d", url="https://example.com/unknown",
                    payload={"commenters": []})
        assert inv.platform is None
        AccountRepository(s).update_investigation_payload(
            inv, payload_json=_big_payload("youtube", video_id="dQw4w9WgXcQ"),
        )
    with get_session() as s:
        inv = s.query(Investigation).filter_by(slug="inv_d").one()
        assert inv.platform == "youtube"
        assert inv.thumbnail_url


def test_an_unclassifiable_row_stays_null_instead_of_failing_the_write():
    with get_session() as s:
        inv = _make(s, user_id=1, slug="inv_e", url="https://example.com/whatever",
                    payload={"commenters": []})
        assert inv.platform is None and inv.thumbnail_url is None


# --------------------------------------------------------------------------- #
# Read path: the blob is never fetched
# --------------------------------------------------------------------------- #
def test_listing_investigations_never_selects_payload_json():
    """The core assertion, made against emitted SQL rather than by inspection."""
    with get_session() as s:
        for i in range(5):
            _make(s, user_id=7, slug=f"inv_p{i}", url=_YT_URL,
                  payload=_big_payload("youtube", video_id="dQw4w9WgXcQ"))

    statements: list[str] = []

    def _record(conn, cursor, statement, *args):
        statements.append(statement)

    with get_session() as s:
        event.listen(s.bind, "before_cursor_execute", _record)
        try:
            rows = AccountRepository(s).list_user_investigations(7, limit=100)
            # Touch every field the summary builder uses, so a lazy load would show up below.
            from app.routes.investigations import _to_summary
            summaries = [_to_summary(r) for r in rows]
        finally:
            event.remove(s.bind, "before_cursor_execute", _record)

    assert len(summaries) == 5
    selects = [st for st in statements if st.lstrip().upper().startswith("SELECT")]
    assert selects, "expected at least the list query to be recorded"
    offenders = [st for st in selects if "payload_json" in st]
    assert not offenders, (
        "payload_json was fetched while listing investigations — either load_only() was dropped or "
        f"the summary builder reads the payload again (lazy load). Offending SQL: {offenders[:1]}"
    )
    # One query for the list; no per-row follow-ups.
    assert len(selects) == 1, (
        f"expected a single SELECT for the whole list, got {len(selects)} — that is an N+1: {selects}"
    )


def test_the_summary_still_reports_platform_and_thumbnail_from_the_columns():
    with get_session() as s:
        _make(s, user_id=8, slug="inv_q", url=_YT_URL,
              payload=_big_payload("youtube", video_id="dQw4w9WgXcQ"))
    with get_session() as s:
        from app.routes.investigations import _to_summary
        rows = AccountRepository(s).list_user_investigations(8, limit=10)
        out = _to_summary(rows[0])
        assert out.platform == "youtube"
        assert out.thumbnail_url and out.thumbnail_url.endswith("/hqdefault.jpg")


def test_legacy_rows_with_null_columns_still_resolve_from_the_url():
    """Rows written before the columns existed must not lose their platform."""
    with get_session() as s:
        inv = _make(s, user_id=9, slug="inv_r", url=_YT_URL,
                    payload=_big_payload("youtube", video_id="dQw4w9WgXcQ"),
                    target_id="dQw4w9WgXcQ")
        inv.platform = None          # simulate a pre-migration row
        inv.thumbnail_url = None
        s.flush()
    with get_session() as s:
        from app.routes.investigations import _to_summary
        rows = AccountRepository(s).list_user_investigations(9, limit=10)
        out = _to_summary(rows[0])
        assert out.platform == "youtube", "URL fallback must still work without the payload"
        assert out.thumbnail_url, "thumbnail should be derivable from target_id"
