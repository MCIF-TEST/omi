"""Memory persistence tests (Sprint 012).

Covers the production PostgreSQL layer (verified on the hermetic SQLite test DB): migrations +
indexes, repository correctness, append-only guarantees, transaction durability, deterministic
retrieval (equivalent to in-memory), candidate narrowing at scale, typed/contradiction lookups,
replay stability, concurrent writes, performance, and the repository factory.
"""
from __future__ import annotations

import threading
import time
from datetime import datetime, timezone

from sqlalchemy import inspect

from app.evidence import Binder
from app.memory.graph import (
    MemoryStore,
    PostgresMemoryStore,
    rank_priors,
    record_settled_investigation,
    retrieve,
)
from app.memory.repository import MemoryRepository, get_memory_store
from app.storage.db import get_session, reset_db_for_tests

NOW = datetime(2026, 6, 25, tzinfo=timezone.utc)


def _payload() -> dict:
    return {
        "overall_probability": 0.72, "overall_tier": "elevated", "confidence": 0.6,
        "contributions": [{"name": "temporal", "impact": 0.5, "direction": "raises"},
                          {"name": "community", "impact": 0.2, "direction": "lowers"}],
        "video": {"clusters": [{"method": "co_engagement", "members": ["@a", "@b", "@c"]}]},
    }


def _bundle():
    return Binder().bind(_payload(), grain="comment_section", subject_ref="inv1", platform="youtube")


def _store() -> PostgresMemoryStore:
    return PostgresMemoryStore(get_session)


def _cand(type_="BehavioralArchetype", signature=("temporal",), label="x", **kw):
    return {"type": type_, "signature": list(signature), "label": label, **kw}


# --- migrations + indexes --------------------------------------------------- #
def test_migration_creates_memory_tables_and_indexes():
    with get_session() as s:
        insp = inspect(s.bind)
        tables = set(insp.get_table_names())
        assert {"knowledge_objects", "observation_ledger", "memory_revisions",
                "knowledge_object_signatures", "prior_context_cache"} <= tables
        idx = {i["name"] for i in insp.get_indexes("knowledge_object_signatures")}
        assert "ix_kosig_token" in idx


# --- repository correctness + append-only ----------------------------------- #
def test_ingest_creates_object_and_observation():
    store = _store()
    ko = store.ingest(candidate=_cand(label="burst"), investigation="h1", stance="supports",
                      evidence_refs=["d1"], independence_key="a", at=NOW.isoformat())
    assert len(store) == 1 and ko.type == "BehavioralArchetype" and len(ko.ledger) == 1
    assert store.get(ko.id).label == "burst"


def test_append_only_accumulation_is_durable_across_sessions():
    store = _store()
    for k in ("a", "b"):
        store.ingest(candidate=_cand(), investigation=f"inv-{k}", stance="supports",
                     evidence_refs=["d"], independence_key=k, at=NOW.isoformat())
    assert len(store) == 1                                   # matched, not duplicated
    fresh = _store()                                         # a new store = new sessions
    ko = fresh.all()[0]
    assert len(ko.ledger) == 2 and ko.independent_support_count() == 2


def test_supersede_keeps_the_row_append_only():
    store = _store()
    ko = store.ingest(candidate=_cand(label="old"), investigation="h1", stance="supports",
                      evidence_refs=["d"], independence_key="a", at=NOW.isoformat())
    store.supersede(ko.id, "ko:new")
    assert all(o.id != ko.id for o in store.all())           # excluded from active set
    assert any(o.id == ko.id for o in store.all(include_superseded=True))   # row kept, not deleted
    assert store.get(ko.id).superseded_by == "ko:new"


# --- deterministic retrieval + narrowing ------------------------------------ #
def test_retrieval_matches_in_memory_exactly():
    def _run(store):
        record_settled_investigation(store, _bundle(), investigation="h1", independence_key="a",
                                     at=NOW.isoformat(), is_control=True)
        record_settled_investigation(store, _bundle(), investigation="h2", independence_key="b", at=NOW.isoformat())
        return [(p.ko_id, p.type, p.is_control, p.score) for p in retrieve(store, _bundle(), now=NOW)]
    assert _run(MemoryStore()) == _run(_store())             # backend-agnostic, identical


