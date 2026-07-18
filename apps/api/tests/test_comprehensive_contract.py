"""Phase 1 — the ONE canonical comprehensive assessment output contract.

Proves the output-contract contradiction is resolved: there is a single machine-readable canonical schema
for the comprehensive MODEL response (Lead-Investigator synthesis wrapper + six FIRST-CLASS reasoning
domains); the model-facing OUTPUT CONTRACT is rendered deterministically FROM that schema (so schema,
contract, and parser can no longer disagree); the parser validates the model output against it; Omi-owned
provenance/subject/echo are NOT required from the model (Omi injects them AFTER validation); and the whole
investigation is still EXACTLY ONE model inference.
"""
from __future__ import annotations

import json
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.governor import validate_comprehensive_model_output
from app.reasoning import analyst
from app.reasoning.comprehensive_investigation_analysis import (
    build_comprehensive_investigation_prompt_package,
)
from app.reasoning.evidence_repository import EvidenceRepository
from app.reasoning.investigation_composer import InvestigationComposer
from app.reasoning.model_providers.base import ReasoningRequest, ReasoningResponse
from app.reasoning.model_providers.remote import RemoteReasoningProvider
from app.reasoning.package_loader import (
    load_comprehensive_investigation_assets,
    reset_package_cache,
)
from app.reasoning.prompts.comprehensive_investigation_template import (
    COMPREHENSIVE_ASSESSMENT_SCHEMA_ID,
    COMPREHENSIVE_OMI_INJECTED_FIELDS,
    COMPREHENSIVE_SECTION_KEYS,
    _render_output_contract,
    comprehensive_investigation_canonical_schema,
    comprehensive_investigation_response_contract,
)
from app.storage.db import reset_db_for_tests

MISTRAL = "mistralai/Mistral-7B-Instruct-v0.3"

_PAYLOAD = {
    "overall_probability": 0.72, "overall_tier": "elevated", "confidence": 0.55,
    "convergence_score": 0.3, "inputs_provided": ["video"], "video_id": "v1",
    "video": {"video_id": "v1", "coordination_score": 0.66, "coordination_tier": "elevated",
              "clusters": [{"method": "co_engagement", "members": ["a", "b", "c"], "score": 0.7,
                            "evidence": ["tight"]}],
              "thread_scan": {"overall_probability": 0.5, "tier": "moderate"},
              "commenters": [
                  {"external_id": "a", "handle": "@a", "overall_probability": 0.8, "tier": "high",
                   "confidence": 0.6,
                   "recent_activity": [{"text": "great video!!", "created_at": "2026-01-01T00:00:00Z"}],
                   "signals": [{"name": "temporal", "probability": 0.8, "evidence": ["low variance"]},
                               {"name": "community", "probability": 0.18}]},
                  {"external_id": "b", "handle": "@b", "overall_probability": 0.55, "tier": "elevated",
                   "signals": [{"name": "temporal", "probability": 0.5}]}]},
}


class _Resp:
    def __init__(self, body): self._body = body
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def read(self): return self._body


@pytest.fixture(autouse=True)
def _fresh(monkeypatch):
    monkeypatch.setenv("HF_TOKEN", "hf_fake")
    reset_db_for_tests("sqlite:///:memory:")
    yield
    reset_package_cache()


def _settings():
    return SimpleNamespace(
        analyst_enabled=True, analyst_endpoint_url="https://ep", analyst_hf_repo="Andrewexiga/omi-analyst-v1",
        analyst_hf_revision="sha1", analyst_prompt_version=None, analyst_model_id=MISTRAL,
        analyst_timeout_seconds=30.0, analyst_max_retries=0, analyst_endpoint_api="messages",
        analyst_cost_per_1k_tokens_usd=0.0, analyst_prompt_assembly="registry",
        memory_persistence_enabled=False, memory_database_url=None)


def _package(ref="prov_ref"):
    snap = EvidenceRepository().snapshot(_PAYLOAD, ref=ref, platform="youtube")
    return InvestigationComposer().compose(snap)


def _six_domains() -> dict:
    return {
        "comment_reasoning": {"assessment": "near-duplicate praise", "citations": ["A1"]},
        "commenter_history_reasoning": {"assessment": "thin history", "citations": []},
        "account_reasoning": {"assessment": "temporal vs community disagree", "citations": ["A1"]},
        "narrative_reasoning": {"assessment": "no narrative evidence present", "citations": []},
        "coordination_reasoning": {"assessment": "one co-engagement cluster", "citations": ["C1"]},
        "campaign_reasoning": {"assessment": "no corroboration-gated campaign", "citations": []},
    }


