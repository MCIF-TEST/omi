from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, field_validator


Platform = Literal["x", "youtube", "reddit", "telegram", "tiktok", "instagram", "unknown"]


class Profile(BaseModel):
    """Platform-agnostic account profile."""

    platform: Platform = "unknown"
    handle: str
    display_name: str | None = None
    bio: str | None = None
    follower_count: int | None = None
    following_count: int | None = None
    created_at: datetime | None = None
    avatar_url: str | None = None
    verified: bool | None = None


class Post(BaseModel):
    """Platform-agnostic post / comment."""

    id: str
    author_handle: str
    text: str
    created_at: datetime
    reply_to_id: str | None = None
    repost_of_id: str | None = None
    # The platform-native context this post lives under: a video ID for
    # YouTube, a subreddit for Reddit, etc. Used for cross-account
    # co-engagement analysis.
    parent_id: str | None = None
    like_count: int | None = None
    reply_count: int | None = None
    repost_count: int | None = None
    source_client: str | None = None  # e.g. "Twitter Web App"


class Tier(str, Enum):
    LOW = "low"
    MODERATE = "moderate"
    ELEVATED = "elevated"
    HIGH = "high"


class SignalResult(BaseModel):
    """Output of a single detector. Probabilities, not verdicts."""

    name: str
    probability: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0, description="How much data backed the estimate")
    evidence: list[str] = Field(default_factory=list)
    sub_signals: dict[str, float] = Field(default_factory=dict)

    @field_validator("evidence")
    @classmethod
    def _strip_evidence(cls, v: list[str]) -> list[str]:
        return [s.strip() for s in v if s and s.strip()]


class AccountAnalysisRequest(BaseModel):
    profile: Profile
    posts: list[Post] = Field(default_factory=list)


class CommentAnalysisRequest(BaseModel):
    comments: list[Post]
    context_platform: Platform = "unknown"


class ScanResult(BaseModel):
    """Aggregated detection output. Always probabilistic, always with evidence."""

    overall_probability: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    tier: Tier
    signals: list[SignalResult]
    summary: str
    # The handle scanned (echoed back for convenience).
    subject: str | None = None
    # Best-guess category of what the account is doing, when tier > low.
    # Probabilistic; ``intent_label`` is human-readable.
    suspected_intent: str | None = None
    intent_label: str | None = None
    # Plain-language list of WHY this account was flagged (one bullet per
    # contributing detector, in order of contribution). Empty for low tier.
    reasons: list[str] = Field(default_factory=list)
    # Plain-language warnings about WHY this scan is low confidence.
    # Surfaces "we didn't have enough posts to run the temporal detector"
    # so the UI can show data-quality caveats explicitly.
    weak_signals: list[str] = Field(default_factory=list)
    # Plain-language record of post-hoc adjustments the aggregator made to the
    # raw log-odds: correlated detectors discounted to avoid double-counting
    # shared evidence, the single-signal HIGH cap, or the convergence bonus.
    # Lets the UI explain *why* the headline number isn't just the sum of the
    # bars. Empty when no adjustment applied.
    score_adjustments: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Video-scan (multi-account) types
# ---------------------------------------------------------------------------


class VideoScanRequest(BaseModel):
    video_url_or_id: str = Field(
        description="YouTube video URL or 11-character video ID."
    )
    max_commenters: int | None = Field(
        default=None,
        ge=1,
        le=500,
        description="Override the global cap on commenters fetched.",
    )
    force_refresh: bool = Field(
        default=False,
        description="Ignore cached scans and re-fetch every commenter from YouTube.",
    )


class CommenterScanResult(BaseModel):
    platform: Platform = "youtube"
    external_id: str
    handle: str
    display_name: str | None = None
    avatar_url: str | None = None
    overall_probability: float
    confidence: float
    tier: Tier
    summary: str
    from_cache: bool
    matched_prior_neighbors: int = 0
    error: str | None = None
    # Cross-account adjustments (set when a coordination cluster catches
    # this commenter inside a full-scan run). The standalone
    # ``overall_probability`` above is what gets persisted to the cache;
    # ``coordination_adjusted_probability`` is the lift after factoring in
    # the cluster. The two are kept separate so caches don't get polluted.
    coordination_adjusted_probability: float | None = None
    coordination_evidence: list[str] = Field(default_factory=list)
    suspected_intent: str | None = None
    intent_label: str | None = None
    reasons: list[str] = Field(default_factory=list)
    # Sample recent activity (only populated for non-low-tier accounts so
    # the UI can show "here's what this account actually wrote" without
    # bloating the response on the 80% of low-suspicion commenters).
    recent_activity: list[dict] = Field(default_factory=list)
    activity_total: int = 0
    weak_signals: list[str] = Field(default_factory=list)
    # Plain-language record of how the aggregator adjusted the raw signal sum:
    # correlated detectors discounted, single-axis HIGH cap, convergence bonus.
    score_adjustments: list[str] = Field(default_factory=list)
    # Per-detector breakdown — populated when signals are available.
    signals: list[SignalResult] = Field(default_factory=list)


