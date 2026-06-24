#!/usr/bin/env python3
"""OmiSphere -> Hugging Face MODEL registration (OMI_ANALYST_MODEL_IMPORT_V1).

Registers / populates the permanent Omi Analyst registry repo
``Andrewexiga/omi-analyst-v1`` from ``ml/analyst/hf_repo_manifest.toml``: the V1
model card (which carries the ``base_model`` YAML metadata that *configures the
foundation model* on the Hub), the config, the base pointer, the system prompt, and
the response schema. The GitHub monorepo stays the source of truth; this publishes the
approved mirror.

SAFETY (production-safe by design):
  * Upload requires the explicit ``--upload`` flag. Default is ``--validate``: no token,
    no network, and no ``huggingface_hub`` dependency needed.
  * Publishes NO weights (V1 = base model + prompt). It does NOT fine-tune, train,
    modify production scoring / detectors / OmiScore, or touch apps/api | apps/web.
  * ``create_repo`` uses ``exist_ok=True`` + ``private=True`` (the repo already exists
    and stays private).
  * ``HF_TOKEN`` is read from the environment and never printed.

Exit 0 = OK, non-zero = failure. Built for CI
(``.github/workflows/hf-analyst-register.yml``) and runnable locally:
    python ml/analyst/register_hf_model.py --validate          # offline, default
    python ml/analyst/register_hf_model.py --dry-run           # print the publish plan
    HF_TOKEN=... python ml/analyst/register_hf_model.py --upload --create-repo
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST = "ml/analyst/hf_repo_manifest.toml"


# --------------------------------------------------------------------------- #
# Manifest
# --------------------------------------------------------------------------- #
def load_manifest(path: Path) -> tuple[dict, list[dict]]:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    target = data.get("target", {})
    files = data.get("file", [])
    return target, files


# --------------------------------------------------------------------------- #
# Frontmatter (stdlib only — no PyYAML dependency)
# --------------------------------------------------------------------------- #
def parse_frontmatter(text: str) -> dict[str, str]:
    """Extract simple scalar keys from a leading ``---`` YAML frontmatter block.

    Only the scalar keys we care about (e.g. ``base_model``, ``license``) are needed.
    A list-valued key returns its first ``- `` item. Returns {} if no frontmatter.
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end = i
            break
    if end is None:
        return {}
    block = lines[1:end]
    out: dict[str, str] = {}
    i = 0
    while i < len(block):
        line = block[i]
        if ":" in line and not line.lstrip().startswith("-"):
            key, _, val = line.partition(":")
            key = key.strip()
            val = val.strip()
            if val == "" and i + 1 < len(block) and block[i + 1].lstrip().startswith("- "):
                val = block[i + 1].lstrip()[2:].strip()  # first list item
            out[key] = val
        i += 1
    return out


