"""Phase P3.3 — Canonical (stage) Prompt Builder consolidation.

Proves there is ONE stage prompt-assembly implementation (``app.reasoning.prompt.build_prompt``) that
every AI reasoning stage routes through; that the per-stage entry points are thin delegators with no
duplicated assembly; that the builder core is stage-agnostic and reaches assets ONLY through the
Package Loader; and that consolidation is byte-identical to the pre-P3.3 per-stage builders.
"""
from __future__ import annotations

from pathlib import Path

from app.reasoning import comment_analysis as CA
from app.reasoning import commenter_history_analysis as CH
from app.reasoning import investigation_summary_analysis as IS
from app.reasoning.comment_analysis import build_comment_prompt_package
from app.reasoning.commenter_history_analysis import build_commenter_history_prompt_package
from app.reasoning.context import build_investigation_context
from app.reasoning.evidence_bundles import (
    build_comment_bundle, build_commenter_history_bundle, build_investigation_summary_bundle,
)
from app.reasoning.investigation_summary_analysis import build_investigation_summary_prompt_package
from app.reasoning.prompt import build_prompt, registered_stages
from app.reasoning.prompt import stage_builder as stage_mod


def _ctx(payload=None):
    payload = payload or {
        "overall_probability": 0.72, "overall_tier": "elevated", "confidence": 0.55, "video_id": "v1",
        "video": {"thread_scan": {"overall_probability": 0.5, "tier": "moderate"},
                  "commenters": [{"external_id": "a", "handle": "@a", "overall_probability": 0.8, "tier": "high",
                                  "confidence": 0.6, "from_cache": False, "matched_prior_neighbors": 2,
                                  "recent_activity": [{"text": "great!!", "created_at": "2026-01-01T00:00:00Z",
                                                       "parent_id": "v9"}]}]}}
    return build_investigation_context(payload, ref="slug1", platform="youtube", slug="slug1", kind="video")


def test_all_stages_are_registered_with_the_one_builder():
    assert set(registered_stages()) >= {"comment", "commenter_history", "investigation_summary"}


def test_stage_entrypoints_delegate_to_build_prompt_byte_identically():
    ctx = _ctx()
    cb = build_comment_bundle(ctx)
    hb = build_commenter_history_bundle(ctx)
    sb = build_investigation_summary_bundle(ctx)
    # the public stage entry == the canonical build_prompt(stage, bundle), byte for byte
    assert build_comment_prompt_package(cb).to_dict() == build_prompt("comment", cb).to_dict()
    assert (build_commenter_history_prompt_package(hb, investigation={"overall_probability": 0.72,
                                                                      "tier": "elevated"}).to_dict()
            == build_prompt("commenter_history", hb,
                            investigation={"overall_probability": 0.72, "tier": "elevated"}).to_dict())
    assert (build_investigation_summary_prompt_package(sb).to_dict()
            == build_prompt("investigation_summary", sb).to_dict())


def test_no_duplicated_prompt_assembly_in_stage_modules():
    """The stage modules carry NO prompt-assembly logic — no system join, manifest, or pp digest.
    All of it lives once in the canonical stage builder."""
    for mod in (CA, CH, IS):
        src = Path(mod.__file__).read_text(encoding="utf-8")
        assert "# OUTPUT CONTRACT" not in src          # the shared system join lives in the builder
        assert "system_prompt_sha" not in src          # the manifest is built once, in the builder
        assert 'prefix="pp:"' not in src               # the pp content-address is computed once
        assert "hashlib" not in src                    # no bespoke hashing in a stage module
        assert "build_prompt(" in src                  # the stage delegates to the ONE builder


def test_builder_is_stage_agnostic_and_loader_only():
    src = Path(stage_mod.__file__).read_text(encoding="utf-8")
    # the builder never imports or names a specific stage
    assert "comment_analysis" not in src and "commenter_history_analysis" not in src
    # it reaches package assets ONLY through the Package Loader — no source-module bypass
    assert "from app.reasoning.package_loader import load_package" in src
    for forbidden in ("app.reasoning.prompts", "app.reasoning.knowledge", "load_ai_package",
                      "default_registry", "constitution_text", "default_library"):
        assert forbidden not in src
    # no inference / endpoint in the builder
    assert "urlopen(" not in src and "_qwen_transport" not in src and "governor" not in src.lower()
