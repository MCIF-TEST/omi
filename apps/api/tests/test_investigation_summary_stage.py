"""Phase P3.4 — the Investigation Summary as a canonical AI reasoning stage.

Proves the overall Investigation Summary is now "just another AI reasoning stage" exactly like Comment
Analysis and Commenter History: it consumes an ``InvestigationSummaryBundle`` (enriched with pure
investigation-synthesis EVIDENCE), assembles its prompt through the ONE canonical stage Prompt Builder
from package assets only (zero embedded prompt text), loads its package asset through the ONE Package
Loader (fail-closed + drift-guarded), reuses the EXISTING analyst response schema (so the website
response / Governor / Floor are unchanged), and — on the production path — reaches the model exclusively
through the AI Investigation Runtime while the deterministic Floor keeps measuring the evidence.
"""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.reasoning import analyst
from app.reasoning import investigation_summary_analysis as ISA
from app.reasoning.context import build_investigation_context
from app.reasoning.evidence_bundles import build_investigation_summary_bundle
from app.reasoning.investigation_summary_analysis import build_investigation_summary_prompt_package
from app.reasoning.package_loader import (
    PackageIntegrityError, load_investigation_summary_assets, reset_package_cache,
)
from app.reasoning.prompt import build_prompt, registered_stages
from app.storage.db import reset_db_for_tests

MISTRAL = "mistralai/Mistral-7B-Instruct-v0.3"

