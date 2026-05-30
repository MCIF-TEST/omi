"""Tests for the graph + coordination intelligence layer (Phase 4)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.graph.algorithms import detect_communities, edge_strength
from app.graph.service import GraphService
from app.graph.store import EdgeRecord, GraphStore
from app.main import app
from app.storage.db import get_session, reset_db_for_tests
from app.storage.models import Account


@pytest.fixture(autouse=True)
def _fresh_db():
    reset_db_for_tests()
    yield


def _make_account(platform="youtube", external_id="UC123", handle="@x", tier="moderate", score=0.5):
    with get_session() as session:
        a = Account(
            platform=platform, external_id=external_id, handle=handle,
            last_tier=tier, last_score=score,
        )
        session.add(a)
    return external_id


# ---------------------------------------------------------------------------
# Store: idempotency + symmetry
# ---------------------------------------------------------------------------


def test_upsert_observation_creates_then_updates():
    with get_session() as session:
        store = GraphStore(session)
        e1 = store.upsert_observation(
            platform="youtube", a="A", b="B",
            method="temporal_semantic_clique", cluster_score=0.7, parent_id="VID",
        )
        assert e1 is not None
        assert e1.observation_count == 1
        assert e1.methods == ["temporal_semantic_clique"]

        e2 = store.upsert_observation(
            platform="youtube", a="A", b="B",
            method="fingerprint_cluster", cluster_score=0.9,
        )
        assert e2 is not None
        assert e2.observation_count == 2
        # Methods dedup + append
        assert sorted(e2.methods) == ["fingerprint_cluster", "temporal_semantic_clique"]
        # Running average: (0.7 + 0.9) / 2 = 0.8
        assert abs(e2.mean_cluster_score - 0.8) < 1e-6


def test_edges_are_symmetric():
    with get_session() as session:
        store = GraphStore(session)
        store.upsert_observation(platform="youtube", a="zeta", b="alpha",
                                 method="co_engagement", cluster_score=0.5)
        # Looking up via either direction returns the same edge
        e1 = store.get_edge("youtube", "alpha", "zeta")
        e2 = store.get_edge("youtube", "zeta", "alpha")
        assert e1 is not None and e2 is not None
        assert (e1.account_a, e1.account_b) == ("alpha", "zeta")
        assert (e2.account_a, e2.account_b) == ("alpha", "zeta")


def test_upsert_cluster_creates_pair_edges():
    with get_session() as session:
        store = GraphStore(session)
        n = store.upsert_cluster(
            platform="youtube",
            members=["A", "B", "C", "D"],
            method="style_match",
            cluster_score=0.65,
            parent_id="VID1",
        )
        # 4 accounts → C(4,2) = 6 edges
        assert n == 6
        edges = store.all_edges("youtube")
        assert len(edges) == 6


def test_upsert_same_member_pair_is_noop():
    with get_session() as session:
        store = GraphStore(session)
        e = store.upsert_observation(platform="youtube", a="X", b="X",
                                     method="co_engagement", cluster_score=0.5)
        assert e is None


def test_neighbors_returns_incident_edges():
    with get_session() as session:
        store = GraphStore(session)
        store.upsert_cluster(platform="youtube",
                             members=["A", "B", "C"], method="age_cohort", cluster_score=0.4)
        n = store.neighbors("youtube", "A")
        assert len(n) == 2
        assert {sorted([e.account_a, e.account_b])[0] for e in n} == {"A"}


# ---------------------------------------------------------------------------
# Strength formula
# ---------------------------------------------------------------------------


def test_edge_strength_in_range():
    e = EdgeRecord(
        platform="youtube", account_a="A", account_b="B",
        observation_count=1, methods=["co_engagement"],
        mean_cluster_score=0.4, last_shared_parent=None,
        first_observed_at=datetime.now(timezone.utc),
        last_observed_at=datetime.now(timezone.utc),
    )
    s = edge_strength(e)
    assert 0.0 <= s <= 1.0


def test_strength_grows_with_diversity_and_recency():
    now = datetime.now(timezone.utc)
    weak = EdgeRecord(
        platform="youtube", account_a="A", account_b="B",
        observation_count=1, methods=["co_engagement"],
        mean_cluster_score=0.4, last_shared_parent=None,
        first_observed_at=now - timedelta(days=80),
        last_observed_at=now - timedelta(days=80),
    )
    strong = EdgeRecord(
        platform="youtube", account_a="A", account_b="B",
        observation_count=8,
        methods=["co_engagement", "temporal_semantic_clique",
                 "fingerprint_cluster", "style_match", "age_cohort"],
        mean_cluster_score=0.85, last_shared_parent=None,
        first_observed_at=now,
        last_observed_at=now,
    )
    assert edge_strength(strong, now=now) > edge_strength(weak, now=now)


# ---------------------------------------------------------------------------
# Community detection
# ---------------------------------------------------------------------------


def test_detect_communities_finds_clear_clusters():
    with get_session() as session:
        store = GraphStore(session)
        # Cluster 1: A-B-C tightly connected
        store.upsert_cluster(platform="youtube", members=["A", "B", "C"],
                             method="temporal_semantic_clique", cluster_score=0.8)
        store.upsert_cluster(platform="youtube", members=["A", "B", "C"],
                             method="fingerprint_cluster", cluster_score=0.85)
        # Cluster 2: X-Y-Z separately
        store.upsert_cluster(platform="youtube", members=["X", "Y", "Z"],
                             method="style_match", cluster_score=0.7)
        store.upsert_cluster(platform="youtube", members=["X", "Y", "Z"],
                             method="co_engagement", cluster_score=0.65)

        edges = store.all_edges("youtube")
        comms = detect_communities(edges, min_size=3)
        assert len(comms) == 2
        # Both communities sized 3
        assert {c.size for c in comms} == {3}
        # Each community is internally consistent — A-B-C together
        for c in comms:
            assert set(c.members) in ({"A", "B", "C"}, {"X", "Y", "Z"})


# ---------------------------------------------------------------------------
# Service-level subgraph
# ---------------------------------------------------------------------------


def test_account_subgraph_includes_two_hop_neighbors():
    with get_session() as session:
        store = GraphStore(session)
        store.upsert_cluster(platform="youtube", members=["FOCAL", "B"],
                             method="co_engagement", cluster_score=0.5)
        store.upsert_cluster(platform="youtube", members=["B", "C"],
                             method="co_engagement", cluster_score=0.5)
        store.upsert_cluster(platform="youtube", members=["C", "D"],
                             method="co_engagement", cluster_score=0.5)
        svc = GraphService(session)
        sg = svc.account_subgraph(platform="youtube", external_id="FOCAL", depth=2)
        ids = {n.external_id for n in sg.nodes}
        # Depth 2 from FOCAL: B (1-hop), C (2-hop). Not D.
        assert "FOCAL" in ids
        assert "B" in ids
        assert "C" in ids
        assert "D" not in ids


# ---------------------------------------------------------------------------
# HTTP routes — user-curated named graphs (/v1/graphs)
# ---------------------------------------------------------------------------


def test_list_graphs_initially_empty():
    with TestClient(app) as tc:
        r = tc.get("/v1/graphs")
        assert r.status_code == 200
        assert r.json() == []


def test_create_and_list_graph():
    with TestClient(app) as tc:
        r = tc.post("/v1/graphs", json={"name": "Test Graph", "platform": "youtube"})
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["name"] == "Test Graph"
        assert body["platform"] == "youtube"
        assert body["member_count"] == 0
        gid = body["id"]

        r2 = tc.get("/v1/graphs")
        assert r2.status_code == 200
        graphs = r2.json()
        assert len(graphs) == 1
        assert graphs[0]["id"] == gid


def test_duplicate_graph_name_returns_409():
    with TestClient(app) as tc:
        tc.post("/v1/graphs", json={"name": "dupe", "platform": "youtube"})
        r = tc.post("/v1/graphs", json={"name": "dupe", "platform": "youtube"})
        assert r.status_code == 409


def test_rename_graph():
    with TestClient(app) as tc:
        r = tc.post("/v1/graphs", json={"name": "old name"})
        gid = r.json()["id"]

        r2 = tc.patch(f"/v1/graphs/{gid}", json={"name": "new name"})
        assert r2.status_code == 200
        assert r2.json()["name"] == "new name"


def test_delete_graph():
    with TestClient(app) as tc:
        r = tc.post("/v1/graphs", json={"name": "to delete"})
        gid = r.json()["id"]

        r2 = tc.delete(f"/v1/graphs/{gid}")
        assert r2.status_code == 204

        r3 = tc.get("/v1/graphs")
        assert r3.json() == []


def test_add_and_remove_member():
    with TestClient(app) as tc:
        gid = tc.post("/v1/graphs", json={"name": "g1"}).json()["id"]

        r = tc.post(
            f"/v1/graphs/{gid}/members",
            json={"external_id": "UCaaa", "handle": "@chan", "tier": "elevated"},
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["external_id"] == "UCaaa"
        assert body["tier"] == "elevated"

        detail = tc.get(f"/v1/graphs/{gid}").json()
        assert len(detail["members"]) == 1

        r2 = tc.delete(f"/v1/graphs/{gid}/members/UCaaa")
        assert r2.status_code == 204

        detail2 = tc.get(f"/v1/graphs/{gid}").json()
        assert len(detail2["members"]) == 0


def test_add_member_idempotent():
    """Adding the same external_id twice returns the existing member (201 first, then same data)."""
    with TestClient(app) as tc:
        gid = tc.post("/v1/graphs", json={"name": "g2"}).json()["id"]
        payload = {"external_id": "UCbbb", "handle": "@dup"}
        r1 = tc.post(f"/v1/graphs/{gid}/members", json=payload)
        r2 = tc.post(f"/v1/graphs/{gid}/members", json=payload)
        assert r1.status_code == 201
        assert r2.json()["external_id"] == "UCbbb"

        detail = tc.get(f"/v1/graphs/{gid}").json()
        assert len(detail["members"]) == 1


def test_graph_detail_includes_coordination_edges_between_members():
    """When two members share a coordination edge, the graph detail returns it."""
    with get_session() as session:
        store = GraphStore(session)
        store.upsert_observation(
            platform="youtube", a="UCmem1", b="UCmem2",
            method="co_engagement", cluster_score=0.8,
        )
    with TestClient(app) as tc:
        gid = tc.post("/v1/graphs", json={"name": "coord-test", "platform": "youtube"}).json()["id"]
        tc.post(f"/v1/graphs/{gid}/members", json={"external_id": "UCmem1", "handle": "mem1"})
        tc.post(f"/v1/graphs/{gid}/members", json={"external_id": "UCmem2", "handle": "mem2"})
        detail = tc.get(f"/v1/graphs/{gid}").json()
        assert len(detail["edges"]) == 1
        edge = detail["edges"][0]
        assert {edge["a"], edge["b"]} == {"UCmem1", "UCmem2"}
        assert 0.0 <= edge["strength"] <= 1.0
