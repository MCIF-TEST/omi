"""Phase P1.2 — the Canonical Package Loader (the ONE runtime package-access layer).

Proves the loader loads + verifies + caches + returns immutable asset bodies, and proves the seven
runtime-contract invariants: the Prompt Builder embeds zero prompt text; every asset originates from
the package; the loader is the only runtime package-access layer (the builder imports nothing else);
GitHub remains the source; GitHub Actions remain the only publish mechanism; Hugging Face remains the
runtime mirror; and the runtime never bypasses the package (verification is fail-closed).
"""
from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest

from app.reasoning.package import load_ai_package
from app.reasoning.package_loader import (
    LoadedPackage,
    PackageIntegrityError,
    load_package,
    reset_package_cache,
)
from app.reasoning.prompt import build_prompt_package
from app.reasoning.prompt import builder as builder_mod
from app.reasoning import package_loader as loader_mod
from app.reasoning.context import build_investigation_context

_REPO_ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(autouse=True)
def _fresh_cache():
    reset_package_cache()
    yield
    reset_package_cache()


def _ctx():
    return build_investigation_context(
        {"overall_probability": 0.6, "overall_tier": "elevated", "video_id": "v1",
         "video": {"commenters": [{"external_id": "a", "handle": "@a", "tier": "high",
                                   "overall_probability": 0.8, "confidence": 0.6,
                                   "signals": [{"name": "temporal", "probability": 0.8, "confidence": 0.7}]}]}},
        ref="slug1", platform="youtube", slug="slug1", kind="video")


# --------------------------------------------------------------------------- #
# Loader behavior — load / verify / cache / immutability
# --------------------------------------------------------------------------- #
def test_loads_all_seven_assets_and_verifies():
    lp = load_package()
    assert isinstance(lp, LoadedPackage)
    # the seven canonical asset bodies are present + non-empty
    assert lp.constitution.strip() and lp.system_prompt.strip() and lp.response_contract.strip()
    assert len(lp.knowledge()) > 0
    assert lp.framework().get("version")
    assert lp.assembly_template().get("system_blocks")
    assert lp.output_schema().get("properties")
    # verification passes and reports the checks it ran
    report = lp.verify()
    assert report["verified"] is True and report["package_hash"] == load_ai_package().package_hash


def test_is_cached_and_immutable():
    lp = load_package()
    assert load_package() is lp                                   # cached (same object)
    with pytest.raises(dataclasses.FrozenInstanceError):
        lp.constitution = "x"                                    # frozen
    k = lp.knowledge(); k.append({"x": 1})
    assert len(lp.knowledge()) == len(k) - 1                     # accessor returns a fresh copy


def test_verify_is_fail_closed_on_drift():
    lp = load_package()
    for tampered_field in ("constitution_hash", "template_hash", "prompt_hash"):
        bad = dataclasses.replace(lp, **{tampered_field: "xx:TAMPERED"})
        with pytest.raises(PackageIntegrityError):
            bad.verify()
    # a bad package is never cached: verify runs on load
    reset_package_cache()
    assert load_package().verify()["verified"] is True


def test_hashes_match_the_package_identity():
    lp = load_package()
    i = load_ai_package()
    h = lp.hashes()
    assert h["prompt_hash"] == i.prompt_hash and h["constitution_hash"] == i.constitution_hash
    assert h["framework_hash"] == i.framework_hash and h["knowledge_hash"] == i.knowledge_hash
    assert h["template_hash"] == i.template_hash and h["contract_hash"] == i.contract_hash
    assert h["package_hash"] == i.package_hash


# --------------------------------------------------------------------------- #
# The seven required proofs
# --------------------------------------------------------------------------- #
def test_proof1_prompt_builder_contains_zero_embedded_prompt_text():
    lp = load_package()
    tmpl = lp.assembly_template()
    src = Path(builder_mod.__file__).read_text(encoding="utf-8")
    banned = (
        [tmpl["response_contract"], tmpl["evidence_preamble"], tmpl["evidence_instruction"]]
        + [b["header"] for b in tmpl["system_blocks"] if b["header"]]
        + [s["header"] for s in tmpl["evidence_sections"]]
    )
    assert not [b for b in banned if b and b in src]


def test_proof2_every_prompt_asset_originates_from_the_package():
    lp = load_package()
    pp = build_prompt_package(_ctx())
    # each system block's content is exactly the loader's asset body
    assert lp.system_prompt in pp.system
    assert lp.constitution in pp.system
    assert lp.response_contract in pp.system
    # nothing in the prompt's framing is builder-authored: every header comes from the asset
    for b in lp.assembly_template()["system_blocks"]:
        if b["header"]:
            assert b["header"] in pp.system
    # the manifest traces every asset hash the loader verified
    for k in ("prompt_hash", "constitution_hash", "framework_hash", "knowledge_hash",
              "template_hash", "contract_hash", "output_schema_hash"):
        assert pp.manifest[k] == getattr(lp, k)


