"""Steps 9-13 — the comprehensive single-inference investigation stage.

Proves the AI-native single-inference contract: the Prompt Builder's canonical investigation input is
the COMPLETE InvestigationPackage; ONE inference sends the full budgeted evidence (seven domains) to the
model in ONE endpoint request; the comprehensive stage is registered with the ONE Canonical Prompt
Builder and embeds zero prompt text; the Governor validates the Lead-Investigator synthesis wrapper and
its citation guard resolves the aliases the model was shown (while still rejecting fabricated refs); and
the six per-domain reasoning sidecars are structurally validated + citation-resolved.
"""
from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.reasoning import analyst
from app.reasoning.comprehensive_investigation_analysis import (
    COMPREHENSIVE_INVESTIGATION_STAGE,
    build_comprehensive_investigation_prompt_package,
)
from app.reasoning.evidence_repository import EvidenceRepository
from app.reasoning.investigation_composer import InvestigationComposer
from app.reasoning.package_loader import load_comprehensive_investigation_assets
from app.reasoning.prompt.stage_builder import registered_stages
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


def _settings(endpoint="https://ep"):
    return SimpleNamespace(
        analyst_enabled=True, analyst_endpoint_url=endpoint, analyst_hf_repo="Andrewexiga/omi-analyst-v1",
        analyst_hf_revision="sha1", analyst_prompt_version=None, analyst_model_id=MISTRAL,
        analyst_timeout_seconds=30.0, analyst_max_retries=0, analyst_endpoint_api="messages",
        analyst_cost_per_1k_tokens_usd=0.0, analyst_prompt_assembly="registry",
        memory_persistence_enabled=False, memory_database_url=None)


def _package():
    snap = EvidenceRepository().snapshot(_PAYLOAD, ref="slug1", platform="youtube")
    return InvestigationComposer().compose(snap)


# --------------------------------------------------------------------------- #
# Stage registration + prompt assembly over the COMPLETE package
# --------------------------------------------------------------------------- #
def test_comprehensive_stage_is_registered_with_the_one_builder():
    assert COMPREHENSIVE_INVESTIGATION_STAGE in registered_stages()


def test_prompt_input_is_the_investigation_package_complete_evidence_is_model_facing():
    pp = build_comprehensive_investigation_prompt_package(_package())
    # system: shared package assets + the comprehensive task + output contract
    assert "COMPREHENSIVE INVESTIGATION TASK" in pp.system
    assert "REASONING & GOVERNANCE CONSTITUTION" in pp.system and "KNOWLEDGE LIBRARY" in pp.system
    assert "OUTPUT CONTRACT" in pp.system
    # user: the COMPLETE budgeted package evidence — the compact account table (with detector columns),
    # near-duplicate comment groups, coordination clusters, the coverage manifest, and the alias legend
    u = pp.user
    assert "signal_columns" in u and "contribution_columns" in u   # compact account table
    assert "near_duplicate_groups" in u                            # comment dedup
    assert "cluster_columns" in u                                  # coordination
    assert "evidence-coverage" in u.lower() or "coverage" in u.lower()
    assert '"A1"' in u or "A1" in u                                # aliasing
    # manifest records the package identity + coverage + the six sidecar keys
    assert pp.manifest["investigation_package_id"].startswith("ipkg:")
    assert len(pp.manifest["comprehensive_section_keys"]) == 6


def test_stage_embeds_zero_prompt_text():
    import inspect

    import app.reasoning.comprehensive_investigation_analysis as mod
    src = inspect.getsource(mod)
    # no task/contract prose is embedded here — it all comes from the package asset
    assert "COMPREHENSIVE INVESTIGATION TASK" not in src
    assert "Emit exactly one JSON object" not in src


def test_committed_hf_template_matches_source_drift_guard():
    """The committed HF mirror (published via the GitHub Action from hf_repo_manifest.toml) must equal a
    freshly generated one — so GitHub source and the Hugging Face package cannot drift."""
    from app.reasoning.prompts.export import comprehensive_investigation_template_matches_committed
    assert comprehensive_investigation_template_matches_committed(), (
        "ml/analyst/hf_repo/prompts/comprehensive_investigation_prompt_template.json is stale — "
        "regenerate via app.reasoning.prompts.export.write_comprehensive_investigation_template()")


def test_loader_verifies_and_is_fail_closed():
    a = load_comprehensive_investigation_assets()
    assert a.verify()["verified"] is True
    assert len(a.section_keys) == 6
    assert a.schema_ref.endswith("analyst_response_schema.json")
    assert a.template_hash.startswith("citmpl:")


