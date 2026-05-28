"""SQLAlchemy models for the self-improving fingerprint store.

Schema choices:

* ``Account`` is keyed on (platform, external_id) — the platform's stable
  identifier (YouTube channel ID, X user ID). The visible handle is mutable
  and is stored for display only.
* ``Account.fingerprint_json`` holds the latest normalized fingerprint
  vector for fast nearest-neighbor lookup; the full scan history lives in
  ``Scan`` rows and is never garbage-collected (the value of the dataset
  grows monotonically).
* ``VideoScan`` records each ``/v1/scan/youtube/video`` invocation so a UI
  can show "this video has been scanned N times before" without re-querying.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Account(Base):
    __tablename__ = "accounts"
    __table_args__ = (UniqueConstraint("platform", "external_id", name="uq_account_platform_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    platform: Mapped[str] = mapped_column(String(32), index=True)
    external_id: Mapped[str] = mapped_column(String(128), index=True)
    handle: Mapped[str] = mapped_column(String(255))
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    bio: Mapped[str | None] = mapped_column(Text, nullable=True)
    follower_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    following_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    account_created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    last_scanned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_tier: Mapped[str | None] = mapped_column(String(16), nullable=True)
    last_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Normalized fixed-width vector. Stored as JSON for portability; for
    # large-scale deployments swap to pgvector / Qdrant.
    fingerprint_json: Mapped[list[float] | None] = mapped_column(JSON, nullable=True)

    scans: Mapped[list["Scan"]] = relationship(
        back_populates="account",
        cascade="all, delete-orphan",
        order_by="Scan.scanned_at.desc()",
    )


class Scan(Base):
    __tablename__ = "scans"
    # Composite for account_history (Phase 2): equality on account_id +
    # ordering on scanned_at DESC.
    __table_args__ = (
        Index("ix_scan_account_time", "account_id", "scanned_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), index=True
    )
    scanned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, index=True
    )

    overall_probability: Mapped[float] = mapped_column(Float)
    confidence: Mapped[float] = mapped_column(Float)
    tier: Mapped[str] = mapped_column(String(16))
    summary: Mapped[str] = mapped_column(Text)
    signals_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON)

    account: Mapped[Account] = relationship(back_populates="scans")


class VideoScan(Base):
    """Aggregate record of a video-level scan."""

    __tablename__ = "video_scans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    platform: Mapped[str] = mapped_column(String(32), index=True)
    video_id: Mapped[str] = mapped_column(String(128), index=True)
    scanned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    commenter_count: Mapped[int] = mapped_column(Integer, default=0)
    fresh_count: Mapped[int] = mapped_column(Integer, default=0)
    cached_count: Mapped[int] = mapped_column(Integer, default=0)
    quota_used: Mapped[int] = mapped_column(Integer, default=0)

    high_count: Mapped[int] = mapped_column(Integer, default=0)
    elevated_count: Mapped[int] = mapped_column(Integer, default=0)
    moderate_count: Mapped[int] = mapped_column(Integer, default=0)
    low_count: Mapped[int] = mapped_column(Integer, default=0)

    coordination_score: Mapped[float | None] = mapped_column(Float, nullable=True)


class CommenterEngagement(Base):
    """Persistent edge: this commenter has been observed engaging with this
    parent content (a video for YouTube, a thread for Reddit, etc.).

    Source for the co-engagement / "fellow travelers" detector. We populate
    one row per (account, parent_id) pair extracted from each commenter's
    recent post history. The unique constraint keeps the index small as
    operators re-scan the same accounts.
    """

    __tablename__ = "commenter_engagements"
    __table_args__ = (
        UniqueConstraint(
            "platform", "account_external_id", "parent_id",
            name="uq_engagement_account_parent",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    platform: Mapped[str] = mapped_column(String(32), index=True)
    account_external_id: Mapped[str] = mapped_column(String(128), index=True)
    parent_id: Mapped[str] = mapped_column(String(128), index=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


# func is imported only to keep alembic-style auto-generated DDL stable; mark used.
_ = func


# ---------------------------------------------------------------------------
# Multi-tenant tables: users + scan log + (future) billing.
#
# These are added in the public-launch update; existing single-user installs
# can keep running without them touched (no FKs into existing tables yet).
# ---------------------------------------------------------------------------


class User(Base):
    """A paying-or-trial user of the OMI service."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Credits remaining (refilled monthly when the subscription renews; also
    # bumped by one-off purchases). Each comprehensive scan costs one credit.
    credits_remaining: Mapped[int] = mapped_column(Integer, default=3)  # 3 free trial credits

    # Stripe linkage
    stripe_customer_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    stripe_subscription_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    subscription_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    subscription_renews_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Soft role flag — set manually in the DB for now. Future: admin panel.
    is_admin: Mapped[bool] = mapped_column(Integer, default=0)

    # Notification preferences. Default ON for email (uses User.email),
    # OFF for webhook (must be explicitly configured).
    notify_alerts_email: Mapped[int] = mapped_column(Integer, default=1)
    notify_alerts_webhook: Mapped[int] = mapped_column(Integer, default=0)
    webhook_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Anti-abuse: hash of the IP this user signed up from. Used by signup to
    # detect duplicate-IP signups (multiple "free trial" accounts from one
    # household). Raw IP never stored.
    signup_ip_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    # Referral system. Every user gets a short URL-safe code at signup. When
    # a friend signs up with this code, the referrer gets +3 credits at
    # signup and +5 more when the referred user starts a subscription.
    referral_code: Mapped[str | None] = mapped_column(String(16), nullable=True, unique=True, index=True)
    referred_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True,
    )
    referral_credits_earned: Mapped[int] = mapped_column(Integer, default=0)
    # Idempotency guard: ensures the subscription-conversion bonus is paid
    # only once even if Stripe sends the subscription.created event twice.
    referral_subscription_bonus_paid: Mapped[int] = mapped_column(Integer, default=0)


