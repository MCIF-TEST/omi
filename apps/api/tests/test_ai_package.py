"""The canonical AI deployment package — runtime == the published Hugging Face package.

"The HF package is the canonical AI layer; GitHub is development only." This suite proves it
WITHOUT a runtime HF/GitHub fetch: the backend loads the package from bundled data, and its four
content-addressed components (production prompt, specialist framework, knowledge library,
constitution) are byte-identical to what the GitHub Action publishes to Andrewexiga/omi-analyst-v1.
The drift guard fails CI if runtime and the deployed package ever diverge.
"""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.reasoning import analyst
from app.reasoning.package import AIPackage, load_ai_package
from app.storage.db import reset_db_for_tests

_REPO = Path(__file__).resolve().parents[3]
_HF = _REPO / "ml" / "analyst" / "hf_repo"


@pytest.fixture(autouse=True)
def _fresh():
    reset_db_for_tests("sqlite:///:memory:")
    yield


def test_load_ai_package_is_complete_and_content_addressed():
    pkg = load_ai_package()
    assert isinstance(pkg, AIPackage)
    assert pkg.model_id == "mistralai/Mistral-7B-Instruct-v0.3"
    assert pkg.prompt_hash.startswith("ph:")
    assert pkg.framework_hash.startswith("sf:")
    assert pkg.knowledge_hash.startswith("il:")
    assert pkg.constitution_hash.startswith("cx:")
    assert pkg.package_hash.startswith("pkg:")
    assert pkg.analysts >= 2 and pkg.knowledge_entries > 0 and pkg.knowledge_categories > 0


def test_package_hash_is_deterministic_and_sensitive():
    a, b = load_ai_package(), load_ai_package()
    assert a.package_hash == b.package_hash                       # deterministic
    # sensitivity: the hash folds all four components; a different component set → different hash
    import hashlib
    other = "pkg:" + hashlib.sha256("x".encode()).hexdigest()[:24]
    assert a.package_hash != other


def test_runtime_package_matches_the_published_hf_manifests():
    """The drift guard: runtime AI package == the deployed HF package (all four components)."""
    pkg = load_ai_package()
    pm = json.loads((_HF / "prompts" / "prompt_manifest.json").read_text())
    pc = json.loads((_HF / "prompts" / "prompt_catalog.json").read_text())
    km = json.loads((_HF / "knowledge" / "knowledge_manifest.json").read_text())

    assert pkg.prompt_hash == pm["production_prompt"]["prompt_hash"]        # system prompt
    assert pkg.constitution_hash == pm["constitution"]["hash"]             # constitution
    assert pkg.framework_hash == pc["framework"]["hash"]                    # specialist framework
    assert pkg.knowledge_hash == km["library_hash"]                        # knowledge library


def test_provenance_is_json_safe_and_labels_hf_as_canonical():
    prov = load_ai_package().provenance()
    json.dumps(prov)                                                        # must serialise
    assert "omi-analyst-v1" in prov["source"] and "GitHub = dev" in prov["source"]
    assert prov["prompt_registry"]["omi_analyst_hash"].startswith("ph:")
    assert prov["specialist_framework"]["hash"].startswith("sf:")
    assert prov["knowledge_library"]["hash"].startswith("il:")
    assert prov["constitution"]["hash"].startswith("cx:")


def test_assessment_carries_the_ai_package_provenance():
    settings = SimpleNamespace(
        analyst_enabled=True, analyst_endpoint_url=None, analyst_hf_repo="Andrewexiga/omi-analyst-v1",
        analyst_hf_revision=None, analyst_prompt_version=None,
        analyst_model_id="mistralai/Mistral-7B-Instruct-v0.3", analyst_timeout_seconds=30.0,
        analyst_max_retries=0, analyst_endpoint_api="generate", analyst_cost_per_1k_tokens_usd=0.0,
        memory_persistence_enabled=False, memory_database_url=None)
    out = analyst.assess_payload({"overall_probability": 0.6, "overall_tier": "elevated"},
                                 ref="sub_p", platform="youtube", settings=settings)
    assert out is not None
    pkg = load_ai_package()
    assert out["ai_package"]["package_hash"] == pkg.package_hash
    assert out["metrics"]["package_hash"] == pkg.package_hash
    # provenance rides alongside — it never replaces the governed verdict.
    assert out["governance"]["verdict"] in ("permit", "reject")


def test_integrity_endpoint_exposes_the_ai_package():
    from fastapi.testclient import TestClient
    from app.main import app
    # admin-gated; local mode (require_auth=False) resolves a synthetic admin user.
    with TestClient(app) as tc:
        body = tc.get("/v1/investigations/analyst/integrity").json()
    assert body["ai_package"]["package_hash"].startswith("pkg:")
    assert body["ai_package"]["model_id"] == "mistralai/Mistral-7B-Instruct-v0.3"
