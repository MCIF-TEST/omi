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


# =========================================================================== #
# Coercion: a good-faith reply RENDERS instead of floorng on a harmless deviation (works first time)
# =========================================================================== #
def _coerce(obj: dict) -> dict:
    from app.governor import coerce_comprehensive_model_output
    return coerce_comprehensive_model_output(
        obj, schema=comprehensive_investigation_canonical_schema(),
        section_keys=COMPREHENSIVE_SECTION_KEYS)


def _valid_after_coercion(obj: dict) -> list[str]:
    return validate_comprehensive_model_output(
        _coerce(obj), schema=comprehensive_investigation_canonical_schema(),
        section_keys=COMPREHENSIVE_SECTION_KEYS)


def test_coercion_drops_unknown_top_level_key_and_validates():
    obj = _valid_model_output()
    obj["summary"] = "a stray field the model liked to add"      # additionalProperties:false would reject
    obj["notes"] = ["another one"]
    coerced = _coerce(obj)
    assert "summary" not in coerced and "notes" not in coerced
    assert _valid_after_coercion(obj) == []


def test_coercion_backfills_a_missing_reasoning_domain():
    obj = _valid_model_output()
    del obj["campaign_reasoning"]
    coerced = _coerce(obj)
    assert coerced["campaign_reasoning"]["assessment"].strip()   # honest "not provided" marker
    assert _valid_after_coercion(obj) == []


def test_coercion_satisfies_f5_when_evidence_against_is_empty():
    obj = _valid_model_output()
    obj["evidence_against"] = []
    obj["confidence_rationale"] = "strong convergent signal"      # lacks the F5 exculpation phrasing
    assert _valid_after_coercion(obj) == []


def test_coercion_derives_tier_and_clamps_score():
    obj = _valid_model_output()
    obj["omi_score"] = 130.7                                      # out of range + float
    del obj["suspicion_tier"]                                     # let it be derived
    coerced = _coerce(obj)
    assert coerced["omi_score"] == 100 and coerced["suspicion_tier"] == "high"
    assert _valid_after_coercion(obj) == []


def test_coercion_derives_omi_score_from_verdict_when_omitted():
    # The exact production case: GPT-5 Mini returns a full assessment (verdict + prose + domains) but
    # omits the numeric omi_score and suspicion_tier. We derive both from ITS OWN verdict so it renders.
    obj = _valid_model_output()
    obj["verdict"] = "likely_inauthentic"
    del obj["omi_score"]
    del obj["suspicion_tier"]
    coerced = _coerce(obj)
    assert coerced["omi_score"] == 72 and coerced["suspicion_tier"] == "elevated"
    assert _valid_after_coercion(obj) == []


def test_coercion_drops_malformed_evidence_items():
    obj = _valid_model_output()
    obj["evidence_for"] = [
        {"signal": "temporal", "claim": "low variance", "evidence_refs": ["A1"]},  # good
        {"signal": "temporal", "claim": "missing refs"},                            # bad → dropped
        "not even an object",                                                        # bad → dropped
    ]
    coerced = _coerce(obj)
    assert len(coerced["evidence_for"]) == 1
    assert _valid_after_coercion(obj) == []


