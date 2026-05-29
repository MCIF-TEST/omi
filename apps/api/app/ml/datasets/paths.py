"""Resolve the repo's ``datasets/`` directory.

Override with the ``OMI_DATASETS_DIR`` environment variable; otherwise we walk
up from this file looking for a ``datasets`` folder (works whether the API runs
from ``apps/api`` or the repo root).
"""

from __future__ import annotations

import os
from pathlib import Path


def default_datasets_dir() -> Path:
    env = os.environ.get("OMI_DATASETS_DIR")
    if env:
        return Path(env).expanduser()
    here = Path(__file__).resolve()
    # Anchor to the repo root (the dir holding ``.git`` or ``apps``) so we don't
    # accidentally match this package's own ``app/ml/datasets`` folder.
    for parent in here.parents:
        if (parent / ".git").exists() or (parent / "apps").is_dir():
            return parent / "datasets"
    return here.parents[4] / "datasets" if len(here.parents) > 4 else Path("datasets")


GENERATED_SUBDIR = "_generated"


def generated_dir(root: Path | None = None) -> Path:
    root = Path(root) if root is not None else default_datasets_dir()
    return root / GENERATED_SUBDIR
