"""End-to-end validation of the live investigation ↔ institutional memory loop (Sprint 015).

These tests drive the **complete pipeline through the real production code** — Binder → Governor →
Analyst Council → Shadow evaluation → Memory Candidate → Background Consolidation → Retrieval — on
realistic comprehensive-scan payloads (multiple behavioral contributions + coordination clusters,
the shape a real investigation emits), never stubbing the council or the Governor. They answer the
Sprint-015 question with evidence: *does institutional memory actually change reasoning on later
investigations, and does it do so without ever moving the engine number?*

The decisive checks:
  * a real settled investigation **populates** memory (Governor-gated),
  * memory **matures** across investigations (candidate → validated → archetype) and then is
    **retrieved and used** on a subsequent investigation,
  * the engine number is **constitutionally preserved** the whole way (memory is context, not proof),
  * a Governor REJECT (or ``learn=False`` probe) writes **nothing**,
  * the loop is **deterministic** (replayable), and the dashboard reports the full metric set.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.main import app
from app.memory.consolidation import consolidate
from app.memory.graph import MemoryStore, PostgresMemoryStore
from app.memory.metrics import dashboard, retrieval_benchmark
from app.memory.pipeline import measure_memory_impact
from app.memory.tiers import ARCHETYPE, CANDIDATE, VALIDATED, tier_of
from app.storage.db import get_session, reset_db_for_tests
from app.storage.repository import AccountRepository

NOW = datetime(2026, 6, 28, tzinfo=timezone.utc)


def _payload(prob: float = 0.79) -> dict:
    """A realistic comprehensive-scan payload — the shape a real coordinated-inauthentic read
    emits: several behavioral contributions (raising + lowering) and multiple coordination
    clusters with overlapping members."""
    return {
        "overall_probability": prob, "overall_tier": "elevated", "confidence": 0.63,
        "contributions": [
            {"name": "temporal_burst", "impact": 0.55, "direction": "raises"},
            {"name": "duplicate_phrasing", "impact": 0.42, "direction": "raises"},
            {"name": "reply_pod", "impact": 0.3, "direction": "raises"},
            {"name": "account_age", "impact": 0.16, "direction": "lowers"},
        ],
        "video": {"clusters": [
            {"method": "co_engagement", "members": ["@a", "@b", "@c", "@d"]},
            {"method": "temporal_synchrony", "members": ["@a", "@b", "@c"]},
        ]},
    }


def _run(store, ref, *, prob=0.79, now=NOW, learn=True):
    return measure_memory_impact(_payload(prob), ref=ref, store=store, now=now, learn=learn)


def _mature(store, *, n=3):
    """Drive ``n`` independent investigations of the same pattern + consolidate, so the pattern
    crosses candidate → validated → archetype (the deterministic distillation lifecycle)."""
    for i in range(1, n + 1):
        _run(store, f"inv-{i:03d}", prob=0.78 + i * 0.01)
        consolidate(store, now=NOW)


# --------------------------------------------------------------------------- #
# A real investigation populates memory — Governor-gated
# --------------------------------------------------------------------------- #
def test_real_investigation_populates_memory():
    store = MemoryStore()
    impact = _run(store, "inv-001")
    assert impact.governor_accepted is True                 # the deterministic ruling was permitted
    assert impact.learned and len(store) == len(impact.learned)   # candidates written from real bundle
    # patterns, never verdicts: what was written is structural archetypes/signatures.
    types = {k.type for k in store.all()}
    assert types <= {"BehavioralArchetype", "CoordinationSignature"}
    assert tier_of(store.all()[0], NOW) == CANDIDATE        # one observation -> candidate, not yet retrievable


def test_learn_false_is_a_pure_probe():
    store = MemoryStore()
    impact = _run(store, "inv-001", learn=False)
    assert impact.retrieved == 0 and len(store) == 0        # measured, but wrote nothing
    assert impact.learned == [] and impact.feedback_recorded == 0
    assert store.feedback() == []


# --------------------------------------------------------------------------- #
# Memory matures and then measurably influences a later investigation
# --------------------------------------------------------------------------- #
def test_memory_matures_then_influences_later_investigation():
    store = MemoryStore()
    # first investigation: nothing to retrieve yet.
    first = _run(store, "inv-000")
    assert first.retrieved == 0
    consolidate(store, now=NOW)

    _mature(store, n=3)                                     # -> archetype tier
    assert ARCHETYPE in set(store.tiers().values())

    # a later investigation of the same pattern now retrieves + uses institutional memory.
    later = _run(store, "inv-later", prob=0.83)
    assert later.retrieved >= 1                             # memory surfaced
    assert later.used >= 1                                  # at least one prior's evidence was cited
    assert 0.0 < later.retrieval_precision <= 1.0
    assert later.evidence_overlap > 0.0                    # surfaced priors overlap the investigation
    assert later.priors and any(p["used"] for p in later.priors)
    # the loop recorded feedback for the surfaced priors.
    assert later.feedback_recorded >= 1 and len(store.feedback()) >= 1


# --------------------------------------------------------------------------- #
# Constitutional invariant — memory is context, never proof
# --------------------------------------------------------------------------- #
def test_engine_number_is_constitutionally_preserved():
    store = MemoryStore()
    _mature(store, n=3)
    impact = _run(store, "inv-check", prob=0.81)
    assert impact.retrieved >= 1                            # memory is active in the council
    assert impact.engine_number_delta == 0.0               # yet the engine number never moves
    assert impact.number_preserved is True                 # memory is context, not proof / OmiScore


def test_governor_gate_blocks_learning_on_reject(monkeypatch):
    """When the Governor REJECTS the ruling, the loop writes no memory candidate (a rejected ruling
    fell back to the Floor; its conclusions are not constitutional evidence)."""
    from app.reasoning.shadow import run_shadow as _rs

    def _rejecting(*args, **kwargs):
        rep = _rs(*args, **kwargs)
        rep.production["trace"]["permitted"] = False        # force a constitutional REJECT
        return rep

    monkeypatch.setattr("app.reasoning.shadow.run_shadow", _rejecting)
    store = MemoryStore()
    impact = measure_memory_impact(_payload(), ref="inv-rej", store=store, now=NOW)
    assert impact.governor_accepted is False
    assert impact.learned == [] and len(store) == 0         # nothing learned from a rejected ruling


# --------------------------------------------------------------------------- #
# Determinism / replay
# --------------------------------------------------------------------------- #
def test_measure_memory_impact_is_deterministic():
    def _once():
        s = MemoryStore()
        _mature(s, n=3)
        return measure_memory_impact(_payload(0.84), ref="inv-rep", store=s, now=NOW, learn=False).to_dict()
    a, b = _once(), _once()
    for k in ("retrieved", "used", "false_retrievals", "retrieval_precision",
              "engine_number_delta", "evidence_overlap", "priors"):
        assert a[k] == b[k]


# --------------------------------------------------------------------------- #
# Dashboard + retrieval benchmark after a real loop
# --------------------------------------------------------------------------- #
def test_dashboard_reports_full_validation_metrics_after_loop():
    store = MemoryStore()
    _mature(store, n=4)
    _run(store, "inv-extra", prob=0.82)
    d = dashboard(store, now=NOW)
    for key in ("by_tier", "distillation_ratio", "compression", "retrieval", "reuse",
                "retrieval_precision", "retrieval_relevance", "false_retrievals",
                "influenced_retrievals", "retrieval_events", "unused_count"):
        assert key in d
    assert d["retrieval"] and d["retrieval"]["latency_ms"] >= 0.0          # real timed retrieval
    assert d["reuse"]["institutional_reuse"] >= 0
    assert d["retrieval_events"] >= 1


def test_retrieval_benchmark_empty_store_is_safe():
    assert retrieval_benchmark(MemoryStore(), now=NOW) == {}                # no retrievable memory yet


# --------------------------------------------------------------------------- #
# Postgres parity + the live admin endpoint over a REAL stored investigation
# --------------------------------------------------------------------------- #
def test_pipeline_postgres_parity():
    reset_db_for_tests("sqlite:///:memory:")
    pg = PostgresMemoryStore(get_session)
    for i in range(1, 4):
        measure_memory_impact(_payload(0.78 + i * 0.01), ref=f"inv-{i:03d}", store=pg, now=NOW)
        consolidate(pg, now=NOW)
    later = measure_memory_impact(_payload(0.83), ref="inv-later", store=pg, now=NOW)
    assert later.retrieved >= 1 and later.number_preserved is True
    assert len(pg.feedback()) >= 1


def test_admin_impact_endpoint_over_real_investigation():
    reset_db_for_tests("sqlite:///:memory:")
    with get_session() as s:
        repo = AccountRepository(s)
        repo.create_investigation(
            user_id=1, slug="inv_real_001", label="real", input_url="https://youtube.com/watch?v=x",
            target_id="x", kind="comprehensive", overall_probability=0.79, overall_tier="elevated",
            summary="real", quota_used=0, payload_json=_payload(),
        )
    with TestClient(app) as tc:
        out = tc.post("/v1/admin/memory/impact/inv_real_001").json()
        assert out["slug"] == "inv_real_001"
        imp = out["impact"]
        assert imp["number_preserved"] is True              # endpoint preserves the engine number
        assert imp["learned"]                               # real investigation populated memory
    # the write landed in the durable store (same test DB).
    assert len(PostgresMemoryStore(get_session)) >= 1
