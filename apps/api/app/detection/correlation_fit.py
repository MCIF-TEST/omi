"""Fit the signal-correlation model from observed detector outputs.

Pure stdlib — no numpy — so it can run inside the API process or a one-off
script without pulling heavy deps onto the runtime path. The unit of
observation is one account's per-detector probability vector, taken from its
most recent persisted scan; only detectors that actually fired (confidence > 0)
contribute, and each pairwise correlation is computed over the accounts where
*both* detectors fired (pairwise-complete), so a detector that abstains on most
accounts doesn't poison the matrix.

The output artifact is consumed by :class:`app.detection.correlation.CorrelationModel`.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone

from app.detection.correlation import DETECTORS

ARTIFACT_VERSION = 1


def _pearson(xs: list[float], ys: list[float]) -> float:
    n = len(xs)
    if n < 2:
        return 0.0
    mx = sum(xs) / n
    my = sum(ys) / n
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    if sxx <= 0 or syy <= 0:
        return 0.0
    return sxy / math.sqrt(sxx * syy)


def fit_correlation(
    observations: list[dict[str, float]],
    *,
    detectors: tuple[str, ...] = DETECTORS,
    min_pairs: int = 20,
    strength: float = 0.5,
    floor: float = 0.15,
    axis_threshold: float = 0.5,
) -> dict:
    """Compute a pairwise correlation matrix from per-account signal vectors.

    A pair with fewer than ``min_pairs`` joint observations is set to 0.0
    (insufficient evidence → treat as independent) and its low support is
    recorded so an operator can see which cells are trustworthy.
    """
    n = len(detectors)
    matrix = [[0.0] * n for _ in range(n)]
    support = [[0] * n for _ in range(n)]
    for i in range(n):
        matrix[i][i] = 1.0
        di = detectors[i]
        for j in range(i + 1, n):
            dj = detectors[j]
            xs: list[float] = []
            ys: list[float] = []
            for obs in observations:
                if di in obs and dj in obs:
                    xs.append(obs[di])
                    ys.append(obs[dj])
            support[i][j] = support[j][i] = len(xs)
            r = _pearson(xs, ys) if len(xs) >= min_pairs else 0.0
            # Only positive correlation represents double-counted evidence; clamp
            # negatives to 0 so anti-correlated detectors aren't discounted.
            matrix[i][j] = matrix[j][i] = round(max(0.0, r), 4)

    return {
        "version": ARTIFACT_VERSION,
        "fitted_at": datetime.now(timezone.utc).isoformat(),
        "n_observations": len(observations),
        "min_pairs": min_pairs,
        "detectors": list(detectors),
        "matrix": matrix,
        "pair_support": support,
        "strength": strength,
        "floor": floor,
        "axis_threshold": axis_threshold,
    }


def observations_from_session(session, *, only_labeled: bool = True) -> list[dict[str, float]]:
    """Build per-account observations from the most recent persisted scan of
    each account (optionally restricted to labeled accounts)."""
    from sqlalchemy import select

    from app.storage.models import Account, AccountLabel, Scan

    stmt = select(Account)
    if only_labeled:
        stmt = select(Account).join(AccountLabel, AccountLabel.account_id == Account.id)
    accounts = list({a.id: a for a in session.execute(stmt).scalars().all()}.values())

    observations: list[dict[str, float]] = []
    for acc in accounts:
        scan = session.execute(
            select(Scan).where(Scan.account_id == acc.id)
            .order_by(Scan.scanned_at.desc()).limit(1)
        ).scalar_one_or_none()
        if scan is None or not scan.signals_json:
            continue
        vec: dict[str, float] = {}
        for s in scan.signals_json:
            try:
                if float(s.get("confidence") or 0.0) > 0.0:
                    vec[s["name"]] = float(s["probability"])
            except (KeyError, TypeError, ValueError):
                continue
        if vec:
            observations.append(vec)
    return observations
