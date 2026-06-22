#!/usr/bin/env python3
"""Tests for OMI_DATASET_DISCOVERY_AND_NORMALIZATION_V1.

numpy/pandas/pyarrow + stdlib. Runnable as:
    python -m pytest ml/corpus/test_omi_corpus.py -q
    python ml/corpus/test_omi_corpus.py
"""
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import zipfile
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
_spec = importlib.util.spec_from_file_location("omi_corpus", _HERE / "omi_corpus.py")
oc = importlib.util.module_from_spec(_spec)
sys.modules["omi_corpus"] = oc
_spec.loader.exec_module(oc)


# --- classification --------------------------------------------------------- #
def test_classify_families():
    assert oc.classify(Path("x.csv"), ["tweetid", "userid", "tweet_text"], "csv", False)[0] == "io_tweets"
    assert oc.classify(Path("x.csv"), ["userid", "following_count"], "csv", False)[0] == "io_users"
    assert oc.classify(Path("x.csv"), ["text", "human_or_ai"], "csv", False)[0] == "ai_text_v1"
    assert oc.classify(Path("x.csv"), ["text_content", "label"], "csv", False)[0] == "ai_text_2026"
    assert oc.classify(Path("x.csv"), ["Tweet_text", "Label"], "csv", False)[0] == "twitterdata"
    assert oc.classify(Path("x.csv"), ["is_fake", "followers"], "csv", False)[0] == "fsm_profile"
    assert oc.classify(Path("x.csv"), ["is_bot_flag"], "csv", False)[0] == "reddit_comment"
    assert oc.classify(Path("x.csv"), ["user_id", "bot_score_english"], "csv", False)[0] == "reference"
    assert oc.classify(Path("real_users.csv"), ["screen_name"], "csv", False)[0] == "userdump"
    assert oc.classify(Path("x.tsv"), ["id", "label"], "tsv", True)[0] == "bot_tsv"
    assert oc.classify(Path("x.csv"), ["foo", "bar"], "csv", False)[0] == "unknown"


# --- label normalization ---------------------------------------------------- #
def test_label_helpers():
    assert oc._auth_human_or_ai("ai") == 1 and oc._auth_human_or_ai("human") == 0
    assert oc._auth_human_or_ai("???") is None
    assert oc._auth_botword("political_Bot") == 1 and oc._auth_botword("human") == 0


def test_converters_emit_unified_records():
    info = oc.FileInfo(dataset="d", path="p.csv", fmt="csv", governance_status="train")
    # fsm: is_fake -> label, numeric kept (incl username feats for fidelity)
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "p.csv"
        p.write_text("followers,username_randomness,is_fake,username\n10,0.9,1,bob\n")
        info.path = str(p)
        recs = list(oc.conv_fsm(p, info, 10))
        r = recs[0]
        assert set(r) == set(oc.RECORD_FIELDS)
        assert r["authenticity_label"] == 1 and r["grain"] == "account"
        nf = json.loads(r["numeric_features_json"])
        assert "username_randomness" in nf and "is_fake" not in nf
    # twitterdata inversion: Label 1 = human -> authenticity 0
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "t.csv"
        p.write_text("Tweet_text,Twitter_Account,Label\nhi,acc,1\nyo,acc2,0\n")
        info.path = str(p)
        recs = list(oc.conv_twitterdata(p, info, 10))
        assert recs[0]["authenticity_label"] == 0 and recs[1]["authenticity_label"] == 1


# --- formats: csv/tsv/json/jsonl/parquet/zip ------------------------------- #
def _corpus(root: Path):
    ds = root / "datasets"
    ds.mkdir(parents=True)
    (ds / "g.csv").write_text("followers,is_fake,username\n10,0,a\n20,1,b\n30,1,c\n")
    (ds / "bots.tsv").write_text("123\tbot\n456\thuman\n")
    (ds / "ai.jsonl").write_text(
        json.dumps({"text": "x", "human_or_ai": "ai"}) + "\n"
        + json.dumps({"text": "y", "human_or_ai": "human"}) + "\n")
    (ds / "items.json").write_text(json.dumps(
        [{"text_content": "a", "label": "human"}, {"text_content": "b", "label": "ai"}]))
    import pandas as pd
    pd.DataFrame({"a": [1, 2]}).to_parquet(ds / "d.parquet")
    with zipfile.ZipFile(ds / "z.zip", "w") as zf:
        zf.writestr("inner.csv", "is_fake,username\n1,zz\n")
    (ds / "bad.json").write_text("{not valid json")
    gov = ds / "manifest.toml"
    gov.write_text(
        '[[file]]\npath="g.csv"\nstatus="train"\nkind="accounts"\n'
        '[[file]]\npath="bots.tsv"\nstatus="validation"\nkind="accounts"\n'
        '[[file]]\npath="ai.jsonl"\nstatus="validation"\nkind="text"\n'
        '[[file]]\npath="items.json"\nstatus="archive"\nkind="text"\n')
    return ds, gov


def test_discover_all_formats():
    with tempfile.TemporaryDirectory() as d:
        ds, gov = _corpus(Path(d))
        g = oc.load_governance(gov)
        infos = oc.discover(ds, g)
        fmts = {i.fmt for i in infos}
        assert {"csv", "tsv", "jsonl", "json", "parquet", "zip"} <= fmts
        byname = {Path(i.path).name: i for i in infos}
        assert byname["g.csv"].family == "fsm_profile" and byname["g.csv"].row_count == 3
        assert byname["bots.tsv"].family == "bot_tsv"
        assert byname["ai.jsonl"].family == "ai_text_v1"
        assert byname["z.zip"].zip_members == ["inner.csv"]
        # invalid json reported unparseable (req 9)
        assert byname["bad.json"].parse_status == "unparseable"


def test_merge_respects_governance_and_grain():
    import pandas as pd
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        ds, gov = _corpus(root)
        g = oc.load_governance(gov)
        infos = oc.discover(ds, g)
        # redirect REPO_ROOT so converters resolve absolute temp paths
        out = root / "merged.parquet"
        merge = oc.build_merged_corpus(infos, out, cap=10)
        df = pd.read_parquet(out)
        assert set(oc.RECORD_FIELDS) == set(df.columns)
        srcs = set(df["dataset"])
        assert "g" in srcs and "bots" in srcs and "ai" in srcs   # train/validation merged
        assert "items" not in srcs                                # archive excluded
        assert {"account", "text"} <= set(df["grain"])
        # archive listed as skipped
        assert any("items.json" in s[0] for s in merge["skipped"])


def test_originals_unchanged():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        ds, gov = _corpus(root)
        src = ds / "g.csv"
        before = (src.read_bytes(), src.stat().st_mtime)
        g = oc.load_governance(gov)
        infos = oc.discover(ds, g)
        oc.build_merged_corpus(infos, root / "m.parquet", cap=10)
        after = (src.read_bytes(), src.stat().st_mtime)
        assert before == after   # read-only: originals untouched


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