class CoordinationClusterOut(BaseModel):
    method: str
    members: list[str]
    score: float = Field(ge=0.0, le=1.0)
    evidence: list[str] = Field(default_factory=list)
    metadata: dict[str, float] = Field(default_factory=dict)


class FullVideoScanResult(BaseModel):
    """The unified per-video output: per-commenter + thread-level + coordination."""

    video_id: str
    platform: Platform = "youtube"

    # Per-commenter rollup
    commenter_count: int
    fresh_count: int
    cached_count: int
    quota_used: int
    tier_distribution: dict[str, int]
    high_suspicion_handles: list[str]
    commenters: list[CommenterScanResult]

    # Thread-level: ai-writing + semantic over the full comment corpus
    thread_scan: ScanResult

    # Cross-account coordination
    coordination_score: float = Field(ge=0.0, le=1.0)
    coordination_tier: Tier
    clusters: list[CoordinationClusterOut]

    # Optional focus account deep-dive (when the request specified one)
    focus_account: CommenterScanResult | None = None

    summary: str

    # Continuation cursor — pass back to the next request to fetch the
    # following batch of commenters on the same video. ``None`` means
    # everything has been fetched.
    next_page_token: str | None = None


class FullVideoScanRequest(BaseModel):
    video_url_or_id: str
    max_commenters: int | None = Field(default=None, ge=1, le=500)
    force_refresh: bool = False
    # External ID (e.g. YouTube channel ID) of a commenter to spotlight in
    # the response.
    focus_account_external_id: str | None = None
    # Continuation cursor — resume YouTube commentThreads pagination from a
    # prior batch so an incremental "+ New Batch" scan reads ONLY new
    # comments instead of re-fetching the ones already in the database.
    start_page_token: str | None = None


# ---------------------------------------------------------------------------
# Comprehensive scan — the unified intelligence endpoint
# ---------------------------------------------------------------------------


class ComprehensiveScanRequest(BaseModel):
    """All inputs optional. Provide whatever you have; the orchestrator scans
    only what's present and cross-correlates the results.

    At least one of ``account_url_or_handle``, ``video_url_or_id``, or
    ``comments_text`` must be supplied."""

    account_url_or_handle: str | None = None
    video_url_or_id: str | None = None
    comments_text: str | None = None
    max_commenters: int = Field(default=150, ge=5, le=500)
    force_refresh: bool = False
    # Continuation: opaque cursor returned from a prior video scan. When
    # supplied, OMI resumes the YouTube commentThreads pagination from there
    # so the user can scan the next batch of commenters on a long video.
    start_page_token: str | None = None


class AccountScanOut(BaseModel):
    """Top-level account scan result returned by /v1/scan/youtube/account
    and embedded in the comprehensive response when an account is provided."""

    external_id: str
    handle: str
    display_name: str | None = None
    avatar_url: str | None = None
    bio: str | None = None
    follower_count: int | None = None
    account_created_at: datetime | None = None
    overall_probability: float
    confidence: float
    tier: Tier
    summary: str
    signals: list[SignalResult]
    from_cache: bool
    matched_prior_neighbors: int = 0
    history_size: int
    suspected_intent: str | None = None
    intent_label: str | None = None
    reasons: list[str] = Field(default_factory=list)
    recent_activity: list[dict] = Field(default_factory=list)
    activity_total: int = 0


class CrossLink(BaseModel):
    """One detected connection between two of the user's inputs.

    Cross-links are the interconnection signal — they explain *how* the
    account, video, and pasted comments relate to each other. Multiple
    cross-links that converge on the same entity compound into a stronger
    verdict (see ``ComprehensiveScanResult.convergence_score``).
    """

    kind: str   # e.g. "focus_in_cluster", "fellow_traveler", "style_match"
    severity: str   # "info" | "moderate" | "elevated" | "high"
    summary: str
    evidence: list[str] = Field(default_factory=list)
    related_entities: list[str] = Field(default_factory=list)
    metadata: dict[str, float] = Field(default_factory=dict)


