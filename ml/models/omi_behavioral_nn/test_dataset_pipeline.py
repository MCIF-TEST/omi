#!/usr/bin/env python3
"""Tests for the OmiBehavioralNet dataset pipeline (V1 dataset builder).

Torch-free (numpy + pandas + pyarrow). Runnable as:
    python -m pytest ml/models/omi_behavioral_nn/test_dataset_pipeline.py -q
    python ml/models/omi_behavioral_nn/test_dataset_pipeline.py
"""
from __future__ import annotations

import importlib.util
import sys
import tempfile
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

_spec = importlib.util.spec_from_file_location("dataset_builder", _HERE / "dataset_builder.py")
db = importlib.util.module_from_spec(_spec)
sys.modules["dataset_builder"] = db
_spec.loader.exec_module(db)


# --- helpers --------------------------------------------------------------- #
def test_numeric_helpers():
    assert db._to01(1.0) == 1.0 and db._to01(-0.0) == 0.0 and db._to01(None) is None
    v = db._log_norm(100.0, db._FOLLOW_CAP)
    assert 0.0 <= v <= 1.0
    assert db._log_norm(None, 10) is None
    assert abs(db._ratio_norm(1.0) - 0.5) < 1e-9   # log10(1)=0 -> mid of [-3,3]
    assert db._ratio_norm(0.0) is None


def test_age_days():
    d = db._age_days("Mon Nov 07 11:00:27 +0000 2011", "")  # updated empty -> snapshot
    assert d and d > 0
    assert db._age_days("", "") is None


def test_adapt_global_maps_and_skips_empty():
    row = {"followers": "431", "following": "679", "follower_following_ratio": "0.63",
           "account_age_days": "", "posts_per_day": "0.2", "caption_similarity_score": "",
           "content_similarity_score": "0.58", "verified": "1.0", "posts": "1000",
           "is_fake": "0", "username": "abc"}
    f = db._adapt_global(row)
    assert "meta_verified" in f and f["meta_verified"] == 1.0
    assert "fp_top_cluster_mass" in f and 0.0 <= f["fp_top_cluster_mass"] <= 1.0
    assert "meta_log_account_age_days" not in f   # empty -> skipped
    assert "fp_mean_cosine" not in f               # empty -> skipped
    assert all(k in db.FEATURE_NAMES for k in f)   # only schema features emitted
    assert "username" not in f and "username_randomness" not in f  # shortcut excluded


def test_label_resolution():
    s_col = db.Source("g", "datasets/g.csv", "global", "column:is_fake", "username")
    assert db._resolve_label(s_col, {"is_fake": "1"}) == 1
    assert db._resolve_label(s_col, {"is_fake": ""}) is None
    s_const = db.Source("u", "datasets/u.csv", "userdump", "const:0", "screen_name")
    assert db._resolve_label(s_const, {}) == 0


def test_username_columns_not_in_schema():
    for col in db.USERNAME_SHORTCUT_COLUMNS:
        assert col not in db.FEATURE_NAMES


# --- end-to-end build on a temp corpus ------------------------------------- #
def _make_corpus(root: Path):
    ds = root / "datasets"
    ds.mkdir(parents=True)
    g = ["followers,following,follower_following_ratio,account_age_days,posts_per_day,"
         "caption_similarity_score,content_similarity_score,verified,posts,is_fake,username"]
    for i in range(20):
        g.append(f"{100+i},{50+i},0.{5+i%4},{1000+i},0.2,0.6,0.5,{i%2},{500+i},{i%2},user{i}")
    (ds / "g.csv").write_text("\n".join(g) + "\n")
    u = ["followers_count,friends_count,verified,statuses_count,created_at,updated,screen_name"]
    for i in range(10):
        u.append(f"{10+i}.0,{20+i}.0,0.0,{200+i}.0,,,real{i}")
    (ds / "u.csv").write_text("\n".join(u) + "\n")
    gov = ds / "manifest.toml"
    gov.write_text('schema_version=2\n'
                   '[[file]]\npath="g.csv"\nstatus="train"\nkind="accounts"\n'
                   '[[file]]\npath="u.csv"\nstatus="train"\nkind="accounts"\n')
    return gov


def _sources():
    return [
        db.Source("g_set", "datasets/g.csv", "global", "column:is_fake", "username"),
        db.Source("u_set", "datasets/u.csv", "userdump", "const:0", "screen_name"),
    ]


def test_build_dataset_end_to_end():
    import pandas as pd
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        gov = _make_corpus(root)
        out = root / "out"
        rep = root / "dataset_report.md"
        summary = db.build_dataset(sources=_sources(), repo_root=root, out_dir=out,
                                   report_path=rep, governance_path=gov, seed=0)
        # parquet files exist and sum to total
        rows = 0
        for name in ("train", "validation", "test"):
            p = pd.read_parquet(out / f"{name}.parquet")
            assert db.AUTH_LABEL in p.columns
            assert all(fn in p.columns for fn in db.FEATURE_NAMES)
            rows += len(p)
        assert rows == summary["total"]
        # both classes present overall
        assert summary["label_balance"].get(0, 0) > 0 and summary["label_balance"].get(1, 0) > 0
        # leakage: no identity / feature-vector spans splits
        assert summary["leakage"]["cross_split_identity_overlap"] == 0
        assert summary["leakage"]["cross_split_feature_hash_overlap"] == 0
        # report content
        text = rep.read_text()
        for token in ["Source counts", "class balance", "Duplicates",
                      "Missing values", "Leakage analysis", "detectors | 16 | 0"]:
            assert token in text, token


def test_build_dataset_dedup():
    import pandas as pd
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        ds = root / "datasets"
        ds.mkdir(parents=True)
        # three identical global rows -> 2 exact-duplicate vectors removed
        hdr = ("followers,following,follower_following_ratio,account_age_days,posts_per_day,"
               "caption_similarity_score,content_similarity_score,verified,posts,is_fake,username")
        rows = [hdr] + [f"100,50,0.5,1000,0.2,0.6,0.5,0,500,0,user{i}" for i in range(3)]
        (ds / "g.csv").write_text("\n".join(rows) + "\n")
        gov = ds / "manifest.toml"
        gov.write_text('[[file]]\npath="g.csv"\nstatus="train"\nkind="accounts"\n')
        out = root / "out"
        summary = db.build_dataset(sources=[db.Source("g", "datasets/g.csv", "global",
                                                      "column:is_fake", "username")],
                                   repo_root=root, out_dir=out, report_path=root / "r.md",
                                   governance_path=gov, seed=0)
        assert summary["dup_removed"] == 2 and summary["total"] == 1


def test_governance_veto_blocks_ingest():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        ds = root / "datasets"
        ds.mkdir(parents=True)
        (ds / "p.csv").write_text("followers,is_fake,username\n10,1,a\n")
        gov = ds / "manifest.toml"
        gov.write_text('[[file]]\npath="p.csv"\nstatus="quarantine"\nkind="accounts"\n')
        try:
            db.build_dataset(sources=[db.Source("p", "datasets/p.csv", "global",
                                                "column:is_fake", "username")],
                             repo_root=root, out_dir=root / "o", report_path=root / "r.md",
                             governance_path=gov)
            raise AssertionError("should refuse quarantined source")
        except SystemExit:
            pass


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
