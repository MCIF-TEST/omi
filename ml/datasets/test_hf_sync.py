#!/usr/bin/env python3
"""Tests for the dataset sync automation (OMI_DATASET_AUTOMATION_V1).

Stdlib-only. Runnable two ways:
    python -m pytest ml/datasets/test_hf_sync.py -q
    python ml/datasets/test_hf_sync.py
"""
from __future__ import annotations

import importlib.util
import sys
import tempfile
import tomllib
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, _HERE / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


hf_upload = _load("hf_upload")
sync = _load("hf_sync")


def _cfg(**kw):
    base = dict(target_repo="o/r", repo_type="dataset", private=True,
                max_upload_size_mb=25.0,
                manual_review_provenance=["twitter_io_disclosure",
                                          "osome_botometer_repository",
                                          "cresci_botometer_repository"],
                overrides=[])
    base.update(kw)
    return sync.Config(**base)


def _item(**kw):
    base = dict(name="x.csv", gov_path="d/x.csv", source_path="/tmp/x.csv",
                rule_type="file", status="train", classification="TRAIN",
                kind="accounts", provenance="", fmt="csv", exists=True,
                size_mb=1.0, file_count=1)
    base.update(kw)
    return sync.Item(**base)


# --- classification buckets ------------------------------------------------- #
def test_blocked_archive_quarantine():
    for st, cls in [("archive", "ARCHIVE"), ("quarantine", "QUARANTINE")]:
        it = sync.classify(_item(status=st, classification=cls), _cfg())
        assert it.bucket == "blocked" and st in it.reason


def test_manual_review_io():
    it = sync.classify(_item(provenance="twitter_io_disclosure"), _cfg())
    assert it.bucket == "manual_review" and "coordination" in it.reason


def test_manual_review_text():
    it = sync.classify(_item(kind="text", status="validation", classification="EVAL"), _cfg())
    assert it.bucket == "manual_review" and "text" in it.reason


def test_manual_review_reference():
    it = sync.classify(_item(status="reference", classification="EVAL"), _cfg())
    assert it.bucket == "manual_review" and "reference" in it.reason


def test_manual_review_large():
    it = sync.classify(_item(size_mb=999.0, status="validation", classification="EVAL",
                             gov_path="d/big.csv", source_path="/tmp/big.csv"), _cfg())
    assert it.bucket == "manual_review" and "large" in it.reason


def test_manual_review_dir():
    it = sync.classify(_item(rule_type="dir", status="validation", classification="EVAL",
                             provenance="curated_known_good"), _cfg())
    assert it.bucket == "manual_review"


def test_manual_review_no_label():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "x.csv"
        p.write_text("a,b\n1,2\n")
        it = sync.classify(_item(source_path=str(p), gov_path="d/x.csv"), _cfg())
        assert it.bucket == "manual_review" and "no label" in it.reason


def test_uploadable_autodetect_label():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "x.csv"
        p.write_text("a,is_fake\n1,0\n2,1\n")
        it = sync.classify(_item(source_path=str(p), gov_path="d/x.csv"), _cfg())
        assert it.bucket == "uploadable" and it.label_column == "is_fake"
        assert it.target_path == "authenticity/mixed_quality/x.csv"


def test_uploadable_override_label_value_and_target():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "real_users.csv"
        p.write_text("id,name\n1,a\n")
        cfg = _cfg(overrides=[{"match": "real_users.csv", "label_value": "real",
                               "target_path": "authenticity/human_accounts/real_users.csv",
                               "trust_level": "medium"}])
        it = sync.classify(_item(name="real_users.csv", gov_path="d/real_users.csv",
                                 source_path=str(p)), cfg)
        assert it.bucket == "uploadable" and it.label_value == "real"
        assert it.target_path == "authenticity/human_accounts/real_users.csv"


# --- incremental upload logic ---------------------------------------------- #
def test_digests_git_blob_sha1():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "h"
        p.write_bytes(b"hello")
        size, git_sha1, sha256 = sync.digests(p)
        # git hash-object of "hello" (no newline)
        assert git_sha1 == "b6fc4c620b67d95f953a5c1c1230aaab5db5a1b0"
        assert size == 5 and len(sha256) == 64


def test_needs_upload():
    assert sync.needs_upload("g", "s", None) is True
    assert sync.needs_upload("g", "s", {"sha256": "s"}) is False
    assert sync.needs_upload("g", "s", {"blob_id": "g"}) is False
    assert sync.needs_upload("g", "s", {"sha256": "x", "blob_id": "y"}) is True


# --- discovery + generated artifacts (temp governance tree) ----------------- #
def _temp_tree(d: Path) -> Path:
    (d / "train.csv").write_text("a,is_fake\n1,0\n2,1\n")
    (d / "poison.csv").write_text("a,b\n1,2\n")
    (d / "nolabel.csv").write_text("a,b\n1,2\n")
    (d / "io").mkdir()
    (d / "io" / "a.csv").write_text("x\n1\n")
    man = d / "manifest.toml"
    man.write_text(
        "schema_version=2\n"
        '[[file]]\npath="train.csv"\nstatus="train"\nkind="accounts"\n'
        '[[file]]\npath="poison.csv"\nstatus="quarantine"\nkind="accounts"\n'
        '[[file]]\npath="nolabel.csv"\nstatus="validation"\nkind="accounts"\n'
        '[[dir]]\npath="io"\nstatus="validation"\nkind="accounts"\nprovenance="twitter_io_disclosure"\n'
    )
    return man


def test_discover_and_classify_buckets():
    with tempfile.TemporaryDirectory() as d:
        man = _temp_tree(Path(d))
        items = sync.classify_all(sync.discover(man, Path(d)), _cfg())
        by = {i.name: i.bucket for i in items}
        assert by["train.csv"] == "uploadable"
        assert by["poison.csv"] == "blocked"
        assert by["nolabel.csv"] == "manual_review"
        assert by["io"] == "manual_review"


def test_generated_manifest_parses_with_v1_loader():
    with tempfile.TemporaryDirectory() as d:
        man = _temp_tree(Path(d))
        items = sync.classify_all(sync.discover(man, Path(d)), _cfg())
        out = Path(d) / "gen.toml"
        orig = sync.GENERATED_MANIFEST
        try:
            sync.GENERATED_MANIFEST = out
            sync.write_manifest(items, _cfg())
        finally:
            sync.GENERATED_MANIFEST = orig
        data = tomllib.loads(out.read_text())
        assert data["target"]["repo_id"] == "o/r"
        names = [e["name"] for e in data["dataset"]]
        assert names == ["train"]                       # only the uploadable one
        target, entries = hf_upload.load_manifest(out)  # V1 loader accepts it
        assert entries[0].label_column == "is_fake"


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