# --------------------------------------------------------------------------- #
# Validation
# --------------------------------------------------------------------------- #
def validate(target: dict, files: list[dict]) -> tuple[bool, list[tuple[str, str, str]], list[str]]:
    """Return (ok, resolved[(source, path_in_repo, kind)], errors).

    Checks every source exists, every JSON parses, the model card's ``base_model``
    frontmatter matches ``target.base_model``, and ``analyst_config.json``'s
    ``base_model`` agrees too. No token, no network.
    """
    errors: list[str] = []
    resolved: list[tuple[str, str, str]] = []

    if not target.get("repo_id"):
        errors.append("manifest [target].repo_id is missing")
    declared_base = target.get("base_model", "")
    if not declared_base:
        errors.append("manifest [target].base_model is missing")

    if not files:
        errors.append("manifest declares no [[file]] entries")

    card_base: str | None = None
    cfg_base: str | None = None

    for entry in files:
        src = entry.get("source", "")
        dst = entry.get("path_in_repo", "")
        kind = entry.get("kind", "")
        if not src or not dst:
            errors.append(f"file entry missing source/path_in_repo: {entry!r}")
            continue
        abs_src = REPO_ROOT / src
        if not abs_src.is_file():
            errors.append(f"source not found: {src}")
            continue
        resolved.append((src, dst, kind))

        if src.endswith(".json"):
            try:
                data = json.loads(abs_src.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                errors.append(f"invalid JSON in {src}: {exc}")
                data = None
            if data is not None and abs_src.name == "analyst_config.json":
                cfg_base = data.get("base_model")

        if kind == "model_card":
            fm = parse_frontmatter(abs_src.read_text(encoding="utf-8"))
            card_base = fm.get("base_model")
            if not fm.get("license"):
                errors.append(f"model card {src} frontmatter missing 'license'")
            if not card_base:
                errors.append(f"model card {src} frontmatter missing 'base_model'")

    if declared_base and card_base and card_base != declared_base:
        errors.append(
            f"base_model mismatch: model card '{card_base}' != manifest '{declared_base}'"
        )
    if declared_base and cfg_base and cfg_base != declared_base:
        errors.append(
            f"base_model mismatch: analyst_config.json '{cfg_base}' != manifest '{declared_base}'"
        )

    return (len(errors) == 0), resolved, errors


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


def do_upload(target: dict, resolved: list[tuple[str, str, str]], create_repo: bool) -> int:
    token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACE_HUB_TOKEN")
    if not token:
        print("FAIL: HF_TOKEN is not set (configure it as a GitHub Actions secret).")
        _summary("❌ **analyst registration FAIL** — HF_TOKEN not set.")
        return 1
    try:
        from huggingface_hub import HfApi
        from huggingface_hub.utils import HfHubHTTPError, RepositoryNotFoundError
    except ImportError as exc:  # pragma: no cover - CI installs the dependency
        print(f"FAIL: huggingface_hub is not installed: {exc}")
        return 1

    repo_id = target["repo_id"]
    repo_type = target.get("repo_type", "model")
    api = HfApi(token=token)

    try:
        if create_repo:
            api.create_repo(
                repo_id=repo_id, repo_type=repo_type,
                private=bool(target.get("private", True)), exist_ok=True,
            )
        info = api.repo_info(repo_id=repo_id, repo_type=repo_type)
    except RepositoryNotFoundError:
        print(f"FAIL: repo '{repo_id}' not found or no access. Use --create-repo "
              "(or check the token has write access).")
        return 1
    except HfHubHTTPError as exc:
        print(f"FAIL: cannot access '{repo_id}': {exc}")
        return 1

    visibility = "private" if getattr(info, "private", True) else "public"
    print(f"Target: {repo_id} ({repo_type}, {visibility})")

    for src, dst, _kind in resolved:
        try:
            api.upload_file(
                path_or_fileobj=str(REPO_ROOT / src),
                path_in_repo=dst,
                repo_id=repo_id, repo_type=repo_type,
                commit_message=f"omi-analyst V1 registration: {dst}",
            )
        except HfHubHTTPError as exc:
            print(f"FAIL: upload denied for '{dst}' -> '{repo_id}' (write access?): {exc}")
            return 1
        print(f"  uploaded {src} -> {dst}")

    print(f"PASS: published {len(resolved)} file(s) to '{repo_id}' "
          f"(base_model={target.get('base_model')}, no weights).")
    _summary(f"✅ **analyst registration PASS** — published {len(resolved)} file(s) to "
             f"`{repo_id}` (base_model `{target.get('base_model')}`, no weights).")
    return 0


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def run(manifest_path: Path, action: str, create_repo: bool) -> int:
    target, files = load_manifest(manifest_path)
    ok, resolved, errors = validate(target, files)

    print(f"Target: {target.get('repo_id')} ({target.get('repo_type', 'model')})  "
          f"base_model={target.get('base_model')}")
    for src, dst, kind in resolved:
        print(f"OK   {src:<46} -> {dst}  [{kind}]")
    for err in errors:
        print(f"ERR  {err}")

    if not ok:
        print(f"\nFAIL: {len(errors)} validation error(s) — nothing published.")
        _summary(f"❌ **analyst registration FAIL** — {len(errors)} validation error(s).")
        return 1

    if action == "validate":
        print(f"\nVALIDATE OK: {len(resolved)} file(s) ready to publish (no upload).")
        return 0
    if action == "dry-run":
        print(f"\nDRY-RUN: would publish {len(resolved)} file(s) to "
              f"'{target.get('repo_id')}' — no write performed.")
        return 0
    print(f"\nUPLOAD: publishing {len(resolved)} file(s) …")
    return do_upload(target, resolved, create_repo)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="OmiSphere -> Hugging Face Analyst MODEL registration")
    p.add_argument("--manifest", default=DEFAULT_MANIFEST)
    g = p.add_mutually_exclusive_group()
    g.add_argument("--validate", action="store_true",
                   help="validate the manifest + files only (default; no token/network)")
    g.add_argument("--dry-run", action="store_true",
                   help="validate + print the publish plan (no write)")
    g.add_argument("--upload", action="store_true",
                   help="validate + publish to HF (needs HF_TOKEN write access)")
    p.add_argument("--create-repo", action="store_true",
                   help="create the repo (private) if missing (exist_ok)")
    args = p.parse_args(argv)

    action = "validate" if args.validate else "upload" if args.upload else \
        "dry-run" if args.dry_run else "validate"
    manifest_path = (REPO_ROOT / args.manifest) if not Path(args.manifest).is_absolute() \
        else Path(args.manifest)
    if not manifest_path.is_file():
        print(f"FAIL: manifest not found: {manifest_path}")
        return 1
    return run(manifest_path, action, args.create_repo)


if __name__ == "__main__":
    sys.exit(main())
