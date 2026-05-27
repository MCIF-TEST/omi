"""Narrative coordination intelligence — multi-signal scoring.

Layer that runs ON TOP of the raw semantic clustering. Where the clustering
module asks "do these comments share topic + framing?", this module asks
the harder question: "is this cluster the product of coordinated, artificial,
or manipulative activity?"

Output is never binary. Every cluster receives a panel of probabilistic
scores:

* ``coordination_score``     — aggregate coordination likelihood
* ``manipulation_probability`` — weighted lift from inauth+burst+sync
* ``synchronization_intensity`` — timing entropy + burst score
* ``semantic_cohesion``      — how tight (vs. diffuse) the cluster is
* ``cluster_confidence``     — number of independent signals firing

The "MOST IMPORTANT RULE" enforced here: only accounts at the MODERATE
risk tier or above contribute to the coordination scoring or appear in
the displayed cluster. Low-risk accounts may be members of the *semantic*
cluster (we need their comments to detect it exists), but they never
appear in propagation graphs or top-account lists.

Tier vocabulary mapping (internal → public):

    internal "low"      → "low"       (excluded from clusters)
    internal "moderate" → "moderate"  (included)
    internal "elevated" → "high"      (included, anchor candidate)
    internal "high"     → "extreme"   (included, primary anchor)
"""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Iterable

# Internal tier rank — used to decide whether an account is eligible for
# inclusion in the narrative coordination layer.
TIER_RANK = {"low": 0, "moderate": 1, "elevated": 2, "high": 3}

# Internal storage tier → user-facing display tier.
DISPLAY_TIER = {
    "low": "low",
    "moderate": "moderate",
    "elevated": "high",
    "high": "extreme",
}

# Minimum internal tier that qualifies for cluster membership.
MIN_INCLUSION_TIER_RANK = TIER_RANK["moderate"]


def display_tier(internal_tier: str | None) -> str:
    """Map storage tier name to the public-facing risk vocabulary."""
    if not internal_tier:
        return "unscored"
    return DISPLAY_TIER.get(internal_tier, internal_tier)


def is_qualifying_tier(internal_tier: str | None) -> bool:
    """Return True iff this account is suspicious enough to appear in clusters."""
    if not internal_tier:
        return False
    return TIER_RANK.get(internal_tier, -1) >= MIN_INCLUSION_TIER_RANK


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class MembershipRecord:
    """One row from narrative_memberships, enriched with tier info."""
    account_external_id: str
    platform: str
    parent_id: str | None
    observed_at: datetime
    text_hash: int          # cheap fingerprint for repost detection
    tier: str | None        # internal tier, or None if account never scanned


@dataclass
class PropagationPoint:
    """One temporal bucket in the propagation timeline."""
    bucket_start: datetime
    count: int
    velocity: float          # comments per hour in this bucket
    suspicious_count: int    # how many were from moderate+ accounts


@dataclass
class CoordinationScores:
    """Multi-dimensional coordination assessment for one narrative cluster.

    All probabilities are in [0,1]. ``cluster_confidence`` is the count of
    independent signals firing at notable strength (≥ 0.4).
    """

    # Aggregate scores (the primary surface)
    coordination_score: float = 0.0
    manipulation_probability: float = 0.0
    synchronization_intensity: float = 0.0
    semantic_cohesion: float = 0.0
    cluster_confidence: int = 0

    # Individual signal components (all 0-1)
    inauthenticity_fraction: float = 0.0    # share of scanned authors at moderate+
    temporal_burst_score: float = 0.0       # peak-to-mean ratio anomaly
    timing_entropy_anomaly: float = 0.0     # how non-uniform the timestamps are
    repost_overlap: float = 0.0             # share of suspicious comments duplicating text
    cross_parent_spread: float = 0.0        # share of suspicious accounts active on >1 parent
    author_concentration: float = 0.0       # gini-like — top 3 authors / total
    persistence_score: float = 0.0          # how long the cluster has stayed active

    # Derived label — never binary, but a short verdict for UX
    coordination_label: str = "unscored"    # organic | mixed | suspicious | coordinated | manipulation_network

    # Narrative-level risk tier in user vocabulary
    risk_tier: str = "low"                  # low | moderate | high | extreme

    # Bookkeeping
    qualifying_member_count: int = 0        # comments from moderate+ accounts
    qualifying_author_count: int = 0
    signal_breakdown: list[dict] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Public entrypoint