class MatrixRow(BaseModel):
    """One row of the coordination matrix visualization.

    Columns are the detector methods; cells are True/False flags. Lets the
    UI render a glanceable account × detector grid that makes "this account
    was caught by four detectors" pop visually.
    """

    external_id: str
    handle: str
    is_focus: bool = False
    tier: Tier
    probability: float
    coordination_adjusted_probability: float | None = None
    detector_flags: dict[str, bool] = Field(default_factory=dict)
    convergence_count: int = 0


class ComprehensiveScanResult(BaseModel):
    """The unified intelligence report: account + video + comments + cross-links."""

    # Per-input results (any can be None if the input wasn't provided)
    focus_account: AccountScanOut | None = None
    video: FullVideoScanResult | None = None
    comments_scan: ScanResult | None = None

    # The interconnection layer
    cross_links: list[CrossLink]
    convergence_score: float = Field(ge=0.0, le=1.0)
    matrix: list[MatrixRow]
    matrix_methods: list[str]

    # Top-level synthesis
    overall_tier: Tier
    overall_probability: float = Field(ge=0.0, le=1.0)
    summary: str
    inputs_provided: list[str]
    quota_used: int = 0

    # Continuation cursor for the video commenter pagination, if applicable.
    next_page_token: str | None = None
    video_id: str | None = None
    # Phase 5: stable URL slug of the saved investigation. UI passes this
    # back on continuation batches so they append to the same record.
    investigation_slug: str | None = None


# ---------------------------------------------------------------------------
# /v1/status — live engine state for the UI header
# ---------------------------------------------------------------------------


class EngineStatus(BaseModel):
    version: str
    env: str
    total_accounts: int
    total_scans: int
    total_engagement_edges: int
    total_video_scans: int
    fingerprints_stored: int
    last_scan_at: datetime | None = None
    youtube_configured: bool
    # Multi-tenant flags for the UI
    auth_required: bool = False
    billing_configured: bool = False
    monthly_credit_grant: int = 20
    # True when the DB lives on an ephemeral disk (SQLite). UI shows a banner
    # so operators know data won't survive a redeploy.
    storage_ephemeral: bool = False
    # YouTube Data API v3 daily quota burn. Counted from VideoScan rows
    # scanned in the last 24 hours. The default daily limit on the free
    # YouTube tier is 10000 units; override via OMI_YOUTUBE_DAILY_QUOTA.
    youtube_quota_used_today: int = 0
    youtube_quota_daily_limit: int = 10000


class VideoScanSummary(BaseModel):
    video_id: str
    platform: Platform = "youtube"
    commenter_count: int
    fresh_count: int
    cached_count: int
    quota_used: int
    tier_distribution: dict[str, int]
    high_suspicion_handles: list[str]
    summary: str
    commenters: list[CommenterScanResult]


# ---------------------------------------------------------------------------
# Account history — /v1/accounts/{platform}/{external_id}/history
# ---------------------------------------------------------------------------


class HistoricalScan(BaseModel):
    """One past scan of an account."""

    scanned_at: datetime
    overall_probability: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    tier: Tier
    summary: str
    reasons: list[str] = Field(default_factory=list)
    weak_signals: list[str] = Field(default_factory=list)
    # Per-detector breakdown — only populated for the latest scan to keep
    # the payload small for older history rows.
    signals: list[SignalResult] = Field(default_factory=list)


class TrendInfo(BaseModel):
    """Categorical + numeric trend over an account's history."""

    direction: Literal["stable", "rising", "falling", "volatile", "insufficient"]
    slope: float
    volatility: float
    net_change: float
    sample_size: int
    summary: str


# ---------------------------------------------------------------------------
# Graph + coordination intelligence — /v1/graph/*
# ---------------------------------------------------------------------------


class GraphNode(BaseModel):
    external_id: str
    handle: str
    display_name: str | None = None
    tier: str | None = None
    last_score: float | None = None
    community_id: int = 0


class GraphEdge(BaseModel):
    a: str
    b: str
    strength: float = Field(ge=0.0, le=1.0)


class AccountSubgraphResponse(BaseModel):
    focal: str
    depth: int
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    community_count: int


class CommunitySampleAccount(BaseModel):
    external_id: str
    handle: str
    tier: str | None = None


class CommunityOut(BaseModel):
    id: int
    size: int
    avg_strength: float
    max_strength: float
    methods_seen: list[str]
    sample_accounts: list[CommunitySampleAccount]
    total_members: int


