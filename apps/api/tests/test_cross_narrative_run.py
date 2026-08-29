"""The pass, the queue, and the dismissals.

Two properties matter most. The pass is RESUMABLE rather than restartable, because the loop it runs
in dies on every deploy and the assignment stage embeds, so redoing work is spend and skipping it is
a silent gap in the corpus. And a dismissal survives the next pass, because an operator who has
already said "this was a news story" must not be asked again every fifteen minutes.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.narrative.cross import run as cross_run
from app.narrative.cross import store
from app.narrative.embeddings import set_embedder_for_tests
from app.storage.db import get_session, reset_db_for_tests
from app.storage.models import CrossFinding, CrossTopic, Investigation, Utterance

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


def _seed(session, *, user_id: int, rows: list[tuple[str, str, datetime, str]]) -> None:
    _counter["n"] += 1
    inv = Investigation(
        user_id=user_id, slug=f"inv_{_counter['n']}", label="t", input_url="https://x.com/1",
        target_id="p1", kind="comprehensive", overall_probability=0.1, overall_tier="low",
        summary="", payload_json={"video": {"commenters": [
            {
                "external_id": account, "handle": account, "platform": "x", "tier": tier,
                "parent_id": "p1",
                "thread_comments": [{"text": text, "created_at": at.isoformat(),
                                     "parent_id": "p1"}],
            }
            for account, text, at, tier in rows
        ]}},
    )
    session.add(inv)
    session.flush()


def _worked_topic(session) -> None:
    """Four quiet weeks, then a week where three customers land on elevated accounts."""
    for offset in range(8, 36):
        _seed(session, user_id=1, rows=[
            (f"reg{offset}_{i}", f"an ordinary water discussion post {offset}-{i}",
             NOW - timedelta(days=offset), "low")
            for i in range(4)
        ])
        _seed(session, user_id=1, rows=[
            (f"eltn{offset}_{i}", f"an ordinary election discussion post {offset}-{i}",
             NOW - timedelta(days=offset), "low")
            for i in range(4)
        ])
    for offset in range(1, 7):
        for customer in (1, 2, 3):
            _seed(session, user_id=customer, rows=[
                (f"op{customer}_{offset}_{i}",
                 f"the water contract is a scandal, share this {offset}-{i}",
                 NOW - timedelta(days=offset), "elevated")
                for i in range(6)
            ])


def _drain(session, *, passes: int = 40) -> cross_run.PassReport:
    last = cross_run.PassReport()
    for _ in range(passes):
        last = cross_run.run_one_pass(session, now=NOW)
    return last


# ---------------------------------------------------------------------------
# The pass
# ---------------------------------------------------------------------------


def test_a_pass_is_bounded_and_the_next_one_continues() -> None:
    set_embedder_for_tests(_AxisEmbedder())
    with get_session() as session:
        for i in range(store.BACKFILL_BATCH + 5):
            _seed(session, user_id=1, rows=[
                (f"a{i}", f"a water treatment discussion number {i}", NOW - timedelta(days=2), "low")
            ])
        session.commit()

    with get_session() as session:
        first = cross_run.run_one_pass(session, now=NOW)
        session.commit()
    assert first.investigations_extracted == store.BACKFILL_BATCH

    with get_session() as session:
        second = cross_run.run_one_pass(session, now=NOW)
        session.commit()
    assert second.investigations_extracted == 5

    with get_session() as session:
        third = cross_run.run_one_pass(session, now=NOW)
        session.commit()
    # Nothing left. A restartable pass would have redone all thirty, re-embedding them for nothing.
    assert third.investigations_extracted == 0


def test_running_the_pass_repeatedly_does_not_duplicate_anything() -> None:
    set_embedder_for_tests(_AxisEmbedder())
    with get_session() as session:
        _seed(session, user_id=1, rows=[
            ("a1", "a water treatment discussion worth reading", NOW - timedelta(days=2), "low")
        ])
        session.commit()

    with get_session() as session:
        _drain(session, passes=5)
        session.commit()

    with get_session() as session:
        assert session.query(Utterance).count() == 1
        assert session.query(CrossTopic).count() == 1
        # One row per (topic, window), so a pass re-run for the same window updates rather than
        # stacking. The scheduler re-runs constantly by design.
        assert session.query(CrossFinding).count() == 1


def test_the_pass_writes_a_finding_carrying_both_scores_separately() -> None:
    set_embedder_for_tests(_AxisEmbedder())
    with get_session() as session:
        _worked_topic(session)
        session.commit()
    with get_session() as session:
        _drain(session)
        session.commit()

    with get_session() as session:
        row = (
            session.query(CrossFinding)
            .filter(CrossFinding.label.like("%water%"))
            .order_by(CrossFinding.anomaly_score.desc())
            .first()
        )

    assert row is not None
    assert row.anomaly_score > 0
    # The components survive to the reader, because which one carried a finding is most of what
    # tells them whether to believe it.
    assert row.volume > 0 and row.tier_mix > 0 and row.independence > 0
    detail = row.anomaly_detail_json
    assert detail["distinct_customers"] == 3
    assert detail["tier_mix_p"] is not None
    assert detail["corpus_scored"] > 0


def test_an_untestable_topic_keeps_its_refusals_on_the_record() -> None:
    set_embedder_for_tests(_AxisEmbedder())
    with get_session() as session:
        _seed(session, user_id=1, rows=[
            ("a1", "a single water comment and nothing else at all", NOW - timedelta(days=2), "low")
        ])
        session.commit()
    with get_session() as session:
        _drain(session, passes=5)
        session.commit()

    with get_session() as session:
        row = session.query(CrossFinding).one()
    # "We looked and could not judge" has to reach the operator. Dropping it makes untestable
    # indistinguishable from clean.
    assert row.anomaly_score == 0.0
    assert row.anomaly_detail_json["refusals"]


# ---------------------------------------------------------------------------
# The queue
# ---------------------------------------------------------------------------


def _client() -> TestClient:
    return TestClient(app)


def test_the_queue_reports_what_the_store_holds_so_it_can_be_watched_filling_up() -> None:
    set_embedder_for_tests(_AxisEmbedder())
    with get_session() as session:
        _seed(session, user_id=1, rows=[
            ("a1", "a water treatment discussion worth reading", NOW - timedelta(days=2), "low")
        ])
        session.commit()
    with get_session() as session:
        _drain(session, passes=5)
        session.commit()

    body = _client().get("/v1/admin/cross-narratives").json()
    assert body["store"]["utterances"] == 1
    assert body["store"]["distinct_customers"] == 1
    # A number that only ever grows means the embedder is down, which is otherwise invisible.
    assert body["pending_assignment"] == 0
    assert "corpus" in body["scope_note"]


def test_the_queue_never_reports_who_scanned_what() -> None:
    set_embedder_for_tests(_AxisEmbedder())
    with get_session() as session:
        _worked_topic(session)
        session.commit()
    with get_session() as session:
        _drain(session)
        session.commit()

    body = _client().get("/v1/admin/cross-narratives?status=all").json()
    serialised = repr(body)
    # The value is in the independence, not the identity. `distinct_customers` is a count.
    assert "user_id" not in serialised
    assert "customer_id" not in serialised
    assert any(f["anomaly_detail"].get("distinct_customers") for f in body["findings"])


def test_a_dismissal_needs_a_reason_and_survives_the_next_pass() -> None:
    set_embedder_for_tests(_AxisEmbedder())
    with get_session() as session:
        _worked_topic(session)
        session.commit()
    with get_session() as session:
        _drain(session)
        session.commit()

    client = _client()
    finding = client.get("/v1/admin/cross-narratives").json()["findings"][0]

    # A dismissal with no reason records that somebody was unconvinced and nothing about why, which
    # cannot be fitted against. These dismissals are the only ground truth this will ever get.
    assert client.post(f"/v1/admin/cross-narratives/{finding['id']}/dismiss", json={}).status_code == 422

    dismissed = client.post(
        f"/v1/admin/cross-narratives/{finding['id']}/dismiss",
        json={"reason": "local news story, the accounts are ordinary"},
    ).json()
    assert dismissed["status"] == "dismissed"

    with get_session() as session:
        _drain(session, passes=3)
        session.commit()

    with get_session() as session:
        row = session.get(CrossFinding, finding["id"])
        assert row.status == "dismissed"
        assert row.dismissal_reason


def test_a_dismissal_can_be_undone_and_the_reason_is_kept() -> None:
    set_embedder_for_tests(_AxisEmbedder())
    with get_session() as session:
        _worked_topic(session)
        session.commit()
    with get_session() as session:
        _drain(session)
        session.commit()

    client = _client()
    finding = client.get("/v1/admin/cross-narratives").json()["findings"][0]
    client.post(
        f"/v1/admin/cross-narratives/{finding['id']}/dismiss",
        json={"reason": "mistaken"},
    )
    reopened = client.post(f"/v1/admin/cross-narratives/{finding['id']}/reopen").json()
    assert reopened["status"] == "open"
    # Kept, because it is training data either way.
    assert reopened["dismissal_reason"] == "mistaken"


def test_the_open_filter_is_what_an_operator_sees_by_default() -> None:
    set_embedder_for_tests(_AxisEmbedder())
    with get_session() as session:
        _worked_topic(session)
        session.commit()
    with get_session() as session:
        _drain(session)
        session.commit()

    client = _client()
    before = client.get("/v1/admin/cross-narratives").json()["total"]
    finding = client.get("/v1/admin/cross-narratives").json()["findings"][0]
    client.post(
        f"/v1/admin/cross-narratives/{finding['id']}/dismiss", json={"reason": "news"},
    )
    after = client.get("/v1/admin/cross-narratives").json()["total"]
    assert after == before - 1
    assert client.get("/v1/admin/cross-narratives?status=all").json()["total"] == before