# ---------------------------------------------------------------------------


def score_narrative(
    *,
    members: list[MembershipRecord],
    first_seen_at: datetime,
    last_seen_at: datetime,
) -> CoordinationScores:
    """Compute the full multi-signal score panel for one narrative.

    Members should be ALL memberships, including low-tier ones — the
    inauthenticity_fraction needs the full denominator. The internal logic
    filters to moderate+ when computing coordination signals.
    """
    scores = CoordinationScores()
    if not members:
        return scores

    # Identify qualifying members (moderate+) — the "intelligence-grade" subset.
    qualifying = [m for m in members if is_qualifying_tier(m.tier)]
    scanned = [m for m in members if m.tier is not None]
    distinct_qualifying_authors = {m.account_external_id for m in qualifying}

    scores.qualifying_member_count = len(qualifying)
    scores.qualifying_author_count = len(distinct_qualifying_authors)

    # --- Signal 1: inauthenticity fraction ----------------------------------
    # Fraction of SCANNED authors at moderate+. Uses scanned authors only —
    # never-scanned authors don't count for or against.
    distinct_scanned_authors = {m.account_external_id for m in scanned}
    if distinct_scanned_authors:
        flagged = {
            m.account_external_id for m in scanned
            if is_qualifying_tier(m.tier)
        }
        scores.inauthenticity_fraction = len(flagged) / len(distinct_scanned_authors)

    # If there are no suspicious authors, everything else is moot.
    if not qualifying:
        scores.coordination_label = "organic"
        scores.risk_tier = "low"
        return scores

    # --- Signal 2: temporal burst score -------------------------------------
    # Look only at suspicious comments. Bucket by hour. The peak-to-mean
    # ratio (normalized) is the burst signal — coordinated drops cluster
    # tightly; organic chatter spreads.
    scores.temporal_burst_score = _temporal_burst(qualifying)

    # --- Signal 3: timing entropy anomaly -----------------------------------
    # How non-uniformly distributed the hour-of-day is for suspicious
    # comments. High value = posting in a narrow window (e.g. all overnight).
    scores.timing_entropy_anomaly = _timing_entropy_anomaly(qualifying)

    # --- Signal 4: repost overlap -------------------------------------------
    # Fraction of suspicious comments that share text-hash with another
    # suspicious comment by a different author.
    scores.repost_overlap = _repost_overlap(qualifying)

    # --- Signal 5: cross-parent spread --------------------------------------
    # Fraction of suspicious authors who commented on >1 distinct parent.
    # Higher = the same accounts following the topic across multiple targets.
    scores.cross_parent_spread = _cross_parent_spread(qualifying)

    # --- Signal 6: author concentration -------------------------------------
    # How concentrated activity is in the top few suspicious accounts.
    # Higher = an amplification cell rather than diffuse engagement.
    scores.author_concentration = _author_concentration(qualifying)

    # --- Signal 7: persistence score ----------------------------------------
    # How many days the cluster has remained active. Brief flashes are
    # often organic; sustained activity from suspicious authors over many
    # days is more characteristic of a campaign.
    scores.persistence_score = _persistence_score(first_seen_at, last_seen_at)

    # --- Signal 8: semantic cohesion ----------------------------------------
    # Proxy: ratio of qualifying members to qualifying authors. High value =
    # individual authors making many cluster contributions = tighter cell.
    if scores.qualifying_author_count > 0:
        ratio = scores.qualifying_member_count / scores.qualifying_author_count
        scores.semantic_cohesion = min(1.0, (ratio - 1.0) / 4.0) if ratio >= 1.0 else 0.0

    # --- Aggregate ----------------------------------------------------------
    # Coordination score: weighted sum of independent signals. Weights chosen
    # so that no single signal can push past 0.5 on its own — coordination
    # requires multiple lines of evidence.
    coord_components = [
        ("inauthenticity",       scores.inauthenticity_fraction, 0.18),
        ("temporal_burst",       scores.temporal_burst_score,    0.15),
        ("timing_entropy",       scores.timing_entropy_anomaly,  0.12),
        ("repost_overlap",       scores.repost_overlap,          0.15),
        ("cross_parent_spread",  scores.cross_parent_spread,     0.10),
        ("author_concentration", scores.author_concentration,    0.10),
        ("persistence",          scores.persistence_score,       0.08),
        ("semantic_cohesion",    scores.semantic_cohesion,       0.12),
    ]
    raw = sum(value * weight for _, value, weight in coord_components)
    # Confidence amplification: clusters firing on >=3 signals get a small
    # multiplicative lift; clusters firing on <=1 signal get suppressed.
    firing = sum(1 for _, v, _ in coord_components if v >= 0.4)
    if firing >= 3:
        raw = min(1.0, raw * 1.15)
    elif firing <= 1:
        raw = raw * 0.7
    scores.coordination_score = round(raw, 4)
    scores.cluster_confidence = firing

    # Manipulation probability: weighted toward inauthenticity + burst + repost
    # (the three signals most diagnostic of artificial amplification).
    manip = (
        scores.inauthenticity_fraction * 0.40
        + scores.temporal_burst_score * 0.25
        + scores.repost_overlap * 0.20
        + scores.timing_entropy_anomaly * 0.15
    )
    scores.manipulation_probability = round(min(1.0, manip), 4)

    # Synchronization intensity: timing-focused.
    sync = (
        scores.temporal_burst_score * 0.55
        + scores.timing_entropy_anomaly * 0.35
        + scores.author_concentration * 0.10
    )
    scores.synchronization_intensity = round(min(1.0, sync), 4)

    # Map to label / risk tier.
    scores.coordination_label = _coordination_label(scores)
    scores.risk_tier = _risk_tier(scores)

    scores.signal_breakdown = [
        {"name": name, "value": round(value, 4), "weight": weight}
        for name, value, weight in coord_components
    ]
    return scores