class CommunitiesResponse(BaseModel):
    platform: Platform
    min_size: int
    communities: list[CommunityOut]


# ---------------------------------------------------------------------------
# User-curated named graphs — /v1/graphs/*
# ---------------------------------------------------------------------------


class CreateGraphRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    platform: str = "youtube"


class RenameGraphRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class AddGraphMemberRequest(BaseModel):
    external_id: str
    handle: str = ""
    display_name: str | None = None
    tier: str | None = None
    avatar_url: str | None = None


class UserGraphMemberOut(BaseModel):
    id: int
    external_id: str
    platform: str
    handle: str
    display_name: str | None = None
    tier: str | None = None
    avatar_url: str | None = None
    added_at: datetime


class UserGraphOut(BaseModel):
    id: int
    name: str
    platform: str
    member_count: int
    created_at: datetime
    updated_at: datetime


class UserGraphDetail(UserGraphOut):
    members: list[UserGraphMemberOut]
    edges: list[GraphEdge]


# ---------------------------------------------------------------------------
# Investigations (Phase 5) — persistent scan records
# ---------------------------------------------------------------------------


class InvestigationSummary(BaseModel):
    """Lightweight investigation row for the dashboard / list endpoints."""

    slug: str
    label: str
    input_url: str
    kind: str
    overall_probability: float = Field(ge=0.0, le=1.0)
    overall_tier: Tier
    summary: str
    quota_used: int
    batch_count: int
    created_at: datetime
    updated_at: datetime
    target_id: str | None = None
    verdict: str | None = None


class InvestigationsListResponse(BaseModel):
    investigations: list[InvestigationSummary]


class InvestigationDetailResponse(BaseModel):
    """Full investigation: summary + the entire ComprehensiveScanResult payload."""

    slug: str
    label: str
    input_url: str
    kind: str
    overall_probability: float
    overall_tier: Tier
    summary: str
    quota_used: int
    batch_count: int
    created_at: datetime
    updated_at: datetime
    payload: dict
    share_token: str | None = None
    is_public: bool = False
    published_at: datetime | None = None
    # Phase 7 — cached commentary fields (null until the user generates).
    commentary_text: str | None = None
    commentary_provider: str | None = None
    commentary_generated_at: datetime | None = None
    # Analyst verdict + notes
    verdict: str | None = None
    concluded_at: datetime | None = None
    notes: str | None = None


class CommentaryResponse(BaseModel):
    """Phase 7 — analyst commentary on an investigation."""

    slug: str
    text: str
    provider: str
    tokens_used: int
    generated_at: datetime
    cached: bool


# ---------------------------------------------------------------------------
# Monitoring + watchlists (Phase 8)
# ---------------------------------------------------------------------------


class AlertOut(BaseModel):
    id: int
    user_id: int | None
    watchlist_id: int | None
    kind: str
    severity: str
    message: str
    payload: dict
    created_at: datetime
    read_at: datetime | None


class AlertsResponse(BaseModel):
    alerts: list[AlertOut]
    unread_count: int


class FeedResponse(BaseModel):
    """Live anomaly feed — global anomalies (user_id NULL)."""

    items: list[AlertOut]


class WatchlistIn(BaseModel):
    kind: Literal["channel", "narrative"] = "channel"
    target_id: str
    label: str | None = None
    alert_threshold_tier: Literal["low", "moderate", "elevated", "high"] = "moderate"


class WatchlistOut(BaseModel):
    id: int
    kind: str
    target_id: str
    label: str
    alert_threshold_tier: str
    last_seen_tier: str | None
    last_seen_probability: float | None
    last_checked_at: datetime | None
    last_alert_at: datetime | None
    created_at: datetime


class WatchlistsResponse(BaseModel):
    watchlists: list[WatchlistOut]


class EdgeDetailResponse(BaseModel):
    platform: Platform
    account_a: str
    account_b: str
    observation_count: int
    methods: list[str]
    mean_cluster_score: float
    strength: float
    last_shared_parent: str | None
    first_observed_at: datetime
    last_observed_at: datetime


# ---------------------------------------------------------------------------
# Narrative intelligence — /v1/narratives
# ---------------------------------------------------------------------------


