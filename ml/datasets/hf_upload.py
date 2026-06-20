#!/usr/bin/env python3
"""OmiSphere -> Hugging Face dataset upload pipeline (OMI_DATASET_UPLOAD_V1).

Production-safe, upload-only. Reads ``ml/datasets/upload_manifest.toml``,
validates each eligible dataset (exists, labels, row count, schema summary),
generates a dataset card, and -- only with ``--upload`` -- pushes eligible
datasets plus the card to the target Hugging Face dataset repo.

SAFETY (production-safe by design):
  * Upload requires the explicit ``--upload`` flag. Default is validate + dry-run.
  * Only status in {train, eval} is eligible; archive/quarantine NEVER upload.
  * ``datasets/manifest.toml`` is authoritative for EXCLUSION: a dataset governed
    there as quarantine/archive is force-excluded even if the upload manifest
    says train/eval (fail-closed on poison).
  * If ANY eligible dataset fails validation, nothing is uploaded.
  * Does NOT train, modify scoring, touch apps/api or apps/web, or deploy.
  * HF_TOKEN is read from the environment and never printed.

Formats: csv, parquet, json. Exit 0 = OK, non-zero = failure.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import tomllib
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

ELIGIBLE_DEFAULT = ("train", "eval")
GOVERNANCE_VETO = ("quarantine", "archive")
SUPPORTED_FORMATS = ("csv", "parquet", "json")
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST = "ml/datasets/upload_manifest.toml"


# --------------------------------------------------------------------------- #
# Models
# --------------------------------------------------------------------------- #
@dataclass
class DatasetEntry:
    name: str
    source_path: str
    fmt: str
    status: str
    label_type: str = ""
    label_column: str | None = None
    label_value: str | None = None
    intended_use: str = ""
    trust_level: str = ""
    target_path: str = ""
    notes: str = ""


@dataclass
class Validation:
    ok: bool
    row_count: int = 0
    columns: list[str] = field(default_factory=list)
    dtypes: dict[str, str] = field(default_factory=dict)
    labels: dict[str, int] = field(default_factory=dict)
    error: str = ""


# --------------------------------------------------------------------------- #
# Manifest + governance
# --------------------------------------------------------------------------- #
def load_manifest(path: Path) -> tuple[dict, list[DatasetEntry]]:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    target = data.get("target", {})
    entries = [
        DatasetEntry(
            name=d["name"],
            source_path=d["source_path"],
            fmt=d.get("format", Path(d["source_path"]).suffix.lstrip(".")).lower(),
            status=d["status"].lower(),
            label_type=d.get("label_type", ""),
            label_column=d.get("label_column"),
            label_value=d.get("label_value"),
            intended_use=d.get("intended_use", ""),
            trust_level=d.get("trust_level", ""),
            target_path=d.get("target_path", ""),
            notes=d.get("notes", ""),
        )
        for d in data.get("dataset", [])
    ]
    return target, entries


def load_governance(path: Path) -> dict:
    """Return {'files': {rel: status}, 'dirs': [(rel, status)]} from datasets/manifest.toml."""
    if not path.is_file():
        return {"files": {}, "dirs": []}
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    files = {f["path"]: f["status"].lower() for f in data.get("file", [])}
    dirs = [(d["path"], d["status"].lower()) for d in data.get("dir", [])]
    return {"files": files, "dirs": dirs}


def governance_status(source_path: str, gov: dict) -> str | None:
    """Resolve a repo-root-relative source path against datasets/-relative rules."""
    rel = source_path
    if rel.startswith("datasets/"):
        rel = rel[len("datasets/"):]
    if rel in gov["files"]:
        return gov["files"][rel]
    best = None
    for prefix, status in gov["dirs"]:
        if rel == prefix or rel.startswith(prefix + "/"):
            if best is None or len(prefix) > len(best[0]):
                best = (prefix, status)
    return best[1] if best else None


def eligibility(entry: DatasetEntry, gov: dict, eligible: tuple[str, ...]) -> tuple[bool, str]:
    gstat = governance_status(entry.source_path, gov)
    if gstat in GOVERNANCE_VETO:
        return False, f"governance veto: datasets/manifest.toml status={gstat}"
    if entry.status not in eligible:
        return False, f"status={entry.status} (not in {','.join(eligible)})"
    return True, "eligible"


# --------------------------------------------------------------------------- #
# Validation (exists, labels, row count, schema summary)
# --------------------------------------------------------------------------- #
def _infer_type(values: list[str]) -> str:
    seen = set()
    for v in values:
        if v is None or v == "":
            continue
        try:
            int(v)
            seen.add("int")
            continue
        except (ValueError, TypeError):
            pass
        try:
            float(v)
            seen.add("float")
            continue
        except (ValueError, TypeError):
            pass
        seen.add("str")
    if not seen:
        return "empty"
    if seen == {"int"}:
        return "int"
    if seen <= {"int", "float"}:
        return "float"
    return "str"


def _read_csv(path: Path, label_column: str | None) -> tuple[int, list[str], dict, dict]:
    with path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.reader(fh)
        try:
            header = next(reader)
        except StopIteration:
            return 0, [], {}, {}
        samples: dict[int, list[str]] = {i: [] for i in range(len(header))}
        label_idx = header.index(label_column) if label_column in header else -1
        label_counts: Counter = Counter()
        rows = 0
        for row in reader:
            rows += 1
            if rows <= 500:
                for i, cell in enumerate(row[: len(header)]):
                    samples[i].append(cell)
            if label_idx >= 0 and label_idx < len(row):
                label_counts[row[label_idx]] += 1
    dtypes = {header[i]: _infer_type(samples[i]) for i in range(len(header))}
    return rows, header, dtypes, dict(label_counts)


def _read_json(path: Path, label_column: str | None) -> tuple[int, list[str], dict, dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        for key in ("data", "rows", "records"):
            if isinstance(data.get(key), list):
                data = data[key]
                break
    if not isinstance(data, list):
        raise ValueError("unsupported JSON shape (expected a list of records or {data:[...]})")
    records = [r for r in data if isinstance(r, dict)]
    columns: list[str] = []
    for r in records[:500]:
        for k in r:
            if k not in columns:
                columns.append(k)
    samples = {c: [str(r.get(c, "")) for r in records[:500]] for c in columns}
    dtypes = {c: _infer_type(samples[c]) for c in columns}
    labels: dict = {}
    if label_column and label_column in columns:
        labels = dict(Counter(str(r.get(label_column, "")) for r in records))
    return len(records), columns, dtypes, labels


def _read_parquet(path: Path, label_column: str | None) -> tuple[int, list[str], dict, dict]:
    try:
        import pyarrow.parquet as pq
    except ImportError as exc:  # pragma: no cover - CI installs pyarrow
        raise ValueError(f"parquet support needs pyarrow: {exc}")
    pf = pq.ParquetFile(str(path))
    schema = pf.schema_arrow
    columns = list(schema.names)
    dtypes = {n: str(schema.field(n).type) for n in columns}
    rows = pf.metadata.num_rows
    labels: dict = {}
    if label_column and label_column in columns:
        col = pq.read_table(str(path), columns=[label_column]).column(label_column).to_pylist()
        labels = dict(Counter(str(v) for v in col))
    return rows, columns, dtypes, labels


def validate_dataset(entry: DatasetEntry) -> Validation:
    path = REPO_ROOT / entry.source_path
    if not path.is_file():
        return Validation(ok=False, error=f"source not found: {entry.source_path}")
    if entry.fmt not in SUPPORTED_FORMATS:
        return Validation(ok=False, error=f"unsupported format: {entry.fmt}")
    reader = {"csv": _read_csv, "json": _read_json, "parquet": _read_parquet}[entry.fmt]
    try:
        rows, columns, dtypes, labels = reader(path, entry.label_column)
    except Exception as exc:  # noqa: BLE001 - surface any read error as invalid
        return Validation(ok=False, error=f"read error: {exc}")

    if rows == 0:
        return Validation(ok=False, columns=columns, error="0 data rows")
    if entry.label_column and entry.label_column not in columns:
        return Validation(
            ok=False, row_count=rows, columns=columns,
            error=f"declared label_column '{entry.label_column}' not in columns",
        )
    if entry.label_value and not labels:
        labels = {entry.label_value: rows}  # constant (filename-labeled) dataset
    if entry.status == "train" and not entry.label_column and not entry.label_value:
        return Validation(
            ok=False, row_count=rows, columns=columns,
            error="train dataset needs a label_column or label_value",
        )
    return Validation(ok=True, row_count=rows, columns=columns, dtypes=dtypes, labels=labels)


# --------------------------------------------------------------------------- #
# Dataset card
# --------------------------------------------------------------------------- #
def _schema_line(v: Validation, cap: int = 20) -> str:
    cols = [f"`{c}`:{v.dtypes.get(c, '?')}" for c in v.columns[:cap]]
    extra = f" … (+{len(v.columns) - cap} more)" if len(v.columns) > cap else ""
    return ", ".join(cols) + extra


def _labels_line(v: Validation, cap: int = 12) -> str:
    if not v.labels:
        return "n/a"
    items = sorted(v.labels.items(), key=lambda kv: (-kv[1], str(kv[0])))[:cap]
    return ", ".join(f"{k}={n}" for k, n in items)


def generate_card(target: dict, uploaded: list[tuple[DatasetEntry, Validation]]) -> str:
    pretty = target.get("pretty_name", target.get("repo_id", "OMI Dataset"))
    lines = [
        "---",
        f"pretty_name: {pretty}",
        "tags:",
        "- omisphere",
        "- authenticity",
        "- bot-detection",
        "- coordination-intelligence",
        "language:",
        "- en",
        "---",
        "",
        f"# {pretty}",
        "",
        "> Auto-generated by `ml/datasets/hf_upload.py` (OMI_DATASET_UPLOAD_V1). "
        "Do not edit by hand — re-run the pipeline.",
        "",
        "## Governance & trust",
        "- Labels are **provenance/ground-truth observations, not verdicts**; "
        "treat them as evidence with the caveats noted per dataset.",
        "- **Quarantine and archive datasets are never uploaded.** "
        "`datasets/manifest.toml` is authoritative for exclusion (fail-closed on poison).",
        "- Only `train`/`eval` datasets appear below; the repo is private.",
        "",
        "## Datasets",
    ]
    for entry, v in uploaded:
        lines += [
            "",
            f"### {entry.name}  ·  `{entry.status}`",
            f"- **path in repo:** `{entry.target_path}`",
            f"- **format:** {entry.fmt}  ·  **rows:** {v.row_count}  ·  "
            f"**columns:** {len(v.columns)}",
            f"- **label type:** {entry.label_type or 'n/a'}  ·  "
            f"**label:** {_labels_line(v)}",
            f"- **trust level:** {entry.trust_level or 'n/a'}",
            f"- **intended use:** {entry.intended_use or 'n/a'}",
            f"- **schema:** {_schema_line(v)}",
        ]
        if entry.notes:
            lines.append(f"- **notes:** {entry.notes}")
    lines.append("")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Reporting + upload
# --------------------------------------------------------------------------- #
def _summary(line: str) -> None:
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not path:
        return
    try:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except OSError:
        pass


def do_upload(target: dict, uploaded: list[tuple[DatasetEntry, Validation]], card: str,
              create_repo: bool) -> int:
    token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACE_HUB_TOKEN")
    if not token:
        print("FAIL: HF_TOKEN is not set (configure it as a GitHub Actions secret).")
        return 1
    try:
        from huggingface_hub import HfApi
        from huggingface_hub.utils import HfHubHTTPError, RepositoryNotFoundError
    except ImportError as exc:  # pragma: no cover - CI installs the dependency
        print(f"FAIL: huggingface_hub is not installed: {exc}")
        return 1

    repo_id = target["repo_id"]
    repo_type = target.get("repo_type", "dataset")
    api = HfApi(token=token)

    try:
        if create_repo:
            api.create_repo(repo_id=repo_id, repo_type=repo_type,
                            private=bool(target.get("private", True)), exist_ok=True)
        api.repo_info(repo_id=repo_id, repo_type=repo_type)
    except RepositoryNotFoundError:
        print(f"FAIL: repo '{repo_id}' not found or no access. "
              "Use --create-repo (or check the token).")
        return 1
    except HfHubHTTPError as exc:
        print(f"FAIL: cannot access '{repo_id}': {exc}")
        return 1

    for entry, _ in uploaded:
        try:
            api.upload_file(
                path_or_fileobj=str(REPO_ROOT / entry.source_path),
                path_in_repo=entry.target_path,
                repo_id=repo_id, repo_type=repo_type,
                commit_message=f"upload {entry.name} ({entry.status})",
            )
        except (HfHubHTTPError,) as exc:
            print(f"FAIL: upload denied for '{entry.name}' -> '{repo_id}' "
                  f"(write access?): {exc}")
            return 1
        print(f"  uploaded {entry.name} -> {entry.target_path}")

    api.upload_file(
        path_or_fileobj=card.encode("utf-8"), path_in_repo="README.md",
        repo_id=repo_id, repo_type=repo_type,
        commit_message="update auto-generated dataset card",
    )
    print(f"PASS: uploaded {len(uploaded)} dataset(s) + dataset card to '{repo_id}'")
    _summary(f"✅ **dataset upload PASS** — {len(uploaded)} dataset(s) + card to "
             f"`{repo_id}`.")
    return 0


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def run(manifest_path: Path, action: str, only: str | None, create_repo: bool,
        eligible: tuple[str, ...]) -> int:
    target, entries = load_manifest(manifest_path)
    gov = load_governance(REPO_ROOT / target.get("governance_manifest", "datasets/manifest.toml"))
    if only:
        entries = [e for e in entries if e.name == only]
        if not entries:
            print(f"FAIL: --only '{only}' matched no dataset in the manifest")
            return 1

    eligible_items: list[tuple[DatasetEntry, Validation]] = []
    invalid = 0
    print(f"Target: {target.get('repo_id')} ({target.get('repo_type','dataset')})")
    print(f"Eligible statuses: {', '.join(eligible)}  ·  governance veto: "
          f"{', '.join(GOVERNANCE_VETO)}\n")
    for entry in entries:
        ok, reason = eligibility(entry, gov, eligible)
        if not ok:
            print(f"SKIP  {entry.name:<34} {reason}")
            continue
        v = validate_dataset(entry)
        if not v.ok:
            print(f"INVALID  {entry.name:<31} {v.error}")
            invalid += 1
            continue
        print(f"OK    {entry.name:<34} rows={v.row_count} cols={len(v.columns)} "
              f"labels[{_labels_line(v)}]")
        eligible_items.append((entry, v))

    print()
    if invalid:
        print(f"FAIL: {invalid} eligible dataset(s) failed validation — nothing uploaded.")
        _summary(f"❌ **dataset upload FAIL** — {invalid} eligible dataset(s) invalid.")
        return 1
    if not eligible_items:
        print("Nothing eligible to upload.")
        return 0

    card = generate_card(target, eligible_items)

    if action == "validate":
        print(f"VALIDATE OK: {len(eligible_items)} eligible dataset(s) ready (no upload).")
        return 0
    if action == "dry-run":
        print(f"DRY-RUN: would upload {len(eligible_items)} dataset(s) + card.\n")
        print("----- generated dataset card (README.md) -----")
        print(card)
        return 0
    # action == "upload"
    print(f"UPLOAD: pushing {len(eligible_items)} dataset(s) + card …")
    return do_upload(target, eligible_items, card, create_repo)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="OmiSphere -> Hugging Face dataset upload pipeline")
    p.add_argument("--manifest", default=DEFAULT_MANIFEST)
    g = p.add_mutually_exclusive_group()
    g.add_argument("--validate", action="store_true", help="validate only (no HF, no token)")
    g.add_argument("--dry-run", action="store_true", help="validate + print plan/card (no write)")
    g.add_argument("--upload", action="store_true", help="validate + upload (needs HF_TOKEN)")
    p.add_argument("--only", default=None, help="restrict to a single dataset name")
    p.add_argument("--create-repo", action="store_true", help="create the repo (private) if missing")
    p.add_argument("--eligible-status", default=",".join(ELIGIBLE_DEFAULT))
    args = p.parse_args(argv)

    action = "validate" if args.validate else "upload" if args.upload else "dry-run"
    manifest_path = (REPO_ROOT / args.manifest) if not Path(args.manifest).is_absolute() else Path(args.manifest)
    if not manifest_path.is_file():
        print(f"FAIL: manifest not found: {manifest_path}")
        return 1
    eligible = tuple(s.strip().lower() for s in args.eligible_status.split(",") if s.strip())
    return run(manifest_path, action, args.only, args.create_repo, eligible)


if __name__ == "__main__":
    sys.exit(main())
