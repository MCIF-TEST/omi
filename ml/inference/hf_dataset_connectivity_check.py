#!/usr/bin/env python3
"""Hugging Face DATASET connectivity check (read + write probe).

Verifies that GitHub Actions can authenticate to Hugging Face with ``HF_TOKEN``,
**read** the dataset repository, and that the token has **upload (write)**
permission -- proven by uploading a tiny temporary probe file and then deleting
it. It uploads NO real dataset and leaves the repo clean.

It deliberately does NOT train, modify production code, or touch scoring.

Exit code 0 = PASS, non-zero = FAIL. Built for CI
(``.github/workflows/hf-dataset-connectivity.yml``) but runnable locally with a
write-capable ``HF_TOKEN`` exported.

Env:
  HF_TOKEN      (required) write-capable token to fully pass the upload probe.
  HF_REPO_ID    (optional) repo to verify; default Andrewexiga/omi-authenticity-dataset.
  HF_REPO_TYPE  (optional) dataset | model | space; default dataset.
"""
from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime, timezone
from typing import NoReturn

REPO_ID = os.environ.get("HF_REPO_ID", "Andrewexiga/omi-authenticity-dataset")
REPO_TYPE = os.environ.get("HF_REPO_TYPE", "dataset")


def _summary(line: str) -> None:
    """Append a line to the GitHub Actions step summary, if running in CI."""
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not path:
        return
    try:
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(line + "\n")
    except OSError:
        pass


def fail(message: str) -> NoReturn:
    """Print a clear FAIL line, record it in the CI summary, and exit non-zero."""
    print(f"FAIL: {message}")
    _summary(f"❌ **HF dataset connectivity FAIL** — {message}")
    sys.exit(1)


def main() -> int:
    # Check the token first so the missing-token path needs no dependencies.
    token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACE_HUB_TOKEN")
    if not token:
        fail("HF_TOKEN is not set (configure it as a GitHub Actions secret).")

    try:
        from huggingface_hub import HfApi
        from huggingface_hub.utils import (
            GatedRepoError,
            HfHubHTTPError,
            RepositoryNotFoundError,
        )
    except ImportError as exc:  # pragma: no cover - CI installs the dependency
        fail(f"huggingface_hub is not installed: {exc}")

    api = HfApi(token=token)

    # 1) Authenticate: confirm the token is valid (never print the token itself).
    try:
        who = api.whoami()
    except HfHubHTTPError as exc:
        fail(f"authentication failed (token rejected): {exc}")
    except Exception as exc:  # network / unexpected
        fail(f"could not reach Hugging Face to authenticate: {exc}")
    identity = who.get("name") or who.get("fullname") or "<unknown>"
    print(f"Authenticated as: {identity}")

    # 2) Verify READ access to the dataset repository.
    try:
        info = api.repo_info(repo_id=REPO_ID, repo_type=REPO_TYPE)
    except RepositoryNotFoundError:
        fail(
            f"repo '{REPO_ID}' ({REPO_TYPE}) not found or token lacks read "
            "access -- create it (or check the repo id / token) before "
            "verifying upload."
        )
    except GatedRepoError:
        fail(f"repo '{REPO_ID}' is gated and the token lacks access.")
    except HfHubHTTPError as exc:
        fail(f"could not read repo '{REPO_ID}': {exc}")
    except Exception as exc:  # network / unexpected
        fail(f"could not reach Hugging Face to read '{REPO_ID}': {exc}")
    visibility = "private" if getattr(info, "private", False) else "public"
    print(f"Read OK: reached '{REPO_ID}' ({REPO_TYPE}, {visibility})")

    # 3) Verify UPLOAD (write) permission with a tiny temporary probe file, then
    #    delete it. No real dataset is uploaded; the repo is left clean.
    run_id = os.environ.get("GITHUB_RUN_ID", "local")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    probe_path = f".omi_connectivity_probe/probe-{stamp}-{run_id}-{uuid.uuid4().hex[:8]}.txt"
    content = (
        "OmiSphere Hugging Face dataset connectivity probe.\n"
        f"Created (UTC): {stamp}\n"
        f"GitHub run: {run_id}\n"
        "Temporary write-permission check -- not a dataset, safe to delete.\n"
    ).encode("utf-8")

    try:
        api.upload_file(
            path_or_fileobj=content,
            path_in_repo=probe_path,
            repo_id=REPO_ID,
            repo_type=REPO_TYPE,
            commit_message="chore: connectivity write probe (temporary, auto-removed)",
        )
    except (HfHubHTTPError, GatedRepoError) as exc:
        fail(
            f"upload permission denied for '{REPO_ID}' -- the token lacks write "
            f"access (use a write-capable token): {exc}"
        )
    except Exception as exc:  # network / unexpected
        fail(f"upload probe to '{REPO_ID}' failed: {exc}")
    print(f"Upload OK: wrote temporary probe '{probe_path}'")

    # 4) Remove the probe -- proves delete permission AND leaves the repo clean.
    try:
        api.delete_file(
            path_in_repo=probe_path,
            repo_id=REPO_ID,
            repo_type=REPO_TYPE,
            commit_message="chore: remove connectivity write probe",
        )
    except Exception as exc:
        # Write was proven, but a leftover probe violates "remove it" -- fail loudly.
        fail(
            f"probe uploaded but cleanup FAILED -- manually remove '{probe_path}' "
            f"from '{REPO_ID}': {exc}"
        )
    print(f"Cleanup OK: removed temporary probe '{probe_path}'")

    print(
        f"PASS: read + write verified on '{REPO_ID}' ({REPO_TYPE}, {visibility}); "
        "probe removed, no real data uploaded"
    )
    _summary(
        f"✅ **HF dataset connectivity PASS** — authenticated as `{identity}`, "
        f"read + upload + delete verified on `{REPO_ID}` ({visibility}); "
        "temporary probe removed, no real data uploaded."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
