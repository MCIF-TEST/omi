"""Operational intelligence — the live institutional learning loop (Sprint 014).

Covers the deterministic operational seams added on top of the tiered memory architecture:

  * memory compression (merge equivalent duplicates → denser, provenance preserved, idempotent),
  * retrieval feedback (``useful`` semantics, aggregation, reuse counting on both stores),
  * the Governor-gated learning write (a rejected ruling teaches memory nothing),
  * retrieval optimization — the learned usefulness bonus (RANKING ONLY), provenance + type filters,
  * adaptive memory quality (measurement only — never alters a memory or a score),
  * the institutional-knowledge dashboard + retrieval precision,
  * Postgres parity, replay determinism, the admin routes, and regression safety.

The constitutional invariants under test: feedback/quality/compression are MEASUREMENTS — they
change retrieval *ranking* and memory *density*, never an investigation's score, a memory's
confidence, the Governor, or OmiScore.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.evidence import Binder
from app.main import app
from app.memory.compression import compress, compression_potential
from app.memory.feedback import RetrievalFeedback, aggregate_feedback, usefulness_map
from app.memory.graph import MemoryStore, PostgresMemoryStore, retrieve
from app.memory.graph.objects import ObservationLedgerEntry
from app.memory.graph.retrieval import rank_priors
from app.memory.learning import (
    learn_from_investigation,
    record_retrieval_feedback,
    retrieve_with_feedback,
)
from app.memory.metrics import dashboard
from app.memory.quality_signals import quality_of, quality_rankings
from app.memory.retrieval_engine import retrieve_priors
from app.memory.tiers import VALIDATED
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


def _obj(store, *, signature, keys, type_="BehavioralArchetype", is_control=False, days_ago=0):
    """Ingest one KnowledgeObject observed by ``keys`` independent investigations (validated when
    ``len(keys) >= 2``). Returns the affected object id."""
    ko = None
    for k in keys:
        ko = store.ingest(
            candidate={"type": type_, "signature": list(signature), "label": "+".join(signature),
                       "is_control": is_control},
            investigation=f"i-{k}", stance="supports", evidence_refs=["d"],
            independence_key=k, at=_at(days_ago),
        )
    return ko.id


# --------------------------------------------------------------------------- #
# Memory compression — denser, not larger; provenance preserved; deterministic
# --------------------------------------------------------------------------- #
def _two_duplicates(store) -> tuple[str, str]:
    """Two ACTIVE objects with identical (type, signature, control) — a compression group."""
    a = store.create(type="BehavioralArchetype", family="patterns_signatures", label="x", signature=["temporal"])
    b = store.create(type="BehavioralArchetype", family="patterns_signatures", label="x", signature=["temporal"])
    store.observe(a.id, ObservationLedgerEntry(investigation="i-a", stance="supports", evidence_refs=["d"],
                                               independence_key="a", at=_at(0)))
    store.observe(a.id, ObservationLedgerEntry(investigation="i-b", stance="supports", evidence_refs=["d"],
                                               independence_key="b", at=_at(0)))
    store.observe(b.id, ObservationLedgerEntry(investigation="i-c", stance="supports", evidence_refs=["d"],
                                               independence_key="c", at=_at(0)))
    return a.id, b.id


def test_compression_merges_duplicates_denser_not_larger():
    s = MemoryStore()
    a, b = _two_duplicates(s)
    assert len(s.all()) == 2
    pot = compression_potential(s)
    assert pot["mergeable_objects"] == 1 and pot["duplicate_groups"] == 1

    rep = compress(s, now=NOW)
    assert rep.active_before == 2 and rep.active_after == 1 and rep.compression_ratio == 0.5
    assert rep.duplicates_merged == 1 and rep.observations_merged == 1
    # provenance preserved: the canonical now holds ALL three observations, none lost.
    canon = s.get(a)
    assert len(canon.ledger) == 3 and {e.independence_key for e in canon.ledger} == {"a", "b", "c"}
    # the duplicate is superseded (kept for audit), not deleted.
    assert s.get(b).superseded_by == a and len(s.all()) == 1
    assert s.get(b) is not None                                    # never hard-deleted


def test_compression_is_idempotent_and_deterministic():
    def _run():
        s = MemoryStore(); _two_duplicates(s)
        r = compress(s, now=NOW)
        return r.to_dict()
    a, b = _run(), _run()
    assert a["merges"] == b["merges"] and a["compression_ratio"] == b["compression_ratio"]
    # second pass on an already-compressed store merges nothing.
    s = MemoryStore(); _two_duplicates(s)
    compress(s, now=NOW)
    assert compress(s, now=NOW).duplicates_merged == 0


def test_compression_preserves_confidence_independence():
    """Merging re-parents observations; the canonical's recomputed confidence reflects the union of
    independent supports — denser evidence, not a changed verdict."""
    s = MemoryStore()
    a, b = _two_duplicates(s)
    before = s.get(a).independent_support_count()                  # 2 (a, b)
    compress(s, now=NOW)
    assert s.get(a).independent_support_count() == 3              # + c, recomputed from the ledger


# --------------------------------------------------------------------------- #
# Retrieval feedback — useful semantics, aggregation, reuse counting
# --------------------------------------------------------------------------- #
def test_feedback_useful_requires_all_three():
    assert RetrievalFeedback("ko:1", "i1", influenced=True, governor_accepted=True, analyst_agreed=True).useful
    assert not RetrievalFeedback("ko:1", "i1", influenced=True, governor_accepted=True).useful
    assert not RetrievalFeedback("ko:1", "i1", governor_accepted=True, analyst_agreed=True).useful


def test_aggregate_and_usefulness_map():
    rows = [
        RetrievalFeedback("ko:1", "i1", influenced=True, governor_accepted=True, analyst_agreed=True, at=_at(2)),
        RetrievalFeedback("ko:1", "i2", influenced=True, governor_accepted=False, analyst_agreed=True, at=_at(1)),
        RetrievalFeedback("ko:2", "i3", influenced=False, governor_accepted=False, analyst_agreed=False, at=_at(0)),
    ]
    agg = aggregate_feedback(rows)
    assert agg["ko:1"]["reuse_count"] == 2 and agg["ko:1"]["useful"] == 1 and agg["ko:1"]["usefulness"] == 0.5
    assert agg["ko:1"]["last_validated"] == _at(2)                 # only the useful one stamps last_validated
    assert agg["ko:2"]["usefulness"] == 0.0
    assert usefulness_map(rows) == {"ko:1": 0.5, "ko:2": 0.0}


def test_record_feedback_increments_reuse_count():
    s = MemoryStore()
    kid = _obj(s, signature=["temporal"], keys=["a", "b"])
    s.record_feedback(RetrievalFeedback(kid, "i1", influenced=True, governor_accepted=True, analyst_agreed=True, at=_at(0)))
    s.record_feedback(RetrievalFeedback(kid, "i2", influenced=True, governor_accepted=True, analyst_agreed=True, at=_at(0)))
    assert s.get(kid).reuse_count == 2
    assert len(s.feedback(ko_id=kid)) == 2 and len(s.feedback()) == 2


# --------------------------------------------------------------------------- #
# Governor-gated learning — a rejected ruling teaches memory nothing
# --------------------------------------------------------------------------- #
def test_learning_is_governor_gated():
    s = MemoryStore()
    assert learn_from_investigation(s, _bundle(), permitted=False, investigation="i1",
                                    independence_key="k1", at=_at(0)) == []
    assert len(s) == 0                                             # REJECT writes nothing
    written = learn_from_investigation(s, _bundle(), permitted=True, investigation="i1",
                                       independence_key="k1", at=_at(0))
    assert written and len(s) == len(written)                     # PERMIT writes the candidates


def test_record_retrieval_feedback_marks_useful_only_when_permitted_and_agreed():
    s = MemoryStore()
    _obj(s, signature=["temporal"], keys=["a", "b"])
    priors = retrieve_priors(s, _bundle(), now=NOW).priors
    assert priors
    fbs = record_retrieval_feedback(s, priors, investigation="i9", permitted=True,
                                    analyst_agreed=True, at=_at(0))
    assert fbs and all(f.useful for f in fbs)                      # influenced+permitted+agreed
    # a rejected ruling records feedback but it is NOT useful (cannot lift ranking).
    fbs2 = record_retrieval_feedback(s, priors, investigation="i10", permitted=False,
                                     analyst_agreed=True, at=_at(0))
    assert fbs2 and not any(f.useful for f in fbs2)


# --------------------------------------------------------------------------- #
# Retrieval optimization — usefulness bonus is RANKING ONLY
# --------------------------------------------------------------------------- #
def test_usefulness_bonus_reorders_ranking_only():
    s = MemoryStore()
    k1 = _obj(s, signature=["temporal"], keys=["a", "b"])         # validated, base score X
    k2 = _obj(s, signature=["co_engagement"], keys=["c", "d"])    # validated, equal base score X
    base = retrieve_priors(s, _bundle(), now=NOW).priors
    assert [p.ko_id for p in base] == sorted([k1, k2])            # tie broken by id (k1 first)
    k1_conf = next(p.confidence for p in base if p.ko_id == k1)

    boosted = retrieve_priors(s, _bundle(), now=NOW, usefulness={k2: 1.0}).priors
    assert boosted[0].ko_id == k2                                  # usefulness lifted k2 above k1
    # RANKING ONLY: the underlying memory's confidence is untouched by feedback.
    assert next(p.confidence for p in boosted if p.ko_id == k1) == k1_conf
    assert next(p.usefulness for p in boosted if p.ko_id == k2) == 1.0


def test_retrieve_with_feedback_applies_learned_usefulness():
    s = MemoryStore()
    k1 = _obj(s, signature=["temporal"], keys=["a", "b"])
    k2 = _obj(s, signature=["co_engagement"], keys=["c", "d"])
    for inv in ("u1", "u2", "u3"):                                # k2 proven useful repeatedly
        s.record_feedback(RetrievalFeedback(k2, inv, influenced=True, governor_accepted=True,
                                            analyst_agreed=True, at=_at(0)))
    res = retrieve_with_feedback(s, _bundle(), now=NOW)
    assert res.priors[0].ko_id == k2                               # learned signal surfaces k2 first


def test_provenance_filter_drops_cross_platform_priors():
    s = MemoryStore()
    glob = _obj(s, signature=["temporal"], keys=["a", "b"])       # global (no explicit scope)
    other = _obj(s, signature=["co_engagement"], keys=["c", "d"])
    s.get(other).platform_scope = ["tiktok"]                       # explicitly scoped elsewhere
    ids = {p.ko_id for p in retrieve_priors(s, _bundle(), now=NOW, platform="youtube").priors}
    assert glob in ids and other not in ids                        # cross-platform prior filtered out
    res = retrieve_priors(s, _bundle(), now=NOW, platform="youtube")
    assert res.plan.provenance_filter == "youtube"


def test_behavioral_type_filter():
    s = MemoryStore()
    beh = _obj(s, signature=["temporal"], keys=["a", "b"], type_="BehavioralArchetype")
    coord = _obj(s, signature=["co_engagement"], keys=["c", "d"], type_="CoordinationSignature")
    ids = {p.ko_id for p in retrieve_priors(s, _bundle(), now=NOW, types=("BehavioralArchetype",)).priors}
    assert beh in ids and coord not in ids


# --------------------------------------------------------------------------- #
# Adaptive memory quality — measurement only
# --------------------------------------------------------------------------- #
def test_quality_of_is_measurement_only():
    s = MemoryStore()
    kid = _obj(s, signature=["temporal"], keys=["a", "b"])
    ko = s.get(kid)
    conf_before, status_before = ko.confidence(NOW), ko.epistemic_status(NOW)
    agg = aggregate_feedback([RetrievalFeedback(kid, "i1", influenced=True, governor_accepted=True,
                                                analyst_agreed=True, at=_at(0))])
    q = quality_of(ko, agg, now=NOW)
    assert q["ko_id"] == kid and 0.0 <= q["quality"] <= 1.0 and q["usefulness"] == 1.0
    # measuring quality must not have mutated the memory's confidence or status.
    assert ko.confidence(NOW) == conf_before and ko.epistemic_status(NOW) == status_before
    ranked = quality_rankings(s, agg, now=NOW)
    assert ranked and ranked[0]["ko_id"] == kid


# --------------------------------------------------------------------------- #
# Institutional-knowledge dashboard
# --------------------------------------------------------------------------- #
def test_dashboard_reports_precision_reuse_and_compression():
    s = MemoryStore()
    k1 = _obj(s, signature=["temporal"], keys=["a", "b"])
    _two_duplicates(s)                                             # adds a compressible pair
    s.record_feedback(RetrievalFeedback(k1, "i1", influenced=True, governor_accepted=True,
                                        analyst_agreed=True, at=_at(0)))
    s.record_feedback(RetrievalFeedback(k1, "i2", influenced=True, governor_accepted=False,
                                        analyst_agreed=True, at=_at(0)))
    d = dashboard(s, now=NOW)
    assert d["retrieval_precision"] == 0.5 and d["retrieval_events"] == 2
    assert d["compression"]["mergeable_objects"] >= 1
    assert d["reuse"]["total_reuse"] == 2 and "unused_retrievable" in d
    assert "by_tier" in d and "distillation_ratio" in d            # embeds memory_stats


# --------------------------------------------------------------------------- #
# Postgres parity
# --------------------------------------------------------------------------- #
def test_postgres_parity_merge_feedback_and_dashboard():
    reset_db_for_tests("sqlite:///:memory:")
    pg = PostgresMemoryStore(get_session)
    a, b = _two_duplicates(pg)
    moved = pg.merge_into(a, b)
    assert moved == 1 and pg.get(b).superseded_by == a
    assert len(pg.get(a).ledger) == 3                              # re-parented, provenance preserved

    kid = _obj(pg, signature=["temporal"], keys=["x", "y"])
    pg.record_feedback(RetrievalFeedback(kid, "i1", influenced=True, governor_accepted=True,
                                         analyst_agreed=True, at=_at(0)))
    assert pg.get(kid).reuse_count == 1 and len(pg.feedback(ko_id=kid)) == 1
    d = dashboard(pg, now=NOW)
    assert d["retrieval_events"] == 1 and d["retrieval_precision"] == 1.0


def test_postgres_compression_pass():
    reset_db_for_tests("sqlite:///:memory:")
    pg = PostgresMemoryStore(get_session)
    _two_duplicates(pg)
    rep = compress(pg, now=NOW)
    assert rep.active_before == 2 and rep.active_after == 1 and rep.observations_merged == 1


# --------------------------------------------------------------------------- #
# Regression — existing retrieval paths unchanged when no Sprint-014 inputs
# --------------------------------------------------------------------------- #
def test_regression_legacy_retrieval_unchanged():
    s = MemoryStore(); _obj(s, signature=["temporal"], keys=["a", "b"])
    assert retrieve(s, _bundle(), now=NOW)[0].ko_id                # Sprint-005 path
    assert rank_priors(s.all(), _bundle(), now=NOW)                # no usefulness arg
    res = retrieve_priors(s, _bundle(), now=NOW)                   # Sprint-013 engine, no filters
    assert res.priors and res.plan.provenance_filter is None and res.plan.type_filter is None


def test_replay_determinism_full_loop():
    def _run():
        s = MemoryStore()
        k = _obj(s, signature=["temporal"], keys=["a", "b"])
        record_retrieval_feedback(s, retrieve_priors(s, _bundle(), now=NOW).priors,
                                  investigation="i9", permitted=True, analyst_agreed=True, at=_at(0))
        return retrieve_with_feedback(s, _bundle(), now=NOW).to_dict(), dashboard(s, now=NOW)
    a, b = _run(), _run()
    assert a[0]["priors"] == b[0]["priors"] and a[1]["retrieval_precision"] == b[1]["retrieval_precision"]


# --------------------------------------------------------------------------- #
# Admin routes
# --------------------------------------------------------------------------- #
def test_admin_dashboard_compress_and_feedback_routes():
    reset_db_for_tests("sqlite:///:memory:")
    pg = PostgresMemoryStore(get_session)
    kid = _obj(pg, signature=["temporal"], keys=["a", "b"])
    _two_duplicates(pg)
    with TestClient(app) as tc:
        compressed = tc.post("/v1/admin/memory/compress").json()
        assert compressed["report"]["duplicates_merged"] >= 1

        rec = tc.post("/v1/admin/memory/feedback", json={
            "ko_id": kid, "investigation": "i1", "influenced": True,
            "governor_accepted": True, "analyst_agreed": True, "at": _at(0)},
        ).json()
        assert rec["recorded"]["useful"] is True

        fb = tc.get("/v1/admin/memory/feedback").json()
        assert fb["count"] == 1

        dash = tc.get("/v1/admin/memory/dashboard").json()
        assert dash["retrieval_events"] == 1 and "compression" in dash
