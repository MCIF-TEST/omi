#!/usr/bin/env python3
"""Hugging Face connectivity check (read-only).

Verifies that Omi can authenticate to Hugging Face with ``HF_TOKEN`` and read the
target model repository. It deliberately does NOT train, upload, modify
production code, or touch scoring -- it only reads metadata.

Exit code 0 = PASS, non-zero = FAIL. Built for CI
(``.github/workflows/hf-connectivity.yml``) but runnable locally with
``HF_TOKEN`` exported.

Env:
  HF_TOKEN      (required) Hugging Face access token; read-only is sufficient.
  HF_REPO_ID    (optional) repo to verify; default Andrewexiga/omi-behavioral-model-v1.
  HF_REPO_TYPE  (optional) model | dataset | space; default model.
"""
from __future__ import annotations

import os
import sys
from typing import NoReturn

REPO_ID = os.environ.get("HF_REPO_ID", "Andrewexiga/omi-behavioral-model-v1")
REPO_TYPE = os.environ.get("HF_REPO_TYPE", "model")


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
    _summary(f"❌ **HF connectivity FAIL** — {message}")
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

    # 2) Verify read access to the target repository.
    try:
        info = api.repo_info(repo_id=REPO_ID, repo_type=REPO_TYPE)
    except RepositoryNotFoundError:
        fail(
            f"repo '{REPO_ID}' ({REPO_TYPE}) not found or token lacks read "
            "access -- check the repo id and that the token can read it."
        )
    except GatedRepoError:
        fail(f"repo '{REPO_ID}' is gated and the token lacks access.")
    except HfHubHTTPError as exc:
        fail(f"could not read repo '{REPO_ID}': {exc}")
    except Exception as exc:  # network / unexpected
        fail(f"could not reach Hugging Face to read '{REPO_ID}': {exc}")

    visibility = "private" if getattr(info, "private", False) else "public"
    sha = getattr(info, "sha", None) or "<none>"
    print(
        f"PASS: reached '{REPO_ID}' ({REPO_TYPE}, {visibility}, "
        f"revision {sha[:12]})"
    )
    _summary(
        f"✅ **HF connectivity PASS** — authenticated as "
        f"`{identity}`, read `{REPO_ID}` ({visibility}, rev `{sha[:12]}`)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