def _valid_model_output() -> dict:
    """A canonically-valid comprehensive MODEL output: the model-owned analytical wrapper + six first-class
    reasoning domains. It contains NONE of the Omi-owned provenance/subject/echo/corroboration fields —
    proving the model is not required to fabricate system-owned metadata."""
    return {
        "verdict": "mixed",
        "omi_score": 62,
        "suspicion_tier": "elevated",
        "confidence_band": "moderate",
        "confidence_rationale": "single-axis temporal signal over thin data; no corroborating detector",
        "headline": "Posting cadence is unusually regular, but the read rests on one signal.",
        "assessment": ("The evidence is consistent with mechanical posting regularity: the temporal "
                       "detector reports low interval variation at moderate confidence. This is a "
                       "single-axis result. These findings are probabilistic; the human analyst sets "
                       "the verdict."),
        "evidence_for": [{"signal": "temporal", "claim": "low inter-post interval variation",
                          "evidence_refs": ["A1"]}],
        "evidence_against": [{"signal": "community", "claim": "a modest established footprint",
                              "evidence_refs": ["A1"]}],
        "uncertainty": ["thin data — engagement and semantic detectors abstained"],
        "what_would_change_this": ["thirty or more posts to corroborate the cadence finding"],
        "limits_statement": "This is a probabilistic assessment; the human analyst sets the final verdict.",
        **_six_domains(),
    }


def _run(model_obj: dict):
    calls = {"n": 0}

    def _fake(req, timeout=None):
        calls["n"] += 1
        return _Resp(json.dumps({"model": MISTRAL,
                                 "choices": [{"message": {"content": json.dumps(model_obj)}}]}).encode())

    with patch("app.reasoning.model_providers.remote.urllib.request.urlopen", _fake):
        out = analyst.assess_payload(_PAYLOAD, ref="sub_c", platform="youtube", settings=_settings())
    return out, calls["n"]


# =========================================================================== #
# 1-3. ONE canonical schema; six domains first-class; synthesis in the same assessment
# =========================================================================== #
def test_one_canonical_comprehensive_schema_exists():
    sch = comprehensive_investigation_canonical_schema()
    assert sch["schema_id"] == COMPREHENSIVE_ASSESSMENT_SCHEMA_ID
    assert sch["type"] == "object" and sch["additionalProperties"] is False
    assert isinstance(sch.get("required"), list) and isinstance(sch.get("properties"), dict)


def test_six_reasoning_domains_are_first_class_required_sections():
    sch = comprehensive_investigation_canonical_schema()
    for key in COMPREHENSIVE_SECTION_KEYS:
        assert key in sch["required"], f"{key} must be a REQUIRED domain"
        assert key in sch["properties"], f"{key} must be a first-class property"
        prop = sch["properties"][key]
        assert prop["type"] == "object"
        assert "assessment" in prop["required"]                       # bounded domain conclusion
        assert "citations" in prop["properties"]                      # evidence grounding
    assert len(COMPREHENSIVE_SECTION_KEYS) == 6


def test_lead_investigator_synthesis_is_part_of_the_same_assessment():
    sch = comprehensive_investigation_canonical_schema()
    for wrapper_field in ("verdict", "headline", "assessment", "evidence_for", "evidence_against",
                          "uncertainty", "confidence_band", "limits_statement"):
        assert wrapper_field in sch["required"]
        assert wrapper_field in sch["properties"]


# =========================================================================== #
# 4-7. No drift; schema change -> contract change -> identity change -> reaches provider
# =========================================================================== #
def test_contract_is_derived_from_schema_and_cannot_drift():
    sch = comprehensive_investigation_canonical_schema()
    contract = comprehensive_investigation_response_contract()
    # the contract IS the deterministic render of the schema (single source of truth)
    assert contract == _render_output_contract(sch)
    # every required field name in the schema appears in the model-facing contract
    for field in sch["required"]:
        assert field in contract


def test_changing_canonical_schema_changes_the_compiled_contract_text():
    sch = comprehensive_investigation_canonical_schema()
    mutated = json.loads(json.dumps(sch))
    mutated["required"] = list(mutated["required"]) + ["diagnostic_reasoning"]  # a schema change
    c1 = _render_output_contract(sch)
    c2 = _render_output_contract(mutated)
    assert c1 != c2
    assert "diagnostic_reasoning" in c2 and "diagnostic_reasoning" not in c1


def test_changing_canonical_schema_changes_compiled_instruction_and_package_identity():
    """Reusing the Phase 0 propagation mechanism: a changed canonical contract flows into pp.system and
    flips system_prompt_sha + prompt_package_id (the compiled-instruction + PromptPackage identities)."""
    a = load_comprehensive_investigation_assets()
    pkg = _package()
    pp1 = build_comprehensive_investigation_prompt_package(pkg, assets=a)

    tmpl = a.template()
    tmpl["response_contract"] = tmpl["response_contract"] + "\n# SCHEMA_CHANGE_SENTINEL_diagnostic"
    a2 = replace(a, _template_json=json.dumps(tmpl, ensure_ascii=False, sort_keys=True))
    pp2 = build_comprehensive_investigation_prompt_package(pkg, assets=a2)

    assert "SCHEMA_CHANGE_SENTINEL_diagnostic" in pp2.system and "SCHEMA_CHANGE_SENTINEL_diagnostic" not in pp1.system
    assert pp2.manifest["system_prompt_sha"] != pp1.manifest["system_prompt_sha"]
    assert pp2.prompt_package_id != pp1.prompt_package_id
    assert pp2.user == pp1.user  # unrelated identity unchanged


