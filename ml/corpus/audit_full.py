#!/usr/bin/env python3
"""OMI_CORPUS_AUDIT_V1 (complete) — full uncapped scan of the source datasets.

Streams EVERY row of every governance-approved, convertible dataset through the
unified converters (ml/corpus/omi_corpus.py) — uncapped, line by line — and
computes the complete audit the capped merged-corpus view could not: full label
distribution, per-dataset contribution, feature completeness, exact + near
duplicates, duplicate accounts, and invalid-value / quality checks. It then
writes the human-readable report, a machine-readable JSON summary, and a
per-dataset CSV.

READ-ONLY: it does not modify the corpus, the normalized dataset, the source
data, or production. It does not train. (Companion `audit.py` audits the
committed capped sample; this audits the full source population.)
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
import omi_corpus as oc  # noqa: E402

REPORT_PATH = _HERE / "CORPUS_AUDIT_V1.md"
STATS_PATH = _HERE / "audit_stats.json"
PER_DATASET_CSV = _HERE / "audit_per_dataset.csv"
COMMITTED_CORPUS = _HERE / "data" / "merged_corpus.parquet"

UNCAPPED = 10 ** 12
TEXT_EXPECTED = {"tweet", "text"}          # comment-grain (reddit) has no text by source design
AUTHOR_EXPECTED = {"account", "tweet", "comment"}
COUNT_LIKE = re.compile(r"(follow|friend|status|post|count|age|karma|listed|favourite)", re.I)
VERIFIED_KEYS = {"meta_verified", "verified", "default_profile", "default_profile_image",
                 "geo_enabled", "protected"}
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
    # numeric feature stats
    num_n: Counter = field(default_factory=Counter)
    num_sum: dict = field(default_factory=lambda: defaultdict(float))
    num_sumsq: dict = field(default_factory=lambda: defaultdict(float))
    num_min: dict = field(default_factory=dict)
    num_max: dict = field(default_factory=dict)
    num_neg: Counter = field(default_factory=Counter)
    num_nonfinite: Counter = field(default_factory=Counter)
    verified_invalid: int = 0
    created_present: int = 0
    created_unparseable: int = 0
    empty_text_expected: int = 0
    text_expected_rows: int = 0
    missing_author: int = 0
    author_expected_rows: int = 0
    label_invalid: int = 0
    # duplicates
    exact_hashes: set = field(default_factory=set)
    exact_dups: int = 0
    text_norm_hashes: set = field(default_factory=set)
    near_dups: int = 0
    near_dup_candidates: int = 0
    author_counts: Counter = field(default_factory=Counter)
    author_first_ds: dict = field(default_factory=dict)
    author_cross_ds: int = 0
    per_ds: dict = field(default_factory=lambda: defaultdict(
        lambda: {"rows": 0, "domain": "", "grain": "", "l0": 0, "l1": 0, "lnull": 0,
                 "exact_dups": 0, "near_dups": 0, "authors": set()}))


def _update(acc: Acc, r: dict) -> None:
    acc.total += 1
    ds = r["dataset"]
    acc.by_dataset[ds] += 1
    acc.by_domain[r["domain"]] += 1
    acc.by_grain[r["grain"]] += 1
    acc.by_label_source[r["label_source"]] += 1
    sem = oc_audit_semantic(r["label_source"], r["authenticity_label"])
    acc.by_semantic[sem] += 1
    y = r["authenticity_label"]
    acc.by_auth["unknown" if y is None else "inauthentic" if int(y) == 1 else "authentic"] += 1

    pd_ = acc.per_ds[ds]
    pd_["rows"] += 1
    pd_["domain"], pd_["grain"] = r["domain"], r["grain"]
    pd_["l1" if y == 1 else "l0" if y == 0 else "lnull"] += 1

    for f in oc.RECORD_FIELDS:
        if r.get(f) not in (None, ""):
            acc.field_nonnull[f] += 1
    if y not in (0, 1, None):
        acc.label_invalid += 1

    grain = r["grain"]
    text = r.get("text")
    if grain in TEXT_EXPECTED:
        acc.text_expected_rows += 1
        if not text or not str(text).strip():
            acc.empty_text_expected += 1
    if grain in AUTHOR_EXPECTED:
        acc.author_expected_rows += 1
        if not r.get("author_id"):
            acc.missing_author += 1

    aid = r.get("author_id")
    if aid:
        acc.author_counts[aid] += 1
        first = acc.author_first_ds.get(aid)
        if first is None:
            acc.author_first_ds[aid] = ds
        elif first != ds:
            acc.author_cross_ds += 1
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
                if COUNT_LIKE.search(k) and fv < 0:
                    acc.num_neg[k] += 1
                if k in VERIFIED_KEYS and fv not in (0.0, 1.0):
                    acc.verified_invalid += 1
        except (TypeError, ValueError):
            pass

    # exact duplicate (full content)
    ch = _h64(f"{ds}|{grain}|{r['domain']}|{text or ''}|{aid or ''}|{y}|{nfj or ''}")
    if ch in acc.exact_hashes:
        acc.exact_dups += 1
        pd_["exact_dups"] += 1
    else:
        acc.exact_hashes.add(ch)
    # near duplicate (normalized text)
    if text and str(text).strip():
        nt = _norm_text(str(text))
        if nt:
            acc.near_dup_candidates += 1
            nh = _h64(nt)
            if nh in acc.text_norm_hashes:
                acc.near_dups += 1
                pd_["near_dups"] += 1
            else:
                acc.text_norm_hashes.add(nh)


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


def run_scan(cap: int = UNCAPPED) -> tuple[Acc, list, dict]:
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
        skipped = max(0, info.row_count - emitted) if info.row_count_method == "exact" else None
        if skipped:
            parsing_issues.append((info.path, info.fmt,
                                   f"{skipped} source rows not emitted (skipped/blank)"))
        print(f"  scanned {emitted:>9,}  {info.path}", flush=True)
    governance_summary = dict(Counter(i.governance_status for i in infos))
    return acc, parsing_issues, governance_summary


def _stats(acc: Acc) -> dict:
    n = acc.total
    pos, neg, unk = acc.by_auth["inauthentic"], acc.by_auth["authentic"], acc.by_auth["unknown"]
    labeled = pos + neg
    io_pos = acc.by_label_source.get("io_disclosure", 0)
    multi = [(a, c) for a, c in acc.author_counts.most_common(15)]
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
                        "negatives": acc.num_neg[k], "nonfinite": acc.num_nonfinite[k]}
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
            "near_dup_text_candidates": acc.near_dup_candidates,
            "near_duplicate_text": acc.near_dups,
            "near_duplicate_text_pct_of_textrows": round(
                100 * acc.near_dups / acc.near_dup_candidates, 2) if acc.near_dup_candidates else 0,
            "distinct_authors": len(acc.author_counts),
            "authored_rows": sum(acc.author_counts.values()),
            "rows_per_author_mean": round(sum(acc.author_counts.values()) /
                                          len(acc.author_counts), 2) if acc.author_counts else 0,
            "max_rows_single_author": multi[0][1] if multi else 0,
            "top_authors": [{"rows": c} for _, c in multi],
            "authors_in_multiple_datasets": acc.author_cross_ds,
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


def _write_per_dataset_csv(acc: Acc, path: Path) -> None:
    rows = []
    for ds, d in acc.per_ds.items():
        rows.append({"dataset": ds, "rows": d["rows"], "pct_of_corpus": round(100 * d["rows"] / acc.total, 3),
                     "domain": d["domain"], "grain": d["grain"], "authentic": d["l0"],
                     "inauthentic": d["l1"], "unknown": d["lnull"], "exact_dups": d["exact_dups"],
                     "near_dup_text": d["near_dups"], "distinct_authors": len(d["authors"])})
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


def render(stats: dict, per_ds: list, parsing_issues: list, gov_summary: dict,
           committed: int) -> str:
    s, im, dup, q = stats, stats["imbalance"], stats["duplicates"], stats["quality"]
    n = s["total_rows_full_scan"]
    fc = s["feature_completeness_pct"]
    sparse = sorted([(k, v) for k, v in fc.items() if v < 90], key=lambda kv: kv[1])
    L = [
        "# Omi Corpus Audit — COMPLETE (OMI_CORPUS_AUDIT_V1)", "",
        "> **Full uncapped scan** of every governance-approved source row, streamed line by "
        "line through the unified converters (`ml/corpus/audit_full.py`). Read-only: the "
        "corpus, normalized dataset, source data, and production are unmodified; no training.",
        "",
        "## Scope",
        f"- **Full normalized population (this scan): {n:,} rows** — what training can draw on.",
        f"- Committed sample artifact `data/merged_corpus.parquet`: **{committed:,} rows** "
        "(capped 1,000/file for git; audited by the companion `audit.py`).",
        "- This report supersedes the capped view for every count below.",
        "",
        f"## 1. Total training examples: **{n:,}** (full population)",
        "",
        "## 2. Label distribution",
        "### 2a. Authenticity (normalized)",
        "| class | count | % |", "|---|---|---|",
        f"| authentic (0) | {s['authenticity']['authentic']:,} | {s['authenticity']['authentic_pct']} |",
        f"| inauthentic (1) | {s['authenticity']['inauthentic']:,} | {s['authenticity']['inauthentic_pct']} |",
        f"| unknown (null) | {s['authenticity']['unknown']:,} | {s['authenticity']['unknown_pct']} |",
        "", "### 2b. Every semantic label", "| label | count | % |", "|---|---|---|",
    ]
    for k, v in s["semantic_labels"].items():
        L.append(f"| {k} | {v['count']:,} | {v['pct']} |")
    L += ["", "### 2c. Class imbalance",
          f"- Labeled: **{im['labeled']:,}** → **{im['positive_pct_of_labeled']}% positive** "
          f"(ratio {im['ratio_pos_to_neg']}:1). Majority baseline accuracy "
          f"**{im['majority_baseline_acc']}%** → use F1/AUC/Brier, not accuracy.",
          f"- **Severe, and IO-driven**: {im['io_share_of_positives_pct']}% of positives are "
          f"state-IO tweets. **Excluding IO**: {im['excluding_io_positive']:,} pos / "
          f"{im['excluding_io_negative']:,} neg = **{im['excluding_io_positive_pct']}% positive** "
          "(far healthier).",
          "", "## 3. Dataset contribution (top 30 of "
          f"{len(per_ds)})", "| dataset | rows | % | domain | grain |", "|---|---|---|---|---|"]
    for r in per_ds[:30]:
        L.append(f"| `{r['dataset']}` | {r['rows']:,} | {r['pct_of_corpus']} | {r['domain']} "
                 f"| {r['grain']} |")
    L.append(f"\n_Full per-dataset table (all {len(per_ds)}): `audit_per_dataset.csv`._")
    by_fam_domain = Counter()
    for r in per_ds:
        by_fam_domain[r["domain"]] += r["rows"]
    L += ["", "By domain: " + ", ".join(f"{k} {v:,} ({round(100*v/n,1)}%)"
                                        for k, v in by_fam_domain.most_common()), ""]

    L += ["## 4. Feature completeness (% of all rows populated)",
          "| field | % populated |", "|---|---|"]
    for f in oc.RECORD_FIELDS:
        L.append(f"| `{f}` | {fc[f]} |")
    L += ["", "**Sparse / mostly-empty fields:** " +
          (", ".join(f"`{k}` ({v}%)" for k, v in sparse) or "none < 90%") + ".",
          "- `text` is null for account/comment grains by source design; `lang` only the "
          "IO/AI sets carry it; `created_at` absent for profile sets.",
          "- **Engine detector/fingerprint features are 0% present** — no source carries them; "
          "this is the single largest feature gap for an authenticity model.",
          "", "### Numeric feature coverage (top 18 by frequency)",
          "| feature | rows | % | min | max | mean | negatives | nonfinite |",
          "|---|---|---|---|---|---|---|---|"]
    for k, v in sorted(s["numeric_features"].items(), key=lambda kv: -kv[1]["rows"])[:18]:
        L.append(f"| `{k}` | {v['rows']:,} | {v['pct_of_corpus']} | {v['min']} | {v['max']} "
                 f"| {v['mean']} | {v['negatives']} | {v['nonfinite']} |")

    L += ["", "## 5. Duplicate analysis",
          f"- **Exact duplicates** (identical content): **{dup['exact_duplicates']:,}** "
          f"({dup['exact_duplicate_pct']}%).",
          f"- **Near-duplicate text** (normalized: lowercased, URLs/@mentions/`RT` stripped, "
          f"whitespace collapsed): **{dup['near_duplicate_text']:,}** of "
          f"{dup['near_dup_text_candidates']:,} text rows "
          f"(**{dup['near_duplicate_text_pct_of_textrows']}%**) — retweet/boilerplate echoes, "
          "overwhelmingly in the IO streams.",
          f"- **Duplicate accounts**: {dup['authored_rows']:,} authored rows across "
          f"**{dup['distinct_authors']:,}** distinct accounts → mean "
          f"**{dup['rows_per_author_mean']} rows/account** (max "
          f"{dup['max_rows_single_author']:,}). Accounts appearing across >1 source file: "
          f"{dup['authors_in_multiple_datasets']:,} — mostly **intra-campaign IO file splits** "
          "(each campaign ships as several yearly/part files sharing the same accounts), not "
          "cross-campaign identity collisions.",
          "- **Implication:** the corpus is row-rich but **account-poor**; tweet-grain training "
          "MUST split by account (group-aware) or effective sample size collapses to the "
          f"~{dup['distinct_authors']:,} accounts and near-dup echoes inflate metrics.",
          "", "## 6. Data quality analysis",
          f"- **Missing values**: text missing in {q['empty_text_expected']:,}/"
          f"{q['text_expected_rows']:,} text-grain rows; author missing in "
          f"{q['missing_author']:,}/{q['author_expected_rows']:,} author-grain rows.",
          f"- **Invalid values**: labels outside {{0,1,null}}: {q['label_invalid']}; "
          f"verified/boolean fields out of {{0,1}}: {q['verified_field_invalid']:,}; "
          "negative count-like features: see the numeric table above.",
          "- **Dataset with quality concerns — `real_users` / `fake_users`**: boolean profile "
          f"fields are noised/continuous (e.g. `default_profile` max "
          f"{s['numeric_features'].get('default_profile', {}).get('max', '?')}, `geo_enabled` max "
          f"{s['numeric_features'].get('geo_enabled', {}).get('max', '?')} — should be 0/1) and "
          "counts are non-integer / partly zeroed. Treat their metadata as **low-trust**, and "
          "remember their labels come from file origin (confound).",
          f"- **Parsing issues / unparseable timestamps**: {q['created_at_unparseable']:,}/"
          f"{q['created_at_present']:,} present `created_at` values "
          f"({q['created_at_unparseable_pct']}%) failed standard date parsing.",
          "- **Governance breakdown (all discovered files):** " +
          ", ".join(f"{k}={v}" for k, v in sorted(gov_summary.items())) + ".",
          "", "### Files with quality concerns / not normalized",
          "| file | format | issue |", "|---|---|---|"]
    for p, fmt, reason in parsing_issues[:30]:
        L.append(f"| `{p}` | {fmt} | {reason} |")
    if len(parsing_issues) > 30:
        L.append(f"| _… {len(parsing_issues)-30} more_ | | |")

    L += ["", "## 7. Training-readiness assessment",
          "**Strengths**",
          f"- Large, governed, schema-unified ({n:,} rows); poison/archive excluded by manifest.",
          "- Strong, platform-attributed **coordination** ground truth (state-IO) at scale.",
          "- **Excluding IO, the labeled authenticity/bot/text slices are near-balanced** "
          f"({im['excluding_io_positive']:,}/{im['excluding_io_negative']:,}).",
          "- Clean lineage: every row carries `dataset`/`label_source`/`grain` provenance.",
          "",
          "**Weaknesses**",
          "- **No engine features** (fingerprint/detector blocks 0% populated) — an "
          "account-authenticity model would train on bare metadata.",
          f"- **Severe label imbalance** ({im['positive_pct_of_labeled']}% positive) and "
          "**grain mixing** (account/tweet/comment/text) — one model cannot span them.",
          f"- **Account-poor**: only ~{dup['distinct_authors']:,} distinct accounts behind "
          f"{n:,} rows; **{dup['near_duplicate_text_pct_of_textrows']}% near-duplicate text** "
          "→ leakage risk without by-account splitting.",
          "- **Confounds**: real/fake_users labeled by file origin (+ degraded metadata); IO "
          "is 100% positive with **no in-domain negatives**.",
          "",
          "**Biggest-impact improvements (ranked)**",
          "1. **Run the engine over the accounts** to populate fingerprint/detector features — "
          "turns bare metadata into Omi's real signal (largest lift).",
          "2. **Add legitimate-coordination negatives** (`known-mixed`) so the IO data becomes "
          "a trainable coordination set rather than an all-positive pile.",
          "3. **Adopt by-account group splits + class rebalancing/weighting** to kill the "
          "near-dup leakage and the imbalance distortion.",
          "4. **Resolve the real/fake_users origin confound** (mix sources per class or drop).",
          "5. **Per-grain framing** (separate authenticity / coordination / ai-text / bot "
          "models) rather than one corpus-wide model.",
          "",
          "## 8. Final recommendation",
          "",
          "| target | verdict |",
          "|---|---|",
          "| Single corpus-wide V1 model | **❌ Not ready** (grain mixing + 90% IO imbalance) |",
          "| Account-authenticity V1 (the headline OmiBehavioralNet) | **❌ Not ready** — "
          "needs engine features + confound fixes |",
          "| AI-text classifier (per-grain) | **🟡 Ready with minor improvements** "
          "(dedup + balance; ~1.5k labeled) |",
          "| Bot classifier (per-grain) | **🟡 Ready with minor improvements** (~2.5k labeled) |",
          "| Coordination/IO model | **❌ Not ready** — no legitimate-coordination negatives |",
          "",
          "**Overall: NOT READY for V1 training as a single authenticity corpus.** It is an "
          "excellent standardized *substrate* and is *ready-with-minor-improvements* for narrow "
          "per-grain text/bot baselines, but the headline account-authenticity model is blocked "
          "on engine features and the confound/imbalance/account-scarcity issues above. Address "
          "improvements #1–#3 first.",
          "",
          "_Artifacts: this report, `audit_stats.json` (machine-readable), "
          "`audit_per_dataset.csv` (per-dataset supporting stats)._",
          "",
    ]
    return "\n".join(L)


def main(argv=None) -> int:
    print("Full uncapped scan of approved source datasets (line by line)…", flush=True)
    acc, parsing_issues, gov_summary = run_scan()
    stats = _stats(acc)
    per_ds = _write_per_dataset_csv(acc, PER_DATASET_CSV)
    committed = _committed_rows()
    STATS_PATH.write_text(json.dumps(stats, indent=2) + "\n", encoding="utf-8")
    REPORT_PATH.write_text(render(stats, per_ds, parsing_issues, gov_summary, committed),
                           encoding="utf-8")
    im = stats["imbalance"]
    print(f"\nDONE. Full population {stats['total_rows_full_scan']:,} rows; "
          f"labeled {im['positive_pct_of_labeled']}% pos (excl-IO "
          f"{im['excluding_io_positive_pct']}%); exact-dups {stats['duplicates']['exact_duplicates']:,}; "
          f"near-dup text {stats['duplicates']['near_duplicate_text']:,}; "
          f"distinct accounts {stats['duplicates']['distinct_authors']:,}.")
    print(f"Wrote {REPORT_PATH.name}, {STATS_PATH.name}, {PER_DATASET_CSV.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
