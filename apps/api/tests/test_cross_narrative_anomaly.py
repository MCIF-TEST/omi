"""Score one: the topic anomaly.

The controls come first, because the confound here is real and does not improve with scale:
customers scan what they SUSPECT, so a news story that makes a subject topical pulls several
customers to it and spikes both volume and cross-customer independence with nothing manufactured.
The tier-mix test is the only thing separating that from an operation, which is why it is required
rather than weighted, and why the score is a product rather than an average.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.narrative.cross import anomaly, rollup, store, topics
from app.narrative.embeddings import set_embedder_for_tests
from app.storage.db import get_session, reset_db_for_tests
from app.storage.models import CrossTopic, Investigation

NOW = datetime(2026, 4, 1, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _fresh_db():
    reset_db_for_tests()
    yield
    set_embedder_for_tests(None)


class _AxisEmbedder:
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


_counter = {"n": 0}


def _seed(session, *, user_id: int, rows: list[tuple[str, str, datetime, str]]) -> None:
    _counter["n"] += 1
    inv = Investigation(
        user_id=user_id, slug=f"inv_{_counter['n']}", label="t", input_url="https://x.com/1",
        kind="comprehensive", overall_probability=0.1, overall_tier="low", summary="",
        payload_json={"video": {"commenters": [
            {
                "external_id": account, "handle": f"@{account}", "platform": "x", "tier": tier,
                "thread_comments": [{"text": text, "created_at": at.isoformat()}],
            }
            for account, text, at, tier in rows
        ]}},
    )
    session.add(inv)
    session.flush()
    store.ingest_investigation(session, inv)


def _build(session) -> None:
    topics.assign_pending(session, limit=5000)
    for topic in session.query(CrossTopic).all():
        rollup.rollup_topic(session, topic.id, now=NOW)


def _topic(session, word: str) -> int:
    return next(t.id for t in session.query(CrossTopic).all() if word in t.label)


def _day(offset: int) -> datetime:
    """`offset` days before NOW."""
    return NOW - timedelta(days=offset)


def _baseline(session, subject: str, *, accounts: int = 4, tier: str = "low") -> None:
    """Four weeks of quiet, ordinary traffic on a subject, from one customer."""
    for offset in range(8, 36):
        _seed(session, user_id=1, rows=[
            (f"reg{i}", f"an ordinary {subject} discussion post number {offset}-{i}",
             _day(offset), tier)
            for i in range(accounts)
        ])


# ---------------------------------------------------------------------------
# Controls: things that must NOT score
# ---------------------------------------------------------------------------


def test_a_viral_news_story_does_not_score_because_its_accounts_are_ordinary() -> None:
    # Volume spikes, three unrelated customers arrive, and the accounts are a representative
    # sample. This is the confound the whole design is built around: it must come out at zero.
    set_embedder_for_tests(_AxisEmbedder())
    with get_session() as session:
        _baseline(session, "water")
        for offset in range(1, 7):
            for customer in (1, 2, 3):
                _seed(session, user_id=customer, rows=[
                    (f"viral{customer}{offset}{i}",
                     f"everyone is talking about the water story today {offset}-{i}",
                     _day(offset), "low")
                    for i in range(8)
                ])
        _build(session)
        session.commit()

    with get_session() as session:
        scored = anomaly.score_topic(session, _topic(session, "water"), now=NOW)

    assert scored is not None
    assert scored.volume > 0, "volume genuinely spiked"
    assert scored.independence > 0, "three unrelated customers genuinely arrived"
    # And yet the finding is zero, because the population it recruited looks like everyone else.
    assert scored.tier_mix == 0.0
    assert scored.score == 0.0


def test_one_curious_customer_is_never_a_finding_however_hard_they_scan() -> None:
    set_embedder_for_tests(_AxisEmbedder())
    with get_session() as session:
        _baseline(session, "water")
        for offset in range(1, 7):
            _seed(session, user_id=1, rows=[
                (f"susp{offset}{i}", f"the water contract scandal thread {offset}-{i}",
                 _day(offset), "elevated")
                for i in range(10)
            ])
        _build(session)
        session.commit()

    with get_session() as session:
        scored = anomaly.score_topic(session, _topic(session, "water"), now=NOW)

    assert scored is not None
    assert scored.independence == 0.0
    assert any("customer" in r for r in scored.refusals)
    assert scored.score == 0.0


def test_a_topic_with_no_history_is_refused_rather_than_called_infinitely_spiky() -> None:
    set_embedder_for_tests(_AxisEmbedder())
    with get_session() as session:
        for customer in (1, 2, 3):
            _seed(session, user_id=customer, rows=[
                (f"new{customer}{i}", f"a brand new water topic nobody has seen {customer}-{i}",
                 _day(2), "elevated")
                for i in range(6)
            ])
        _build(session)
        session.commit()

    with get_session() as session:
        scored = anomaly.score_topic(session, _topic(session, "water"), now=NOW)

    assert scored is not None
    assert any("baseline" in r for r in scored.refusals)
    assert scored.score == 0.0


def test_a_handful_of_accounts_is_refused_because_the_ratio_is_noise() -> None:
    set_embedder_for_tests(_AxisEmbedder())
    with get_session() as session:
        _baseline(session, "water")
        for customer in (1, 2, 3):
            _seed(session, user_id=customer, rows=[
                (f"few{customer}", f"one water comment from customer {customer}", _day(2), "high"),
            ])
        _build(session)
        session.commit()

    with get_session() as session:
        scored = anomaly.score_topic(session, _topic(session, "water"), now=NOW)

    assert scored is not None
    assert any("scored accounts" in r for r in scored.refusals)
    assert scored.score == 0.0


# ---------------------------------------------------------------------------
# The case it exists to catch
# ---------------------------------------------------------------------------


def test_a_worked_topic_scores_on_all_three_components() -> None:
    set_embedder_for_tests(_AxisEmbedder())
    with get_session() as session:
        # An ordinary corpus, so the base rate of elevated accounts is low.
        _baseline(session, "water")
        _baseline(session, "election")
        # Then a week in which three unrelated customers land on the same subject and the accounts
        # they find are overwhelmingly elevated. Volume up, mix biased, independence real.
        for offset in range(1, 7):
            for customer in (1, 2, 3):
                _seed(session, user_id=customer, rows=[
                    (f"op{customer}{offset}{i}",
                     f"the water contract is a scandal, share this {offset}-{i}",
                     _day(offset), "elevated")
                    for i in range(6)
                ])
        _build(session)
        session.commit()

    with get_session() as session:
        scored = anomaly.score_topic(session, _topic(session, "water"), now=NOW)

    assert scored is not None, "topic exists"
    assert scored.testable, scored.refusals
    assert scored.volume > 0.0
    assert scored.tier_mix > 0.0
    assert scored.independence > 0.0
    assert scored.score > 0.0
    # The arithmetic is on the record, so a reader can check it rather than trust it.
    assert scored.scored_accounts >= anomaly.MIN_ACCOUNTS
    assert scored.tier_mix_p is not None and scored.tier_mix_p <= 0.05
    assert scored.corpus_scored > 0


# ---------------------------------------------------------------------------
# The pieces
# ---------------------------------------------------------------------------


def test_the_score_is_a_product_so_any_single_zero_refuses_the_topic() -> None:
    # Averaging would let a huge volume spike carry a topic whose accounts look completely
    # ordinary, which is every viral news story.
    from app.narrative.cross.anomaly import TopicAnomaly

    a = TopicAnomaly(topic_id=1, label="x", window_start="a", window_end="b")
    a.volume, a.tier_mix, a.independence = 1.0, 0.0, 1.0
    assert a.volume * a.tier_mix * a.independence == 0.0


def test_the_tier_mix_scale_is_logarithmic() -> None:
    assert anomaly.tier_mix_strength(0.2) == 0.0
    assert anomaly.tier_mix_strength(0.05) == pytest.approx(0.5, abs=0.01)
    assert anomaly.tier_mix_strength(0.0025) == pytest.approx(1.0, abs=0.01)
    # A linear scale would call these two nearly the same reading.
    assert anomaly.tier_mix_strength(0.04) < anomaly.tier_mix_strength(0.0001)


def test_the_binomial_tail_is_exact_at_the_edges() -> None:
    assert anomaly.binomial_tail(10, 0, 0.3) == 1.0
    assert anomaly.binomial_tail(10, 11, 0.3) == 0.0
    assert anomaly.binomial_tail(1, 1, 0.25) == pytest.approx(0.25)
    assert anomaly.binomial_tail(3, 3, 0.5) == pytest.approx(0.125)


def test_distinct_customers_is_counted_over_the_window_not_summed_per_day() -> None:
    # Two customers who scanned on DIFFERENT days are two customers. Taking a per-day maximum
    # would report one, and understate the only component nothing else can compute.
    set_embedder_for_tests(_AxisEmbedder())
    with get_session() as session:
        _seed(session, user_id=1, rows=[("a1", "a water comment on monday", _day(5), "low")])
        _seed(session, user_id=2, rows=[("a2", "a water comment on tuesday", _day(4), "low")])
        _build(session)
        session.commit()

    with get_session() as session:
        scored = anomaly.score_topic(session, _topic(session, "water"), now=NOW)

    assert scored is not None
    assert scored.distinct_customers == 2


def test_an_untestable_topic_is_returned_with_its_reasons_not_silently_dropped() -> None:
    set_embedder_for_tests(_AxisEmbedder())
    with get_session() as session:
        _seed(session, user_id=1, rows=[("a1", "a single lonely water comment with nothing around it", _day(2), "low")])
        _build(session)
        session.commit()

    with get_session() as session:
        results = anomaly.score_all(session, now=NOW)

    assert len(results) == 1
    # Dropping it would be indistinguishable from finding nothing, which is how a detector gets to
    # be broken in a way nobody can see.
    assert results[0].refusals
    assert results[0].score == 0.0