class ScanLog(Base):
    """One row per scan a user initiates. Auditable history + analytics."""

    __tablename__ = "scan_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, index=True
    )
    platform: Mapped[str] = mapped_column(String(32))
    scan_type: Mapped[str] = mapped_column(String(32))   # "comprehensive", "account", etc.
    credits_cost: Mapped[int] = mapped_column(Integer, default=1)
    target_input: Mapped[str | None] = mapped_column(String(500), nullable=True)
    success: Mapped[int] = mapped_column(Integer, default=1)


class DemoScanLog(Base):
    """One row per anonymous demo scan. Used to enforce IP-based rate limits
    so the free demo can't be abused. IPs are hashed (never stored raw) so
    this is GDPR-friendly even though it gates abuse-control."""

    __tablename__ = "demo_scan_logs"
    __table_args__ = (
        Index("ix_demo_ip_created", "ip_hash", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ip_hash: Mapped[str] = mapped_column(String(64), index=True)
    video_id: Mapped[str] = mapped_column(String(64))
    user_agent_snippet: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, index=True,
    )
    success: Mapped[int] = mapped_column(Integer, default=1)


class BillingEvent(Base):
    """Inbound Stripe webhook events. Stored idempotent by event id."""

    __tablename__ = "billing_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    stripe_event_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


# ---------------------------------------------------------------------------
# Narrative intelligence (Phase 3) — cluster of similar comments across the
# entire corpus. Centroid + member count + last-seen drives the trending
# narratives feed.
# ---------------------------------------------------------------------------


class Narrative(Base):
    """A semantic cluster of comments that share a topic / framing.

    Centroid is the running-average embedding of all members; we update
    it incrementally as new members are added.
    """

    __tablename__ = "narratives"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # An auto-generated representative excerpt — closest member to centroid
    # when the narrative was last summarized.
    label: Mapped[str] = mapped_column(String(280), default="")
    centroid_json: Mapped[list[float]] = mapped_column(JSON)
    dimensions: Mapped[int] = mapped_column(Integer, default=384)
    member_count: Mapped[int] = mapped_column(Integer, default=0, index=True)
    # Number of distinct accounts contributing — high = wide spread.
    distinct_authors: Mapped[int] = mapped_column(Integer, default=0)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, index=True)


# ---------------------------------------------------------------------------
# Graph + coordination intelligence (Phase 4) — persistent, cumulative
# coordination edges across every scan. Symmetric (account_a < account_b
# at write time so we never store both directions).
# ---------------------------------------------------------------------------


