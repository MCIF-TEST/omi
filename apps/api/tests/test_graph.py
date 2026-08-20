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
        # An edge now carries the REASON it exists, not one opaque float. `strength` was a per-scan
        # mean cluster score, which is not a probability of anything; a line drawn between two named
        # people has to be readable or it is asking to be trusted rather than checked.
        assert "strength" not in edge
        assert 0.0 <= edge["posterior"] <= 1.0
        for field in ("families", "contexts", "methods", "first_seen", "last_seen"):
            assert field in edge, field
        assert "co_engagement" in edge["methods"]


# ==================================================================================================
# The redesigned graph: explainable edges, real communities, and who is missing
# ==================================================================================================
# What was wrong, and what each test here holds:
#
#   * every edge collapsed to one float (`mean_cluster_score`) while the row already carried the
#     accumulated likelihood ratio, the evidence families and the distinct posts;
#   * the client hardcoded `community_id: 0` for every node, so the whole community dimension of the
#     visualisation was dead, while `_louvain` sat unwired in app/graph/algorithms.py;
#   * the client rebuilt a score from the tier band (high -> 0.9) and sized nodes by it, which is an
#     invented figure on a product whose claim is that it does not invent figures;
#   * edges only ever ran between accounts the user had already added, so a graph could only show
#     back what its owner already knew.
def _mk_graph(tc, name: str, platform: str = "youtube") -> int:
    return tc.post("/v1/graphs", json={"name": name, "platform": platform}).json()["id"]


def _seed_edge(a: str, b: str, *, log_lr: float, families: list[str],
               contexts: list[str], platform: str = "youtube") -> None:
    """Write a coordination edge with real accumulated evidence on it."""
    from app.storage.models import CoordinationEdge

    with get_session() as session:
        session.add(CoordinationEdge(
            platform=platform, account_a=a, account_b=b,
            observation_count=len(contexts), methods_json=["verbatim_echo"],
            mean_cluster_score=0.5, log_lr_sum=log_lr,
            families_json=families, contexts_json=contexts, platforms_json=[platform],
        ))
        session.commit()


class TestAnEdgeCarriesItsReasoning:
    def test_the_posterior_comes_from_accumulated_evidence_not_a_cluster_mean(self):
        """`mean_cluster_score` is a per-scan average, not a probability. The posterior is the same
        number the detector uses to decide a pair is coordinated, so the graph and the detector now
        agree by construction."""
        _seed_edge("UCp1", "UCp2", log_lr=3.0, families=["text", "timing"], contexts=["v1", "v2"])
        with TestClient(app) as tc:
            gid = _mk_graph(tc, "posterior-test")
            tc.post(f"/v1/graphs/{gid}/members", json={"external_id": "UCp1"})
            tc.post(f"/v1/graphs/{gid}/members", json={"external_id": "UCp2"})
            edge = tc.get(f"/v1/graphs/{gid}").json()["edges"][0]
        # mean_cluster_score was 0.5; a log10 LR of 3.0 against the stated prior is far above it.
        assert edge["posterior"] > 0.9
        assert edge["families"] == ["text", "timing"]
        assert edge["contexts"] == 2

    def test_an_edge_from_before_the_accumulation_layer_still_renders(self):
        """log_lr_sum 0 means "seen, but before we were measuring", not "no evidence". Collapsing
        such an edge to the prior would silently blank every graph built before that layer."""
        _seed_edge("UCold1", "UCold2", log_lr=0.0, families=[], contexts=[])
        with get_session() as session:
            from app.storage.models import CoordinationEdge
            from sqlalchemy import select as sel
            row = session.execute(sel(CoordinationEdge).where(
                CoordinationEdge.account_a == "UCold1")).scalar_one()
            row.mean_cluster_score = 0.62
            session.commit()
        with TestClient(app) as tc:
            gid = _mk_graph(tc, "legacy-edge")
            tc.post(f"/v1/graphs/{gid}/members", json={"external_id": "UCold1"})
            tc.post(f"/v1/graphs/{gid}/members", json={"external_id": "UCold2"})
            edge = tc.get(f"/v1/graphs/{gid}").json()["edges"][0]
        assert edge["posterior"] == pytest.approx(0.62, abs=1e-3)


class TestCommunitiesAreDetectedNotHardcoded:
    def test_unconnected_members_are_community_zero(self):
        """The honest and by far most common state for a curated graph. It must be visually
        distinct rather than dressed up as a cluster of one."""
        with TestClient(app) as tc:
            gid = _mk_graph(tc, "no-edges")
            for ext in ("UCa", "UCb", "UCc"):
                tc.post(f"/v1/graphs/{gid}/members", json={"external_id": ext})
            d = tc.get(f"/v1/graphs/{gid}").json()
        assert all(m["community_id"] == 0 for m in d["members"])
        assert all(m["degree"] == 0 for m in d["members"])
        assert d["community_count"] == 0

    def test_two_separate_clusters_get_different_ids(self):
        """The reason this dimension exists: one saved graph can hold two unrelated operations."""
        _seed_edge("UCx1", "UCx2", log_lr=3.0, families=["text"], contexts=["v1"])
        _seed_edge("UCy1", "UCy2", log_lr=3.0, families=["text"], contexts=["v2"])
        with TestClient(app) as tc:
            gid = _mk_graph(tc, "two-clusters")
            for ext in ("UCx1", "UCx2", "UCy1", "UCy2"):
                tc.post(f"/v1/graphs/{gid}/members", json={"external_id": ext})
            d = tc.get(f"/v1/graphs/{gid}").json()
        by_id = {m["external_id"]: m["community_id"] for m in d["members"]}
        assert by_id["UCx1"] == by_id["UCx2"] != 0
        assert by_id["UCy1"] == by_id["UCy2"] != 0
        assert by_id["UCx1"] != by_id["UCy1"]
        assert all(m["degree"] == 1 for m in d["members"])


