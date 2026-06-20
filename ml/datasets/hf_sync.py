#!/usr/bin/env python3
"""OmiSphere dataset sync: GitHub -> Hugging Face (OMI_DATASET_AUTOMATION_V1).

Automates discovery + classification + incremental upload of governed datasets:
  1. discover every dataset governed in datasets/manifest.toml (file + dir rules),
  2. classify each into uploadable / blocked / manual_review (reason for each),
  3. write a dataset inventory (json + md) and a generated upload manifest,
  4. incrementally upload the uploadable datasets to the target HF dataset repo
     (skip unchanged by content hash -> updates never duplicate files),
  5. auto-generate + upload the dataset card.

Preserves train/eval/archive/quarantine classifications. archive/quarantine are
NEVER uploaded (governance veto). Reuses the validated V1 pipeline
(ml/datasets/hf_upload.py) for validation + card generation.

Upload-only. Does NOT train, modify scoring, or touch apps/api / apps/web.
HF_TOKEN is read from the environment and never printed.

Modes: --discover (inventory only) | --dry-run (default; + validate + plan, no
network) | --sync (incremental upload, needs a write-capable HF_TOKEN).
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys
import tomllib
from dataclasses import asdict, dataclass, field
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
import hf_upload as up  # noqa: E402  (sibling module: validation + card + models)

REPO_ROOT = up.REPO_ROOT
DATASETS_ROOT = REPO_ROOT / "datasets"
GOVERNANCE = DATASETS_ROOT / "manifest.toml"
SYNC_CONFIG = _HERE / "sync_config.toml"
INVENTORY_JSON = _HERE / "dataset_inventory.json"
INVENTORY_MD = _HERE / "dataset_inventory.md"
GENERATED_MANIFEST = _HERE / "sync_upload_manifest.toml"

DATA_EXTS = {".csv", ".tsv", ".json", ".parquet"}
CLASS = {"train": "TRAIN", "validation": "EVAL", "reference": "EVAL",
         "heuristic": "EVAL", "archive": "ARCHIVE", "quarantine": "QUARANTINE"}
LABEL_CANDIDATES = ["is_fake", "is_bot_flag", "is_bot", "human_or_ai", "label", "bot"]


# --------------------------------------------------------------------------- #
@dataclass
class Config:
    target_repo: str
    repo_type: str
    private: bool
    max_upload_size_mb: float
    manual_review_provenance: list[str]
    overrides: list[dict]


@dataclass
class Item:
    name: str
    gov_path: str           # datasets/-relative
    source_path: str        # repo-root-relative
    rule_type: str          # "file" | "dir"
    status: str             # governance status
    classification: str     # TRAIN/EVAL/ARCHIVE/QUARANTINE
    kind: str = ""
    provenance: str = ""
    fmt: str = ""
    exists: bool = False
    size_mb: float = 0.0
    file_count: int = 1
    bucket: str = ""        # uploadable | blocked | manual_review
    reason: str = ""
    target_path: str = ""
    label_column: str | None = None
    label_value: str | None = None
    label_type: str = ""
    trust_level: str = ""
    intended_use: str = ""
    notes: str = ""


# --------------------------------------------------------------------------- #
def load_config(path: Path) -> Config:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    r = data.get("routing", {})
    return Config(
        target_repo=r.get("target_repo", "Andrewexiga/omi-authenticity-dataset"),
        repo_type=r.get("repo_type", "dataset"),
        private=bool(r.get("private", True)),
        max_upload_size_mb=float(r.get("max_upload_size_mb", 25.0)),
        manual_review_provenance=list(r.get("manual_review_provenance", [])),
        overrides=list(data.get("override", [])),
    )


def _override_for(gov_path: str, config: Config) -> dict | None:
    base = gov_path.rsplit("/", 1)[-1]
    for ov in config.overrides:
        m = ov.get("match", "")
        if gov_path == m or gov_path.endswith("/" + m) or base == m or base == m.rsplit("/", 1)[-1]:
            return ov
    return None


def _read_header(path: Path) -> list[str]:
    try:
        with path.open("r", encoding="utf-8", newline="") as fh:
            return next(csv.reader(fh), [])
    except OSError:
        return []


# --------------------------------------------------------------------------- #
# Discovery
# --------------------------------------------------------------------------- #
def _relpath(p: Path) -> str:
    """Path relative to the repo root, or absolute if it lives outside (tests)."""
    try:
        return str(p.relative_to(REPO_ROOT))
    except ValueError:
        return str(p)


def discover(governance: Path = GOVERNANCE, datasets_root: Path = DATASETS_ROOT) -> list[Item]:
    gov = tomllib.loads(governance.read_text(encoding="utf-8"))
    items: list[Item] = []

    for f in gov.get("file", []):
        rel = f["path"]
        src = datasets_root / rel
        status = f["status"].lower()
        items.append(Item(
            name=Path(rel).name, gov_path=rel,
            source_path=_relpath(datasets_root / rel),
            rule_type="file", status=status, classification=CLASS.get(status, "EVAL"),
            kind=f.get("kind", ""), provenance=f.get("provenance", ""),
            fmt=Path(rel).suffix.lstrip(".").lower(),
            exists=src.is_file(),
            size_mb=round(src.stat().st_size / 1e6, 3) if src.is_file() else 0.0,
            file_count=1 if src.is_file() else 0,
        ))

    for d in gov.get("dir", []):
        rel = d["path"]
        root = datasets_root / rel
        status = d["status"].lower()
        files = [p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in DATA_EXTS] \
            if root.is_dir() else []
        total = sum(p.stat().st_size for p in files)
        exts = {p.suffix.lstrip(".").lower() for p in files}
        items.append(Item(
            name=rel, gov_path=rel, source_path=_relpath(root),
            rule_type="dir", status=status, classification=CLASS.get(status, "EVAL"),
            kind=d.get("kind", ""), provenance=d.get("provenance", ""),
            fmt="/".join(sorted(exts)) if exts else "",
            exists=bool(files), size_mb=round(total / 1e6, 3), file_count=len(files),
        ))
    return items


# --------------------------------------------------------------------------- #
# Classification
# --------------------------------------------------------------------------- #
def _resolve_label(item: Item, config: Config) -> tuple[str | None, str | None]:
    ov = _override_for(item.gov_path, config)
    if ov:
        if ov.get("label_column"):
            return "column", ov["label_column"]
        if ov.get("label_value"):
            return "value", ov["label_value"]
    if item.fmt == "csv" and item.exists:
        header = _read_header(REPO_ROOT / item.source_path)
        for cand in LABEL_CANDIDATES:
            if cand in header:
                return "column", cand
    return None, None


def classify(item: Item, config: Config) -> Item:
    ov = _override_for(item.gov_path, config) or {}
    item.label_type = ov.get("label_type", "")
    item.trust_level = ov.get("trust_level", "medium")
    item.intended_use = ov.get("intended_use", "")
    item.notes = ov.get("notes", "")

    if item.classification in ("ARCHIVE", "QUARANTINE"):
        item.bucket, item.reason = "blocked", f"governance {item.status} (never uploaded)"
        return item
    if not item.exists or item.file_count == 0:
        item.bucket, item.reason = "manual_review", "declared in governance but no files present"
        return item
    if item.provenance == "twitter_io_disclosure":
        item.bucket, item.reason = "manual_review", \
            "coordination IO domain — belongs in a coordination dataset repo (large/multi-file)"
        return item
    if item.provenance in config.manual_review_provenance:
        item.bucket, item.reason = "manual_review", \
            f"provenance '{item.provenance}' needs a headerless adapter before upload"
        return item
    if item.kind == "text":
        item.bucket, item.reason = "manual_review", \
            "text-grain (not account authenticity) — choose target repo separately"
        return item
    if item.status == "reference":
        item.bucket, item.reason = "manual_review", "reference/calibration set (no class label)"
        return item
    if item.rule_type == "dir":
        item.bucket, item.reason = "manual_review", \
            "multi-file archive — review grain/target before upload"
        return item
    if item.size_mb > config.max_upload_size_mb:
        item.bucket, item.reason = "manual_review", \
            f"large file ({item.size_mb} MB > {config.max_upload_size_mb} MB) — needs explicit sign-off"
        return item
    kind, ref = _resolve_label(item, config)
    if kind is None:
        item.bucket, item.reason = "manual_review", \
            "no label mapping (add an override in sync_config.toml)"
        return item
    if kind == "column":
        item.label_column = ref
    else:
        item.label_value = ref
    item.target_path = ov.get("target_path", f"authenticity/mixed_quality/{item.name}")
    item.bucket, item.reason = "uploadable", "train/eval authenticity, labeled, within size limit"
    return item


def classify_all(items: list[Item], config: Config) -> list[Item]:
    return [classify(i, config) for i in items]


# --------------------------------------------------------------------------- #
# Inventory + generated manifest
# --------------------------------------------------------------------------- #
def write_inventory(items: list[Item], config: Config) -> None:
    INVENTORY_JSON.write_text(json.dumps(
        {"target_repo": config.target_repo, "datasets": [asdict(i) for i in items]},
        indent=2) + "\n", encoding="utf-8")

    by_bucket: dict[str, list[Item]] = {"uploadable": [], "blocked": [], "manual_review": []}
    for i in items:
        by_bucket[i.bucket].append(i)
    lines = [
        "# OmiSphere Dataset Inventory (OMI_DATASET_AUTOMATION_V1)",
        "",
        "> Auto-generated by `ml/datasets/hf_sync.py` from `datasets/manifest.toml`. "
        "Do not edit by hand.",
        "",
        f"Target repo: `{config.target_repo}`  ·  "
        f"uploadable **{len(by_bucket['uploadable'])}** · "
        f"blocked **{len(by_bucket['blocked'])}** · "
        f"manual review **{len(by_bucket['manual_review'])}**",
    ]
    for bucket, title in [("uploadable", "Uploadable"), ("blocked", "Blocked"),
                          ("manual_review", "Requires manual review")]:
        lines += ["", f"## {title} ({len(by_bucket[bucket])})", "",
                  "| dataset | class | kind | fmt | size MB | files | reason |",
                  "|---|---|---|---|---|---|---|"]
        for i in sorted(by_bucket[bucket], key=lambda x: x.gov_path):
            lines.append(f"| `{i.gov_path}` | {i.classification} | {i.kind or '-'} | "
                         f"{i.fmt or '-'} | {i.size_mb} | {i.file_count} | {i.reason} |")
    INVENTORY_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_manifest(items: list[Item], config: Config) -> None:
    up_items = [i for i in items if i.bucket == "uploadable"]
    lines = [
        "# GENERATED by ml/datasets/hf_sync.py — do not edit by hand.",
        "# Uploadable datasets discovered from datasets/manifest.toml.",
        "schema_version = 1", "",
        "[target]",
        f'repo_id = "{config.target_repo}"',
        f'repo_type = "{config.repo_type}"',
        f"private = {str(config.private).lower()}",
        'governance_manifest = "datasets/manifest.toml"',
        'pretty_name = "OMI Authenticity Dataset"',
    ]
    for i in up_items:
        status = "train" if i.classification == "TRAIN" else "eval"
        lines += ["", "[[dataset]]", f'name = "{Path(i.name).stem}"',
                  f'source_path = "{i.source_path}"', f'format = "{i.fmt}"',
                  f'label_type = "{i.label_type or ("binary" if i.label_column else "account_authenticity")}"']
        if i.label_column:
            lines.append(f'label_column = "{i.label_column}"')
        if i.label_value:
            lines.append(f'label_value = "{i.label_value}"')
        lines += [f'intended_use = "{i.intended_use}"', f'trust_level = "{i.trust_level}"',
                  f'status = "{status}"', f'target_path = "{i.target_path}"']
        if i.notes:
            lines.append(f'notes = "{i.notes}"')
    GENERATED_MANIFEST.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _to_entry(i: Item) -> "up.DatasetEntry":
    status = "train" if i.classification == "TRAIN" else "eval"
    return up.DatasetEntry(
        name=Path(i.name).stem, source_path=i.source_path, fmt=i.fmt, status=status,
        label_type=i.label_type, label_column=i.label_column, label_value=i.label_value,
        intended_use=i.intended_use, trust_level=i.trust_level,
        target_path=i.target_path, notes=i.notes)


# --------------------------------------------------------------------------- #
# Incremental upload (skip-unchanged by content hash -> no duplication)
# --------------------------------------------------------------------------- #
def digests(path: Path) -> tuple[int, str, str]:
    data = path.read_bytes()
    size = len(data)
    git_sha1 = hashlib.sha1(b"blob %d\0" % size + data).hexdigest()
    return size, git_sha1, hashlib.sha256(data).hexdigest()


def needs_upload(git_sha1: str, sha256: str, remote: dict | None) -> bool:
    if not remote:
        return True
    if remote.get("sha256") and remote["sha256"] == sha256:
        return False
    if remote.get("blob_id") and remote["blob_id"] == git_sha1:
        return False
    return True


def _remote_index(api, repo_id: str, repo_type: str) -> dict:
    from huggingface_hub.utils import RepositoryNotFoundError
    try:
        info = api.repo_info(repo_id=repo_id, repo_type=repo_type, files_metadata=True)
    except RepositoryNotFoundError:
        return {}
    idx = {}
    for s in getattr(info, "siblings", None) or []:
        lfs = getattr(s, "lfs", None)
        sha256 = None
        if lfs:
            sha256 = lfs.get("sha256") if isinstance(lfs, dict) else getattr(lfs, "sha256", None)
        idx[s.rfilename] = {"blob_id": getattr(s, "blob_id", None), "sha256": sha256}
    return idx


def sync_upload(items: list[Item], config: Config, card: str, create_repo: bool) -> int:
    token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACE_HUB_TOKEN")
    if not token:
        print("FAIL: HF_TOKEN is not set (configure it as a GitHub Actions secret).")
        return 1
    try:
        from huggingface_hub import HfApi
        from huggingface_hub.utils import HfHubHTTPError, RepositoryNotFoundError
    except ImportError as exc:  # pragma: no cover
        print(f"FAIL: huggingface_hub is not installed: {exc}")
        return 1

    api = HfApi(token=token)
    repo_id, repo_type = config.target_repo, config.repo_type
    try:
        if create_repo:
            api.create_repo(repo_id=repo_id, repo_type=repo_type,
                            private=config.private, exist_ok=True)
        api.repo_info(repo_id=repo_id, repo_type=repo_type)
    except RepositoryNotFoundError:
        print(f"FAIL: repo '{repo_id}' not found. Use --create-repo or check the token.")
        return 1
    except HfHubHTTPError as exc:
        print(f"FAIL: cannot access '{repo_id}': {exc}")
        return 1

    remote = _remote_index(api, repo_id, repo_type)
    uploaded = skipped = 0
    for i in [x for x in items if x.bucket == "uploadable"]:
        _, git_sha1, sha256 = digests(REPO_ROOT / i.source_path)
        if not needs_upload(git_sha1, sha256, remote.get(i.target_path)):
            print(f"  unchanged  {i.name} -> {i.target_path}")
            skipped += 1
            continue
        try:
            api.upload_file(path_or_fileobj=str(REPO_ROOT / i.source_path),
                            path_in_repo=i.target_path, repo_id=repo_id, repo_type=repo_type,
                            commit_message=f"sync {i.name} ({i.classification})")
        except HfHubHTTPError as exc:
            print(f"FAIL: upload denied for '{i.name}' (write access?): {exc}")
            return 1
        print(f"  uploaded   {i.name} -> {i.target_path}")
        uploaded += 1

    card_sha1 = hashlib.sha1(b"blob %d\0" % len(card.encode()) + card.encode()).hexdigest()
    if needs_upload(card_sha1, hashlib.sha256(card.encode()).hexdigest(), remote.get("README.md")):
        api.upload_file(path_or_fileobj=card.encode("utf-8"), path_in_repo="README.md",
                        repo_id=repo_id, repo_type=repo_type,
                        commit_message="update auto-generated dataset card")
        print("  uploaded   dataset card (README.md)")
    else:
        print("  unchanged  dataset card (README.md)")

    print(f"PASS: sync complete — {uploaded} uploaded, {skipped} unchanged, to '{repo_id}'")
    _summary(f"✅ **dataset sync PASS** — {uploaded} uploaded, {skipped} unchanged "
             f"to `{repo_id}`.")
    return 0


def _summary(line: str) -> None:
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not path:
        return
    try:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except OSError:
        pass


# --------------------------------------------------------------------------- #
# Report + CLI
# --------------------------------------------------------------------------- #
def report(items: list[Item]) -> None:
    buckets = {"uploadable": [], "blocked": [], "manual_review": []}
    for i in items:
        buckets[i.bucket].append(i)
    for bucket, title in [("uploadable", "UPLOADABLE"), ("blocked", "BLOCKED"),
                          ("manual_review", "MANUAL REVIEW")]:
        print(f"\n=== {title} ({len(buckets[bucket])}) ===")
        for i in sorted(buckets[bucket], key=lambda x: x.gov_path):
            print(f"  [{i.classification:<10}] {i.gov_path}  ({i.size_mb} MB)  — {i.reason}")


def run(mode: str, only: str | None, create_repo: bool) -> int:
    config = load_config(SYNC_CONFIG)
    items = classify_all(discover(), config)
    if only:
        items = [i for i in items if i.name == only or Path(i.name).stem == only]
        if not items:
            print(f"FAIL: --only '{only}' matched nothing")
            return 1
    write_inventory(items, config)
    write_manifest(items, config)
    print(f"Inventory: {INVENTORY_JSON.relative_to(REPO_ROOT)} / "
          f"{INVENTORY_MD.relative_to(REPO_ROOT)}")
    print(f"Generated manifest: {GENERATED_MANIFEST.relative_to(REPO_ROOT)}")
    report(items)

    uploadable = [i for i in items if i.bucket == "uploadable"]
    if mode == "discover":
        return 0

    # Validate uploadable datasets (exists, labels, rows, schema) before any push.
    validations, invalid = [], 0
    print("\n=== VALIDATION (uploadable) ===")
    for i in uploadable:
        v = up.validate_dataset(_to_entry(i))
        if v.ok:
            print(f"  OK    {i.name} rows={v.row_count} cols={len(v.columns)} "
                  f"labels[{up._labels_line(v)}]")
            validations.append((_to_entry(i), v))
        else:
            print(f"  INVALID {i.name}: {v.error}")
            invalid += 1
    if invalid:
        print(f"\nFAIL: {invalid} uploadable dataset(s) failed validation — nothing uploaded.")
        return 1
    if not validations:
        print("\nNothing uploadable.")
        return 0

    card = up.generate_card({"pretty_name": "OMI Authenticity Dataset",
                             "repo_id": config.target_repo}, validations)
    if mode == "dry-run":
        print(f"\nDRY-RUN: {len(validations)} dataset(s) would sync (incremental). "
              "No network calls made.")
        return 0
    print(f"\nSYNC: uploading {len(validations)} dataset(s) (incremental) …")
    return sync_upload(items, config, card, create_repo)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="OmiSphere GitHub -> HF dataset sync")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--discover", action="store_true", help="write inventory + manifest only")
    g.add_argument("--dry-run", action="store_true", help="default: validate + plan, no network")
    g.add_argument("--sync", action="store_true", help="incremental upload (needs HF_TOKEN)")
    p.add_argument("--only", default=None)
    p.add_argument("--create-repo", action="store_true")
    args = p.parse_args(argv)
    mode = "discover" if args.discover else "sync" if args.sync else "dry-run"
    return run(mode, args.only, args.create_repo)


if __name__ == "__main__":
    sys.exit(main())
