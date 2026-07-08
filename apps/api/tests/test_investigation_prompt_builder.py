"""Phase P1.1 — the Canonical Prompt Builder + the Prompt Template package asset.

Proves the runtime contract for this layer: the Prompt Builder assembles the final prompt EXCLUSIVELY
from package assets (system prompt, constitution, framework, knowledge, response contract) with the
InvestigationContext as its only evidence input; it embeds ZERO prompt text (all scaffolding lives in
the published Prompt Template asset); the output PromptPackage is content-addressed and traces every
asset + the context it was built from; the asset is drift-guarded and published through the existing
GitHub→HF pipeline; and the builder performs no inference.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.reasoning.context import build_investigation_context
from app.reasoning.package import load_ai_package
from app.reasoning.prompt import PromptPackage, build_prompt_package
from app.reasoning.prompt import builder as builder_mod
from app.reasoning.prompts import assembly_template, constitution_text, default_registry, template_hash
from app.reasoning.prompts.export import (
    prompt_template_manifest,
    prompt_template_matches_committed,
    render_prompt_template_json,
    PROMPT_TEMPLATE_PATH,
)


def _context():
    payload = {
        "overall_probability": 0.72, "overall_tier": "elevated", "summary": "x",
        "inputs_provided": ["video"], "video_id": "v1",
        "contributions": [{"name": "temporal", "impact": 0.4, "direction": "raises", "headline": "bursty"}],
        "video": {
            "coordination_score": 0.66, "coordination_tier": "elevated",
            "clusters": [{"method": "co_engagement", "members": ["a", "b", "c"], "score": 0.7,
                          "evidence": ["tight"]}],
            "commenters": [{"external_id": "a", "handle": "@a", "overall_probability": 0.8, "tier": "high",
                            "confidence": 0.6, "reasons": ["bursty posting"],
                            "signals": [{"name": "temporal", "probability": 0.8, "confidence": 0.7}]}],
        },
    }
    return build_investigation_context(payload, ref="slug1", platform="youtube", slug="slug1", kind="video")


def test_builds_prompt_package_from_context():
    pp = build_prompt_package(_context())
    assert isinstance(pp, PromptPackage)
    assert pp.response_format == "json_object"
    assert pp.schema_ref == "schema/analyst_response_schema.json"
    assert pp.model_id == "mistralai/Mistral-7B-Instruct-v0.3"
    assert pp.system and pp.user and pp.prompt_package_id.startswith("pp:")


def test_system_is_assembled_only_from_package_assets():
    pp = build_prompt_package(_context())
    tmpl = assembly_template()
    # the omi_analyst system prompt (registry asset) opens it
    assert default_registry().resolve("omi_analyst").template[:60] in pp.system
    # the constitution asset is present
    assert constitution_text()[:40] in pp.system
    # the assembly asset's block headers + the response contract are present
    for b in tmpl["system_blocks"]:
        if b["header"]:
            assert b["header"] in pp.system
    assert tmpl["response_contract"] in pp.system


def test_user_presents_the_investigation_context_evidence():
    ctx = _context()
    pp = build_prompt_package(ctx)
    tmpl = assembly_template()
    assert tmpl["evidence_preamble"] in pp.user
    assert tmpl["evidence_instruction"] in pp.user
    for s in tmpl["evidence_sections"]:
        assert s["header"] in pp.user
    # the evidence is the InvestigationContext data (pseudonymized identifiers), not prose
    assert "sub_" in pp.user
    assert ctx.coordination.clusters[0].method in pp.user  # co_engagement present as data


def test_builder_module_contains_zero_embedded_prompt_text():
    """Every header / preamble / contract / instruction must live ONLY in the template asset —
    the builder source must contain none of them."""
    tmpl = assembly_template()
    src = Path(builder_mod.__file__).read_text(encoding="utf-8")
    banned = (
        [tmpl["response_contract"], tmpl["evidence_preamble"], tmpl["evidence_instruction"]]
        + [b["header"] for b in tmpl["system_blocks"] if b["header"]]
        + [b["preamble"] for b in tmpl["system_blocks"] if b["preamble"]]
        + [s["header"] for s in tmpl["evidence_sections"]]
    )
    leaks = [b for b in banned if b and b in src]
    assert not leaks, f"builder embeds prompt text that must come from the asset: {leaks[:3]}"


def test_builder_performs_no_inference():
    """This layer builds a prompt; it never invokes a model. The module must not import the model
    transport, and the PromptPackage must expose no send/complete surface."""
    src = Path(builder_mod.__file__).read_text(encoding="utf-8")
    # No transport import, no HTTP client, no model-call sites (precise patterns, not prose words).
    assert "model_providers" not in src and "RemoteReasoning" not in src
    assert "import urllib" not in src and "urlopen(" not in src and ".complete(" not in src
    pp = build_prompt_package(_context())
    for attr in ("send", "complete", "infer", "call", "generate"):
        assert not hasattr(pp, attr)


def test_prompt_package_is_content_addressed_and_traces_every_asset():
    ctx = _context()
    pp = build_prompt_package(ctx)
    pkg = load_ai_package()
    m = pp.manifest
    assert m["package_hash"] == pkg.package_hash
    assert m["prompt_hash"] == pkg.prompt_hash and m["framework_hash"] == pkg.framework_hash
    assert m["knowledge_hash"] == pkg.knowledge_hash and m["constitution_hash"] == pkg.constitution_hash
    assert m["template_hash"] == pkg.template_hash and m["contract_hash"] == pkg.contract_hash
    assert m["context_id"] == ctx.context_id and m["system_prompt_sha"].startswith("sys:")
    # deterministic; a different investigation yields a different package id
    assert build_prompt_package(ctx).prompt_package_id == pp.prompt_package_id
    other = build_prompt_package(build_investigation_context(
        {"overall_probability": 0.1, "overall_tier": "low"}, ref="slug2", platform="youtube"))
    assert other.prompt_package_id != pp.prompt_package_id


def test_package_hash_includes_the_template_and_contract_assets(monkeypatch):
    """The Prompt Template + Response Contract are package components: changing the template changes
    the package_hash (so a scaffolding change is an attributable package version)."""
    before = load_ai_package().package_hash
    monkeypatch.setattr("app.reasoning.prompts.template_hash", lambda: "tmpl:CHANGED_FOR_TEST")
    after = load_ai_package().package_hash
    assert after != before
    assert after.startswith("pkg:")


def test_template_asset_is_versioned_and_content_addressed():
    a = template_hash()
    assert a.startswith("tmpl:") and a == template_hash()  # deterministic
    tmpl = assembly_template()
    assert tmpl["version"] == "tmpl-v1"
    assert {b["slot"] for b in tmpl["system_blocks"]} >= {
        "system_prompt", "constitution", "specialist_framework", "knowledge_library", "response_contract"}


def test_asset_is_drift_guarded_and_published_via_the_existing_pipeline():
    # committed HF mirror equals a freshly generated one (GitHub == HF on the scaffolding)
    assert prompt_template_matches_committed() is True
    assert PROMPT_TEMPLATE_PATH.exists()
    assert PROMPT_TEMPLATE_PATH.read_text(encoding="utf-8") == render_prompt_template_json()
    # the manifest carries the same hashes the runtime package resolves (runtime == HF)
    man = prompt_template_manifest()
    pkg = load_ai_package()
    assert man["template_hash"] == pkg.template_hash
    assert man["response_contract_hash"] == pkg.contract_hash
    # it is registered in the HF publish manifest (existing register_hf_model pipeline)
    import importlib.util
    root = Path(__file__).resolve().parents[3]
    spec = importlib.util.spec_from_file_location("rhm", root / "ml" / "analyst" / "register_hf_model.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    target, files = mod.load_manifest(root / "ml" / "analyst" / "hf_repo_manifest.toml")
    ok, resolved, errors = mod.validate(target, files)
    assert ok, errors
    assert "prompts/prompt_template.json" in {dst for _s, dst, _k in resolved}
