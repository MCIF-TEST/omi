"""AI deployment package & prompt-system consolidation (Sprint 024).

Verifies the deployment-layer consolidation: the complete per-prompt **Prompt Catalog** (full
metadata generated from the registry + specialist library, drift-guarded), its inclusion in the HF
publish manifest, and that the production docs (model card + deployment runbook) cover the required
operator sections. All artifacts are reproducible from GitHub; no prompt system is duplicated and no
specialist is activated.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

from app.reasoning.prompts.export import (
    CATALOG_PATH,
    catalog_matches_committed,
    prompt_catalog,
    render_catalog_json,
)

_REPO_ROOT = Path(__file__).resolve().parents[3]

# The 14 metadata fields the charter requires for every specialist prompt.
_REQUIRED_FIELDS = (
    "mission", "inputs", "outputs", "constraints", "evidence_rules", "citation_rules",
    "memory_rules", "context_rules", "governor_compatibility", "json_schema", "version",
    "prompt_hash", "constitution_version", "dependencies",
)


# --------------------------------------------------------------------------- #
# Phase 2 — the Prompt Catalog
# --------------------------------------------------------------------------- #
def test_catalog_matches_committed_and_is_registry_derived():
    assert catalog_matches_committed() is True
    assert CATALOG_PATH.exists()
    assert CATALOG_PATH.read_text(encoding="utf-8") == render_catalog_json()


def test_catalog_covers_production_prompt_and_all_specialists():
    c = prompt_catalog()
    assert c["counts"]["specialists"] == 13 and c["specialists_activated"] is False
    assert c["production_prompt"]["key"] == "omi_analyst"
    assert c["production_prompt"]["prompt_hash"].startswith("ph:")
    assert c["production_prompt"]["json_schema"] == "schema/analyst_response_schema.json"
    keys = {s["key"] for s in c["specialists"]}
    assert {"behavior_analyst", "coordination_analyst", "judge", "memory_analyst",
            "calibration_analyst", "risk_analyst"} <= keys


def test_every_specialist_entry_has_complete_metadata():
    c = prompt_catalog()
    for entry in c["specialists"]:
        for field in _REQUIRED_FIELDS:
            assert field in entry and entry[field], f"{entry['key']} missing {field}"
        assert entry["prompt_hash"].startswith("ph:")
        assert entry["constitution_version"] == c["constitution"]["version"]
        assert entry["dependencies"]["primary_blocks"]          # constitution-block dependencies
        assert isinstance(entry["reasoning_rules"], dict)
    # the Judge targets the analyst assessment schema; a finding specialist targets a council artifact.
    judge = next(s for s in c["specialists"] if s["key"] == "judge")
    assert judge["json_schema"] == "schema/analyst_response_schema.json"


def test_hf_manifest_publishes_manifest_and_catalog():
    spec = importlib.util.spec_from_file_location(
        "register_hf_model", _REPO_ROOT / "ml" / "analyst" / "register_hf_model.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    target, files = mod.load_manifest(_REPO_ROOT / "ml" / "analyst" / "hf_repo_manifest.toml")
    ok, resolved, errors = mod.validate(target, files)
    assert ok, errors
    published = {dst for _s, dst, _k in resolved}
    assert {"prompts/prompt_manifest.json", "prompts/prompt_catalog.json"} <= published


# --------------------------------------------------------------------------- #
# Phase 5/6 — production documentation coverage
# --------------------------------------------------------------------------- #
def test_deployment_runbook_covers_every_operator_section():
    doc = (_REPO_ROOT / "ml" / "analyst" / "DEPLOYMENT.md").read_text(encoding="utf-8").lower()
    for topic in ("inference endpoint", "environment variable", "revision", "render", "supabase",
                  "health", "smoke test", "rollback", "monitoring", "troubleshooting",
                  "expected logs", "expected", "failure recovery"):
        assert topic in doc, topic
    # the exact activation env vars must be named so deployment needs no guessing.
    for var in ("omi_analyst_enabled", "omi_analyst_endpoint_url", "omi_analyst_endpoint_api",
                "hf_token", "omi_analyst_hf_revision"):
        assert var in doc, var


def test_model_card_covers_production_sections():
    card = (_REPO_ROOT / "ml" / "analyst" / "hf_repo" / "README.md").read_text(encoding="utf-8").lower()
    for section in ("architecture & reasoning pipeline", "specialist architecture", "governor",
                    "memory", "shadow mode", "prompt registry", "deployment", "roadmap",
                    "version compatibility", "repository relationships", "limitations"):
        assert section in card, section
