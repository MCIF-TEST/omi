"""The operation registry: resolving a finding to the operator behind it.

`persist.py` stores findings. This stores OPERATIONS, and the difference is the whole point. Two
findings a month apart, on different posts, in different customers' investigations, with not one
account in common, can be the same adversary running its second campaign. A finding store says
"two findings". A registry says "one operation, seen twice, which rotated every account".

---------------------------------------------------------------------------------------------------
RESOLUTION ORDER, AND WHY IT IS NOT JUST MEMBER OVERLAP
---------------------------------------------------------------------------------------------------

1. **Member overlap.** Cheapest and strongest when it applies. It applies to a re-scan, a
   continuation batch, or a campaign that reused accounts.
2. **Profile similarity.** The case member overlap is blind to, and the case that matters: a serious
   operation burns its accounts, so overlap is exactly zero precisely when the adversary is
   competent. Weighted Jaccard over the discriminative profile catches it.
3. **Create.** A formation nobody has seen before.

MEASURED SEPARATION for step 2, across five profiles learned from two operators: the same operator
scored 0.356 to 0.770 across different runs and different organic backgrounds, while different
operators scored 0.022 to 0.036. The threshold sits between, an order of magnitude clear of the
top of the wrong distribution, and it is deliberately looser than
`tracking/signature.SIGNATURE_MATCH_THRESHOLD` (0.40) because that value would have missed the
worst genuine match at 0.356.

---------------------------------------------------------------------------------------------------
WHAT THIS DOES NOT DO
---------------------------------------------------------------------------------------------------

Recording an operation is not publishing one, exactly as recording a finding is not. No share token,
no `Campaign` row, nothing on a customer surface. The registry is an internal memory that makes the
next finding better informed, and a place for an operator to say "this one is real" or "this is a
newsroom" once, rather than once per run.
"""

from __future__ import annotations

import logging
import secrets
from datetime import datetime, timezone

from sqlalchemy import select

from app.netdetect.formation import (
    Composition,
    FormationProfile,
    ProfileFeature,
    build_profile,
    composition_of,
    merge_profiles,
    phase_of,
    profile_similarity,
)
from app.netdetect.significance import Corpus
from app.netdetect.types import Candidate
from app.storage.models import NetdetectFormation

logger = logging.getLogger("omi.netdetect.registry")

#: Weighted-Jaccard profile similarity at which two findings are the same operator. See the module
#: docstring for the measurement this sits inside.
FORMATION_MATCH_THRESHOLD = 0.20

#: Formations compared against a new finding in one resolution pass. Ordered most-recently-seen
#: first, because an operation seen last week is a likelier match than one dormant for a year, and
#: an unbounded scan would make recording a finding cost more as the registry grows.
MAX_CANDIDATES = 200


def _now() -> datetime:
    return datetime.now(timezone.utc)


def profile_from_row(row: NetdetectFormation) -> FormationProfile:
    """Rebuild the in-memory profile from a stored row."""
    features = [
        ProfileFeature(
            family=str(f.get("family") or ""),
            kind=str(f.get("kind") or ""),
            value=str(f.get("value") or ""),
            surprise=float(f.get("surprise") or 0.0),
            prevalence=float(f.get("prevalence") or 1.0),
        )
        for f in (row.profile_json or [])
        if isinstance(f, dict)
    ]
    return FormationProfile(
        features=features,
        families={f.family for f in features},
        corpus_size=0,
    )


def _profile_to_json(profile: FormationProfile) -> list[dict]:
    return [
        {
            "family": f.family, "kind": f.kind, "value": f.value,
            "surprise": f.surprise, "prevalence": f.prevalence,
        }
        for f in profile.features
    ]


def _composition_to_json(comp: Composition) -> dict:
    return {
        "scored": comp.scored, "unscored": comp.unscored,
        "median": comp.median, "minimum": comp.minimum, "maximum": comp.maximum,
        "posture": comp.posture, "note": comp.note, "concealment": comp.concealment,
    }


def load_profiles(session, *, limit: int = MAX_CANDIDATES,
                  include_dismissed: bool = False) -> dict[str, FormationProfile]:
    """Every known formation's identity, for assigning accounts against.

    Dismissed formations are excluded by default: somebody has already said this is not an
    operation, and continuing to assign accounts to it would keep making a claim they refused.
    """
    stmt = select(NetdetectFormation)
    if not include_dismissed:
        stmt = stmt.where(NetdetectFormation.status != "dismissed")
    rows = list(session.execute(
        stmt.order_by(NetdetectFormation.last_seen.desc().nullslast()).limit(limit)
    ).scalars())
    return {r.formation_key: profile_from_row(r) for r in rows}


