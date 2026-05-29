"""Memory-learning evaluation harness — the "becomes smarter over time" pillar.

The vision's central promise is that the engine *becomes smarter as more videos
are analyzed*. Two other benchmarks measure within-scan accuracy; this one
measures the **longitudinal** claim: as the persistent fingerprint store
accumulates previously-scored accounts, does a new sparse-history account that
behaves like known-bad accounts get correctly flagged — when, scored cold (empty
store), it would slip through?

This is the across-scan analog of the coordination *rescue* benchmark:

* rescue   — the **coordination** dimension recovers recall **within one scan**
  (peers on the same video).
* memory   — the **memory** dimension recovers recall **across scans** (the
  reference set grows every time a video is analyzed).

It drives the real production code: ``analyze_account`` (standalone) →
``extract_fingerprint`` → ``compute_memory_signal`` against a reference store of
a given size → ``aggregate``. ``compute_memory_signal`` is pure (the caller
supplies the candidate accounts), so the whole harness is DB-free and
deterministic — the reference store is synthesised in-memory at each size.

The headline is a **learning curve**: adjusted probability as a function of how
many similar prior accounts the store has seen. A bad account in a bad
neighborhood should climb into a flagged tier as the store fills; a clean
account in a clean neighborhood must stay low; an account whose fingerprint
matches nothing in the store must be left untouched at every size (the memory
signal is conservative — zero confidence when there is no match).

Scenario JSON schema (array of objects):

    {
      "label": "bad_neighborhood_rescue",
      "neighborhood": "bad",            // bad | good | distant
      "role": "bot",                     // bot | organic (ground truth)
      "neighbor_score": 0.85,            // last_score stamped on reference accounts
      "neighbor_confidence": 0.7,        // last_confidence on reference accounts
      "expected_standalone_tier": "low",
      "profile": { ...Profile fields... },
      "posts":   [ { ...Post fields... }, ... ]
    }
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from app.detection.engine import analyze_account
from app.detection.scoring import aggregate
from app.memory.fingerprint import extract_fingerprint
from app.memory.prior import compute_memory_signal
from app.schemas import Post, Profile, ScanResult, Tier
from app.storage.models import Account

BENCHMARKS_DIR = Path(__file__).parent / "benchmarks"
DEFAULT_MEMORY_BENCHMARK = BENCHMARKS_DIR / "memory_v1.json"
MEMORY_BENCHMARK_VERSION = "memory_v1"

# Reference-store sizes to probe along the learning curve.
STORE_SIZES: tuple[int, ...] = (0, 1, 2, 3, 5, 8)

# Tiers at or above this count as "flagged" for recall purposes.
FLAGGED_TIERS = (Tier.ELEVATED, Tier.HIGH)


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class MemoryScenario:
    label: str
    neighborhood: str  # bad | good | distant
    role: str          # bot | organic
    neighbor_score: float
    neighbor_confidence: float
    profile: dict[str, Any]
    posts: list[dict[str, Any]]
    expected_standalone_tier: str | None = None


@dataclass
class CurvePoint:
    store_size: int
    memory_probability: float
    memory_confidence: float
    adjusted_probability: float
    adjusted_tier: str


@dataclass
class MemoryScenarioResult:
    label: str
    neighborhood: str
    role: str
    standalone_probability: float
    standalone_tier: str
    curve: list[CurvePoint] = field(default_factory=list)

    @property
    def cold(self) -> CurvePoint:
        return self.curve[0]

    @property
    def warm(self) -> CurvePoint:
        return self.curve[-1]

    @property
    def standalone_flagged(self) -> bool:
        return Tier(self.standalone_tier) in FLAGGED_TIERS

    @property
    def warm_flagged(self) -> bool:
        return Tier(self.warm.adjusted_tier) in FLAGGED_TIERS

    @property
    def is_monotonic(self) -> bool:
        """Adjusted probability never decreases as the store grows."""
        ps = [p.adjusted_probability for p in self.curve]
        return all(b >= a - 1e-9 for a, b in zip(ps, ps[1:]))


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------

def load_memory_benchmark(path: Path | str | None = None) -> list[MemoryScenario]:
    path = Path(path) if path else DEFAULT_MEMORY_BENCHMARK
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError(f"Memory benchmark {path} must be a JSON array.")
    scenarios: list[MemoryScenario] = []
    for raw in data:
        scenarios.append(MemoryScenario(
            label=raw.get("label", "?"),
            neighborhood=raw.get("neighborhood", "bad"),
            role=raw.get("role", "bot"),
            neighbor_score=float(raw.get("neighbor_score", 0.85)),
            neighbor_confidence=float(raw.get("neighbor_confidence", 0.7)),
            profile=raw.get("profile", {}),
            posts=raw.get("posts", []),
            expected_standalone_tier=raw.get("expected_standalone_tier"),
        ))
    return scenarios


# ---------------------------------------------------------------------------
# Reference-store synthesis
# ---------------------------------------------------------------------------

def _close_fingerprint(base: list[float], j: int) -> list[float]:
    """Deterministic small perturbation — stays well inside the 0.35 match
    radius (distance ~0.08 over 21 dims) while differing per neighbor."""
    return [min(1.0, max(0.0, base[d] + ((d + 2 * j) % 5 - 2) * 0.012))
            for d in range(len(base))]


def _distant_fingerprint(base: list[float]) -> list[float]:
    """A fingerprint half a unit away in every dimension — distance ~2.3,
    far outside the match radius, so the memory signal must ignore it."""
    return [(base[d] + 0.5) % 1.0 for d in range(len(base))]


def _build_store(
    scenario: MemoryScenario, base_fingerprint: list[float], size: int
) -> list[Account]:
    accounts: list[Account] = []
    for j in range(size):
        if scenario.neighborhood == "distant":
            fp = _distant_fingerprint(base_fingerprint)
        else:
            fp = _close_fingerprint(base_fingerprint, j)
        accounts.append(Account(
            external_id=f"{scenario.label}_ref{j}",
            platform="youtube",
            fingerprint_json=fp,
            last_score=scenario.neighbor_score,
            last_confidence=scenario.neighbor_confidence,
        ))
    return accounts


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def _coerce(d: dict[str, Any]) -> dict[str, Any]:
    if isinstance(d.get("created_at"), str):
        return {**d, "created_at": datetime.fromisoformat(d["created_at"].replace("Z", "+00:00"))}
    return d


def run_memory_scenario(scenario: MemoryScenario) -> MemoryScenarioResult:
    profile = Profile(**_coerce(scenario.profile))
    posts = [Post(**_coerce(p)) for p in scenario.posts]
    standalone: ScanResult = analyze_account(profile, posts)
    fingerprint = extract_fingerprint(standalone)

    curve: list[CurvePoint] = []
    for size in STORE_SIZES:
        store = _build_store(scenario, fingerprint, size)
        mem = compute_memory_signal(fingerprint, store, exclude_external_id=profile.handle)
        adjusted = aggregate(list(standalone.signals) + [mem])
        curve.append(CurvePoint(
            store_size=size,
            memory_probability=round(mem.probability, 4),
            memory_confidence=round(mem.confidence, 4),
            adjusted_probability=round(adjusted.overall_probability, 4),
            adjusted_tier=adjusted.tier.value,
        ))

    return MemoryScenarioResult(
        label=scenario.label,
        neighborhood=scenario.neighborhood,
        role=scenario.role,
        standalone_probability=round(standalone.overall_probability, 4),
        standalone_tier=standalone.tier.value,
        curve=curve,
    )


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------

def compute_memory_report(results: list[MemoryScenarioResult]) -> dict[str, Any]:
    n = len(results)
    if n == 0:
        return {"n_scenarios": 0}

    bad = [r for r in results if r.neighborhood == "bad"]
    good = [r for r in results if r.neighborhood == "good"]
    distant = [r for r in results if r.neighborhood == "distant"]

    # Learning: bad accounts under-flagged cold, flagged warm.
    cold_bad_recall = (
        sum(1 for r in bad if Tier(r.cold.adjusted_tier) in FLAGGED_TIERS) / len(bad)
        if bad else 0.0
    )
    warm_bad_recall = (
        sum(1 for r in bad if r.warm_flagged) / len(bad) if bad else 0.0
    )
    bad_monotonic = (
        sum(1 for r in bad if r.is_monotonic) / len(bad) if bad else 1.0
    )
    mean_warm_lift = (
        sum(r.warm.adjusted_probability - r.cold.adjusted_probability for r in bad) / len(bad)
        if bad else 0.0
    )

    # Clean accounts in a clean neighborhood must not be escalated by memory.
    good_false_lift = (
        sum(1 for r in good if Tier(r.warm.adjusted_tier) in FLAGGED_TIERS) / len(good)
        if good else 0.0
    )

    # Accounts that match nothing must be untouched at every store size.
    distant_inert = (
        sum(
            1 for r in distant
            if all(abs(p.adjusted_probability - r.cold.adjusted_probability) < 1e-6
                   for p in r.curve)
        ) / len(distant)
        if distant else 1.0
    )

    per_scenario = []
    for r in results:
        per_scenario.append({
            "label": r.label,
            "neighborhood": r.neighborhood,
            "role": r.role,
            "standalone_tier": r.standalone_tier,
            "standalone_probability": r.standalone_probability,
            "learning_curve": [
                {
                    "store_size": p.store_size,
                    "memory_confidence": p.memory_confidence,
                    "adjusted_probability": p.adjusted_probability,
                    "adjusted_tier": p.adjusted_tier,
                }
                for p in r.curve
            ],
            "warm_flagged": r.warm_flagged,
            "monotonic": r.is_monotonic,
        })

    return {
        "benchmark_version": MEMORY_BENCHMARK_VERSION,
        "n_scenarios": n,
        "n_bad": len(bad),
        "n_good": len(good),
        "n_distant": len(distant),
        "store_sizes": list(STORE_SIZES),
        "cold_bad_recall": round(cold_bad_recall, 3),
        "warm_bad_recall": round(warm_bad_recall, 3),
        "memory_recall_lift": round(warm_bad_recall - cold_bad_recall, 3),
        "bad_monotonic_rate": round(bad_monotonic, 3),
        "mean_warm_prob_lift": round(mean_warm_lift, 4),
        "good_false_lift": round(good_false_lift, 3),
        "distant_inert_rate": round(distant_inert, 3),
        "per_scenario": per_scenario,
    }


def evaluate_memory(scenarios: list[MemoryScenario]) -> dict[str, Any]:
    results = [run_memory_scenario(s) for s in scenarios]
    return compute_memory_report(results)


def evaluate_memory_default() -> dict[str, Any]:
    return evaluate_memory(load_memory_benchmark())
