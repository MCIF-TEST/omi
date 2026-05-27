"""Account-age cohort anomaly.

A typical YouTube video pulls commenters from a 15-year-wide spread of
account creation dates. Bot farms ship accounts in batches; a video whose
commenters are heavily concentrated in a single narrow creation window
(say, 30% of accounts created within the same 4 weeks) is almost certainly
showing artificial engagement.

We compute the max share of commenters falling into any sliding 4-week
window and flag anomalies. The members of the dominant window get bundled
into a single ``CoordinationCluster``.
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from app.detection.coordination._types import CoordinationCluster, CoordinationFinding


@dataclass
class CohortEntry:
    external_id: str
    handle: str
    created_at: datetime | None


def detect_age_cohorts(
    entries: list[CohortEntry],
    *,
    window_days: int = 28,
    suspicious_share: float = 0.25,
    min_window_size: int = 3,
) -> CoordinationFinding:
    dated = [
        (e, _to_utc(e.created_at))
        for e in entries
        if e.created_at is not None
    ]
    if len(dated) < min_window_size:
        return CoordinationFinding(
            method="age_cohort",
            overall_score=0.5,
            confidence=0.0,
            clusters=[],
            evidence=[
                f"Need ≥ {min_window_size} commenters with account-creation dates; "
                f"have {len(dated)}."
            ],
        )

    # Bin by week, then slide a 4-week window across weeks to find the densest interval.
    by_week: dict[datetime, list[CohortEntry]] = defaultdict(list)
    for entry, ts in dated:
        week_anchor = ts - timedelta(days=ts.weekday())
        week_anchor = week_anchor.replace(hour=0, minute=0, second=0, microsecond=0)
        by_week[week_anchor].append(entry)

    sorted_weeks = sorted(by_week.keys())
    best_share = 0.0
    best_members: list[CohortEntry] = []
    best_window_start: datetime | None = None

    # Slide a real calendar window across the week anchors.
    for i, start in enumerate(sorted_weeks):
        end = start + timedelta(days=window_days)
        members: list[CohortEntry] = []
        for j in range(i, len(sorted_weeks)):
            if sorted_weeks[j] >= end:
                break
            members.extend(by_week[sorted_weeks[j]])
        share = len(members) / len(dated)
        if share > best_share and len(members) >= min_window_size:
            best_share = share
            best_members = members
            best_window_start = start

    clusters: list[CoordinationCluster] = []
    if best_share >= suspicious_share and best_window_start is not None:
        window_end = best_window_start + timedelta(days=window_days)
        # Score: how far past the suspicious threshold are we.
        excess = (best_share - suspicious_share) / max(1e-3, 1.0 - suspicious_share)
        score = min(1.0, 0.55 + 0.45 * excess)
        clusters.append(
            CoordinationCluster(
                method="age_cohort",
                members=sorted(e.external_id for e in best_members),
                score=score,
                evidence=[
                    f"{len(best_members)} of {len(dated)} commenters ({best_share:.0%}) "
                    f"created their accounts between "
                    f"{best_window_start.date().isoformat()} and "
                    f"{window_end.date().isoformat()} — an unusually narrow window "
                    f"for an organic audience."
                ],
                metadata={
                    "window_share": best_share,
                    "window_days": float(window_days),
                    "cohort_size": float(len(best_members)),
                },
            )
        )

    overall = 1.0 / (1.0 + math.exp(-(best_share - suspicious_share) * 12))
    confidence = min(1.0, len(dated) / 25.0)
    evidence: list[str] = [
        f"Densest {window_days}-day account-creation window holds "
        f"{best_share:.0%} of commenters with known creation dates."
    ]

    return CoordinationFinding(
        method="age_cohort",
        overall_score=float(overall),
        confidence=confidence,
        clusters=clusters,
        evidence=evidence,
    )


def _to_utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