# ---------------------------------------------------------------------------
# Individual signal computers
# ---------------------------------------------------------------------------


def _temporal_burst(qualifying: list[MembershipRecord]) -> float:
    """Peak-to-mean ratio of hourly suspicious comments, normalized to [0,1].

    Bucket suspicious comments by hour. Burst = max bucket / mean bucket.
    Organic activity hovers around mean = ~1; coordinated bursts spike
    20x+. We squash via log so the score is well-behaved.
    """
    if len(qualifying) < 3:
        return 0.0
    buckets: Counter = Counter()
    for m in qualifying:
        if m.observed_at is None:
            continue
        bucket = m.observed_at.replace(minute=0, second=0, microsecond=0)
        buckets[bucket] += 1
    if not buckets:
        return 0.0
    counts = list(buckets.values())
    mean = sum(counts) / len(counts)
    peak = max(counts)
    if mean <= 0:
        return 0.0
    ratio = peak / mean
    # Log-squash: ratio of 4x → 0.5, 10x → 0.78, 30x → 0.96.
    return max(0.0, min(1.0, math.log(ratio) / math.log(30)))


def _timing_entropy_anomaly(qualifying: list[MembershipRecord]) -> float:
    """Anomaly score from hour-of-day entropy.

    Distribute suspicious comments across 24 hours. Compute Shannon entropy.
    Maximum entropy = log2(24) ≈ 4.585 (uniform). Tight posting windows
    drop the entropy. We normalize: anomaly = 1 - (entropy / max).
    """
    if len(qualifying) < 5:
        return 0.0
    hours: Counter = Counter()
    total = 0
    for m in qualifying:
        if m.observed_at is None:
            continue
        hours[m.observed_at.hour] += 1
        total += 1
    if total < 5 or not hours:
        return 0.0
    entropy = 0.0
    for c in hours.values():
        p = c / total
        if p > 0:
            entropy -= p * math.log2(p)
    max_entropy = math.log2(24)
    if max_entropy <= 0:
        return 0.0
    # Hard floor: even uniform-ish distributions return tiny anomaly. We
    # want the score to ramp once entropy < ~3.5 (= ~11 effective hours).
    raw = 1.0 - (entropy / max_entropy)
    # Quadratic emphasis so only sharply non-uniform distributions score high.
    return max(0.0, min(1.0, raw * raw * 1.6))


