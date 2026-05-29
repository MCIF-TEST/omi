"""Coordination-rescue evaluation harness — the end-to-end keystone.

The two existing benchmarks measure the halves in isolation:

* ``seed_v1`` proves the single-account engine **under-flags** sparse-history
  accounts (per-tier recall near zero on elevated/moderate) — by design, it
  prefers a miss to a false accusation when an account has only a few comments.
* ``coordination_v1`` proves the cross-account detectors **accurately recover**
  planted coordination clusters (cluster recall 0.857, member precision 1.0).

Neither measures the *bridge*: when a sparse-history bot the single-account
engine would score LOW sits inside a detected coordination cluster, does the
coordination signal lift it into the correct tier? That bridge — orchestrator
Phase 4, now extracted to :mod:`app.detection.coordination.elevate` — is the
entire product value proposition: "we catch coordinated campaigns even though
lone accounts score conservatively."

This harness measures the **recall rescue** end-to-end, driving the real
production code:

  standalone   = analyze_account(profile, posts)          # the conservative score
  clusters     = <coordination detectors over the batch>  # real detectors
  adjusted     = apply_coordination(standalone, clusters)  # the production lift

Metrics:

  * **standalone_bot_recall** — fraction of bot accounts the single-account
    engine alone scores ELEVATED/HIGH. Expected LOW (that's the problem).
  * **adjusted_bot_recall**   — same fraction after coordination lift. The
    rescue moves this up; the gap is the headline.
  * **rescue_rate**           — of bots that were (a) under-flagged standalone
    and (b) caught in a cluster, the fraction lifted to ELEVATED/HIGH.
  * **mean_prob_lift**        — mean (adjusted_p − standalone_p) over in-cluster
    bots. Must be > 0.
  * **organic_false_lift**    — fraction of organic accounts pushed into
    ELEVATED/HIGH by coordination. Must stay ~0 (organics shouldn't be in
    clusters; if they are, they shouldn't be wrongly escalated).

Scenario JSON schema (array of objects) — a superset of the coordination
schema, adding ``profile`` and ``posts`` per account for the standalone scan:

    {
      "label": "temporal_burst_rescue",
      "scenario_type": "temporal_semantic",   // which detector(s) to run
      "accounts": [
        {
          "external_id": "uc_bot1",
          "handle": "@bot1",
          "role": "bot",                        // bot | organic (ground truth)
          "expected_standalone_tier": "low",    // optional sanity annotation
          "profile": { ...Profile fields... },
          "posts":   [ { ...Post fields... }, ... ],
          // coordination inputs (same as coordination_v1):
          "created_at": "...", "engaged_video_ids": [...], "texts": [...],
          "fingerprint": [...], "individual_probability": 0.7,
          "video_comment": { "comment_id": "...", "text": "...", "created_at": "..." }
        }
      ]
    }
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from app.detection.coordination._types import CoordinationCluster
from app.detection.coordination.elevate import apply_coordination, coordination_membership
from app.detection.engine import analyze_account
from app.evaluation.coordination_benchmark import (
    AccountEntry,
    CoordinationScenario,
    _parse_dt,
    _run_detectors,
)
from app.schemas import Post, Profile, ScanResult, Tier

BENCHMARKS_DIR = Path(__file__).parent / "benchmarks"
DEFAULT_RESCUE_BENCHMARK = BENCHMARKS_DIR / "coordination_rescue_v1.json"
RESCUE_BENCHMARK_VERSION = "coordination_rescue_v1"

# Tiers at or above this count as "flagged" for recall purposes.
FLAGGED_TIERS = (Tier.ELEVATED, Tier.HIGH)


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class RescueAccount:
    external_id: str
    handle: str
    role: str  # bot | organic
    profile: dict[str, Any]
    posts: list[dict[str, Any]]
    expected_standalone_tier: str | None = None
    # coordination inputs (forwarded to the detector dispatch)
    coordination: AccountEntry | None = None


@dataclass
class RescueScenario:
    label: str
    scenario_type: str
    accounts: list[RescueAccount]


@dataclass
class RescueAccountResult:
    external_id: str
    role: str
    in_cluster: bool
    standalone_tier: str
    standalone_p: float
    adjusted_tier: str
    adjusted_p: float

    @property
    def standalone_flagged(self) -> bool:
        return Tier(self.standalone_tier) in FLAGGED_TIERS

    @property
    def adjusted_flagged(self) -> bool:
        return Tier(self.adjusted_tier) in FLAGGED_TIERS

    @property
    def rescued(self) -> bool:
        """Bot that was under-flagged standalone, in a cluster, now flagged."""
        return (
            self.role == "bot"
            and self.in_cluster
            and not self.standalone_flagged
            and self.adjusted_flagged
        )


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------

def _coordination_entry(a: dict[str, Any]) -> AccountEntry:
    vc = a.get("video_comment") or {}
    return AccountEntry(
        external_id=a["external_id"],
        handle=a.get("handle", a["external_id"]),
        role=a.get("role", "organic"),
        created_at=_parse_dt(a.get("created_at")),
        engaged_video_ids=list(a.get("engaged_video_ids", [])),
        texts=list(a.get("texts", [])),
        fingerprint=a.get("fingerprint"),
        individual_probability=float(a.get("individual_probability", 0.5)),
        video_comment_id=vc.get("comment_id"),
        video_comment_text=vc.get("text"),
        video_comment_created_at=_parse_dt(vc.get("created_at")),
    )


def load_rescue_benchmark(path: Path | str | None = None) -> list[RescueScenario]:
    path = Path(path) if path else DEFAULT_RESCUE_BENCHMARK
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError(f"Rescue benchmark {path} must be a JSON array.")

    scenarios: list[RescueScenario] = []
    for raw in data:
        accounts: list[RescueAccount] = []
        for a in raw.get("accounts", []):
            accounts.append(RescueAccount(
                external_id=a["external_id"],
                handle=a.get("handle", a["external_id"]),
                role=a.get("role", "organic"),
                profile=a.get("profile", {}),
                posts=a.get("posts", []),
                expected_standalone_tier=a.get("expected_standalone_tier"),
                coordination=_coordination_entry(a),
            ))
        scenarios.append(RescueScenario(
            label=raw.get("label", "?"),
            scenario_type=raw.get("scenario_type", "multi"),
            accounts=accounts,
        ))
    return scenarios


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def _coerce(d: dict[str, Any]) -> dict[str, Any]:
    if isinstance(d.get("created_at"), str):
        return {**d, "created_at": datetime.fromisoformat(d["created_at"].replace("Z", "+00:00"))}
    return d


def _standalone_scan(account: RescueAccount) -> ScanResult:
    profile = Profile(**_coerce(account.profile))
    posts = [Post(**_coerce(p)) for p in account.posts]
    return analyze_account(profile, posts)


def run_rescue_scenario(scenario: RescueScenario) -> list[RescueAccountResult]:
    # 1) standalone single-account scores
    standalone: dict[str, ScanResult] = {
        a.external_id: _standalone_scan(a) for a in scenario.accounts
    }

    # 2) real coordination detectors over the batch
    coord_scenario = CoordinationScenario(
        label=scenario.label,
        scenario_type=scenario.scenario_type,
        expected_coordination="",  # unused by the detector dispatch
        accounts=[a.coordination for a in scenario.accounts if a.coordination],
        planted_clusters=[],
    )
    findings = _run_detectors(coord_scenario)
    clusters: list[CoordinationCluster] = [c for f in findings for c in f.clusters]
    by_member = coordination_membership(clusters)

    # 3) apply the production elevation and record the before/after
    results: list[RescueAccountResult] = []
    for a in scenario.accounts:
        base = standalone[a.external_id]
        cl_for = by_member.get(a.external_id, [])
        adjusted = apply_coordination(base, cl_for)
        results.append(RescueAccountResult(
            external_id=a.external_id,
            role=a.role,
            in_cluster=bool(cl_for),
            standalone_tier=base.tier.value,
            standalone_p=round(base.overall_probability, 4),
            adjusted_tier=adjusted.tier.value,
            adjusted_p=round(adjusted.overall_probability, 4),
        ))
    return results


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------

def compute_rescue_report(
    per_scenario: dict[str, list[RescueAccountResult]],
) -> dict[str, Any]:
    all_results = [r for rs in per_scenario.values() for r in rs]
    bots = [r for r in all_results if r.role == "bot"]
    organics = [r for r in all_results if r.role == "organic"]

    if not bots:
        return {"n_accounts": len(all_results), "n_bots": 0}

    standalone_bot_recall = sum(1 for r in bots if r.standalone_flagged) / len(bots)
    adjusted_bot_recall = sum(1 for r in bots if r.adjusted_flagged) / len(bots)

    # Rescue rate: of bots under-flagged standalone AND in a cluster, how many
    # the coordination lift moves into a flagged tier.
    rescuable = [r for r in bots if r.in_cluster and not r.standalone_flagged]
    rescued = [r for r in rescuable if r.adjusted_flagged]
    rescue_rate = (len(rescued) / len(rescuable)) if rescuable else 0.0

    in_cluster_bots = [r for r in bots if r.in_cluster]
    mean_prob_lift = (
        sum(r.adjusted_p - r.standalone_p for r in in_cluster_bots) / len(in_cluster_bots)
        if in_cluster_bots else 0.0
    )

    # Organic false lift: organics that cross into a flagged tier post-coordination
    # despite being clean standalone.
    organic_false_lift = (
        sum(1 for r in organics if not r.standalone_flagged and r.adjusted_flagged) / len(organics)
        if organics else 0.0
    )

    scenario_detail = {}
    for label, rs in per_scenario.items():
        s_bots = [r for r in rs if r.role == "bot"]
        scenario_detail[label] = {
            "n_bots": len(s_bots),
            "n_organic": sum(1 for r in rs if r.role == "organic"),
            "bots_in_cluster": sum(1 for r in s_bots if r.in_cluster),
            "standalone_flagged_bots": sum(1 for r in s_bots if r.standalone_flagged),
            "adjusted_flagged_bots": sum(1 for r in s_bots if r.adjusted_flagged),
            "rescued_bots": sum(1 for r in s_bots if r.rescued),
        }

    return {
        "benchmark_version": RESCUE_BENCHMARK_VERSION,
        "n_accounts": len(all_results),
        "n_bots": len(bots),
        "n_organic": len(organics),
        "standalone_bot_recall": round(standalone_bot_recall, 3),
        "adjusted_bot_recall": round(adjusted_bot_recall, 3),
        "recall_lift": round(adjusted_bot_recall - standalone_bot_recall, 3),
        "rescue_rate": round(rescue_rate, 3),
        "n_rescuable": len(rescuable),
        "n_rescued": len(rescued),
        "mean_prob_lift": round(mean_prob_lift, 4),
        "organic_false_lift": round(organic_false_lift, 3),
        "per_scenario": scenario_detail,
    }


def evaluate_rescue(scenarios: list[RescueScenario]) -> dict[str, Any]:
    per_scenario = {s.label: run_rescue_scenario(s) for s in scenarios}
    return compute_rescue_report(per_scenario)


def evaluate_rescue_default() -> dict[str, Any]:
    return evaluate_rescue(load_rescue_benchmark())