def resolve(session, profile: FormationProfile, members: list[str],
            *, platform: str) -> tuple[NetdetectFormation | None, str, float]:
    """Find the operation this finding belongs to.

    Returns ``(row, how, similarity)`` where ``how`` is "members", "profile" or "new". The reason is
    carried rather than inferred because "we recognised the accounts" and "we recognised the
    behaviour despite every account being new" are very different claims about an adversary.
    """
    candidates = list(session.execute(
        select(NetdetectFormation)
        .where(NetdetectFormation.platform == platform)
        .order_by(NetdetectFormation.last_seen.desc().nullslast())
        .limit(MAX_CANDIDATES)
    ).scalars())

    member_set = set(members)
    for row in candidates:
        roster = set((row.members_json or {}).keys())
        if roster & member_set:
            return row, "members", 1.0

    best_row, best_sim = None, 0.0
    for row in candidates:
        sim = profile_similarity(profile_from_row(row), profile)
        if sim > best_sim:
            best_row, best_sim = row, sim
    if best_row is not None and best_sim >= FORMATION_MATCH_THRESHOLD:
        return best_row, "profile", round(best_sim, 4)
    return None, "new", round(best_sim, 4)


def record(session, candidate: Candidate, corpus: Corpus, *, platform: str,
           context_id: str | None, scores: list[float | None] | None = None,
           now: datetime | None = None) -> tuple[NetdetectFormation, str]:
    """Fold a finding into the registry, creating or updating the operation behind it.

    Returns ``(row, how)``. Never raises into the caller's run: a registry failure degrades FUTURE
    findings and must not turn a completed detection into an error for the operator reading it.
    """
    at = now or _now()
    profile = build_profile(candidate, corpus)
    members = sorted(candidate.members)

    row, how, similarity = resolve(session, profile, members, platform=platform)
    if row is None:
        row = NetdetectFormation(
            formation_key=secrets.token_hex(8),
            platform=platform,
            profile_json=[], families_json=[], members_json={},
            composition_json={}, contexts_json=[],
            first_seen=at, sighting_count=0,
        )
        session.add(row)
        merged = profile
    else:
        merged = merge_profiles(profile_from_row(row), profile)

    row.profile_json = _profile_to_json(merged)
    row.families_json = sorted(merged.families)

    roster = dict(row.members_json or {})
    stamp = at.isoformat()
    for member in members:
        entry = roster.get(member)
        if isinstance(entry, dict):
            entry["last_seen"] = stamp
        else:
            roster[member] = {"first_seen": stamp, "last_seen": stamp}
    row.members_json = roster
    row.member_count = len(roster)

    if scores is not None:
        row.composition_json = _composition_to_json(composition_of(scores))

    # ONLY A DISTINCT POST COUNTS AS A SIGHTING. Re-running the detector on one investigation, which
    # an operator does constantly while tuning, is the same observation arriving twice; counting it
    # would let anyone inflate an operation's history by pressing a button.
    contexts = list(row.contexts_json or [])
    if context_id and context_id not in contexts:
        contexts.append(context_id)
        row.contexts_json = contexts[:50]
        row.sighting_count = int(row.sighting_count or 0) + 1
        row.last_seen = at
    elif row.last_seen is None:
        row.last_seen = at

    previous = row.phase
    row.phase = phase_of(row.first_seen, row.last_seen, previous_phase=previous, now=at)
    if row.phase != previous:
        row.previous_phase = previous
    row.updated_at = at
    return row, how


def refresh_phases(session, *, now: datetime | None = None) -> int:
    """Re-derive every formation's phase.

    Needed because DORMANT IS A TRANSITION NOTHING TRIGGERS. A formation goes quiet by having no new
    sighting, which is the absence of an event, so no write ever happens to notice it. Without a
    sweep the registry would show a year-dead operation as active forever.
    """
    at = now or _now()
    changed = 0
    for row in session.execute(select(NetdetectFormation)).scalars():
        previous = row.phase
        nxt = phase_of(row.first_seen, row.last_seen, previous_phase=previous, now=at)
        if nxt != previous:
            row.previous_phase = previous
            row.phase = nxt
            row.updated_at = at
            changed += 1
    return changed