class NarrativeOut(BaseModel):
    """A single narrative — semantic cluster of comments sharing topic/framing."""

    id: int
    label: str
    member_count: int
    distinct_authors: int
    recent_members: int
    spread_ratio: float = Field(ge=0.0, le=1.0)
    first_seen_at: datetime
    last_seen_at: datetime
    sample_text: str
    # Legacy risk fields (kept for backwards compatibility with old clients).
    inauthenticity_score: float = 0.0   # fraction of scanned members flagged elevated/high
    risk_label: str = "unknown"          # organic | mixed | suspicious | likely_coordinated
    platforms: list[str] = Field(default_factory=list)

    # ---- New coordination intelligence fields (Phase 9) -------------------
    # User-facing risk band derived from the multi-signal coordination panel.
    # Values: "low" | "moderate" | "high" | "extreme".
    risk_tier: str = "low"
    # Aggregate coordination likelihood in [0, 1].
    coordination_score: float = 0.0
    # Probability the cluster reflects artificial amplification.
    manipulation_probability: float = 0.0
    # Timing-focused score: bursts + entropy.
    synchronization_intensity: float = 0.0
    # Semantic tightness proxy.
    semantic_cohesion: float = 0.0
    # Number of independent signals firing at notable strength (0-8).
    cluster_confidence: int = 0
    # One-word verdict — see coordination.py for the mapping.
    coordination_label: str = "unscored"   # organic | mixed | suspicious | coordinated | manipulation_network
    # Counts restricted to MODERATE+ accounts (the "intelligence-grade" subset).
    qualifying_member_count: int = 0
    qualifying_author_count: int = 0


class NarrativesResponse(BaseModel):
    """List of trending narratives + the embedding stack identifier."""

    window_days: int
    embedder: str
    narratives: list[NarrativeOut]


# ---------------------------------------------------------------------------
# Narrative detail (drill-down page)
# ---------------------------------------------------------------------------


class NarrativeActivityPoint(BaseModel):
    date: str   # "2024-01-15"
    count: int


class NarrativeTopAccount(BaseModel):
    external_id: str
    handle: str
    display_name: str | None = None
    platform: str
    comment_count: int
    tier: str | None = None   # internal storage tier
    display_tier: str | None = None   # public-facing risk band: low|moderate|high|extreme
    # Number of distinct parents this account participated in (cross-spread).
    distinct_parents: int = 0
    # Composite per-account influence score within this cluster, in [0,1].
    influence_score: float = 0.0


class NarrativeSample(BaseModel):
    text: str
    account_external_id: str
    handle: str | None = None
    platform: str
    parent_id: str | None = None   # video/post ID
    observed_at: datetime


class NarrativeSignalBreakdown(BaseModel):
    """One row of the coordination signal breakdown."""

    name: str
    value: float = Field(ge=0.0, le=1.0)
    weight: float = Field(ge=0.0, le=1.0)


class NarrativePropagationPoint(BaseModel):
    """One bucket of the propagation timeline (default 6-hour buckets)."""

    bucket_start: datetime
    count: int
    velocity: float          # comments per hour
    suspicious_count: int    # how many came from moderate+ accounts


class NarrativeBurst(BaseModel):
    """An identified amplification burst on the propagation timeline."""

    bucket_start: datetime
    velocity: float
    ratio: float             # velocity / rolling-mean baseline
    severity: str            # moderate | high | extreme
    suspicious_count: int


class NarrativeGraphNode(BaseModel):
    """One node in the narrative coordination subgraph.

    Only MODERATE+ accounts appear in this graph — the "MOST IMPORTANT RULE".
    """

    external_id: str
    handle: str
    platform: str
    tier: str | None = None              # internal tier
    display_tier: str | None = None      # public-facing risk band
    comment_count: int = 0
    distinct_parents: int = 0
    influence_score: float = 0.0


class NarrativeGraphEdge(BaseModel):
    """One coordination edge between two MODERATE+ accounts in this cluster."""

    a: str                 # external_id
    b: str                 # external_id
    strength: float = Field(ge=0.0, le=1.0)
    methods: list[str] = Field(default_factory=list)


class NarrativeGraph(BaseModel):
    nodes: list[NarrativeGraphNode]
    edges: list[NarrativeGraphEdge]


class NarrativeOriginWindow(BaseModel):
    first_seen: datetime
    suspicious_first_seen: datetime | None = None
    lag_hours: float | None = None       # gap between narrative emergence and suspicious amplification


