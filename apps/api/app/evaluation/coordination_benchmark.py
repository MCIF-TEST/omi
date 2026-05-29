"""Multi-account coordination evaluation harness.

Exercises the coordination detectors (age_cohort, co_engagement, style_match,
temporal_semantic, fingerprint_cluster) over synthetic video scenarios — something
the single-account seed benchmark cannot do at all, because those detectors
require a peer batch to have any signal.

Each scenario represents one "video scan":

  * a set of commenter accounts with ground-truth labels (bot vs organic),
  * the coordination signal each account contributes (video comment, engagement
    history, creation date, etc.),
  * a list of "planted clusters" that the detector should recover.

Metrics:

  * **cluster_recall**  — fraction of planted clusters matched by a detected
    cluster (Jaccard ≥ 0.50 threshold).
  * **member_precision** — of accounts flagged in any detected cluster, what
    fraction were actually labeled bot.
  * **member_recall**    — of bot accounts, what fraction were caught in any
    detected cluster.
  * **clean_pass_rate**  — fraction of "no-coordination" scenarios where no
    clusters were detected (false-positive guard).

Scenario JSON schema (array of objects):

    {
      "label": "temporal_burst_amplification",
      "scenario_type": "temporal_semantic",   // age_cohort | co_engagement |
                                              // style_match | temporal_semantic |
                                              // fingerprint_cluster | multi
      "expected_coordination": "high",        // none | low | moderate | high
      "accounts": [
        {
          "external_id": "uc_bot1",
          "handle": "@bot1",
          "role": "bot",                       // bot | organic (ground truth)
          // age_cohort:
          "created_at": "2024-01-10T00:00:00Z",   // null → unknown
          // co_engagement:
          "engaged_video_ids": ["vid1", "vid2"],
          // style_match:
          "texts": ["comment text 1", ...],
          // fingerprint_cluster:
          "fingerprint": [0.1, 0.2, ...],      // 21-dim
          "individual_probability": 0.75,
          // temporal_semantic:
          "video_comment": {
            "comment_id": "cmt_x",
            "text": "...",
            "created_at": "2024-01-15T14:30:01Z"
          }
        }
      ],
      "planted_clusters": [
        {
          "method": "temporal_semantic",
          "members": ["uc_bot1", "uc_bot2", "uc_bot3"]
        }
      ]
    }
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.detection.coordination.co_engagement import EngagementEntry, detect_co_engagement
from app.detection.coordination.cohort import CohortEntry, detect_age_cohorts
from app.detection.coordination.fingerprint_cluster import FingerprintEntry, detect_fingerprint_clusters
from app.detection.coordination.style_match import StyleEntry, detect_style_matches
from app.detection.coordination.temporal_semantic import CommentEntry, detect_temporal_semantic_cliques
from app.detection.coordination._types import CoordinationCluster, CoordinationFinding

BENCHMARKS_DIR = Path(__file__).parent / "benchmarks"
DEFAULT_COORDINATION_BENCHMARK = BENCHMARKS_DIR / "coordination_v1.json"
COORDINATION_BENCHMARK_VERSION = "coordination_v1"

# Jaccard threshold for declaring a detected cluster "matches" a planted one.
CLUSTER_MATCH_JACCARD = 0.50


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class PlantedCluster:
    method: str
    members: list[str]


@dataclass
class AccountEntry:
    external_id: str
    handle: str
    role: str  # "bot" | "organic"
    created_at: datetime | None = None
    engaged_video_ids: list[str] = field(default_factory=list)
    texts: list[str] = field(default_factory=list)
    fingerprint: list[float] | None = None
    individual_probability: float = 0.5
    video_comment_id: str | None = None
    video_comment_text: str | None = None
    video_comment_created_at: datetime | None = None


@dataclass
class CoordinationScenario:
    label: str
    scenario_type: str
    expected_coordination: str  # none | low | moderate | high
    accounts: list[AccountEntry]
    planted_clusters: list[PlantedCluster]


@dataclass
class CoordinationEvalRow:
    label: str
    scenario_type: str
    expected_coordination: str
    n_accounts: int
    n_bots: int
    n_organic: int
    planted_clusters: list[PlantedCluster]
    detected_clusters: list[CoordinationCluster]
    # Derived metrics (computed by score_findings)
    cluster_recall: float = 0.0      # fraction of planted clusters matched
    member_precision: float = 0.0    # precision of flagged member set
    member_recall: float = 0.0       # recall of bot member set
    matched_planted: int = 0         # absolute count for aggregation


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------

def _parse_dt(v: Any) -> datetime | None:
    if v is None:
        return None
    if isinstance(v, datetime):
        return v
    s = str(v).replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def load_coordination_benchmark(
    path: Path | str | None = None,
) -> list[CoordinationScenario]:
    path = Path(path) if path else DEFAULT_COORDINATION_BENCHMARK
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError(f"Coordination benchmark {path} must be a JSON array.")

    scenarios: list[CoordinationScenario] = []
    for raw in data:
        accounts: list[AccountEntry] = []
        for a in raw.get("accounts", []):
            vc = a.get("video_comment") or {}
            accounts.append(AccountEntry(
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
            ))
        planted = [
            PlantedCluster(method=pc["method"], members=list(pc["members"]))
            for pc in raw.get("planted_clusters", [])
        ]
        scenarios.append(CoordinationScenario(
            label=raw.get("label", "?"),
            scenario_type=raw.get("scenario_type", "multi"),
            expected_coordination=raw.get("expected_coordination", "none"),
            accounts=accounts,
            planted_clusters=planted,
        ))
    return scenarios


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def _run_detectors(
    scenario: CoordinationScenario,
) -> list[CoordinationFinding]:
    st = scenario.scenario_type
    findings: list[CoordinationFinding] = []
    accts = scenario.accounts

    if st in ("age_cohort", "multi"):
        entries = [
            CohortEntry(
                external_id=a.external_id,
                handle=a.handle,
                created_at=a.created_at,
            )
            for a in accts
        ]
        if entries:
            findings.append(detect_age_cohorts(entries))

    if st in ("co_engagement", "multi"):
        entries_ce = [
            EngagementEntry(
                external_id=a.external_id,
                handle=a.handle,
                engaged_video_ids=set(a.engaged_video_ids),
            )
            for a in accts
            if a.engaged_video_ids
        ]
        if entries_ce:
            findings.append(detect_co_engagement(entries_ce))

    if st in ("style_match", "multi"):
        entries_sm = [
            StyleEntry(
                external_id=a.external_id,
                handle=a.handle,
                texts=a.texts,
            )
            for a in accts
            if a.texts
        ]
        if entries_sm:
            findings.append(detect_style_matches(entries_sm))

    if st in ("temporal_semantic", "multi"):
        comments = [
            CommentEntry(
                comment_id=a.video_comment_id or f"cmt_{a.external_id}",
                author_external_id=a.external_id,
                text=a.video_comment_text or "",
                created_at=a.video_comment_created_at or datetime.now(timezone.utc),
            )
            for a in accts
            if a.video_comment_text
        ]
        if comments:
            findings.append(detect_temporal_semantic_cliques(comments))

    if st in ("fingerprint_cluster", "multi"):
        entries_fp = [
            FingerprintEntry(
                external_id=a.external_id,
                handle=a.handle,
                fingerprint=a.fingerprint,
                individual_probability=a.individual_probability,
            )
            for a in accts
            if a.fingerprint is not None
        ]
        if entries_fp:
            findings.append(detect_fingerprint_clusters(entries_fp))

    return findings


def _jaccard(a: set[str], b: set[str]) -> float:
    union = a | b
    return len(a & b) / len(union) if union else 0.0


def _score_findings(
    scenario: CoordinationScenario,
    findings: list[CoordinationFinding],
) -> CoordinationEvalRow:
    all_detected: list[CoordinationCluster] = [
        c for f in findings for c in f.clusters
    ]
    detected_sets = [set(c.members) for c in all_detected]

    bot_ids = {a.external_id for a in scenario.accounts if a.role == "bot"}
    flagged_ids: set[str] = {m for c in all_detected for m in c.members}

    # Cluster recall: fraction of planted clusters with a matching detected cluster.
    matched = 0
    for pc in scenario.planted_clusters:
        pc_set = set(pc.members)
        if any(_jaccard(pc_set, ds) >= CLUSTER_MATCH_JACCARD for ds in detected_sets):
            matched += 1
    cluster_recall = matched / max(1, len(scenario.planted_clusters)) if scenario.planted_clusters else (
        1.0 if not all_detected else 0.0  # no planted = expect no detections
    )

    # Member precision/recall.
    if flagged_ids:
        member_prec = len(flagged_ids & bot_ids) / len(flagged_ids)
    else:
        member_prec = 1.0  # nothing flagged; no false positives

    if bot_ids:
        member_rec = len(flagged_ids & bot_ids) / len(bot_ids)
    else:
        member_rec = 1.0 if not flagged_ids else 0.0

    return CoordinationEvalRow(
        label=scenario.label,
        scenario_type=scenario.scenario_type,
        expected_coordination=scenario.expected_coordination,
        n_accounts=len(scenario.accounts),
        n_bots=len(bot_ids),
        n_organic=len(scenario.accounts) - len(bot_ids),
        planted_clusters=scenario.planted_clusters,
        detected_clusters=all_detected,
        cluster_recall=round(cluster_recall, 3),
        member_precision=round(member_prec, 3),
        member_recall=round(member_rec, 3),
        matched_planted=matched,
    )


def run_coordination_scenario(scenario: CoordinationScenario) -> CoordinationEvalRow:
    findings = _run_detectors(scenario)
    return _score_findings(scenario, findings)


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------

def compute_coordination_report(rows: list[CoordinationEvalRow]) -> dict[str, Any]:
    n = len(rows)
    if n == 0:
        return {"n_scenarios": 0}

    # Global averages (excluding clean scenarios from cluster recall since
    # there are no planted clusters to recall).
    planted_rows = [r for r in rows if r.planted_clusters]
    clean_rows = [r for r in rows if not r.planted_clusters or r.expected_coordination == "none"]

    cluster_recall = (
        sum(r.cluster_recall for r in planted_rows) / len(planted_rows)
        if planted_rows else 1.0
    )
    member_precision = sum(r.member_precision for r in rows) / n
    member_recall = (
        sum(r.member_recall for r in rows if r.n_bots > 0) /
        max(1, sum(1 for r in rows if r.n_bots > 0))
    )

    # Clean pass rate: in scenarios expected to have no coordination, did
    # the detectors stay silent?
    actually_clean = [r for r in rows if r.expected_coordination == "none"]
    clean_pass_rate = (
        sum(1 for r in actually_clean if not r.detected_clusters) / len(actually_clean)
        if actually_clean else 1.0
    )

    # Per-scenario detail.
    per_scenario = []
    for r in rows:
        n_det = len(r.detected_clusters)
        n_planted = len(r.planted_clusters)
        per_scenario.append({
            "label": r.label,
            "scenario_type": r.scenario_type,
            "expected_coordination": r.expected_coordination,
            "n_accounts": r.n_accounts,
            "n_bots": r.n_bots,
            "planted_clusters": n_planted,
            "detected_clusters": n_det,
            "matched_planted": r.matched_planted,
            "cluster_recall": r.cluster_recall,
            "member_precision": r.member_precision,
            "member_recall": r.member_recall,
        })

    return {
        "benchmark_version": COORDINATION_BENCHMARK_VERSION,
        "n_scenarios": n,
        "n_with_planted": len(planted_rows),
        "n_clean": len(actually_clean),
        "cluster_recall": round(cluster_recall, 3),
        "member_precision": round(member_precision, 3),
        "member_recall": round(member_recall, 3),
        "clean_pass_rate": round(clean_pass_rate, 3),
        "per_scenario": per_scenario,
    }


def evaluate_coordination(scenarios: list[CoordinationScenario]) -> dict[str, Any]:
    rows = [run_coordination_scenario(s) for s in scenarios]
    return compute_coordination_report(rows)


def evaluate_coordination_default() -> dict[str, Any]:
    return evaluate_coordination(load_coordination_benchmark())
