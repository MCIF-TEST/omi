"""The utterance store: extraction, idempotency, and the retention rule.

The property worth the most here is idempotency. The backfill is driven by a scheduler that dies on
every deploy and by an operator who will run it twice to be sure, so a second pass that doubled
every row would double every volume and tier-mix number that every score is computed from, and
nothing anywhere would look wrong.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.narrative.cross import store
from app.storage.db import get_session, reset_db_for_tests
from app.storage.models import Investigation, Utterance


@pytest.fixture(autouse=True)
def _fresh_db():
    reset_db_for_tests()
    yield


def _payload(commenters: list[dict]) -> dict:
    return {"video": {"commenters": commenters}}


def _commenter(ext: str, comments: list[dict], *, tier: str = "low", platform: str = "x") -> dict:
    return {
        "external_id": ext,
        "handle": f"@{ext}",
        "platform": platform,
        "tier": tier,
        "thread_comments": comments,
    }


def _comment(text: str, at: datetime | str | None = None) -> dict:
    return {"text": text, "created_at": at}


LONG = "the water treatment plant contract was awarded without any tender"


def _investigation(session, *, user_id: int = 1, slug: str = "inv_1", payload: dict | None = None):
    inv = Investigation(
        user_id=user_id, slug=slug, label="t", input_url="https://x.com/1",
        kind="comprehensive", overall_probability=0.1, overall_tier="low",
        summary="", payload_json=payload or {},
    )
    session.add(inv)
    session.flush()
    return inv


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------


def test_it_reads_the_comments_made_under_the_scanned_post() -> None:
    at = datetime(2026, 3, 1, 9, tzinfo=timezone.utc)
    rows = store.extract(_payload([_commenter("a1", [_comment(LONG, at)], tier="elevated")]))
    assert len(rows) == 1
    assert rows[0].account_external_id == "a1"
    assert rows[0].posted_at == at
    # Frozen at extraction: re-reading a later score would rewrite the history the tier-mix test
    # is measured against.
    assert rows[0].tier == "elevated"


def test_the_accounts_own_timeline_is_not_read_as_a_topic() -> None:
    # `recent_activity` says what an account talks about generally. Counting it here would let one
    # prolific account's unrelated history dominate a topic it barely touched.
    payload = _payload([{
        "external_id": "a1", "platform": "x", "tier": "low",
        "thread_comments": [_comment(LONG)],
        "recent_activity": [{"text": "something else entirely about football and nothing here"}],
    }])
    rows = store.extract(payload)
    assert len(rows) == 1
    assert "water" in rows[0].text


def test_short_comments_are_dropped() -> None:
    # "nice", "lol", "first" cluster into one enormous meaningless blob and drown real topics.
    rows = store.extract(_payload([_commenter("a1", [_comment("nice"), _comment(LONG)])]))
    assert len(rows) == 1


def test_an_iso_string_timestamp_is_understood() -> None:
    rows = store.extract(_payload([_commenter("a1", [_comment(LONG, "2026-03-01T09:00:00Z")])]))
    assert rows[0].posted_at == datetime(2026, 3, 1, 9, tzinfo=timezone.utc)


def test_an_unparseable_timestamp_is_unknown_rather_than_now() -> None:
    rows = store.extract(_payload([_commenter("a1", [_comment(LONG, "not-a-date")])]))
    assert rows[0].posted_at is None


def test_a_malformed_payload_yields_nothing_rather_than_raising() -> None:
    assert store.extract({}) == []
    assert store.extract({"video": None}) == []
    assert store.extract({"video": {"commenters": ["not-a-dict"]}}) == []


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------


def test_extracting_the_same_investigation_twice_writes_one_set_of_rows() -> None:
    # An ISO string, because `payload_json` is JSON and that is what production actually stores.
    payload = _payload([_commenter("a1", [_comment(LONG, "2026-03-01T00:00:00Z")])])
    with get_session() as session:
        inv = _investigation(session, payload=payload)
        assert store.ingest_investigation(session, inv) == 1
        assert store.ingest_investigation(session, inv) == 0
        session.commit()

    with get_session() as session:
        assert session.query(Utterance).count() == 1


def test_the_same_comment_reached_through_two_customers_is_one_comment() -> None:
    # Two customers scanning the same post is not two comments, and counting it twice would inflate
    # every volume number with our own duplication.
    payload = _payload([_commenter("a1", [_comment(LONG, "2026-03-01T00:00:00Z")])])
    with get_session() as session:
        first = _investigation(session, user_id=1, slug="inv_1", payload=payload)
        second = _investigation(session, user_id=2, slug="inv_2", payload=payload)
        store.ingest_investigation(session, first)
        store.ingest_investigation(session, second)
        session.commit()

    with get_session() as session:
        assert session.query(Utterance).count() == 1


def test_the_backfill_resumes_from_its_watermark() -> None:
    with get_session() as session:
        for i in range(3):
            _investigation(
                session, slug=f"inv_{i}",
                payload=_payload([_commenter(f"a{i}", [_comment(f"{LONG} number {i}")])]),
            )
        session.commit()

    with get_session() as session:
        seen, written = store.backfill(session, limit=2)
        session.commit()
    assert (seen, written) == (2, 2)

    with get_session() as session:
        seen, written = store.backfill(session, limit=2)
        session.commit()
    # The third only. A restart would have redone the first two, re-embedding them later for nothing.
    assert (seen, written) == (1, 1)

    with get_session() as session:
        assert store.backfill(session, limit=2) == (0, 0)


def test_one_malformed_investigation_does_not_stop_the_ones_behind_it() -> None:
    with get_session() as session:
        _investigation(session, slug="inv_bad", payload={"video": {"commenters": [None]}})
        _investigation(
            session, slug="inv_good",
            payload=_payload([_commenter("a1", [_comment(LONG)])]),
        )
        session.commit()

    with get_session() as session:
        seen, written = store.backfill(session, limit=10)
        session.commit()
    assert seen == 2 and written == 1


# ---------------------------------------------------------------------------
# Retention
# ---------------------------------------------------------------------------


def test_expired_text_is_dropped_but_the_row_and_its_counts_survive() -> None:
    with get_session() as session:
        inv = _investigation(session, payload=_payload([_commenter("a1", [_comment(LONG)])]))
        store.ingest_investigation(session, inv)
        session.commit()

    later = datetime.now(timezone.utc) + timedelta(days=store.TEXT_RETENTION_DAYS + 1)
    with get_session() as session:
        assert store.purge_expired_text(session, now=later) == 1
        session.commit()

    with get_session() as session:
        row = session.query(Utterance).one()
        assert row.text is None
        # The row is what the rolling counts are computed from, so detection survives the text going.
        assert row.account_external_id == "a1"
        assert store.store_stats(session)["utterances"] == 1
        assert store.store_stats(session)["text_retained"] == 0


def test_purging_is_safe_to_run_repeatedly() -> None:
    with get_session() as session:
        inv = _investigation(session, payload=_payload([_commenter("a1", [_comment(LONG)])]))
        store.ingest_investigation(session, inv)
        session.commit()

    later = datetime.now(timezone.utc) + timedelta(days=store.TEXT_RETENTION_DAYS + 1)
    with get_session() as session:
        store.purge_expired_text(session, now=later)
        session.commit()
    with get_session() as session:
        assert store.purge_expired_text(session, now=later) == 0


def test_nothing_inside_the_window_is_touched() -> None:
    with get_session() as session:
        inv = _investigation(session, payload=_payload([_commenter("a1", [_comment(LONG)])]))
        store.ingest_investigation(session, inv)
        session.commit()
    with get_session() as session:
        assert store.purge_expired_text(session) == 0
        assert session.query(Utterance).one().text is not None


def test_the_post_is_taken_from_the_investigation_not_from_the_reply_chain() -> None:
    # A thread comment carries `parent_comment_id`, the comment it replied to, which is a different
    # thing from the post. The post is what distinguishes "two customers scanned the same thing"
    # from "two customers arrived independently", and it is what the cohort excludes from its
    # evidence, so reading the reply chain here would quietly break both.
    payload = _payload([{
        "external_id": "a1", "platform": "x", "tier": "low",
        "thread_comments": [{
            "text": LONG, "created_at": "2026-03-01T09:00:00Z",
            "parent_comment_id": "some_other_comment",
        }],
    }])
    with get_session() as session:
        inv = _investigation(session, payload=payload)
        inv.target_id = "the_real_post"
        store.ingest_investigation(session, inv)
        session.commit()

    with get_session() as session:
        assert session.query(Utterance).one().parent_id == "the_real_post"


def test_the_post_falls_back_to_the_payloads_own_video_id() -> None:
    # Rows written before `target_id` was reliably set still have it inside the payload.
    payload = {"video": {"video_id": "vid_from_payload", "commenters": [
        _commenter("a1", [_comment(LONG, "2026-03-01T09:00:00Z")]),
    ]}}
    with get_session() as session:
        inv = _investigation(session, payload=payload)
        inv.target_id = None
        store.ingest_investigation(session, inv)
        session.commit()

    with get_session() as session:
        assert session.query(Utterance).one().parent_id == "vid_from_payload"