def test_candidates_for_narrows_yet_ranks_identically():
    store = _store()
    record_settled_investigation(store, _bundle(), investigation="h1", independence_key="a",
                                 at=NOW.isoformat(), is_control=True)
    store.ingest(candidate=_cand(signature=["unrelated_detector"], label="noise"),
                 investigation="h2", stance="supports", evidence_refs=["d"], independence_key="z", at=NOW.isoformat())
    cands = store.candidates_for(_bundle())
    assert cands and not any(c.label == "noise" for c in cands)    # unrelated object narrowed out
    via_candidates = retrieve(store, _bundle(), now=NOW)
    via_all = rank_priors(store.all(), _bundle(), now=NOW)
    assert [p.ko_id for p in via_candidates] == [p.ko_id for p in via_all]   # narrowing is correct


def test_typed_and_contradiction_and_control_lookups():
    store = _store()
    record_settled_investigation(store, _bundle(), investigation="h1", independence_key="a", at=NOW.isoformat())
    record_settled_investigation(store, _bundle(), investigation="h2", independence_key="b",
                                 at=NOW.isoformat(), stance="contradicts")
    assert store.find_by_type("BehavioralArchetype")
    assert store.find_contradicted()                         # has a contradicting observation
    store.ingest(candidate=_cand("LegitimateCoordinationControl", ["co_engagement"], "ctrl", is_control=True),
                 investigation="h3", stance="supports", evidence_refs=["d"], independence_key="c", at=NOW.isoformat())
    assert store.find_controls() and store.find_controls()[0].is_control


def test_retrieval_is_replay_stable():
    store = _store()
    record_settled_investigation(store, _bundle(), investigation="h1", independence_key="a",
                                 at=NOW.isoformat(), is_control=True)
    r1 = [(p.ko_id, p.score) for p in retrieve(store, _bundle(), now=NOW)]
    r2 = [(p.ko_id, p.score) for p in retrieve(store, _bundle(), now=NOW)]
    assert r1 == r2 and r1


# --- factory (abstraction) -------------------------------------------------- #
def test_factory_selects_backend_and_satisfies_interface():
    class _Off:
        memory_persistence_enabled = False
        memory_database_url = None
    class _On:
        memory_persistence_enabled = True
        memory_database_url = None
    assert isinstance(get_memory_store(_Off()), MemoryStore)
    pg = get_memory_store(_On())
    assert isinstance(pg, PostgresMemoryStore)
    assert isinstance(pg, MemoryRepository) and isinstance(MemoryStore(), MemoryRepository)


# --- concurrency + performance ---------------------------------------------- #
def test_concurrent_appends_are_lossless(tmp_path):
    reset_db_for_tests(f"sqlite:///{tmp_path}/mem.db")       # file-backed (WAL) for real concurrency
    try:
        seed = _store()
        seed.ingest(candidate=_cand(), investigation="seed", stance="supports",
                    evidence_refs=["d"], independence_key="seed", at=NOW.isoformat())

        def worker(i: int) -> None:
            _store().ingest(candidate=_cand(), investigation=f"t{i}", stance="supports",
                            evidence_refs=["d"], independence_key=f"k{i}", at=NOW.isoformat())
        threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        fresh = _store()
        assert len(fresh) == 1                               # all matched the seed (no duplicates)
        assert len(fresh.all()[0].ledger) == 9               # seed + 8, none lost (append-only)
    finally:
        reset_db_for_tests("sqlite:///:memory:")


def test_retrieval_performance_with_candidate_narrowing():
    store = _store()
    for i in range(100):
        store.ingest(candidate=_cand(signature=[f"sig{i}"], label=f"a{i}"), investigation=f"inv{i}",
                     stance="supports", evidence_refs=["d"], independence_key=f"k{i}", at=NOW.isoformat())
    record_settled_investigation(store, _bundle(), investigation="match", independence_key="m",
                                 at=NOW.isoformat(), is_control=True)
    t0 = time.perf_counter()
    priors = retrieve(store, _bundle(), now=NOW)
    elapsed = time.perf_counter() - t0
    assert priors and elapsed < 1.0
    assert len(store.candidates_for(_bundle())) < len(store.all())   # index narrowing avoids full scan
