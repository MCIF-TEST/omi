from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="OMI_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    env: str = "development"
    log_level: str = "INFO"
    api_port: int = 8000

    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"

    # Detector weights. Tuned by hand for Phase 0; will be calibrated against a
    # labeled fixture set in Phase 1.
    weight_temporal: float = Field(default=1.0)
    weight_semantic: float = Field(default=1.2)
    # ai_writing is a SUPPLEMENTAL signal (see ``SUPPLEMENTAL_DETECTORS`` in
    # app.detection.scoring): it is computed and shown as context but never
    # contributes to the suspicion composite. The weight is 0.0 as a mechanical
    # backstop — the supplemental exclusion in the aggregator is authoritative
    # and holds even if this weight is later changed. AI-assisted phrasing is
    # not evidence of inauthenticity; treating it as such false-positives on
    # ESL writers, formal writers, and legitimate Grammarly/LLM-assisted humans.
    weight_ai_writing: float = Field(default=0.0)
    weight_profile: float = Field(default=0.7)
    weight_memory: float = Field(default=0.6)
    weight_voice: float = Field(default=0.5)
    weight_engagement: float = Field(default=0.9)
    weight_coordination: float = Field(default=0.9)

    # Signal-decorrelation factors. Several detectors share an underlying
    # evidence basis: ``semantic`` + ``ai_writing`` both read text patterns,
    # while ``temporal`` + ``engagement`` + ``coordination`` all partly read
    # posting timing/cadence. Combining them in log-odds space as if they were
    # independent double-counts the shared component and produces overconfident
    # scores. When more than one member of a correlated group fires, every
    # member beyond the strongest has its contribution multiplied by the group's
    # redundancy factor (compounding for a third member). 1.0 disables the
    # discount (treat as fully independent); lower discounts harder.
    decorrelation_redundancy_content: float = Field(default=0.55)
    decorrelation_redundancy_timing: float = Field(default=0.65)

    # Optional learned signal-correlation model. When this JSON artifact exists
    # (produced by ``scripts/fit_correlation.py`` from the labeled corpus), the
    # aggregator derives its decorrelation factors AND its independence-axis
    # assignment from the *measured* pairwise detector correlations instead of
    # the hand-tuned groups above. Absent or unreadable → fall back to the
    # default group model, so behavior is unchanged out of the box.
    correlation_model_path: str = "models/signal_correlation.json"

    # Baseline prior probability that an arbitrary scanned account exhibits
    # synthetic / coordinated behavior. Accounts being scanned have selection
    # bias (they're suspected enough to be worth scanning), so 0.15 is more
    # realistic than the population baseline. Tune downward for unbiased
    # batch scans (e.g. every commenter on a randomly-picked video).
    prior_probability: float = 0.15

    # Storage. SQLite by default so the engine works with zero infrastructure;
    # override with a Postgres URL in production.
    database_url: str = "sqlite:///./data/omi.db"

    # YouTube ingestion.
    youtube_api_key: str | None = None
    # Max commenters to fetch per video scan (bounds YouTube quota use).
    scan_max_commenters: int = 100
    # Max recent comments to pull per commenter (their "history").
    scan_max_history_per_commenter: int = 50
    # If we've scanned an account within this many days, reuse the cached score.
    scan_cache_ttl_days: int = 7
    # YouTube Data API v3 daily quota cap. Defaults to the free-tier limit;
    # set higher if you've requested a quota increase from Google. Used for
    # the health-pill warning level and the /v1/status quota_used_today number.
    youtube_daily_quota: int = 10000

    # Memory / fingerprint nearest-neighbor settings.
    memory_k: int = 5
    memory_distance_threshold: float = 0.35  # euclidean over normalized vectors

    # -----------------------------------------------------------------------
    # Multi-tenant / billing settings (used in the public-launch build).
    # All optional in dev: when unset, billing routes return helpful 503s and
    # the auth layer falls back to a permissive "local mode" — useful while
    # running OMI on a single machine without setting up Stripe.
    # -----------------------------------------------------------------------

    # Required for production. A random 64+ char string used to sign session
    # cookies. Rotate this and every existing session is invalidated.
    session_secret: str = "dev-only-change-me-please-12345678901234567890"
    # When True, /v1/scan/* requires an authenticated user with credits.
    # When False, all scans are unauthenticated and unlimited (local-mode).
    require_auth: bool = False
    # Free trial credits handed out at signup.
    free_trial_credits: int = 3
    # Credits added when a subscription becomes active or renews.
    monthly_credit_grant: int = 20
    # Comma-separated list of email addresses auto-promoted to admin on
    # signup. Admins skip credit consumption and see /v1/metrics. Lowercased
    # for comparison.
    super_admin_emails: str = ""
    # Public base URL of the service — needed for Stripe success/cancel
    # redirects. Example: ``https://omisphere.app``
    public_base_url: str = "http://localhost:8000"

    # Stripe — get these from dashboard.stripe.com (use test keys until live).
    stripe_secret_key: str | None = None
    stripe_webhook_secret: str | None = None
    # The Stripe Price ID of your $9.99/mo subscription product
    # (e.g. ``price_1ABC...``). Created once in the Stripe dashboard.
    stripe_price_id: str | None = None

    # -----------------------------------------------------------------------
    # LLM enhancement layer (Phase 7).
    # If unset, the reasoning module falls back to a TemplateProvider that
    # generates competent commentary from the same structured input — the
    # product is fully functional without any LLM key.
    # -----------------------------------------------------------------------
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-haiku-4-5-20251001"
    reasoning_max_tokens: int = 320
    reasoning_max_input_chars: int = 4000

    # -----------------------------------------------------------------------
    # Learned detector (ML track). Off by default: when use_ml_scorer is
    # False or no model artifact is present, scanning runs the rule engine
    # unchanged. Point ml_model_path at a joblib bundle (downloaded from the
    # HuggingFace Hub repo named in hf_model_repo) to activate blended
    # scoring. ml_blend_weight controls how much the model overrides the
    # hand-tuned score (0 = ignore model, 1 = trust model fully).
    # -----------------------------------------------------------------------
    use_ml_scorer: bool = False
    ml_model_path: str | None = None
    ml_text_model_path: str | None = None
    hf_model_repo: str | None = None
    ml_blend_weight: float = 0.5

    # -----------------------------------------------------------------------
    # Monitoring (Phase 8)
    # -----------------------------------------------------------------------
    enable_monitoring: bool = False
    monitoring_interval_seconds: int = 300
    watchlist_recheck_hours: int = 6
    watchlist_max_per_tick: int = 5
    narrative_spike_min_recent: int = 5
    narrative_spike_growth_ratio: float = 2.0
    high_tier_surge_min: int = 3
    high_tier_surge_baseline_ratio: float = 2.0

    # -----------------------------------------------------------------------
    # Alert delivery (Phase 11). Configure SMTP credentials to enable email
    # notifications; leave smtp_host empty to disable email entirely. Webhook
    # delivery has no global config — it's per-user via User.webhook_url.
    # -----------------------------------------------------------------------
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_from: str = "alerts@omisphere.ai"
    smtp_use_tls: bool = True
    alert_webhook_timeout_seconds: float = 10.0


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