def _repost_overlap(qualifying: list[MembershipRecord]) -> float:
    """Fraction of suspicious comments whose text-hash appears under
    multiple distinct authors. High value = templated/copy-pasted.
    """
    if len(qualifying) < 3:
        return 0.0
    by_hash: dict[int, set[str]] = defaultdict(set)
    for m in qualifying:
        by_hash[m.text_hash].add(m.account_external_id)
    repeated_hashes = {h for h, authors in by_hash.items() if len(authors) >= 2}
    if not repeated_hashes:
        return 0.0
    overlapping = sum(1 for m in qualifying if m.text_hash in repeated_hashes)
    return overlapping / len(qualifying)


def _cross_parent_spread(qualifying: list[MembershipRecord]) -> float:
    """Fraction of suspicious authors that posted on >1 parent (video / thread).

    Cross-target activity from suspicious accounts is one of the strongest
    signals of a coordinated campaign — the same accounts following the
    same narrative across multiple videos.
    """
    if not qualifying:
        return 0.0
    parents_by_author: dict[str, set[str]] = defaultdict(set)
    for m in qualifying:
        if m.parent_id:
            parents_by_author[m.account_external_id].add(m.parent_id)
    if not parents_by_author:
        return 0.0
    multi = sum(1 for parents in parents_by_author.values() if len(parents) >= 2)
    return multi / len(parents_by_author)


def _author_concentration(qualifying: list[MembershipRecord]) -> float:
    """Share of qualifying comments accounted for by the top 3 authors.

    Amplification cells where 3 accounts produce 90% of suspicious activity
    score very high; diffuse engagement scores low.
    """
    if not qualifying:
        return 0.0
    counts = Counter(m.account_external_id for m in qualifying)
    if len(counts) <= 3:
        return 0.0   # not enough authors for concentration to mean anything
    top3 = sum(c for _, c in counts.most_common(3))
    return top3 / len(qualifying)


def _persistence_score(first: datetime, last: datetime) -> float:
    """Days alive, squashed. 1d → 0.1; 7d → 0.4; 30d → 0.75; 90d+ → ~1.0."""
    if first is None or last is None:
        return 0.0
    delta_days = max(0.0, (last - first).total_seconds() / 86400.0)
    return max(0.0, min(1.0, math.log1p(delta_days) / math.log1p(90)))


# ---------------------------------------------------------------------------
# Labels
# ---------------------------------------------------------------------------


def _coordination_label(s: CoordinationScores) -> str:
    """Map aggregate scores to a one-word verdict."""
    if s.qualifying_member_count == 0:
        return "organic"
    score = s.coordination_score
    manip = s.manipulation_probability
    if score >= 0.65 or manip >= 0.7:
        return "manipulation_network"
    if score >= 0.45:
        return "coordinated"
    if score >= 0.25 or s.inauthenticity_fraction >= 0.35:
        return "suspicious"
    if s.inauthenticity_fraction >= 0.15:
        return "mixed"
    return "organic"


def _risk_tier(s: CoordinationScores) -> str:
    """Map aggregate to the user-facing 4-band risk vocabulary."""
    score = s.coordination_score
    if score >= 0.65 or s.manipulation_probability >= 0.7:
        return "extreme"
    if score >= 0.45:
        return "high"
    if score >= 0.22 or s.inauthenticity_fraction >= 0.20:
        return "moderate"
    return "low"


# ---------------------------------------------------------------------------
# Propagation analysis
# ---------------------------------------------------------------------------


