"""Phase 2 — expose real coordinated campaigns to the existing coordination engine.

The objective is *not* new detectors. It is to route the state-IO disclosure
campaigns (and legitimate controls) through the SAME detectors the synthetic
coordination benchmark already runs — ``age_cohort``, ``style_match``,
``fingerprint_cluster``, ``temporal_semantic``, ``co_engagement`` — preserving
the real timestamps Phase 0 unlocked, and measure precision / recall / FPR and
per-detector contribution.

Reuse: an account becomes an
:class:`~app.evaluation.coordination_benchmark.AccountEntry` exactly as the
benchmark scenarios do; ``_run_detectors`` builds the detector inputs and runs
them; :func:`~app.detection.coordination.aggregate.aggregate_coordination`
reduces the findings and hands back the signed per-detector breakdown.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Iterable

from app.detection.coordination.aggregate import aggregate_coordination
from app.detection.coordination.temporal_semantic import (
    CommentEntry, detect_temporal_semantic_cliques,
)
from app.detection.engine import analyze_account
from app.evaluation.coordination_benchmark import (
    AccountEntry, CoordinationScenario, _run_detectors,
)
from app.memory.fingerprint import extract_fingerprint
from app.ml.public_import import PublicRecord, _to_posts, _to_profile, coalesce_records


def account_entry(rec: PublicRecord, role: str) -> AccountEntry:
    """Score one public record through the real engine and shape it as a
    coordination AccountEntry (fingerprint + individual probability + the real
    creation date and first real-timestamped post as its representative event)."""
    posts = _to_posts(rec)
    scan = analyze_account(_to_profile(rec), posts)
    created = None
    if rec.account_age_days is not None:
        created = datetime.now(timezone.utc) - timedelta(days=max(0, rec.account_age_days))
    first_time = next((t for t in rec.post_times if t), None)
    return AccountEntry(
        external_id=rec.external_id,
        handle=rec.handle or rec.external_id,
        role=role,
        created_at=created,
        texts=list(rec.texts),
        fingerprint=extract_fingerprint(scan),
        individual_probability=scan.overall_probability,
        video_comment_id=f"{rec.external_id}:0",
        video_comment_text=(rec.texts[0] if rec.texts else None),
        video_comment_created_at=first_time,
    )


def build_scenario(label: str, records: list[PublicRecord], *, role: str,
                   expected: str, cap: int = 120) -> CoordinationScenario:
    accts = [account_entry(r, role) for r in coalesce_records(records)[:cap]]
    return CoordinationScenario(
        label=label, scenario_type="multi", expected_coordination=expected,
        accounts=accts, planted_clusters=[],
    )


def _temporal_on_event_stream(records: Iterable[PublicRecord], cap_events: int = 4000) -> dict:
    """Supplementary probe: feed a bounded stream of *real tweets* (multiple per
    account, with real timestamps) to the temporal-semantic detector — the shape
    it was built for (same-window near-duplicate posts across accounts), which
    the one-event-per-account scenario underuses."""
    comments: list[CommentEntry] = []
    for rec in records:
        for i, (text, when) in enumerate(zip(rec.texts, rec.post_times)):
            if text and when:
                comments.append(CommentEntry(
                    comment_id=f"{rec.external_id}:{i}",
                    author_external_id=rec.external_id,
                    text=text, created_at=when,
                ))
            if len(comments) >= cap_events:
                break
        if len(comments) >= cap_events:
            break
    if len(comments) < 3:
        return {"events": len(comments), "clusters": 0, "score": 0.0, "authors_flagged": 0}
    finding = detect_temporal_semantic_cliques(comments)
    flagged = {m for c in finding.clusters for m in c.members}
    return {
        "events": len(comments), "clusters": len(finding.clusters),
        "score": round(finding.overall_score, 3), "confidence": round(finding.confidence, 3),
        "authors_flagged": len(flagged),
    }


def evaluate_scenario(scn: CoordinationScenario,
                      event_records: list[PublicRecord] | None = None) -> dict:
    """Run all detectors on the scenario, aggregate, and return precision/recall
    inputs + the signed per-detector contribution breakdown."""
    findings = _run_detectors(scn)
    agg = aggregate_coordination(findings)
    n = len(scn.accounts)
    flagged: set[str] = {m for f in findings for c in f.clusters for m in c.members}
    bots = {a.external_id for a in scn.accounts if a.role == "bot"}
    organic = {a.external_id for a in scn.accounts if a.role == "organic"}
    out = {
        "label": scn.label,
        "role": scn.accounts[0].role if scn.accounts else "?",
        "expected": scn.expected_coordination,
        "n_accounts": n,
        "score": round(agg.score, 3),
        "weighted_mean": round(agg.weighted_mean, 3),
        "corroboration": round(agg.corroboration, 3),
        "flagged_members": len(flagged),
        "flagged_fraction": round(len(flagged) / max(1, n), 3),
        # recall = caught bots / bots; fpr = flagged organic / organic
        "recall": round(len(flagged & bots) / len(bots), 3) if bots else None,
        "fpr": round(len(flagged & organic) / len(organic), 3) if organic else None,
        "clusters_by_method": {f.method: len(f.clusters) for f in findings},
        "contributions": [
            {"method": c.method, "score": round(c.score, 3),
             "confidence": round(c.confidence, 3), "reliability": c.reliability,
             "mean_weight": round(c.mean_weight, 3), "evidence": round(c.evidence, 3)}
            for c in agg.contributions
        ],
    }
    if event_records is not None:
        out["temporal_event_stream"] = _temporal_on_event_stream(event_records)
    return out
