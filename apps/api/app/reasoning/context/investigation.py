"""Investigation Context Builder (Phase P1.0) — the ONE authoritative evidence-assembly layer.

This is the single place investigation evidence is gathered and organized **before any inference
is performed**. It is a *pure, deterministic assembler*: it computes no score, runs no model,
constructs no prompt, calls no endpoint, and writes nothing. Given the same inputs it produces the
same content-addressed :class:`InvestigationContext`.

It does not re-extract evidence — it **reuses the existing deterministic collectors**:

* :class:`app.evidence.Binder` — the canonical, content-addressed Evidence Bundle (behavioral /
  detector / coordination / graph / narrative / metadata facets + epistemics). The Behavioral,
  Graph, and part of the Coordination sections are projected from it.
* :func:`app.memory.graph.retrieve` (+ :func:`app.memory.repository.get_memory_store`) — the exact
  institutional-memory retrieval the production analyst already uses. The Memory section reuses it.
* the engine's serialized investigation ``payload`` (``Investigation.payload_json`` — the same
  object ``assess_payload`` consumes) — the raw grain sections (Investigation / Post / Author /
  Comments / Accounts / Coordination / Campaigns / Cross-platform / Timing / Engagement) are
  projected from it.

The output is ONE typed :class:`InvestigationContext` with typed sections. It becomes the only
input into the (future) Prompt Builder. **This layer does not format anything into a prompt** — the
sections are structured evidence, nothing else.

Account identifiers are pseudonymized at the boundary (the same ``sub_`` scheme the Evidence Bundle
uses), so the context carries no raw handle / PII in its identifiers. (Redaction of PII *inside*
free-text comment bodies before they reach a model is a Prompt-Builder concern — see the deliverable
notes, not this layer.)
"""
from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from typing import Any

from app.evidence.binder import Binder
from app.evidence.bundle import DISCRIMINATIVE_METHODS, digest

INVESTIGATION_CONTEXT_VERSION = "ictx-v1"

# Bounds keep the assembled object finite regardless of scan size (mirrors the Binder's member cap).
# Phase 5H — full-investigation coverage. OmiSphere optimizes for investigation QUALITY over API cost, so
# the account/commenter ceiling is raised to carry EVERY commenter of a normal investigation (up to ~150,
# with headroom) into the evidence the AI reasons over — no upstream sampling. This is the single knob that
# governs how many commenters reach the model; raising it further (300/500/1000) needs no other change, and
# any residual overflow beyond the ceiling stays DISCLOSED via the sampling manifest (never silent).
_MAX_ACCOUNTS = 250
_MAX_COMMENT_SAMPLES = 250
_MAX_PER_ACCOUNT_SAMPLES = 4
_MAX_CLUSTERS = 40
_MAX_CROSS_LINKS = 40
_MAX_GRAPH_EDGES = 80
_MAX_BEHAVIORAL = 40
_MAX_MEMORY = 8

# The canonical, ordered section set. "for example" in the brief — implemented in full, with the
# responsibilities that the tree folds (timing / engagement / cross-platform / previous
# investigations) promoted to their own typed sections so *everything* is typed.
SECTION_ORDER = (
    "investigation", "post", "author", "comments", "accounts", "coordination", "narratives",
    "campaigns", "graph", "behavioral", "timing", "engagement", "cross_platform", "omiscore",
    "memory", "previous_investigations", "metadata",
)


def _pseudo(ref: str) -> str:
    """Stable pseudonymous reference — identical to the Evidence Bundle's scheme so refs
    cross-reference. The context never carries a raw handle / external id in its identifiers."""
    ref = ref or ""
    if ref.startswith("sub_"):
        return ref
    return "sub_" + hashlib.sha256(ref.encode("utf-8")).hexdigest()[:12]


# --------------------------------------------------------------------------- #
# Typed sections — each is structured evidence only (no prose, no prompt text)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Section:
    """Base for every typed section. ``present`` says whether real evidence was assembled for it
    (a section is always emitted, even when empty, so the shape is stable for the Prompt Builder)."""

    present: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class InvestigationSection(Section):
    ref: str = ""
    platform: str = "unknown"
    slug: str | None = None
    kind: str | None = None
    inputs_provided: tuple[str, ...] = ()
    overall_probability: float = 0.0
    overall_tier: str = "low"
    confidence: float = 0.0
    convergence_score: float = 0.0
    summary: str = ""
    quota_used: int = 0


