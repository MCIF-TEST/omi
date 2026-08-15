"""Writing a detection run: the payload block, the index row, and the Campaign bridge.

Three destinations, each for a different reader:

* ``payload_json["campaign_detection_v1"]`` holds everything, evidence artifacts included. It is
  the record, and it lives beside the analyst's own cache under the same discipline.
* ``campaign_detections`` is a denormalised index so the admin queue can list and filter without
  loading the heaviest payloads in the product.
* ``Campaign`` / ``CampaignMember`` / ``CampaignObservation``, via the existing
  ``CampaignService``, but ONLY for corroborated findings. A lead is never a campaign row.
"""

from __future__ import annotations

import logging
from dataclasses import asdict
from datetime import datetime, timezone

from app.campaigns.detector.types import (
    FAMILY_TIMING,
    METHOD_FAMILY,
    DetectionRun,
    Edge,
    Finding,
)

logger = logging.getLogger(__name__)

PAYLOAD_KEY = "campaign_detection_v1"

#: Only corroborated findings become durable Campaign rows. A lead stays in the payload where an
#: admin can look at it and decide. Publishing a claim about a group of named people is an
#: operator's decision, never a side effect of a scan finishing.
CAMPAIGN_METHOD_PREFIX = "cohort"


# ---------------------------------------------------------------------------------------------
# Serialisation
# ---------------------------------------------------------------------------------------------
def _edge_dict(e: Edge) -> dict:
    return {
        "a": e.a, "b": e.b, "method": e.method, "family": e.family,
        "weight": round(e.weight, 4), "sentence": e.sentence, "artifact": e.artifact,
        "statistic": list(e.statistic) if e.statistic else None,
    }


def _finding_dict(f: Finding) -> dict:
    d = asdict(f)
    d["edges"] = [_edge_dict(e) for e in f.edges]
    return d


def to_dict(run: DetectionRun) -> dict:
    return {
        "version": 1,
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "passes": run.passes,
        "score_source": run.score_source,
        "platform": run.platform,
        "cohort_size": run.cohort_size,
        "scanned_total": run.scanned_total,
        "thresholds_version": run.thresholds_version,
        "best_score": run.best_score,
        "best_label": run.best_label,
        "lone_high_scorers": run.lone_high_scorers,
        "notes": run.notes,
        "findings": [_finding_dict(f) for f in run.findings],
    }


def stored_run(payload: dict) -> dict | None:
    block = payload.get(PAYLOAD_KEY)
    return block if isinstance(block, dict) else None


def inherited_timing_edges(previous: dict | None) -> list[Edge]:
    """Pass 1's timing edges, rehydrated so a later pass cannot lose them.

    Only the TIMING family is carried, and only as a floor: every signal re-runs on each pass, and
    ``fuse_pairs`` takes the strongest edge within a family, so an inherited edge never
    double-counts with its own recomputation.

    It exists for investigations whose payload predates ``video.thread_arrivals``. Timing is the one
    signal whose null needs every comment under the post, including from authors never selected for
    scoring, and on an older payload the only arrivals available are the scanned accounts' own.
    That under-states the rate, which over-states significance in the direction that invents
    findings, so a recomputation there would be worse than useless. Carrying pass 1's edges means
    the timing evidence stays as measured when the full stream was still in hand.
    """
    if not previous:
        return []
    out: list[Edge] = []
    for f in previous.get("findings") or []:
        if not isinstance(f, dict):
            continue
        for e in f.get("edges") or []:
            if not isinstance(e, dict):
                continue
            method = e.get("method")
            if METHOD_FAMILY.get(str(method)) != FAMILY_TIMING:
                continue
            stat = e.get("statistic")
            out.append(Edge(
                a=str(e.get("a") or ""), b=str(e.get("b") or ""), method=str(method),
                weight=float(e.get("weight") or 0.0),
                sentence=str(e.get("sentence") or ""), artifact=str(e.get("artifact") or ""),
                statistic=(str(stat[0]), float(stat[1])) if isinstance(stat, list) and len(stat) == 2 else None,
            ))
    return [e for e in out if e.a and e.b]