class CoordinationEdge(Base):
    __tablename__ = "coordination_edges"
    __table_args__ = (
        UniqueConstraint(
            "platform", "account_a", "account_b",
            name="uq_coord_edge_pair",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    platform: Mapped[str] = mapped_column(String(32), index=True)
    account_a: Mapped[str] = mapped_column(String(128), index=True)
    account_b: Mapped[str] = mapped_column(String(128), index=True)
    # Number of distinct per-scan clusters where this pair co-occurred.
    observation_count: Mapped[int] = mapped_column(Integer, default=0)
    # Set of detector method names that have flagged this pair, JSON list.
    methods_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    # Mean per-cluster score across all observations (running average).
    mean_cluster_score: Mapped[float] = mapped_column(Float, default=0.0)
    # Most recent video / parent_id the pair were observed under (for drill-down).
    last_shared_parent: Mapped[str | None] = mapped_column(String(128), nullable=True)
    first_observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    last_observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, index=True)


# ---------------------------------------------------------------------------
# Investigations (Phase 5) — persistent record of a user's scan with stable
# URL slug. Continuation batches append to the same investigation so the
# user has one canonical record per piece of work.
# ---------------------------------------------------------------------------


class Investigation(Base):
    __tablename__ = "investigations"
    # Composite for /v1/investigations (dashboard list): equality on
    # user_id + ordering by created_at DESC.
    __table_args__ = (
        Index("ix_inv_user_created", "user_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    # Short URL-safe id (e.g. ``inv_a1b2c3d4``) — stable across redeploys.
    slug: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    # Auto-generated human label.
    label: Mapped[str] = mapped_column(String(280))
    # The raw input the user pasted.
    input_url: Mapped[str] = mapped_column(String(500))
    # Resolved primary target id (video id, channel id, etc.) — for joins.
    target_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    kind: Mapped[str] = mapped_column(String(32))   # "video" | "channel" | "comprehensive"
    overall_probability: Mapped[float] = mapped_column(Float, default=0.0)
    overall_tier: Mapped[str] = mapped_column(String(16), default="low")
    summary: Mapped[str] = mapped_column(Text, default="")
    quota_used: Mapped[int] = mapped_column(Integer, default=0)
    batch_count: Mapped[int] = mapped_column(Integer, default=1)
    # Full serialized ComprehensiveScanResult payload. We replace this on
    # continuation batches with the merged result.
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    # Phase 6: public sharing — opt-in, revocable token.
    share_token: Mapped[str | None] = mapped_column(String(48), nullable=True, unique=True, index=True)
    is_public: Mapped[bool] = mapped_column(Integer, default=0)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Phase 7: cached analyst-style commentary. Populated on demand; survives
    # across reloads so we don't re-spend tokens.
    commentary_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    commentary_provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    commentary_tokens_used: Mapped[int] = mapped_column(Integer, default=0)
    commentary_generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Analyst verdict — set by the user to mark the investigation concluded.
    verdict: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    concluded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


# ---------------------------------------------------------------------------
# Monitoring (Phase 8) — watchlists + alerts + anomaly feed.
# ---------------------------------------------------------------------------


class Watchlist(Base):
    __tablename__ = "watchlists"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "kind", "target_id",
            name="uq_watchlist_user_target",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(32))   # "channel" | "narrative"
    target_id: Mapped[str] = mapped_column(String(128), index=True)
    label: Mapped[str] = mapped_column(String(280), default="")
    # Tier threshold at which an alert fires — alerts only when current tier
    # is at or above this rank. Stored as string for clarity.
    alert_threshold_tier: Mapped[str] = mapped_column(String(16), default="moderate")
    # Last observed tier / probability — used to detect changes.
    last_seen_tier: Mapped[str | None] = mapped_column(String(16), nullable=True)
    last_seen_probability: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_alert_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class Alert(Base):
    __tablename__ = "alerts"
    __table_args__ = (
        Index("ix_alert_user_created", "user_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True,
    )
    watchlist_id: Mapped[int | None] = mapped_column(
        ForeignKey("watchlists.id", ondelete="SET NULL"), nullable=True, index=True,
    )
    # "tier_change" | "narrative_spike" | "high_tier_surge"
    kind: Mapped[str] = mapped_column(String(32), index=True)
    severity: Mapped[str] = mapped_column(String(16), default="info")
    message: Mapped[str] = mapped_column(Text)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, index=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Delivery tracking — when the alert was sent to email/webhook channels
    # and any error encountered. NULL delivered_at = not yet delivered.
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    delivery_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    delivery_error: Mapped[str | None] = mapped_column(String(500), nullable=True)


class NarrativeMembership(Base):
    """One comment that belongs to a narrative."""

    __tablename__ = "narrative_memberships"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    narrative_id: Mapped[int] = mapped_column(
        ForeignKey("narratives.id", ondelete="CASCADE"), index=True
    )
    platform: Mapped[str] = mapped_column(String(32), index=True)
    account_external_id: Mapped[str] = mapped_column(String(128), index=True)
    parent_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    comment_text: Mapped[str] = mapped_column(Text)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, index=True)


# ---------------------------------------------------------------------------
# Phase 10 — Universal content intelligence database.
#
# Every analysed video / post / thread becomes a persistent ContentEntity.
# Each scan adds a CommentBatch under that entity, and individual comments
# are deduplicated into ContentComment rows. Intelligence (coordination
# scores, tier distribution, narrative drift) is recomputed across all
# accumulated batches — the more the platform is used, the smarter it gets.
# ---------------------------------------------------------------------------


class ContentEntity(Base):
    """Master intelligence record for one piece of content.

    Keyed on ``(platform, content_id)`` — the platform-native identifier
    (YouTube video ID, X status ID, Reddit submission ID, etc.). Shared
    across all users: anyone scanning the same content contributes to the
    same record.
    """

    __tablename__ = "content_entities"
    __table_args__ = (
        UniqueConstraint("platform", "content_id", name="uq_content_platform_id"),
        Index("ix_content_last_scan", "platform", "last_scanned_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    platform: Mapped[str] = mapped_column(String(32), index=True)
    content_id: Mapped[str] = mapped_column(String(128), index=True)
    kind: Mapped[str] = mapped_column(String(32), default="video")    # video | post | thread

    # Display metadata — populated opportunistically from scan responses.
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    author_external_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    author_handle: Mapped[str | None] = mapped_column(String(255), nullable=True)
    canonical_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    thumbnail_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Cumulative counters — updated each time a new batch is recorded.
    total_batches: Mapped[int] = mapped_column(Integer, default=0)
    total_comments_collected: Mapped[int] = mapped_column(Integer, default=0)
    total_distinct_authors: Mapped[int] = mapped_column(Integer, default=0)
    # Number of distinct users (User.id) who have contributed batches.
    contributor_count: Mapped[int] = mapped_column(Integer, default=0)

    # Latest aggregate intelligence (denormalized for fast list rendering).
    latest_coordination_score: Mapped[float] = mapped_column(Float, default=0.0)
    latest_risk_tier: Mapped[str] = mapped_column(String(16), default="low")
    latest_tier_distribution: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    latest_reply_pod_count: Mapped[int] = mapped_column(Integer, default=0)

    # Timestamps
    first_scanned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    last_scanned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, index=True)


class CommentBatch(Base):
    """One ingestion event for a ContentEntity.

    Each scan a user performs against the same content produces a new
    batch. Batches are immutable — they record the snapshot at scan time.
    """

    __tablename__ = "comment_batches"
    __table_args__ = (
        Index("ix_batch_content_time", "content_entity_id", "fetched_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    content_entity_id: Mapped[int] = mapped_column(
        ForeignKey("content_entities.id", ondelete="CASCADE"), index=True
    )
    # The user who triggered this batch (NULL = system / unauthenticated).
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True,
    )
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, index=True,
    )

    # Raw counts — what the platform returned for this batch.
    comments_fetched: Mapped[int] = mapped_column(Integer, default=0)
    new_comments: Mapped[int] = mapped_column(Integer, default=0)        # deduplicated against existing batches
    duplicates: Mapped[int] = mapped_column(Integer, default=0)
    distinct_authors: Mapped[int] = mapped_column(Integer, default=0)
    new_authors: Mapped[int] = mapped_column(Integer, default=0)         # authors first seen in this batch

    # Aggregate intelligence at the time of this batch.
    coordination_score: Mapped[float] = mapped_column(Float, default=0.0)
    risk_tier: Mapped[str] = mapped_column(String(16), default="low")
    tier_distribution: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    # Optional per-batch payload — short summary or note from the orchestrator.
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Platform pagination cursor — pass to the next scan of this content to
    # resume fetching new comments instead of re-reading the same ones.
    # ``None`` means we've exhausted the thread.
    next_page_token: Mapped[str | None] = mapped_column(String(500), nullable=True)


class ContentComment(Base):
    """One comment under a ContentEntity, deduplicated across batches.

    Comments are keyed on ``(content_entity_id, external_comment_id)`` so
    that re-scanning the same content never inserts the same comment twice.
    ``first_batch_id`` records which batch first observed this comment, so
    longitudinal analysis can ask "which batch did this user first appear in".
    """

    __tablename__ = "content_comments"
    __table_args__ = (
        UniqueConstraint(
            "content_entity_id", "external_comment_id",
            name="uq_content_comment_id",
        ),
        Index(
            "ix_comment_content_observed",
            "content_entity_id", "observed_at",
        ),
        Index(
            "ix_comment_content_author",
            "content_entity_id", "author_external_id",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    content_entity_id: Mapped[int] = mapped_column(
        ForeignKey("content_entities.id", ondelete="CASCADE"), index=True
    )
    first_batch_id: Mapped[int] = mapped_column(
        ForeignKey("comment_batches.id", ondelete="CASCADE"), index=True
    )
    external_comment_id: Mapped[str] = mapped_column(String(128), index=True)
    parent_comment_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    author_external_id: Mapped[str] = mapped_column(String(128), index=True)
    author_handle: Mapped[str | None] = mapped_column(String(255), nullable=True)
    text: Mapped[str] = mapped_column(Text)
    like_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reply_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, index=True,
    )


# ============================================================================
# Phase 12 — Ground-truth labeling for calibration
# ============================================================================

class AccountLabel(Base):
    """Operator-supplied ground-truth judgment on an account's true nature.

    Drives the calibration harness's --from-db mode: instead of running the
    engine against a synthetic JSON fixture, we run it against accounts the
    operators have labeled and compare the predicted tier against the labeled
    expectation. This is how the system improves over time on real data
    instead of a stale benchmark.

    One row per (account, user) so two reviewers can independently label the
    same account — disagreement is itself a signal the case is genuinely
    ambiguous.

    Provenance is tracked so we can weight 'manual' labels differently from
    'youtube_suspension' labels (the latter come straight from YouTube's own
    moderation actions and are higher-confidence ground truth).
    """

    __tablename__ = "account_labels"
    __table_args__ = (
        UniqueConstraint("account_id", "user_id", name="uq_account_label_per_user"),
        Index("ix_account_label_source", "source", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), index=True
    )
    # Nullable because youtube_suspension labels aren't owned by any user.
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # Categorical verdict: what the labeler thinks this account *is*.
    # 'bot' | 'human' | 'unclear' | 'commercial_spam' | 'political_coord'
    # | 'engagement_farm' | 'ai_content' | 'suspended'
    label: Mapped[str] = mapped_column(String(32), index=True)

    # The tier the labeler thinks the OMI engine *should* return for this
    # account. Used by the calibration harness as the ground-truth target.
    expected_tier: Mapped[str] = mapped_column(String(16))

    # 'high' | 'medium' — how confident the labeler is in this judgment.
    # Low-confidence labels are still kept (they're useful for spotting
    # genuinely ambiguous cases) but the harness can filter on this.
    confidence: Mapped[str] = mapped_column(String(8), default="medium")

    # 'manual' | 'youtube_suspension' | 'imported_dataset'
    source: Mapped[str] = mapped_column(String(32), default="manual")

    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, index=True,
    )

    account: Mapped["Account"] = relationship()


# ---------------------------------------------------------------------------
# Bulk scan jobs — queue of URLs submitted for background processing.
# ---------------------------------------------------------------------------


class ScanJob(Base):
    """A user-submitted batch of URLs to scan sequentially in the background."""

    __tablename__ = "scan_jobs"
    __table_args__ = (
        Index("ix_scanjob_user_created", "user_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Stable public identifier exposed in the API (avoids leaking DB row IDs).
    job_id: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    # JSON list of URLs submitted by the user.
    urls_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    # JSON list of BulkScanJobResult dicts, one per URL (appended as items complete).
    results_json: Mapped[list[dict]] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(16), default="queued", index=True)
    total: Mapped[int] = mapped_column(Integer, default=0)
    completed: Mapped[int] = mapped_column(Integer, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, default=0)
    credits_estimate: Mapped[int] = mapped_column(Integer, default=0)
    credits_used: Mapped[int] = mapped_column(Integer, default=0)
    max_commenters: Mapped[int] = mapped_column(Integer, default=100)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

