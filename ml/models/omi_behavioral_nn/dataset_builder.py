"""Dataset builder for the Omi Behavioral NN — OMI_FEATURE_SCHEMA_V1 contract.

Torch-free core (importable + testable without PyTorch): it maps a feature dict
to the canonical, ordered 42-dim vector defined by
``ml/features/OMI_FEATURE_SCHEMA_V1.md`` (== ``apps/api/app/ml/features.py``
``build_feature_vector``, ``FEATURE_SCHEMA_VERSION = 1``). The thin PyTorch
wrappers (``BehavioralDataset``, ``to_tensor``) import torch lazily.

Contract (append-only; reorder/remove breaks artifacts):
  21 fingerprint (fp_*) + 16 detector (det_<d>_{probability,confidence}) + 5
  metadata (meta_*) = 42 dims, all normalized to [0, 1].
  An absent detector defaults to (probability=0.5, confidence=0.0).
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import math
import sys
import tomllib
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

FEATURE_SCHEMA_VERSION = 1

# --- A1 fingerprint (21) — name -> raw (lo, hi) normalization range ----------- #
FINGERPRINT_RANGES: dict[str, tuple[float, float]] = {
    "fp_interval_cov": (0.0, 2.0),
    "fp_quiet_hours": (0.0, 12.0),
    "fp_burst_ratio": (0.0, 30.0),
    "fp_peak_hourly_rate": (0.0, 30.0),
    "fp_mean_cosine": (0.0, 1.0),
    "fp_top_cluster_mass": (0.0, 1.0),
    "fp_mean_ngram_jaccard": (0.0, 1.0),
    "fp_burstiness": (0.0, 1.2),
    "fp_hedge_rate": (0.0, 0.5),
    "fp_em_dash_rate": (0.0, 1.0),
    "fp_sentence_start_rep": (0.0, 1.0),
    "fp_handle_entropy": (0.0, 5.0),
    "fp_posts_per_day": (0.0, 100.0),
    "fp_follower_ratio_log": (-3.0, 3.0),
    "fp_bio_quality": (0.0, 30.0),
    "fp_emoji_density": (0.0, 0.30),
    "fp_url_inclusion_rate": (0.0, 1.0),
    "fp_emoji_burst_rate": (0.0, 1.0),
    "fp_engagement_bait_rate": (0.0, 0.50),
    "fp_overall_probability": (0.0, 1.0),
    "fp_confidence": (0.0, 1.0),
}
FINGERPRINT_FEATURES: list[str] = list(FINGERPRINT_RANGES)

# --- A2 detector block (16) — 8 detectors x (probability, confidence) -------- #
DETECTOR_NAMES: list[str] = [
    "temporal", "semantic", "ai_writing", "voice",
    "engagement", "profile", "memory", "coordination",
]
DETECTOR_FEATURES: list[str] = [
    f"det_{d}_{attr}" for d in DETECTOR_NAMES for attr in ("probability", "confidence")
]

# --- A3 metadata (5) — log1p-normalized to [0,1]; meta_verified in {0,1} ------ #
METADATA_FEATURES: list[str] = [
    "meta_log_followers", "meta_log_following", "meta_log_account_age_days",
    "meta_verified", "meta_log_post_count",
]

FEATURE_NAMES: list[str] = FINGERPRINT_FEATURES + DETECTOR_FEATURES + METADATA_FEATURES
INPUT_DIM: int = len(FEATURE_NAMES)  # 42
BLOCKS: dict[str, int] = {"fingerprint": 21, "detectors": 16, "metadata": 5}

# Schema defaults for absent values: detector probability -> 0.5, else 0.0.
DEFAULTS: dict[str, float] = {
    name: (0.5 if name in DETECTOR_FEATURES and name.endswith("_probability") else 0.0)
    for name in FEATURE_NAMES
}

assert INPUT_DIM == 42, f"feature schema must be 42-dim, got {INPUT_DIM}"
assert sum(BLOCKS.values()) == INPUT_DIM


def normalize_fingerprint(raw: dict[str, float]) -> dict[str, float]:
    """Min-max normalize raw fingerprint values into [0, 1] per FINGERPRINT_RANGES."""
    out: dict[str, float] = {}
    for name, (lo, hi) in FINGERPRINT_RANGES.items():
        if name in raw and raw[name] is not None:
            span = hi - lo or 1.0
            out[name] = float(min(1.0, max(0.0, (float(raw[name]) - lo) / span)))
    return out


def build_vector(features: dict[str, float]) -> list[float]:
    """Assemble the ordered 42-dim vector; absent values use the schema DEFAULTS."""
    vec = [float(features.get(name, DEFAULTS[name])) for name in FEATURE_NAMES]
    if len(vec) != INPUT_DIM:  # pragma: no cover - guarded by construction
        raise ValueError(f"expected {INPUT_DIM} features, built {len(vec)}")
    return vec


def vectorize_many(rows: list[dict[str, float]]) -> np.ndarray:
    """Stack many feature dicts into an (N, 42) float32 matrix."""
    if not rows:
        return np.empty((0, INPUT_DIM), dtype=np.float32)
    return np.asarray([build_vector(r) for r in rows], dtype=np.float32)


def synthetic_batch(n: int = 64, seed: int = 0) -> tuple[np.ndarray, np.ndarray]:
    """Schema-shaped RANDOM data for wiring/smoke checks only — NOT training data.

    Returns (X[n,42] in [0,1], y[n] in {0,1}). Architecture-only; carries no real
    signal and must never be used to train a real model.
    """
    rng = np.random.default_rng(seed)
    X = rng.random((n, INPUT_DIM), dtype=np.float32)
    y = (rng.random(n) < 0.5).astype(np.float32)
    return X, y


# --------------------------------------------------------------------------- #
# Thin PyTorch wrappers (torch imported lazily so the core stays torch-free).
# --------------------------------------------------------------------------- #
def to_tensor(matrix: np.ndarray):
    """Convert an (N, 42) array to a CPU float32 torch tensor."""
    import torch
    return torch.as_tensor(np.asarray(matrix, dtype=np.float32))


def make_dataset(X: np.ndarray, y: np.ndarray):
    """Build a torch TensorDataset from feature/label arrays (CPU)."""
    import torch
    from torch.utils.data import TensorDataset
    return TensorDataset(
        torch.as_tensor(np.asarray(X, dtype=np.float32)),
        torch.as_tensor(np.asarray(y, dtype=np.float32)).reshape(-1, 1),
    )


# =========================================================================== #
# Trainable-dataset pipeline (OMI_BEHAVIORAL_NEURAL_NETWORK_V1_DATASET_BUILDER)
#
# Ingests the approved authenticity datasets, maps their RAW account attributes
# into the 42-dim OMI_FEATURE_SCHEMA_V1 vector + a unified `authenticity_label`
# (0=authentic, 1=inauthentic), dedups, splits, and writes train/validation/test
# parquet + dataset_report.md. No training; no production/scoring change.
#
# Honest coverage limits (see the report): these datasets carry no engine
# detector outputs (detector block stays at the schema default 0.5/0.0) and the
# username-morphology family is EXCLUDED by policy (behavioral V2 audit shortcut).
# =========================================================================== #
REPO_ROOT = Path(__file__).resolve().parents[3]
GOVERNANCE = REPO_ROOT / "datasets" / "manifest.toml"
NN_DIR = Path(__file__).resolve().parent
DATA_DIR = NN_DIR / "data"
REPORT_PATH = NN_DIR / "dataset_report.md"
AUTH_LABEL = "authenticity_label"

# Excluded from features by policy — the username-morphology shortcut (V2 audit).
USERNAME_SHORTCUT_COLUMNS = [
    "username", "username_length", "username_randomness", "digits_count",
    "digit_ratio", "special_char_count", "repeat_char_count",
]
_FOLLOW_CAP = 1e7
_POST_CAP = 1e6
_AGE_CAP = 7300.0  # ~20 years
_TW_FMT = "%a %b %d %H:%M:%S %z %Y"
_SNAPSHOT = datetime(2023, 6, 1, tzinfo=timezone.utc)


@dataclass
class Source:
    name: str
    path: str            # relative to repo root
    adapter: str         # key into ADAPTERS
    label_mode: str      # "column:<col>" | "const:0" | "const:1"
    id_col: str


SOURCES: list[Source] = [
    Source("fake_social_media_global_2.0",
           "datasets/Datasets/Fake Social Media Account Detection Dataset/fake_social_media_global_2.0.csv",
           "global", "column:is_fake", "username"),
    Source("real_users",
           "datasets/Datasets/Fake Social Media Account Detection Dataset/real_users.csv",
           "userdump", "const:0", "screen_name"),
    Source("fake_users",
           "datasets/Datasets/Fake Social Media Account Detection Dataset/fake_users.csv",
           "userdump", "const:1", "screen_name"),
]

# Documented raw -> OMI_FEATURE_SCHEMA_V1 mapping (for the report).
MAPPING_NOTES: dict[str, dict[str, str]] = {
    "global": {
        "meta_log_followers": "log1p(followers)/log1p(1e7)",
        "meta_log_following": "log1p(following)/log1p(1e7)",
        "meta_log_account_age_days": "log1p(account_age_days)/log1p(7300)",
        "meta_verified": "verified>0.5",
        "meta_log_post_count": "log1p(posts)/log1p(1e6)",
        "fp_posts_per_day": "posts_per_day/100 (clip)",
        "fp_follower_ratio_log": "norm(log10(follower_following_ratio), -3..3)",
        "fp_mean_cosine": "caption_similarity_score",
        "fp_top_cluster_mass": "content_similarity_score",
    },
    "userdump": {
        "meta_log_followers": "log1p(followers_count)/log1p(1e7)",
        "meta_log_following": "log1p(friends_count)/log1p(1e7)",
        "meta_log_account_age_days": "log1p(age days from created_at/updated)/log1p(7300)",
        "meta_verified": "verified>0.5",
        "meta_log_post_count": "log1p(statuses_count)/log1p(1e6)",
    },
}


def _f(row: dict, key: str) -> float | None:
    """Parse a numeric cell; return None for missing/empty/unparseable."""
    v = row.get(key)
    if v is None or str(v).strip() == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _to01(v: float | None) -> float | None:
    return None if v is None else (1.0 if v > 0.5 else 0.0)


def _log_norm(x: float | None, cap: float) -> float | None:
    if x is None:
        return None
    return min(1.0, max(0.0, math.log1p(max(x, 0.0)) / math.log1p(cap)))


def _ratio_norm(x: float | None) -> float | None:
    if x is None or x <= 0:
        return None
    val = max(-3.0, min(3.0, math.log10(x)))
    return (val + 3.0) / 6.0


def _parse_dt(s: str | None):
    if not s or not str(s).strip():
        return None
    for fmt in (_TW_FMT, "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            d = datetime.strptime(str(s).strip(), fmt)
            return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _age_days(created: str | None, updated: str | None) -> float | None:
    c = _parse_dt(created)
    if c is None:
        return None
    u = _parse_dt(updated) or _SNAPSHOT
    days = (u - c).days
    return float(days) if days > 0 else None


def _clip01(x: float | None) -> float | None:
    return None if x is None else min(1.0, max(0.0, x))


def _adapt_global(row: dict) -> dict[str, float]:
    out = {
        "meta_log_followers": _log_norm(_f(row, "followers"), _FOLLOW_CAP),
        "meta_log_following": _log_norm(_f(row, "following"), _FOLLOW_CAP),
        "meta_log_account_age_days": _log_norm(_f(row, "account_age_days"), _AGE_CAP),
        "meta_verified": _to01(_f(row, "verified")),
        "meta_log_post_count": _log_norm(_f(row, "posts"), _POST_CAP),
        "fp_posts_per_day": _clip01((_f(row, "posts_per_day") or 0.0) / 100.0)
        if _f(row, "posts_per_day") is not None else None,
        "fp_follower_ratio_log": _ratio_norm(_f(row, "follower_following_ratio")),
        "fp_mean_cosine": _clip01(_f(row, "caption_similarity_score")),
        "fp_top_cluster_mass": _clip01(_f(row, "content_similarity_score")),
    }
    return {k: v for k, v in out.items() if v is not None}


def _adapt_userdump(row: dict) -> dict[str, float]:
    out = {
        "meta_log_followers": _log_norm(_f(row, "followers_count"), _FOLLOW_CAP),
        "meta_log_following": _log_norm(_f(row, "friends_count"), _FOLLOW_CAP),
        "meta_verified": _to01(_f(row, "verified")),
        "meta_log_post_count": _log_norm(_f(row, "statuses_count"), _POST_CAP),
        "meta_log_account_age_days": _log_norm(
            _age_days(row.get("created_at"), row.get("updated")), _AGE_CAP),
    }
    return {k: v for k, v in out.items() if v is not None}


ADAPTERS = {"global": _adapt_global, "userdump": _adapt_userdump}


def _resolve_label(src: Source, row: dict) -> int | None:
    if src.label_mode.startswith("const:"):
        return int(src.label_mode.split(":")[1])
    col = src.label_mode.split(":", 1)[1]
    v = _f(row, col)
    return None if v is None else int(v > 0.5)


def _read_csv(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def _governance_status(rel_path: str, governance_path: Path) -> str | None:
    if not governance_path.is_file():
        return None
    gov = tomllib.loads(governance_path.read_text(encoding="utf-8"))
    rel = rel_path[len("datasets/"):] if rel_path.startswith("datasets/") else rel_path
    for f in gov.get("file", []):
        if f["path"] == rel:
            return f["status"].lower()
    return None


def _split(df, seed: int, fracs: tuple[float, float, float]) -> dict:
    """Group-aware stratified split by identity_hash (no identity spans splits)."""
    rng = np.random.default_rng(seed)
    by_id = df.groupby("identity_hash")[AUTH_LABEL].mean().round().astype(int)
    ids, labels = by_id.index.to_numpy(), by_id.to_numpy()
    assign: dict[str, str] = {}
    for lab in (0, 1):
        sel = ids[labels == lab].copy()
        rng.shuffle(sel)
        n = len(sel)
        n_tr, n_va = int(n * fracs[0]), int(n * fracs[1])
        for i, idh in enumerate(sel):
            assign[idh] = "train" if i < n_tr else "validation" if i < n_tr + n_va else "test"
    s = df["identity_hash"].map(assign)
    return {name: df[s == name].reset_index(drop=True) for name in ("train", "validation", "test")}


def _leakage_checks(splits: dict) -> dict:
    sets_id = {k: set(v["identity_hash"]) for k, v in splits.items()}
    sets_fh = {k: set(v["feature_hash"]) for k, v in splits.items()}
    pairs = [("train", "validation"), ("train", "test"), ("validation", "test")]
    id_overlap = sum(len(sets_id[a] & sets_id[b]) for a, b in pairs)
    fh_overlap = sum(len(sets_fh[a] & sets_fh[b]) for a, b in pairs)
    return {"cross_split_identity_overlap": id_overlap,
            "cross_split_feature_hash_overlap": fh_overlap}


def build_dataset(sources: list[Source] = None, repo_root: Path = REPO_ROOT,
                  out_dir: Path = DATA_DIR, report_path: Path = REPORT_PATH,
                  governance_path: Path = GOVERNANCE, seed: int = 42,
                  splits: tuple[float, float, float] = (0.7, 0.15, 0.15)) -> dict:
    import pandas as pd

    sources = sources if sources is not None else SOURCES
    records: list[dict] = []
    per_source: dict[str, dict] = {}
    populated: dict[str, Counter] = {}

    for src in sources:
        path = repo_root / src.path
        gstat = _governance_status(src.path, governance_path)
        if gstat in ("archive", "quarantine"):
            raise SystemExit(f"governance veto: {src.name} status={gstat} — refusing to ingest")
        rows = _read_csv(path)
        adapter = ADAPTERS[src.adapter]
        pop: Counter = Counter()
        label_counts: Counter = Counter()
        n = 0
        for r in rows:
            label = _resolve_label(src, r)
            if label is None:
                continue
            fdict = adapter(r)
            vec = build_vector(fdict)
            ident = str(r.get(src.id_col, "")).strip()
            fhash = hashlib.sha1(np.asarray(vec, dtype=np.float32).tobytes()).hexdigest()[:16]
            idhash = (hashlib.sha1(f"{src.name}:{ident}".encode()).hexdigest()[:16]
                      if ident else fhash)
            rec = {name: vec[i] for i, name in enumerate(FEATURE_NAMES)}
            rec.update({AUTH_LABEL: int(label), "source": src.name,
                        "identity_hash": idhash, "feature_hash": fhash,
                        "coverage": sum(1 for k in fdict if k in FEATURE_NAMES)})
            records.append(rec)
            for k in fdict:
                if k in FEATURE_NAMES:
                    pop[k] += 1
            label_counts[int(label)] += 1
            n += 1
        per_source[src.name] = {"rows": n, "label_0": label_counts[0],
                                "label_1": label_counts[1], "governance": gstat}
        populated[src.name] = pop

    df = pd.DataFrame.from_records(records)
    before = len(df)
    df = df.drop_duplicates(subset=FEATURE_NAMES).reset_index(drop=True)
    dup_removed = before - len(df)
    identity_dups = int(df["identity_hash"].duplicated().sum())

    parts = _split(df, seed, splits)
    leak = _leakage_checks(parts)

    out_dir.mkdir(parents=True, exist_ok=True)
    cols = FEATURE_NAMES + [AUTH_LABEL, "source", "identity_hash"]
    for name, part in parts.items():
        part[cols].to_parquet(out_dir / f"{name}.parquet", index=False)

    report = _assemble_report(df, parts, per_source, populated, dup_removed,
                              identity_dups, leak, out_dir)
    report_path.write_text(report, encoding="utf-8")

    return {
        "total": len(df), "dup_removed": dup_removed,
        "train": len(parts["train"]), "validation": len(parts["validation"]),
        "test": len(parts["test"]), "leakage": leak,
        "label_balance": {int(k): int(v) for k, v in df[AUTH_LABEL].value_counts().items()},
    }


def _assemble_report(df, parts, per_source, populated, dup_removed, identity_dups,
                     leak, out_dir) -> str:
    total = len(df)
    pos = int(df[AUTH_LABEL].sum())
    neg = total - pos
    try:
        art = out_dir.relative_to(REPO_ROOT)
    except ValueError:
        art = out_dir
    L = [
        "# Omi Behavioral NN — Dataset Report (V1)",
        "",
        "> Auto-generated by `ml/datasets`… `ml/models/omi_behavioral_nn/dataset_builder.py "
        "--build`. First trainable corpus for OmiBehavioralNet. No training performed.",
        "",
        f"**Unified schema:** {INPUT_DIM}-dim OMI_FEATURE_SCHEMA_V1 vector + "
        f"`{AUTH_LABEL}` (0=authentic, 1=inauthentic) + provenance "
        "(`source`, `identity_hash`).",
        "",
        "## A. Source counts",
        "| source | rows | authentic (0) | inauthentic (1) | governance |",
        "|---|---|---|---|---|",
    ]
    for name, s in per_source.items():
        L.append(f"| `{name}` | {s['rows']} | {s['label_0']} | {s['label_1']} | {s['governance']} |")
    L += [
        "",
        "## B. Label counts & class balance",
        f"- Total rows (post-dedup): **{total}**",
        f"- authentic (0): **{neg}** ({neg/total:.1%}) · inauthentic (1): **{pos}** ({pos/total:.1%})",
        "",
        "### Per-split row & label counts (C. Row counts)",
        "| split | rows | label 0 | label 1 |",
        "|---|---|---|---|",
    ]
    for name in ("train", "validation", "test"):
        p = parts[name]
        L.append(f"| {name} | {len(p)} | {int((p[AUTH_LABEL]==0).sum())} | "
                 f"{int((p[AUTH_LABEL]==1).sum())} |")
    L += [
        "",
        "## Duplicates",
        f"- Exact feature-vector duplicates removed: **{dup_removed}**",
        f"- Repeated identities remaining (post-dedup): **{identity_dups}**",
        "",
        "## Missing values / feature coverage",
        "Per-block share of rows with a NON-default (populated) value. The detector "
        "block is entirely schema-default because these datasets carry no engine "
        "detector outputs (the engine was not run).",
        "",
        "| block | dims | populated dims | note |",
        "|---|---|---|---|",
    ]
    all_pop = Counter()
    for c in populated.values():
        all_pop.update(c)
    fp_pop = sum(1 for k in FINGERPRINT_FEATURES if all_pop.get(k, 0) > 0)
    det_pop = sum(1 for k in DETECTOR_FEATURES if all_pop.get(k, 0) > 0)
    meta_pop = sum(1 for k in METADATA_FEATURES if all_pop.get(k, 0) > 0)
    L += [
        f"| fingerprint | 21 | {fp_pop} | partial — only aggregate behavioral proxies map |",
        f"| detectors | 16 | {det_pop} | **0 — schema default (0.5/0.0); engine not run** |",
        f"| metadata | 5 | {meta_pop} | followers/following/age/verified/post count |",
        "",
        f"Populated-feature counts are over the **{sum(s['rows'] for s in per_source.values())} "
        f"ingested rows** (pre-dedup; {dup_removed} exact-duplicate vectors removed → "
        f"{total} unique rows):",
        "",
        "| feature | rows populated |",
        "|---|---|",
    ]
    for name in FEATURE_NAMES:
        if all_pop.get(name, 0) > 0:
            L.append(f"| `{name}` | {all_pop[name]} |")
    L += [
        "",
        "### Raw → schema mapping",
    ]
    for adapter_name, m in MAPPING_NOTES.items():
        L.append(f"- **{adapter_name}**: " + "; ".join(f"`{k}` ← {v}" for k, v in m.items()))
    L += [
        "",
        "## D. Leakage analysis",
        f"1. **Cross-split identity overlap:** {leak['cross_split_identity_overlap']} "
        "(group-aware split by `identity_hash`; **PASS** at 0).",
        f"2. **Cross-split feature-vector overlap:** {leak['cross_split_feature_hash_overlap']} "
        "(exact duplicates removed before splitting; **PASS** at 0).",
        "3. **Username-morphology shortcut EXCLUDED by policy** (behavioral V2 audit: "
        "~71% of V1 signal was username morphology and did not generalize). Excluded raw "
        f"columns: {', '.join('`'+c+'`' for c in USERNAME_SHORTCUT_COLUMNS)}.",
        "4. **Label columns excluded from features:** `is_fake` (global_2.0) is the label "
        "only; real/fake_users are filename-labeled. The label is engine-INDEPENDENT.",
        "5. **No engine-output circularity:** the detector block + engine prior are "
        "schema-default here (engine not run), so no engine verdict leaks into features.",
        "6. **Source↔label confound (WARNING):** `real_users`→0 and `fake_users`→1 are "
        "labeled by dataset origin, so any systematic collection/processing difference "
        "between those two dumps is confounded with the label. Their counts are also "
        "non-integer / partly zeroed (pre-processed), so their metadata signal is degraded.",
        "",
        "## Limitations & recommendation",
        "This V1 corpus is **metadata-dominated**: the 16 detector dims and most of the 21 "
        "fingerprint dims are unavailable without running the engine over account histories, "
        "and the anti-shortcut policy removes the (non-generalizing) username features. It is "
        "a working **pipeline + baseline corpus**, not a production-grade training set. The "
        "real unlock — per `ml/features/OMI_FEATURE_SCHEMA_V1.md` §C — is engine-feature "
        "extraction (populate `fp_*`/`det_*`) + engine-independent analyst labels. **Do not "
        "train a shipped model on this as-is.**",
        "",
        f"Artifacts: `{art}/` train.parquet · validation.parquet · test.parquet.",
        "",
    ]
    return "\n".join(L)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Build the OmiBehavioralNet V1 trainable dataset")
    p.add_argument("--build", action="store_true", help="build parquet splits + report")
    p.add_argument("--seed", type=int, default=42)
    args = p.parse_args(argv)
    if not args.build:
        print("Dataset pipeline ready. Run with --build to produce "
              "data/{train,validation,test}.parquet + dataset_report.md "
              "(no training is performed).")
        return 0
    summary = build_dataset(seed=args.seed)
    print(f"Built: total={summary['total']} (dedup -{summary['dup_removed']})  "
          f"train={summary['train']} val={summary['validation']} test={summary['test']}")
    print(f"Label balance: {summary['label_balance']}")
    print(f"Leakage checks: {summary['leakage']}")
    print(f"Report: {REPORT_PATH.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