def propagation_timeline(
    members: list[MembershipRecord],
    *,
    bucket_hours: int = 6,
    max_buckets: int = 40,
) -> list[PropagationPoint]:
    """Bucket the cluster's activity over time, with suspicious-author split.

    Used by the UI to draw the propagation wave + identify burst points.
    """
    if not members:
        return []
    times = sorted(m.observed_at for m in members if m.observed_at is not None)
    if not times:
        return []
    start = times[0].replace(minute=0, second=0, microsecond=0)
    end = times[-1].replace(minute=0, second=0, microsecond=0) + timedelta(hours=bucket_hours)
    # Keep the number of buckets reasonable — auto-widen the bucket if the
    # span is large enough that we'd overshoot max_buckets.
    span_hours = max(1, int((end - start).total_seconds() // 3600))
    bucket_hours = max(bucket_hours, math.ceil(span_hours / max_buckets))

    points: dict[datetime, list[int]] = {}   # bucket_start -> [total, suspicious]
    for m in members:
        if m.observed_at is None:
            continue
        offset_hours = int((m.observed_at - start).total_seconds() // 3600)
        bucket_idx = offset_hours // bucket_hours
        bucket_start = start + timedelta(hours=bucket_idx * bucket_hours)
        if bucket_start not in points:
            points[bucket_start] = [0, 0]
        points[bucket_start][0] += 1
        if is_qualifying_tier(m.tier):
            points[bucket_start][1] += 1

    out: list[PropagationPoint] = []
    for bucket_start in sorted(points.keys()):
        total, suspicious = points[bucket_start]
        out.append(PropagationPoint(
            bucket_start=bucket_start,
            count=total,
            velocity=total / bucket_hours,
            suspicious_count=suspicious,
        ))
    return out


def amplification_bursts(timeline: list[PropagationPoint]) -> list[dict]:
    """Identify burst points: buckets where velocity > 2.5 × rolling mean.

    Returns a list of {bucket_start, velocity, severity} for the UI to
    annotate the propagation chart with spike markers.
    """
    if len(timeline) < 4:
        return []
    velocities = [p.velocity for p in timeline]
    bursts: list[dict] = []
    for i, point in enumerate(timeline):
        window = velocities[max(0, i - 3):i] or [0.0]
        baseline = sum(window) / len(window)
        if baseline <= 0:
            continue
        ratio = point.velocity / baseline
        if ratio >= 2.5:
            bursts.append({
                "bucket_start": point.bucket_start.isoformat(),
                "velocity": round(point.velocity, 2),
                "ratio": round(ratio, 2),
                "severity": "extreme" if ratio >= 5.0 else "high" if ratio >= 3.5 else "moderate",
                "suspicious_count": point.suspicious_count,
            })
    return bursts


def origin_window(members: list[MembershipRecord]) -> dict | None:
    """Identify the cluster's origin window — first burst of suspicious activity.

    Returns {first_seen, suspicious_first_seen, lag_hours} so the UI can
    show "narrative emerged X hours before suspicious amplification began",
    which is a tell for influence operations seeded into organic discourse.
    """
    if not members:
        return None
    times = sorted([m for m in members if m.observed_at is not None], key=lambda m: m.observed_at)
    if not times:
        return None
    first = times[0]
    suspicious = [m for m in times if is_qualifying_tier(m.tier)]
    if not suspicious:
        return {
            "first_seen": first.observed_at.isoformat(),
            "suspicious_first_seen": None,
            "lag_hours": None,
        }
    susp_first = suspicious[0]
    lag = (susp_first.observed_at - first.observed_at).total_seconds() / 3600.0
    return {
        "first_seen": first.observed_at.isoformat(),
        "suspicious_first_seen": susp_first.observed_at.isoformat(),
        "lag_hours": round(lag, 2),
    }


# ---------------------------------------------------------------------------
# Text fingerprinting — cheap, deterministic, no external deps
# ---------------------------------------------------------------------------


def text_fingerprint(text: str) -> int:
    """Stable hash of normalised text for repost detection.

    Lower-cases, strips punctuation noise, collapses whitespace, then
    fingerprints. Returns a Python int (64-bit hashable).
    """
    if not text:
        return 0
    import re
    s = re.sub(r"\s+", " ", re.sub(r"[^\w\s]", "", text.lower())).strip()
    if not s:
        return 0
    # Built-in hash is randomised between Python runs — use a deterministic
    # polynomial hash so reposts cluster across requests.
    h = 1469598103934665603
    for ch in s:
        h ^= ord(ch)
        h = (h * 1099511628211) & ((1 << 63) - 1)
    return h