class NarrativeDetail(BaseModel):
    """Full drill-down for a single narrative cluster."""

    id: int
    label: str
    member_count: int
    distinct_authors: int
    spread_ratio: float
    first_seen_at: datetime
    last_seen_at: datetime
    inauthenticity_score: float
    risk_label: str
    platforms: list[str]
    platform_breakdown: dict[str, int]
    activity: list[NarrativeActivityPoint]   # daily buckets, last 30 days
    top_accounts: list[NarrativeTopAccount]  # MODERATE+ accounts only — filtered per the rule
    samples: list[NarrativeSample]           # 15 most recent comments
    ai_analysis: str
    ai_provider: str

    # ---- New coordination intelligence fields (Phase 9) -------------------
    risk_tier: str = "low"                   # low | moderate | high | extreme
    coordination_score: float = 0.0
    manipulation_probability: float = 0.0
    synchronization_intensity: float = 0.0
    semantic_cohesion: float = 0.0
    cluster_confidence: int = 0
    coordination_label: str = "unscored"
    qualifying_member_count: int = 0
    qualifying_author_count: int = 0
    signal_breakdown: list[NarrativeSignalBreakdown] = Field(default_factory=list)
    propagation: list[NarrativePropagationPoint] = Field(default_factory=list)
    bursts: list[NarrativeBurst] = Field(default_factory=list)
    origin: NarrativeOriginWindow | None = None
    graph: NarrativeGraph = Field(default_factory=lambda: NarrativeGraph(nodes=[], edges=[]))


# ---------------------------------------------------------------------------
# Phase 10 — Content intelligence schemas
# ---------------------------------------------------------------------------


class ContentEntitySummary(BaseModel):
    id: int
    platform: str
    content_id: str
    kind: str
    title: str | None = None
    author_external_id: str | None = None
    author_handle: str | None = None
    canonical_url: str | None = None
    thumbnail_url: str | None = None
    total_batches: int
    total_comments_collected: int
    total_distinct_authors: int
    contributor_count: int
    latest_coordination_score: float
    latest_risk_tier: str
    latest_tier_distribution: dict[str, int] = Field(default_factory=dict)
    reply_pod_count: int = 0
    first_scanned_at: datetime
    last_scanned_at: datetime


class CommentBatchOut(BaseModel):
    id: int
    fetched_at: datetime
    comments_fetched: int
    new_comments: int
    duplicates: int
    distinct_authors: int
    new_authors: int
    coordination_score: float
    risk_tier: str
    tier_distribution: dict[str, int] = Field(default_factory=dict)
    summary: str | None = None
    has_more: bool = False    # true iff the platform left a continuation cursor


class ContentCommentOut(BaseModel):
    id: int
    external_comment_id: str
    author_external_id: str
    author_handle: str | None = None
    text: str
    like_count: int | None = None
    reply_count: int | None = None
    observed_at: datetime
    first_batch_id: int


class ContentEntityDetail(BaseModel):
    entity: ContentEntitySummary
    batches: list[CommentBatchOut]
    recent_comments: list[ContentCommentOut]
    total_comments: int
    # True iff the platform's pagination cursor for this entity is still live
    # — meaning a "+ New batch" scan would resume from where the last one
    # stopped (cheap, fast, only ingests new comments) rather than restart
    # from page 1 (slow, mostly dedupes).
    has_continuation: bool = False


class ContentEntityListResponse(BaseModel):
    total: int
    platform: str | None = None
    entities: list[ContentEntitySummary]


class ContentCommentsResponse(BaseModel):
    total: int
    comments: list[ContentCommentOut]


class BatchDiffResponse(BaseModel):
    """Comparison between two batches of the same content entity.

    Surfaces what changed since the previous scan — coordination drift,
    new authors, sample comments — so an analyst running a re-scan sees
    "what's new" in one glance instead of having to scroll the whole
    batch history.
    """
    from_batch: CommentBatchOut
    to_batch: CommentBatchOut
    coordination_score_delta: float
    risk_tier_changed: bool
    tier_distribution_delta: dict[str, int]
    new_comment_count: int
    new_author_count: int
    new_authors: list[str]
    sample_new_comments: list[ContentCommentOut]


class AuthorContentRow(BaseModel):
    entity: ContentEntitySummary
    comment_count: int
    first_comment: datetime
    last_comment: datetime
    sample_text: str


class AuthorPresenceResponse(BaseModel):
    platform: str
    author_external_id: str
    author_handle: str | None = None
    total_comments: int
    content_count: int
    first_seen: datetime | None = None
    last_seen: datetime | None = None
    entities: list[AuthorContentRow]


class AuthorCommentRow(BaseModel):
    """One comment by an author, with the content entity it was posted on."""

    comment: ContentCommentOut
    entity: ContentEntitySummary