# ---------------------------------------------------------------------------------------------
# Writing
# ---------------------------------------------------------------------------------------------
def write_payload_block(session, investigation, run: DetectionRun) -> dict:
    """Store the run on the investigation.

    Reassigns ``payload_json`` rather than mutating it, because SQLAlchemy does not track in-place
    changes to a JSON column, and wraps the write in a SAVEPOINT so a failure here cannot corrupt
    the surrounding transaction. Both are the pattern ``analyst.persist_assessment`` established.
    """
    block = to_dict(run)
    try:
        with session.begin_nested():
            investigation.payload_json = {
                **(investigation.payload_json or {}), PAYLOAD_KEY: block,
            }
            session.add(investigation)
    except Exception:  # noqa: BLE001 - persistence of an advisory result is best-effort
        logger.exception(
            "campaign detector: could not persist detection for inv=%s",
            getattr(investigation, "slug", "?"),
        )
    return block


def upsert_index_row(session, investigation, run: DetectionRun) -> None:
    """Keep the admin queue's index row in step with the payload block."""
    try:
        from sqlalchemy import select

        from app.storage.models import CampaignDetection

        slug = str(getattr(investigation, "slug", "") or "")
        if not slug:
            return
        campaigns = sum(1 for f in run.findings if f.label == "corroborated")
        with session.begin_nested():
            row = session.execute(
                select(CampaignDetection).where(CampaignDetection.investigation_slug == slug)
            ).scalar_one_or_none()
            if row is None:
                row = CampaignDetection(investigation_slug=slug)
                session.add(row)
            row.user_id = getattr(investigation, "user_id", None)
            row.platform = run.platform or "unknown"
            row.computed_at = datetime.now(timezone.utc)
            row.passes = run.passes
            row.score_source = run.score_source
            row.scanned_total = run.scanned_total
            row.cohort_size = run.cohort_size
            row.finding_count = len(run.findings)
            row.campaign_count = campaigns
            row.best_score = run.best_score
            row.best_label = run.best_label
            row.thresholds_version = run.thresholds_version
            # A re-run reopens a row an admin had dismissed ONLY if it now finds a campaign it did
            # not find before. Otherwise a dismissal would be undone by every refinement pass, and
            # a queue that refills itself is a queue nobody reads.
            if row.status == "dismissed" and campaigns > 0 and (row.campaign_count or 0) == 0:
                row.status = "open"
    except Exception:  # noqa: BLE001
        logger.exception("campaign detector: could not upsert detection index row")


def record_campaigns(session, investigation, run: DetectionRun) -> int:
    """Bridge corroborated findings into the durable, deployment-global campaign record.

    ONE ``record_clusters`` call per finding. ``record_clusters`` applies a single
    ``coordination_score`` to everything in the call and ``merge_clusters`` unions any two clusters
    sharing an account, so batching two findings into one call would both mis-score them and risk
    fusing them. Communities are member-disjoint by construction, so per-finding calls cannot merge
    across findings.
    """
    corroborated = [f for f in run.findings if f.label == "corroborated"]
    if not corroborated:
        return 0

    written = 0
    try:
        from app.campaigns.service import CampaignService
        from app.detection.coordination._types import CoordinationCluster

        context_id = str(getattr(investigation, "target_id", "") or "") or None
        service = CampaignService(session)
        for f in corroborated:
            # One cluster per method, all sharing the finding's member list, so merge_clusters
            # folds them into a single component carrying every method that fired.
            clusters = [
                CoordinationCluster(
                    method=m,
                    members=list(f.members),
                    score=f.score,
                    evidence=list(f.evidence),
                )
                for m in (f.methods or ["verbatim_echo"])
            ]
            try:
                with session.begin_nested():
                    service.record_clusters(
                        platform=run.platform or "unknown",
                        context_id=context_id,
                        clusters=clusters,
                        coordination_score=f.score,
                        confidence=min(1.0, 0.4 + 0.2 * len(f.families_fired)),
                    )
                written += 1
            except Exception:  # noqa: BLE001 - one bad finding must not lose the others
                logger.exception("campaign detector: could not record campaign for %s",
                                 f.finding_id)
    except Exception:  # noqa: BLE001
        logger.exception("campaign detector: campaign bridge unavailable")
    return written


def save(session, investigation, run: DetectionRun) -> dict:
    """Everything, in the order that keeps the three stores consistent."""
    block = write_payload_block(session, investigation, run)
    record_campaigns(session, investigation, run)
    upsert_index_row(session, investigation, run)
    return block
