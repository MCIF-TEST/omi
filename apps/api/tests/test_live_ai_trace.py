"""Live AI integration — end-to-end trace + integrity diagnostics (Sprint 018).

Verifies the read-only instrumentation that proves the production AI pipeline is wired and shows,
per stage, what executes vs what falls back to deterministic — and that prompt integrity holds
(the Prompt Registry is the single source of truth; GitHub == the Hugging Face model-card mirror).
The trace reflects the REAL production runtime (Orchestrator + mandatory Governor), so it can never
claim a connection that isn't there.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.reasoning.trace import endpoint_health, prompt_integrity, trace_investigation
from app.storage.db import get_session, reset_db_for_tests
from app.storage.repository import AccountRepository


@pytest.fixture(autouse=True)
def _fresh():
    reset_db_for_tests("sqlite:///:memory:")
    yield


def _payload() -> dict:
    return {
        "overall_probability": 0.74, "overall_tier": "elevated", "confidence": 0.6,
        "contributions": [{"name": "temporal", "impact": 0.5, "direction": "raises"},
                          {"name": "community", "impact": 0.2, "direction": "lowers"}],
        "video": {"clusters": [{"method": "co_engagement", "members": ["@a", "@b", "@c"]}]},
    }


# --------------------------------------------------------------------------- #
# Prompt integrity — GitHub == HF, registry is the single source of truth
# --------------------------------------------------------------------------- #
def test_prompt_integrity_registry_is_single_source_and_no_drift():
    pi = prompt_integrity()
    assert pi["registry_is_single_source"] is True
    assert pi["ml_doc_mirror_matches"] is True             # GitHub registry == HF model-card source
    names = {s["specialist"] for s in pi["specialists"]}
    assert {"omi_analyst", "behavior_analyst"} <= names
    assert all(s["prompt_hash"].startswith("ph:") for s in pi["specialists"])
    # revision-pin status is surfaced (unpinned by default → operator action).
    assert "model_revision_pinned" in pi


def test_endpoint_health_reports_not_configured_cleanly():
    h = endpoint_health()
    assert h["status"] == "not_configured"                 # no endpoint/token in test env
    assert h["reachable"] is None and h["endpoint_configured"] is False


# --------------------------------------------------------------------------- #
# End-to-end trace — every stage reported, faithful to the real runtime
# --------------------------------------------------------------------------- #
def test_trace_reports_every_stage_with_timing_and_fallback():
    t = trace_investigation(_payload(), ref="sub_x", platform="youtube")
    stages = {s["stage"]: s for s in t["stages"]}
    for expected in ("evidence_bundle", "memory_retrieval", "context_builder", "prompt_registry",
                     "qwen_model", "specialist_output_and_judge", "governor", "final_response",
                     "supabase_memory_write", "shadow_evaluation", "continuous_improvement",
                     "engineering_dashboard"):
        assert expected in stages, expected
        assert "duration_ms" in stages[expected] and "fallback" in stages[expected]
    # every stage carries a timing; the total is the sum.
    assert t["total_duration_ms"] >= 0.0


def test_trace_qwen_falls_back_to_deterministic_without_endpoint():
    t = trace_investigation(_payload(), ref="sub_x", platform="youtube")
    stages = {s["stage"]: s for s in t["stages"]}
    # no endpoint configured → the Qwen stage runs the deterministic provider.
    assert stages["qwen_model"]["fallback"] == "deterministic"
    assert "deterministic" in stages["qwen_model"]["outputs"]["provider"]
    # the prompt that reached the model stage came from the registry (Sprint 016).
    assert stages["qwen_model"]["outputs"]["prompt"].get("source") == "registry"


def test_trace_runs_through_the_mandatory_governor():
    t = trace_investigation(_payload(), ref="sub_x", platform="youtube")
    gov = next(s for s in t["stages"] if s["stage"] == "governor")
    assert gov["status"] == "executed"
    assert gov["outputs"]["verdict"] in ("permit", "reject")
    assert (gov["outputs"]["trace_id"] or "").startswith("vt:")
    assert gov["outputs"]["constitution_version"] == 1
    # echo discipline: the engine number is preserved through the trace.
    spec = next(s for s in t["stages"] if s["stage"] == "specialist_output_and_judge")
    assert spec["outputs"]["suspicion_probability"] == 0.74


def test_trace_reports_memory_connected_context_still_shadow_only():
    """Sprint 021 wired institutional memory into the production analyst (prior_context); the Context
    Builder still feeds only the shadow council — the trace reflects each honestly."""
    t = trace_investigation(_payload(), ref="sub_x", platform="youtube")
    stages = {s["stage"]: s for s in t["stages"]}
    assert stages["memory_retrieval"]["transmitted_to_production_analyst"] is True
    assert stages["context_builder"]["transmitted_to_production_analyst"] is False


# --------------------------------------------------------------------------- #
# Admin endpoints
# --------------------------------------------------------------------------- #
def test_admin_integrity_and_trace_endpoints():
    with get_session() as s:
        AccountRepository(s).create_investigation(
            user_id=1, slug="inv_trace_001", label="t", input_url="https://youtube.com/watch?v=x",
            target_id="x", kind="comprehensive", overall_probability=0.74, overall_tier="elevated",
            summary="t", quota_used=0, payload_json=_payload())
    with TestClient(app) as tc:
        integ = tc.get("/v1/investigations/analyst/integrity").json()
        assert integ["prompt_integrity"]["registry_is_single_source"] is True
        assert integ["endpoint_health"]["status"] == "not_configured"

        traced = tc.post("/v1/investigations/inv_trace_001/analyst/trace").json()
        assert traced["slug"] == "inv_trace_001"
        assert any(st["stage"] == "governor" for st in traced["trace"]["stages"])
        assert traced["trace"]["flag_state"]["governor"] == "mandatory"
