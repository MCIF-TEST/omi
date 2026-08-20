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
    Boolean,
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

    # Clerk identity linkage (auth provider). Set when a user signs in via Clerk; the local row still
    # owns credits/subscription/investigations, keyed to the Clerk user by this id (linked by email on
    # first Clerk sign-in so existing accounts keep their data).
    clerk_user_id: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True, index=True)

    # Stripe linkage
    stripe_customer_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    stripe_subscription_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    subscription_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    subscription_renews_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Which plan this account is entitled to (a slug from app/core/plans.py). Written when an
    # invoice is paid, from the Stripe Price on that invoice, so the entitlement always comes from
    # money that actually moved rather than from what a client claimed.
    #
    # NULL means Free, and every read goes through ``plans.get_tier`` which maps NULL and any
    # unknown slug to Free. Failing closed matters here: rows written before this column existed
    # (i.e. every current subscriber) must not resolve to a paid tier by accident, and a customer
    # wrongly shown Free can fix it in one click while the reverse gives the product away.
    plan_tier: Mapped[str | None] = mapped_column(String(32), nullable=True)

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

    # Password reset. We store only a SHA-256 hash of the reset token (never
    # the raw token), with a short expiry. Cleared after a successful reset
    # so a token is single-use.
    reset_token_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    reset_token_expires: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


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

    # --- Cross-scan evidence accumulation (the planet-scale layer) ---------------------------
    # Accumulated log10 likelihood ratio for this pair across every post it has been seen on,
    # already discounted for context correlation. This is what makes a pair that was merely
    # suspicious on one post decisive after being seen again on an unrelated one, and it is the
    # entire reason tracking operations globally improves accuracy rather than just storage.
    log_lr_sum: Mapped[float] = mapped_column(Float, default=0.0)
    # Which evidence families have ever fired on this pair, JSON list. Distinct from methods_json,
    # which is per-detector: families are the independence unit the probability model combines on.
    families_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    # The distinct posts this pair co-occurred under, capped. Replaces relying on
    # last_shared_parent, which is overwritten on every observation and so destroys exactly the
    # history this feature needs: without it there is no way to tell one post seen twice from two
    # different posts, and only the second is independent evidence.
    contexts_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    # Platforms this pair has been seen on. A cross-platform pair carries both.
    platforms_json: Mapped[list[str]] = mapped_column(JSON, default=list)


# ---------------------------------------------------------------------------
# Campaign intelligence — a detected coordination cluster materialized as a
# first-class, EVOLVING asset. Principle: store OBSERVED EVIDENCE, never a
# verdict-as-truth. Each re-detection appends a CampaignObservation and the
# aggregate fields are recomputed, so later evidence can change the picture; no
# boolean "this is a manipulation campaign" is ever stored. Recurrence is found
# by member-set overlap. This is the cluster-shaped object the per-scan pipeline
# used to discard (only pairwise CoordinationEdges + a scalar survived).
# ---------------------------------------------------------------------------


