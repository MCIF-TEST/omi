#!/usr/bin/env python3
"""Tests for the HF dataset upload pipeline (OMI_DATASET_UPLOAD_V1).

Stdlib-only (no huggingface_hub / pyarrow / pandas needed). Runnable two ways:
    python -m pytest ml/datasets/test_hf_upload.py -q
    python ml/datasets/test_hf_upload.py            # self-contained runner
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("hf_upload", _HERE / "hf_upload.py")
hf = importlib.util.module_from_spec(_spec)
sys.modules["hf_upload"] = hf  # register before exec so @dataclass can resolve hints
_spec.loader.exec_module(hf)


# --- eligibility / governance veto ----------------------------------------- #
def test_eligibility_by_status():
    gov = {"files": {}, "dirs": []}
    for status, expect in [("train", True), ("eval", True),
                           ("archive", False), ("quarantine", False)]:
        e = hf.DatasetEntry(name="x", source_path="/tmp/x.csv", fmt="csv", status=status)
        ok, _ = hf.eligibility(e, gov, ("train", "eval"))
        assert ok is expect, f"{status} -> {ok}"


def test_governance_veto_overrides_train():
    gov = {"files": {"Datasets/p.csv": "quarantine"}, "dirs": []}
    e = hf.DatasetEntry(name="x", source_path="datasets/Datasets/p.csv", fmt="csv", status="train")
    ok, reason = hf.eligibility(e, gov, ("train", "eval"))
    assert not ok and "veto" in reason


def test_governance_dir_prefix_veto():
    gov = {"files": {}, "dirs": [("Datasets/Arc", "archive")]}
    e = hf.DatasetEntry(name="x", source_path="datasets/Datasets/Arc/sub/f.csv",
                        fmt="csv", status="train")
    ok, _ = hf.eligibility(e, gov, ("train", "eval"))
    assert not ok


# --- validation: csv / json / errors --------------------------------------- #
def test_validate_csv():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "x.csv"
        p.write_text("a,is_fake\n1,0\n2,1\n3,1\n")
        e = hf.DatasetEntry(name="x", source_path=str(p), fmt="csv",
                            status="train", label_column="is_fake")
        v = hf.validate_dataset(e)
        assert v.ok and v.row_count == 3
        assert set(v.columns) == {"a", "is_fake"} and v.labels == {"0": 1, "1": 2}


def test_validate_json():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "x.json"
        p.write_text(json.dumps([{"a": 1, "label": "bot"},
                                 {"a": 2, "label": "human"},
                                 {"a": 3, "label": "bot"}]))
        e = hf.DatasetEntry(name="x", source_path=str(p), fmt="json",
                            status="eval", label_column="label")
        v = hf.validate_dataset(e)
        assert v.ok and v.row_count == 3 and v.labels == {"bot": 2, "human": 1}


def test_label_value_constant():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "x.csv"
        p.write_text("a,b\n1,2\n3,4\n")
        e = hf.DatasetEntry(name="x", source_path=str(p), fmt="csv",
                            status="train", label_value="real")
        v = hf.validate_dataset(e)
        assert v.ok and v.labels == {"real": 2}


def test_missing_label_column_fails():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "x.csv"
        p.write_text("a,b\n1,2\n")
        e = hf.DatasetEntry(name="x", source_path=str(p), fmt="csv",
                            status="eval", label_column="is_fake")
        v = hf.validate_dataset(e)
        assert not v.ok and "label_column" in v.error


def test_train_needs_label():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "x.csv"
        p.write_text("a,b\n1,2\n")
        e = hf.DatasetEntry(name="x", source_path=str(p), fmt="csv", status="train")
        v = hf.validate_dataset(e)
        assert not v.ok and "label" in v.error


def test_missing_file_fails():
    e = hf.DatasetEntry(name="x", source_path="/tmp/_omi_nope_.csv", fmt="csv",
                        status="train", label_value="x")
    v = hf.validate_dataset(e)
    assert not v.ok and "not found" in v.error


# --- dataset card ----------------------------------------------------------- #
def test_card_contains_fields():
    v = hf.Validation(ok=True, row_count=3, columns=["a", "is_fake"],
                      dtypes={"a": "int", "is_fake": "int"}, labels={"0": 1, "1": 2})
    e = hf.DatasetEntry(name="ds1", source_path="/tmp/x.csv", fmt="csv", status="train",
                        label_type="binary_authenticity", trust_level="high",
                        target_path="authenticity/x.csv", intended_use="train", notes="caveat")
    card = hf.generate_card({"pretty_name": "OMI Authenticity Dataset", "repo_id": "o/r"},
                            [(e, v)])
    for token in ["OMI Authenticity Dataset", "ds1", "binary_authenticity", "high",
                  "rows:** 3", "never uploaded", "not verdicts", "authenticity/x.csv"]:
        assert token in card, token


# --- integration via main() (no network) ----------------------------------- #
def _temp_manifest(d: Path, valid: bool = True) -> Path:
    (d / "x.csv").write_text("a,is_fake\n1,0\n2,1\n")
    label_col = "is_fake" if valid else "missing_col"
    man = d / "man.toml"
    man.write_text(
        "schema_version=1\n"
        "[target]\n"
        'repo_id="o/r"\n'
        'repo_type="dataset"\n'
        'governance_manifest="/tmp/_omi_no_gov_.toml"\n'
        'pretty_name="OMI Authenticity Dataset"\n'
        "[[dataset]]\n"
        'name="x"\n'
        f'source_path="{(d / "x.csv").as_posix()}"\n'
        'format="csv"\n'
        'label_type="binary"\n'
        f'label_column="{label_col}"\n'
        'status="train"\n'
        'target_path="authenticity/x.csv"\n'
        "[[dataset]]\n"
        'name="poison"\n'
        f'source_path="{(d / "x.csv").as_posix()}"\n'
        'format="csv"\n'
        'status="quarantine"\n'
        'target_path="DO_NOT/x.csv"\n'
    )
    return man


def test_dry_run_excludes_quarantine_no_network():
    with tempfile.TemporaryDirectory() as d:
        man = _temp_manifest(Path(d), valid=True)
        assert hf.main(["--manifest", str(man), "--dry-run"]) == 0


def test_invalid_eligible_fails():
    with tempfile.TemporaryDirectory() as d:
        man = _temp_manifest(Path(d), valid=False)
        assert hf.main(["--manifest", str(man), "--validate"]) == 1


def test_upload_without_token_fails_no_network():
    saved = {k: os.environ.pop(k, None) for k in ("HF_TOKEN", "HUGGINGFACE_HUB_TOKEN")}
    try:
        with tempfile.TemporaryDirectory() as d:
            man = _temp_manifest(Path(d), valid=True)
            assert hf.main(["--manifest", str(man), "--upload"]) == 1
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
