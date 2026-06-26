"""Aggregate evaluation statistics (Sprint 007) — the dashboard substrate.

``aggregate_stats`` reduces a set of ``ShadowReport`` dicts to the engineering metrics that
answer the sprint's question — *does the AI-backed council outperform the deterministic
baseline?*: AI success / fallback / citation-failure rates, agreement + number-preserved
rates, Governor statistics, latency, and an agreement trend. A pure function of the reports,
so the same corpus always yields the same stats. ``ShadowLedger`` is a thin in-memory
accumulator over it.
"""
from __future__ import annotations

from typing import Any


def _rate(num: int, den: int) -> float | None:
    return round(num / den, 4) if den else None


def aggregate_stats(reports: list[dict]) -> dict:
    """Reduce shadow reports to engineering metrics. ``ai_eligible`` counts runs where an AI
    provider was actually attempted (mode ``ai`` or ``fallback``); deterministic-only runs
    (no endpoint configured) are excluded from the AI rates but counted in agreement."""
    n = len(reports)
    if n == 0:
        return {"n": 0}

    def diag(r: dict) -> dict:
        return r.get("diagnostics") or {}

    def cmp(r: dict) -> dict:
        return r.get("comparison") or {}

    ai = sum(1 for r in reports if diag(r).get("ai_mode") == "ai")
    fallback = sum(1 for r in reports if diag(r).get("ai_mode") == "fallback")
    deterministic = sum(1 for r in reports if diag(r).get("ai_mode") == "deterministic")
    ai_eligible = ai + fallback

    citation_failures = sum(1 for r in reports if diag(r).get("citation_failure"))
    agreements = sum(1 for r in reports if cmp(r).get("overall_agreement"))
    number_preserved = sum(1 for r in reports if cmp(r).get("number_preserved"))
    shadow_permitted = sum(1 for r in reports if (r.get("shadow") or {}).get("trace", {}).get("permitted"))
    shadow_floor = sum(1 for r in reports if (r.get("shadow") or {}).get("fallback"))

    latencies = [d for r in reports if (d := diag(r).get("latency_ms")) is not None]
    attempts = [a for r in reports if (a := diag(r).get("attempts")) is not None]

    return {
        "n": n,
        "ai_runs": ai,
        "fallback_runs": fallback,
        "deterministic_runs": deterministic,
        "ai_success_rate": _rate(ai, ai_eligible),
        "fallback_rate": _rate(fallback, ai_eligible),
        "citation_failures": citation_failures,
        "citation_failure_rate": _rate(citation_failures, ai_eligible),
        "agreement_rate": _rate(agreements, n),
        "number_preserved_rate": _rate(number_preserved, n),
        "governor": {
            "shadow_permit_rate": _rate(shadow_permitted, n),
            "shadow_floor_fallback_rate": _rate(shadow_floor, n),
        },
        "avg_latency_ms": round(sum(latencies) / len(latencies), 2) if latencies else None,
        "avg_attempts": round(sum(attempts) / len(attempts), 2) if attempts else None,
        "agreement_trend": [bool(cmp(r).get("overall_agreement")) for r in reports][-50:],
    }


class ShadowLedger:
    """An in-memory accumulator of shadow reports for engineering aggregation."""

    def __init__(self) -> None:
        self._reports: list[dict] = []

    def add(self, report: Any) -> None:
        self._reports.append(report.to_dict() if hasattr(report, "to_dict") else dict(report))

    def reports(self) -> list[dict]:
        return list(self._reports)

    def stats(self) -> dict:
        return aggregate_stats(self._reports)

    def __len__(self) -> int:
        return len(self._reports)
