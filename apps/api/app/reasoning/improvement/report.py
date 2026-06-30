"""Structured engineering reports (Sprint 011).

A deterministic roll-up over a set of evaluation snapshots (one per configuration) + the
promotion ledger: the best-performing prompt / context mode / evidence mode (by label agreement,
tie-broken by control FPR then latency), agreement + control-FPR + latency by config, Governor
statistics, replay stability, and the recommendation/promotion summary. Pure function of its
inputs — the same snapshots always produce the same report.
"""
from __future__ import annotations

from typing import Any


def _num(v: Any, default: float = -1.0) -> float:
    return float(v) if isinstance(v, (int, float)) else default


def _best(snapshots: list[dict], lever: str) -> dict | None:
    """The snapshot that varies ``lever`` and scores best: highest agreement, then lowest control
    FPR, then lowest latency, then label (deterministic tie-break)."""
    scoped = [s for s in snapshots if lever in (s.get("config") or {})]
    if not scoped:
        return None
    best = min(scoped, key=lambda s: (
        -_num(s.get("agreement_rate")), _num(s.get("control_fpr"), 1.0),
        _num(s.get("avg_latency_ms"), 1e12), str(s.get("label")),
    ))
    return {"config": best.get("config"), "label": best.get("label"),
            "agreement_rate": best.get("agreement_rate"), "control_fpr": best.get("control_fpr")}


def engineering_report(
    snapshots: list[dict], *, recommendations: list[dict] | None = None, ledger: Any = None,
) -> dict:
    """Build the structured engineering report. ``snapshots`` are flat metric dicts (see
    ``build_snapshot``); ``recommendations`` are ``Recommendation.to_dict()``; ``ledger`` is an
    optional ``PromotionLedger``."""
    snapshots = sorted(snapshots, key=lambda s: str(s.get("label")))
    recommendations = recommendations or []

    by_config = [
        {"label": s.get("label"), "agreement_rate": s.get("agreement_rate"),
         "control_fpr": s.get("control_fpr"), "avg_latency_ms": s.get("avg_latency_ms"),
         "number_preserved_rate": s.get("number_preserved_rate")}
        for s in snapshots
    ]

    return {
        "n_configs": len(snapshots),
        "best_prompt": _best(snapshots, "prompt_version"),
        "best_context_mode": _best(snapshots, "context_mode"),
        "best_evidence_mode": _best(snapshots, "enrich"),
        "agreement_trend": [s.get("agreement_rate") for s in snapshots],
        "control_fpr": {s.get("label"): s.get("control_fpr") for s in snapshots},
        "latency": {s.get("label"): s.get("avg_latency_ms") for s in snapshots},
        "replay_stability": {
            "number_preserved": all(_num(s.get("number_preserved_rate"), 1.0) >= 1.0 for s in snapshots),
        },
        "governor": {
            "permit_rate": {s.get("label"): s.get("governor_permit_rate") for s in snapshots},
            "floor_fallback_rate": {s.get("label"): s.get("governor_floor_rate") for s in snapshots},
        },
        "benchmark_summary": by_config,
        "recommendations": {
            "total": len(recommendations),
            "by_action": _count(recommendations, "action"),
            "by_severity": _count(recommendations, "severity"),
        },
        "promotions": ledger.summary() if ledger is not None else None,
    }


def _count(items: list[dict], key: str) -> dict:
    out: dict[str, int] = {}
    for it in items:
        out[it.get(key, "?")] = out.get(it.get(key, "?"), 0) + 1
    return dict(sorted(out.items()))
