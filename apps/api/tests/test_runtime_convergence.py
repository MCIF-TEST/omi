"""Runtime convergence — ONE canonical AI runtime (Sprint 017 → P3.2).

P3.2 eliminates the final parallel production reasoning path: the website's analyst now executes
through the **AI Investigation Runtime** (``runtime.infer`` — the same primitive Comment Analysis
reasons through), with the legacy council's judge-then-floor adjudication semantics preserved
exactly. These tests lock the convergence guarantees so a second runtime can never silently return:

  * production ``assess_payload`` runs through ``AIInvestigationRuntime.infer`` (ONE Binder + ONE
    mandatory Governor + ONE deterministic Floor + ONE forensic capture) — the council Orchestrator
    is never convened in production (it remains Shadow-Mode-only);
  * a Governor REJECT falls back to the **rich** analyst floor (schema-shaped), re-validated, with
    the legacy governance bookkeeping (deterministic-floor / fallback_from / rejected_codes);
  * the analyst's model call goes through the ONE constitutional transport;
  * OmiScore is untouched (the engine number is echoed), and the deterministic fallback is intact.
"""
from __future__ import annotations

import pytest

from app.reasoning import analyst
from app.storage.db import reset_db_for_tests


@pytest.fixture(autouse=True)
def _fresh():
    reset_db_for_tests("sqlite:///:memory:")
    yield


def _payload() -> dict:
    return {
        "overall_probability": 0.72, "overall_tier": "elevated", "confidence": 0.6,
        "summary": "Elevated suspicion across multiple signals.",
        "contributions": [
            {"name": "temporal", "impact": 0.5, "direction": "raises"},
            {"name": "community", "impact": 0.2, "direction": "lowers"},
        ],
        "video": {"clusters": [{"method": "co_engagement", "members": ["@a", "@b", "@c"]}]},
    }


def _enable(monkeypatch):
    monkeypatch.setattr(analyst, "analyst_enabled", lambda settings=None: True)


def test_production_executes_through_the_canonical_runtime(monkeypatch):
    """The single, decisive convergence check (P3.2): production reasoning is produced by the AI
    Investigation Runtime's ``infer`` — exactly once, with the judge-then-floor semantics — and the
    council Orchestrator is NEVER convened in production."""
    _enable(monkeypatch)
    from app.reasoning.orchestrator import Orchestrator
    from app.reasoning.runtime import AIInvestigationRuntime

    infer_calls = []
    orchestrator_runs = []
    real_infer = AIInvestigationRuntime.infer

    def _spy_infer(self, pp, gov_bundle, **kwargs):
        infer_calls.append({"adjudication": kwargs.get("adjudication"),
                            "schema_prefilter": kwargs.get("schema_prefilter")})
        return real_infer(self, pp, gov_bundle, **kwargs)

    monkeypatch.setattr(AIInvestigationRuntime, "infer", _spy_infer)
    monkeypatch.setattr(Orchestrator, "run",
                        lambda self, *a, **k: orchestrator_runs.append(1))
    out = analyst.assess_payload(_payload(), ref="sub_x", platform="youtube")
    assert out is not None
    # ONE runtime inference with the legacy judge-then-floor semantics; NO council orchestration.
    assert infer_calls == [{"adjudication": "judge_then_floor", "schema_prefilter": True}]
    assert orchestrator_runs == []
    # the mandatory Governor stamped the result, and the engine number was echoed (OmiScore intact).
    assert out["governance"]["verdict"] == "permit"
    assert out["governance"]["trace_id"].startswith("vt:")
    assert out["suspicion_probability"] == 0.72


def test_reject_falls_back_to_rich_analyst_floor_not_lean_ruling(monkeypatch):
    """On Governor REJECT the converged path serves the RICH analyst floor (schema-shaped), so the
    response contract is preserved — never the lean council ``build_ruling_assessment`` shape."""
    _enable(monkeypatch)
    from app.governor import Governor
    from app.governor.audit import ValidationTrace

    real = Governor.validate
    calls = {"n": 0}

    def _reject_first(self, ruling, bundle, **kw):
        calls["n"] += 1
        if calls["n"] == 1:  # reject the judge's assessment, permit the floor
            return ValidationTrace(verdict="reject", violation_codes=["S9"], stage_results=[],
                                   version_binding={}, input_digest="in:x", bundle_id=bundle.bundle_id(),
                                   fallback_path="floor")
        return real(self, ruling, bundle, **kw)

    monkeypatch.setattr(Governor, "validate", _reject_first)
    out = analyst.assess_payload(_payload(), ref="sub_x", platform="youtube")
    assert out is not None
    gov = out["governance"]
    assert gov["provider"] == "deterministic-floor" and gov["rejected_codes"] == ["S9"]
    assert gov["fallback_from"]                         # the analyst provider that was rejected
    # RICH schema preserved on the floor path (fields the lean council ruling does not carry).
    for field in ("confidence_rationale", "what_would_change_this", "limits_statement", "subject"):
        assert field in out


def test_one_governor_one_constitution(monkeypatch):
    """The analyst path and the council share ONE Governor / constitution version."""
    _enable(monkeypatch)
    from app.governor import Governor

    out = analyst.assess_payload(_payload(), ref="sub_x", platform="youtube")
    assert out["governance"]["constitution_version"] == Governor.constitution_version


def test_prompt_comes_from_the_one_registry(monkeypatch):
    """Convergence preserves Sprint-016: the system prompt is the registry's, content-addressed."""
    _enable(monkeypatch)
    from app.reasoning.prompts import default_registry

    out = analyst.assess_payload(_payload(), ref="sub_x", platform="youtube")
    prompt = out["governance"]["prompt"]
    assert prompt["source"] == "registry" and prompt["analyst"] == "omi_analyst"
    assert prompt["hash"] == default_registry().resolve("omi_analyst").prompt_hash
