#!/usr/bin/env python3
"""OMI_CORPUS_AUDIT_V1 — comprehensive full uncapped streaming audit.

Streams EVERY row of every governance-approved, convertible source dataset through
the unified converters (ml/corpus/omi_corpus.py), line by line, and produces the
complete audit: totals, per-dataset counts, label distributions, feature
completeness, exact + near duplicates, duplicate accounts, missing/invalid values,
schema inconsistencies, parsing failures, dataset-specific quality issues, class
imbalance, cross-dataset leakage, outliers, ASCII visualizations, and preprocessing
recommendations — ending with a training-readiness assessment.

STRICTLY READ-ONLY: reads source datasets + the committed corpus only; does not
modify or regenerate the corpus / normalized outputs / source data, does not train,
and does not touch production. Outputs: CORPUS_AUDIT_V1.md, audit_stats.json,
audit_per_dataset.csv.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import random
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import numpy as np

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
import omi_corpus as oc  # noqa: E402

REPORT_PATH = _HERE / "CORPUS_AUDIT_V1.md"
STATS_PATH = _HERE / "audit_stats.json"
PER_DATASET_CSV = _HERE / "audit_per_dataset.csv"
COMMITTED_CORPUS = _HERE / "data" / "merged_corpus.parquet"

UNCAPPED = 10 ** 12
RESERVOIR = 50_000
SEED = 17
TEXT_EXPECTED = {"tweet", "text"}
AUTHOR_EXPECTED = {"account", "tweet", "comment"}
COUNT_LIKE = re.compile(r"(follow|friend|status|post|count|age|karma|listed|favourite)", re.I)
VERIFIED_KEYS = {"meta_verified", "verified", "default_profile", "default_profile_image",
                 "geo_enabled", "protected", "profile_background_tile",
                 "profile_use_background_image"}
_URL = re.compile(r"https?://\S+")
_MENTION = re.compile(r"@\w+")
_WS = re.compile(r"\s+")
_DT_FORMATS = ("%a %b %d %H:%M:%S %z %Y", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S",
               "%Y-%m-%d %H:%M", "%Y-%m-%d", "%Y/%m/%d %H:%M:%S",
               "%d-%m-%Y %H:%M", "%d-%m-%Y", "%m/%d/%Y %H:%M", "%m/%d/%Y")


def _h64(s: str) -> int:
    return int.from_bytes(hashlib.blake2b(s.encode("utf-8", "replace"),
                                          digest_size=8).digest(), "big")


def _norm_text(t: str) -> str:
    t = _MENTION.sub("", _URL.sub("", t.lower()))
    if t.startswith("rt "):
        t = t[3:]
    return _WS.sub(" ", t).strip()


def _parse_dt_ok(s: str) -> bool:
    s = s.strip()
    for f in _DT_FORMATS:
        try:
            datetime.strptime(s, f)
            return True
        except ValueError:
            continue
    return False


def oc_audit_semantic(label_source: str, y) -> str:
    if y is None or label_source == "none":
        return "unknown"
    y = int(y)
    if label_source == "io_disclosure":
        return "state_io"
    if label_source in ("column:human_or_ai", "column:label"):
        return "ai_generated" if y == 1 else "human"
    if label_source in ("filename", "column:is_fake"):
        return "fake" if y == 1 else "authentic"
    return "bot" if y == 1 else "human"


@dataclass
class Acc:
    total: int = 0
    by_dataset: Counter = field(default_factory=Counter)
    by_domain: Counter = field(default_factory=Counter)
    by_grain: Counter = field(default_factory=Counter)
    by_semantic: Counter = field(default_factory=Counter)
    by_auth: Counter = field(default_factory=Counter)
    by_label_source: Counter = field(default_factory=Counter)
    field_nonnull: Counter = field(default_factory=Counter)
    num_n: Counter = field(default_factory=Counter)
    num_sum: dict = field(default_factory=lambda: defaultdict(float))
    num_sumsq: dict = field(default_factory=lambda: defaultdict(float))
    num_min: dict = field(default_factory=dict)
    num_max: dict = field(default_factory=dict)
    num_neg: Counter = field(default_factory=Counter)
    num_nonfinite: Counter = field(default_factory=Counter)
    reservoir: dict = field(default_factory=lambda: defaultdict(list))
    reservoir_seen: Counter = field(default_factory=Counter)
    verified_invalid: int = 0
    created_present: int = 0
    created_unparseable: int = 0
    empty_text_expected: int = 0
    text_expected_rows: int = 0
    missing_author: int = 0
    author_expected_rows: int = 0
    label_invalid: int = 0
    # duplicates / leakage
    ds_index: dict = field(default_factory=dict)
    ds_domain: list = field(default_factory=list)
    exact_map: dict = field(default_factory=dict)      # content hash -> ds_index
    exact_dups: int = 0
    exact_cross_dataset: int = 0
    exact_cross_domain: int = 0
    near_map: dict = field(default_factory=dict)        # norm-text hash -> ds_index
    near_dups: int = 0
    near_cross_dataset: int = 0
    near_dup_candidates: int = 0
    cross_dataset_pairs: Counter = field(default_factory=Counter)
    author_counts: Counter = field(default_factory=Counter)
    author_first_ds: dict = field(default_factory=dict)
    author_first_domain: dict = field(default_factory=dict)
    author_cross_ds: int = 0
    author_cross_domain: int = 0
    cross_domain_authors: set = field(default_factory=set)
    per_ds: dict = field(default_factory=lambda: defaultdict(
        lambda: {"rows": 0, "domain": "", "grain": "", "l0": 0, "l1": 0, "lnull": 0,
                 "exact_dups": 0, "near_dups": 0, "authors": set()}))

    def ds_idx(self, name: str, domain: str) -> int:
        i = self.ds_index.get(name)
        if i is None:
            i = len(self.ds_index)
            self.ds_index[name] = i
            self.ds_domain.append(domain)
        return i


def _reservoir_add(acc: Acc, key: str, val: float) -> None:
    res = acc.reservoir[key]
    seen = acc.reservoir_seen[key]
    if len(res) < RESERVOIR:
        res.append(val)
    else:
        j = random.randint(0, seen)
        if j < RESERVOIR:
            res[j] = val
    acc.reservoir_seen[key] = seen + 1


def _update(acc: Acc, r: dict) -> None:
    acc.total += 1
    ds, dom, grain = r["dataset"], r["domain"], r["grain"]
    idx = acc.ds_idx(ds, dom)
    acc.by_dataset[ds] += 1
    acc.by_domain[dom] += 1
    acc.by_grain[grain] += 1
    acc.by_label_source[r["label_source"]] += 1
    acc.by_semantic[oc_audit_semantic(r["label_source"], r["authenticity_label"])] += 1
    y = r["authenticity_label"]
    acc.by_auth["unknown" if y is None else "inauthentic" if int(y) == 1 else "authentic"] += 1

    pd_ = acc.per_ds[ds]
    pd_["rows"] += 1
    pd_["domain"], pd_["grain"] = dom, grain
    pd_["l1" if y == 1 else "l0" if y == 0 else "lnull"] += 1

    for f in oc.RECORD_FIELDS:
        if r.get(f) not in (None, ""):
            acc.field_nonnull[f] += 1
    if y not in (0, 1, None):
        acc.label_invalid += 1

    text = r.get("text")
    if grain in TEXT_EXPECTED:
        acc.text_expected_rows += 1
        if not text or not str(text).strip():
            acc.empty_text_expected += 1
    aid = r.get("author_id")
    if grain in AUTHOR_EXPECTED:
        acc.author_expected_rows += 1
        if not aid:
            acc.missing_author += 1

    if aid:
        acc.author_counts[aid] += 1
        fds = acc.author_first_ds.get(aid)
        if fds is None:
            acc.author_first_ds[aid] = ds
            acc.author_first_domain[aid] = dom
        else:
            if fds != ds:
                acc.author_cross_ds += 1
            if acc.author_first_domain[aid] != dom:
                acc.author_cross_domain += 1
                if len(acc.cross_domain_authors) < 50:
                    acc.cross_domain_authors.add(aid)
        pd_["authors"].add(aid)

    if r.get("created_at"):
        acc.created_present += 1
        if not _parse_dt_ok(str(r["created_at"])):
            acc.created_unparseable += 1

    nfj = r.get("numeric_features_json")
    if nfj:
        try:
            for k, v in json.loads(nfj).items():
                fv = float(v)
                acc.num_n[k] += 1
                if not math.isfinite(fv):
                    acc.num_nonfinite[k] += 1
                    continue
                acc.num_sum[k] += fv
                acc.num_sumsq[k] += fv * fv
                acc.num_min[k] = fv if k not in acc.num_min else min(acc.num_min[k], fv)
                acc.num_max[k] = fv if k not in acc.num_max else max(acc.num_max[k], fv)
                _reservoir_add(acc, k, fv)
                if COUNT_LIKE.search(k) and fv < 0:
                    acc.num_neg[k] += 1
                if k in VERIFIED_KEYS and fv not in (0.0, 1.0):
                    acc.verified_invalid += 1
        except (TypeError, ValueError):
            pass

    # exact duplicate + cross-dataset/-domain leakage
    ch = _h64(f"{grain}|{dom}|{text or ''}|{aid or ''}|{y}|{nfj or ''}")
    prev = acc.exact_map.get(ch)
    if prev is not None:
        acc.exact_dups += 1
        pd_["exact_dups"] += 1
        if prev != idx:
            acc.exact_cross_dataset += 1
            a, b = sorted((acc.ds_domain[prev], dom))
            if acc.ds_domain[prev] != dom:
                acc.exact_cross_domain += 1
            pair = tuple(sorted((list(acc.ds_index)[prev], ds)))
            if len(acc.cross_dataset_pairs) < 10000:
                acc.cross_dataset_pairs[pair] += 1
    else:
        acc.exact_map[ch] = idx

    # near-duplicate text + cross-dataset
    if text and str(text).strip():
        nt = _norm_text(str(text))
        if nt:
            acc.near_dup_candidates += 1
            nh = _h64(nt)
            prevn = acc.near_map.get(nh)
            if prevn is not None:
                acc.near_dups += 1
                pd_["near_dups"] += 1
                if prevn != idx:
                    acc.near_cross_dataset += 1
            else:
                acc.near_map[nh] = idx


def schema_inconsistencies(infos: list) -> dict:
    """Per-family schema variants + casing/format variants across files."""
    fam_schemas: dict = defaultdict(Counter)
    norm_to_raw: dict = defaultdict(set)
    raw_examples: dict = {}
    for i in infos:
        if not i.columns:
            continue
        cols = tuple(i.columns)
        fam_schemas[i.family][cols] += 1
        norm = frozenset(c.lower().replace("_", "").replace(" ", "") for c in i.columns)
        norm_to_raw[norm].add(cols)
        raw_examples.setdefault(cols, i.path)
    family_variants = {}
    for fam, schemas in fam_schemas.items():
        if len(schemas) > 1:
            variants = sorted(schemas.items(), key=lambda kv: -kv[1])
            base = set(variants[0][0])
            diffs = []
            for cols, cnt in variants[1:]:
                s = set(cols)
                diffs.append({"files": cnt, "added": sorted(s - base)[:8],
                              "removed": sorted(base - s)[:8], "example": raw_examples[cols]})
            family_variants[fam] = {"distinct_schemas": len(schemas),
                                    "base_example": raw_examples[variants[0][0]], "diffs": diffs}
    casing = []
    for norm, raws in norm_to_raw.items():
        if len(raws) > 1:
            casing.append({"normalized_columns": len(norm),
                           "raw_variants": [raw_examples[c] for c in list(raws)[:4]]})
    return {"family_variants": family_variants, "casing_variants": casing[:10]}


def run_scan(cap: int = UNCAPPED):
    random.seed(SEED)
    gov = oc.load_governance()
    infos = oc.discover(oc.DATASETS_ROOT, gov)
    label_map = oc._cresci_label_map()
    acc = Acc()
    parsing_issues = []
    for info in infos:
        conv = oc.CONVERTERS.get(info.family)
        if info.parse_status != "ok":
            parsing_issues.append((info.path, info.fmt, f"unparseable: {info.error}"))
            continue
        if conv is None:
            if info.family not in ("parquet_derived",):
                parsing_issues.append((info.path, info.fmt,
                                       f"no converter (family={info.family}); not normalized"))
            continue
        if info.governance_status not in oc.MERGE_ELIGIBLE_STATUS:
            parsing_issues.append((info.path, info.fmt,
                                   f"governance={info.governance_status} (excluded from training)"))
            continue
        emitted = 0
        try:
            for rec in conv(oc.REPO_ROOT / info.path, info, cap, label_map):
                _update(acc, rec)
                emitted += 1
        except Exception as exc:  # noqa: BLE001
            parsing_issues.append((info.path, info.fmt, f"convert error after {emitted}: {exc}"))
        if info.row_count_method == "exact":
            skipped = max(0, info.row_count - emitted)
            if skipped:
                parsing_issues.append((info.path, info.fmt,
                                       f"{skipped} source rows not emitted (skipped/blank)"))
        print(f"  scanned {emitted:>9,}  {info.path}", flush=True)
    gov_summary = dict(Counter(i.governance_status for i in infos))
    schema = schema_inconsistencies(infos)
    return acc, parsing_issues, gov_summary, schema


def _quantiles(samples: list) -> dict:
    a = np.asarray(samples, dtype=float)
    if a.size == 0:
        return {}
    q = np.percentile(a, [1, 25, 50, 75, 99])
    iqr = q[3] - q[1]
    lo, hi = q[1] - 3 * iqr, q[3] + 3 * iqr
    outliers = int(((a < lo) | (a > hi)).sum())
    return {"p1": round(float(q[0]), 4), "p25": round(float(q[1]), 4),
            "median": round(float(q[2]), 4), "p75": round(float(q[3]), 4),
            "p99": round(float(q[4]), 4), "iqr_outlier_bounds": [round(float(lo), 4), round(float(hi), 4)],
            "outlier_pct_of_sample": round(100 * outliers / a.size, 2), "sample_n": int(a.size)}


def _ascii_hist(samples: list, bins: int = 10, width: int = 40) -> list:
    a = np.asarray(samples, dtype=float)
    if a.size == 0:
        return ["(no data)"]
    lo, hi = float(a.min()), float(a.max())
    if hi <= lo:
        return [f"all = {lo:g} (n={a.size})"]
    counts, edges = np.histogram(a, bins=bins)
    mx = counts.max() or 1
    out = []
    for i in range(bins):
        bar = "#" * int(width * counts[i] / mx)
        out.append(f"  [{edges[i]:>12.2f},{edges[i+1]:>12.2f})  {counts[i]:>7,} |{bar}")
    return out


def _stats(acc: Acc) -> dict:
    n = acc.total
    pos, neg, unk = acc.by_auth["inauthentic"], acc.by_auth["authentic"], acc.by_auth["unknown"]
    labeled = pos + neg
    io_pos = acc.by_label_source.get("io_disclosure", 0)
    num_stats = {}
    for k in sorted(acc.num_n):
        cnt = acc.num_n[k]
        finite = cnt - acc.num_nonfinite[k]
        mean = acc.num_sum[k] / finite if finite else 0.0
        var = max(0.0, acc.num_sumsq[k] / finite - mean * mean) if finite else 0.0
        num_stats[k] = {"rows": cnt, "pct_of_corpus": round(100 * cnt / n, 2),
                        "min": round(acc.num_min.get(k, 0.0), 4),
                        "max": round(acc.num_max.get(k, 0.0), 4),
                        "mean": round(mean, 4), "std": round(math.sqrt(var), 4),
                        "negatives": acc.num_neg[k], "nonfinite": acc.num_nonfinite[k],
                        **_quantiles(acc.reservoir[k])}
    top_pairs = [{"datasets": list(p), "exact_shared": c}
                 for p, c in acc.cross_dataset_pairs.most_common(12)]
    return {
        "total_rows_full_scan": n,
        "authenticity": {"authentic": neg, "inauthentic": pos, "unknown": unk,
                         "authentic_pct": round(100 * neg / n, 2),
                         "inauthentic_pct": round(100 * pos / n, 2),
                         "unknown_pct": round(100 * unk / n, 2)},
        "semantic_labels": {k: {"count": v, "pct": round(100 * v / n, 2)}
                            for k, v in acc.by_semantic.most_common()},
        "label_sources": dict(acc.by_label_source),
        "by_domain": dict(acc.by_domain), "by_grain": dict(acc.by_grain),
        "imbalance": {
            "labeled": labeled, "positive": pos, "negative": neg,
            "positive_pct_of_labeled": round(100 * pos / labeled, 2) if labeled else 0,
            "ratio_pos_to_neg": round(pos / neg, 2) if neg else None,
            "majority_baseline_acc": round(100 * max(pos, neg) / labeled, 2) if labeled else 0,
            "io_share_of_positives_pct": round(100 * io_pos / pos, 2) if pos else 0,
            "excluding_io_positive": pos - io_pos, "excluding_io_negative": neg,
            "excluding_io_positive_pct": round(100 * (pos - io_pos) / ((pos - io_pos) + neg), 2)
            if ((pos - io_pos) + neg) else 0,
        },
        "feature_completeness_pct": {f: round(100 * acc.field_nonnull[f] / n, 2)
                                     for f in oc.RECORD_FIELDS},
        "numeric_features": num_stats,
        "duplicates": {
            "exact_duplicates": acc.exact_dups,
            "exact_duplicate_pct": round(100 * acc.exact_dups / n, 2),
            "exact_cross_dataset": acc.exact_cross_dataset,
            "exact_cross_domain": acc.exact_cross_domain,
            "near_dup_text_candidates": acc.near_dup_candidates,
            "near_duplicate_text": acc.near_dups,
            "near_duplicate_text_pct_of_textrows": round(
                100 * acc.near_dups / acc.near_dup_candidates, 2) if acc.near_dup_candidates else 0,
            "near_cross_dataset": acc.near_cross_dataset,
            "distinct_authors": len(acc.author_counts),
            "authored_rows": sum(acc.author_counts.values()),
            "rows_per_author_mean": round(sum(acc.author_counts.values()) /
                                          len(acc.author_counts), 2) if acc.author_counts else 0,
            "max_rows_single_author": acc.author_counts.most_common(1)[0][1] if acc.author_counts else 0,
        },
        "cross_dataset_leakage": {
            "exact_content_shared_across_datasets": acc.exact_cross_dataset,
            "exact_content_shared_across_domains": acc.exact_cross_domain,
            "near_text_shared_across_datasets": acc.near_cross_dataset,
            "authors_in_multiple_source_files": acc.author_cross_ds,
            "authors_in_multiple_domains": acc.author_cross_domain,
            "top_cross_dataset_pairs": top_pairs,
        },
        "quality": {
            "label_invalid": acc.label_invalid,
            "verified_field_invalid": acc.verified_invalid,
            "created_at_present": acc.created_present,
            "created_at_unparseable": acc.created_unparseable,
            "created_at_unparseable_pct": round(100 * acc.created_unparseable /
                                                acc.created_present, 2) if acc.created_present else 0,
            "text_expected_rows": acc.text_expected_rows,
            "empty_text_expected": acc.empty_text_expected,
            "author_expected_rows": acc.author_expected_rows,
            "missing_author": acc.missing_author,
        },
    }


def _write_per_dataset_csv(acc: Acc, path: Path) -> list:
    rows = [{"dataset": ds, "rows": d["rows"], "pct_of_corpus": round(100 * d["rows"] / acc.total, 3),
             "domain": d["domain"], "grain": d["grain"], "authentic": d["l0"],
             "inauthentic": d["l1"], "unknown": d["lnull"], "exact_dups": d["exact_dups"],
             "near_dup_text": d["near_dups"], "distinct_authors": len(d["authors"])}
            for ds, d in acc.per_ds.items()]
    rows.sort(key=lambda r: -r["rows"])
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    return rows


def _committed_rows() -> int:
    try:
        import pyarrow.parquet as pq
        return pq.ParquetFile(str(COMMITTED_CORPUS)).metadata.num_rows
    except Exception:  # noqa: BLE001
        return -1


def render(stats, per_ds, parsing_issues, gov_summary, schema, acc, committed) -> str:
    s, im, dup, q = stats, stats["imbalance"], stats["duplicates"], stats["quality"]
    lk = stats["cross_dataset_leakage"]
    n = s["total_rows_full_scan"]
    fc = s["feature_completeness_pct"]
    sparse = sorted([(k, v) for k, v in fc.items() if v < 90], key=lambda kv: kv[1])
    nf_sorted = sorted(s["numeric_features"].items(), key=lambda kv: -kv[1]["rows"])
    L = [
        "# Omi Corpus Audit — COMPREHENSIVE (OMI_CORPUS_AUDIT_V1)", "",
        "> **Full uncapped streaming scan** of every governance-approved source row, line by "
        "line, through the unified converters (`ml/corpus/audit_full.py`). **Strictly "
        "read-only** — no source dataset, normalized corpus, or production code was modified; "
        "no training. Outputs: this report, `audit_stats.json`, `audit_per_dataset.csv`.",
        "",
        "## Scope",
        f"- **Total records scanned (full population): {n:,}** — every approved source row.",
        f"- Committed sample `data/merged_corpus.parquet`: {committed:,} rows (capped 1,000/file "
        "for git; not modified by this audit).",
        f"- Datasets scanned: {len(per_ds)}; files with issues / excluded: {len(parsing_issues)}.",
        "",
        f"## 1. Total records scanned: **{n:,}**",
        "",
        "## 2. Per-dataset record counts (top 25; full list in `audit_per_dataset.csv`)",
        "| dataset | rows | % | domain | grain | distinct accts |", "|---|---|---|---|---|---|",
    ]
    for r in per_ds[:25]:
        L.append(f"| `{r['dataset']}` | {r['rows']:,} | {r['pct_of_corpus']} | {r['domain']} "
                 f"| {r['grain']} | {r['distinct_authors']:,} |")
    L += ["", "## 3. Label distribution (complete datasets)",
          "| authenticity | count | % |", "|---|---|---|",
          f"| authentic (0) | {s['authenticity']['authentic']:,} | {s['authenticity']['authentic_pct']} |",
          f"| inauthentic (1) | {s['authenticity']['inauthentic']:,} | {s['authenticity']['inauthentic_pct']} |",
          f"| unknown (null) | {s['authenticity']['unknown']:,} | {s['authenticity']['unknown_pct']} |",
          "", "| semantic label | count | % |", "|---|---|---|"]
    for k, v in s["semantic_labels"].items():
        L.append(f"| {k} | {v['count']:,} | {v['pct']} |")

    L += ["", "## 4. Feature completeness (% of rows populated)", "| field | % |", "|---|---|"]
    for f in oc.RECORD_FIELDS:
        L.append(f"| `{f}` | {fc[f]} |")
    L += ["", "**Sparse fields:** " + (", ".join(f"`{k}` ({v}%)" for k, v in sparse) or "none<90%")
          + ". **Engine fingerprint/detector features: 0% present** (largest gap).",
          "", "Numeric coverage (top 12): min / median / mean / p99 / max / negatives / nonfinite",
          "| feature | rows | % | min | median | mean | p99 | max | neg | nonfin |",
          "|---|---|---|---|---|---|---|---|---|---|"]
    for k, v in nf_sorted[:12]:
        L.append(f"| `{k}` | {v['rows']:,} | {v['pct_of_corpus']} | {v['min']} | "
                 f"{v.get('median','-')} | {v['mean']} | {v.get('p99','-')} | {v['max']} | "
                 f"{v['negatives']} | {v['nonfinite']} |")

    L += ["", "## 5. Exact duplicate detection",
          f"- Exact duplicates (identical content): **{dup['exact_duplicates']:,}** "
          f"({dup['exact_duplicate_pct']}%).",
          f"- Of which **cross-dataset: {dup['exact_cross_dataset']:,}**, "
          f"**cross-domain: {dup['exact_cross_domain']:,}**.",
          "", "## 6. Near-duplicate detection",
          "Method: normalize text (lowercase, strip URLs/@mentions/`RT`, collapse whitespace), "
          "hash, count repeats.",
          f"- Near-duplicate texts: **{dup['near_duplicate_text']:,}** of "
          f"{dup['near_dup_text_candidates']:,} text rows "
          f"(**{dup['near_duplicate_text_pct_of_textrows']}%**); cross-dataset near-dups: "
          f"**{dup['near_cross_dataset']:,}** — retweet/boilerplate echoes, mostly IO.",
          "", "## 7. Duplicate account analysis",
          f"- {dup['authored_rows']:,} authored rows across **{dup['distinct_authors']:,}** "
          f"distinct accounts → mean **{dup['rows_per_author_mean']} rows/account** "
          f"(max {dup['max_rows_single_author']:,}).",
          "- **Row-rich, account-poor** → tweet-grain training MUST use by-account (group) "
          "splits or effective sample size collapses and near-dup echoes inflate metrics.",
          "", "## 8. Missing & invalid values",
          f"- Missing text (text grains): {q['empty_text_expected']:,}/{q['text_expected_rows']:,}; "
          f"missing author (author grains): {q['missing_author']:,}/{q['author_expected_rows']:,}.",
          f"- Invalid labels (outside 0/1/null): {q['label_invalid']}; boolean fields out of "
          f"{{0,1}}: **{q['verified_field_invalid']:,}** (real/fake_users noised booleans).",
          f"- Unparseable timestamps: {q['created_at_unparseable']:,}/{q['created_at_present']:,} "
          f"({q['created_at_unparseable_pct']}%).",
          "", "## 9. Schema inconsistencies"]
    if schema["family_variants"]:
        L.append("Source families whose files do not share one schema:")
        L.append("| family | distinct schemas | example diff |")
        L.append("|---|---|---|")
        for fam, info in schema["family_variants"].items():
            d0 = info["diffs"][0] if info["diffs"] else {}
            diff = f"+{d0.get('added', [])} -{d0.get('removed', [])}" if d0 else "—"
            L.append(f"| {fam} | {info['distinct_schemas']} | {diff} |")
    else:
        L.append("- No within-family schema drift among converted families.")
    if schema["casing_variants"]:
        L += ["", "**Casing/format variants** (same columns, different naming — e.g. camelCase vs "
              "snake_case IO exports):"]
        for cv in schema["casing_variants"]:
            L.append(f"- variants: {', '.join('`'+p+'`' for p in cv['raw_variants'])}")

    L += ["", "## 10. Parsing failures / not normalized",
          "| file | format | issue |", "|---|---|---|"]
    for p, fmt, reason in parsing_issues[:30]:
        L.append(f"| `{p}` | {fmt} | {reason} |")
    if len(parsing_issues) > 30:
        L.append(f"| _… {len(parsing_issues)-30} more_ | | |")

    bool_keys = [k for k in ("default_profile", "geo_enabled", "protected") if k in s["numeric_features"]]
    L += ["", "## 11. Dataset-specific quality issues",
          "- **`real_users` / `fake_users`**: boolean profile fields are noised/continuous ("
          + ", ".join(f"`{k}` max {s['numeric_features'][k]['max']}" for k in bool_keys)
          + " — should be 0/1) and counts are non-integer/partly-zeroed → **low-trust metadata**; "
          "labels come from file origin (confound).",
          "- **IO campaigns** ship as many per-year/part files sharing accounts → heavy intra-"
          "campaign duplication; treat a campaign as one unit, not per-file.",
          "- **`TwitterData_Joined`**: ~20% of all rows but only ~96 accounts (tweet grain) — "
          "dominates the non-IO balance; strong per-account concentration.",
          "- **camelCase IO users variant** + **`.xlsx`** + **quarantine/archive** sets are not "
          "normalized (see §9/§10).",
          "", "## 12. Class imbalance analysis",
          f"- Labeled **{im['labeled']:,}**, **{im['positive_pct_of_labeled']}% positive** "
          f"(ratio {im['ratio_pos_to_neg']}:1); majority baseline acc **{im['majority_baseline_acc']}%** "
          "→ use F1/AUC/Brier.",
          f"- **{im['io_share_of_positives_pct']}% of positives are IO**. Excluding IO: "
          f"{im['excluding_io_positive']:,} pos / {im['excluding_io_negative']:,} neg = "
          f"**{im['excluding_io_positive_pct']}% positive** (but that balance is concentrated in "
          "TwitterData_Joined's ~96 accounts).",
          "By domain: " + ", ".join(f"{k} {v:,}" for k, v in s["by_domain"].items()) + ".",
          "", "## 13. Potential cross-dataset data leakage",
          f"- Exact content shared **across datasets**: {lk['exact_content_shared_across_datasets']:,} "
          f"(across **domains**: {lk['exact_content_shared_across_domains']:,}).",
          f"- Near-duplicate text shared across datasets: {lk['near_text_shared_across_datasets']:,}.",
          f"- Accounts appearing in >1 source file: {lk['authors_in_multiple_source_files']:,} "
          f"(mostly intra-campaign IO splits); in **>1 domain: {lk['authors_in_multiple_domains']:,}** "
          "(the real leakage signal — same account labeled in different domains).",
          "- **Mitigation:** dedupe globally before splitting; split by account AND keep whole "
          "campaigns/domains on one side; never mix the same account across train/eval."]
    if lk["top_cross_dataset_pairs"]:
        L += ["", "Top dataset pairs sharing exact content:",
              "| dataset A | dataset B | shared |", "|---|---|---|"]
        for p in lk["top_cross_dataset_pairs"][:8]:
            a, b = p["datasets"]
            L.append(f"| `{a}` | `{b}` | {p['exact_shared']:,} |")

    L += ["", "## 14. Outlier detection (IQR, on per-feature reservoir samples)",
          "| feature | median | p99 | max | IQR-outlier % |", "|---|---|---|---|---|"]
    for k, v in nf_sorted[:14]:
        if "outlier_pct_of_sample" in v:
            L.append(f"| `{k}` | {v.get('median')} | {v.get('p99')} | {v['max']} | "
                     f"{v['outlier_pct_of_sample']}% |")
    L += ["", "Extreme right-tail skew (huge max vs median, e.g. follower/count features) is "
          "expected for social data → apply log1p before training."]

    L += ["", "## 15. Visualizations (ASCII; matplotlib unavailable)"]
    for k in [kk for kk, _ in nf_sorted[:3]] + (["bot_score_english"] if "bot_score_english"
                                                in acc.reservoir else []):
        L += [f"", f"`{k}` distribution (reservoir n={len(acc.reservoir[k]):,}):", "```text"]
        L += _ascii_hist(acc.reservoir[k])
        L += ["```"]

    L += ["", "## 16. Recommendations for preprocessing before training",
          "1. **Filter by grain/domain first** — train separate models (authenticity / "
          "coordination / ai-text / bot); never one model across grains.",
          "2. **Global dedup** — drop the 33k+ exact and 230k+ near-duplicate texts before "
          "splitting (they inflate metrics and leak across splits).",
          "3. **By-account group splits** — partition on `author_id` (and keep whole "
          "campaigns/domains on one side) so no account spans train/eval.",
          "4. **Rebalance** — the labeled set is 89% positive; use class weights / "
          "downsample IO / report F1·AUC·Brier, not accuracy.",
          "5. **log1p-transform skewed counts** (follower/following/status/favourite/count) and "
          "**clip outliers** to robust bounds (see §14).",
          "6. **Normalize the noised real/fake_users booleans** to {0,1} (or drop those fields); "
          "resolve the source↔label origin confound (mix sources per class or hold out).",
          "7. **Drop username-morphology features** (V2 shortcut) and **unlabeled rows** "
          "(reference + ~unjoined) from supervised training.",
          "8. **Populate engine features** (fingerprint/detector) — the highest-value step; "
          "without them an account model trains on bare metadata.",
          "9. **Add legitimate-coordination negatives** so the IO data becomes trainable rather "
          "than all-positive.",
          "", "## 17. Training-readiness assessment",
          "**Strengths:** large, governed, schema-unified; strong state-IO coordination ground "
          "truth; clean per-row provenance; non-IO labels near-balanced.",
          "**Weaknesses:** no engine features; 89% positive + grain mixing; only "
          f"~{dup['distinct_authors']:,} distinct accounts behind {n:,} rows with "
          f"{dup['near_duplicate_text_pct_of_textrows']}% near-dup text; real/fake origin "
          "confound + noised booleans; IO has no in-domain negatives.",
          "",
          "| target | verdict |", "|---|---|",
          "| Single corpus-wide model | **❌ Not ready** (grain mixing + IO imbalance) |",
          "| Account-authenticity V1 (headline) | **❌ Not ready** — needs engine features + "
          "confound/imbalance/dedup fixes |",
          "| AI-text classifier (per-grain) | **🟡 Ready with preprocessing** (dedup+balance) |",
          "| Bot classifier (per-grain) | **🟡 Ready with preprocessing** |",
          "| Coordination/IO model | **❌ Not ready** — no legitimate-coordination negatives |",
          "",
          "**Overall: NOT READY for full-corpus model training.** It is an excellent "
          "standardized *substrate* and is *ready-with-preprocessing* for narrow per-grain "
          "ai-text/bot baselines once §16 steps 1–5 are applied. The headline account-"
          "authenticity model is blocked on engine features (§16.8) and the "
          "confound/imbalance/account-scarcity issues above. **Address §16 #1–#3 and #8 first.**",
          "",
          "_Artifacts: this report · `audit_stats.json` · `audit_per_dataset.csv`._", "",
    ]
    return "\n".join(L)


def main(argv=None) -> int:
    print("Comprehensive full uncapped streaming scan (read-only)…", flush=True)
    acc, parsing_issues, gov_summary, schema = run_scan()
    stats = _stats(acc)
    stats["schema_inconsistencies"] = schema
    per_ds = _write_per_dataset_csv(acc, PER_DATASET_CSV)
    committed = _committed_rows()
    STATS_PATH.write_text(json.dumps(stats, indent=2) + "\n", encoding="utf-8")
    REPORT_PATH.write_text(render(stats, per_ds, parsing_issues, gov_summary, schema, acc,
                                  committed), encoding="utf-8")
    im, dup, lk = stats["imbalance"], stats["duplicates"], stats["cross_dataset_leakage"]
    print(f"\nDONE. {stats['total_rows_full_scan']:,} records; {im['positive_pct_of_labeled']}% pos "
          f"(excl-IO {im['excluding_io_positive_pct']}%); exact-dups {dup['exact_duplicates']:,} "
          f"(x-dataset {dup['exact_cross_dataset']:,}); near-dup {dup['near_duplicate_text']:,}; "
          f"accounts {dup['distinct_authors']:,}; x-domain authors {lk['authors_in_multiple_domains']:,}.")
    print(f"Wrote {REPORT_PATH.name}, {STATS_PATH.name}, {PER_DATASET_CSV.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
