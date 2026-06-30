"""Memory compression — denser, not larger (Sprint 014).

Institutional memory must become DENSER as it accumulates, not merely bigger. Compression is a
deterministic background pass (off the live investigation path) that:

  * merges duplicate archetypes / equivalent behavioral signatures into one canonical object,
  * re-parents the duplicates' observations onto the canonical — provenance preserved: every
    observation keeps its own investigation + evidence + independence key,
  * reports redundant observations (those that no longer add independent support) and obsolete
    (retired/superseded) memories as **measurements**.

What it NEVER does: invent a memory, delete evidence, hard-delete an object, or change a
confidence / score / the Governor / OmiScore. Merging is append-only in spirit — observation
rows are re-pointed (not copied, not deleted) and the now-empty duplicate is flagged
``superseded`` (kept for audit; archived to a non-retrievable tier by the next consolidation
pass). A pure function of ``(store, now)`` — fully replayable.

Two active objects are duplicates iff they share ``(type, exact signature set, control-status)``.
The canonical is the **lowest id** in the group (stable, deterministic); every other member is
merged into it. Redundancy is neutralized at the *aggregate* level (independence-key dedup
already prevents double-counting) — observations are retained, never removed.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class CompressionReport:
    """The deterministic outcome of a compression pass."""

    total_before: int
    active_before: int
    groups: int
    duplicate_groups: int
    merges: list = field(default_factory=list)        # [{canonical, merged:[ids], observations_moved}]
    duplicates_merged: int = 0
    observations_merged: int = 0
    redundant_observations: int = 0                    # measurement: obs that add no independent support
    obsolete: list = field(default_factory=list)       # retired/superseded ids (measurement, not deleted)
    active_after: int = 0
    compression_ratio: float = 1.0                     # active_after / active_before (lower = denser)
    ran_at: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def _group_key(ko: Any) -> tuple:
    """Equivalence class for compression: same type, exact signature set, same control-status."""
    return (ko.type, frozenset(ko.signature), bool(ko.is_control))


def _redundant_observations(ko: Any) -> int:
    """Observations on ``ko`` that repeat an existing ``(independence_key|investigation, stance)`` —
    they're retained for audit but add no independent support, so they're pure density. Measurement
    only; nothing is removed."""
    seen: set[tuple] = set()
    redundant = 0
    for e in ko.ledger:
        key = (e.independence_key or e.investigation, e.stance)
        if key in seen:
            redundant += 1
        else:
            seen.add(key)
    return redundant


def compression_potential(store: Any, *, now: datetime | None = None) -> dict:
    """Read-only measurement: how much *denser* a compression pass COULD make the store, without
    mutating anything. Counts duplicate equivalence groups, the objects that would be merged away,
    and the redundant observations — the dashboard's compression view. Deterministic."""
    active = sorted(store.all(), key=lambda k: k.id)
    groups: dict[tuple, list] = {}
    for ko in active:
        groups.setdefault(_group_key(ko), []).append(ko)
    dup_groups = [m for m in groups.values() if len(m) > 1]
    mergeable = sum(len(m) - 1 for m in dup_groups)
    redundant = sum(_redundant_observations(k) for k in active)
    return {
        "active": len(active),
        "groups": len(groups),
        "duplicate_groups": len(dup_groups),
        "mergeable_objects": mergeable,
        "redundant_observations": redundant,
        "projected_active_after": len(active) - mergeable,
        "projected_ratio": round((len(active) - mergeable) / len(active), 4) if active else 1.0,
    }


def compress(store: Any, *, now: datetime | None = None) -> CompressionReport:
    """Run one compression pass: merge equivalent duplicates into a canonical object (denser, not
    larger), preserving every observation's provenance, and report density measurements.
    Deterministic given ``(store, now)``. Idempotent — re-running on a compressed store merges
    nothing (each group already has a single active object)."""
    active = sorted(store.all(), key=lambda k: k.id)              # non-superseded
    active_before = len(active)
    total_before = len(store.all(include_superseded=True))

    groups: dict[tuple, list] = {}
    for ko in active:
        groups.setdefault(_group_key(ko), []).append(ko)

    merges: list[dict] = []
    duplicates_merged = 0
    observations_merged = 0
    duplicate_groups = 0
    for _key, members in sorted(groups.items(), key=lambda kv: min(k.id for k in kv[1])):
        if len(members) < 2:
            continue
        duplicate_groups += 1
        members_sorted = sorted(members, key=lambda k: k.id)
        canonical = members_sorted[0]
        merged_ids: list[str] = []
        moved = 0
        for dup in members_sorted[1:]:
            moved += store.merge_into(canonical.id, dup.id)
            merged_ids.append(dup.id)
            duplicates_merged += 1
        observations_merged += moved
        merges.append({"canonical": canonical.id, "merged": merged_ids, "observations_moved": moved})

    # measurements over the post-merge corpus (no mutation): density + obsolescence.
    redundant = sum(_redundant_observations(k) for k in store.all())
    obsolete = sorted(
        k.id for k in store.all(include_superseded=True)
        if k.superseded_by or k.retireable(now)
    )

    active_after = len(store.all())
    return CompressionReport(
        total_before=total_before, active_before=active_before, groups=len(groups),
        duplicate_groups=duplicate_groups, merges=merges, duplicates_merged=duplicates_merged,
        observations_merged=observations_merged, redundant_observations=redundant, obsolete=obsolete,
        active_after=active_after,
        compression_ratio=round(active_after / active_before, 4) if active_before else 1.0,
        ran_at=(now or datetime.now(timezone.utc)).isoformat(),
    )