class Campaign(Base):
    __tablename__ = "campaigns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    campaign_key: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(280), default="")
    platform: Mapped[str] = mapped_column(String(32), index=True)
    # Observed coordination — the LATEST and the strongest ever seen. Not a
    # verdict: these are measurements that future observations can move.
    coordination_score: Mapped[float] = mapped_column(Float, default=0.0, index=True)
    max_coordination_score: Mapped[float] = mapped_column(Float, default=0.0)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    member_count: Mapped[int] = mapped_column(Integer, default=0, index=True)
    # Recurrence: how many distinct detections have rolled into this campaign.
    observation_count: Mapped[int] = mapped_column(Integer, default=0, index=True)
    methods_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    hashtags_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    mentions_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    # Representative evidence strings from the detectors (capped) + a theme.
    evidence_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    theme: Mapped[str | None] = mapped_column(String(280), nullable=True)
    # Descriptive observation state ("observed" / "recurring"), NOT a verdict.
    status: Mapped[str] = mapped_column(String(24), default="observed")
    first_detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, index=True)
    # Opt-in public sharing (mirrors Investigation): read-only, revocable,
    # token-gated. share_token is the public handle; is_public gates the public
    # report; published_at stamps the first share. Nullable + default-off so
    # existing campaigns are private until explicitly shared.
    share_token: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_public: Mapped[int] = mapped_column(Integer, default=0)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # --- Operation-level tracking ---------------------------------------------------------------
    # Calibrated P(coordinated) for this operation, distinct from `coordination_score` which is the
    # legacy 0..1 detector output. Kept as a separate column rather than overwriting the old one so
    # campaigns recorded by the per-scan engine and by the cohort detector stay distinguishable.
    posterior: Mapped[float] = mapped_column(Float, default=0.0)
    # MinHash sketch over the operation's BEHAVIOUR (script, handle factory, provisioning shape,
    # tooling), never over its account ids. This is what lets an operation be recognised after it
    # burns every account it was using: member overlap cannot, because there is no overlap.
    signature_json: Mapped[list[int] | None] = mapped_column(JSON, nullable=True)
    # "detected" for something this deployment observed, "disclosure" for a known operation seeded
    # from a public archive. A disclosure row has a signature and no live members.
    origin: Mapped[str] = mapped_column(String(24), default="detected")
    # Set when an operation has not been observed for the dormancy window; cleared on resurfacing.
    dormant_since: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resurfaced_count: Mapped[int] = mapped_column(Integer, default=0)
    platforms_json: Mapped[list[str]] = mapped_column(JSON, default=list)


class OperationSignatureBand(Base):
    """LSH band index over ``Campaign.signature_json``.

    Exists so matching an operation is an indexed lookup instead of comparing a new sketch against
    every campaign in the deployment. Follows the one index-assisted retrieval pattern already
    proven in this codebase, ``memory/graph/postgres.py`` (token -> ids -> load).

    NOT unique on ``(band_index, band_key)``: collisions are the entire mechanism. Many operations
    may share a band key, and the sketch comparison afterwards is what decides. Rows are small and
    there are 32 per operation, which is nothing against the database budget.
    """

    __tablename__ = "operation_signature_bands"
    __table_args__ = (
        Index("ix_opsig_band", "band_index", "band_key"),
        Index("ix_opsig_campaign", "campaign_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id"))
    band_index: Mapped[int] = mapped_column(Integer)
    band_key: Mapped[str] = mapped_column(String(32))


class CampaignMember(Base):
    __tablename__ = "campaign_members"
    __table_args__ = (
        UniqueConstraint("campaign_id", "account_external_id", name="uq_campaign_member"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id"), index=True)
    platform: Mapped[str] = mapped_column(String(32))
    account_external_id: Mapped[str] = mapped_column(String(128), index=True)
    handle: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # Per-member recurrence: how many detections this account appeared in.
    times_observed: Mapped[int] = mapped_column(Integer, default=1)
    methods_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class CampaignObservation(Base):
    """One detection event — the raw evidence, retained so the campaign's
    aggregates can be recomputed and history never overwritten."""

    __tablename__ = "campaign_observations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id"), index=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, index=True)
    platform: Mapped[str] = mapped_column(String(32))
    context_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    coordination_score: Mapped[float] = mapped_column(Float, default=0.0)
    member_count: Mapped[int] = mapped_column(Integer, default=0)
    methods_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    evidence_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    member_ids_json: Mapped[list[str]] = mapped_column(JSON, default=list)


