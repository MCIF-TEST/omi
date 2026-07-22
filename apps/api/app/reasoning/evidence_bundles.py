"""Canonical per-stage Evidence Bundles (Phase P3.0).

The desired AI-native architecture gives **every reasoning stage its own canonical Evidence Bundle**
— not one investigation blob. This module defines those seven immutable bundles and their
deterministic builders. It is the pure evidence substrate the future per-stage reasoning will
consume; it builds no prompt, calls no model, and changes no runtime behaviour or output.

Each bundle:

* is **immutable** (frozen dataclass, tuple fields, nested frozen items — no mutable dicts),
* is **deterministic** and **content-addressed** (``bundle_id`` = a hash of its evidence only),
* is **hashable** + **serializable** (``to_dict``) + **independently testable**,
* carries **only the evidence its stage needs** — no presentation, no UI, no prose, no AI text,
* references shared entities by stable id (pseudonymous ``sub_*`` account refs, ``cl:`` cluster
  refs, and ``eb:`` bundle ids) so no field or cluster is duplicated across bundles.

The seven bundles form a DAG: the six stage bundles are leaves; the InvestigationSummaryBundle is
the root that references the other six by ``bundle_id`` (content-addressed composition).

Source of truth: the deterministic :class:`InvestigationContext` (Phase P1.0) — already the
canonical assembly of every deterministic Omi output. The builders *project* per-stage slices of it,
so nothing is re-extracted and the deterministic engine is untouched.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from app.evidence.bundle import digest
from app.reasoning.context.investigation import InvestigationContext

EVIDENCE_BUNDLE_SCHEMA_VERSION = 1


class _BundleMixin:
    """Content-addressing + serialization for a frozen evidence bundle. Adds no dataclass fields —
    ``asdict`` serializes only the bundle's own evidence fields, so ``bundle_id`` is a pure function
    of the evidence."""

    def _content(self) -> dict[str, Any]:
        return asdict(self)  # type: ignore[arg-type]

    def bundle_id(self) -> str:
        return digest(self._content(), prefix="eb:")

    def to_dict(self) -> dict[str, Any]:
        return {**self._content(), "bundle_id": self.bundle_id()}


# --------------------------------------------------------------------------- #
# Nested evidence items (frozen — immutable + hashable)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class CommentItem:
    author_ref: str
    text: str
    created_at: str | None = None
    parent_ref: str | None = None


@dataclass(frozen=True)
class CommenterHistoryItem:
    author_ref: str
    activity_sample_count: int = 0
    matched_prior_neighbors: int = 0
    from_cache: bool = False


@dataclass(frozen=True)
class SignalItem:
    name: str                          # detector identity — preserved so the AI can weigh disagreement
    probability: float = 0.0
    confidence: float = 0.0
    supplemental: bool = False
    evidence: tuple[str, ...] = ()     # the detector's factual justification lines (provenance)


@dataclass(frozen=True)
class ContributionItem:
    name: str                          # detector identity
    impact: float = 0.0
    direction: str = "neutral"
    supplemental: bool = False
    logit_delta: float = 0.0           # how much this detector moved the score (measurement)
    decorrelation_factor: float = 1.0  # correlation down-weighting applied (measurement)
    evidence: str = ""                 # provenance string for the contribution


@dataclass(frozen=True)
class OmiScoreItem:
    # OmiScore is a deterministic INDEX (measurement). risk_level — a heuristic band/classification —
    # is NOT projected as evidence (it would tell the model a conclusion); only the numeric index rides.
    omi_score: float | None = None
    authenticity_score: float | None = None


@dataclass(frozen=True)
class RawPostItem:
    """One raw post/comment by an account — text + time only, the model reads the actual content."""
    text: str = ""
    created_at: str | None = None


@dataclass(frozen=True)
class AccountItem:
    author_ref: str
    # --- RAW METADATA (AI-first): the objective collected facts the model reasons from. No score. ---
    follower_count: int | None = None
    following_count: int | None = None
    account_created_at: str | None = None
    post_count: int | None = None
    recent_posts: tuple[RawPostItem, ...] = ()
    # --- COMPUTED engine fields: retained for OTHER features (alerts/campaigns) but NOT rendered to the
    #     model — the AI produces its own per-account score from the raw metadata above. ---
    overall_probability: float = 0.0
    coordination_adjusted_probability: float | None = None
    tier: str = "low"
    confidence: float = 0.0
    signals: tuple[SignalItem, ...] = ()
    contributions: tuple[ContributionItem, ...] = ()
    weak_signals: tuple[str, ...] = ()
    omiscore: OmiScoreItem | None = None


@dataclass(frozen=True)
class MemoryPriorItem:
    type: str
    label: str
    confidence: float = 0.0
    influence_class: str = ""
    epistemic_status: str = ""


@dataclass(frozen=True)
class NarrativeItem:
    narrative_ref: str
    member_count: int = 0
    distinct_authors: int = 0
    spread_ratio: float | None = None
    inauthenticity_score: float | None = None


@dataclass(frozen=True)
class ClusterItem:
    cluster_ref: str          # content id of the cluster (stable across bundles)
    method: str
    member_refs: tuple[str, ...] = ()
    members_count: int = 0
    score: float = 0.0
    discriminative: bool = False
    evidence: tuple[str, ...] = ()


@dataclass(frozen=True)
class GraphEdgeItem:
    type: str
    from_ref: str
    to_ref: str


@dataclass(frozen=True)
class CrossLinkItem:
    kind: str
    severity: str = "info"
    evidence: tuple[str, ...] = ()
    related_refs: tuple[str, ...] = ()


@dataclass(frozen=True)
class CoordinationDigestItem:
    """Investigation-level coordination EVIDENCE (a digest — the clusters themselves are owned by the
    Coordination bundle). Pure measured numbers: score, tier, the single-axis-cap state, which
    discriminative methods fired, and how many clusters. No verdict, no prose."""

    coordination_score: float = 0.0
    coordination_tier: str = "low"
    single_axis_capped: bool = False
    discriminative_methods: tuple[str, ...] = ()
    cluster_count: int = 0


@dataclass(frozen=True)
class AccountsDigestItem:
    """Investigation-level account roll-up EVIDENCE (the per-account detail is owned by the Account
    bundle). Pure measured counts + probabilities — how many accounts, how many reach each suspicion
    band, and the peak/mean engine probability. No verdict, no prose."""

    count: int = 0
    flagged_count: int = 0          # tier in {moderate, elevated, high}
    high_count: int = 0             # tier == high
    max_probability: float = 0.0
    mean_probability: float = 0.0


# --------------------------------------------------------------------------- #
# The seven canonical stage bundles
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class CommentEvidenceBundle(_BundleMixin):
    """Stage: comment analysis. Owns the comment-section content (pseudonymous authors) + the
    thread-level engine signal."""

    stage: str = "comment_analysis"
    schema_version: int = EVIDENCE_BUNDLE_SCHEMA_VERSION
    comments: tuple[CommentItem, ...] = ()
    thread_probability: float | None = None
    thread_tier: str | None = None
    comment_count: int = 0


@dataclass(frozen=True)
class CommenterHistoryBundle(_BundleMixin):
    """Stage: commenter history analysis. Owns each commenter's posting *track record* — history
    volume, memory-neighbour recurrence, cache provenance. (Detector signals live in the Account
    bundle; comment text lives in the Comment bundle — joined by ``author_ref``.)"""

    stage: str = "commenter_history"
    schema_version: int = EVIDENCE_BUNDLE_SCHEMA_VERSION
    commenters: tuple[CommenterHistoryItem, ...] = ()
    count: int = 0


@dataclass(frozen=True)
class AccountEvidenceBundle(_BundleMixin):
    """Stage: account analysis. Owns per-account authenticity evidence — detector signals, signed
    contributions, OmiScore, weak signals, intent code — plus account-level institutional memory."""

    stage: str = "account_analysis"
    schema_version: int = EVIDENCE_BUNDLE_SCHEMA_VERSION
    accounts: tuple[AccountItem, ...] = ()
    memory_priors: tuple[MemoryPriorItem, ...] = ()
    count: int = 0


@dataclass(frozen=True)
class NarrativeEvidenceBundle(_BundleMixin):
    """Stage: narrative analysis. Owns message-cluster evidence (spread, authorship,
    inauthenticity). Populated when the Narrative store is linked to the investigation (a P1.2
    completeness item) — typed but empty until then."""

    stage: str = "narrative_analysis"
    schema_version: int = EVIDENCE_BUNDLE_SCHEMA_VERSION
    narratives: tuple[NarrativeItem, ...] = ()
    count: int = 0


@dataclass(frozen=True)
class CoordinationEvidenceBundle(_BundleMixin):
    """Stage: coordination analysis. Owns the cross-account coordination evidence — every detector
    cluster (with a stable ``cluster_ref``), the corroboration state, and the batch graph edges."""

    stage: str = "coordination_analysis"
    schema_version: int = EVIDENCE_BUNDLE_SCHEMA_VERSION
    coordination_score: float = 0.0
    coordination_tier: str = "low"
    single_axis_capped: bool = False
    discriminative_methods: tuple[str, ...] = ()
    clusters: tuple[ClusterItem, ...] = ()
    graph_edges: tuple[GraphEdgeItem, ...] = ()
    cluster_count: int = 0


@dataclass(frozen=True)
class CampaignEvidenceBundle(_BundleMixin):
    """Stage: campaign analysis. Owns the *materialization* evidence — which coordination clusters
    are corroboration-gated (score >= 0.5) campaign candidates. References the clusters by
    ``cluster_ref`` (the cluster data itself is owned by the Coordination bundle — no duplication)."""

    stage: str = "campaign_analysis"
    schema_version: int = EVIDENCE_BUNDLE_SCHEMA_VERSION
    candidate_cluster_refs: tuple[str, ...] = ()
    count: int = 0


@dataclass(frozen=True)
class InvestigationSummaryBundle(_BundleMixin):
    """Stage: investigation synthesis. The DAG root — owns investigation-level evidence (echoed
    overall numbers, inputs, post identity, cross-links) and references the six stage bundles by
    ``bundle_id`` (content-addressed composition)."""

    stage: str = "investigation_summary"
    schema_version: int = EVIDENCE_BUNDLE_SCHEMA_VERSION
    overall_probability: float = 0.0
    overall_tier: str = "low"
    confidence: float = 0.0
    convergence_score: float = 0.0
    inputs_provided: tuple[str, ...] = ()
    post_content_id: str | None = None
    platform: str = "unknown"
    cross_links: tuple[CrossLinkItem, ...] = ()
    # --- P3.4 enrichment — the investigation-synthesis EVIDENCE the AI Investigation Summary stage
    # reasons over. Per the doctrine "the deterministic system measures evidence; the AI reasons over
    # evidence", these are pure measured signals (no prose, no verdict): the coordination digest, the
    # signed contribution drivers, the account roll-up, data-quality caveats, and institutional-memory
    # context. Additive — the six ``component_bundle_ids`` DAG references are retained unchanged.
    coordination: CoordinationDigestItem | None = None
    contributions: tuple[ContributionItem, ...] = ()
    accounts_digest: AccountsDigestItem | None = None
    weak_signals: tuple[str, ...] = ()
    memory_priors: tuple[MemoryPriorItem, ...] = ()
    # (stage, bundle_id) pairs — a hashable, deterministic map of the six referenced stage bundles.
    component_bundle_ids: tuple[tuple[str, str], ...] = ()

    def component_map(self) -> dict[str, str]:
        return dict(self.component_bundle_ids)


# --------------------------------------------------------------------------- #
# Deterministic builders — project per-stage slices of the InvestigationContext
# --------------------------------------------------------------------------- #
def _cluster_item(c) -> ClusterItem:
    """One ClusterItem with a stable content id (so Coordination + Campaign reference the same
    cluster without copying it)."""
    member_refs = tuple(c.get("member_refs", ()))
    ref = digest({"method": c.get("method"), "members": list(member_refs),
                  "score": c.get("score")}, prefix="cl:")
    return ClusterItem(
        cluster_ref=ref, method=str(c.get("method") or ""), member_refs=member_refs,
        members_count=int(c.get("members_count") or 0), score=float(c.get("score") or 0.0),
        discriminative=bool(c.get("discriminative")), evidence=tuple(c.get("evidence", ())),
    )


def build_comment_bundle(ctx: InvestigationContext) -> CommentEvidenceBundle:
    c = ctx.comments
    return CommentEvidenceBundle(
        comments=tuple(CommentItem(author_ref=s.author_ref, text=s.text, created_at=s.created_at,
                                   parent_ref=s.parent_ref) for s in c.samples),
        thread_probability=c.thread_probability, thread_tier=c.thread_tier,
        comment_count=c.sample_count,
    )


def build_commenter_history_bundle(ctx: InvestigationContext) -> CommenterHistoryBundle:
    items = tuple(
        CommenterHistoryItem(author_ref=a.ref, activity_sample_count=a.activity_sample_count,
                             matched_prior_neighbors=a.matched_prior_neighbors, from_cache=a.from_cache)
        for a in ctx.accounts.accounts
    )
    return CommenterHistoryBundle(commenters=items, count=len(items))


def build_account_bundle(ctx: InvestigationContext) -> AccountEvidenceBundle:
    omi_by_ref = {s.get("ref"): s for s in ctx.omiscore.scores}
    accounts = []
    for a in ctx.accounts.accounts:
        o = omi_by_ref.get(a.ref)
        accounts.append(AccountItem(
            author_ref=a.ref,
            follower_count=a.follower_count, following_count=a.following_count,
            account_created_at=a.account_created_at, post_count=a.post_count,
            recent_posts=tuple(RawPostItem(text=p.text, created_at=p.created_at) for p in a.recent_posts),
            overall_probability=a.overall_probability,
            coordination_adjusted_probability=a.coordination_adjusted_probability,
            tier=a.tier, confidence=a.confidence,
            signals=tuple(SignalItem(name=s.name, probability=s.probability, confidence=s.confidence,
                                     supplemental=s.supplemental, evidence=s.evidence) for s in a.signals),
            contributions=tuple(ContributionItem(name=k.name, impact=k.impact, direction=k.direction,
                                                 supplemental=k.supplemental, logit_delta=k.logit_delta,
                                                 decorrelation_factor=k.decorrelation_factor,
                                                 evidence=k.evidence) for k in a.contributions),
            weak_signals=a.weak_signals,
            omiscore=(OmiScoreItem(omi_score=o.get("omi_score"),
                                   authenticity_score=o.get("authenticity_score")) if o else None),
        ))
    priors = tuple(MemoryPriorItem(type=p.type, label=p.label, confidence=p.confidence,
                                   influence_class=p.influence_class, epistemic_status=p.epistemic_status)
                   for p in ctx.memory.priors)
    return AccountEvidenceBundle(accounts=tuple(accounts), memory_priors=priors, count=len(accounts))


def build_narrative_bundle(ctx: InvestigationContext) -> NarrativeEvidenceBundle:
    items = []
    for n in ctx.narratives.narratives:
        ref = digest({"label": n.get("label"), "members": n.get("member_count")}, prefix="nr:")
        items.append(NarrativeItem(
            narrative_ref=ref, member_count=int(n.get("member_count") or 0),
            distinct_authors=int(n.get("distinct_authors") or 0),
            spread_ratio=n.get("spread_ratio"), inauthenticity_score=n.get("inauthenticity_score"),
        ))
    return NarrativeEvidenceBundle(narratives=tuple(items), count=len(items))


def build_coordination_bundle(ctx: InvestigationContext) -> CoordinationEvidenceBundle:
    co = ctx.coordination
    clusters = tuple(_cluster_item(asdict(cl)) for cl in co.clusters)
    edges = tuple(GraphEdgeItem(type=e.type, from_ref=e.from_ref, to_ref=e.to_ref)
                  for e in ctx.graph.edges)
    return CoordinationEvidenceBundle(
        coordination_score=co.coordination_score, coordination_tier=co.coordination_tier,
        single_axis_capped=co.single_axis_capped, discriminative_methods=co.discriminative_methods,
        clusters=clusters, graph_edges=edges, cluster_count=len(clusters),
    )


def build_campaign_bundle(ctx: InvestigationContext) -> CampaignEvidenceBundle:
    # Campaign candidates are the corroboration-gated (>=0.5) clusters — referenced by cluster_ref,
    # not copied (the Coordination bundle owns the cluster data).
    refs = tuple(_cluster_item(asdict(cl)).cluster_ref for cl in ctx.campaigns.candidates)
    return CampaignEvidenceBundle(candidate_cluster_refs=refs, count=len(refs))


_FLAGGED_TIERS = {"moderate", "elevated", "high"}


def _coordination_digest(ctx: InvestigationContext) -> CoordinationDigestItem | None:
    """The investigation-level coordination EVIDENCE digest (numbers only; the clusters stay owned by
    the Coordination bundle). ``None`` when the engine surfaced no coordination section."""
    co = ctx.coordination
    if not co.present:
        return None
    return CoordinationDigestItem(
        coordination_score=co.coordination_score, coordination_tier=co.coordination_tier,
        single_axis_capped=co.single_axis_capped,
        discriminative_methods=tuple(co.discriminative_methods), cluster_count=co.cluster_count,
    )


def _summary_contributions(ctx: InvestigationContext) -> tuple[ContributionItem, ...]:
    """Surface the strongest signed drivers across the investigation's accounts as investigation-level
    EVIDENCE — the per-account contributions deduplicated by name (strongest |impact| kept), ordered
    deterministically, and capped. Pure surfacing: no score is recomputed and nothing is summed."""
    strongest: dict[str, ContributionItem] = {}
    for a in ctx.accounts.accounts:
        for k in a.contributions:
            cur = strongest.get(k.name)
            if cur is None or abs(k.impact) > abs(cur.impact):
                # Preserve the detector's measured provenance (logit_delta / decorrelation_factor /
                # evidence) so investigation-level surfacing never strips the disagreement signal.
                strongest[k.name] = ContributionItem(
                    name=k.name, impact=k.impact, direction=k.direction, supplemental=k.supplemental,
                    logit_delta=k.logit_delta, decorrelation_factor=k.decorrelation_factor,
                    evidence=k.evidence)
    ordered = sorted(strongest.values(), key=lambda c: (-abs(c.impact), c.name))
    return tuple(ordered[:8])


def _accounts_digest(ctx: InvestigationContext) -> AccountsDigestItem | None:
    """The investigation-level account roll-up EVIDENCE (counts + probabilities; per-account detail
    stays owned by the Account bundle). ``None`` when no accounts were assembled."""
    accounts = ctx.accounts.accounts
    if not accounts:
        return None
    probs = [a.overall_probability for a in accounts]
    return AccountsDigestItem(
        count=len(accounts),
        flagged_count=sum(1 for a in accounts if a.tier in _FLAGGED_TIERS),
        high_count=sum(1 for a in accounts if a.tier == "high"),
        max_probability=round(max(probs), 6), mean_probability=round(sum(probs) / len(probs), 6),
    )


def _summary_weak_signals(ctx: InvestigationContext) -> tuple[str, ...]:
    """Deduplicated data-quality caveats across the accounts — first-seen order (deterministic given
    the account order), capped. Evidence of what limits the read, never a verdict."""
    seen: list[str] = []
    for a in ctx.accounts.accounts:
        for w in a.weak_signals:
            if w not in seen:
                seen.append(w)
            if len(seen) >= 8:
                return tuple(seen)
    return tuple(seen)


def build_investigation_summary_bundle(
    ctx: InvestigationContext, *, components: dict[str, str] | None = None,
) -> InvestigationSummaryBundle:
    inv = ctx.investigation
    links = tuple(CrossLinkItem(kind=l.kind, severity=l.severity, evidence=l.evidence,
                                related_refs=l.related_refs) for l in ctx.cross_platform.links)
    priors = tuple(MemoryPriorItem(type=p.type, label=p.label, confidence=p.confidence,
                                   influence_class=p.influence_class, epistemic_status=p.epistemic_status)
                   for p in ctx.memory.priors)
    return InvestigationSummaryBundle(
        overall_probability=inv.overall_probability, overall_tier=inv.overall_tier,
        confidence=inv.confidence, convergence_score=inv.convergence_score,
        inputs_provided=inv.inputs_provided, post_content_id=ctx.post.content_id,
        platform=inv.platform, cross_links=links,
        coordination=_coordination_digest(ctx), contributions=_summary_contributions(ctx),
        accounts_digest=_accounts_digest(ctx), weak_signals=_summary_weak_signals(ctx),
        memory_priors=priors,
        component_bundle_ids=tuple(sorted((components or {}).items())),
    )


@dataclass(frozen=True)
class EvidenceBundleSet:
    """The seven canonical bundles for one investigation. The summary is the DAG root referencing
    the other six by ``bundle_id``."""

    comment: CommentEvidenceBundle
    commenter_history: CommenterHistoryBundle
    account: AccountEvidenceBundle
    narrative: NarrativeEvidenceBundle
    coordination: CoordinationEvidenceBundle
    campaign: CampaignEvidenceBundle
    summary: InvestigationSummaryBundle

    def stage_bundles(self) -> dict[str, _BundleMixin]:
        return {
            "comment_analysis": self.comment, "commenter_history": self.commenter_history,
            "account_analysis": self.account, "narrative_analysis": self.narrative,
            "coordination_analysis": self.coordination, "campaign_analysis": self.campaign,
            "investigation_summary": self.summary,
        }

    def to_dict(self) -> dict[str, Any]:
        return {name: b.to_dict() for name, b in self.stage_bundles().items()}


def build_evidence_bundles(context: InvestigationContext) -> EvidenceBundleSet:
    """Build all seven canonical stage bundles for one investigation. Deterministic + side-effect
    free; no prompt, no model, no runtime change. The summary references the six stage bundles by id.
    """
    comment = build_comment_bundle(context)
    commenter_history = build_commenter_history_bundle(context)
    account = build_account_bundle(context)
    narrative = build_narrative_bundle(context)
    coordination = build_coordination_bundle(context)
    campaign = build_campaign_bundle(context)
    components = {
        "comment_analysis": comment.bundle_id(), "commenter_history": commenter_history.bundle_id(),
        "account_analysis": account.bundle_id(), "narrative_analysis": narrative.bundle_id(),
        "coordination_analysis": coordination.bundle_id(), "campaign_analysis": campaign.bundle_id(),
    }
    summary = build_investigation_summary_bundle(context, components=components)
    return EvidenceBundleSet(
        comment=comment, commenter_history=commenter_history, account=account, narrative=narrative,
        coordination=coordination, campaign=campaign, summary=summary,
    )


__all__ = [
    "EVIDENCE_BUNDLE_SCHEMA_VERSION",
    "CoordinationDigestItem", "AccountsDigestItem",
    "CommentEvidenceBundle", "CommenterHistoryBundle", "AccountEvidenceBundle",
    "NarrativeEvidenceBundle", "CoordinationEvidenceBundle", "CampaignEvidenceBundle",
    "InvestigationSummaryBundle", "EvidenceBundleSet",
    "build_comment_bundle", "build_commenter_history_bundle", "build_account_bundle",
    "build_narrative_bundle", "build_coordination_bundle", "build_campaign_bundle",
    "build_investigation_summary_bundle", "build_evidence_bundles",
]
