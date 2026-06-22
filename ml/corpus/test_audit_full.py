#!/usr/bin/env python3
"""Tests for the full-scan auditor (ml/corpus/audit_full.py).

    python -m pytest ml/corpus/test_audit_full.py -q
    python ml/corpus/test_audit_full.py
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
_spec = importlib.util.spec_from_file_location("audit_full", _HERE / "audit_full.py")
af = importlib.util.module_from_spec(_spec)
sys.modules["audit_full"] = af
_spec.loader.exec_module(af)


def test_semantic():
    assert af.oc_audit_semantic("io_disclosure", 1) == "state_io"
    assert af.oc_audit_semantic("column:is_fake", 1) == "fake"
    assert af.oc_audit_semantic("filename", 0) == "authentic"
    assert af.oc_audit_semantic("column:label", 1) == "ai_generated"
    assert af.oc_audit_semantic("tsv_label", 0) == "human"
    assert af.oc_audit_semantic("none", None) == "unknown"


def test_norm_text():
    a = af._norm_text("RT @bob check https://t.co/x THIS  out")
    assert "@bob" not in a and "https" not in a and not a.startswith("rt ")
    # two formatting variants normalize equal (near-dup)
    assert af._norm_text("Hello   World") == af._norm_text("hello world")


def test_parse_dt_ok():
    assert af._parse_dt_ok("2020-04-19 05:53")     # IO tweet_time
    assert af._parse_dt_ok("27-11-2016 06:15")     # TwitterData
    assert af._parse_dt_ok("2020-01-11")           # IO account_creation_date
    assert not af._parse_dt_ok("not a date")


def _rec(**kw):
    base = dict(record_id="r", dataset="d", source_path="p", domain="authenticity",
                grain="account", text=None, author_id="a1", created_at="2020-01-11",
                lang=None, authenticity_label=1, label_raw="1", label_source="column:is_fake",
                numeric_features_json='{"followers": 5.0}', governance_status="train",
                schema_version=1)
    base.update(kw)
    return base


def test_update_accumulates_and_dedups():
    acc = af.Acc()
    af._update(acc, _rec(record_id="r1"))
    af._update(acc, _rec(record_id="r2"))          # identical content -> exact dup
    af._update(acc, _rec(record_id="r3", author_id="a2", numeric_features_json='{"followers": 9.0}'))
    assert acc.total == 3
    assert acc.exact_dups == 1                       # r2 duplicates r1
    assert acc.by_semantic["fake"] == 3
    assert acc.num_n["followers"] == 3 and acc.num_neg["followers"] == 0
    assert len(acc.author_counts) == 2 and acc.author_counts["a1"] == 2


def test_update_near_dup_text():
    acc = af.Acc()
    af._update(acc, _rec(record_id="t1", grain="tweet", text="Hello World",
                         numeric_features_json=None))
    af._update(acc, _rec(record_id="t2", grain="tweet", text="hello   world",
                         author_id="a9", numeric_features_json=None))
    assert acc.near_dups == 1                        # normalized text matches


def test_stats_shape():
    acc = af.Acc()
    for i in range(5):
        af._update(acc, _rec(record_id=f"r{i}", author_id=f"a{i}",
                             numeric_features_json='{"followers": %d.0}' % i))
    s = af._stats(acc)
    for key in ("total_rows_full_scan", "authenticity", "semantic_labels", "imbalance",
                "feature_completeness_pct", "numeric_features", "duplicates", "quality",
                "cross_dataset_leakage"):
        assert key in s
    assert s["total_rows_full_scan"] == 5


def test_quantiles_and_hist():
    q = af._quantiles(list(range(101)))
    assert q["median"] == 50.0 and q["p25"] == 25.0 and q["p75"] == 75.0
    assert q["outlier_pct_of_sample"] == 0.0 and q["sample_n"] == 101
    assert af._quantiles([]) == {}
    assert af._ascii_hist([]) == ["(no data)"]
    assert "all = 5" in af._ascii_hist([5, 5, 5])[0]
    assert len(af._ascii_hist([1, 1, 2, 3, 8], bins=5)) == 5


def test_schema_inconsistencies():
    from types import SimpleNamespace as NS
    infos = [
        NS(family="io_users", columns=["userid", "follower_count"], path="a"),
        NS(family="io_users", columns=["userid", "follower_count", "extra"], path="b"),
        NS(family="cc", columns=["userId", "followerCount"], path="c"),       # casing variant
        NS(family="sc", columns=["userid", "follower_count"], path="d"),       # of c
    ]
    res = af.schema_inconsistencies(infos)
    assert res["family_variants"]["io_users"]["distinct_schemas"] == 2
    assert len(res["casing_variants"]) >= 1


def test_cross_dataset_and_domain_leakage():
    acc = af.Acc()
    # identical content in two different datasets, same domain -> cross-dataset exact dup
    af._update(acc, _rec(record_id="1", dataset="d1", domain="authenticity",
                         author_id="a", numeric_features_json=None))
    af._update(acc, _rec(record_id="2", dataset="d2", domain="authenticity",
                         author_id="a", numeric_features_json=None))
    assert acc.exact_cross_dataset >= 1
    # same author later appears in a different domain -> cross-domain author (leakage signal)
    af._update(acc, _rec(record_id="3", dataset="d3", domain="bot", grain="tweet",
                         author_id="a", text="hi", numeric_features_json=None,
                         label_source="tsv_label"))
    assert acc.author_cross_domain >= 1


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
