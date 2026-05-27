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
