#!/usr/bin/env python3
"""OMI_DATASET_DISCOVERY_AND_NORMALIZATION_V1 — discover, profile, normalize.

Recursively scans the dataset directory, profiles every supported file (CSV, TSV,
JSON, JSONL, Parquet, ZIP-inspected), designs/implements a single unified Omi
record schema able to represent all grains (account / tweet / comment / text),
converts governance-approved datasets into it, and emits:
  - inventory.json / inventory.md      (per-file inventory)
  - schema_comparison.md               (how datasets differ)
  - data/merged_corpus.parquet         (normalized, governance-filtered, capped)
  - data_quality_report.md             (quality + leakage + unparseable)

Originals are never modified (read-only). No model training. ML/dataset tooling
only; no production/scoring change.

Key honesty: the unified schema carries an explicit `grain`/`domain` discriminator
so heterogeneous datasets coexist WITHOUT pretending they are one training
population — filter by grain before training. Governance excludes
archive/quarantine from the merge (poison stays out).
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import sys
import tomllib
import zipfile
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path

csv.field_size_limit(10_000_000)

REPO_ROOT = Path(__file__).resolve().parents[2]
DATASETS_ROOT = REPO_ROOT / "datasets"
GOVERNANCE = DATASETS_ROOT / "manifest.toml"
CORPUS_DIR = Path(__file__).resolve().parent
DATA_DIR = CORPUS_DIR / "data"

SCHEMA_VERSION = 1
SUPPORTED_EXTS = {".csv", ".tsv", ".json", ".jsonl", ".parquet", ".zip", ".xlsx"}
DATA_EXTS_IN_ZIP = {".csv", ".tsv", ".json", ".jsonl"}
SAMPLE_ROWS = 5000           # rows read for missing/dup/label profiling
EXACT_COUNT_MAX_BYTES = 50_000_000  # above this, row count is line-based (approx)
MAX_ROWS_PER_FILE = 1000     # per-file cap for the committed merged corpus
LABELISH = ["is_fake", "is_bot_flag", "is_bot", "Bot Label", "bot_type_label",
            "human_or_ai", "label", "Label"]
USERNAME_SHORTCUT = {"username", "username_length", "username_randomness", "digits_count",
                     "digit_ratio", "special_char_count", "repeat_char_count"}

# Unified Omi record fields (parquet columns).
RECORD_FIELDS = ["record_id", "dataset", "source_path", "domain", "grain", "text",
                 "author_id", "created_at", "lang", "authenticity_label", "label_raw",
                 "label_source", "numeric_features_json", "governance_status",
                 "schema_version"]


# --------------------------------------------------------------------------- #
# Governance
# --------------------------------------------------------------------------- #
def load_governance(path: Path = GOVERNANCE) -> dict:
    if not path.is_file():
        return {"files": {}, "dirs": []}
    gov = tomllib.loads(path.read_text(encoding="utf-8"))
    return {"files": {f["path"]: f["status"].lower() for f in gov.get("file", [])},
            "dirs": [(d["path"], d["status"].lower(),
                      d.get("provenance", ""), d.get("kind", "")) for d in gov.get("dir", [])]}


def governance_for(rel_to_datasets: str, gov: dict) -> tuple[str | None, str, str]:
    """Return (status, provenance, kind) for a datasets/-relative path."""
    if rel_to_datasets in gov["files"]:
        return gov["files"][rel_to_datasets], "", ""
    best = None
    for prefix, status, prov, kind in gov["dirs"]:
        if rel_to_datasets == prefix or rel_to_datasets.startswith(prefix + "/"):
            if best is None or len(prefix) > len(best[0]):
                best = (prefix, status, prov, kind)
    return (best[1], best[2], best[3]) if best else (None, "", "")


# --------------------------------------------------------------------------- #
# Profiling
# --------------------------------------------------------------------------- #
@dataclass
class FileInfo:
    dataset: str
    path: str                 # repo-root relative
    fmt: str
    row_count: int = 0
    row_count_method: str = "exact"
    columns: list[str] = field(default_factory=list)
    detected_labels: dict = field(default_factory=dict)
    missing_cells_pct: float = 0.0
    top_missing: dict = field(default_factory=dict)
    duplicate_rows_pct: float = 0.0
    governance_status: str = "undeclared"
    provenance: str = ""
    domain: str = "other"
    grain: str = "unknown"
    family: str = "none"
    parse_status: str = "ok"
    error: str = ""
    sampled: bool = False
    zip_members: list[str] = field(default_factory=list)


def _delim(fmt: str) -> str:
    return "\t" if fmt == "tsv" else ","


def _count_lines(path: Path) -> int:
    n = 0
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            n += chunk.count(b"\n")
    return n


def _row_count_tabular(path: Path, fmt: str, has_header: bool) -> tuple[int, str]:
    size = path.stat().st_size
    if size <= EXACT_COUNT_MAX_BYTES:
        with path.open("r", encoding="utf-8", errors="replace", newline="") as fh:
            n = sum(1 for _ in csv.reader(fh, delimiter=_delim(fmt)))
        return (max(0, n - (1 if has_header else 0)), "exact")
    approx = _count_lines(path)
    return (max(0, approx - (1 if has_header else 0)), "approx-line")


def _profile_rows(rows: list[list[str]], columns: list[str]) -> dict:
    """Missing %, duplicate %, and label distributions on a sampled row list."""
    if not rows:
        return {"missing_cells_pct": 0.0, "top_missing": {}, "duplicate_rows_pct": 0.0,
                "detected_labels": {}}
    n = len(rows)
    ncol = len(columns) or (len(rows[0]) if rows else 0)
    miss = Counter()
    seen = set()
    dups = 0
    label_idx = {c: columns.index(c) for c in LABELISH if c in columns}
    label_vals = {c: Counter() for c in label_idx}
    for r in rows:
        key = tuple(r)
        if key in seen:
            dups += 1
        else:
            seen.add(key)
        for i in range(min(ncol, len(r))):
            if r[i] is None or str(r[i]).strip() == "":
                miss[columns[i] if i < len(columns) else str(i)] += 1
        for c, i in label_idx.items():
            if i < len(r):
                label_vals[c][r[i]] += 1
    total_cells = n * ncol or 1
    top_missing = {k: v for k, v in sorted(miss.items(), key=lambda kv: -kv[1])[:5] if v}
    return {
        "missing_cells_pct": round(100 * sum(miss.values()) / total_cells, 2),
        "top_missing": top_missing,
        "duplicate_rows_pct": round(100 * dups / n, 2),
        "detected_labels": {c: dict(sorted(v.items(), key=lambda kv: -kv[1])[:8])
                            for c, v in label_vals.items()},
    }


def _read_tabular_sample(path: Path, fmt: str, limit: int):
    """Return (columns, rows[list[list]]) for up to `limit` data rows."""
    with path.open("r", encoding="utf-8", errors="replace", newline="") as fh:
        reader = csv.reader(fh, delimiter=_delim(fmt))
        try:
            header = next(reader)
        except StopIteration:
            return [], []
        rows = []
        for i, row in enumerate(reader):
            if i >= limit:
                break
            rows.append(row)
    return header, rows


def _looks_headerless(path: Path, fmt: str) -> bool:
    """Headerless id+label TSVs (astroturf/cresci): first field numeric id."""
    if fmt != "tsv":
        return False
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        first = fh.readline().strip().split("\t")
    return len(first) == 2 and first[0].isdigit()


# --------------------------------------------------------------------------- #
# Classification (family -> domain/grain)
# --------------------------------------------------------------------------- #
def classify(path: Path, columns: list[str], fmt: str, headerless: bool) -> tuple[str, str, str]:
    name = path.name.lower()
    cols = set(columns)
    if headerless:
        return "bot_tsv", "bot", "account"
    if fmt == "json" and "_tweets" in name and "cresci" in name:
        return "cresci_json", "bot", "tweet"
    if "tweetid" in cols and "userid" in cols:
        return "io_tweets", "coordination", "tweet"
    if "userid" in cols and "following_count" in cols:
        return "io_users", "coordination", "account"
    if "human_or_ai" in cols:
        return "ai_text_v1", "ai_text", "text"
    if "text_content" in cols and "label" in cols:
        return "ai_text_2026", "ai_text", "text"
    if "Tweet_text" in cols and "Label" in cols:
        return "twitterdata", "authenticity", "tweet"
    if "is_fake" in cols:
        return "fsm_profile", "authenticity", "account"
    if "is_bot_flag" in cols:
        return "reddit_comment", "bot", "comment"
    if "Bot Label" in cols:
        return "bot_detection", "bot", "account"
    if any("bot_score" in c for c in columns):   # e.g. bot_score_english
        return "reference", "reference", "account"
    if name in ("real_users.csv", "fake_users.csv"):
        return "userdump", "authenticity", "account"
    if name in ("twitterdata_fe.csv", "twitter_data.csv", "twitter_users.csv", "location_data.csv"):
        return "generic_account", "authenticity", "account"
    return "unknown", "other", "unknown"


# --------------------------------------------------------------------------- #
# Converters -> unified Omi records
# --------------------------------------------------------------------------- #
def _isfloat(v) -> bool:
    try:
        float(v)
        return True
    except (TypeError, ValueError):
        return False


def _numeric(row: dict, exclude: set) -> dict:
    return {k: float(v) for k, v in row.items()
            if k not in exclude and v not in (None, "") and _isfloat(v)}


def _auth_human_or_ai(v) -> int | None:
    s = str(v).strip().lower()
    if s in ("ai", "ai_generated", "machine", "generated", "1", "1.0", "fake"):
        return 1
    if s in ("human", "0", "0.0", "real", "authentic"):
        return 0
    return None


def _auth_botword(v) -> int | None:
    s = str(v).strip().lower()
    if "bot" in s or "spam" in s or "fake" in s:
        return 1
    if "human" in s or "genuine" in s or "real" in s:
        return 0
    return None


def _emit(idx, dataset, src, domain, grain, *, text=None, author_id=None,
          created_at=None, lang=None, label=None, label_raw=None, label_source="none",
          numeric=None, governance="undeclared") -> dict:
    rid = hashlib.sha1(
        f"{dataset}:{author_id or ''}:{(text or '')[:48]}:{idx}".encode()).hexdigest()[:16]
    return {
        "record_id": rid, "dataset": dataset, "source_path": src, "domain": domain,
        "grain": grain, "text": text, "author_id": (str(author_id) if author_id else None),
        "created_at": (str(created_at) if created_at else None), "lang": lang,
        "authenticity_label": (None if label is None else int(label)),
        "label_raw": (None if label_raw is None else str(label_raw)),
        "label_source": label_source,
        "numeric_features_json": (json.dumps(numeric, sort_keys=True) if numeric else None),
        "governance_status": governance, "schema_version": SCHEMA_VERSION,
    }


def _dict_rows(path: Path, fmt: str, cap: int):
    with path.open("r", encoding="utf-8", errors="replace", newline="") as fh:
        for i, row in enumerate(csv.DictReader(fh, delimiter=_delim(fmt))):
            if i >= cap:
                break
            yield i, row


def conv_io_tweets(path, info, cap, label_map=None):
    for i, r in _dict_rows(path, info.fmt, cap):
        yield _emit(i, info.dataset, info.path, "coordination", "tweet",
                    text=r.get("tweet_text"), author_id=r.get("userid"),
                    created_at=r.get("tweet_time"), lang=r.get("tweet_language"),
                    label=1, label_raw="state_io", label_source="io_disclosure",
                    numeric=_numeric({k: r.get(k) for k in ("follower_count", "following_count")}, set()),
                    governance=info.governance_status)


def conv_io_users(path, info, cap, label_map=None):
    for i, r in _dict_rows(path, info.fmt, cap):
        yield _emit(i, info.dataset, info.path, "coordination", "account",
                    text=r.get("user_profile_description"), author_id=r.get("userid"),
                    created_at=r.get("account_creation_date"), label=1, label_raw="state_io",
                    label_source="io_disclosure",
                    numeric=_numeric({k: r.get(k) for k in ("follower_count", "following_count")}, set()),
                    governance=info.governance_status)


def conv_ai_v1(path, info, cap, label_map=None):
    for i, r in _dict_rows(path, info.fmt, cap):
        yield _emit(i, info.dataset, info.path, "ai_text", "text", text=r.get("text"),
                    lang=r.get("language"), label=_auth_human_or_ai(r.get("human_or_ai")),
                    label_raw=r.get("human_or_ai"), label_source="column:human_or_ai",
                    governance=info.governance_status)


def conv_ai_2026(path, info, cap, label_map=None):
    for i, r in _dict_rows(path, info.fmt, cap):
        yield _emit(i, info.dataset, info.path, "ai_text", "text", text=r.get("text_content"),
                    label=_auth_human_or_ai(r.get("label")), label_raw=r.get("label"),
                    label_source="column:label", governance=info.governance_status)


def conv_twitterdata(path, info, cap, label_map=None):
    for i, r in _dict_rows(path, info.fmt, cap):
        raw = str(r.get("Label", "")).strip()
        label = 0 if raw in ("1", "1.0") else 1 if raw in ("0", "0.0") else None  # 1=human
        yield _emit(i, info.dataset, info.path, "authenticity", "tweet",
                    text=r.get("Tweet_text"), author_id=r.get("Twitter_Account"),
                    created_at=r.get("Tweet_created_at"), label=label, label_raw=raw,
                    label_source="column:Label(1=human)", governance=info.governance_status)


def conv_fsm(path, info, cap, label_map=None):
    excl = {"is_fake"}
    for i, r in _dict_rows(path, info.fmt, cap):
        v = r.get("is_fake")
        label = None if v in (None, "") or not _isfloat(v) else int(float(v) > 0.5)
        yield _emit(i, info.dataset, info.path, "authenticity", "account",
                    author_id=r.get("username"), label=label, label_raw=v,
                    label_source="column:is_fake", numeric=_numeric(r, excl),
                    governance=info.governance_status)


def conv_userdump(path, info, cap, label_map=None):
    label = 0 if info.dataset == "real_users" else 1
    excl = {"id", "name", "screen_name", "url", "description", "dataset", "lang",
            "time_zone", "location", "created_at", "updated"}
    for i, r in _dict_rows(path, info.fmt, cap):
        yield _emit(i, info.dataset, info.path, "authenticity", "account",
                    author_id=r.get("screen_name"), created_at=r.get("created_at"),
                    label=label, label_raw=info.dataset, label_source="filename",
                    numeric=_numeric(r, excl), governance=info.governance_status)


def conv_reddit(path, info, cap, label_map=None):
    excl = {"comment_id", "subreddit", "is_bot_flag", "bot_type_label"}
    for i, r in _dict_rows(path, info.fmt, cap):
        v = str(r.get("is_bot_flag", "")).strip().lower()
        label = 1 if v in ("true", "1", "1.0") else 0 if v in ("false", "0", "0.0") else None
        yield _emit(i, info.dataset, info.path, "bot", "comment", author_id=r.get("comment_id"),
                    label=label, label_raw=r.get("is_bot_flag"), label_source="column:is_bot_flag",
                    numeric=_numeric(r, excl), governance=info.governance_status)


def conv_reference(path, info, cap, label_map=None):
    for i, r in _dict_rows(path, info.fmt, cap):
        yield _emit(i, info.dataset, info.path, "reference", "account",
                    label=None, label_source="none", numeric=_numeric(r, set()),
                    governance=info.governance_status)


def conv_bot_tsv(path, info, cap, label_map=None):
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        for i, line in enumerate(fh):
            if i >= cap:
                break
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 2:
                continue
            yield _emit(i, info.dataset, info.path, "bot", "account", author_id=parts[0],
                        label=_auth_botword(parts[1]), label_raw=parts[1],
                        label_source="tsv_label", governance=info.governance_status)


def conv_cresci_json(path, info, cap, label_map=None):
    data = json.loads(path.read_text(encoding="utf-8"))
    recs = data if isinstance(data, list) else list(data.values())
    for i, rec in enumerate(recs):
        if i >= cap:
            break
        if not isinstance(rec, dict):
            continue
        user = rec.get("user") or {}
        uid = str(user.get("id") or user.get("id_str") or user.get("screen_name") or "")
        label = (label_map or {}).get(uid)
        yield _emit(i, info.dataset, info.path, "bot", "tweet", text=rec.get("text"),
                    author_id=uid, created_at=rec.get("created_at"), label=label,
                    label_raw=None if label is None else "cresci",
                    label_source="join:cresci_tsv" if label is not None else "none",
                    governance=info.governance_status)


CONVERTERS = {
    "io_tweets": conv_io_tweets, "io_users": conv_io_users, "ai_text_v1": conv_ai_v1,
    "ai_text_2026": conv_ai_2026, "twitterdata": conv_twitterdata, "fsm_profile": conv_fsm,
    "userdump": conv_userdump, "reddit_comment": conv_reddit, "reference": conv_reference,
    "bot_tsv": conv_bot_tsv, "cresci_json": conv_cresci_json,
}
MERGE_ELIGIBLE_STATUS = {"train", "validation", "reference"}


# --------------------------------------------------------------------------- #
# Discovery
# --------------------------------------------------------------------------- #
def _profile_json_like(records: list[dict], row_count: int) -> tuple[list[str], dict]:
    cols: list[str] = []
    for rec in records[:SAMPLE_ROWS]:
        if isinstance(rec, dict):
            for k in rec:
                if k not in cols:
                    cols.append(k)
    rows = [[str(rec.get(c, "")) for c in cols] for rec in records[:SAMPLE_ROWS]
            if isinstance(rec, dict)]
    return cols, _profile_rows(rows, cols)


def profile_file(path: Path, gov: dict, root: Path = DATASETS_ROOT) -> FileInfo:
    try:
        rel = str(path.relative_to(REPO_ROOT))
    except ValueError:
        rel = str(path)
    try:
        rel_ds = str(path.relative_to(root))
    except ValueError:
        rel_ds = rel
    status, prov, _ = governance_for(rel_ds, gov)
    fmt = path.suffix.lstrip(".").lower()
    info = FileInfo(dataset=path.stem, path=rel, fmt=fmt,
                    governance_status=status or "undeclared", provenance=prov)
    try:
        if fmt in ("csv", "tsv"):
            headerless = _looks_headerless(path, fmt)
            if headerless:
                info.columns = ["id", "label"]
                rc = _count_lines(path)
                info.row_count, info.row_count_method = rc, "exact"
                header, rows = [], []
                with path.open("r", encoding="utf-8", errors="replace") as fh:
                    for i, line in enumerate(fh):
                        if i >= SAMPLE_ROWS:
                            break
                        rows.append(line.rstrip("\n").split("\t"))
                prof = _profile_rows(rows, info.columns)
            else:
                header, rows = _read_tabular_sample(path, fmt, SAMPLE_ROWS)
                info.columns = header
                info.row_count, info.row_count_method = _row_count_tabular(path, fmt, True)
                prof = _profile_rows(rows, header)
            info.sampled = info.row_count > len(rows)
            _apply_profile(info, prof)
            info.family, info.domain, info.grain = classify(path, info.columns, fmt, headerless)
        elif fmt == "jsonl":
            recs = []
            with path.open("r", encoding="utf-8", errors="replace") as fh:
                for i, line in enumerate(fh):
                    line = line.strip()
                    if not line:
                        continue
                    if i < SAMPLE_ROWS:
                        try:
                            recs.append(json.loads(line))
                        except json.JSONDecodeError:
                            pass
            info.row_count = _count_lines(path)
            info.columns, prof = _profile_json_like(recs, info.row_count)
            info.sampled = info.row_count > len(recs)
            _apply_profile(info, prof)
            info.family, info.domain, info.grain = classify(path, info.columns, fmt, False)
        elif fmt == "json":
            data = json.loads(path.read_text(encoding="utf-8"))
            recs = data if isinstance(data, list) else (
                data.get("data") if isinstance(data, dict) and isinstance(data.get("data"), list)
                else list(data.values()) if isinstance(data, dict) else [])
            info.row_count = len(recs)
            info.columns, prof = _profile_json_like([r for r in recs if isinstance(r, dict)],
                                                    info.row_count)
            info.sampled = info.row_count > SAMPLE_ROWS
            _apply_profile(info, prof)
            info.family, info.domain, info.grain = classify(path, info.columns, fmt, False)
        elif fmt == "parquet":
            import pyarrow.parquet as pq
            pf = pq.ParquetFile(str(path))
            info.columns = list(pf.schema_arrow.names)
            info.row_count = pf.metadata.num_rows
            info.family, info.domain, info.grain = "parquet_derived", "derived", "mixed"
        elif fmt == "zip":
            with zipfile.ZipFile(path) as zf:
                info.zip_members = [n for n in zf.namelist() if not n.endswith("/")]
            info.family, info.domain, info.grain = "zip_container", "other", "mixed"
            info.row_count = len(info.zip_members)
        elif fmt == "xlsx":
            try:
                import openpyxl  # noqa: F401
                import pandas as pd
                df = pd.read_excel(path, nrows=SAMPLE_ROWS)
                info.columns = [str(c) for c in df.columns]
                info.row_count = len(df)
                info.family, info.domain, info.grain = "xlsx", "authenticity", "account"
            except Exception as exc:  # noqa: BLE001
                info.parse_status = "unparseable"
                info.error = f"xlsx engine unavailable: {exc}"
        else:
            info.parse_status = "unparseable"
            info.error = f"unsupported format {fmt}"
    except Exception as exc:  # noqa: BLE001
        info.parse_status = "unparseable"
        info.error = str(exc)[:200]
    return info


def _apply_profile(info: FileInfo, prof: dict) -> None:
    info.detected_labels = prof["detected_labels"]
    info.missing_cells_pct = prof["missing_cells_pct"]
    info.top_missing = prof["top_missing"]
    info.duplicate_rows_pct = prof["duplicate_rows_pct"]


def discover(root: Path = DATASETS_ROOT, gov: dict | None = None) -> list[FileInfo]:
    gov = gov if gov is not None else load_governance()
    infos: list[FileInfo] = []
    for p in sorted(root.rglob("*")):
        if p.is_file() and p.suffix.lower() in SUPPORTED_EXTS:
            infos.append(profile_file(p, gov, root))
    return infos


# --------------------------------------------------------------------------- #
# Cresci tsv label map (for joining cresci tweet json)
# --------------------------------------------------------------------------- #
def _cresci_label_map() -> dict:
    tsv = DATASETS_ROOT / "cresci-rtbust-2019" / "cresci-rtbust-2019.tsv"
    out = {}
    if tsv.is_file():
        with tsv.open("r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                parts = line.rstrip("\n").split("\t")
                if len(parts) == 2:
                    out[parts[0]] = _auth_botword(parts[1])
    return out


# --------------------------------------------------------------------------- #
# Builders
# --------------------------------------------------------------------------- #
def build_merged_corpus(infos: list[FileInfo], out_path: Path,
                        cap: int = MAX_ROWS_PER_FILE) -> dict:
    import pandas as pd
    label_map = _cresci_label_map()
    records: list[dict] = []
    merged_files, skipped = [], []
    for info in infos:
        conv = CONVERTERS.get(info.family)
        if conv is None or info.parse_status != "ok":
            skipped.append((info.path, info.family, "no converter / unparseable"))
            continue
        if info.governance_status not in MERGE_ELIGIBLE_STATUS:
            skipped.append((info.path, info.family,
                            f"governance={info.governance_status} (not merged)"))
            continue
        n0 = len(records)
        try:
            for rec in conv(REPO_ROOT / info.path, info, cap, label_map):
                records.append(rec)
        except Exception as exc:  # noqa: BLE001
            skipped.append((info.path, info.family, f"convert error: {exc}"))
            continue
        merged_files.append((info.path, info.family, len(records) - n0,
                             info.row_count, info.row_count > cap))
    df = pd.DataFrame.from_records(records, columns=RECORD_FIELDS)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out_path, index=False)
    by = lambda col: {str(k): int(v) for k, v in df[col].value_counts(dropna=False).items()}
    labeled = int(df["authenticity_label"].notna().sum())
    return {
        "rows": len(df), "files_merged": len(merged_files), "files_skipped": len(skipped),
        "by_grain": by("grain"), "by_domain": by("domain"),
        "labeled_rows": labeled, "unlabeled_rows": len(df) - labeled,
        "label_balance": {str(int(k)): int(v) for k, v in
                          df["authenticity_label"].dropna().astype(int).value_counts().items()},
        "merged_files": merged_files, "skipped": skipped, "cap": cap,
    }


def write_inventory(infos: list[FileInfo], json_path: Path, md_path: Path) -> None:
    json_path.write_text(json.dumps([asdict(i) for i in infos], indent=2) + "\n",
                         encoding="utf-8")
    L = ["# Omi Dataset Inventory (OMI_DATASET_DISCOVERY_AND_NORMALIZATION_V1)", "",
         "> Auto-generated by `ml/corpus/omi_corpus.py`. Originals unmodified.", "",
         f"Scanned **{len(infos)}** files under `datasets/`.", "",
         "| dataset | format | rows | cols | grain | domain | governance | labels | miss% | dup% | parse |",
         "|---|---|---|---|---|---|---|---|---|---|---|"]
    for i in infos:
        lbl = ",".join(i.detected_labels) or ("io_disclosure" if i.domain == "coordination"
                                              else "filename" if i.family == "userdump" else "-")
        rc = f"{i.row_count}{'~' if i.row_count_method!='exact' else ''}"
        L.append(f"| `{i.path}` | {i.fmt} | {rc} | {len(i.columns)} | {i.grain} | {i.domain} "
                 f"| {i.governance_status} | {lbl} | {i.missing_cells_pct} | "
                 f"{i.duplicate_rows_pct} | {i.parse_status} |")
    md_path.write_text("\n".join(L) + "\n", encoding="utf-8")


def write_schema_comparison(infos: list[FileInfo], path: Path) -> None:
    fams: dict[str, list[FileInfo]] = {}
    for i in infos:
        fams.setdefault(i.family, []).append(i)
    L = ["# Schema Comparison", "",
         "How the discovered datasets differ, grouped by detected family, and how each "
         "maps into the unified Omi schema (see `UNIFIED_OMI_SCHEMA.md`).", "",
         "| family | domain | grain | files | example columns | unified mapping |",
         "|---|---|---|---|---|---|"]
    mapnote = {
        "io_tweets": "userid→author_id, tweet_text→text, tweet_time→created_at, label=1 (io)",
        "io_users": "userid→author_id, follower/following→numeric, label=1 (io)",
        "ai_text_v1": "text→text, human_or_ai→authenticity_label, language→lang",
        "ai_text_2026": "text_content→text, label→authenticity_label",
        "twitterdata": "Tweet_text→text, Twitter_Account→author_id, Label(1=human)→inverted label",
        "fsm_profile": "username→author_id, numeric cols→numeric, is_fake→label",
        "userdump": "screen_name→author_id, numeric→numeric, filename→label",
        "reddit_comment": "comment_id→author_id, numeric→numeric, is_bot_flag→label",
        "reference": "numeric (bot_score)→numeric, label=None",
        "bot_tsv": "id→author_id, tsv label word→label",
        "cresci_json": "user.id→author_id, text→text, join cresci tsv→label",
        "generic_account": "numeric→numeric (archive; not merged)",
        "bot_detection": "quarantine poison — not merged",
        "parquet_derived": "derived Omi output — not a source",
        "unknown": "no converter",
    }
    for fam, items in sorted(fams.items()):
        ex = ", ".join((items[0].columns or [])[:6]) or "-"
        L.append(f"| {fam} | {items[0].domain} | {items[0].grain} | {len(items)} | "
                 f"{ex} | {mapnote.get(fam, '-')} |")
    L += ["", "### Key differences",
          "- **Grain varies**: account (profiles), tweet (IO / TwitterData / cresci), "
          "comment (reddit), text (AI sets). The unified schema keeps a `grain` column so "
          "these never silently merge into one training population.",
          "- **Label encoding varies**: `is_fake`, `human_or_ai`, headerless TSV words, "
          "filename, inverted `Label` (1=human), implicit io_disclosure (=1), or none "
          "(reference). All normalize to `authenticity_label` ∈ {0,1,null} + `label_raw`.",
          "- **Features vary**: account sets carry numeric profile features "
          "(→ `numeric_features_json`); tweet/text sets carry `text`. No dataset carries "
          "engine detector outputs."]
    path.write_text("\n".join(L) + "\n", encoding="utf-8")


def write_quality_report(infos: list[FileInfo], merge: dict, path: Path) -> None:
    parseable = [i for i in infos if i.parse_status == "ok"]
    unparseable = [i for i in infos if i.parse_status != "ok"]
    fmt_counts = Counter(i.fmt for i in infos)
    gov_counts = Counter(i.governance_status for i in infos)
    high_missing = sorted([i for i in parseable if i.missing_cells_pct > 10],
                          key=lambda i: -i.missing_cells_pct)[:10]
    high_dup = sorted([i for i in parseable if i.duplicate_rows_pct > 5],
                      key=lambda i: -i.duplicate_rows_pct)[:10]
    total_rows = sum(i.row_count for i in parseable)
    L = ["# Data Quality Report (OMI_DATASET_DISCOVERY_AND_NORMALIZATION_V1)", "",
         f"Files: **{len(infos)}** ({len(parseable)} parseable, {len(unparseable)} "
         f"unparseable). Approx total source rows: **{total_rows:,}**.", "",
         "## Formats", "| format | files |", "|---|---|"]
    for f, c in sorted(fmt_counts.items()):
        L.append(f"| {f} | {c} |")
    L += ["", "## Governance breakdown", "| status | files |", "|---|---|"]
    for s, c in sorted(gov_counts.items()):
        L.append(f"| {s} | {c} |")
    L += ["", "## Missing values (top offenders, sampled)", "| file | miss% | top columns |",
          "|---|---|---|"]
    for i in high_missing:
        L.append(f"| `{i.path}` | {i.missing_cells_pct} | {', '.join(i.top_missing) or '-'} |")
    if not high_missing:
        L.append("| _none > 10%_ | | |")
    L += ["", "## Duplicate rows (top offenders, sampled)", "| file | dup% |", "|---|---|"]
    for i in high_dup:
        L.append(f"| `{i.path}` | {i.duplicate_rows_pct} |")
    if not high_dup:
        L.append("| _none > 5%_ | |")
    L += ["", "## Unparseable / not normalized (req 9)", "| file | format | reason |",
          "|---|---|---|"]
    for i in unparseable:
        L.append(f"| `{i.path}` | {i.fmt} | {i.error} |")
    nconv = [i for i in parseable if i.family not in CONVERTERS and i.family not in
             ("parquet_derived",)]
    for i in nconv_unique(nconv):
        L.append(f"| `{i.path}` | {i.fmt} | no converter (family={i.family}); not normalized |")
    if not unparseable and not nconv:
        L.append("| _none_ | | |")
    L += ["", "## Merged corpus", f"- Rows: **{merge['rows']:,}** from "
          f"{merge['files_merged']} files (cap {merge['cap']}/file; "
          f"{merge['files_skipped']} files skipped).",
          f"- By grain: {merge['by_grain']}", f"- By domain: {merge['by_domain']}",
          f"- Labeled: {merge['labeled_rows']:,} (balance 0/1 = {merge['label_balance']}); "
          f"unlabeled: {merge['unlabeled_rows']:,}", "",
          "## Leakage & integrity warnings (req D)",
          "1. **Cross-grain merge is intentional but must be filtered**: the corpus mixes "
          "account/tweet/comment/text rows; train per-grain by filtering `grain`/`domain` — "
          "do NOT train one model across grains.",
          "2. **Username-morphology shortcut present** in `fsm_profile` numeric features "
          f"({', '.join(sorted(USERNAME_SHORTCUT))}) — V2 audit shortcut. Preserved here for "
          "fidelity but **must be dropped before training** (the NN dataset builder already does).",
          "3. **Source↔label confound**: `real_users`(0)/`fake_users`(1) are labeled by file "
          "origin; IO sets are labeled implicitly (=1). Origin differences are confounded "
          "with the label.",
          "4. **No engine-output circularity**: no dataset carries engine detector/score "
          "outputs, so none leak into features.",
          "5. **Caps applied**: large files are capped at "
          f"{merge['cap']} rows in the committed corpus (sampling) — see merged-file table "
          "below; full normalization is reproducible by raising `--max-rows`.",
          "6. **Duplicates**: per-file duplicate rates are sampled above; the per-grain NN "
          "builders dedup on the feature vector before splitting.",
          f"7. **Merged class imbalance**: labeled balance 0/1 = {merge['label_balance']} "
          f"(~{round(100 * merge['label_balance'].get('1', 0) / max(1, merge['labeled_rows']))}% "
          "inauthentic), driven by the many IO tweet files (all label=1, each capped). "
          "Per-domain balance differs — rebalance or filter by `domain` before training.", "",
          "### Merged files (rows in / source rows / capped)",
          "| file | family | rows in corpus | source rows | capped |", "|---|---|---|---|---|"]
    for p, fam, n, src, capped in merge["merged_files"]:
        L.append(f"| `{p}` | {fam} | {n} | {src} | {'yes' if capped else 'no'} |")
    path.write_text("\n".join(L) + "\n", encoding="utf-8")


def nconv_unique(items):
    seen, out = set(), []
    for i in items:
        if i.path not in seen:
            seen.add(i.path)
            out.append(i)
    return out


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Omi dataset discovery + normalization")
    p.add_argument("--discover", action="store_true", help="inventory + schema comparison only")
    p.add_argument("--build", action="store_true", help="full: inventory + merge + reports")
    p.add_argument("--max-rows", type=int, default=MAX_ROWS_PER_FILE)
    args = p.parse_args(argv)

    gov = load_governance()
    infos = discover(DATASETS_ROOT, gov)
    write_inventory(infos, CORPUS_DIR / "inventory.json", CORPUS_DIR / "inventory.md")
    write_schema_comparison(infos, CORPUS_DIR / "schema_comparison.md")
    print(f"Discovered {len(infos)} files -> inventory.json/md, schema_comparison.md")

    if not args.build:
        print("Run with --build to produce data/merged_corpus.parquet + data_quality_report.md "
              "(no training).")
        return 0

    merge = build_merged_corpus(infos, DATA_DIR / "merged_corpus.parquet", cap=args.max_rows)
    write_quality_report(infos, merge, CORPUS_DIR / "data_quality_report.md")
    print(f"Merged corpus: {merge['rows']} rows from {merge['files_merged']} files "
          f"(skipped {merge['files_skipped']}); by_grain={merge['by_grain']}")
    print(f"Reports: inventory.md, schema_comparison.md, data_quality_report.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
