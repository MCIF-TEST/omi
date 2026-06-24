#!/usr/bin/env python3
"""Tests for the HF Analyst model registration pipeline (OMI_ANALYST_MODEL_IMPORT_V1).

Stdlib-only (no huggingface_hub needed). Also acts as an integration check that the
real ml/analyst/hf_repo_manifest.toml + staged files validate. Runnable two ways:
    python -m pytest ml/analyst/test_register_hf_model.py -q
    python ml/analyst/test_register_hf_model.py            # self-contained runner
"""
from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("register_hf_model", _HERE / "register_hf_model.py")
reg = importlib.util.module_from_spec(_spec)
sys.modules["register_hf_model"] = reg
_spec.loader.exec_module(reg)

_REAL_MANIFEST = reg.REPO_ROOT / "ml/analyst/hf_repo_manifest.toml"
_BASE_MODEL = "Qwen/Qwen3-4B-Thinking-2507-FP8"


# --- frontmatter parsing ---------------------------------------------------- #
def test_parse_frontmatter_scalar():
    fm = reg.parse_frontmatter("---\nlicense: apache-2.0\nbase_model: Qwen/X\n---\nbody")
    assert fm["license"] == "apache-2.0" and fm["base_model"] == "Qwen/X"


def test_parse_frontmatter_list_value():
    fm = reg.parse_frontmatter("---\nbase_model:\n- Qwen/X\n- Qwen/Y\n---\n")
    assert fm["base_model"] == "Qwen/X"  # first list item


def test_parse_frontmatter_none_without_block():
    assert reg.parse_frontmatter("# no frontmatter here") == {}


# --- the REAL manifest validates (integration) ------------------------------ #
def test_real_manifest_validates():
    target, files = reg.load_manifest(_REAL_MANIFEST)
    assert target["repo_id"] == "Andrewexiga/omi-analyst-v1"
    assert target["base_model"] == _BASE_MODEL
    ok, resolved, errors = reg.validate(target, files)
    assert ok, f"real manifest failed validation: {errors}"
    # every declared file resolved, and the card + schema + config are present
    paths = {dst for _s, dst, _k in resolved}
    for expected in ("README.md", "config/analyst_config.json", "base/BASE_MODEL.md",
                     "prompts/analyst_system_prompt_v1.md",
                     "schema/analyst_response_schema.json"):
        assert expected in paths, f"missing {expected} in {paths}"


def test_real_card_declares_base_model():
    target, files = reg.load_manifest(_REAL_MANIFEST)
    card = next(f for f in files if f.get("kind") == "model_card")
    fm = reg.parse_frontmatter((reg.REPO_ROOT / card["source"]).read_text(encoding="utf-8"))
    assert fm.get("base_model") == _BASE_MODEL
    assert fm.get("license") == "apache-2.0"


# --- validation failure modes (synthetic) ----------------------------------- #
def _write(d: Path, rel: str, text: str) -> None:
    p = d / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def test_missing_source_fails():
    target = {"repo_id": "o/r", "repo_type": "model", "base_model": _BASE_MODEL}
    files = [{"source": "ml/analyst/__does_not_exist__.md", "path_in_repo": "README.md",
              "kind": "model_card"}]
    ok, _resolved, errors = reg.validate(target, files)
    assert not ok and any("source not found" in e for e in errors)


def test_base_model_mismatch_fails(tmp_path_factory=None):
    # Point REPO_ROOT at a temp tree with a card whose base_model disagrees.
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        _write(root, "card.md", "---\nlicense: apache-2.0\nbase_model: Qwen/WRONG\n---\n")
        saved = reg.REPO_ROOT
        try:
            reg.REPO_ROOT = root
            target = {"repo_id": "o/r", "repo_type": "model", "base_model": _BASE_MODEL}
            files = [{"source": "card.md", "path_in_repo": "README.md", "kind": "model_card"}]
            ok, _resolved, errors = reg.validate(target, files)
            assert not ok and any("base_model mismatch" in e for e in errors)
        finally:
            reg.REPO_ROOT = saved


def test_invalid_json_fails():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        _write(root, "card.md", "---\nlicense: apache-2.0\nbase_model: %s\n---\n" % _BASE_MODEL)
        _write(root, "bad.json", "{ not valid json ")
        saved = reg.REPO_ROOT
        try:
            reg.REPO_ROOT = root
            target = {"repo_id": "o/r", "repo_type": "model", "base_model": _BASE_MODEL}
            files = [
                {"source": "card.md", "path_in_repo": "README.md", "kind": "model_card"},
                {"source": "bad.json", "path_in_repo": "config/x.json", "kind": "config"},
            ]
            ok, _resolved, errors = reg.validate(target, files)
            assert not ok and any("invalid JSON" in e for e in errors)
        finally:
            reg.REPO_ROOT = saved


# --- CLI integration (no network) ------------------------------------------- #
def test_main_validate_real_ok():
    assert reg.main(["--manifest", str(_REAL_MANIFEST), "--validate"]) == 0


def test_main_dry_run_real_ok():
    assert reg.main(["--manifest", str(_REAL_MANIFEST), "--dry-run"]) == 0


def test_upload_without_token_fails_no_network():
    saved = {k: os.environ.pop(k, None) for k in ("HF_TOKEN", "HUGGINGFACE_HUB_TOKEN")}
    try:
        assert reg.main(["--manifest", str(_REAL_MANIFEST), "--upload"]) == 1
    finally:
        for k, val in saved.items():
            if val is not None:
                os.environ[k] = val


def _run_all() -> bool:
    tests = [v for k, v in sorted(globals().items())
             if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in tests:
        try:
            fn()
            print(f"PASS {fn.__name__}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"FAIL {fn.__name__}: {exc}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    return failed == 0


if __name__ == "__main__":
    sys.exit(0 if _run_all() else 1)
