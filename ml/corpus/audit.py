#!/usr/bin/env python3
"""OMI_CORPUS_AUDIT_V1 — read-only audit of the normalized Omi corpus.

Reads ml/corpus/data/merged_corpus.parquet and emits CORPUS_AUDIT_V1.md +
audit_stats.json: row count, label distribution (semantic + authenticity),
per-dataset contribution, feature availability/completeness, duplicate analysis,
class-imbalance analysis, exclusion recommendations, and a V1-readiness verdict.

Read-only: does not modify data, train, or change production.
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

CORPUS_DIR = Path(__file__).resolve().parent
CORPUS_PATH = CORPUS_DIR / "data" / "merged_corpus.parquet"
REPORT_PATH = CORPUS_DIR / "CORPUS_AUDIT_V1.md"
STATS_PATH = CORPUS_DIR / "audit_stats.json"

USERNAME_SHORTCUT = {"username", "username_length", "username_randomness", "digits_count",
                     "digit_ratio", "special_char_count", "repeat_char_count"}
TEXT_GRAINS = {"tweet", "text", "comment"}
ACCOUNT_GRAINS = {"account"}


def semantic_label(label_source: str, y) -> str:
    """Map (label_source, authenticity_label) to a semantic class."""
    if pd.isna(y) or label_source == "none":
        return "unknown"
    y = int(y)
    if label_source == "io_disclosure":
        return "state_io"
    if label_source in ("column:human_or_ai", "column:label"):
        return "ai_generated" if y == 1 else "human"
    if label_source in ("filename", "column:is_fake"):
        return "fake" if y == 1 else "authentic"
    return "bot" if y == 1 else "human"   # tsv/cresci/is_bot_flag/Label(1=human)


def _pct(n, d) -> float:
    return round(100 * n / d, 2) if d else 0.0


def compute_stats(df: pd.DataFrame) -> dict:
    n = len(df)
    df = df.copy()
    df["semantic"] = [semantic_label(s, y) for s, y in
                      zip(df["label_source"], df["authenticity_label"])]

    # 1-2 label distributions
    auth = df["authenticity_label"]
    authenticity = {"authentic(0)": int((auth == 0).sum()),
                    "inauthentic(1)": int((auth == 1).sum()),
                    "unknown(null)": int(auth.isna().sum())}
    semantic = {k: int(v) for k, v in df["semantic"].value_counts().items()}
    requested = {b: int((df["semantic"] == b).sum())
                 for b in ["human", "bot", "fake", "authentic", "unknown"]}
    additional = {b: int((df["semantic"] == b).sum())
                  for b in ["ai_generated", "state_io"]}

    # 3 dataset contribution
    contrib = [{"dataset": k, "rows": int(v), "pct": _pct(v, n)}
               for k, v in df["dataset"].value_counts().items()]

    # 4 feature availability
    fields = {c: _pct(df[c].notna().sum(), n) for c in df.columns if c != "semantic"}
    # numeric keys inside numeric_features_json
    numkeys: Counter = Counter()
    n_numeric_rows = 0
    for s in df["numeric_features_json"].dropna():
        try:
            d = json.loads(s)
        except (TypeError, ValueError):
            continue
        n_numeric_rows += 1
        numkeys.update(d.keys())
    numeric_key_freq = {k: {"rows": int(v), "pct_of_corpus": _pct(v, n)}
                        for k, v in numkeys.most_common(40)}
    # grain-aware completeness
    txt = df[df["grain"].isin(TEXT_GRAINS)]
    acct = df[df["grain"].isin(ACCOUNT_GRAINS)]
    grain_completeness = {
        "text_in_text_grains_pct": _pct(txt["text"].notna().sum(), len(txt)),
        "numeric_in_account_grains_pct": _pct(acct["numeric_features_json"].notna().sum(), len(acct)),
        "label_overall_pct": _pct(auth.notna().sum(), n),
    }

    # 5 duplicates
    content_cols = ["dataset", "grain", "domain", "text", "author_id",
                    "authenticity_label", "numeric_features_json"]
    content_dups = int(df.duplicated(subset=content_cols).sum())
    full_dups = int(df.duplicated(subset=[c for c in df.columns
                                          if c not in ("record_id", "semantic")]).sum())
    rid_dups = int(df["record_id"].duplicated().sum())
    authored = df[df["author_id"].notna()]
    distinct_authors = int(authored["author_id"].nunique())
    author_rows = int(len(authored))
    per_author = authored.groupby("author_id").size()
    authors_multi_dataset = int((authored.groupby("author_id")["dataset"].nunique() > 1).sum())
    duplicates = {
        "record_id_duplicates": rid_dups,
        "exact_full_row_duplicates": full_dups,
        "content_duplicates": content_dups,
        "content_duplicate_pct": _pct(content_dups, n),
        "authored_rows": author_rows,
        "distinct_authors": distinct_authors,
        "rows_per_author_mean": round(author_rows / distinct_authors, 2) if distinct_authors else 0,
        "max_rows_single_author": int(per_author.max()) if len(per_author) else 0,
        "authors_in_multiple_datasets": authors_multi_dataset,
    }

    # 6 class imbalance
    labeled = auth.dropna()
    pos = int((labeled == 1).sum())
    neg = int((labeled == 0).sum())
    no_io = df[df["label_source"] != "io_disclosure"]["authenticity_label"].dropna()
    imbalance = {
        "labeled_rows": int(len(labeled)),
        "positive_inauthentic": pos, "negative_authentic": neg,
        "positive_pct_of_labeled": _pct(pos, len(labeled)),
        "imbalance_ratio_pos_to_neg": round(pos / neg, 2) if neg else None,
        "majority_baseline_accuracy_pct": _pct(max(pos, neg), len(labeled)),
        "positives_from_io": int((df["label_source"] == "io_disclosure").sum()),
        "io_share_of_positives_pct": _pct((df["label_source"] == "io_disclosure").sum(), pos),
        "excluding_io": {
            "labeled": int(len(no_io)), "positive": int((no_io == 1).sum()),
            "negative": int((no_io == 0).sum()),
            "positive_pct": _pct(int((no_io == 1).sum()), len(no_io)),
        },
        "by_grain": {g: {"0": int(((df["grain"] == g) & (auth == 0)).sum()),
                         "1": int(((df["grain"] == g) & (auth == 1)).sum()),
                         "null": int(((df["grain"] == g) & auth.isna()).sum())}
                     for g in df["grain"].unique()},
        "by_domain": {d: {"0": int(((df["domain"] == d) & (auth == 0)).sum()),
                          "1": int(((df["domain"] == d) & (auth == 1)).sum()),
                          "null": int(((df["domain"] == d) & auth.isna()).sum())}
                      for d in df["domain"].unique()},
    }

    # username-shortcut presence
    shortcut_rows = 0
    for s in df["numeric_features_json"].dropna():
        try:
            if USERNAME_SHORTCUT & set(json.loads(s).keys()):
                shortcut_rows += 1
        except (TypeError, ValueError):
            pass

    return {
        "total_rows": n,
        "authenticity_distribution": authenticity,
        "semantic_distribution": semantic,
        "requested_buckets": requested,
        "additional_buckets": additional,
        "dataset_contribution": contrib,
        "feature_availability_pct": fields,
        "grain_completeness": grain_completeness,
        "numeric_key_frequency": numeric_key_freq,
        "duplicates": duplicates,
        "class_imbalance": imbalance,
        "username_shortcut_rows": shortcut_rows,
    }


def render_report(s: dict) -> str:
    im = s["class_imbalance"]
    dup = s["duplicates"]
    L = [
        "# Omi Corpus Audit (OMI_CORPUS_AUDIT_V1)", "",
        "> Read-only audit of `ml/corpus/data/merged_corpus.parquet` "
        "(`ml/corpus/audit.py`). No data modified, no training, no production change.",
        "",
        f"## 1. Total rows: **{s['total_rows']:,}**",
        "",
        "## 2. Label distribution",
        "### Authenticity (normalized)",
        "| class | rows | % |", "|---|---|---|",
    ]
    n = s["total_rows"]
    for k, v in s["authenticity_distribution"].items():
        L.append(f"| {k} | {v:,} | {_pct(v, n)} |")
    L += ["", "### Requested semantic buckets", "| label | rows | % |", "|---|---|---|"]
    for k, v in {**s["requested_buckets"], **s["additional_buckets"]}.items():
        L.append(f"| {k} | {v:,} | {_pct(v, n)} |")
    L += ["", "_human/authentic → authenticity 0; bot/fake/ai_generated/state_io → 1; "
          "unknown → null. ai_generated & state_io are the additional labels._", "",
          "## 3. Dataset contribution", "| dataset | rows | % |", "|---|---|---|"]
    for c in s["dataset_contribution"][:25]:
        L.append(f"| `{c['dataset']}` | {c['rows']:,} | {c['pct']} |")
    if len(s["dataset_contribution"]) > 25:
        L.append(f"| _… {len(s['dataset_contribution']) - 25} more_ | | |")

    L += ["", "## 4. Feature availability (% of rows populated)",
          "| field | % populated |", "|---|---|"]
    for k, v in s["feature_availability_pct"].items():
        L.append(f"| `{k}` | {v} |")
    gc = s["grain_completeness"]
    L += ["", "**Grain-aware completeness:** "
          f"text present in {gc['text_in_text_grains_pct']}% of text-grain rows; "
          f"numeric features in {gc['numeric_in_account_grains_pct']}% of account-grain rows; "
          f"labels on {gc['label_overall_pct']}% of all rows.",
          "", "**Mostly-missing / absent:** `lang` "
          f"({s['feature_availability_pct'].get('lang')}%); engine detector/score features "
          "are **entirely absent** (the engine was never run over these accounts) — the "
          "single biggest feature gap.", "",
          "Top numeric feature keys (inside `numeric_features_json`):",
          "| key | rows | % of corpus |", "|---|---|---|"]
    for k, v in list(s["numeric_key_frequency"].items())[:15]:
        L.append(f"| `{k}` | {v['rows']:,} | {v['pct_of_corpus']} |")

    L += ["", "## 5. Duplicate analysis",
          f"- Exact full-row duplicates: **{dup['exact_full_row_duplicates']}**",
          f"- Content duplicates (same dataset/grain/text/author/label/features): "
          f"**{dup['content_duplicates']}** ({dup['content_duplicate_pct']}%)",
          f"- `record_id` collisions: {dup['record_id_duplicates']}",
          f"- Authored rows: {dup['authored_rows']:,} across **{dup['distinct_authors']:,}** "
          f"distinct authors → mean {dup['rows_per_author_mean']} rows/author "
          f"(max {dup['max_rows_single_author']:,}). Authors in >1 dataset: "
          f"{dup['authors_in_multiple_datasets']}.",
          "- **Implication:** heavy author repetition (IO tweet streams) → any tweet-grain "
          "training MUST use group-aware (by-author) splits to avoid leakage.", "",
          "## 6. Class imbalance",
          f"- Labeled rows: **{im['labeled_rows']:,}** "
          f"({im['positive_inauthentic']:,} inauthentic / {im['negative_authentic']:,} "
          f"authentic) → **{im['positive_pct_of_labeled']}% positive**, ratio "
          f"{im['imbalance_ratio_pos_to_neg']}:1.",
          f"- Majority-class baseline accuracy = **{im['majority_baseline_accuracy_pct']}%** "
          "→ accuracy is misleading; use balanced metrics (F1/AUC/Brier).",
          f"- **{im['io_share_of_positives_pct']}% of positives are IO** "
          f"({im['positives_from_io']:,} state_io tweets). **Excluding IO**, the labeled "
          f"slice is {im['excluding_io']['positive']:,} pos / {im['excluding_io']['negative']:,} "
          f"neg = **{im['excluding_io']['positive_pct']}% positive — near-balanced.**",
          "", "### Balance by domain", "| domain | authentic(0) | inauthentic(1) | unknown |",
          "|---|---|---|---|"]
    for d, b in im["by_domain"].items():
        L.append(f"| {d} | {b['0']:,} | {b['1']:,} | {b['null']:,} |")
    L += ["", "### Balance by grain", "| grain | authentic(0) | inauthentic(1) | unknown |",
          "|---|---|---|---|"]
    for g, b in im["by_grain"].items():
        L.append(f"| {g} | {b['0']:,} | {b['1']:,} | {b['null']:,} |")

    L += ["", "## 7. Datasets / slices to EXCLUDE before training",
          "1. **`activity_botscore` (reference, 1,000 rows, no labels)** — unlabeled; "
          "exclude from supervised training (calibration only).",
          "2. **Coordination / IO tweets (27,702 rows, all label=1, tweet grain, no in-domain "
          "negatives)** — exclude from any account-authenticity model: wrong grain, drives the "
          "90% imbalance, and cannot train IO-vs-legitimate without legitimate-coordination "
          "negatives (the `known-mixed` gap).",
          "3. **AI-text unlabeled rows (~170)** — drop rows with null label.",
          "4. **`real_users` / `fake_users` (source↔label confound + degraded, partly-zeroed "
          "metadata)** — use with strong caution or hold out; never expose `source`/origin as a "
          "feature.",
          f"5. **Username-morphology features** (present in {s['username_shortcut_rows']:,} rows' "
          "`numeric_features_json`) — drop before training (V2 audit shortcut).",
          "", "## 8. Recommendation — is the corpus ready for V1 training?",
          "**Not ready as a single cross-grain authenticity model; conditionally usable "
          "per-grain.**",
          "", "| candidate model | usable slice | verdict |", "|---|---|---|",
          "| One model over the whole corpus | — | ❌ No — mixes account/tweet/comment/text "
          "grains and is 90% IO-positive |",
          "| Account-authenticity V1 | ~3,000 labeled account rows (fsm + user dumps) | "
          "⚠️ Marginal — metadata-only, source-confounded, shortcut-laden |",
          "| Coordination/IO | 27.7k IO tweets, **0 negatives** | ❌ No — needs "
          "legitimate-coordination negatives |",
          "| AI-text classifier | ~1,516 labeled (855 human / 661 ai) | ✅ Baseline-viable "
          "(small, near-balanced) |",
          "| Bot classifier | ~2,537 labeled (990 human / 1,547 bot) | ✅ Baseline-viable |",
          "",
          "**Bottom line:** the corpus is a sound, well-governed *standardized substrate*, but "
          "**not** ready for a production V1 authenticity model. Train **per-grain**, exclude the "
          "slices in §7, use **group-aware (by-author) splits** and **balanced metrics**, and "
          "note the encouraging finding that the **non-IO labeled slice is near-balanced**. The "
          "highest-value unlocks remain unchanged from prior audits: **engine-derived features** "
          "(populate the absent detector/fingerprint signal) and **engine-independent labels + "
          "legitimate-coordination negatives**.",
          "",
    ]
    return "\n".join(L)


def main(argv=None) -> int:
    if not CORPUS_PATH.is_file():
        print(f"FAIL: corpus not found at {CORPUS_PATH} — run omi_corpus.py --build first.")
        return 1
    df = pd.read_parquet(CORPUS_PATH)
    stats = compute_stats(df)
    STATS_PATH.write_text(json.dumps(stats, indent=2) + "\n", encoding="utf-8")
    REPORT_PATH.write_text(render_report(stats), encoding="utf-8")
    im = stats["class_imbalance"]
    print(f"Audited {stats['total_rows']:,} rows -> {REPORT_PATH.name}, {STATS_PATH.name}")
    print(f"Labeled {im['labeled_rows']:,} ({im['positive_pct_of_labeled']}% positive; "
          f"excl-IO {im['excluding_io']['positive_pct']}%). "
          f"Recommendation: per-grain, not single-model. See report §8.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