def test_canonical_contract_reaches_the_reasoning_provider_boundary(monkeypatch):
    """The authoritative canonical output contract reaches the ReasoningProvider.complete boundary."""
    captured: dict = {}

    def _spy(self, request: ReasoningRequest) -> ReasoningResponse:
        captured["request"] = request
        return ReasoningResponse(text='{"x":1}', model=self.model)

    monkeypatch.setattr(RemoteReasoningProvider, "complete", _spy)
    analyst.assess_payload(_PAYLOAD, ref="sub_reach", platform="youtube", settings=_settings())
    assert comprehensive_investigation_response_contract() in captured["request"].system
    assert COMPREHENSIVE_ASSESSMENT_SCHEMA_ID in captured["request"].system


# =========================================================================== #
# 8-11. Parser behaviour: valid parses; missing/forbidden fail; Omi metadata not required
# =========================================================================== #
def test_valid_comprehensive_model_output_parses_successfully():
    errs = validate_comprehensive_model_output(
        _valid_model_output(), schema=comprehensive_investigation_canonical_schema(),
        section_keys=COMPREHENSIVE_SECTION_KEYS)
    assert errs == [], f"expected valid, got {errs}"


def test_missing_reasoning_domain_fails_validation():
    obj = _valid_model_output()
    del obj["campaign_reasoning"]
    errs = validate_comprehensive_model_output(
        obj, schema=comprehensive_investigation_canonical_schema(),
        section_keys=COMPREHENSIVE_SECTION_KEYS)
    assert any("campaign_reasoning" in e for e in errs)


def test_empty_reasoning_section_fails_validation():
    obj = _valid_model_output()
    obj["narrative_reasoning"] = {"assessment": "   ", "citations": []}  # empty assessment
    errs = validate_comprehensive_model_output(
        obj, schema=comprehensive_investigation_canonical_schema(),
        section_keys=COMPREHENSIVE_SECTION_KEYS)
    assert any("narrative_reasoning" in e for e in errs)


def test_forbidden_extra_top_level_field_fails_validation():
    obj = _valid_model_output()
    obj["smuggled_section"] = {"assessment": "not allowed"}
    errs = validate_comprehensive_model_output(
        obj, schema=comprehensive_investigation_canonical_schema(),
        section_keys=COMPREHENSIVE_SECTION_KEYS)
    assert any("smuggled_section" in e for e in errs)


def test_omi_owned_metadata_is_not_required_from_the_model():
    """The model output that carries NONE of the Omi-owned provenance/subject fields is still valid —
    Omi injects those after validation; the model must never be asked to fabricate them."""
    obj = _valid_model_output()
    # AI-first: the model OWNS omi_score + suspicion_tier (they ARE in the output). Only the provenance/
    # subject + the factual corroboration state are Omi-owned and absent from the model output.
    for f in COMPREHENSIVE_OMI_INJECTED_FIELDS + ("corroboration",):
        assert f not in obj
    errs = validate_comprehensive_model_output(
        obj, schema=comprehensive_investigation_canonical_schema(),
        section_keys=COMPREHENSIVE_SECTION_KEYS)
    assert errs == []


# =========================================================================== #
# 12-14. Projection after validation; ONE inference; frontend-compat persisted shape
# =========================================================================== #
def test_omi_metadata_is_injected_after_canonical_validation():
    """The model output has no provenance/subject; after canonical validation OmiSphere injects them
    (from the Floor) to form the governed assessment — model analysis + Omi metadata, boundary explicit."""
    out, calls = _run(_valid_model_output())
    assert out["investigation_trace"]["model_backed"] is True, "a canonically-valid output must be model-backed"
    # Omi-owned provenance/subject injected (were NOT in the model output)
    assert isinstance(out.get("subject"), dict) and out["subject"].get("platform") == "youtube"
    for f in COMPREHENSIVE_OMI_INJECTED_FIELDS:
        assert f in out, f"Omi injected field {f} missing from the governed assessment"
    # the MODEL's analytical content survived (not the Floor's)
    assert out["headline"].startswith("Posting cadence is unusually regular")
    assert out["comprehensive_sections"]["coordination_reasoning"]["assessment"] == "one co-engagement cluster"


def test_exactly_one_primary_inference_for_the_whole_investigation():
    out, calls = _run(_valid_model_output())
    assert calls == 1
    assert out["investigation_trace"]["inference_count"] == 1


def test_persisted_shape_stays_frontend_compatible():
    """The governed assessment still carries every field the existing analyst panel renders — the wrapper
    (verdict / suspicion_probability / confidence_band / evidence_for) + the six comprehensive_sections +
    governance — so no frontend change is required (compatibility projection = identity here)."""
    out, _ = _run(_valid_model_output())
    for field in ("verdict", "omi_score", "suspicion_tier", "confidence_band", "evidence_for",
                  "evidence_against", "headline", "assessment", "uncertainty", "governance"):
        assert field in out, f"frontend-facing field {field} missing"
    assert set(out["comprehensive_sections"]) == set(COMPREHENSIVE_SECTION_KEYS)
    assert "verdict" in out["governance"] and "provider" in out["governance"]
