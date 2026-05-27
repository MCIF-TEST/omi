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
    """One past scan of an account, lightweight (no full signals payload)."""

    scanned_at: datetime
    overall_probability: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    tier: Tier
    summary: str


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


class NarrativesResponse(BaseModel):
    """List of trending narratives + the embedding stack identifier."""

    window_days: int
    embedder: str
    narratives: list[NarrativeOut]


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
    trend: TrendInfo