class AuthorCommentsResponse(BaseModel):
    """Every comment we've seen one author make on a platform."""

    platform: str
    author_external_id: str
    author_handle: str | None = None
    total: int
    comments: list[AuthorCommentRow]


class AccountAnalysisResponse(BaseModel):
    """LLM (or template) behavioural analysis for a single account."""

    platform: str
    external_id: str
    handle: str
    analysis: str
    provider: str   # "template" | "anthropic-claude-haiku-..."


class AccountHistoryResponse(BaseModel):
    """Full history snapshot for an account.

    Used by the OMISPHERE web app's account page to plot the score curve
    over time and surface a rising/falling/stable/volatile trend chip.
    """

    platform: Platform
    external_id: str
    handle: str
    display_name: str | None = None
    bio: str | None = None
    follower_count: int | None = None
    account_created_at: datetime | None = None
    first_seen_at: datetime | None = None
    last_scanned_at: datetime | None = None
    scans: list[HistoricalScan]
    total_scans: int = 0  # total persisted scans (may exceed len(scans) if page-limited)
    trend: TrendInfo


# ---------------------------------------------------------------------------
# Phase 12 — Ground-truth labels
# ---------------------------------------------------------------------------


LABEL_KINDS = (
    "bot", "human", "unclear", "commercial_spam", "political_coord",
    "engagement_farm", "ai_content", "suspended",
)
LABEL_SOURCES = ("manual", "youtube_suspension", "imported_dataset", "synthetic")
LABEL_CONFIDENCES = ("high", "medium")


class AccountLabelOut(BaseModel):
    id: int
    account_id: int
    user_id: int | None
    user_email: str | None = None
    platform: str
    external_id: str
    handle: str | None = None
    label: str
    expected_tier: str
    confidence: str
    source: str
    rationale: str | None = None
    created_at: datetime


class AccountLabelCreate(BaseModel):
    """Create a label by referring to an account that's already been scanned.

    Provide the account either by its DB ID (preferred when coming from the
    UI which already has it) or by (platform, external_id) for scripts.
    """

    account_id: int | None = None
    platform: str | None = None
    external_id: str | None = None
    label: str
    expected_tier: str
    confidence: str = "medium"
    rationale: str | None = None


class AccountLabelsListResponse(BaseModel):
    total: int
    labels: list[AccountLabelOut]
    by_label: dict[str, int]
    by_source: dict[str, int]


class CalibrationFixtureCase(BaseModel):
    """Shaped like the synthetic calibration JSON so scripts/calibrate.py
    can swap data sources without further code changes."""

    label: str
    expected_tier: str
    expected_probability: float | None = None
    profile: dict
    posts: list[dict]


class CalibrationFixtureResponse(BaseModel):
    n_cases: int
    by_label: dict[str, int]
    by_source: dict[str, int]
    cases: list[CalibrationFixtureCase]


# ---------------------------------------------------------------------------
# Feature: Cross-scan account search  (/v1/accounts/search)
# ---------------------------------------------------------------------------


class AccountSearchResult(BaseModel):
    external_id: str
    platform: str
    handle: str
    display_name: str | None = None
    tier: Tier | None = None
    overall_probability: float | None = None
    last_scanned_at: datetime | None = None
    first_seen_at: datetime | None = None
    follower_count: int | None = None


class AccountSearchResponse(BaseModel):
    query: str
    platform: str
    results: list[AccountSearchResult]


# ---------------------------------------------------------------------------
# Feature: Activity log  (/v1/activity)
# ---------------------------------------------------------------------------


class ActivityEntry(BaseModel):
    id: int
    created_at: datetime
    platform: str
    scan_type: str
    credits_cost: int
    target_input: str | None = None
    success: bool
    refunded: bool = False


class ActivityLogResponse(BaseModel):
    entries: list[ActivityEntry]
    total: int
    limit: int
    offset: int
    credits_spent_total: int
    credits_refunded_total: int


# ---------------------------------------------------------------------------
# Feature: Investigation verdict  (/v1/investigations/{slug} PATCH)
# ---------------------------------------------------------------------------

INVESTIGATION_VERDICTS = (
    "pending",
    "confirmed_bot_ring",
    "likely_inauthentic",
    "mixed",
    "likely_authentic",
    "inconclusive",
)

VERDICT_LABELS: dict[str, str] = {
    "pending": "Pending",
    "confirmed_bot_ring": "Confirmed bot ring",
    "likely_inauthentic": "Likely inauthentic",
    "mixed": "Mixed",
    "likely_authentic": "Likely authentic",
    "inconclusive": "Inconclusive",
}


