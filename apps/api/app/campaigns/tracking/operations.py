"""Operation identity: matching, merging, and the dormant/resurfaced lifecycle.

Matching order, and the order is the point:

1. **Member overlap.** The same accounts turned up again. Cheapest and most certain.
2. **Signature collision.** No shared accounts, but the same script, handle factory, provisioning
   pattern or tooling. This is the case member overlap cannot see and the case that matters: a
   serious operation burns its accounts between runs, so by the time you are looking at its third
   campaign there is nothing left to overlap with.
3. **Create.** Genuinely new.

Without step 2 the system reports a first sighting every time an operation rotates, which is both
wrong and exactly backwards: rotation is evidence of sophistication, and the product would respond
by forgetting.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.campaigns.tracking import signature as sig
from app.storage.models import Campaign, CampaignMember, OperationSignatureBand

logger = logging.getLogger(__name__)

#: No observation for this long and an operation is dormant. Not deleted, not closed: operations
#: come back, and the fact that one came back after four months is itself a finding.
DORMANCY_DAYS = 90

#: Above this many members, require the Jaccard floor rather than accepting a bare shared-account
#: count. `CampaignService._match_or_create` accepts `jaccard >= 0.30 OR shared >= 3`, so three
#: shared accounts link a 5-member cluster to a 500-member campaign at j = 0.006. That OR is
#: reasonable while campaigns are small and absurd once one is large.
LARGE_CAMPAIGN_MEMBERS = 25


def find_by_signature(session, sketch: list[int] | None) -> Campaign | None:
    """The campaign whose behavioural signature best matches, or None.

    Band collision generates candidates by indexed lookup; the sketch comparison decides. This is
    the whole reason the band table exists: without it, matching would compare a new sketch against
    every campaign in the deployment on every scan.
    """
    if not sketch:
        return None
    keys = sig.band_keys(sketch)
    try:
        rows = session.execute(
            select(OperationSignatureBand.campaign_id, OperationSignatureBand.band_index,
                   OperationSignatureBand.band_key)
        ).all()
    except Exception:  # noqa: BLE001
        logger.warning("operations: signature band lookup failed", exc_info=True)
        return None

    wanted = {(i, k) for i, k in enumerate(keys)}
    candidate_ids = sorted({cid for cid, idx, key in rows if (idx, key) in wanted})
    if not candidate_ids:
        return None

    best, best_similarity = None, 0.0
    for campaign in session.execute(
        select(Campaign).where(Campaign.id.in_(candidate_ids))
    ).scalars().all():
        similarity = sig.signature_similarity(sketch, campaign.signature_json)
        if similarity >= sig.SIGNATURE_MATCH_THRESHOLD and similarity > best_similarity:
            best, best_similarity = campaign, similarity
    if best is not None:
        logger.info(
            "operations: matched campaign %s by signature at %.2f (no member overlap needed)",
            best.campaign_key, best_similarity,
        )
    return best


def store_signature(session, campaign: Campaign, sketch: list[int], keys: list[str]) -> None:
    """Persist a sketch and reindex its bands.

    Bands are replaced rather than appended: a campaign that has grown has a different signature,
    and leaving the old bands would keep matching it against what it used to be.
    """
    try:
        campaign.signature_json = list(sketch)
        session.query(OperationSignatureBand).filter(
            OperationSignatureBand.campaign_id == campaign.id
        ).delete(synchronize_session=False)
        for index, key in enumerate(keys):
            session.add(OperationSignatureBand(
                campaign_id=campaign.id, band_index=index, band_key=key,
            ))
    except Exception:  # noqa: BLE001
        logger.warning("operations: could not store signature for %s",
                       getattr(campaign, "campaign_key", "?"), exc_info=True)


def member_overlap_match(
    session, *, platform: str, members: set[str],
) -> tuple[Campaign | None, float]:
    """The best member-overlap match, with the large-campaign correction applied."""
    if not members:
        return None, 0.0
    rows = session.execute(
        select(CampaignMember.campaign_id, CampaignMember.account_external_id).where(
            CampaignMember.platform == platform,
            CampaignMember.account_external_id.in_(members),
        )
    ).all()
    if not rows:
        return None, 0.0

    shared_by_campaign: dict[int, set[str]] = {}
    for campaign_id, account in rows:
        shared_by_campaign.setdefault(campaign_id, set()).add(account)

    best, best_j = None, 0.0
    for campaign_id, shared in sorted(shared_by_campaign.items()):
        campaign = session.get(Campaign, campaign_id)
        if campaign is None:
            continue
        union = max(1, (campaign.member_count or 0) + len(members) - len(shared))
        j = len(shared) / union
        # Small campaign: a few shared accounts is a real link. Large campaign: it is not, and
        # accepting it would let every new cluster fall into the deployment's biggest campaign.
        if (campaign.member_count or 0) >= LARGE_CAMPAIGN_MEMBERS:
            accept = j >= 0.30
        else:
            accept = j >= 0.30 or len(shared) >= 3
        if accept and j > best_j:
            best, best_j = campaign, j
    return best, best_j


def mark_lifecycle(campaign: Campaign, *, now: datetime | None = None) -> str:
    """Update dormancy on observation. Returns what happened, for logging and the UI."""
    now = now or datetime.now(timezone.utc)
    last = campaign.last_seen_at
    if last is not None and last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)

    was_dormant = campaign.dormant_since is not None or (
        last is not None and (now - last) > timedelta(days=DORMANCY_DAYS)
    )
    campaign.last_seen_at = now
    if was_dormant:
        campaign.dormant_since = None
        campaign.resurfaced_count = int(campaign.resurfaced_count or 0) + 1
        return "resurfaced"
    return "observed"


def sweep_dormant(session, *, now: datetime | None = None) -> int:
    """Mark operations dormant that have not been seen inside the window.

    NOTHING CALLS THIS, and both halves of what this docstring used to say were false. It claimed to
    be "called opportunistically from the detection path", and no call site exists anywhere in
    `app/`; it justified not being scheduled by saying the deployment has no scheduler, and
    `app/monitoring/scheduler.py` runs a pass holding a Postgres advisory lock, which is exactly
    where `netdetect.registry.refresh_phases` was wired for the same job.

    IT IS STILL NOT WIRED, DELIBERATELY, and the difference from `refresh_phases` is the point.
    There, the phase column was the thing an operator reads off the formation catalogue and nothing
    else derived it, so leaving it unswept meant every dormant operation presented as live. Here,
    `mark_seen` derives dormancy inline from `last_seen_at` (`dormant_since is not None OR the last
    sighting is older than DORMANCY_DAYS`), so resurgence detection works without this ever running,
    and no route or export serves `dormant_since`. Scheduling a write for a column nothing reads
    would be speculative work.

    So this is dead code with a live purpose: wire it the day something consumes the stored column,
    and delete the derived half of `mark_seen`'s check at the same time so the two cannot disagree.
    """
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=DORMANCY_DAYS)
    changed = 0
    try:
        for campaign in session.execute(
            select(Campaign).where(
                Campaign.last_seen_at < cutoff,
                Campaign.dormant_since.is_(None),
            ).limit(100)
        ).scalars().all():
            campaign.dormant_since = now
            changed += 1
    except Exception:  # noqa: BLE001
        logger.warning("operations: dormancy sweep failed", exc_info=True)
    return changed
