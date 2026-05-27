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
    weight_ai_writing: float = Field(default=0.8)
    weight_profile: float = Field(default=0.7)
    weight_memory: float = Field(default=0.6)
    weight_voice: float = Field(default=0.5)
    weight_engagement: float = Field(default=0.9)
    weight_coordination: float = Field(default=0.9)

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


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