# --------------------------------------------------------------------------- #
# Governor citation resolution — the alias universe the model was shown resolves
# --------------------------------------------------------------------------- #
def test_governor_resolves_shown_aliases_and_rejects_fabrication():
    from app.governor import Governor
    from app.reasoning.investigation_render import build_alias_legend

    pkg = _package()
    snap = EvidenceRepository().snapshot(_PAYLOAD, ref="slug1", platform="youtube")
    gov_bundle = snap.gov_bundle
    legend = build_alias_legend(pkg)
    gov_bundle.extra_citable = set(pkg.evidence_index) | legend.alias_tokens()
    # a wrapper citing a SHOWN alias resolves (S2 passes); a fabricated ref does not
    hl = gov_bundle.headline()
    base = {"suspicion_probability": round(float(hl.get("overall_probability") or 0.0), 6),
            "suspicion_tier": hl.get("tier"), "verdict": "monitor", "confidence_band": "moderate",
            "confidence_rationale": "r", "headline": "h", "assessment": "a", "uncertainty": "u",
            "what_would_change_this": "w", "limits_statement": "l", "corroboration": {}}
    good = dict(base, evidence_for=[{"claim": "co-engagement", "evidence_refs": ["A1"]}],
                evidence_against=[{"claim": "low community", "evidence_refs": ["A1"]}])
    t_good = Governor().validate(good, gov_bundle)
    assert "fabrication" not in t_good.violation_codes, "a shown alias citation must resolve (S2)"

    bad = dict(base, evidence_for=[{"claim": "made up", "evidence_refs": ["FABRICATED_REF"]}],
               evidence_against=[{"claim": "x", "evidence_refs": ["A1"]}])
    t_bad = Governor().validate(bad, gov_bundle)
    assert "fabrication" in t_bad.violation_codes, "a fabricated citation must still fail (S2)"


def test_validate_comprehensive_sections_structural_and_citations():
    from app.governor import validate_comprehensive_sections
    from app.reasoning.investigation_render import build_alias_legend

    pkg = _package()
    legend = build_alias_legend(pkg).to_manifest()
    keys = load_comprehensive_investigation_assets().section_keys
    raw = {
        "account_reasoning": {"assessment": "temporal vs community disagree", "citations": ["A1"]},
        "coordination_reasoning": {"assessment": "one ring", "citations": ["C1"]},
        "comment_reasoning": {"assessment": "duplicate praise", "citations": ["FAKE_1"]},
        "commenter_history_reasoning": {"assessment": "thin", "citations": []},
        "narrative_reasoning": {"assessment": "none", "citations": []},
        # campaign_reasoning intentionally MISSING to exercise the structural check
    }
    rep = validate_comprehensive_sections(raw, section_keys=keys,
                                          evidence_index=pkg.evidence_index, legend=legend)
    assert rep["structurally_valid"] is False                       # campaign_reasoning missing
    assert "campaign_reasoning" in rep["missing_sections"]
    assert rep["sections"]["account_reasoning"]["resolved"] == ["A1"]
    assert rep["sections"]["coordination_reasoning"]["resolved"] == ["C1"]
    assert rep["sections"]["comment_reasoning"]["unresolved"] == ["FAKE_1"]
    assert rep["unresolved_total"] == 1


# --------------------------------------------------------------------------- #
# Production path — ONE endpoint request carries the complete package evidence
# --------------------------------------------------------------------------- #
def test_production_path_sends_one_request_with_the_complete_package():
    captured: dict = {}
    calls = {"n": 0}

    def _fake(req, timeout=None):
        calls["n"] += 1
        captured["body"] = json.loads(req.data.decode())
        return _Resp(json.dumps({"model": MISTRAL,
                                 "choices": [{"message": {"content": '{"x":1}'}}]}).encode())

    with patch("app.reasoning.model_providers.remote.urllib.request.urlopen", _fake):
        out = analyst.assess_payload(_PAYLOAD, ref="sub_prod", platform="youtube",
                                     settings=_settings())
    # EXACTLY ONE endpoint request for the whole investigation
    assert calls["n"] == 1, "the comprehensive investigation must be ONE endpoint request"
    # that request carried the complete budgeted package evidence (compact account table etc.)
    user_sent = captured["body"]["messages"][1]["content"]
    assert "signal_columns" in user_sent and "near_duplicate_groups" in user_sent
    # provenance records the comprehensive single-inference assembly
    assert out["prompt_build"]["mode"] == "stage:comprehensive_investigation"
    assert out["prompt_build"]["investigation_package_id"].startswith("ipkg:")
    assert out["prompt_build"]["evidence_coverage_mode"] in ("complete", "large_investigation")


def test_website_compat_output_is_the_existing_analyst_shape_plus_sidecars():
    """Website compatibility (step 15): the governed output still carries the existing analyst response
    fields the website renders, PLUS the additive comprehensive sections + validation."""
    def _fake(req, timeout=None):
        return _Resp(json.dumps({"model": MISTRAL,
                                 "choices": [{"message": {"content": '{"x":1}'}}]}).encode())

    with patch("app.reasoning.model_providers.remote.urllib.request.urlopen", _fake):
        out = analyst.assess_payload(_PAYLOAD, ref="sub_c", platform="youtube", settings=_settings())
    # the existing analyst response shape is intact (website renders these unchanged)
    for field in ("verdict", "suspicion_tier", "suspicion_probability", "confidence_band", "headline",
                  "assessment", "evidence_for", "evidence_against", "uncertainty", "governance"):
        assert field in out, f"website-compat field {field} missing"
    # additive: the comprehensive sections + their structural validation report
    assert "comprehensive_sections" in out and "comprehensive_validation" in out
    assert "structurally_valid" in out["comprehensive_validation"]
