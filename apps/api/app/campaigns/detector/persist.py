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
        # Required, not decorative: for the two measured-null signals this p-value IS the
        # denominator of the likelihood ratio, so an edge rehydrated without it silently drops to
        # LR 1.0 and contributes nothing. That failure is invisible, which is why it is serialised
        # explicitly rather than recovered from `statistic`.
        "measured_p": e.measured_p,
        "log10_lr": round(e.log10_lr, 4),
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
            # Fall back to `statistic` for blocks written before `measured_p` was serialised: for
            # a timing edge that tuple is ("p_value", p), which is the same number. Without this an
            # inherited edge would carry no p-value, its likelihood ratio would silently be 1.0, and
            # the timing evidence pass 1 measured would vanish rather than transfer.
            measured = e.get("measured_p")
            if measured is None and isinstance(stat, list) and len(stat) == 2 and stat[0] == "p_value":
                measured = stat[1]
            out.append(Edge(
                a=str(e.get("a") or ""), b=str(e.get("b") or ""), method=str(method),
                weight=float(e.get("weight") or 0.0),
                sentence=str(e.get("sentence") or ""), artifact=str(e.get("artifact") or ""),
                statistic=(str(stat[0]), float(stat[1])) if isinstance(stat, list) and len(stat) == 2 else None,
                measured_p=float(measured) if measured is not None else None,
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


def record_campaigns(session, investigation, run: DetectionRun, cohort=None) -> int:
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
                    sketch = _signature_for(f, cohort)
                    campaigns = service.record_clusters(
                        platform=run.platform or "unknown",
                        context_id=context_id,
                        clusters=clusters,
                        coordination_score=f.score,
                        confidence=min(1.0, 0.4 + 0.2 * len(f.families_fired)),
                        # Passed so `_match_or_create` can recognise this operation even when it
                        # shares no accounts with its own previous run.
                        signature=sketch[0] if sketch else None,
                    )
                    _attach_operation_identity(session, campaigns, f, run, sketch)
                written += 1
            except Exception:  # noqa: BLE001 - one bad finding must not lose the others
                logger.exception("campaign detector: could not record campaign for %s",
                                 f.finding_id)
    except Exception:  # noqa: BLE001
        logger.exception("campaign detector: campaign bridge unavailable")
    return written


def _signature_for(finding, cohort):
    """The finding's behavioural signature, or None when the group has shown too little of itself."""
    if cohort is None:
        return None
    try:
        from app.campaigns.tracking import signature as sig

        accounts_by_id = {a.external_id: a for a in getattr(cohort, "accounts", [])}
        if not accounts_by_id:
            return None
        return sig.signature_for_members(finding.members, accounts_by_id)
    except Exception:  # noqa: BLE001
        logger.warning("campaign detector: could not build a signature", exc_info=True)
        return None


def _attach_operation_identity(session, campaigns, finding, run: DetectionRun, built) -> None:
    """Give a recorded campaign its posterior, its behavioural signature and its lifecycle state.

    The signature is what lets this operation be recognised after it replaces every account it is
    currently using, so writing it is not bookkeeping: it is the only durable identity an operation
    has. See ``tracking/signature.py``.
    """
    if not campaigns:
        return
    try:
        from app.campaigns.tracking import operations

        for campaign in campaigns:
            campaign.posterior = max(float(campaign.posterior or 0.0), float(finding.score))
            campaign.origin = campaign.origin or "detected"
            platforms = set(campaign.platforms_json or []) | {run.platform or "unknown"}
            campaign.platforms_json = sorted(platforms)
            state = operations.mark_lifecycle(campaign)
            if state == "resurfaced":
                logger.info(
                    "operations: campaign %s resurfaced after dormancy (now %s sightings)",
                    campaign.campaign_key, campaign.observation_count,
                )
            if built is not None:
                operations.store_signature(session, campaign, built[0], built[1])
    except Exception:  # noqa: BLE001 - identity is an enhancement, never a reason to lose the row
        logger.warning("campaign detector: could not attach operation identity", exc_info=True)


def save(session, investigation, run: DetectionRun, cohort=None) -> dict:
    """Everything, in the order that keeps the four stores consistent.

    ``cohort`` is optional so a caller with only a stored run can still persist it, but without it
    no behavioural signature can be built, and an operation recorded with no signature cannot be
    recognised after it rotates its accounts.
    """
    block = write_payload_block(session, investigation, run)
    record_campaigns(session, investigation, run, cohort)
    record_global_evidence(session, investigation, run, cohort)
    upsert_index_row(session, investigation, run)
    return block


def record_global_evidence(session, investigation, run: DetectionRun, cohort) -> int:
    """Fold this scan's pairwise evidence into the deployment-wide coordination graph.

    Recorded for EVERY pair that produced evidence, not only the ones inside a corroborated
    finding. That is the whole point of accumulating: a pair at 0.86 today is below the bar and
    still worth remembering, because the same pair seen again on an unrelated post next month is
    what takes it over. Discarding sub-threshold evidence would mean the system could only ever
    learn from what it had already decided.
    """
    if cohort is None:
        return 0
    try:
        from app.campaigns.detector.fuse import pair_evidence
        from app.campaigns.tracking import graph

        edges = [e for f in run.findings for e in f.edges]
        if not edges:
            return 0
        return graph.record_pairs(
            session,
            platform=run.platform or "unknown",
            context_id=str(getattr(investigation, "target_id", "") or "") or None,
            pair_evidence=pair_evidence(edges),
        )
    except Exception:  # noqa: BLE001 - accumulation must never fail a scan
        logger.warning("campaign detector: could not record global evidence", exc_info=True)
        return 0
