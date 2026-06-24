#!/usr/bin/env python3
"""Hugging Face Analyst model PULL check (OMI_ANALYST_MODEL_IMPORT_V1).

Verifies that GitHub (or any consumer) can **pull** the Omi Analyst registry repo
``Andrewexiga/omi-analyst-v1`` from Hugging Face using ``HF_TOKEN``: it authenticates,
reads the repo, and downloads the lightweight text artifacts (card, config, prompt,
schema, base pointer) via ``snapshot_download`` — proving the end-to-end pull path,
not just metadata access. Weights are intentionally excluded so the check stays light.

It deliberately does NOT train, fine-tune, upload, modify production code, or touch
scoring. Read-only pull. ``HF_TOKEN`` is never printed.

Exit code 0 = PASS, non-zero = FAIL. Built for CI
(``.github/workflows/hf-analyst-pull.yml``) but runnable locally with ``HF_TOKEN``.

Env:
  HF_TOKEN                 (required) Hugging Face access token; read-only is enough.
  OMI_ANALYST_HF_REPO      (optional) repo to pull; default Andrewexiga/omi-analyst-v1.
  OMI_ANALYST_HF_REVISION  (optional) pin a revision/sha/tag; default the repo's main.
"""
from __future__ import annotations

import os
import sys
import tempfile
from typing import NoReturn

REPO_ID = os.environ.get("OMI_ANALYST_HF_REPO", "Andrewexiga/omi-analyst-v1")
REVISION = os.environ.get("OMI_ANALYST_HF_REVISION") or None

# Pull only the lightweight contract/text artifacts — never the weights.
ALLOW_PATTERNS = [
    "*.md", "*.json", ".gitattributes",
    "config/*", "prompts/*", "schema/*", "base/*", "model_cards/*",
]


def _summary(line: str) -> None:
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not path:
        return
    try:
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(line + "\n")
    except OSError:
        pass


def fail(message: str) -> NoReturn:
    print(f"FAIL: {message}")
    _summary(f"❌ **HF analyst pull FAIL** — {message}")
    sys.exit(1)


def main() -> int:
    token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACE_HUB_TOKEN")
    if not token:
        fail("HF_TOKEN is not set (configure it as a GitHub Actions secret).")

    try:
        from huggingface_hub import HfApi, snapshot_download
        from huggingface_hub.utils import (
            GatedRepoError,
            HfHubHTTPError,
            RepositoryNotFoundError,
        )
    except ImportError as exc:  # pragma: no cover - CI installs the dependency
        fail(f"huggingface_hub is not installed: {exc}")

    api = HfApi(token=token)

    # 1) Authenticate.
    try:
        who = api.whoami()
    except HfHubHTTPError as exc:
        fail(f"authentication failed (token rejected): {exc}")
    except Exception as exc:  # network / unexpected
        fail(f"could not reach Hugging Face to authenticate: {exc}")
    identity = who.get("name") or who.get("fullname") or "<unknown>"
    print(f"Authenticated as: {identity}")

    # 2) Read the repo.
    try:
        info = api.repo_info(repo_id=REPO_ID, repo_type="model", revision=REVISION)
    except RepositoryNotFoundError:
        fail(f"repo '{REPO_ID}' not found or token lacks read access.")
    except GatedRepoError:
        fail(f"repo '{REPO_ID}' is gated and the token lacks access.")
    except HfHubHTTPError as exc:
        fail(f"could not read repo '{REPO_ID}': {exc}")
    except Exception as exc:  # network / unexpected
        fail(f"could not reach Hugging Face to read '{REPO_ID}': {exc}")

    visibility = "private" if getattr(info, "private", False) else "public"
    sha = (getattr(info, "sha", None) or "<none>")[:12]

    # 3) Actually pull the lightweight artifacts (the real "can GitHub pull it" test).
    try:
        with tempfile.TemporaryDirectory() as tmp:
            path = snapshot_download(
                repo_id=REPO_ID, repo_type="model", revision=REVISION,
                token=token, local_dir=tmp, allow_patterns=ALLOW_PATTERNS,
            )
            pulled = [
                os.path.relpath(os.path.join(root, f), path)
                for root, _dirs, fnames in os.walk(path) for f in fnames
                if not f.startswith(".")  # skip .cache bookkeeping
            ]
    except HfHubHTTPError as exc:
        fail(f"pull (snapshot_download) failed for '{REPO_ID}': {exc}")
    except Exception as exc:  # network / unexpected
        fail(f"could not pull '{REPO_ID}': {exc}")

    n = len(pulled)
    if n == 0:
        # Auth + read + download path all work, but the repo has no artifacts yet.
        print(f"PASS (pull path OK): '{REPO_ID}' ({visibility}, rev {sha}) reachable and "
              "downloadable, but 0 artifacts matched — the repo is not populated yet. "
              "Run the registration (hf-analyst-register) to publish the V1 files.")
        _summary(f"⚠️ **HF analyst pull OK, repo empty** — `{identity}` can pull "
                 f"`{REPO_ID}` ({visibility}, rev `{sha}`); 0 artifacts — run "
                 "`hf-analyst-register` to populate it.")
        return 0

    preview = ", ".join(sorted(pulled)[:8]) + (" …" if n > 8 else "")
    print(f"PASS: pulled {n} artifact(s) from '{REPO_ID}' ({visibility}, rev {sha}): "
          f"{preview}")
    _summary(f"✅ **HF analyst pull PASS** — `{identity}` pulled {n} artifact(s) from "
             f"`{REPO_ID}` ({visibility}, rev `{sha}`).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
