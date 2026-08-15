"""Campaign intelligence — materialize detected coordination clusters as
first-class, EVOLVING assets.

Principle (per directive): store EVIDENCE and OBSERVATIONS, not verdicts as
truth. Each detection appends a :class:`CampaignObservation`; the campaign's
aggregate fields are recomputed from its observations + members, so later
evidence can change the picture. No boolean "this is a manipulation campaign" is
ever stored — only the observed coordination score, the corroborating detector
methods, the participating accounts, and the evidence strings.

This fills the gap the audit found: the per-scan pipeline computed coordination
clusters and then discarded the cluster-shaped object, keeping only pairwise
``CoordinationEdge`` rows and a scalar ``coordination_score``. Here the cluster
becomes a durable, queryable, recurring record.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.storage.models import Campaign, CampaignMember, CampaignObservation

_TAG_RE = re.compile(r"[#@]\w{2,}")
_MIN_MEMBERS = 3          # a campaign needs at least 3 coordinated accounts
_MATCH_JACCARD = 0.30     # member-overlap to count as the SAME recurring campaign
_MATCH_MIN_SHARED = 3
_EVIDENCE_CAP = 8
_TAG_CAP = 25


@dataclass
class _Component:
    """A coordinated account group = clusters merged by shared membership."""
    members: set[str]
    methods: set[str] = field(default_factory=set)
    score: float = 0.0
    evidence: list[str] = field(default_factory=list)


def merge_clusters(clusters) -> list[_Component]:
    """Merge the per-detector clusters that share accounts into connected
    components — the actual coordinated groups (one campaign candidate each)."""
    comps: list[_Component] = []
    for cl in clusters:
        members = {m for m in cl.members}
        if len(members) < 2:
            continue
        comps.append(_Component(members=members, methods={cl.method},
                                score=float(cl.score or 0.0),
                                evidence=list(cl.evidence or [])))
    # Fixpoint-merge overlapping components (small N per scan).
    changed = True
    while changed:
        changed = False
        for i in range(len(comps)):
            for j in range(i + 1, len(comps)):
                if comps[i].members & comps[j].members:
                    comps[i].members |= comps[j].members
                    comps[i].methods |= comps[j].methods
                    comps[i].score = max(comps[i].score, comps[j].score)
                    comps[i].evidence.extend(comps[j].evidence)
                    del comps[j]
                    changed = True
                    break
            if changed:
                break
    return comps


class CampaignService:
    def __init__(self, session: Session):
        self.s = session

    # -- public ------------------------------------------------------------
    def record_clusters(self, *, platform: str, context_id: str | None,
                        clusters, coordination_score: float,
                        confidence: float | None = None,
                        texts_by_account: dict[str, list[str]] | None = None,
                        handles: dict[str, str] | None = None,
                        signature: list[int] | None = None) -> list[Campaign]:
        """Persist each coordinated group as a campaign (recurring or new).

        Caller should gate on a trustworthy verdict (e.g. corroboration-gated
        ``coordination_score >= 0.5``) so clean scans don't manufacture
        campaigns — consistent with the Phase 3 precision work.
        """
        handles = handles or {}
        out: list[Campaign] = []
        for comp in merge_clusters(clusters):
            if len(comp.members) < _MIN_MEMBERS:
                continue
            tags = self._tags_for(comp.members, texts_by_account or {})
            conf = confidence if confidence is not None else min(1.0, 0.4 + 0.2 * len(comp.methods))
            camp = self._match_or_create(
                platform, comp, coordination_score, conf, tags, signature=signature,
            )
            self._observe(camp, platform, context_id, comp, coordination_score)
            self._upsert_members(camp, platform, comp, handles)
            self._recompute(camp, comp, coordination_score, tags)
            out.append(camp)
        if out:
            self.s.flush()
        return out

    # -- internals ---------------------------------------------------------
    def _tags_for(self, members, texts_by_account) -> dict[str, list[str]]:
        hashtags, mentions = set(), set()
        for acc in members:
            for t in texts_by_account.get(acc, []):
                for tok in _TAG_RE.findall(t or ""):
                    (hashtags if tok[0] == "#" else mentions).add(tok.lower())
        return {"hashtags": sorted(hashtags)[:_TAG_CAP],
                "mentions": sorted(mentions)[:_TAG_CAP]}

    def _name(self, platform: str, comp: _Component, tags: dict) -> str:
        top = (tags["hashtags"][:1] or tags["mentions"][:1])
        label = top[0] if top else "+".join(sorted(comp.methods)[:2]) or "cluster"
        return f"{platform} coordination · {label} · {len(comp.members)} accounts"

    def _match_or_create(self, platform, comp, score, conf, tags, signature=None) -> Campaign:
        """Match an existing operation, or mint one.

        Order matters. Member overlap first: the same accounts reappearing is the cheapest and most
        certain link. Then behavioural signature: an operation that has burned every account it used
        shares NO members with its own previous run, so overlap cannot see it and this is the only
        thing that can. Then create.

        Without the signature step the system reports a first sighting every time an operation
        rotates, which is exactly backwards, because rotating is what the sophisticated ones do.
        """
        rows = self.s.execute(
            select(CampaignMember.campaign_id, CampaignMember.account_external_id)
            .where(CampaignMember.platform == platform,
                   CampaignMember.account_external_id.in_(comp.members))
        ).all()
        by_camp: dict[int, set[str]] = {}
        for cid, acc in rows:
            by_camp.setdefault(cid, set()).add(acc)

        best, best_j = None, 0.0
        for cid, accs in sorted(by_camp.items()):
            camp = self.s.get(Campaign, cid)
            if camp is None:
                continue
            shared = len(accs)
            union = max(1, camp.member_count + len(comp.members) - shared)
            j = shared / union
            # `jaccard >= 0.30 OR shared >= 3` is right while a campaign is small and wrong once it
            # is large: three shared accounts would link a 5-account cluster to a 500-account
            # campaign at j = 0.006, and every later cluster would fall into the same one.
            from app.campaigns.tracking.operations import LARGE_CAMPAIGN_MEMBERS

            if (camp.member_count or 0) >= LARGE_CAMPAIGN_MEMBERS:
                accept = j >= _MATCH_JACCARD
            else:
                accept = j >= _MATCH_JACCARD or shared >= _MATCH_MIN_SHARED
            if accept and j >= best_j:
                best, best_j = camp, j
        if best is not None:
            return best

        if signature:
            try:
                from app.campaigns.tracking.operations import find_by_signature

                matched = find_by_signature(self.s, signature)
                if matched is not None:
                    return matched
            except Exception:  # noqa: BLE001 - a failed lookup must not block recording
                pass

        camp = Campaign(
            campaign_key=uuid.uuid4().hex[:16],
            name=self._name(platform, comp, tags),
            platform=platform,
            coordination_score=score, max_coordination_score=score, confidence=conf,
            member_count=0, observation_count=0,
            methods_json=sorted(comp.methods),
            hashtags_json=tags["hashtags"], mentions_json=tags["mentions"],
            evidence_json=comp.evidence[:_EVIDENCE_CAP], theme=None, status="observed",
        )
        self.s.add(camp)
        self.s.flush()
        return camp

    def _observe(self, camp, platform, context_id, comp, score) -> None:
        self.s.add(CampaignObservation(
            campaign_id=camp.id, platform=platform, context_id=context_id,
            coordination_score=score, member_count=len(comp.members),
            methods_json=sorted(comp.methods), evidence_json=comp.evidence[:_EVIDENCE_CAP],
            member_ids_json=sorted(comp.members),
        ))

    def _upsert_members(self, camp, platform, comp, handles) -> None:
        existing = {m.account_external_id: m for m in self.s.execute(
            select(CampaignMember).where(CampaignMember.campaign_id == camp.id)
        ).scalars()}
        from app.storage.models import _utcnow
        now = _utcnow()
        for acc in comp.members:
            m = existing.get(acc)
            if m is None:
                self.s.add(CampaignMember(
                    campaign_id=camp.id, platform=platform, account_external_id=acc,
                    handle=handles.get(acc), times_observed=1,
                    methods_json=sorted(comp.methods),
                ))
            else:
                m.times_observed += 1
                m.last_seen_at = now
                m.methods_json = sorted(set(m.methods_json or []) | comp.methods)
                if handles.get(acc):
                    m.handle = handles[acc]

    def _recompute(self, camp, comp, score, tags) -> None:
        from app.storage.models import _utcnow
        camp.member_count = self.s.query(CampaignMember).filter(
            CampaignMember.campaign_id == camp.id).count()
        camp.observation_count = self.s.query(CampaignObservation).filter(
            CampaignObservation.campaign_id == camp.id).count()
        camp.coordination_score = score
        camp.max_coordination_score = max(camp.max_coordination_score, score)
        camp.methods_json = sorted(set(camp.methods_json or []) | comp.methods)
        camp.hashtags_json = sorted(set(camp.hashtags_json or []) | set(tags["hashtags"]))[:_TAG_CAP]
        camp.mentions_json = sorted(set(camp.mentions_json or []) | set(tags["mentions"]))[:_TAG_CAP]
        if comp.evidence and not camp.evidence_json:
            camp.evidence_json = comp.evidence[:_EVIDENCE_CAP]
        camp.status = "recurring" if camp.observation_count > 1 else "observed"
        camp.last_seen_at = now if (now := _utcnow()) else camp.last_seen_at