@dataclass(frozen=True)
class PostSection(Section):
    """The content under investigation (the post / video). Title / publish-time / view stats are
    NOT carried on the scan payload — they require the content-intelligence collector (P1.2 gap)."""

    content_id: str | None = None
    platform: str = "unknown"
    title: str | None = None
    published_at: str | None = None
    metadata_available: bool = False


@dataclass(frozen=True)
class AuthorSection(Section):
    """The primary subject account of the investigation (the focus account, when one was scanned).
    For a comment-section investigation the post's uploader is not collected — ``present=False``."""

    ref: str | None = None
    platform: str = "unknown"
    overall_probability: float | None = None
    tier: str | None = None
    confidence: float | None = None
    # Ruling 3 (frozen architecture): intent_label / suspected_intent / reasons are heuristic
    # INTERPRETATIONS, not observations — they are no longer evidence and are not projected here. If
    # an intent label is needed for compatibility it is derived from the AI investigation AFTER
    # reasoning, never from the deterministic engine before it.
    follower_count: int | None = None
    history_size: int | None = None
    account_created_at: str | None = None


@dataclass(frozen=True)
class CommentSample(Section):
    author_ref: str = ""
    text: str = ""
    created_at: str | None = None
    parent_ref: str | None = None


@dataclass(frozen=True)
class CommentsSection(Section):
    thread_probability: float | None = None
    thread_tier: str | None = None
    sample_count: int = 0
    samples: tuple[CommentSample, ...] = ()


@dataclass(frozen=True)
class SignalEvidence(Section):
    name: str = ""              # detector identity — preserved so the AI weighs disagreement
    probability: float = 0.0
    confidence: float = 0.0
    supplemental: bool = False
    # Detector provenance — the detector's own factual justification lines. RESTORED (the projection
    # previously dropped these), so the model can cite the observation, not just the score.
    evidence: tuple[str, ...] = ()


@dataclass(frozen=True)
class ContributionEvidence(Section):
    name: str = ""              # detector identity
    impact: float = 0.0
    direction: str = "neutral"
    supplemental: bool = False
    headline: str = ""
    # Signed-contribution measurements — RESTORED (previously dropped): the logit contribution and the
    # correlation down-weighting are how much a detector moved the score, and why. Measurements, not
    # conclusions.
    logit_delta: float = 0.0
    decorrelation_factor: float = 1.0
    evidence: str = ""


@dataclass(frozen=True)
class RawPostSample(Section):
    """One raw post/comment by this account — the model reads the actual text + time (never a score)."""
    text: str = ""
    created_at: str | None = None


@dataclass(frozen=True)
class AccountEvidence(Section):
    ref: str = ""
    platform: str = "unknown"
    # --- RAW METADATA (AI-first): the objective, collected facts the model reasons from. No score. ---
    follower_count: int | None = None
    following_count: int | None = None
    account_created_at: str | None = None       # ISO timestamp — the model derives account age itself
    post_count: int | None = None               # size of this account's activity history
    recent_posts: tuple[RawPostSample, ...] = ()  # raw sample of this account's own posts (text + time)
    activity_sample_count: int = 0
    from_cache: bool = False
    matched_prior_neighbors: int = 0
    # --- COMPUTED engine fields (retained on the object for OTHER features — alerts/campaigns — but NO
    #     longer rendered to the model; the AI produces its own scores from the raw metadata above). ---
    overall_probability: float = 0.0
    coordination_adjusted_probability: float | None = None
    tier: str = "low"
    confidence: float = 0.0
    weak_signals: tuple[str, ...] = ()
    coordination_evidence: tuple[str, ...] = ()
    score_adjustments: tuple[str, ...] = ()
    signals: tuple[SignalEvidence, ...] = ()
    contributions: tuple[ContributionEvidence, ...] = ()


@dataclass(frozen=True)
class AccountsSection(Section):
    count: int = 0
    accounts: tuple[AccountEvidence, ...] = ()


@dataclass(frozen=True)
class ClusterEvidence(Section):
    method: str = ""
    members_count: int = 0
    member_refs: tuple[str, ...] = ()
    score: float = 0.0
    discriminative: bool = False
    evidence: tuple[str, ...] = ()


@dataclass(frozen=True)
class CoordinationSection(Section):
    coordination_score: float = 0.0
    coordination_tier: str = "low"
    single_axis_capped: bool = False
    discriminative_methods: tuple[str, ...] = ()
    cluster_count: int = 0
    clusters: tuple[ClusterEvidence, ...] = ()


