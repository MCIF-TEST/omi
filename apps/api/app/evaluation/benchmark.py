"""Run the detection engine over a labeled benchmark and score it.

This is the keystone of the "intelligence-grade, continuously improving"
mandate: it turns "is the engine any good?" from a vibe into a number
(Brier, tier accuracy, macro-F1, per-tier P/R/F1, confusion matrix,
per-detector influence) that the test suite gates on and an admin
endpoint surfaces.

The seed benchmark (``benchmarks/seed_v1.json``) is a curated set of
labeled archetypes spanning every tier and every detector. As real
ground-truth labels accumulate (YouTube suspensions, analyst labels via
the LabelWidget), they can be exported into additional benchmark files
with the same schema — at which point the same harness measures the
engine against reality, and the gate ratchets up.

Benchmark file schema (JSON array):

    [
      {
        "label": "ai_content_high",     # human-readable category
        "expected_tier": "high",         # low | moderate | elevated | high
        "expected_probability": 0.85,    # optional; defaults to tier midpoint
        "profile": { ...Profile fields... },
        "posts":   [ { ...Post fields... }, ... ]
      },
      ...
    ]
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from app.detection.engine import analyze_account
from app.evaluation.metrics import EvalRow, compute_report, expected_prob
from app.schemas import Post, Profile

# Versioned seed benchmark shipped with the package.
BENCHMARKS_DIR = Path(__file__).parent / "benchmarks"
DEFAULT_BENCHMARK = BENCHMARKS_DIR / "seed_v1.json"

# Bump when the benchmark's composition changes in a way that makes two
# reports incomparable (cases added/removed/relabeled).
BENCHMARK_VERSION = "seed_v1"


@dataclass
class BenchmarkCase:
    label: str
    expected_tier: str
    expected_probability: float | None
    profile: dict[str, Any]
    posts: list[dict[str, Any]] = field(default_factory=list)


def _coerce_dt(d: dict[str, Any]) -> dict[str, Any]:
    """Tolerate ISO-8601 strings (incl. trailing Z) for created_at."""
    if isinstance(d.get("created_at"), str):
        return {**d, "created_at": datetime.fromisoformat(d["created_at"].replace("Z", "+00:00"))}
    return d


def load_benchmark(path: Path | str | None = None) -> list[BenchmarkCase]:
    path = Path(path) if path else DEFAULT_BENCHMARK
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError(f"Benchmark {path} must be a JSON array.")
    cases: list[BenchmarkCase] = []
    for raw in data:
        cases.append(BenchmarkCase(
            label=raw.get("label", "?"),
            expected_tier=raw.get("expected_tier", "low"),
            expected_probability=raw.get("expected_probability"),
            profile=raw.get("profile", {}),
            posts=raw.get("posts", []),
        ))
    return cases


def run_case(case: BenchmarkCase) -> EvalRow:
    """Run the live detection engine over one case and capture the result."""
    profile = Profile(**_coerce_dt(case.profile))
    posts = [Post(**_coerce_dt(p)) for p in case.posts]
    scan = analyze_account(profile, posts)
    return EvalRow(
        label=case.label,
        expected_tier=case.expected_tier,
        expected_p=expected_prob(case.expected_tier, case.expected_probability),
        predicted_tier=scan.tier.value,
        predicted_p=scan.overall_probability,
        confidence=scan.confidence,
        signals=[
            {"name": s.name, "probability": s.probability, "confidence": s.confidence}
            for s in scan.signals
        ],
        weak_signals=list(scan.weak_signals or []),
    )


def evaluate(cases: list[BenchmarkCase]) -> dict[str, Any]:
    """Run the engine over every case and return the full scoreboard report."""
    rows = [run_case(c) for c in cases]
    report = compute_report(rows)
    report["benchmark_version"] = BENCHMARK_VERSION
    return report


def evaluate_default() -> dict[str, Any]:
    """Convenience: evaluate the shipped seed benchmark."""
    return evaluate(load_benchmark())
