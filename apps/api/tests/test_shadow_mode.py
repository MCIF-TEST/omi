"""Shadow Mode evaluation pipeline tests (Sprint 007).

Covers the deterministic comparison engine (correctness + metric accuracy + determinism),
shadow execution (deterministic / AI / fallback), Governor compatibility, deterministic replay
+ drift detection, aggregate stats, artifact persistence, the admin observability routes, and
regression safety (the user-facing production result is never changed by a shadow run).
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.main import app
from app.reasoning.model_providers import MockReasoningProvider, ProviderTimeout
from app.reasoning.orchestrator import BehaviorAnalyst, CounterEvidenceAnalyst, Orchestrator
from app.reasoning.shadow import aggregate_stats, compare, memory_revision, replay, run_shadow
from app.storage.db import get_session, reset_db_for_tests
from app.storage.models import Investigation, User

NOW = datetime(2026, 6, 25, tzinfo=timezone.utc)


def _payload() -> dict:
    return {
        "overall_probability": 0.72, "overall_tier": "elevated", "confidence": 0.6,
        "weak_signals": ["only 8 posts"], "single_axis_capped": False,
        "contributions": [
            {"name": "temporal", "impact": 0.5, "direction": "raises"},        # ev:0002
            {"name": "community", "impact": 0.2, "direction": "lowers"},       # ev:0003
            {"name": "ai_writing", "impact": 0.1, "direction": "neutral", "supplemental": True},  # ev:0004
        ],
        "video": {"clusters": [{"method": "co_engagement", "members": ["@a", "@b", "@c"]}]},  # ev:0005
    }


def _valid_provider() -> MockReasoningProvider:
    return MockReasoningProvider(structured={
        "findings": [{"signal": "temporal", "claim": "Bursty posting raises suspicion.",
                      "direction": "raises", "evidence_refs": ["ev:0002"]}],
        "uncertainty": ["Only 8 posts."],
    })


class _Settings:
    def __init__(self, **kw):
        self.analyst_enabled = kw.get("analyst_enabled", False)
        self.analyst_endpoint_url = kw.get("analyst_endpoint_url", None)
        self.analyst_hf_repo = kw.get("analyst_hf_repo", "Andrewexiga/omi-analyst-v1")
        self.analyst_hf_revision = kw.get("analyst_hf_revision", None)
        self.analyst_timeout_seconds = kw.get("analyst_timeout_seconds", 30.0)
        self.analyst_max_retries = kw.get("analyst_max_retries", 2)


def _mk_view(assessment: dict, *, bb_digest: str = "bb:x", permitted: bool = True, fallback: bool = False) -> dict:
    return {
        "assessment": assessment,
        "trace": {"permitted": permitted, "verdict": assessment.get("verdict"),
                  "trace_id": "t", "violation_codes": []},
        "fallback": fallback,
        "blackboard_digest": {"digest": bb_digest},
    }


def _seed(slug: str = "inv_shadow") -> None:
    with get_session() as session:
        u = User(email="a@x.com", password_hash="x", credits_remaining=3)
        session.add(u); session.flush()
        session.add(Investigation(
            user_id=u.id, slug=slug, label="Video xyz",
            input_url="https://youtube.com/watch?v=xyz", kind="video",
            overall_probability=0.72, overall_tier="elevated",
            summary="Elevated.", payload_json=_payload(),
        ))


# --- comparison engine: correctness, metric accuracy, determinism ----------- #
def test_comparison_metric_accuracy():
    prod = _mk_view({
        "verdict": "mixed", "suspicion_tier": "elevated", "confidence_band": "low",
        "coordination_label": "suspicious", "suspicion_probability": 0.72,
        "evidence_for": [{"signal": "temporal", "evidence_refs": ["ev:0002"]}],
        "evidence_against": [{"signal": "community", "evidence_refs": ["ev:0003"]}],
        "uncertainty": ["only 8 posts"],
    }, bb_digest="bb:A")
    shadow = _mk_view({
        "verdict": "mixed", "suspicion_tier": "elevated", "confidence_band": "moderate",
        "coordination_label": "suspicious", "suspicion_probability": 0.72,
        "evidence_for": [{"signal": "temporal", "evidence_refs": ["ev:0002"]},
                         {"signal": "co_engagement", "evidence_refs": ["ev:0005"]}],
        "evidence_against": [{"signal": "community", "evidence_refs": ["ev:0003"]}],
        "uncertainty": ["only 8 posts", "ai added a caveat"],
    }, bb_digest="bb:B")
    c = compare(prod, shadow)
    assert c["agreement"]["verdict"] is True and c["agreement"]["confidence_band"] is False
    assert c["disagreement"]["confidence_band"] == {"production": "low", "shadow": "moderate"}
    assert c["overall_agreement"] is False
    assert c["evidence_overlap"]["jaccard"] == round(2 / 3, 4)        # {2,3} vs {2,3,5}
    assert c["evidence_overlap"]["shadow_only"] == ["ev:0005"]
    assert c["confidence_delta"] == 0.0 and c["number_preserved"] is True
    assert c["uncertainty_delta"]["delta"] == 1 and c["uncertainty_delta"]["shadow_only"] == ["ai added a caveat"]
    assert c["blackboard"]["identical"] is False


def test_comparison_is_deterministic():
    prod = _mk_view({"verdict": "mixed", "suspicion_probability": 0.5, "evidence_for": [], "evidence_against": []})
    shadow = _mk_view({"verdict": "mixed", "suspicion_probability": 0.5, "evidence_for": [], "evidence_against": []})
    assert compare(prod, shadow) == compare(prod, shadow)
    assert compare(prod, shadow)["comparison_id"] == compare(prod, shadow)["comparison_id"]


# --- shadow execution: deterministic / AI / fallback ------------------------ #
def test_shadow_runs_deterministically_without_a_provider():
    rep = run_shadow(_payload(), ref="inv1", settings=_Settings())
    assert rep.production["trace"]["permitted"] and rep.shadow["trace"]["permitted"]
    assert rep.diagnostics["ai_mode"] == "deterministic"
    assert rep.comparison["overall_agreement"] is True               # identical councils
    assert rep.comparison["number_preserved"] is True
    assert rep.production["assessment"]["suspicion_probability"] == 0.72


def test_shadow_runs_the_ai_path_with_a_provider():
    rep = run_shadow(_payload(), ref="inv1", settings=_Settings(), provider=_valid_provider())
    assert rep.diagnostics["ai_mode"] == "ai" and rep.shadow["trace"]["permitted"]
    assert rep.comparison["number_preserved"] is True                # AI never moves the number


def test_shadow_falls_back_when_provider_fails():
    rep = run_shadow(_payload(), ref="inv1", settings=_Settings(),
                     provider=MockReasoningProvider(error=ProviderTimeout("slow")))
    assert rep.diagnostics["ai_mode"] == "fallback"
    assert rep.diagnostics["fallback_reason"] == "ProviderTimeout"
    assert rep.shadow["trace"]["permitted"]                          # pipeline stays operational


def test_production_result_matches_the_baseline_council():
    rep = run_shadow(_payload(), ref="inv1", settings=_Settings(), provider=_valid_provider())
    baseline = Orchestrator(modules=[BehaviorAnalyst(), CounterEvidenceAnalyst()]).run(
        _payload(), ref="inv1", platform="youtube")
    assert rep.production["assessment"] == baseline.assessment       # regression safety


# --- deterministic replay + drift detection --------------------------------- #
def test_replay_reproduces_deterministically():
    first = run_shadow(_payload(), ref="inv1", settings=_Settings(), provider=_valid_provider())
    res = replay(_payload(), previous=first, ref="inv1", settings=_Settings(), provider=_valid_provider())
    assert res["reproduced"] and res["production_reproduced"] and res["shadow_reproduced"]
    assert res["same_inputs"]["bundle_id"] and res["same_inputs"]["model_revision"]
    assert res["drift"] == {}


def test_replay_detects_shadow_drift_under_a_changed_model():
    first = run_shadow(_payload(), ref="inv1", settings=_Settings(), provider=_valid_provider())
    drifted = MockReasoningProvider(structured={"findings": [
        {"signal": "community", "claim": "now reads as raising", "direction": "raises",
         "evidence_refs": ["ev:0003"]}]})
    res = replay(_payload(), previous=first, ref="inv1", settings=_Settings(), provider=drifted)
    assert res["production_reproduced"] is True                      # deterministic path always reproduces
    assert res["shadow_reproduced"] is False                         # changed model → drift


# --- memory revision + aggregate stats -------------------------------------- #
def test_memory_revision_is_deterministic_and_sensitive():
    from app.memory.graph import MemoryStore
    assert memory_revision(None) == "none"
    s1 = MemoryStore()
    empty = memory_revision(s1)
    cand = {"type": "BehavioralArchetype", "signature": ["temporal"], "label": "x"}
    s1.ingest(candidate=cand, investigation="h", stance="supports", evidence_refs=["d"],
              independence_key="a", at=NOW.isoformat())
    assert memory_revision(s1) != empty                              # state change → new revision
    s2 = MemoryStore()
    s2.ingest(candidate=cand, investigation="h", stance="supports", evidence_refs=["d"],
              independence_key="a", at=NOW.isoformat())
    assert memory_revision(s1) == memory_revision(s2)                # same state → same revision


def test_aggregate_stats_accuracy():
    reports = [
        {"diagnostics": {"ai_mode": "ai", "latency_ms": 10.0, "attempts": 1},
         "comparison": {"overall_agreement": True, "number_preserved": True},
         "shadow": {"trace": {"permitted": True}, "fallback": False}},
        {"diagnostics": {"ai_mode": "fallback", "citation_failure": True},
         "comparison": {"overall_agreement": False, "number_preserved": True},
         "shadow": {"trace": {"permitted": True}, "fallback": False}},
    ]
    st = aggregate_stats(reports)
    assert st["n"] == 2 and st["ai_runs"] == 1 and st["fallback_runs"] == 1
    assert st["ai_success_rate"] == 0.5 and st["fallback_rate"] == 0.5
    assert st["citation_failures"] == 1 and st["citation_failure_rate"] == 0.5
    assert st["agreement_rate"] == 0.5 and st["number_preserved_rate"] == 1.0
    assert st["avg_latency_ms"] == 10.0
    assert aggregate_stats([]) == {"n": 0}


# --- admin observability routes + persistence ------------------------------- #
def test_shadow_status_route():
    reset_db_for_tests("sqlite:///:memory:")
    with TestClient(app) as tc:
        body = tc.get("/v1/admin/shadow/status").json()
        assert body["pipeline"] == "operational" and body["governor"] == "mandatory"
        assert body["production_path"] == "deterministic"


def test_shadow_run_persist_fetch_and_stats_routes():
    reset_db_for_tests("sqlite:///:memory:")
    _seed("inv_shadow")
    with TestClient(app) as tc:
        r = tc.post("/v1/admin/shadow/investigations/inv_shadow")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["cached"] is False
        assert body["report"]["comparison"]["number_preserved"] is True
        assert "production" in body["report"] and "shadow" in body["report"]

        assert tc.post("/v1/admin/shadow/investigations/inv_shadow").json()["cached"] is True   # idempotent
        assert "comparison" in tc.get("/v1/admin/shadow/investigations/inv_shadow").json()["report"]
        assert tc.get("/v1/admin/shadow/stats").json()["n"] >= 1


def test_shadow_fetch_404_without_evaluation():
    reset_db_for_tests("sqlite:///:memory:")
    _seed("inv_none")
    with TestClient(app) as tc:
        assert tc.get("/v1/admin/shadow/investigations/inv_none").status_code == 404
