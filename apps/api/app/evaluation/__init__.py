"""Detection-engine evaluation harness.

Makes accuracy a measured, gated, surfaced number rather than an assumption.
See :mod:`app.evaluation.benchmark` for the single-account runner,
:mod:`app.evaluation.coordination_benchmark` for the multi-account runner,
and :mod:`app.evaluation.metrics` for the pure scoring functions.
"""

from app.evaluation.benchmark import (
    BENCHMARK_VERSION,
    DEFAULT_BENCHMARK,
    BenchmarkCase,
    evaluate,
    evaluate_default,
    load_benchmark,
    run_case,
)
from app.evaluation.coordination_benchmark import (
    COORDINATION_BENCHMARK_VERSION,
    DEFAULT_COORDINATION_BENCHMARK,
    CoordinationScenario,
    CoordinationEvalRow,
    compute_coordination_report,
    evaluate_coordination,
    evaluate_coordination_default,
    load_coordination_benchmark,
    run_coordination_scenario,
)
from app.evaluation.rescue_benchmark import (
    RESCUE_BENCHMARK_VERSION,
    DEFAULT_RESCUE_BENCHMARK,
    RescueScenario,
    RescueAccountResult,
    compute_rescue_report,
    evaluate_rescue,
    evaluate_rescue_default,
    load_rescue_benchmark,
    run_rescue_scenario,
)
from app.evaluation.metrics import (
    TIER_MIDPOINT,
    EvalRow,
    compute_report,
    expected_prob,
    majority_class_rate,
    per_tier_metrics,
)

__all__ = [
    "BENCHMARK_VERSION",
    "DEFAULT_BENCHMARK",
    "BenchmarkCase",
    "evaluate",
    "evaluate_default",
    "load_benchmark",
    "run_case",
    "COORDINATION_BENCHMARK_VERSION",
    "DEFAULT_COORDINATION_BENCHMARK",
    "CoordinationScenario",
    "CoordinationEvalRow",
    "compute_coordination_report",
    "evaluate_coordination",
    "evaluate_coordination_default",
    "load_coordination_benchmark",
    "run_coordination_scenario",
    "RESCUE_BENCHMARK_VERSION",
    "DEFAULT_RESCUE_BENCHMARK",
    "RescueScenario",
    "RescueAccountResult",
    "compute_rescue_report",
    "evaluate_rescue",
    "evaluate_rescue_default",
    "load_rescue_benchmark",
    "run_rescue_scenario",
    "TIER_MIDPOINT",
    "EvalRow",
    "compute_report",
    "expected_prob",
    "majority_class_rate",
    "per_tier_metrics",
]