class TestSuggestions:
    def test_an_account_linked_into_the_graph_is_suggested(self):
        """The most useful thing a coordination graph can do, and the old endpoint could not do it
        at all: it only ever drew edges between accounts already added."""
        _seed_edge("UCin1", "UCout", log_lr=3.0, families=["text", "timing"], contexts=["v1", "v2"])
        with TestClient(app) as tc:
            gid = _mk_graph(tc, "suggest-1")
            tc.post(f"/v1/graphs/{gid}/members", json={"external_id": "UCin1"})
            d = tc.get(f"/v1/graphs/{gid}").json()
        assert [s["external_id"] for s in d["suggestions"]] == ["UCout"]
        s = d["suggestions"][0]
        assert s["linked_to"] == "UCin1" and s["links_into_graph"] == 1
        assert s["families"] == ["text", "timing"]

    def test_an_account_tied_to_several_members_ranks_first(self):
        """One strong edge can be a coincidence with a good story. An account tied to two separate
        members of a curated set is the shape of an operation, so that ordering is the point."""
        # 2.5 and not 2.0: a log10 LR of 2.0 lands at posterior 0.773, just under the suggestion
        # bar, which is the gate working rather than a bug. Both links must clear it for the
        # multi-link ranking to be the thing under test.
        _seed_edge("UCm1", "UCmany", log_lr=2.5, families=["text"], contexts=["v1"])
        _seed_edge("UCm2", "UCmany", log_lr=2.5, families=["timing"], contexts=["v2"])
        _seed_edge("UCm1", "UCsingle", log_lr=6.0, families=["text"], contexts=["v3"])
        with TestClient(app) as tc:
            gid = _mk_graph(tc, "suggest-rank")
            tc.post(f"/v1/graphs/{gid}/members", json={"external_id": "UCm1"})
            tc.post(f"/v1/graphs/{gid}/members", json={"external_id": "UCm2"})
            d = tc.get(f"/v1/graphs/{gid}").json()
        names = [s["external_id"] for s in d["suggestions"]]
        assert names[0] == "UCmany", f"multi-link account must rank first, got {names}"
        assert d["suggestions"][0]["links_into_graph"] == 2
        # And it accumulates the families across both of its links into the graph.
        assert d["suggestions"][0]["families"] == ["text", "timing"]

    def test_a_weak_link_is_not_suggested(self):
        """Offering a lead the evidence does not support trains the operator to add accounts on our
        say-so. A suggestion has to clear the same bar the detector uses."""
        _seed_edge("UCw1", "UCweak", log_lr=0.2, families=["text"], contexts=["v1"])
        with TestClient(app) as tc:
            gid = _mk_graph(tc, "suggest-weak")
            tc.post(f"/v1/graphs/{gid}/members", json={"external_id": "UCw1"})
            d = tc.get(f"/v1/graphs/{gid}").json()
        assert d["suggestions"] == []

    def test_an_existing_member_is_never_suggested(self):
        _seed_edge("UCboth1", "UCboth2", log_lr=3.0, families=["text"], contexts=["v1"])
        with TestClient(app) as tc:
            gid = _mk_graph(tc, "suggest-member")
            tc.post(f"/v1/graphs/{gid}/members", json={"external_id": "UCboth1"})
            tc.post(f"/v1/graphs/{gid}/members", json={"external_id": "UCboth2"})
            d = tc.get(f"/v1/graphs/{gid}").json()
        assert d["suggestions"] == []
        assert len(d["edges"]) == 1


class TestTheScoreIsCarriedNotInvented:
    def test_the_real_score_round_trips(self):
        """The UI used to rebuild a number from the tier band and size every node by it. A tier is a
        band and a band cannot be un-rounded: 50 and 74 are both elevated and are not the same."""
        with TestClient(app) as tc:
            gid = _mk_graph(tc, "score-test")
            tc.post(f"/v1/graphs/{gid}/members",
                    json={"external_id": "UCs1", "tier": "elevated", "omi_score": 63})
            m = tc.get(f"/v1/graphs/{gid}").json()["members"][0]
        assert m["omi_score"] == 63 and m["tier"] == "elevated"

    def test_a_member_added_without_a_score_reports_null_not_zero(self):
        """Null means not captured. Zero would say this account looks like a real person, which is a
        different claim and one nobody made."""
        with TestClient(app) as tc:
            gid = _mk_graph(tc, "score-null")
            tc.post(f"/v1/graphs/{gid}/members", json={"external_id": "UCs2", "tier": "low"})
            m = tc.get(f"/v1/graphs/{gid}").json()["members"][0]
        assert m["omi_score"] is None
