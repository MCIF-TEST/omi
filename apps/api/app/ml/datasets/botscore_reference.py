"""External bot-score reference (``activity_botscore.csv``) for tier calibration.

The dataset carries a continuous Botometer score per account (``bot_score_english``,
0–1) with **no class label**, so it can neither train a model nor be scored through
the engine. What it *can* do is anchor the **expected base rate**: what fraction of a
real population an *independent* bot detector considers bot-like. That base rate is a
sanity check for Omi's own flag rate — if Omi escalates a far larger share of a
comparable population, the thresholds are likely too aggressive.

This is intentionally a small, read-only reference utility (status ``reference`` in
the manifest), not an ingest adapter: profile-only rows are non-discriminative
through the engine, so persisting them would add noise, not signal.
"""

from __future__ import annotations

import csv
import statistics
from pathlib import Path

# Mirror app.detection.scoring._tier_for so the external score speaks Omi's tiers.
_CUTOFFS = ((0.25, "low"), (0.50, "moderate"), (0.75, "elevated"))


def score_to_tier(score: float) -> str:
    for hi, name in _CUTOFFS:
        if score < hi:
            return name
    return "high"


def botscore_distribution(path: str | Path) -> dict:
    """Tier-binned distribution of the external bot scores.

    Returns counts + fractions per Omi tier and the ``flagged_fraction``
    (elevated+high) — the base rate to compare Omi's escalation rate against.
    """
    scores: list[float] = []
    with Path(path).open(encoding="utf-8", errors="replace") as fh:
        for row in csv.DictReader(fh):
            raw = row.get("bot_score_english")
            try:
                scores.append(float(raw))
            except (TypeError, ValueError):
                continue
    n = len(scores)
    tiers = {"low": 0, "moderate": 0, "elevated": 0, "high": 0}
    for s in scores:
        tiers[score_to_tier(s)] += 1
    flagged = tiers["elevated"] + tiers["high"]
    return {
        "n": n,
        "mean_bot_score": round(statistics.fmean(scores), 4) if scores else 0.0,
        "tiers": tiers,
        "tier_fractions": {k: round(v / n, 4) for k, v in tiers.items()} if n else {},
        "flagged_fraction": round(flagged / n, 4) if n else 0.0,  # elevated+high
    }