class VerdictUpdate(BaseModel):
    verdict: str | None = None
    notes: str | None = None


# ---------------------------------------------------------------------------
# Feature: Bulk scan queue  (/v1/scan/bulk)
# ---------------------------------------------------------------------------


class BulkScanRequest(BaseModel):
    urls: list[str] = Field(min_length=1, max_length=20, description="Up to 20 video or channel URLs.")
    max_commenters: int = Field(default=100, ge=5, le=300)


class BulkScanJobResult(BaseModel):
    url: str
    status: str  # "pending" | "running" | "ok" | "failed"
    slug: str | None = None
    tier: str | None = None
    probability: float | None = None
    error: str | None = None


class BulkScanJobSummary(BaseModel):
    job_id: str
    status: str  # "queued" | "running" | "done" | "failed"
    total: int
    completed: int
    failed_count: int
    credits_estimate: int
    credits_used: int
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None


class BulkScanJobResponse(BaseModel):
    job: BulkScanJobSummary
    results: list[BulkScanJobResult]


class BulkScanJobsListResponse(BaseModel):
    jobs: list[BulkScanJobSummary]


# ---------------------------------------------------------------------------
# Phase B: Channel-level deep intelligence  (/v1/channels/{platform}/{id}/intelligence)
# ---------------------------------------------------------------------------


class ChannelVideoSummary(BaseModel):
    content_id: str
    title: str | None = None
    canonical_url: str | None = None
    thumbnail_url: str | None = None
    total_batches: int
    total_comments_collected: int
    total_distinct_authors: int
    latest_coordination_score: float
    latest_risk_tier: str
    latest_tier_distribution: dict[str, int] = Field(default_factory=dict)
    first_scanned_at: datetime
    last_scanned_at: datetime


class ChannelRiskPoint(BaseModel):
    content_id: str
    date: datetime
    coordination_score: float
    risk_tier: str
    comment_count: int


class ChannelTopCommenter(BaseModel):
    external_id: str
    platform: str
    handle: str
    video_count: int
    tier: str | None = None
    overall_probability: float | None = None


class ChannelAudienceComposition(BaseModel):
    high: int
    elevated: int
    moderate: int
    low: int
    total_commenters: int


# ---------------------------------------------------------------------------
# Phase C: Reply tree + engagement pods  (/v1/content/{platform}/{id}/reply-tree)
# ---------------------------------------------------------------------------


class ReplyTreeNode(BaseModel):
    comment_id: str
    parent_comment_id: str | None = None
    author_external_id: str
    author_handle: str | None = None
    author_tier: str | None = None
    text: str
    like_count: int | None = None
    reply_count: int | None = None
    posted_at: datetime
    # Direct replies (one level deep). YouTube exposes replies as a flat
    # list under each top-level comment, so the tree is effectively 2-tier.
    replies: list["ReplyTreeNode"] = Field(default_factory=list)
    # Reply-pod id this node belongs to, if the pod detector flagged it.
    # Frontend uses this to colour-code the tree.
    pod_id: int | None = None


class ReplyTreeResponse(BaseModel):
    platform: str
    content_id: str
    total_comments: int
    top_level_count: int
    reply_count: int
    roots: list[ReplyTreeNode]


class ReplyPodMember(BaseModel):
    external_id: str
    handle: str | None = None
    tier: str | None = None
    overall_probability: float | None = None


class ReplyPodOut(BaseModel):
    pod_id: int
    score: float
    members: list[ReplyPodMember]
    evidence: list[str]
    interaction_count: int


class ReplyPodsResponse(BaseModel):
    platform: str
    content_id: str
    pod_count: int
    pods: list[ReplyPodOut]


class ChannelIntelligenceResponse(BaseModel):
    platform: str
    external_id: str
    handle: str
    display_name: str | None = None
    bio: str | None = None
    follower_count: int | None = None
    first_seen_at: datetime | None = None
    last_scanned_at: datetime | None = None
    video_count: int
    videos: list[ChannelVideoSummary]
    audience_composition: ChannelAudienceComposition
    risk_trend: list[ChannelRiskPoint]
    top_commenters: list[ChannelTopCommenter]
    # Aggregate engagement velocity: average comments per scanned video.
    # Computed across all videos in the result set.
    avg_comments_per_video: float = 0.0
    # Returning users: distinct commenters appearing on 2+ videos / total
    # distinct commenters across all videos. High values mean a tight,
    # loyal audience; very high values (with low video count) can hint at
    # synthetic engagement.
    returning_commenter_ratio: float = 0.0
