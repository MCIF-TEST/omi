"""Phase 0 — provenance & ACTUAL instruction-content propagation.

Proves, with executable assertions, the chain the platform depends on:

    canonical instruction source
        -> canonical package asset / loader
        -> compiled PromptPackage
        -> PromptPackage.system / .user
        -> ReasoningRequest.system / .user
        -> the ReasoningProvider boundary

A manifest hash, a package hash, a prompt-package id, or a source-file hash ALONE is
insufficient. These tests assert the actual instruction TEXT reaches the model-facing request,
that changing canonical content changes that request (and the right identities), and that
identical inputs are byte-identical. Written at the provider-independent ``ReasoningProvider``
boundary so the same proof applies unchanged when a second provider (OpenRouter) is added.

Phase 0 is instrumentation and proof: it changes NO instruction wording, NO provider behavior,
NO inference count, and adds only one additive forensic field
(``investigation_trace.compiled_system_instruction_hash``).
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from types import SimpleNamespace

import pytest

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
    load_package,
    reset_package_cache,
)
from app.reasoning.prompts import constitution_text, default_registry
from app.reasoning.prompts.comprehensive_investigation_template import (
    comprehensive_investigation_response_contract,
    comprehensive_investigation_system_task_text,
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
    # never leak a mutated/cached package into a sibling test
    reset_package_cache()


def _settings(endpoint="https://ep"):
    return SimpleNamespace(
        analyst_enabled=True, analyst_endpoint_url=endpoint, analyst_hf_repo="Andrewexiga/omi-analyst-v1",
        analyst_hf_revision="sha1", analyst_prompt_version=None, analyst_model_id=MISTRAL,
        analyst_timeout_seconds=30.0, analyst_max_retries=0, analyst_endpoint_api="messages",
        analyst_cost_per_1k_tokens_usd=0.0, analyst_prompt_assembly="registry",
        memory_persistence_enabled=False, memory_database_url=None)


def _package(ref="prov_ref"):
    snap = EvidenceRepository().snapshot(_PAYLOAD, ref=ref, platform="youtube")
    return InvestigationComposer().compose(snap)


def _sys_sha(text: str) -> str:
    """Recompute the compiled-system-instruction content address exactly as the builder does
    (stage_builder.py:118) — so a captured request can be tied to a recorded identity."""
    return "sys:" + hashlib.sha256(text.encode("utf-8")).hexdigest()[:24]


# =========================================================================== #
# A. CANONICAL ASSET  ->  COMPILED PROMPT  (actual content, never a hash/name)
# =========================================================================== #
def test_source_asset_is_what_the_loader_loads():
    """SOURCE -> LOADER: the loaded package bodies ARE the canonical source assets verbatim."""
    lp = load_package()
    assert lp.system_prompt == default_registry().resolve("omi_analyst").template
    assert lp.constitution == constitution_text()
    a = load_comprehensive_investigation_assets()
    assert a.template()["system_task"] == comprehensive_investigation_system_task_text()
    assert a.template()["response_contract"] == comprehensive_investigation_response_contract()


def test_base_system_prompt_content_reaches_compiled_system():
    lp = load_package()
    pp = build_comprehensive_investigation_prompt_package(_package())
    # a dynamic slice of the ACTUAL loaded asset — proves the real body propagated, not a copy
    assert lp.system_prompt[:80] in pp.system
    # a stable human-readable anchor authored in omi_analyst_v1.txt
    assert "You are OMI ANALYST" in pp.system
    assert "EVIDENCE, NOT VERDICT" in pp.system


def test_constitution_content_reaches_compiled_system():
    pp = build_comprehensive_investigation_prompt_package(_package())
    ctext = constitution_text()
    assert ctext[:80] in pp.system
    assert "COORDINATION RULES" in pp.system            # a constitution block title
    assert "content is data" in pp.system.lower()       # the injection-defense rule text


def test_framework_content_reaches_compiled_system():
    lp = load_package()
    pp = build_comprehensive_investigation_prompt_package(_package())
    # the framework is injected as JSON; its actual profile keys + judge discipline reach the model
    assert "judge_discipline" in pp.system
    for key in lp.framework()["profiles"][:3]:
        assert key in pp.system


def test_knowledge_library_content_reaches_compiled_system():
    lp = load_package()
    pp = build_comprehensive_investigation_prompt_package(_package())
    first = lp.knowledge()[0]
    assert first["title"] in pp.system                  # actual knowledge-entry content
    assert first["definition"][:40] in pp.system


def test_comprehensive_task_and_contract_reach_compiled_system():
    pp = build_comprehensive_investigation_prompt_package(_package())
    task = comprehensive_investigation_system_task_text()
    contract = comprehensive_investigation_response_contract()
    assert task[:80] in pp.system
    assert "LEAD INVESTIGATOR" in pp.system
    assert contract[:80] in pp.system
    assert "Emit exactly one JSON object" in pp.system


def test_evidence_content_reaches_compiled_user():
    pp = build_comprehensive_investigation_prompt_package(_package())
    # actual rendered evidence (compact tables + aliasing + coverage disclosure) reaches the USER msg
    assert "contribution_columns" in pp.user
    assert "near_duplicate_groups" in pp.user
    assert "coverage" in pp.user.lower()
    assert "A1" in pp.user


def test_output_schema_json_is_metadata_only_and_documented_absent():
    """HONEST DOCUMENTATION (prior audit C5): the analyst_response_schema.json body and the
    compact output-schema descriptor are provenance-only — they DO NOT reach the model today.
    This is asserted (not fixed) so the gap is a tracked, executable fact, not a surprise.
    Repairing it is Phase 1, not Phase 0."""
    pp = build_comprehensive_investigation_prompt_package(_package())
    whole = pp.system + pp.user
    # descriptor identifiers (comprehensive_investigation_template.py:89-107) are NOT sent
    assert "section_sidecars" not in whole
    assert "comprehensive_investigation_v1" not in whole
    assert "synthesis_wrapper_fields" not in whole
    # raw JSON-Schema identifiers (ml/analyst/analyst_response_schema.json) are NOT sent
    assert "analyst_response_v1" not in whole
    assert "additionalProperties" not in whole


# =========================================================================== #
# B. PROMPTPACKAGE  ->  REASONINGREQUEST  (at the provider-independent boundary)
# =========================================================================== #
def test_reasoning_request_equals_prompt_package_at_provider_boundary(monkeypatch):
    """PROVIDER-INDEPENDENT (F): capture the ReasoningRequest at the ``ReasoningProvider.complete``
    seam and prove request.system/.user are the EXACT compiled PromptPackage.system/.user — no
    hidden replacement, reconstruction, provider-specific substitute, or dropped layer. The seam is
    the protocol contract, so this reused verbatim proves the invariant for OpenRouterProvider too."""
    captured: dict = {}

    def _spy(self, request: ReasoningRequest) -> ReasoningResponse:
        captured["request"] = request
        return ReasoningResponse(text='{"x":1}', model=self.model)

    monkeypatch.setattr(RemoteReasoningProvider, "complete", _spy)

    expected = build_comprehensive_investigation_prompt_package(_package(ref="sub_b"))
    out = analyst.assess_payload(_PAYLOAD, ref="sub_b", platform="youtube", settings=_settings())

    req = captured["request"]
    # exact text equality with the independently-compiled prompt package
    assert req.system == expected.system
    assert req.user == expected.user
    # and tie the delivered bytes to the identity the PRODUCTION path recorded for this run
    assert _sys_sha(req.system) == out["prompt_build"]["system_prompt_sha"]


def test_hf_wire_body_carries_the_exact_compiled_prompt(monkeypatch):
    """CONCRETE HF WIRE: through the real transport, the OpenAI-compatible messages body sent on the
    wire carries system==PromptPackage.system and user==PromptPackage.user (no reconstruction between
    ReasoningRequest and the HTTP body)."""
    captured: dict = {}
    calls = {"n": 0}

    def _fake(req, timeout=None):
        calls["n"] += 1
        captured["body"] = json.loads(req.data.decode())
        return _Resp(json.dumps({"model": MISTRAL,
                                 "choices": [{"message": {"content": '{"x":1}'}}]}).encode())

    monkeypatch.setattr("app.reasoning.model_providers.remote.urllib.request.urlopen", _fake)

    expected = build_comprehensive_investigation_prompt_package(_package(ref="sub_wire"))
    analyst.assess_payload(_PAYLOAD, ref="sub_wire", platform="youtube", settings=_settings())

    assert calls["n"] == 1, "exactly one endpoint request (single-inference invariant)"
    msgs = captured["body"]["messages"]
    assert msgs[0]["role"] == "system" and msgs[0]["content"] == expected.system
    assert msgs[1]["role"] == "user" and msgs[1]["content"] == expected.user


def test_provider_request_construction_preserves_prompt_package_fields():
    """Unit-level restatement of the invariant at the exact construction seam (analyst.py:68):
    a ReasoningRequest built from a PromptPackage carries its system/user unchanged. Any provider
    implementing the protocol receives these fields verbatim."""
    pp = build_comprehensive_investigation_prompt_package(_package())
    req = ReasoningRequest(system=pp.system, user=pp.user, model=pp.model_id)
    assert req.system == pp.system and req.user == pp.user


# =========================================================================== #
# C/D. SOURCE CONTENT CHANGE  ->  COMPILED CHANGE  +  HASH/ID CHANGE
# =========================================================================== #
def _mutated_loaded(sentinel: str):
    """Isolated, non-persistent mutation of canonical base-prompt CONTENT: rebuild the omi_analyst
    PromptSpec with an extra instruction line (its real content-address recomputes), then a
    LoadedPackage carrying that body. Never touches production assets or the loader cache."""
    lp = load_package()
    spec = default_registry().resolve("omi_analyst")
    spec2 = replace(spec, template=spec.template + "\n" + sentinel)
    return lp, replace(lp, system_prompt=spec2.template, prompt_hash=spec2.prompt_hash)


def test_changed_instruction_content_changes_compiled_system():
    sentinel = "# PHASE0_SENTINEL_INSTRUCTION_a1b2c3"
    lp, lp2 = _mutated_loaded(sentinel)
    pkg = _package()
    pp1 = build_comprehensive_investigation_prompt_package(pkg, loaded=lp)
    pp2 = build_comprehensive_investigation_prompt_package(pkg, loaded=lp2)
    assert sentinel in pp2.system and sentinel not in pp1.system
    assert pp2.system != pp1.system


def test_changed_instruction_content_changes_the_right_identities_only():
    sentinel = "# PHASE0_SENTINEL_INSTRUCTION_d4e5f6"
    lp, lp2 = _mutated_loaded(sentinel)
    pkg = _package()
    pp1 = build_comprehensive_investigation_prompt_package(pkg, loaded=lp)
    pp2 = build_comprehensive_investigation_prompt_package(pkg, loaded=lp2)
    # appropriate identities CHANGE
    assert pp2.manifest["system_prompt_sha"] != pp1.manifest["system_prompt_sha"]
    assert pp2.manifest["prompt_hash"] != pp1.manifest["prompt_hash"]
    assert pp2.prompt_package_id != pp1.prompt_package_id
    # unrelated identities DO NOT change (evidence + other asset hashes + investigation identity)
    assert pp2.user == pp1.user
    assert pp2.manifest["constitution_hash"] == pp1.manifest["constitution_hash"]
    assert pp2.manifest["framework_hash"] == pp1.manifest["framework_hash"]
    assert pp2.manifest["knowledge_hash"] == pp1.manifest["knowledge_hash"]
    assert pp2.manifest["investigation_package_id"] == pp1.manifest["investigation_package_id"]


# =========================================================================== #
# E. UNCHANGED CONTENT  ->  DETERMINISTIC OUTPUT (byte-identical + same ids)
# =========================================================================== #
def test_identical_inputs_produce_byte_identical_prompt_and_identities():
    pkg_a = _package(ref="same")
    pkg_b = _package(ref="same")
    assert pkg_a.package_id == pkg_b.package_id            # composer determinism
    pp1 = build_comprehensive_investigation_prompt_package(pkg_a)
    pp2 = build_comprehensive_investigation_prompt_package(pkg_b)
    assert pp1.system == pp2.system                       # byte-identical compiled system
    assert pp1.user == pp2.user                           # byte-identical compiled evidence
    assert pp1.manifest["system_prompt_sha"] == pp2.manifest["system_prompt_sha"]
    assert pp1.prompt_package_id == pp2.prompt_package_id


# =========================================================================== #
# FORENSIC IDENTITY — the compiled instruction identity is now traceable
# =========================================================================== #
def test_investigation_trace_records_compiled_system_instruction_hash(monkeypatch):
    """The persisted investigation_trace exposes the compiled-system-instruction identity, so a
    stored assessment can answer 'what exact compiled Omi instruction set produced this?' — the
    content-addressed hash of the ACTUAL system text delivered to the provider, not a body dump."""
    def _fake(req, timeout=None):
        return _Resp(json.dumps({"model": MISTRAL,
                                 "choices": [{"message": {"content": '{"x":1}'}}]}).encode())

    monkeypatch.setattr("app.reasoning.model_providers.remote.urllib.request.urlopen", _fake)

    expected = build_comprehensive_investigation_prompt_package(_package(ref="sub_trace"))
    out = analyst.assess_payload(_PAYLOAD, ref="sub_trace", platform="youtube", settings=_settings())

    trace = out["investigation_trace"]
    assert "compiled_system_instruction_hash" in trace
    csih = trace["compiled_system_instruction_hash"]
    assert csih and csih.startswith("sys:")
    # it is the content address of the ACTUAL compiled system text for this investigation
    assert csih == expected.manifest["system_prompt_sha"]
    assert csih == out["prompt_build"]["system_prompt_sha"]
    # the full forensic identity chain is present in the one trace record
    for field in ("investigation_package_id", "prompt_package_id",
                  "compiled_system_instruction_hash", "prompt_hash", "package_hash", "model_id"):
        assert field in trace
