"""Coordination → per-account score elevation.

When a full video scan detects that an account sits inside one or more
coordination clusters, that cross-account evidence should lift the account's
individual score: a lone commenter with three generic comments is unremarkable,
but the *same* commenter caught inside a 12-account burst-and-amplify ring is a
confirmed campaign participant.

This is the bridge between two otherwise-separate scoring paths:

* the single-account rule engine (conservative by design — it under-flags
  sparse-history accounts because it prefers a miss to a false accusation), and
* the cross-account coordination detectors (which need no per-account history
  depth — they read the *relationships* between accounts on a video).

The logic lived inline in the orchestrator's full-scan path (Phase 4). It is
extracted here so it is:

* **pure** — no I/O, no DB, trivially unit-testable,
* **shared** — the orchestrator and the rescue benchmark both call it, so what
  CI measures is exactly what production runs (the same discipline as
  ``app.evaluation.metrics``).

The elevation never mutates the persisted single-account scan; it composes a
``coordination`` :class:`SignalResult` and re-aggregates a *what-if* result.
"""

from __future__ import annotations

from collections import defaultdict

from app.detection.coordination._types import CoordinationCluster
from app.detection.scoring import aggregate
from app.schemas import ScanResult, SignalResult

# The detector name the aggregator looks up ``weight_coordination`` under.
COORDINATION_SIGNAL_NAME = "coordination"

# Base confidence floor + per-distinct-detector bump. More independent
# detectors agreeing that an account is coordinated => higher confidence in the
# composed signal. Mirrors the original orchestrator constants exactly.
_BASE_CONFIDENCE = 0.55
_PER_METHOD_CONFIDENCE = 0.20
_MAX_EVIDENCE = 5


def coordination_membership(
    clusters: list[CoordinationCluster],
) -> dict[str, list[CoordinationCluster]]:
    """Invert a flat cluster list into ``{member_external_id: [clusters]}``.

    An account can sit in several clusters (e.g. flagged by both the temporal
    burst detector and the fingerprint detector); all of them inform its lift.
    """
    by_member: dict[str, list[CoordinationCluster]] = defaultdict(list)
    for cl in clusters:
        for m in cl.members:
            by_member[m].append(cl)
    return dict(by_member)


def build_coordination_signal(
    clusters: list[CoordinationCluster],
) -> SignalResult | None:
    """Compose a single ``coordination`` SignalResult from a member's clusters.

    Returns ``None`` if the account is in no cluster (no signal to inject).
    The probability is the strongest cluster the account belongs to; the
    confidence rises with the number of *distinct* detector methods that
    independently flagged it.
    """
    if not clusters:
        return None
    methods = sorted({c.method for c in clusters})
    max_p = max(c.score for c in clusters)
    conf = min(1.0, _BASE_CONFIDENCE + _PER_METHOD_CONFIDENCE * len(methods))
    return SignalResult(
        name=COORDINATION_SIGNAL_NAME,
        probability=max_p,
        confidence=conf,
        evidence=[e for c in clusters for e in c.evidence][:_MAX_EVIDENCE],
        sub_signals={"detector_count": float(len(methods))},
    )


def apply_coordination(
    scan: ScanResult,
    clusters: list[CoordinationCluster],
) -> ScanResult:
    """Re-score ``scan`` with the account's coordination evidence folded in.

    Pure and non-mutating: returns the original ``scan`` unchanged when the
    account is in no cluster, otherwise returns a fresh re-aggregated result
    that adds the ``coordination`` signal to the existing detector signals.
    """
    signal = build_coordination_signal(clusters)
    if signal is None:
        return scan
    return aggregate(list(scan.signals) + [signal])