@dataclass(frozen=True)
class CampaignsSection(Section):
    """Materialized-campaign candidates: the corroboration-gated (score >= 0.5) coordination
    clusters — exactly what ``scan_video_full`` Phase 5.5 persists as ``Campaign`` records."""

    count: int = 0
    candidates: tuple[ClusterEvidence, ...] = ()


@dataclass(frozen=True)
class NarrativesSection(Section):
    """Narrative (message-cluster) evidence lives in the Narrative store, not on the scan payload
    (it is ingested asynchronously). Hydrating it requires a session (P1.2 completeness gap)."""

    count: int = 0
    narratives: tuple[dict, ...] = ()


@dataclass(frozen=True)
class GraphEdge(Section):
    type: str = ""
    from_ref: str = ""
    to_ref: str = ""


@dataclass(frozen=True)
class GraphSection(Section):
    """Projected from the Evidence Bundle's normalized graph (member entities + typed edges)."""

    account_entities: int = 0
    relationship_count: int = 0
    member_refs: tuple[str, ...] = ()
    edges: tuple[GraphEdge, ...] = ()


@dataclass(frozen=True)
class BehavioralItem(Section):
    ev_id: str = ""
    detector: str = ""
    kind: str = ""
    direction: str = "neutral"
    impact: float = 0.0
    supplemental: bool = False


@dataclass(frozen=True)
class BehavioralSection(Section):
    """Projected from the Evidence Bundle's behavioral facet + epistemics (the deterministic
    evidence-of-record). Nothing recomputed — it references bundle ``ev:`` ids."""

    items: tuple[BehavioralItem, ...] = ()
    contradictions: tuple[dict, ...] = ()
    unknowns: tuple[dict, ...] = ()
    missing_evidence: tuple[dict, ...] = ()


@dataclass(frozen=True)
class TimingSection(Section):
    """Temporal evidence: the temporal detector's read (per subject) + whether timestamped
    activity is available. Derived from the payload's signals — nothing recomputed."""

    temporal_probability: float | None = None
    temporal_confidence: float | None = None
    accounts_with_temporal_signal: int = 0
    timestamped_activity_available: bool = False


@dataclass(frozen=True)
class EngagementSection(Section):
    """Engagement evidence: the engagement-farming detector read + co-engagement coordination."""

    engagement_probability: float | None = None
    engagement_confidence: float | None = None
    accounts_with_engagement_signal: int = 0
    co_engagement_clusters: int = 0


@dataclass(frozen=True)
class CrossLinkEvidence(Section):
    kind: str = ""
    severity: str = "info"
    summary: str = ""
    evidence: tuple[str, ...] = ()
    related_refs: tuple[str, ...] = ()


@dataclass(frozen=True)
class CrossPlatformSection(Section):
    """The interconnection layer — cross-links between the investigation's inputs (related account
    identifiers pseudonymized)."""

    count: int = 0
    links: tuple[CrossLinkEvidence, ...] = ()


@dataclass(frozen=True)
class OmiScoreSection(Section):
    """Per-account OmiScore verdicts. Composed from the per-account signals already in the payload
    by reusing the deterministic ``compute_omiscore`` collector (an index, never a new detection)."""

    count: int = 0
    scores: tuple[dict, ...] = ()


@dataclass(frozen=True)
class MemoryItem(Section):
    type: str = ""
    label: str = ""
    confidence: float = 0.0
    stability: float = 0.0
    epistemic_status: str = ""
    influence_class: str = ""
    basis: str = ""
    note: str = "institutional memory — background context, never proof"


@dataclass(frozen=True)
class MemorySection(Section):
    count: int = 0
    priors: tuple[MemoryItem, ...] = ()


@dataclass(frozen=True)
class PreviousInvestigationsSection(Section):
    """Prior investigation snapshots for the same subject. Requires a by-target lookup that is not a
    ready collector today (P1.2 completeness gap)."""

    count: int = 0
    investigations: tuple[dict, ...] = ()


@dataclass(frozen=True)
class MetadataSection(Section):
    context_version: str = INVESTIGATION_CONTEXT_VERSION
    platform: str = "unknown"
    binder_version: str = ""
    bundle_id: str = ""
    bundle_schema_version: int = 0
    capabilities: dict = field(default_factory=dict)
    section_counts: dict = field(default_factory=dict)
    pii_posture: str = "identifiers pseudonymized (sub_*); comment bodies carried verbatim"