def test_proof3_loader_is_the_only_runtime_package_access_layer():
    """The canonical Prompt Builder must reach assets ONLY through the loader — it may not import any
    package-source module or call the identity/registry/constitution/etc. directly."""
    src = Path(builder_mod.__file__).read_text(encoding="utf-8")
    assert "from app.reasoning.package_loader import" in src
    # Source-module imports + source-only functions. (`assembly_template`/`response_contract`/
    # `knowledge`/`framework` are ALSO loader methods, so they are reached via `lp.` — allowed —
    # and are deliberately not banned here; the import bans below make the source versions
    # unreachable anyway.)
    forbidden = (
        "app.reasoning.prompts", "app.reasoning.knowledge", "app.reasoning.package ",
        "import load_ai_package", "load_ai_package(", "default_registry", "constitution_text",
        "framework_profiles", "default_library",
    )
    leaks = [f for f in forbidden if f in src]
    assert not leaks, f"builder bypasses the loader: {leaks}"


def test_proof4_github_remains_the_source():
    """The loaded bodies are exactly the GitHub source-of-truth modules — the loader reads that
    source, it does not invent or fork a copy."""
    from app.reasoning.prompts import (
        assembly_template, constitution_text, default_registry, response_contract,
    )
    lp = load_package()
    assert lp.constitution == constitution_text()
    assert lp.system_prompt == default_registry().resolve("omi_analyst").template
    assert lp.response_contract == response_contract()
    assert lp.assembly_template() == assembly_template()


def test_proof5_github_actions_remain_the_only_publish_mechanism():
    """The loader loads + validates only — it contains no publish/upload/write path. Publishing is
    the register_hf_model pipeline the GitHub Action runs."""
    lsrc = Path(loader_mod.__file__).read_text(encoding="utf-8").lower()
    for publish_primitive in ("push_to_hub", "hfapi", "upload_file", "upload_folder", ".write_text(",
                              "requests.post", "urlopen("):
        assert publish_primitive not in lsrc
    # the publish pipeline (Action) still validates the manifest offline
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "rhm", _REPO_ROOT / "ml" / "analyst" / "register_hf_model.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    target, files = mod.load_manifest(_REPO_ROOT / "ml" / "analyst" / "hf_repo_manifest.toml")
    ok, _resolved, errors = mod.validate(target, files)
    assert ok, errors


def test_proof6_hugging_face_remains_the_runtime_package():
    """The loaded bodies' hashes equal the committed HF manifests (runtime == the published HF
    package); the drift guards keep GitHub and HF in lockstep."""
    from app.reasoning.prompts.export import (
        KNOWLEDGE_PATH, MANIFEST_PATH, PROMPT_TEMPLATE_PATH,
        knowledge_matches_committed, manifest_matches_committed, prompt_template_matches_committed,
    )
    assert manifest_matches_committed() and knowledge_matches_committed() and prompt_template_matches_committed()
    lp = load_package()
    pm = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    km = json.loads(KNOWLEDGE_PATH.read_text(encoding="utf-8"))
    pt = json.loads(PROMPT_TEMPLATE_PATH.read_text(encoding="utf-8"))
    assert lp.prompt_hash == pm["production_prompt"]["prompt_hash"]
    assert lp.constitution_hash == pm["constitution"]["hash"]
    assert lp.knowledge_hash == km["library_hash"]
    assert lp.template_hash == pt["template_hash"] and lp.contract_hash == pt["response_contract_hash"]


def test_proof7_runtime_never_bypasses_the_package():
    """Fail-closed loading means a drifted/partial package cannot be served, and the builder can only
    obtain assets through the verified loader (proof 3). A verification failure raises rather than
    silently degrading."""
    lp = load_package()
    bad = dataclasses.replace(lp, system_prompt="")  # a partial/empty asset
    with pytest.raises(PackageIntegrityError):
        bad.verify()
    # build_prompt_package obtains its package solely via load_package (default arg path)
    import inspect
    sig = inspect.signature(build_prompt_package)
    assert "loaded" in sig.parameters  # injectable, but defaults to the canonical loader
    pp = build_prompt_package(_ctx())
    assert pp.manifest["package_hash"] == load_ai_package().package_hash


def test_loader_only_loads_no_assembly_no_inference():
    """The loader assembles no prompt and invokes no model."""
    lsrc = Path(loader_mod.__file__).read_text(encoding="utf-8")
    assert "model_providers" not in lsrc and "RemoteReasoning" not in lsrc
    assert "build_prompt_package" not in lsrc and "def build_" not in lsrc.replace("def _build_loaded_package", "")
