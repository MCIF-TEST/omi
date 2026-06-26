"""Tiered Institutional Knowledge Architecture tests (Sprint 013).

Covers the deterministic distillation tiers, the background consolidation pipeline (promotion /
demotion / archival, idempotent, evidence-backed revisions), scalable + explainable + tier-aware
retrieval (never a full scan, budgeted, temporal), memory metrics, Postgres parity, replay
determinism, the admin routes, and regression safety.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.evidence import Binder
from app.main import app
from app.memory.consolidation import consolidate
from app.memory.graph import MemoryStore, PostgresMemoryStore, retrieve
from app.memory.metrics import memory_stats
from app.memory.retrieval_engine import retrieve_priors
from app.memory.tiers import ARCHETYPE, ARCHIVED, CANDIDATE, INSTITUTIONAL, VALIDATED, tier_of
from app.storage.db import get_session, reset_db_for_tests

NOW = datetime(2026, 6, 25, tzinfo=timezone.utc)


def _at(days_ago: float) -> str:
    return (NOW - timedelta(days=days_ago)).isoformat()


def _payload() -> dict:
    return {
        "overall_probability": 0.72, "overall_tier": "elevated", "confidence": 0.6,
        "contributions": [{"name": "temporal", "impact": 0.5, "direction": "raises"},
                          {"name": "community", "impact": 0.2, "direction": "lowers"}],
        "video": {"clusters": [{"method": "co_engagement", "members": ["@a", "@b", "@c"]}]},
    }


def _bundle():
    return Binder().bind(_payload(), grain="comment_section", subject_ref="inv1", platform="youtube")


def _ingest(store, *, obs, signature=("temporal",), type_="BehavioralArchetype", is_control=False):
    for stance, key, days_ago in obs:
        store.ingest(candidate={"type": type_, "signature": list(signature), "label": "x", "is_control": is_control},
                     investigation=f"i-{key}", stance=stance, evidence_refs=["d"], independence_key=key, at=_at(days_ago))


def _one(store):
    return store.all(include_superseded=True)[0]


# --- the distillation lifecycle (deterministic tiers) ----------------------- #
def test_tier_of_maps_the_lifecycle():
    s = MemoryStore(); _ingest(s, obs=[("supports", "a", 0)])
    assert tier_of(_one(s), NOW) == CANDIDATE                       # 1 support -> hypothesized
    s = MemoryStore(); _ingest(s, obs=[("supports", "a", 0), ("supports", "b", 0)])
    assert tier_of(_one(s), NOW) == VALIDATED                       # 2 -> observed
    s = MemoryStore(); _ingest(s, obs=[("supports", k, 0) for k in "abc"])
    assert tier_of(_one(s), NOW) == ARCHETYPE                       # 3 stable -> corroborated
    s = MemoryStore(); _ingest(s, obs=[("supports", "a", 40), ("supports", "b", 30),
                                       ("supports", "c", 20), ("supports", "d", 10), ("supports", "e", 0)])
    assert tier_of(_one(s), NOW) == INSTITUTIONAL                   # 5 stable, long-lived
    s = MemoryStore(); _ingest(s, obs=[("supports", "a", 3000)])
    assert tier_of(_one(s), NOW) == ARCHIVED                        # decayed below floor -> retired
    s = MemoryStore(); _ingest(s, obs=[("supports", "a", 0), ("contradicts", "b", 0), ("contradicts", "c", 0)])
    assert tier_of(_one(s), NOW) == CANDIDATE                       # contested falls back to candidate


# --- background consolidation pipeline -------------------------------------- #
def test_consolidation_promotes_records_and_is_idempotent():
    s = MemoryStore(); _ingest(s, obs=[("supports", "a", 0), ("supports", "b", 0)])
    r1 = consolidate(s, now=NOW)
    assert r1.promotions and r1.by_tier.get(VALIDATED) == 1 and not r1.demotions
    assert s.tiers()[_one(s).id] == VALIDATED                       # tier cache refreshed
    assert any("tier:" in v["change"] for v in _one(s).version_history)   # evidence-backed revision
    assert consolidate(s, now=NOW).promotions == []                # idempotent on unchanged store


def test_consolidation_is_deterministic():
    def _run():
        s = MemoryStore(); _ingest(s, obs=[("supports", "a", 0), ("supports", "b", 0)])
        return consolidate(s, now=NOW).to_dict()
    a, b = _run(), _run()
    assert {k: a[k] for k in ("total", "by_tier", "promotions")} == {k: b[k] for k in ("total", "by_tier", "promotions")}


# --- scalable, explainable, tier-aware retrieval ---------------------------- #
def test_candidates_are_not_surfaced_validated_are():
    s = MemoryStore(); _ingest(s, obs=[("supports", "a", 0)])       # candidate
    assert retrieve_priors(s, _bundle(), now=NOW).priors == []
    _ingest(s, obs=[("supports", "b", 0)])                          # -> validated
    res = retrieve_priors(s, _bundle(), now=NOW)
    assert len(res.priors) == 1 and res.priors[0].tier == VALIDATED


def test_retrieval_never_full_scans_and_is_explainable():
    s = MemoryStore()
    _ingest(s, obs=[("supports", "a", 0), ("supports", "b", 0)])    # matching, validated
    for i in range(50):                                            # noise: non-overlapping signatures
        _ingest(s, signature=(f"noise{i}",), obs=[("supports", f"k{i}", 0), ("supports", f"k{i}b", 0)])
    res = retrieve_priors(s, _bundle(), now=NOW)
    assert res.plan.scanned == 1 and res.plan.corpus_total == 51   # narrowed by signature, not scanned
    assert res.plan.scan_fraction < 0.1 and res.plan.basis
    assert res.plan.strategies["signature"] == 1 and "behavioral" in res.plan.strategies


def test_retrieval_budget_and_determinism():
    s = MemoryStore()
    for i in range(4):
        _ingest(s, signature=("temporal", f"d{i}"), obs=[("supports", f"a{i}", 0), ("supports", f"b{i}", 0)])
    r1 = retrieve_priors(s, _bundle(), budget=2, now=NOW)
    r2 = retrieve_priors(s, _bundle(), budget=2, now=NOW)
    assert len(r1.priors) == 2
    assert [(p.ko_id, p.score) for p in r1.priors] == [(p.ko_id, p.score) for p in r2.priors]


def test_temporal_window_filters_stale_priors():
    s = MemoryStore(); _ingest(s, obs=[("supports", "a", 400), ("supports", "b", 400)])   # validated but stale
    assert retrieve_priors(s, _bundle(), now=NOW).priors                      # no window -> present
    assert retrieve_priors(s, _bundle(), now=NOW, temporal_window_days=180).priors == []  # windowed out


# --- metrics ---------------------------------------------------------------- #
def test_memory_stats_reports_tiers_and_distillation():
    s = MemoryStore()
    _ingest(s, signature=("temporal",), obs=[("supports", k, 0) for k in "abc"])         # archetype
    _ingest(s, signature=("other",), obs=[("supports", "x", 0)])                          # candidate
    st = memory_stats(s, now=NOW)
    assert st["knowledge_objects"] == 2 and st["by_tier"].get(ARCHETYPE) == 1
    assert st["retrievable"] == 1 and 0.0 < st["distillation_ratio"] <= 1.0


# --- Postgres parity -------------------------------------------------------- #
def test_postgres_parity_tiers_consolidation_and_counts():
    reset_db_for_tests("sqlite:///:memory:")
    pg = PostgresMemoryStore(get_session)
    _ingest(pg, obs=[("supports", "a", 0), ("supports", "b", 0)])
    consolidate(pg, now=NOW)
    assert pg.tiers()[_one(pg).id] == VALIDATED                    # tier column refreshed
    assert pg.tier_counts().get(VALIDATED) == 1                    # SQL GROUP BY (scalable)
    res = retrieve_priors(pg, _bundle(), now=NOW)
    assert len(res.priors) == 1 and res.priors[0].tier == VALIDATED


# --- regression: existing retrieve still works ------------------------------ #
def test_legacy_retrieve_still_works():
    s = MemoryStore(); _ingest(s, obs=[("supports", "a", 0), ("supports", "b", 0)])
    priors = retrieve(s, _bundle(), now=NOW)                        # the Sprint-005 path, unchanged
    assert priors and priors[0].ko_id


# --- admin routes ----------------------------------------------------------- #
def test_memory_admin_routes():
    reset_db_for_tests("sqlite:///:memory:")
    pg = PostgresMemoryStore(get_session)
    _ingest(pg, obs=[("supports", "a", 0), ("supports", "b", 0)])
    with TestClient(app) as tc:
        consolidated = tc.post("/v1/admin/memory/consolidate").json()
        assert consolidated["report"]["total"] == 1 and consolidated["stats"]["retrievable"] == 1
        stats = tc.get("/v1/admin/memory/stats").json()
        assert stats["knowledge_objects"] == 1 and stats["by_tier"].get(VALIDATED) == 1
