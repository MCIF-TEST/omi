"""Tests for narrative clustering + ingestion + retrieval."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.narrative.clustering import best_match, cosine, update_centroid
from app.narrative.embeddings import (
    Embedder, HashingEmbedder, get_embedder, set_embedder_for_tests,
)
from app.narrative.service import IngestItem, NarrativeService
from app.storage.db import get_session, reset_db_for_tests


@pytest.fixture(autouse=True)
def _fresh_db():
    reset_db_for_tests()
    yield
    set_embedder_for_tests(None)


# ---------------------------------------------------------------------------
# A deterministic embedder for tests — maps known topics to known vectors so
# we can assert cluster membership without depending on sentence-transformers.
# ---------------------------------------------------------------------------


class _TopicEmbedder:
    """Tiny synthetic embedder. Keywords steer the vector toward a topic axis."""

    dimensions = 4
    space = "topic-test:4"

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self.embed_one(t) for t in texts]

    def embed_one(self, text: str) -> list[float]:
        t = (text or "").lower()
        vec = [0.0] * 4
        if "vaccine" in t or "vaccin" in t:        vec[0] += 1.0
        if "election" in t or "vote" in t:         vec[1] += 1.0
        if "crypto" in t or "btc" in t or "coin" in t: vec[2] += 1.0
        # Default mass on a "general" axis so empty texts still get a vector
        vec[3] += 0.3
        # Normalize
        norm = sum(v * v for v in vec) ** 0.5 or 1.0
        return [v / norm for v in vec]


# ---------------------------------------------------------------------------
# Clustering math
# ---------------------------------------------------------------------------


def test_cosine_unit_vectors():
    a = [1.0, 0.0]
    b = [1.0, 0.0]
    assert cosine(a, b) == pytest.approx(1.0)
    c = [0.0, 1.0]
    assert cosine(a, c) == pytest.approx(0.0)


def test_update_centroid_running_average():
    old = [1.0, 0.0]
    updated = update_centroid(old, 1, [0.0, 1.0])
    # Average of [1,0] and [0,1] = [0.5, 0.5] → normalized = [√½, √½]
    assert updated[0] == pytest.approx(updated[1])


def test_best_match_returns_none_when_no_candidates():
    decision = best_match([1.0, 0.0], [])
    assert decision.narrative_id is None


def test_best_match_assigns_when_above_threshold():
    candidates = [(7, [1.0, 0.0], 1)]
    decision = best_match([0.99, 0.01], candidates, match_threshold=0.9)
    assert decision.narrative_id == 7


def test_best_match_spawns_when_below_threshold():
    candidates = [(7, [1.0, 0.0], 1)]
    decision = best_match([0.0, 1.0], candidates, match_threshold=0.9)
    assert decision.narrative_id is None


# ---------------------------------------------------------------------------
# End-to-end ingest → list_trending
# ---------------------------------------------------------------------------


def test_ingest_clusters_same_topic_together():
    set_embedder_for_tests(_TopicEmbedder())
    items = [
        IngestItem("the vaccine is safe and effective for everyone", "youtube", "acct-A"),
        IngestItem("vaccine rollout is going smoothly worldwide", "youtube", "acct-B"),
        IngestItem("vaccines are critical for public health", "youtube", "acct-C"),
        IngestItem("the election was free and fair this year", "youtube", "acct-D"),
        IngestItem("crypto is the future of finance", "youtube", "acct-E"),
    ]
    with get_session() as session:
        service = NarrativeService(session, embedder=_TopicEmbedder())
        n = service.ingest_batch(items)
        assert n == 5
        trending = service.list_trending(window_days=30, limit=10)

    # Three topics → 3 narratives
    assert len(trending) == 3
    # The vaccine narrative should have 3 distinct authors
    top = max(trending, key=lambda t: t.member_count)
    assert top.member_count == 3
    assert top.distinct_authors == 3


def test_short_comments_are_skipped():
    set_embedder_for_tests(_TopicEmbedder())
    items = [
        IngestItem("lol", "youtube", "a"),
        IngestItem("nice", "youtube", "b"),
        IngestItem("vaccines are essential for public well-being", "youtube", "c"),
    ]
    with get_session() as session:
        service = NarrativeService(session, embedder=_TopicEmbedder())
        n = service.ingest_batch(items)
        assert n == 1


def test_distinct_authors_only_bumped_on_new_author():
    set_embedder_for_tests(_TopicEmbedder())
    items = [
        IngestItem("vaccines are safe and good", "youtube", "acct-A"),
        IngestItem("vaccines work and are widely studied", "youtube", "acct-A"),  # same author
        IngestItem("vaccines have saved many lives this year", "youtube", "acct-B"),
    ]
    with get_session() as session:
        service = NarrativeService(session, embedder=_TopicEmbedder())
        service.ingest_batch(items)
        trending = service.list_trending(window_days=30, limit=5)

    assert len(trending) == 1
    n = trending[0]
    assert n.member_count == 3
    assert n.distinct_authors == 2


# ---------------------------------------------------------------------------
# HTTP route
# ---------------------------------------------------------------------------


def test_narratives_endpoint_returns_list():
    set_embedder_for_tests(_TopicEmbedder())
    with get_session() as session:
        NarrativeService(session, embedder=_TopicEmbedder()).ingest_batch([
            IngestItem("vaccines are wildly effective in trials", "youtube", "a"),
            IngestItem("vaccines save lives across populations", "youtube", "b"),
            IngestItem("election integrity matters for democracy", "youtube", "c"),
        ])
    with TestClient(app) as tc:
        r = tc.get("/v1/narratives?window_days=30&limit=5")
        assert r.status_code == 200, r.text
        body = r.json()
        assert "narratives" in body
        assert body["window_days"] == 30
        assert len(body["narratives"]) >= 1
        # Highest-volume narrative first
        first = body["narratives"][0]
        assert first["member_count"] >= 1
        assert isinstance(first["spread_ratio"], (int, float))


# ---------------------------------------------------------------------------
# Embedder fallback
# ---------------------------------------------------------------------------


def test_hashing_embedder_produces_consistent_vectors():
    e = HashingEmbedder(dims=64)
    v1 = e.embed_one("the same comment text")
    v2 = e.embed_one("the same comment text")
    assert v1 == v2
    # Norm ≈ 1.0
    norm = sum(x * x for x in v1) ** 0.5
    assert 0.99 < norm < 1.01


def test_get_embedder_returns_something_in_local_dev():
    set_embedder_for_tests(None)
    e = get_embedder()
    assert isinstance(e.dimensions, int)
    assert e.dimensions > 0


# ---------------------------------------------------------------------------
# Post time, not scan time.
#
# Every temporal statistic over narrative membership used to read the INGEST time, so each member
# of one scan shared a single timestamp and any scan was a perfect burst by construction. The
# detector was measuring our own scanner. These pin the distinction, including the case that makes
# a fallback tempting and wrong: a source that gave us no timestamp.
# ---------------------------------------------------------------------------


def test_the_stored_time_is_when_the_comment_was_posted() -> None:
    from datetime import datetime, timedelta, timezone

    from app.storage.models import NarrativeMembership

    set_embedder_for_tests(_TopicEmbedder())
    base = datetime(2026, 3, 1, 9, 0, tzinfo=timezone.utc)
    posted = [base, base + timedelta(days=1), base + timedelta(days=2)]

    with get_session() as session:
        svc = NarrativeService(session)
        svc.ingest_batch([
            IngestItem(
                text=f"the water treatment plant story number {i}",
                platform="x",
                account_external_id=f"a{i}",
                posted_at=t,
            )
            for i, t in enumerate(posted)
        ])
        session.commit()

    with get_session() as session:
        stored = sorted(
            m.posted_at for m in session.query(NarrativeMembership).all()
        )
    assert len(stored) == 3
    # Three distinct days, exactly as posted. Ingest time would have collapsed these into one
    # instant and reported a burst.
    assert len({t.date() for t in stored}) == 3


def test_a_comment_with_no_post_time_is_stored_as_unknown_not_as_now() -> None:
    from app.storage.models import NarrativeMembership

    set_embedder_for_tests(_TopicEmbedder())
    with get_session() as session:
        NarrativeService(session).ingest_batch([
            IngestItem(
                text="the water treatment plant story, no timestamp available",
                platform="x",
                account_external_id="a1",
            )
        ])
        session.commit()

    with get_session() as session:
        row = session.query(NarrativeMembership).one()
    # NULL, never the ingest time. Substituting `now` is what made a scan look like a burst, and it
    # is indistinguishable afterwards from a comment genuinely posted at that moment.
    assert row.posted_at is None
    # The ingest time is still recorded, in the column that means it.
    assert row.observed_at is not None


def test_a_row_with_no_post_time_is_skipped_by_the_temporal_statistics() -> None:
    from datetime import datetime, timedelta, timezone

    from app.narrative.coordination import MembershipRecord, propagation_timeline

    at = datetime(2026, 3, 1, 14, 0, tzinfo=timezone.utc)
    members = [
        MembershipRecord("a1", "x", "p", at, 1, None),
        MembershipRecord("a2", "x", "p", at + timedelta(minutes=10), 2, None),
        MembershipRecord("a3", "x", "p", None, 3, None),
    ]
    timeline = propagation_timeline(members)
    # Two placed comments, not three. The third has no known post time, and a statistic that
    # substituted the scan time for it would report an arrival that never happened.
    assert sum(p.count for p in timeline) == 2


# ---------------------------------------------------------------------------
# The vector space guard.
#
# Switching embedders does not raise: `cosine` answers 0.0 on a width mismatch, so every utterance
# misses every stored topic and spawns a duplicate. The run reports success and the topic space
# forks in half. These pin the two halves of the guard.
# ---------------------------------------------------------------------------


class _WideEmbedder:
    """A different model in a different space, same shape of interface."""

    dimensions = 6
    space = "api:other-model:6"

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self.embed_one(t) for t in texts]

    def embed_one(self, text: str) -> list[float]:
        vec = [0.0] * 6
        vec[len(text) % 6] = 1.0
        return vec


def test_a_topic_records_the_space_its_centroid_was_built_in() -> None:
    from app.storage.models import Narrative

    set_embedder_for_tests(_TopicEmbedder())
    with get_session() as session:
        NarrativeService(session).ingest_batch([
            IngestItem(text="the water treatment plant story", platform="x",
                       account_external_id="a1")
        ])
        session.commit()

    with get_session() as session:
        assert session.query(Narrative).one().embedding_space == _TopicEmbedder.space


def test_a_different_embedder_does_not_match_against_the_old_centroids() -> None:
    from app.storage.models import Narrative

    set_embedder_for_tests(_TopicEmbedder())
    with get_session() as session:
        NarrativeService(session).ingest_batch([
            IngestItem(text="the water treatment plant story", platform="x",
                       account_external_id="a1")
        ])
        session.commit()

    # Same text, new model. It must start a topic in the new space rather than silently join,
    # or be compared against, a centroid that means nothing to it.
    set_embedder_for_tests(_WideEmbedder())
    with get_session() as session:
        NarrativeService(session).ingest_batch([
            IngestItem(text="the water treatment plant story", platform="x",
                       account_external_id="a2")
        ])
        session.commit()

    with get_session() as session:
        spaces = {n.embedding_space for n in session.query(Narrative).all()}
    # Two topics, one per space. Not one topic holding vectors from both.
    assert spaces == {_TopicEmbedder.space, _WideEmbedder.space}


def test_an_unavailable_embedder_skips_the_batch_instead_of_degrading() -> None:
    from app.narrative.embeddings import EmbeddingUnavailable
    from app.storage.models import Narrative

    class _Down:
        dimensions = 4
        space = "api:down:4"

        def embed(self, texts: list[str]) -> list[list[float]]:
            raise EmbeddingUnavailable("provider unreachable")

        def embed_one(self, text: str) -> list[float]:
            raise EmbeddingUnavailable("provider unreachable")

    set_embedder_for_tests(_Down())
    with get_session() as session:
        assigned = NarrativeService(session).ingest_batch([
            IngestItem(text="the water treatment plant story", platform="x",
                       account_external_id="a1")
        ])
        session.commit()

    # Nothing assigned and nothing written. The text is still on the investigation, so this is
    # recoverable; a topic spawned in the wrong space would not have been.
    assert assigned == 0
    with get_session() as session:
        assert session.query(Narrative).count() == 0
