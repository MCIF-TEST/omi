#!/usr/bin/env python3
"""Tests for OMI_CORPUS_AUDIT_V1 (ml/corpus/audit.py). Read-only stat helpers.

    python -m pytest ml/corpus/test_audit.py -q
    python ml/corpus/test_audit.py
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
_spec = importlib.util.spec_from_file_location("audit", _HERE / "audit.py")
au = importlib.util.module_from_spec(_spec)
sys.modules["audit"] = au
_spec.loader.exec_module(au)


def test_semantic_label():
    assert au.semantic_label("io_disclosure", 1) == "state_io"
    assert au.semantic_label("column:is_fake", 1) == "fake"
    assert au.semantic_label("column:is_fake", 0) == "authentic"
    assert au.semantic_label("filename", 0) == "authentic"
    assert au.semantic_label("column:human_or_ai", 1) == "ai_generated"
    assert au.semantic_label("column:human_or_ai", 0) == "human"
    assert au.semantic_label("tsv_label", 1) == "bot"
    assert au.semantic_label("column:is_bot_flag", 0) == "human"
    assert au.semantic_label("none", None) == "unknown"
    assert au.semantic_label("column:is_fake", np.nan) == "unknown"


def _df():
    rows = []
    # 2 io tweets (same author -> author repetition), 2 fsm (fake/authentic), 1 reference null
    rows.append(dict(record_id="a", dataset="io", source_path="p", domain="coordination",
                     grain="tweet", text="t1", author_id="u1", created_at=None, lang="en",
                     authenticity_label=1.0, label_raw="state_io", label_source="io_disclosure",
                     numeric_features_json=None, governance_status="validation", schema_version=1))
    rows.append(dict(record_id="b", dataset="io", source_path="p", domain="coordination",
                     grain="tweet", text="t2", author_id="u1", created_at=None, lang="en",
                     authenticity_label=1.0, label_raw="state_io", label_source="io_disclosure",
                     numeric_features_json=None, governance_status="validation", schema_version=1))
    rows.append(dict(record_id="c", dataset="fsm", source_path="p", domain="authenticity",
                     grain="account", text=None, author_id="x", created_at=None, lang=None,
                     authenticity_label=1.0, label_raw="1", label_source="column:is_fake",
                     numeric_features_json='{"followers": 1.0, "username_randomness": 0.9}',
                     governance_status="train", schema_version=1))
    rows.append(dict(record_id="d", dataset="fsm", source_path="p", domain="authenticity",
                     grain="account", text=None, author_id="y", created_at=None, lang=None,
                     authenticity_label=0.0, label_raw="0", label_source="column:is_fake",
                     numeric_features_json='{"followers": 2.0}',
                     governance_status="train", schema_version=1))
    rows.append(dict(record_id="e", dataset="ref", source_path="p", domain="reference",
                     grain="account", text=None, author_id="z", created_at=None, lang=None,
                     authenticity_label=np.nan, label_raw=None, label_source="none",
                     numeric_features_json='{"bot_score_english": 0.3}',
                     governance_status="reference", schema_version=1))
    return pd.DataFrame(rows)


def test_compute_stats():
    s = au.compute_stats(_df())
    assert s["total_rows"] == 5
    assert s["authenticity_distribution"] == {"authentic(0)": 1, "inauthentic(1)": 3,
                                              "unknown(null)": 1}
    assert s["requested_buckets"]["fake"] == 1 and s["requested_buckets"]["authentic"] == 1
    assert s["additional_buckets"]["state_io"] == 2
    # dataset contribution
    contrib = {c["dataset"]: c["rows"] for c in s["dataset_contribution"]}
    assert contrib["io"] == 2 and contrib["fsm"] == 2 and contrib["ref"] == 1
    # author repetition: u1 twice
    assert s["duplicates"]["max_rows_single_author"] == 2
    assert s["duplicates"]["distinct_authors"] == 4
    # imbalance excl-IO: 1 pos (fsm fake) / 1 neg (fsm authentic)
    assert s["class_imbalance"]["excluding_io"]["positive"] == 1
    assert s["class_imbalance"]["excluding_io"]["negative"] == 1
    # username shortcut detected in 1 row
    assert s["username_shortcut_rows"] == 1
    # numeric key frequency picks up followers (2 rows)
    assert s["numeric_key_frequency"]["followers"]["rows"] == 2


def test_report_renders():
    s = au.compute_stats(_df())
    md = au.render_report(s)
    for token in ["Total rows", "Label distribution", "Dataset contribution",
                  "Feature availability", "Duplicate analysis", "Class imbalance",
                  "EXCLUDE before training", "Recommendation"]:
        assert token in md, token


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
