"""Anomaly detectors — pure functions over the existing DB.

Two detectors for Phase 8:

1. ``detect_narrative_spikes`` — narratives whose membership rate has
   accelerated (>2x baseline) AND have at least N new members in the
   trailing hour.
2. ``detect_high_tier_surge`` — investigations at elevated/high tier in
   the trailing hour vs the 24h baseline.

Both write Alert rows (user_id NULL = global anomaly visible to all).
Cheap to run on the existing tables — no new infrastructure.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.storage.models import (
    Alert, Investigation, Narrative, NarrativeMembership,
)


@dataclass
class AnomalyHit:
    kind: str       # "narrative_spike" | "high_tier_surge"
    severity: str   # "info" | "moderate" | "elevated"
    message: str
    payload: dict


# ---------------------------------------------------------------------------
# Narrative spikes
# ---------------------------------------------------------------------------


def detect_narrative_spikes(
    session: Session, *, settings: Settings | None = None,
) -> list[AnomalyHit]:
    """Find narratives growing >= growth_ratio× hour-over-hour."""
    settings = settings or get_settings()
    now = datetime.now(timezone.utc)
    one_h = now - timedelta(hours=1)
    two_h = now - timedelta(hours=2)

    # Memberships in the last hour, grouped by narrative_id
    recent_rows = session.execute(
        select(
            NarrativeMembership.narrative_id,
            func.count(NarrativeMembership.id).label("n"),
        )
        .where(NarrativeMembership.observed_at >= one_h)
        .group_by(NarrativeMembership.narrative_id)
    ).all()
    recent_map = {nid: int(n) for (nid, n) in recent_rows if nid is not None}

    # Memberships in the prior hour, grouped
    prior_rows = session.execute(
        select(
            NarrativeMembership.narrative_id,
            func.count(NarrativeMembership.id).label("n"),
        )
        .where(
            NarrativeMembership.observed_at >= two_h,
            NarrativeMembership.observed_at < one_h,
        )
        .group_by(NarrativeMembership.narrative_id)
    ).all()
    prior_map = {nid: int(n) for (nid, n) in prior_rows if nid is not None}

    if not recent_map:
        return []

    # Pull narrative labels for the spiking ids
    candidates = [
        nid for nid, recent in recent_map.items()
        if recent >= settings.narrative_spike_min_recent
        and recent > prior_map.get(nid, 0) * settings.narrative_spike_growth_ratio
    ]
    if not candidates:
        return []

    rows = list(session.execute(
        select(Narrative).where(Narrative.id.in_(candidates))
    ).scalars())

    hits: list[AnomalyHit] = []
    for n in rows:
        recent = recent_map.get(n.id, 0)
        prior = prior_map.get(n.id, 0)
        growth = (recent / prior) if prior else float("inf")
        # Severity scaled to growth magnitude
        sev = "elevated" if growth >= 4 or recent >= 15 else "moderate"
        hits.append(AnomalyHit(
            kind="narrative_spike",
            severity=sev,
            message=(
                f"Narrative #{n.id} surged: {recent} new members in the last hour "
                f"(prior hour: {prior}). Label: {n.label[:120]}"
            ),
            payload={
                "narrative_id": n.id,
                "label": n.label,
                "recent_members": recent,
                "prior_members": prior,
                "distinct_authors": n.distinct_authors,
                "total_members": n.member_count,
            },
        ))
    return hits


# ---------------------------------------------------------------------------
# High-tier surges
# ---------------------------------------------------------------------------


def detect_high_tier_surge(
    session: Session, *, settings: Settings | None = None,
) -> list[AnomalyHit]:
    settings = settings or get_settings()
    now = datetime.now(timezone.utc)
    one_h = now - timedelta(hours=1)
    day = now - timedelta(hours=24)

    last_hour = int(session.execute(
        select(func.count(Investigation.id)).where(
            Investigation.created_at >= one_h,
            Investigation.overall_tier.in_(("elevated", "high")),
        )
    ).scalar_one())
    last_day = int(session.execute(
        select(func.count(Investigation.id)).where(
            Investigation.created_at >= day,
            Investigation.overall_tier.in_(("elevated", "high")),
        )
    ).scalar_one())
    baseline = last_day / 24.0  # avg per hour over the trailing day

    threshold = max(settings.high_tier_surge_min, baseline * settings.high_tier_surge_baseline_ratio)
    if last_hour < threshold:
        return []

    sev = "elevated" if last_hour >= max(6, baseline * 4) else "moderate"
    return [AnomalyHit(
        kind="high_tier_surge",
        severity=sev,
        message=(
            f"High-tier scan surge: {last_hour} elevated/high investigations "
            f"in the last hour (24h baseline ≈ {baseline:.1f}/h)."
        ),
        payload={
            "last_hour": last_hour,
            "baseline_per_hour": baseline,
            "threshold": threshold,
        },
    )]


# ---------------------------------------------------------------------------
# Idempotency helpers — avoid spamming duplicate alerts.
# ---------------------------------------------------------------------------


def alert_already_open(
    session: Session, kind: str, payload_key: str, payload_value, *, within_minutes: int = 60,
) -> bool:
    """Has an alert of this kind for this entity fired in the last N minutes?"""
    from sqlalchemy import cast, String as _String
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=within_minutes)
    rows = session.execute(
        select(Alert).where(
            Alert.kind == kind,
            Alert.created_at >= cutoff,
        )
    ).scalars()
    for r in rows:
        if (r.payload_json or {}).get(payload_key) == payload_value:
            return True
    return False
