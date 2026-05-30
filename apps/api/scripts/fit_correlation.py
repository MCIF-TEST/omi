"""Fit + write the learned signal-correlation model.

Runs over the accounts already in the database (their most recent scans),
measures how the detectors co-vary, and writes the artifact the aggregator
loads at runtime. With no artifact the engine uses its hand-tuned defaults, so
this is the step that turns the decorrelation factors and independence axes from
estimates into measurements.

    cd apps/api

    # Preview the matrix without writing it.
    python -m scripts.fit_correlation --dry-run

    # Fit over labeled accounts and write to the configured path.
    python -m scripts.fit_correlation

    # Bootstrap data first: generate + ingest the synthetic corpus, then fit.
    python -m scripts.datasets synthetic --n 60
    python -m scripts.fit_correlation --all
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings  # noqa: E402
from app.detection.correlation import DETECTORS  # noqa: E402
from app.detection.correlation_fit import (  # noqa: E402
    fit_correlation,
    observations_from_session,
)


def _print_matrix(artifact: dict) -> None:
    det = artifact["detectors"]
    short = [d[:6] for d in det]
    print(f"n_observations: {artifact['n_observations']}  "
          f"min_pairs: {artifact['min_pairs']}")
    print("        " + " ".join(f"{s:>6}" for s in short))
    for i, row in enumerate(artifact["matrix"]):
        print(f"{short[i]:>6}  " + " ".join(f"{v:6.2f}" for v in row))


def main() -> int:
    ap = argparse.ArgumentParser(description="Fit the learned signal-correlation model.")
    settings = get_settings()
    ap.add_argument("--out", type=Path, default=Path(settings.correlation_model_path))
    ap.add_argument("--all", action="store_true",
                    help="Use every scanned account, not just labeled ones.")
    ap.add_argument("--min-pairs", type=int, default=20,
                    help="Min joint observations before a pair's correlation is trusted.")
    ap.add_argument("--strength", type=float, default=0.5,
                    help="How aggressively correlation discounts (0..1).")
    ap.add_argument("--floor", type=float, default=0.15,
                    help="Lower bound on any single detector's contribution factor.")
    ap.add_argument("--axis-threshold", type=float, default=0.5,
                    help="Correlation at/above which two detectors share an axis.")
    ap.add_argument("--dry-run", action="store_true",
                    help="Print the matrix; do not write the artifact.")
    args = ap.parse_args()

    try:
        from app.storage.db import get_session
    except Exception as e:  # noqa: BLE001
        print(f"No DB available: {e}", file=sys.stderr)
        return 1

    with get_session() as session:
        observations = observations_from_session(session, only_labeled=not args.all)

    if not observations:
        print("No usable observations found. Scan or ingest some accounts first "
              "(e.g. python -m scripts.datasets synthetic), then re-run.",
              file=sys.stderr)
        return 1

    artifact = fit_correlation(
        observations,
        detectors=DETECTORS,
        min_pairs=args.min_pairs,
        strength=args.strength,
        floor=args.floor,
        axis_threshold=args.axis_threshold,
    )

    _print_matrix(artifact)

    if args.dry_run:
        print("\n(dry run — artifact not written)")
        return 0

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(artifact, indent=2), encoding="utf-8")
    print(f"\nwrote correlation model → {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