class CampaignDetection(Base):
    """One run of the cohort coordination detector over one investigation.

    A denormalised index row, deliberately: the findings and every evidence artifact live in
    ``Investigation.payload_json`` under ``campaign_detection_v1``, and the admin queue must be
    able to list and filter without touching that blob. This is the same lesson the archive list
    already paid for (see ``list_user_investigations`` and its ``load_only``), and it bites harder
    here because these are the heaviest payloads in the product.

    Uniqueness is declared as an ``Index(..., unique=True)`` rather than a ``UniqueConstraint`` on
    purpose. The boot-time upgrade pass in ``storage/db.py`` backfills ``table.indexes`` onto
    databases that predate a change but cannot see ``table.constraints``, so the Index form
    survives a table that already exists and the constraint form silently does not.
    """

    __tablename__ = "campaign_detections"
    __table_args__ = (
        Index("ix_campaign_detection_slug", "investigation_slug", unique=True),
        Index("ix_campaign_detection_rank", "status", "best_score"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    investigation_slug: Mapped[str] = mapped_column(String(64))
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    platform: Mapped[str] = mapped_column(String(32), default="unknown", index=True)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, index=True,
    )
    passes: Mapped[int] = mapped_column(Integer, default=1)
    #: "analyst" or "engine". Which score defined the 70+ cohort, so a reader can tell whether the
    #: finding rests on the customer-visible number or on the deterministic one.
    score_source: Mapped[str] = mapped_column(String(16), default="engine")
    scanned_total: Mapped[int] = mapped_column(Integer, default=0)
    cohort_size: Mapped[int] = mapped_column(Integer, default=0)
    finding_count: Mapped[int] = mapped_column(Integer, default=0)
    campaign_count: Mapped[int] = mapped_column(Integer, default=0)
    best_score: Mapped[float] = mapped_column(Float, default=0.0)
    best_label: Mapped[str] = mapped_column(String(32), default="no_campaign_detected")
    #: "open" until an admin acts; "dismissed" records a labelled negative, which is the only
    #: source of ground truth this detector will ever accumulate.
    status: Mapped[str] = mapped_column(String(16), default="open", index=True)
    resolution_note: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    thresholds_version: Mapped[str] = mapped_column(String(32), default="cohort-v1")


# ---------------------------------------------------------------------------
# User-curated named graphs — operators manually collect profiles into
# named graphs; Omi draws coordination edges between members automatically.
# ---------------------------------------------------------------------------


class UserGraph(Base):
    __tablename__ = "user_graphs"
    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_user_graph_name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    platform: Mapped[str] = mapped_column(String(32), default="youtube")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class UserGraphMember(Base):
    __tablename__ = "user_graph_members"
    __table_args__ = (
        UniqueConstraint("graph_id", "external_id", name="uq_graph_member"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    graph_id: Mapped[int] = mapped_column(ForeignKey("user_graphs.id", ondelete="CASCADE"), index=True)
    external_id: Mapped[str] = mapped_column(String(128), index=True)
    platform: Mapped[str] = mapped_column(String(32), default="youtube")
    handle: Mapped[str] = mapped_column(String(280), default="")
    display_name: Mapped[str | None] = mapped_column(String(280), nullable=True)
    tier: Mapped[str | None] = mapped_column(String(16), nullable=True)
    # THE REAL SCORE, not one derived from the tier. The graph UI used to rebuild a number from the
    # tier band (high -> 0.9, elevated -> 0.7, moderate -> 0.45) and size every node by it, which is
    # an invented figure on a surface whose whole claim is that it does not invent figures. A tier is
    # a band and a band cannot be un-rounded: 50 and 74 are both "elevated" and are not the same
    # account. NULL means the score was not captured when the member was added, which is different
    # from zero and renders as an unsized node rather than a confident small one.
    omi_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


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
    # Overall confidence (how much data backed the verdict), derived from the
    # payload at save time. Nullable: investigations saved before this shipped
    # have no value and must not be shown as low-confidence.
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    summary: Mapped[str] = mapped_column(Text, default="")
    quota_used: Mapped[int] = mapped_column(Integer, default=0)
    batch_count: Mapped[int] = mapped_column(Integer, default=1)
    # Full serialized ComprehensiveScanResult payload. We replace this on
    # continuation batches with the merged result.
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    # Denormalised from payload_json at write time so LISTING investigations never loads the blob.
    # payload_json holds every commenter's scores, evidence, posts and analyst sections — often
    # megabytes — and the archive page asks for 100 rows at once. Deriving `platform` and a thumbnail
    # from the payload during a list meant parsing all of it to produce two short strings: a memory
    # and latency cliff that grows with how much a customer has actually used the product.
    #
    # Nullable because rows written before these columns existed hold NULL; the read path falls back
    # to URL / target_id heuristics, which need no payload.
    platform: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    thumbnail_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
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
    # Funnel: the share token this row was CLAIMED from, when a visitor arrived on someone else's
    # public report and signed up from it. Set on the COPY, never on the original, and it is what
    # makes claiming idempotent: a second claim of the same token by the same user returns the copy
    # that already exists instead of duplicating a payload that can run to megabytes.
    #
    # Deliberately NOT unique: the same report can be claimed by many different visitors, which is
    # the entire point of the funnel.
    claimed_from_token: Mapped[str | None] = mapped_column(String(48), nullable=True, index=True)
    # How many commenters were COMPILED for this post, against however many were actually scored
    # (payload video.commenter_count). The gap is the honest, specific fact the shared-report funnel
    # runs on: "this report checked 25 of the 312 accounts that replied". Set at scan time from the
    # candidate-list row count, which is free there and needs no join on the read path.
    #
    # Nullable because rows written before this existed cannot know it, and the read path must render
    # the report without the number rather than inventing one.
    commenters_available: Mapped[int | None] = mapped_column(Integer, nullable=True)
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
    # Platform the target belongs to, so History links and re-scans route to the
    # right place. Defaults to "youtube" for rows created before this column
    # existed (the only platform watchlists supported at the time).
    platform: Mapped[str] = mapped_column(
        String(32), default="youtube", server_default="youtube"
    )
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
# Select-then-scan — the FREE "compile" step caches the commenters found on a
# piece of content so the user can pick which to actually scan + score.
# ============================================================================

class CandidateList(Base):
    """A cached list of the commenters found on one piece of content, per user — the free 'compile' step
    of the select-then-scan flow. Rows are :class:`CommenterCandidate`. Persists the platform pagination
    cursor so 'add 25/50 more' continues past what is already cached; ``exhausted`` marks the end."""

    __tablename__ = "candidate_lists"
    __table_args__ = (
        UniqueConstraint("user_id", "platform", "content_id", name="uq_candidate_list"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True,
    )
    platform: Mapped[str] = mapped_column(String(32), index=True)
    content_id: Mapped[str] = mapped_column(String(255), index=True)
    content_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    # The post's real human title (YouTube video title / tweet text) — used to label the investigation
    # instead of "Scan of <url>". Captured best-effort on the first compile.
    content_title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # The investigation this post's scored batches grow into (set on the first scored selection); later
    # selections continue into the SAME investigation so the overall OMI recomputes over everyone scored.
    investigation_slug: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    # The platform pagination cursor for the NEXT page of commenters (null once exhausted).
    next_cursor: Mapped[str | None] = mapped_column(Text, nullable=True)
    exhausted: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow,
    )


class CommenterCandidate(Base):
    """One commenter found on the content, cached for selection (NOT scored yet). Deduplicated per
    ``(list_id, external_id)``; ``seq`` preserves fetch order for a stable list. ``meta_json`` is the
    exact ``commenters_meta`` entry and ``comments_json`` the raw comments by this author, so the score
    step can reconstruct the scan input for the SELECTED accounts without re-fetching."""

    __tablename__ = "commenter_candidates"
    __table_args__ = (
        UniqueConstraint("list_id", "external_id", name="uq_commenter_candidate"),
        Index("ix_candidate_list_seq", "list_id", "seq"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    list_id: Mapped[int] = mapped_column(
        ForeignKey("candidate_lists.id", ondelete="CASCADE"), index=True,
    )
    external_id: Mapped[str] = mapped_column(String(255), index=True)
    handle: Mapped[str | None] = mapped_column(String(255), nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    comment_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    comment_count: Mapped[int] = mapped_column(Integer, default=1)
    seq: Mapped[int] = mapped_column(Integer, default=0)
    meta_json: Mapped[str] = mapped_column(Text)
    comments_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    scanned: Mapped[bool] = mapped_column(Boolean, default=False)   # set true once scored, for the UI
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


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



# ---------------------------------------------------------------------------
# Founder-learning event log (master-plan Phase 4).
#
# The SMALLEST first-party record of real user behaviour, scoped to five
# questions only: did the user experience value / come back / share something /
# trust the result / would they pay. Five event kinds total (featured_viewed,
# campaign_export, campaign_share_minted, public_report_view, wtp_answer/
# wtp_dismissed); everything else those questions need is DERIVED from the
# existing ledgers (ScanLog, Investigation, BillingEvent) at read time.
#
# Privacy is structural: no IP, no user agent, no fingerprint, no session ids,
# no third parties. ``user_id`` is nullable because anonymous public-report
# views are logged tokens-only. Payloads pass a per-kind whitelist in
# app.analytics.event_log before they are ever written.
# ---------------------------------------------------------------------------


class EventLog(Base):
    """One row per learning-relevant user action. Append-only."""

    __tablename__ = "event_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(String(32), index=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    payload_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, index=True
    )


# ---------------------------------------------------------------------------
# Institutional Intelligence Memory — production persistence (Sprint 012).
#
# The durable home of the memory system (Sprint 005/006). The CONSTITUTION lives
# in the domain model (app/memory/graph/objects.py), not the schema: confidence,
# contradiction history, and epistemic status are RECOMPUTED from the append-only
# observation ledger — never stored — so memory always evolves and can never
# ossify into a stored verdict. These tables persist evidence + observed patterns
# only; the typed memories (coordination / behavioral / control / narrative /
# campaign) are rows distinguished by ``type`` (+ ``is_control``), indexed for
# lookup at scale. No LLM opinion is ever written.
# ---------------------------------------------------------------------------


class KnowledgeObjectRow(Base):
    """A persisted KnowledgeObject — a recurring, falsifiable pattern. Aggregates are derived
    from the ledger, never stored here."""

    __tablename__ = "knowledge_objects"
    __table_args__ = (
        Index("ix_ko_type_control", "type", "is_control"),
        Index("ix_ko_active", "superseded_by"),
    )

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    type: Mapped[str] = mapped_column(String(64))     # indexed via composite ix_ko_type_control (leading col)
    family: Mapped[str] = mapped_column(String(64), default="patterns_signatures")
    label: Mapped[str] = mapped_column(Text, default="")
    signature: Mapped[list] = mapped_column(JSON, default=list)
    attributes: Mapped[dict] = mapped_column(JSON, default=dict)
    is_control: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    influence_class: Mapped[str] = mapped_column(String(16), default="context")
    superseded_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    half_life_days: Mapped[float] = mapped_column(Float, default=180.0)
    retirement_floor: Mapped[float] = mapped_column(Float, default=0.12)
    platform_scope: Mapped[list] = mapped_column(JSON, default=list)
    # Sprint 013: cached distillation tier (derived from the ledger; refreshed by consolidation).
    # A performance cache for tier-filtered queries — never the source of truth.
    tier: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    last_consolidated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Sprint 014: denormalized retrieval-reuse counter (source of truth is retrieval_feedback).
    # A measurement that influences future retrieval RANKING only — never a score or verdict.
    reuse_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    observations: Mapped[list["ObservationLedgerRow"]] = relationship(
        back_populates="knowledge_object", cascade="all, delete-orphan",
        order_by="ObservationLedgerRow.seq",
    )
    signatures: Mapped[list["KnowledgeObjectSignatureRow"]] = relationship(
        back_populates="knowledge_object", cascade="all, delete-orphan",
    )


class KnowledgeObjectSignatureRow(Base):
    """One signature token of a KnowledgeObject — the indexed seam for fast signature lookup
    across millions of objects (find candidates sharing a firing detector/method)."""

    __tablename__ = "knowledge_object_signatures"
    __table_args__ = (
        Index("ix_kosig_token", "token"),
        UniqueConstraint("ko_id", "token", name="uq_kosig_ko_token"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ko_id: Mapped[str] = mapped_column(ForeignKey("knowledge_objects.id", ondelete="CASCADE"))  # leading col of uq_kosig_ko_token
    token: Mapped[str] = mapped_column(String(128))
    knowledge_object: Mapped["KnowledgeObjectRow"] = relationship(back_populates="signatures")


class ObservationLedgerRow(Base):
    """One append-only evidence observation. Never updated or deleted — the raw record is kept so
    aggregates can be recomputed and history is never overwritten."""

    __tablename__ = "observation_ledger"
    __table_args__ = (
        Index("ix_obs_ko_seq", "ko_id", "seq"),
        Index("ix_obs_stance", "stance"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ko_id: Mapped[str] = mapped_column(ForeignKey("knowledge_objects.id", ondelete="CASCADE"))  # leading col of ix_obs_ko_seq
    seq: Mapped[int] = mapped_column(Integer, default=0)
    investigation: Mapped[str] = mapped_column(String(128), index=True)
    stance: Mapped[str] = mapped_column(String(16))
    evidence_refs: Mapped[list] = mapped_column(JSON, default=list)
    independence_key: Mapped[str] = mapped_column(String(128), default="")
    at: Mapped[str] = mapped_column(String(40), default="")
    human_anchor: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    memory_influence: Mapped[str] = mapped_column(String(16), default="none")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    knowledge_object: Mapped["KnowledgeObjectRow"] = relationship(back_populates="observations")


class MemoryRevisionRow(Base):
    """Version history for a KnowledgeObject — every create / observe / supersede step (audit)."""

    __tablename__ = "memory_revisions"
    __table_args__ = (Index("ix_memrev_ko", "ko_id", "rev"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ko_id: Mapped[str] = mapped_column(ForeignKey("knowledge_objects.id", ondelete="CASCADE"))  # leading col of ix_memrev_ko
    rev: Mapped[int] = mapped_column(Integer, default=1)
    change: Mapped[str] = mapped_column(String(64), default="")
    investigation: Mapped[str | None] = mapped_column(String(128), nullable=True)
    at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class RetrievalFeedbackRow(Base):
    """Append-only retrieval feedback (Sprint 014). Records WHY a memory was retrieved and what
    happened — whether it influenced reasoning, whether the Governor accepted the ruling that
    used it, and whether the analyst agreed. This improves future retrieval RANKING only; it
    never changes an investigation's score, the Governor, or OmiScore. Measurement, not control."""

    __tablename__ = "retrieval_feedback"
    __table_args__ = (Index("ix_rfb_ko", "ko_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ko_id: Mapped[str] = mapped_column(ForeignKey("knowledge_objects.id", ondelete="CASCADE"))  # leading col of ix_rfb_ko
    investigation: Mapped[str] = mapped_column(String(128), index=True)
    selected_because: Mapped[str] = mapped_column(Text, default="")
    influenced: Mapped[bool] = mapped_column(Boolean, default=False)
    governor_accepted: Mapped[bool] = mapped_column(Boolean, default=False)
    analyst_agreed: Mapped[bool] = mapped_column(Boolean, default=False)
    at: Mapped[str] = mapped_column(String(40), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class PriorContextCacheRow(Base):
    """A cached PriorContext retrieval keyed by the bundle signature hash. Memory influences
    CONTEXT only; this is a read accelerator, never a source of new evidence."""

    __tablename__ = "prior_context_cache"
    # signature_hash carries unique=True (→ a unique index); a separate ix_pcc_sig would duplicate it.

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    signature_hash: Mapped[str] = mapped_column(String(80), unique=True)
    result: Mapped[list] = mapped_column(JSON, default=list)
    memory_revision: Mapped[str | None] = mapped_column(String(80), nullable=True)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class ReportDispute(Base):
    """Someone named in a public report objecting to it.

    This is the recourse an accused account has, and it is a legal artifact as much as a product one:
    OmiSphere publishes scored claims about named real people who never agreed to be analysed, and
    "we reviewed it and acted within a day" is a materially different position from "they had no way
    to reach us". It is also the operational answer to a GDPR objection or erasure request about a
    person whose data was collected indirectly.

    Append-only in spirit: a dispute is never deleted, only resolved, so the trail of what was
    reported and what was done about it survives. `ip_hash` exists ONLY to rate-limit abuse and is a
    hash, never a stored address.

    Deliberately NOT auto-unpublishing on submission. That would let anyone silence any report by
    claiming to be named in it, which is its own abuse vector; the mitigation is that an admin can
    unpublish in one call and the queue is small enough to action quickly.
    """

    __tablename__ = "report_disputes"
    __table_args__ = (
        Index("ix_dispute_status_created", "status", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # The shared report objected to. Kept as the raw token because the investigation may later be
    # unshared or deleted, and the record of the complaint has to outlive the thing complained about.
    share_token: Mapped[str] = mapped_column(String(48), index=True)
    investigation_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    # Which account in the report this is about, as the complainant identified it.
    subject_handle: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # How to reach them with an outcome. Optional: someone may object without wanting contact.
    contact: Mapped[str | None] = mapped_column(String(320), nullable=True)
    reason: Mapped[str] = mapped_column(Text, default="")
    # open -> reviewing -> upheld (report removed) | rejected (report stands)
    status: Mapped[str] = mapped_column(String(16), default="open", index=True)
    resolution_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    ip_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, index=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Feedback(Base):
    """User-submitted product feedback. Any signed-in user can create one; only admins can list/search
    them (the admin feedback queue). The submitter is recorded for context; the message is the point."""

    __tablename__ = "feedback"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), index=True, nullable=True)
    category: Mapped[str] = mapped_column(String(40), default="general")
    message: Mapped[str] = mapped_column(Text, default="")
    page: Mapped[str | None] = mapped_column(String(300), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, index=True)


class UpstreamUsage(Base):
    """A daily counter of calls made to the paid upstream APIs (twitterapi.io, YouTube).

    This exists because ONE route spends real money with no billing control behind it. The compile
    step (``POST /v1/scan/link/commenters``) requires auth but charges no credits and calls the X API,
    which bills per read, so credits cannot guard it: there is nothing to spend. Its only ceiling was
    an in-process 30/minute limiter, which bounds a burst and not a day, is per instance, and resets
    on every deploy. Thirty a minute sustained is roughly 43,000 calls per user per day, and nothing
    anywhere recorded that they had happened. The first signal would have been the invoice.

    An aggregate row rather than an event log, on purpose. The budget check runs before every upstream
    fetch and has to be one indexed lookup, and a per-call log of a launch's traffic grows without
    bound for a question ("how much did today cost") that only ever needs the sum. Per-scan detail
    already exists in ``ScanLog`` and on the investigation itself.

    ``scope`` / ``scope_id`` rather than a user FK because the most important row has no user: the
    deployment-wide total, which is the one that answers "is the API budget on fire right now". Rows
    are keyed on a UTC date string, never a timestamp, so a rollover is a different row rather than a
    window that has to be computed.
    """

    __tablename__ = "upstream_usage"
    __table_args__ = (
        # The budget lookup. Every column it filters on is NOT NULL, so unlike `candidate_lists` this
        # constraint is genuinely enforced (SQL treats NULLs as distinct, which is what makes that
        # table's constraint inert for anonymous rows).
        UniqueConstraint("scope", "scope_id", "usage_date", "platform", name="uq_upstream_usage_key"),
        Index("ix_upstream_usage_date", "usage_date", "scope"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # "user" (scope_id is the user id) or "global" (scope_id is ""). Never NULL.
    scope: Mapped[str] = mapped_column(String(16), default="user")
    scope_id: Mapped[str] = mapped_column(String(64), default="")
    # UTC "YYYY-MM-DD". A string so the daily boundary is unambiguous across drivers and timezones.
    usage_date: Mapped[str] = mapped_column(String(10))
    platform: Mapped[str] = mapped_column(String(16), default="x")
    # What actually bills: upstream provider calls. twitterapi.io charges per call.
    api_calls: Mapped[int] = mapped_column(Integer, default=0)
    # How many of our own requests produced them, for reading the ratio back.
    requests: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class WaitlistEntry(Base):
    """Somebody who asked to be told when OmiSphere opens.

    The list a pre-launch campaign exists to build. Two things about it are load-bearing:

    **The email is unique.** Somebody who submits the form twice, or who joins from the landing page
    and then creates an account, is ONE person. Without the constraint the launch blast mails them
    twice, which is the single most obvious way to look amateur on the one day everybody is looking.

    **``notified_at`` is the idempotency key for the launch email.** It is stamped per address as the
    mail is accepted, not after the whole run, so a blast that dies half way through resumes instead
    of restarting. Re-running it is therefore always safe, which matters because the operator will
    almost certainly run it twice.
    """

    __tablename__ = "waitlist"
    __table_args__ = (
        Index("ix_waitlist_notified", "notified_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    #: Lowercased and stripped before insert, so Foo@Bar.com and foo@bar.com are one person.
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    #: Where they came from: "landing", "coming_soon", "signup". Tells you which surface actually
    #: converts, which is worth knowing before spending money driving traffic to one of them.
    source: Mapped[str] = mapped_column(String(32), default="coming_soon")
    #: Abuse triage only. A hash, never the address itself: this table is a list of people who have
    #: done nothing but express interest, and it should not also be a log of where they live.
    ip_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    #: When the launch email was accepted for this address. NULL means still owed one.
    notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
