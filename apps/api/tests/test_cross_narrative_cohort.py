"""Score two: netdetect over the cross-investigation cohort.

The point of this layer is the union. An operation spread thinly over eight posts scanned by three
customers is invisible in each of those eight scans and obvious once the accounts are assembled in
one place, which is the one thing no single investigation and no single customer can do.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.narrative.cross import cohort, rollup, store, topics
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

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self.embed_one(t) for t in texts]

    def embed_one(self, text: str) -> list[float]:
        vec = [0.0] * 4
        vec[0 if "water" in (text or "").lower() else 1] = 1.0
        return vec


_counter = {"n": 0}


def _investigation(session, *, user_id: int, post: str, commenters: list[dict]) -> None:
    _counter["n"] += 1
    inv = Investigation(
        user_id=user_id, slug=f"inv_{_counter['n']}", label="t",
        input_url=f"https://x.com/{post}", target_id=post,
        kind="comprehensive", overall_probability=0.1, overall_tier="low", summary="",
        payload_json={"video": {"commenters": commenters}},
    )
    session.add(inv)
    session.flush()
    store.ingest_investigation(session, inv)


def _account(
    ext: str, post: str, *, text: str, at: datetime, client: str | None = None,
    created: str | None = None, tier: str = "low",
) -> dict:
    return {
        "external_id": ext,
        "handle": ext,
        "platform": "x",
        "tier": tier,
        "account_created_at": created,
        "bio": None,
        "parent_id": post,
        "thread_comments": [{
            "text": text, "created_at": at.isoformat(), "parent_id": post,
            "source_client": client,
        }],
        "recent_activity": [{
            "text": text, "created_at": at.isoformat(), "parent_id": post,
            "source_client": client,
        }],
    }


def _build(session) -> int:
    topics.assign_pending(session, limit=5000)
    for topic in session.query(CrossTopic).all():
        rollup.rollup_topic(session, topic.id, now=NOW)
    return next(t.id for t in session.query(CrossTopic).all() if "water" in t.label)


WATER = "the water treatment contract deserves a much closer look than it got"


def test_a_cohort_too_small_to_estimate_a_null_is_refused_and_says_so() -> None:
    set_embedder_for_tests(_AxisEmbedder())
    with get_session() as session:
        _investigation(session, user_id=1, post="p1", commenters=[
            _account(f"a{i}", "p1", text=f"{WATER} {i}", at=NOW - timedelta(days=2))
            for i in range(5)
        ])
        topic_id = _build(session)
        session.commit()

    with get_session() as session:
        result = cohort.score_topic_cohort(session, topic_id, now=NOW)

    assert result.detection is None
    # "We looked and could not test" is a different, more trustworthy statement than "we found
    # nothing", and the difference has to survive to the reader.
    assert result.refused is not None and "null" in result.refused


def test_an_enormous_cohort_is_refused_rather_than_searched() -> None:
    set_embedder_for_tests(_AxisEmbedder())
    with get_session() as session:
        for chunk in range(7):
            _investigation(session, user_id=1, post=f"p{chunk}", commenters=[
                _account(f"a{chunk}_{i}", f"p{chunk}", text=f"{WATER} {chunk} {i}",
                         at=NOW - timedelta(days=2))
                for i in range(100)
            ])
        topic_id = _build(session)
        session.commit()

    with get_session() as session:
        result = cohort.score_topic_cohort(session, topic_id, now=NOW)

    assert result.detection is None
    assert result.refused is not None and "formation" in result.refused


def test_the_cohort_is_assembled_across_investigations_and_customers() -> None:
    set_embedder_for_tests(_AxisEmbedder())
    with get_session() as session:
        # Three customers, three posts, ten accounts each. No single investigation holds the
        # cohort; the union does.
        for customer, post in ((1, "p1"), (2, "p2"), (3, "p3")):
            _investigation(session, user_id=customer, post=post, commenters=[
                _account(f"{post}_a{i}", post, text=f"{WATER} {post} {i}",
                         at=NOW - timedelta(days=2))
                for i in range(10)
            ])
        topic_id = _build(session)
        session.commit()

    with get_session() as session:
        result = cohort.score_topic_cohort(session, topic_id, now=NOW)

    assert result.accounts == 30
    assert result.investigations == 3
    assert result.detection is not None


def test_the_posts_the_topic_was_found_on_are_excluded_from_the_evidence() -> None:
    # Every account in the cohort engaged those posts by construction. Without the exclusion the
    # whole cohort shares a perfect feature and reports as one enormous operation, and here it is
    # worse than in a single scan because it would manufacture a link between every pair of posts.
    set_embedder_for_tests(_AxisEmbedder())
    with get_session() as session:
        for customer, post in ((1, "p1"), (2, "p2"), (3, "p3")):
            _investigation(session, user_id=customer, post=post, commenters=[
                _account(f"{post}_a{i}", post, text=f"{WATER} {post} {i}",
                         at=NOW - timedelta(days=2))
                for i in range(10)
            ])
        topic_id = _build(session)
        session.commit()

    with get_session() as session:
        result = cohort.score_topic_cohort(session, topic_id, now=NOW)

    assert result.excluded_contexts == 3
    # An ordinary cohort of strangers who happen to share a subject is not a finding.
    assert result.findings == []


def test_the_most_complete_block_wins_when_an_account_appears_twice() -> None:
    # The same account seen in two investigations has two blocks that differ mainly in how much
    # history each scan collected. Reading the thinner copy finds fewer features, which reads as
    # innocence the account has not earned.
    thin = {
        "external_id": "shared", "handle": "shared", "platform": "x", "tier": "low",
        "thread_comments": [], "recent_activity": [],
    }
    fat = {
        "external_id": "shared", "handle": "shared", "platform": "x", "tier": "low",
        "bio": "a bio", "account_created_at": "2020-01-01T00:00:00Z",
        "thread_comments": [{"text": "one", "created_at": NOW.isoformat()}],
        "recent_activity": [{"text": "two", "created_at": NOW.isoformat()}],
    }
    assert cohort._evidence_weight(fat) > cohort._evidence_weight(thin)


def test_nothing_here_reads_an_accounts_suspicion_score() -> None:
    """Coordination and botness are orthogonal axes.

    The operation worth catching is the one whose members each score 30 alone: a filter on
    suspicion is blind to it by construction, which is the defect the old 70+ cohort filter had.
    Proved behaviourally rather than by reading the source, because what matters is that the answer
    does not move, not that a particular field name is absent.
    """
    set_embedder_for_tests(_AxisEmbedder())
    with get_session() as session:
        for customer, post in ((1, "p1"), (2, "p2"), (3, "p3")):
            _investigation(session, user_id=customer, post=post, commenters=[
                _account(f"{post}_a{i}", post, text=f"{WATER} {post} {i}",
                         at=NOW - timedelta(days=2), tier="low")
                for i in range(10)
            ])
        topic_id = _build(session)
        session.commit()

    with get_session() as session:
        as_low = cohort.score_topic_cohort(session, topic_id, now=NOW)

    # Same accounts, same behaviour, every one of them now scored as high as the product goes.
    with get_session() as session:
        from app.storage.models import Investigation as _Inv

        for inv in session.query(_Inv).all():
            payload = dict(inv.payload_json)
            for row in payload["video"]["commenters"]:
                row["tier"] = "high"
                row["overall_probability"] = 0.99
                row["omi_score"] = 99
            inv.payload_json = payload
        session.commit()

    with get_session() as session:
        as_high = cohort.score_topic_cohort(session, topic_id, now=NOW)

    assert [c.members for c in as_low.findings] == [c.members for c in as_high.findings]
    assert [round(c.score, 6) for c in as_low.findings] \
        == [round(c.score, 6) for c in as_high.findings]
    assert as_low.accounts == as_high.accounts


# ---------------------------------------------------------------------------
# The narrative family: co-occurrence on OTHER topics.
#
# Only computable here. A single investigation has no topic assignment at all, so this is the one
# place netdetect's narrative family can be filled, and it is the paraphrase axis the embedding
# work was for.
# ---------------------------------------------------------------------------


def test_the_cohorts_own_topic_is_never_its_own_evidence() -> None:
    # Every member spoke on it by construction. Counting it would hand a perfect feature to the
    # whole cohort and report a topic's entire population as one operation.
    set_embedder_for_tests(_AxisEmbedder())
    with get_session() as session:
        for customer, post in ((1, "p1"), (2, "p2"), (3, "p3")):
            _investigation(session, user_id=customer, post=post, commenters=[
                _account(f"{post}_a{i}", post, text=f"{WATER} {post} {i}",
                         at=NOW - timedelta(days=2))
                for i in range(10)
            ])
        topic_id = _build(session)
        session.commit()

    with get_session() as session:
        others = cohort._other_topics(session, {"p1_a0", "p2_a0"}, topic_id)

    assert all(topic_id not in ts for ts in others.values())


def test_members_who_co_occur_elsewhere_carry_narrative_evidence() -> None:
    """The claim is not "these accounts talked about water", which is why they were assembled.

    It is "these accounts ALSO co-occur on a second, unrelated subject".
    """
    set_embedder_for_tests(_AxisEmbedder())
    with get_session() as session:
        # The water cohort, across three customers.
        for customer, post in ((1, "p1"), (2, "p2"), (3, "p3")):
            _investigation(session, user_id=customer, post=post, commenters=[
                _account(f"{post}_a{i}", post, text=f"{WATER} {post} {i}",
                         at=NOW - timedelta(days=2))
                for i in range(10)
            ])
        # A second, unrelated subject that some of the same accounts also turn up on.
        _investigation(session, user_id=1, post="p9", commenters=[
            _account("p1_a0", "p9", text="an entirely separate subject discussed at length here",
                     at=NOW - timedelta(days=3)),
            _account("p2_a0", "p9", text="the same separate subject from a different angle again",
                     at=NOW - timedelta(days=3)),
        ])
        topic_id = _build(session)
        session.commit()

    with get_session() as session:
        others = cohort._other_topics(session, {"p1_a0", "p2_a0", "p3_a0"}, topic_id)

    # The two that appeared on the second subject carry a topic the third does not.
    assert others.get("p1_a0")
    assert others.get("p2_a0")
    assert others.get("p1_a0") == others.get("p2_a0")
    assert "p3_a0" not in others


def test_the_cohort_result_reports_whether_the_family_had_anything_to_work_with() -> None:
    # An operator reading a finding needs to know the difference between "the narrative family
    # found nothing" and "the narrative family had no input", which are not the same statement.
    set_embedder_for_tests(_AxisEmbedder())
    with get_session() as session:
        for customer, post in ((1, "p1"), (2, "p2"), (3, "p3")):
            _investigation(session, user_id=customer, post=post, commenters=[
                _account(f"{post}_a{i}", post, text=f"{WATER} {post} {i}",
                         at=NOW - timedelta(days=2))
                for i in range(10)
            ])
        topic_id = _build(session)
        session.commit()

    with get_session() as session:
        result = cohort.score_topic_cohort(session, topic_id, now=NOW)

    assert result.shared_other_topics == 0