_PAYLOAD = {
    "overall_probability": 0.72, "overall_tier": "elevated", "confidence": 0.55,
    "convergence_score": 0.3, "inputs_provided": ["video"], "video_id": "v1",
    "cross_links": [{"kind": "fellow_traveler", "severity": "elevated", "summary": "co-appeared",
                     "evidence": ["5 shared"], "related_entities": ["a", "b"]}],
    "video": {"coordination_score": 0.66, "coordination_tier": "elevated",
              "clusters": [{"method": "co_engagement", "members": ["a", "b", "c"], "score": 0.7,
                            "evidence": ["tight"]}],
              "commenters": [{"external_id": "a", "handle": "@a", "overall_probability": 0.8,
                              "tier": "high", "confidence": 0.6,
                              "contributions": [{"name": "temporal", "impact": 0.4, "direction": "raises"}],
                              "weak_signals": ["few posts on file"]}]},
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


def _bundle():
    ctx = build_investigation_context(_PAYLOAD, ref="slug1", platform="youtube", slug="slug1", kind="video")
    return build_investigation_summary_bundle(ctx)


def _settings(endpoint=None):
    return SimpleNamespace(
        analyst_enabled=True, analyst_endpoint_url=endpoint, analyst_hf_repo="Andrewexiga/omi-analyst-v1",
        analyst_hf_revision="sha1", analyst_prompt_version=None, analyst_model_id=MISTRAL,
        analyst_timeout_seconds=30.0, analyst_max_retries=0, analyst_endpoint_api="messages",
        analyst_cost_per_1k_tokens_usd=0.0, analyst_prompt_assembly="registry",
        memory_persistence_enabled=False, memory_database_url=None)


# --------------------------------------------------------------------------- #
# Stage registration + one canonical builder
# --------------------------------------------------------------------------- #
def test_investigation_summary_is_registered_with_the_one_builder():
    assert "investigation_summary" in registered_stages()


def test_stage_entrypoint_delegates_to_build_prompt_byte_identically():
    b = _bundle()
    assert (build_investigation_summary_prompt_package(b).to_dict()
            == build_prompt("investigation_summary", b).to_dict())


def test_stage_module_embeds_zero_prompt_text():
    """The stage module carries NO prompt-assembly logic and no embedded prompt scaffolding — all of it
    lives in the package asset + the ONE canonical builder."""
    src = Path(ISA.__file__).read_text(encoding="utf-8")
    assert "# OUTPUT CONTRACT" not in src
    assert "system_prompt_sha" not in src
    assert 'prefix="pp:"' not in src
    assert "hashlib" not in src
    assert "build_prompt(" in src


# --------------------------------------------------------------------------- #
# The prompt is assembled from package assets only, over the enriched bundle
# --------------------------------------------------------------------------- #
def test_prompt_assembles_from_package_assets_and_reuses_existing_schema():
    b = _bundle()
    pp = build_investigation_summary_prompt_package(b)
    # system: the shared package assets + the stage task + the output contract
    for marker in ("REASONING & GOVERNANCE CONSTITUTION",
                   "KNOWLEDGE LIBRARY", "INVESTIGATION SUMMARY TASK", "OUTPUT CONTRACT"):
        assert marker in pp.system
    # the specialist-council framework is NOT injected (single Lead Investigator, not a council)
    assert "SPECIALIST INVESTIGATION FRAMEWORK" not in pp.system
    # the summary stage REUSES the existing analyst response schema (no new schema)
    assert pp.schema_ref == "schema/analyst_response_schema.json"
    assert pp.manifest["package_hash"] == "pkg:584c7d83403b565f006d5a35"   # investigation package unchanged
    assert pp.manifest["investigation_summary_bundle_id"] == b.bundle_id()


def test_user_message_carries_the_enriched_bundle_evidence():
    pp = build_investigation_summary_prompt_package(_bundle())
    for section in ("Investigation-level engine signal", "Cross-account coordination digest",
                    "Strongest signed contribution drivers", "Account roll-up", "Cross-links",
                    "Data-quality caveats", "Institutional-memory context",
                    "Component evidence bundles"):
        assert section in pp.user
    # the coordination digest + account roll-up numbers are present as DATA (echoed, not recomputed)
    assert "co_engagement" in pp.user and "0.66" in pp.user and "few posts on file" in pp.user


# --------------------------------------------------------------------------- #
# The Package Loader loads + verifies + drift-guards the asset (fail-closed)
# --------------------------------------------------------------------------- #
def test_loader_verifies_and_is_fail_closed():
    reset_package_cache()
    a = load_investigation_summary_assets()
    assert a.verify()["verified"] is True
    assert a.schema_ref.endswith("analyst_response_schema.json")
    bad = SimpleNamespace(system_task="", response_contract=a.response_contract, schema_ref=a.schema_ref,
                          template=a.template, output_schema=a.output_schema)
    with pytest.raises(PackageIntegrityError):
        type(a).verify(bad)


def test_committed_hf_template_matches_source_drift_guard():
    from app.reasoning.prompts.export import investigation_summary_template_matches_committed
    assert investigation_summary_template_matches_committed(), (
        "committed investigation_summary_prompt_template.json is stale — regenerate via "
        "app.reasoning.prompts.export.write_investigation_summary_template")


# --------------------------------------------------------------------------- #
# Production path — the model reaches the canonical stage prompt; the compat shape is unchanged
# --------------------------------------------------------------------------- #
def test_production_path_is_now_the_comprehensive_single_inference_not_the_summary_stage():
    """The Investigation-Summary stage is SUPERSEDED as the production path by the comprehensive
    single-inference stage (the summary bundle is a strict projection of the complete package). The
    summary stage module + builder remain intact (proven above), but production no longer routes
    through it — it sends the COMPLETE InvestigationPackage in one comprehensive request."""
    captured = {}

    def _fake(req, timeout=None):
        captured["body"] = json.loads(req.data.decode())
        return _Resp(json.dumps({"model": MISTRAL,
                                 "choices": [{"message": {"content": '{"x":1}'}}]}).encode())

    with patch("app.reasoning.model_providers.remote.urllib.request.urlopen", _fake):
        out = analyst.assess_payload(_PAYLOAD, ref="sub_is", platform="youtube", settings=_settings("https://ep"))
    system_sent = captured["body"]["messages"][0]["content"]
    assert "COMPREHENSIVE INVESTIGATION TASK" in system_sent      # the single-inference stage reached the model
    assert "INVESTIGATION SUMMARY TASK" not in system_sent
    assert out["prompt_build"]["mode"] == "stage:comprehensive_investigation"


def test_compat_output_is_the_existing_analyst_response_shape():
    """The compatibility layer is unchanged: on the deterministic Floor path (default production — no
    endpoint) the stage still produces the exact analyst_response_schema fields the website renders."""
    out = analyst._assess_core(_PAYLOAD, ref="sub_is", platform="youtube", settings=_settings(None), capture={})
    for field in ("verdict", "suspicion_tier", "suspicion_probability", "confidence_band", "headline",
                  "assessment", "evidence_for", "evidence_against", "uncertainty",
                  "what_would_change_this", "governance", "prompt_build", "metrics"):
        assert field in out, f"missing website field {field!r}"
    assert out["governance"]["provider"] == "deterministic-analyst-v1"   # floor unchanged
    assert out["suspicion_tier"] == "elevated"                            # engine number echoed, not recomputed
