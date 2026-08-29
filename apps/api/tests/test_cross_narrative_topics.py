"""Topic assignment and the topic-day rollup.

Two properties carry most of the weight. Topics are EMERGENT, so nothing here names a subject and
the test corpus proves separation rather than recognition. And the rollup buckets on POST time, so
one scan of a month-old thread spreads across the days it was actually written on instead of
spiking on the day we happened to look at it.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.narrative.cross import rollup, store, topics
from app.narrative.embeddings import EmbeddingUnavailable, set_embedder_for_tests
from app.storage.db import get_session, reset_db_for_tests
from app.storage.models import CrossTopic, CrossTopicDay, Investigation, Utterance


@pytest.fixture(autouse=True)
def _fresh_db():
    reset_db_for_tests()
    yield
    set_embedder_for_tests(None)


class _AxisEmbedder:
    """Four orthogonal axes, chosen by a keyword. Enough to prove separation without a real model."""

    dimensions = 4
    space = "axis-test:4"

    _AXES = {"water": 0, "election": 1, "vaccine": 2}

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self.embed_one(t) for t in texts]

    def embed_one(self, text: str) -> list[float]:
        vec = [0.0] * 4
        lowered = (text or "").lower()
        for word, axis in self._AXES.items():
            if word in lowered:
                vec[axis] = 1.0
                return vec
        vec[3] = 1.0
        return vec


def _seed(session, *, slug: str, user_id: int, rows: list[tuple[str, str, str | None, str]]):
    """rows: (account, text, iso timestamp or None, tier)."""
    inv = Investigation(
        user_id=user_id, slug=slug, label="t", input_url="https://x.com/1",
        kind="comprehensive", overall_probability=0.1, overall_tier="low", summary="",
        payload_json={"video": {"commenters": [
            {
                "external_id": account, "handle": f"@{account}", "platform": "x", "tier": tier,
                "thread_comments": [{"text": text, "created_at": at}],
            }
            for account, text, at, tier in rows
        ]}},
    )
    session.add(inv)
    session.flush()
    store.ingest_investigation(session, inv)
    return inv


LONG_WATER = "the water treatment contract was awarded with no tender at all"
LONG_ELECTION = "the election result in that county was certified far too quickly"


# ---------------------------------------------------------------------------
# Assignment
# ---------------------------------------------------------------------------


def test_unrelated_subjects_land_in_different_topics_with_nobody_naming_them() -> None:
    set_embedder_for_tests(_AxisEmbedder())
    with get_session() as session:
        _seed(session, slug="i1", user_id=1, rows=[
            ("a1", LONG_WATER, "2026-03-01T09:00:00Z", "low"),
            ("a2", LONG_ELECTION, "2026-03-01T09:05:00Z", "low"),
        ])
        session.commit()

    with get_session() as session:
        result = topics.assign_pending(session)
        session.commit()

    assert result.assigned == 2
    assert result.topics_created == 2
    with get_session() as session:
        labels = [t.label for t in session.query(CrossTopic).all()]
    # The label is derived from the topic's own contents. No taxonomy anywhere produced it.
    assert any("water" in label for label in labels)
    assert any("election" in label for label in labels)


def test_the_same_subject_from_two_customers_joins_one_topic() -> None:
    set_embedder_for_tests(_AxisEmbedder())
    with get_session() as session:
        _seed(session, slug="i1", user_id=1, rows=[("a1", LONG_WATER, "2026-03-01T09:00:00Z", "low")])
        _seed(session, slug="i2", user_id=2, rows=[
            ("a2", "another water treatment story from a different angle entirely", "2026-03-02T09:00:00Z", "low"),
        ])
        session.commit()

    with get_session() as session:
        topics.assign_pending(session)
        session.commit()

    with get_session() as session:
        assert session.query(CrossTopic).count() == 1
        topic = session.query(CrossTopic).one()
        assert topic.utterance_count == 2
        assert topic.account_count == 2


def test_assignment_is_resumable_rather_than_restartable() -> None:
    set_embedder_for_tests(_AxisEmbedder())
    with get_session() as session:
        _seed(session, slug="i1", user_id=1, rows=[
            (f"a{i}", f"{LONG_WATER} number {i}", "2026-03-01T09:00:00Z", "low")
            for i in range(4)
        ])
        session.commit()

    with get_session() as session:
        assert topics.assign_pending(session, limit=2).assigned == 2
        session.commit()
    with get_session() as session:
        # The queue is `topic_id IS NULL`, so the remainder is exactly where it was left.
        assert topics.pending_count(session) == 2
        assert topics.assign_pending(session, limit=10).assigned == 2
        session.commit()
    with get_session() as session:
        assert topics.pending_count(session) == 0
        assert topics.assign_pending(session).assigned == 0


def test_an_unavailable_embedder_assigns_nothing_rather_than_using_another_one() -> None:
    class _Down:
        dimensions = 4
        space = "api:down:4"

        def embed(self, texts: list[str]) -> list[list[float]]:
            raise EmbeddingUnavailable("provider unreachable")

        def embed_one(self, text: str) -> list[float]:
            raise EmbeddingUnavailable("provider unreachable")

    set_embedder_for_tests(_AxisEmbedder())
    with get_session() as session:
        _seed(session, slug="i1", user_id=1, rows=[("a1", LONG_WATER, "2026-03-01T09:00:00Z", "low")])
        session.commit()

    set_embedder_for_tests(_Down())
    with get_session() as session:
        result = topics.assign_pending(session)
        session.commit()

    assert result.skipped is True
    assert result.assigned == 0
    with get_session() as session:
        # Still queued, still recoverable. A topic spawned in the wrong space would not have been.
        assert topics.pending_count(session) == 1
        assert session.query(CrossTopic).count() == 0


# ---------------------------------------------------------------------------
# The rollup
# ---------------------------------------------------------------------------


def _assign_all(session) -> int:
    topics.assign_pending(session, limit=1000)
    return session.query(CrossTopic).one().id


def test_days_are_bucketed_on_when_the_comment_was_posted() -> None:
    set_embedder_for_tests(_AxisEmbedder())
    with get_session() as session:
        # One scan, three days of history under it. Bucketing on the scan time would report a
        # single spike on today and call it a burst.
        _seed(session, slug="i1", user_id=1, rows=[
            ("a1", f"{LONG_WATER} one", "2026-03-01T09:00:00Z", "low"),
            ("a2", f"{LONG_WATER} two", "2026-03-02T09:00:00Z", "low"),
            ("a3", f"{LONG_WATER} three", "2026-03-03T09:00:00Z", "low"),
        ])
        topic_id = _assign_all(session)
        rollup.rollup_topic(session, topic_id, now=datetime(2026, 3, 4, tzinfo=timezone.utc))
        session.commit()

    with get_session() as session:
        days = sorted(d.day for d in session.query(CrossTopicDay).all())
    assert days == ["2026-03-01", "2026-03-02", "2026-03-03"]


def test_an_utterance_with_no_post_time_is_left_out_rather_than_dated_to_today() -> None:
    set_embedder_for_tests(_AxisEmbedder())
    with get_session() as session:
        _seed(session, slug="i1", user_id=1, rows=[
            ("a1", f"{LONG_WATER} one", "2026-03-01T09:00:00Z", "low"),
            ("a2", f"{LONG_WATER} two", None, "low"),
        ])
        topic_id = _assign_all(session)
        rollup.rollup_topic(session, topic_id, now=datetime(2026, 3, 4, tzinfo=timezone.utc))
        session.commit()

    with get_session() as session:
        rows = session.query(CrossTopicDay).all()
    assert len(rows) == 1
    assert rows[0].utterances == 1


def test_distinct_customers_is_counted_not_summed() -> None:
    set_embedder_for_tests(_AxisEmbedder())
    with get_session() as session:
        # Three customers, independently, on one day. This is the number the whole system exists
        # to measure, and it is the one a customer cannot compute for themselves.
        for user_id in (1, 2, 3):
            _seed(session, slug=f"i{user_id}", user_id=user_id, rows=[
                (f"a{user_id}", f"{LONG_WATER} from customer {user_id}", "2026-03-01T09:00:00Z", "low"),
            ])
        topic_id = _assign_all(session)
        rollup.rollup_topic(session, topic_id, now=datetime(2026, 3, 2, tzinfo=timezone.utc))
        session.commit()

    with get_session() as session:
        row = session.query(CrossTopicDay).one()
    assert row.distinct_customers == 3
    assert row.distinct_investigations == 3
    assert row.distinct_accounts == 3


def test_the_tier_mix_counts_accounts_and_not_comments() -> None:
    set_embedder_for_tests(_AxisEmbedder())
    with get_session() as session:
        # One elevated account talking forty times is ONE elevated account. Counting comments would
        # let a single prolific bot carry the binomial tail on its own.
        rows = [("loud", f"{LONG_WATER} take {i}", "2026-03-01T09:00:00Z", "elevated") for i in range(5)]
        rows.append(("quiet", f"{LONG_WATER} just once", "2026-03-01T10:00:00Z", "low"))
        _seed(session, slug="i1", user_id=1, rows=rows)
        topic_id = _assign_all(session)
        rollup.rollup_topic(session, topic_id, now=datetime(2026, 3, 2, tzinfo=timezone.utc))
        session.commit()

    with get_session() as session:
        row = session.query(CrossTopicDay).one()
    assert row.utterances == 6
    assert row.scored_accounts == 2
    assert row.elevated_accounts == 1


def test_novelty_counts_accounts_never_seen_on_this_topic_before() -> None:
    set_embedder_for_tests(_AxisEmbedder())
    with get_session() as session:
        _seed(session, slug="i1", user_id=1, rows=[
            ("a1", f"{LONG_WATER} day one", "2026-03-01T09:00:00Z", "low"),
            ("a1", f"{LONG_WATER} day two", "2026-03-02T09:00:00Z", "low"),
            ("a2", f"{LONG_WATER} newcomer", "2026-03-02T10:00:00Z", "low"),
        ])
        topic_id = _assign_all(session)
        rollup.rollup_topic(session, topic_id, now=datetime(2026, 3, 3, tzinfo=timezone.utc))
        session.commit()

    with get_session() as session:
        days = {d.day: d for d in session.query(CrossTopicDay).all()}
    assert days["2026-03-01"].novel_accounts == 1
    # a1 is not new on the second day; a2 is.
    assert days["2026-03-02"].novel_accounts == 1


def test_rolling_up_twice_does_not_double_a_day() -> None:
    set_embedder_for_tests(_AxisEmbedder())
    with get_session() as session:
        _seed(session, slug="i1", user_id=1, rows=[("a1", LONG_WATER, "2026-03-01T09:00:00Z", "low")])
        topic_id = _assign_all(session)
        now = datetime(2026, 3, 2, tzinfo=timezone.utc)
        rollup.rollup_topic(session, topic_id, now=now)
        rollup.rollup_topic(session, topic_id, now=now)
        session.commit()

    with get_session() as session:
        rows = session.query(CrossTopicDay).all()
    assert len(rows) == 1 and rows[0].utterances == 1


def test_the_corpus_base_rate_can_exclude_the_topic_under_test() -> None:
    set_embedder_for_tests(_AxisEmbedder())
    with get_session() as session:
        _seed(session, slug="i1", user_id=1, rows=[
            ("a1", LONG_WATER, "2026-03-01T09:00:00Z", "elevated"),
            ("a2", LONG_ELECTION, "2026-03-01T09:00:00Z", "low"),
        ])
        topics.assign_pending(session, limit=1000)
        for topic in session.query(CrossTopic).all():
            rollup.rollup_topic(session, topic.id, now=datetime(2026, 3, 2, tzinfo=timezone.utc))
        session.commit()

    with get_session() as session:
        water = next(t for t in session.query(CrossTopic).all() if "water" in t.label)
        everything = rollup.corpus_elevated_rate(session)
        without = rollup.corpus_elevated_rate(session, exclude_topic_id=water.id)

    assert everything == (1, 2)
    # A cluster counted in its own background inflates the distribution it is tested against and
    # hides itself. Excluding it is what makes the comparison mean anything.
    assert without == (0, 1)
