"""Evaluation snapshots (Sprint 011).

Reduce a gold-corpus evaluation under one configuration into a single flat metrics dict the
recommendation engine compares. A snapshot folds together the corpus label scoring (agreement,
control FPR, number-preserved), the shadow aggregate stats (latency, fallback, citation-failure,
Governor), and the average context + evidence quality. Deterministic given a deterministic
provider, so two snapshots of the same config are identical — the basis for reproducible
recommendations.
"""
from __future__ import annotations

from typing import Any

from app.reasoning.evaluation import evaluate_corpus
from app.reasoning.shadow import aggregate_stats


def _avg(values: list[float]) -> float | None:
    nums = [float(v) for v in values if isinstance(v, (int, float))]
    return round(sum(nums) / len(nums), 4) if nums else None


def _label(config: dict) -> str:
    return ",".join(f"{k}={config[k]}" for k in sorted(config))


def build_snapshot(
    corpus: Any, *, config: dict, label: str | None = None, provider: Any = None,
    registry: Any = None, settings: Any | None = None, store: Any = None, now: Any = None,
) -> dict:
    """Evaluate ``corpus`` under ``config`` and fold the results into a flat metrics snapshot.

    ``config`` keys (any subset): ``prompt_version`` / ``context_mode`` / ``enrich`` / ``budget``.
    Deterministic given a deterministic provider."""
    config = dict(config)
    ev = evaluate_corpus(
        corpus, registry=registry, prompt_version=config.get("prompt_version"),
        context_mode=config.get("context_mode"), context_budget=config.get("budget"),
        enrich=bool(config.get("enrich", False)), provider=provider,
        settings=settings, store=store, now=now,
    )
    summary = ev["summary"]
    reports = ev["reports"]
    stats = aggregate_stats(reports)
    gov = stats.get("governor", {}) if isinstance(stats.get("governor"), dict) else {}

    ctx_retention = _avg([
        (r.get("context") or {}).get("metrics", {}).get("citation_retention")
        for r in reports if isinstance((r.get("context") or {}).get("metrics"), dict)
    ])
    ev_completeness = _avg([(r.get("evidence") or {}).get("evidence_completeness") for r in reports])
    facet_coverage = _avg([(r.get("evidence") or {}).get("facet_coverage") for r in reports])

    return {
        "label": label or _label(config),
        "config": config,
        "n": summary.get("n", len(reports)),
        "agreement_rate": summary.get("agreement_rate"),
        "control_fpr": summary.get("shadow_control_fpr"),
        "production_control_fpr": summary.get("production_control_fpr"),
        "number_preserved_rate": summary.get("number_preserved_rate"),
        "avg_latency_ms": stats.get("avg_latency_ms"),
        "fallback_rate": stats.get("fallback_rate"),
        "citation_failure_rate": stats.get("citation_failure_rate"),
        "governor_permit_rate": gov.get("shadow_permit_rate"),
        "governor_floor_rate": gov.get("shadow_floor_fallback_rate"),
        "citation_retention": ctx_retention,
        "evidence_completeness": ev_completeness,
        "facet_coverage": facet_coverage,
    }