# --------------------------------------------------------------------------- #
# The assembled object
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class InvestigationContext:
    """The ONE typed evidence object — the only input the Prompt Builder will consume.

    Content-addressed (``context_id``): a pure function of the assembled evidence (no wall-clock),
    so identical evidence yields an identical id. Read-only; carries no prompt text."""

    context_version: str
    context_id: str
    investigation: InvestigationSection
    post: PostSection
    author: AuthorSection
    comments: CommentsSection
    accounts: AccountsSection
    coordination: CoordinationSection
    narratives: NarrativesSection
    campaigns: CampaignsSection
    graph: GraphSection
    behavioral: BehavioralSection
    timing: TimingSection
    engagement: EngagementSection
    cross_platform: CrossPlatformSection
    omiscore: OmiScoreSection
    memory: MemorySection
    previous_investigations: PreviousInvestigationsSection
    metadata: MetadataSection

    def sections(self) -> list[tuple[str, Section]]:
        return [(name, getattr(self, name)) for name in SECTION_ORDER]

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "context_version": self.context_version,
            "context_id": self.context_id,
        }
        for name, section in self.sections():
            out[name] = section.to_dict()
        return out


# --------------------------------------------------------------------------- #
# Projection helpers (pure; reuse collectors; never recompute a score)
# --------------------------------------------------------------------------- #
def _f(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _video(payload: dict) -> dict:
    v = payload.get("video")
    return v if isinstance(v, dict) else {}


def _commenters(payload: dict) -> list[dict]:
    cs = _video(payload).get("commenters") or payload.get("commenters") or []
    return [c for c in cs if isinstance(c, dict)]


def _identity_map(commenters: list[dict]) -> dict[str, str]:
    """A canonical identity map so an account has ONE stable ref across every section. An account's
    canonical ident is ``handle or external_id`` (what :func:`_account_evidence` pseudonymizes); this
    maps BOTH its ``external_id`` and its ``handle`` to that canonical ident. Coordination clusters
    (and the graph) reference members by whichever key the detector emitted — usually ``external_id``
    — so without this remap a cluster member and its account get two different ``sub_`` refs and the
    account↔coordination join silently breaks (bridges / cluster membership become invisible)."""
    idmap: dict[str, str] = {}
    for c in commenters:
        ident = c.get("handle") or c.get("external_id") or ""
        if not ident:
            continue
        for key in (c.get("external_id"), c.get("handle"), ident):
            if key:
                idmap[str(key)] = str(ident)
    return idmap


def _clusters(payload: dict) -> list[dict]:
    coord = payload.get("coordination")
    cls = (
        (coord.get("clusters") if isinstance(coord, dict) else None)
        or _video(payload).get("clusters")
        or payload.get("clusters")
        or []
    )
    return [c for c in cls if isinstance(c, dict)]


def _signal(s: dict) -> SignalEvidence:
    return SignalEvidence(
        present=True, name=str(s.get("name") or "?"), probability=_f(s.get("probability")),
        confidence=_f(s.get("confidence")), supplemental=bool(s.get("supplemental", False)),
        evidence=tuple(str(e) for e in (s.get("evidence") or [])[:5]),
    )


def _contribution(c: dict) -> ContributionEvidence:
    return ContributionEvidence(
        present=True, name=str(c.get("name") or "?"), impact=_f(c.get("impact")),
        direction=str(c.get("direction") or "neutral"), supplemental=bool(c.get("supplemental", False)),
        headline=str(c.get("headline") or "")[:200],
        logit_delta=_f(c.get("logit_delta")), decorrelation_factor=_f(c.get("decorrelation_factor"), 1.0),
        evidence=str(c.get("evidence") or "")[:200],
    )


def _cluster_evidence(cl: dict, idmap: dict[str, str] | None = None) -> ClusterEvidence:
    members = cl.get("members")
    member_list = [str(m) for m in members] if isinstance(members, list) else []
    method = str(cl.get("method") or "")
    idmap = idmap or {}
    return ClusterEvidence(
        present=True, method=method,
        members_count=len(member_list) if member_list else int(_f(members)),
        # Resolve each member through the canonical identity map so a cluster member pseudonymizes to
        # the SAME ``sub_`` ref as its account record (an orphan member with no account maps to itself).
        member_refs=tuple(_pseudo(idmap.get(m, m)) for m in member_list[:25]),
        score=_f(cl.get("score")), discriminative=method in DISCRIMINATIVE_METHODS,
        evidence=tuple(str(e) for e in (cl.get("evidence") or [])[:6]),
    )


def _int_or_none(v) -> int | None:
    try:
        return int(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _account_evidence(c: dict, platform: str) -> AccountEvidence:
    ident = c.get("handle") or c.get("external_id") or ""
    signals = tuple(_signal(s) for s in (c.get("signals") or []) if isinstance(s, dict))
    contribs = tuple(_contribution(x) for x in (c.get("contributions") or []) if isinstance(x, dict))
    adj = c.get("coordination_adjusted_probability")
    activity = c.get("recent_activity") or []
    # RAW behavioral samples for THIS account (text + time only — the model reads the actual posts).
    posts = tuple(
        RawPostSample(present=True, text=str(a.get("text") or "").strip()[:400],
                      created_at=(str(a.get("created_at")) if a.get("created_at") else None))
        for a in activity[:_MAX_PER_ACCOUNT_SAMPLES]
        if isinstance(a, dict) and str(a.get("text") or "").strip()
    )
    post_count = c.get("history_size")
    if post_count is None:
        post_count = len(activity)
    return AccountEvidence(
        present=True, ref=_pseudo(str(ident)), platform=str(c.get("platform") or platform),
        # RAW metadata the AI reasons from — no computed score.
        follower_count=_int_or_none(c.get("follower_count")),
        following_count=_int_or_none(c.get("following_count")),
        account_created_at=(str(c.get("account_created_at")) if c.get("account_created_at") else None),
        post_count=_int_or_none(post_count),
        recent_posts=posts,
        activity_sample_count=len(activity),
        from_cache=bool(c.get("from_cache", False)),
        matched_prior_neighbors=int(_f(c.get("matched_prior_neighbors"))),
        # Computed engine fields retained on the object for OTHER features; NOT rendered to the model.
        overall_probability=_f(c.get("overall_probability")),
        coordination_adjusted_probability=(None if adj is None else _f(adj)),
        tier=str(c.get("tier") or "low"), confidence=_f(c.get("confidence")),
        weak_signals=tuple(str(w) for w in (c.get("weak_signals") or [])[:8]),
        coordination_evidence=tuple(str(e) for e in (c.get("coordination_evidence") or [])[:8]),
        score_adjustments=tuple(str(a) for a in (c.get("score_adjustments") or [])[:8]),
        signals=signals, contributions=contribs,
    )


def _build_comments(payload: dict, commenters: list[dict]) -> CommentsSection:
    thread = _video(payload).get("thread_scan") or {}
    samples: list[CommentSample] = []
    for c in commenters:
        ident = c.get("handle") or c.get("external_id") or ""
        aref = _pseudo(str(ident))
        for a in (c.get("recent_activity") or [])[:_MAX_PER_ACCOUNT_SAMPLES]:
            if not isinstance(a, dict):
                continue
            text = str(a.get("text") or "").strip()
            if not text:
                continue
            parent = a.get("parent_id")
            samples.append(CommentSample(
                present=True, author_ref=aref, text=text[:600],
                created_at=(str(a.get("created_at")) if a.get("created_at") else None),
                parent_ref=(_pseudo(str(parent)) if parent else None),
            ))
            if len(samples) >= _MAX_COMMENT_SAMPLES:
                break
        if len(samples) >= _MAX_COMMENT_SAMPLES:
            break
    has_thread = bool(thread)
    return CommentsSection(
        present=bool(samples or has_thread),
        thread_probability=(_f(thread.get("overall_probability")) if has_thread else None),
        thread_tier=(str(thread.get("tier")) if has_thread else None),
        sample_count=len(samples), samples=tuple(samples),
    )


def _named_signal_stats(commenters: list[dict], name: str) -> tuple[float | None, float | None, int]:
    """Mean probability/confidence of a named detector across commenters that carry it (evidence
    surfacing — not a recomputation)."""
    probs, confs = [], []
    for c in commenters:
        for s in (c.get("signals") or []):
            if isinstance(s, dict) and s.get("name") == name and _f(s.get("confidence")) > 0:
                probs.append(_f(s.get("probability")))
                confs.append(_f(s.get("confidence")))
    n = len(probs)
    if not n:
        return None, None, 0
    return round(sum(probs) / n, 6), round(sum(confs) / n, 6), n


# --------------------------------------------------------------------------- #
# The builder
# --------------------------------------------------------------------------- #
def build_investigation_context(
    payload: dict,
    *,
    ref: str,
    platform: str = "unknown",
    slug: str | None = None,
    kind: str | None = None,
    settings: Any = None,
    store: Any = None,
    now: Any = None,
    grain: str = "comment_section",
) -> InvestigationContext:
    """Assemble the ONE :class:`InvestigationContext` for an investigation payload.

    Deterministic and side-effect-free: reuses the :class:`Binder` (evidence graph),
    :func:`retrieve` (institutional memory), and :func:`compute_omiscore`, and projects the raw
    grain sections from ``payload``. Never runs a model, never builds a prompt, never writes.
    ``store`` (memory) defaults to the durable store exactly as ``assess_payload`` does; an empty
    store no-ops. Sections that need a store not yet wired (narratives / OmiScore-from-store /
    previous investigations) are emitted empty-but-typed — a P1.2 completeness item. Never raises
    for the caller — assembly failures degrade a section to empty.
    """
    payload = payload or {}
    commenters = _commenters(payload)
    clusters = _clusters(payload)
    coord = payload.get("coordination") if isinstance(payload.get("coordination"), dict) else {}

    # --- reuse the canonical Evidence Bundle (behavioral / coordination / graph facets) ---------
    try:
        bundle = Binder().bind(
            payload, grain=grain, subject_ref=ref, platform=platform, enrich=True,
        )
    except Exception:  # noqa: BLE001 — evidence assembly must never break the caller
        bundle = None

    investigation = InvestigationSection(
        present=True, ref=_pseudo(ref), platform=platform, slug=slug, kind=kind,
        inputs_provided=tuple(str(i) for i in (payload.get("inputs_provided") or [])),
        overall_probability=_f(payload.get("overall_probability")),
        overall_tier=str(payload.get("overall_tier") or payload.get("tier") or "low"),
        confidence=_f(payload.get("confidence")),
        convergence_score=_f(payload.get("convergence_score")),
        summary=str(payload.get("summary") or ""), quota_used=int(_f(payload.get("quota_used"))),
    )

    video_id = payload.get("video_id") or _video(payload).get("video_id")
    post = PostSection(
        present=bool(video_id), content_id=(str(video_id) if video_id else None),
        platform=platform, title=None, published_at=None, metadata_available=False,
    )

    focus = payload.get("focus_account") if isinstance(payload.get("focus_account"), dict) else None
    if focus:
        fident = focus.get("handle") or focus.get("external_id") or ""
        author = AuthorSection(
            present=True, ref=_pseudo(str(fident)), platform=platform,
            overall_probability=_f(focus.get("overall_probability")),
            tier=str(focus.get("tier") or "low"), confidence=_f(focus.get("confidence")),
            # Ruling 3: intent_label / suspected_intent / reasons are interpretations, not evidence.
            follower_count=(int(_f(focus.get("follower_count"))) if focus.get("follower_count") is not None else None),
            history_size=(int(_f(focus.get("history_size"))) if focus.get("history_size") is not None else None),
            account_created_at=(str(focus.get("account_created_at")) if focus.get("account_created_at") else None),
        )
    else:
        author = AuthorSection(present=False)

    comments = _build_comments(payload, commenters)

    account_items = tuple(_account_evidence(c, platform) for c in commenters[:_MAX_ACCOUNTS])
    accounts = AccountsSection(present=bool(account_items), count=len(account_items), accounts=account_items)

    idmap = _identity_map(commenters)
    cluster_items = tuple(_cluster_evidence(cl, idmap) for cl in clusters[:_MAX_CLUSTERS] if cl.get("method"))
    disc_methods = tuple(sorted({c.method for c in cluster_items if c.discriminative}))
    coordination = CoordinationSection(
        present=bool(cluster_items) or bool(_video(payload).get("coordination_score") is not None),
        coordination_score=_f(_video(payload).get("coordination_score") or payload.get("coordination_score")),
        coordination_tier=str(_video(payload).get("coordination_tier") or "low"),
        single_axis_capped=bool(coord.get("single_axis_capped") or payload.get("single_axis_capped")),
        discriminative_methods=disc_methods, cluster_count=len(cluster_items), clusters=cluster_items,
    )

    campaign_candidates = tuple(c for c in cluster_items if c.score >= 0.5)
    campaigns = CampaignsSection(
        present=bool(campaign_candidates), count=len(campaign_candidates), candidates=campaign_candidates,
    )

    narratives = _narratives_section()

    graph = _graph_section(bundle)
    behavioral = _behavioral_section(bundle)

    t_prob, t_conf, t_n = _named_signal_stats(commenters, "temporal")
    timing = TimingSection(
        present=bool(t_n) or comments.sample_count > 0,
        temporal_probability=t_prob, temporal_confidence=t_conf, accounts_with_temporal_signal=t_n,
        timestamped_activity_available=any(s.created_at for s in comments.samples),
    )

    e_prob, e_conf, e_n = _named_signal_stats(commenters, "engagement")
    co_eng = sum(1 for c in cluster_items if c.method == "co_engagement")
    engagement = EngagementSection(
        present=bool(e_n) or bool(co_eng),
        engagement_probability=e_prob, engagement_confidence=e_conf,
        accounts_with_engagement_signal=e_n, co_engagement_clusters=co_eng,
    )

    links = []
    for l in (payload.get("cross_links") or [])[:_MAX_CROSS_LINKS]:
        if not isinstance(l, dict):
            continue
        links.append(CrossLinkEvidence(
            present=True, kind=str(l.get("kind") or ""), severity=str(l.get("severity") or "info"),
            summary=str(l.get("summary") or "")[:400],
            evidence=tuple(str(e) for e in (l.get("evidence") or [])[:4]),
            related_refs=tuple(_pseudo(str(e)) for e in (l.get("related_entities") or [])[:6]),
        ))
    cross_platform = CrossPlatformSection(present=bool(links), count=len(links), links=tuple(links))

    omiscore = _omiscore_section(platform, commenters)
    memory = _memory_section(bundle, store=store, settings=settings, now=now)
    previous = _previous_investigations_section()

    # --- metadata (excludes wall-clock from the content address) --------------------------------
    section_counts = {
        "accounts": accounts.count, "comment_samples": comments.sample_count,
        "clusters": coordination.cluster_count, "campaign_candidates": campaigns.count,
        "cross_links": cross_platform.count, "graph_edges": len(graph.edges),
        "behavioral_items": len(behavioral.items), "memory_priors": memory.count,
        "narratives": narratives.count, "omiscores": omiscore.count,
        "previous_investigations": previous.count,
    }
    metadata = MetadataSection(
        present=True, context_version=INVESTIGATION_CONTEXT_VERSION, platform=platform,
        binder_version=(getattr(bundle, "version_binding", {}) or {}).get("binder_version", "") if bundle else "",
        bundle_id=(bundle.bundle_id() if bundle is not None else ""),
        bundle_schema_version=(getattr(bundle, "version_binding", {}) or {}).get("bundle_schema_version", 0) if bundle else 0,
        capabilities=(dict(getattr(bundle, "capabilities", {})) if bundle else {}),
        section_counts=section_counts,
    )

    sections = {
        "investigation": investigation, "post": post, "author": author, "comments": comments,
        "accounts": accounts, "coordination": coordination, "narratives": narratives,
        "campaigns": campaigns, "graph": graph, "behavioral": behavioral, "timing": timing,
        "engagement": engagement, "cross_platform": cross_platform, "omiscore": omiscore,
        "memory": memory, "previous_investigations": previous, "metadata": metadata,
    }
    context_id = digest(
        {"version": INVESTIGATION_CONTEXT_VERSION,
         "sections": {name: sections[name].to_dict() for name in SECTION_ORDER}},
        prefix="ictx:",
    )
    return InvestigationContext(
        context_version=INVESTIGATION_CONTEXT_VERSION, context_id=context_id, **sections,
    )


# --------------------------------------------------------------------------- #
# Section builders that reuse a collector (bundle / memory / payload)
# --------------------------------------------------------------------------- #
def _graph_section(bundle: Any) -> GraphSection:
    if bundle is None:
        return GraphSection(present=False)
    accounts = [e for e in bundle.entities.values() if e.kind == "account"]
    edges = [
        GraphEdge(present=True, type=r.type,
                  from_ref=(bundle.entities[r.from_].ref if r.from_ in bundle.entities else r.from_),
                  to_ref=(bundle.entities[r.to].ref if r.to in bundle.entities else r.to))
        for r in bundle.relationships[:_MAX_GRAPH_EDGES]
    ]
    return GraphSection(
        present=bool(accounts or edges), account_entities=len(accounts),
        relationship_count=len(bundle.relationships),
        member_refs=tuple(e.ref for e in accounts[:_MAX_ACCOUNTS]), edges=tuple(edges),
    )


def _behavioral_section(bundle: Any) -> BehavioralSection:
    if bundle is None:
        return BehavioralSection(present=False)
    items = []
    for it in bundle.evidence.values():
        if it.facet != "behavioral":
            continue
        items.append(BehavioralItem(
            present=True, ev_id=it.id, detector=it.originating_detector, kind=it.kind,
            direction=it.direction, impact=abs(_f((it.value or {}).get("impact"))),
            supplemental=bool(it.supplemental),
        ))
    items.sort(key=lambda x: (-x.impact, x.ev_id))
    epi = bundle.epistemics or {}
    return BehavioralSection(
        present=bool(items), items=tuple(items[:_MAX_BEHAVIORAL]),
        contradictions=tuple(epi.get("contradictions") or []),
        unknowns=tuple(epi.get("unknowns") or []),
        missing_evidence=tuple(epi.get("missing_evidence") or []),
    )


def _memory_section(bundle: Any, *, store: Any, settings: Any, now: Any) -> MemorySection:
    """Reuse the production memory collector (``retrieve``). ``store`` defaults to the durable
    store (``get_memory_store``) exactly as ``assess_payload`` does; an empty store no-ops."""
    if bundle is None:
        return MemorySection(present=False)
    try:
        from app.memory.graph import retrieve
        if store is None:
            from app.core.config import get_settings
            from app.memory.repository import get_memory_store
            store = get_memory_store(settings or get_settings())
        priors = retrieve(store, bundle, top_k=_MAX_MEMORY, now=now) if store is not None else []
    except Exception:  # noqa: BLE001 — memory must never break assembly
        return MemorySection(present=False)
    items = tuple(
        MemoryItem(
            present=True, type=str(getattr(p, "type", "")), label=str(getattr(p, "label", "")),
            confidence=round(_f(getattr(p, "confidence", 0.0)), 3),
            stability=round(_f(getattr(p, "stability_score", 0.0)), 3),
            epistemic_status=str(getattr(p, "epistemic_status", "")),
            influence_class=str(getattr(p, "influence_class", "")),
            basis=str(getattr(p, "match_basis", "")),
        )
        for p in priors
    )
    return MemorySection(present=bool(items), count=len(items), priors=items)


def _narratives_section() -> NarrativesSection:
    """Narrative (message-cluster) evidence lives in the Narrative store keyed by message cluster
    and is ingested asynchronously after a scan; there is no ready per-investigation collector
    today. Emitted empty-but-typed — linking narratives to an investigation is a P1.2 completeness
    item (see the deliverable), not a section this layer fabricates."""
    return NarrativesSection(present=False)


def _omiscore_section(platform: str, commenters: list[dict]) -> OmiScoreSection:
    """Per-account OmiScore — REUSES the real ``compute_omiscore`` collector over the per-account
    ``signals`` already in the payload. OmiScore is a deterministic *composition/index* over
    existing signals (classified "stays sensor"), never a new detection — so this recomputes no
    score and needs no session/store. A commenter we cannot compose is simply skipped."""
    if not commenters:
        return OmiScoreSection(present=False)
    try:
        from app.intelligence.omiscore import compute_omiscore
        from app.schemas import ScanResult, SignalResult, Tier
    except Exception:  # noqa: BLE001
        return OmiScoreSection(present=False)
    scores: list[dict] = []
    for c in commenters[:_MAX_ACCOUNTS]:
        raw = [s for s in (c.get("signals") or []) if isinstance(s, dict)]
        if not raw:
            continue
        ident = c.get("handle") or c.get("external_id") or ""
        try:
            scan = ScanResult(
                overall_probability=_f(c.get("overall_probability")),
                confidence=_f(c.get("confidence")), tier=Tier(str(c.get("tier") or "low")),
                summary=str(c.get("summary") or ""),
                signals=[SignalResult(
                    name=str(s.get("name") or "?"), probability=_f(s.get("probability")),
                    confidence=_f(s.get("confidence")), evidence=list(s.get("evidence") or []),
                    sub_signals=dict(s.get("sub_signals") or {}),
                    supplemental=bool(s.get("supplemental", False)),
                ) for s in raw],
            )
            omi = compute_omiscore(scan)
        except Exception:  # noqa: BLE001 — skip any commenter we cannot compose
            continue
        scores.append({
            "ref": _pseudo(str(ident)),
            "omi_score": getattr(omi, "omi_score", None),
            "authenticity_score": getattr(omi, "authenticity_score", None),
            # risk_level (heuristic band) is NOT projected as evidence — only the numeric index rides.
        })
    return OmiScoreSection(present=bool(scores), count=len(scores), scores=tuple(scores))


def _previous_investigations_section() -> PreviousInvestigationsSection:
    """Prior investigation snapshots for the same subject require a by-target lookup that is not a
    ready collector today (investigations are listed by user, not by target). Emitted
    empty-but-typed — a P1.2 completeness item, not a section this layer fabricates."""
    return PreviousInvestigationsSection(present=False)


__all__ = [
    "INVESTIGATION_CONTEXT_VERSION", "SECTION_ORDER", "InvestigationContext",
    "build_investigation_context",
]