def test_coercion_normalizes_per_account_items():
    obj = _valid_model_output()
    obj["omi_score"] = 62                                                            # overall read (fallback)
    obj["commenter_assessments"] = [
        {"ref": "A1", "omi_score": 130,
         "assessment": "This account's raw omi_score arrived over-range and its suspicion_tier was "
                       "omitted entirely, so the coercion layer must clamp the score into the valid 0-100 "
                       "band and derive a tier from the clamped value rather than discarding the model's "
                       "per-account work outright."},   # clamp + derive tier
        {"ref": "A2", "suspicion_tier": "high",
         "assessment": "This account's suspicion_tier arrived as high but the numeric omi_score was "
                       "omitted, so the coercion layer must derive a representative score from the tier's "
                       "band midpoint rather than leaving the field missing or defaulting to zero."},
        # derive score from tier
        {"ref": "A3",
         "assessment": "This account arrived with neither a numeric omi_score nor a suspicion_tier, so "
                       "the coercion layer must fall back to inheriting the investigation's overall read "
                       "rather than dropping the per-account entry or inventing an unsupported number."},
        # KEEP → inherit overall
        {"assessment": "This item arrived with no account alias ref at all, so it cannot be joined back "
                       "to any real commenter identity and the coercion layer is expected to drop it "
                       "entirely rather than keep an orphaned per-account result around."},
        # no ref → dropped
    ]
    coerced = _coerce(obj)
    ca = {i["ref"]: i for i in coerced["commenter_assessments"]}
    assert set(ca) == {"A1", "A2", "A3"}                          # only the ref-less item is dropped
    assert ca["A1"]["omi_score"] == 100 and ca["A1"]["suspicion_tier"] == "high"
    assert ca["A2"]["omi_score"] == 87 and ca["A2"]["suspicion_tier"] == "high"   # high-band midpoint
    assert ca["A3"]["omi_score"] == 62 and ca["A3"]["suspicion_tier"] == "elevated"  # inherited overall
    assert _valid_after_coercion(obj) == []


def test_coercion_still_floors_when_core_substance_is_missing():
    # The model must supply the substance it alone can produce — coercion never invents it. omi_score /
    # suspicion_tier are NOT in this set: they are derivable from the model's own verdict. This holds when
    # there are NO per-account results to derive an overall read from.
    for core in ("verdict", "headline", "assessment"):
        obj = _valid_model_output()
        del obj[core]
        assert _valid_after_coercion(obj), f"expected floor when {core} is missing"


def test_wrapper_is_salvaged_from_per_account_results_when_the_model_omits_it():
    """Real failure mode from production: the model produced per-account results but omitted the executive
    wrapper (verdict/omi_score/suspicion_tier/headline/assessment). Rather than discard the per-account AI
    work, the coercion derives the overall read from the model's OWN per-account scores so it renders."""
    obj = _valid_model_output()
    for core in ("verdict", "omi_score", "suspicion_tier", "headline", "assessment"):
        obj.pop(core, None)
    obj["commenter_assessments"] = [
        {"ref": "A1", "omi_score": 12, "suspicion_tier": "low",
         "assessment": "This account reads organic across every signal reviewed: its posting cadence is "
                       "irregular in the way a real person's browsing habits are, its follower/following "
                       "ratio is unremarkable, and there is no independent corroboration for anything "
                       "bought or automated about it.", "citations": ["A1"]},
        {"ref": "A2", "omi_score": 82, "suspicion_tier": "high",
         "assessment": "This account fits an amplifier profile: comment timing clusters tightly around "
                       "the same narrow windows as other accounts in this thread, its history is thin "
                       "relative to its posting volume here, and the combination is far more consistent "
                       "with coordinated engagement than organic interest.", "citations": ["A2"]},
        {"ref": "A3", "omi_score": 55, "suspicion_tier": "elevated",
         "assessment": "This account has too thin a history to fully corroborate either explanation: the "
                       "few signals available lean slightly toward inauthentic, but there is not enough "
                       "independent evidence yet to place it higher than an elevated-but-uncertain read.",
         "citations": ["A3"]},
    ]
    coerced = _coerce(obj)
    assert _valid_after_coercion(obj) == []                       # renders instead of floorng
    assert isinstance(coerced["omi_score"], int)                  # overall derived from per-account scores
    assert coerced["verdict"] in ("mixed", "likely_inauthentic", "inconclusive", "likely_authentic")
    assert len(coerced["commenter_assessments"]) == 3             # every per-account result survived


def test_envelope_wrapped_output_is_unwrapped_and_renders():
    """A model that wraps the whole assessment in one top-level key is unwrapped, not discarded."""
    obj = {"investigation": _valid_model_output()}
    assert _valid_after_coercion(obj) == []


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
