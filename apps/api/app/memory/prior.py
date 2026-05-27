"""Memory-derived prior signal.

Given a freshly-computed fingerprint for an account, ask the persistent
fingerprint store: "Have we seen accounts that behave like this before? What
did we conclude about them?"

If the nearest neighbors cluster around high suspicion, that becomes
additional evidence in the scorer. If the DB is empty or no close neighbors
exist, the signal returns zero confidence so it doesn't move the score.

This is what makes Omi self-improving: every scan grows the reference set
that future scans get compared against.
"""

from __future__ import annotations

from app.memory.fingerprint import euclidean
from app.schemas import SignalResult
from app.storage.models import Account


def compute_memory_signal(
    fingerprint: list[float],
    candidates: list[Account],
    *,
    k: int = 5,
    distance_threshold: float = 0.35,
    exclude_external_id: str | None = None,
) -> SignalResult:
    """Find the k nearest neighbors and turn them into a SignalResult.

    Parameters
    ----------
    fingerprint
        The freshly-computed normalized vector for the account being scored.
    candidates
        Every persisted account that has a fingerprint (the caller decides
        how to load them; this function does no I/O).
    k
        How many neighbors to consider.
    distance_threshold
        Neighbors farther than this are ignored. Smaller = stricter match.
    exclude_external_id
        Skip this account when present (used during re-scans so an account
        doesn't get matched to itself).
    """
    if not candidates:
        return SignalResult(
            name="memory",
            probability=0.5,
            confidence=0.0,
            evidence=["No prior fingerprints in the database yet."],
        )

    distances: list[tuple[float, Account]] = []
    for cand in candidates:
        if exclude_external_id and cand.external_id == exclude_external_id:
            continue
        if not cand.fingerprint_json or cand.last_score is None:
            continue
        try:
            d = euclidean(fingerprint, cand.fingerprint_json)
        except ValueError:
            # Fingerprint dimensions changed between deployments — ignore old vectors.
            continue
        distances.append((d, cand))

    distances.sort(key=lambda x: x[0])
    close = [(d, c) for d, c in distances[:k] if d <= distance_threshold]

    if not close:
        return SignalResult(
            name="memory",
            probability=0.5,
            confidence=0.0,
            evidence=[
                "No previously-scored accounts behave similarly enough to inform this scan."
            ],
            sub_signals={
                "neighbors_total_in_db": float(len(distances)),
                "nearest_distance": float(distances[0][0]) if distances else 1.0,
                "close_neighbors": 0.0,
            },
        )

    # Inverse-distance weighted average of neighbor probabilities.
    weights = [max(1e-3, 1.0 - d / distance_threshold) for d, _ in close]
    total_w = sum(weights)
    weighted_prob = (
        sum(w * (c.last_score or 0.0) for (_, c), w in zip(close, weights)) / total_w
    )

    # Mean confidence of neighbors moderates this signal's own confidence,
    # so a bunch of low-confidence priors don't get amplified.
    neighbor_conf = sum(c.last_confidence or 0.0 for _, c in close) / len(close)
    # Saturate at k/2 close neighbors.
    coverage = min(1.0, len(close) / max(1, k / 2))
    confidence = coverage * neighbor_conf

    flagged = [c for _, c in close if (c.last_score or 0) >= 0.5]
    evidence = [
        f"Behavioral fingerprint resembles {len(close)} previously-scored "
        f"account{'s' if len(close) != 1 else ''} "
        f"(weighted mean probability {weighted_prob:.2f})."
    ]
    if flagged:
        evidence.append(
            f"{len(flagged)} of those neighbor{'s' if len(flagged) != 1 else ''} "
            f"previously scored at elevated or high suspicion."
        )

    return SignalResult(
        name="memory",
        probability=_clip01(weighted_prob),
        confidence=_clip01(confidence),
        evidence=evidence,
        sub_signals={
            "close_neighbors": float(len(close)),
            "nearest_distance": float(close[0][0]),
            "mean_neighbor_distance": float(sum(d for d, _ in close) / len(close)),
            "neighbors_total_in_db": float(len(distances)),
        },
    )


def _clip01(x: float) -> float:
    return max(0.0, min(1.0, float(x)))
