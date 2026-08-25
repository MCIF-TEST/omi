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

    # --- Narrative embeddings (topic clustering across investigations) ----------------------------
    #
    # Emergent topics are only as good as the embedding behind them. Unconfigured, `get_embedder()`
    # falls back to `HashingEmbedder`, whose own docstring says it will not catch paraphrases: "same
    # topic" degrades to "same words", so two accounts pushing one narrative in different phrasing
    # never cluster, which is exactly the case the feature exists to catch.
    #
    # Deliberately provider-agnostic: any OpenAI-compatible `/v1/embeddings` endpoint works, so the
    # vendor is a deployment decision rather than a code one. Whichever is chosen must be named in
    # the privacy policy's subprocessor list BEFORE this is switched on: it sends other people's
    # public posts off our servers, and those people are not our users and never agreed to anything.
    # `narrative_embedding_provider` is that name, and the admin surface refuses to report the
    # embedder as configured without it.
    narrative_embedding_base_url: str | None = None
    narrative_embedding_model: str | None = None
    narrative_embedding_api_key: str | None = None
    #: Human-readable vendor name for the subprocessor disclosure, e.g. "OpenAI".
    narrative_embedding_provider: str | None = None
    #: Optional output width, for providers that support shortening (OpenAI's `dimensions`).
    narrative_embedding_dimensions: int | None = None
    narrative_embedding_timeout_seconds: float = 30.0
    #: Texts per request. Providers cap both count and total tokens; 96 is under every common limit.
    narrative_embedding_batch_size: int = 96

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
    weight_narrative: float = Field(default=0.8)
    # community is a DOWNWARD-only anchor (GAP-07): it can subtract suspicion for
    # established, audience-bearing accounts but never add it. Weight controls how
    # much an established community can offset behavioral suspicion — kept modest
    # so a blatant multi-axis bot still outweighs it.
    weight_community: float = Field(default=0.9)

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

    # Twitter / X ingestion (twitterapi.io adapter). The detection engine is
    # platform-agnostic; this key only powers the ingestion layer that maps
    # tweets/profiles onto the shared Profile/Post schemas. Never commit it —
    # set OMI_TWITTER_API_KEY in the environment / .env.
    twitter_api_key: str | None = None
    twitter_api_base_url: str = "https://api.twitterapi.io"
    # Max recent tweets to pull per single-account scan (history depth bounds
    # the per-scan provider cost).
    scan_twitter_max_history: int = 50
    # Credits charged for a single-account Twitter deep-scan. Flat (not batch):
    # one account's ~50-tweet history is a fraction of a 50-commenter batch, so
    # this is intentionally cheap. The 10-credits-per-50 batch rate
    # (credits_per_batch_twitter) applies to multi-account tweet-thread scans.
    credits_per_twitter_account: int = 1

    # YouTube ingestion.
    youtube_api_key: str | None = None
    # Max commenters to fetch per video scan (bounds YouTube quota use).
    scan_max_commenters: int = 100
    # Select-then-scan COMPILE step (the free list you pick from). Decoupled from the per-scan cap
    # above: the list is meant to mirror the whole comment section so you can browse and select, so it
    # can grow far larger than what you'd actually score. Bounds one compile page, the whole pool, and
    # the comment sample pulled to enumerate commenters.
    candidate_pool_max: int = 1000        # most commenters one post's list can hold
    candidate_page_max: int = 200         # most commenters a single compile call fetches
    candidate_first_page: int = 100       # commenters pulled on the first compile
    candidate_min_comments: int = 100     # never sample fewer than this many comments to find them
    # Max recent comments to pull per commenter (their "history").
    scan_max_history_per_commenter: int = 50
    # If we've scanned an account within this many days, reuse the cached score.
    scan_cache_ttl_days: int = 7
    # A cache hit reuses the stored SCORE. This decides whether it also re-pulls the account's
    # profile + post history for the EVIDENCE the Omi Analyst reads. On (default), the cache saves
    # the scoring and DB work but the model still sees what the account actually wrote; off, a
    # cached account reaches the model with an empty post list that is indistinguishable from an
    # account which has never posted. Turning it off saves upstream API calls on repeat accounts at
    # the cost of a materially worse per-account verdict for them. OMI_SCAN_REFETCH_EVIDENCE_FOR_CACHED.
    scan_refetch_evidence_for_cached: bool = True
    # Wall-clock budget for an async scan job. A job stuck queued/running past
    # this (slow/hung scan, or a worker killed by OOM/restart) is reaped: marked
    # failed + refunded, so it can never poll forever. Kept under the client's
    # ~8-min poll window so the user sees a clean failure, not a timeout.
    # Scan-job watchdog. The budget SCALES with the job's size (see scan_job_budget_seconds): a flat
    # number is wrong by construction when one job is 1 account and the next is 100. These three are
    # the floor (small jobs), the per-account allowance, and a hard ceiling for a truly wedged job.
    # Deliberately generous: the watchdog exists to catch a DEAD worker, and reaping a LIVE one is the
    # expensive mistake — it refunds and reports failure for a scan whose upstream calls were already
    # paid for, and whose investigation may already be saved.
    scan_job_timeout_seconds: int = 300
    scan_job_timeout_per_account_seconds: float = 12.0
    scan_job_timeout_max_seconds: int = 1800
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
    # PRE-LAUNCH LOCKDOWN. When true, only admins can use the product: every other signed-in user
    # is refused on product routes and sent to the waitlist. Marketing pages, sign-up, sign-in and
    # public shared reports stay open. See app/core/lockdown.py for what is allowed through and why.
    #
    # Default False so that deleting the variable OPENS the site rather than silently leaving it
    # shut; render.yaml commits 'true' explicitly while the campaign is running. The boot log states
    # which mode is live on every start.
    lockdown: bool = False

    # When True, /v1/scan/* requires an authenticated user with credits.
    # When False, all scans are unauthenticated and unlimited (local-mode).
    require_auth: bool = False
    # Free trial credits handed out at signup.
    free_trial_credits: int = 5
    # NOTE: there is no `monthly_credit_grant` any more. What a paid invoice grants is a property
    # of the TIER the customer bought (app/core/plans.py), resolved from the Stripe Price on the
    # invoice. A single global grant could only ever be right for one of three plans, and leaving it
    # here as a fallback would mean a misconfigured Price silently paid out the wrong tier's credits
    # instead of telling the operator their Price ids are wrong.

    # -----------------------------------------------------------------------
    # Batch-based scan pricing.
    #
    # A comment-batch scan is billed *per batch of commenters scanned* rather
    # than a flat rate per call, so credit cost tracks the per-commenter API
    # cost. This matters most for metered data APIs: YouTube's quota is
    # effectively free (10k units/day ≈ 195 scans), but X/Twitter charges
    # ~$0.005 per post read, so a 50-commenter batch with H posts of history
    # each costs ~50×(H+4)×$0.005 in real money.
    #
    # Credits charged = ceil(accounts_scored / scan_batch_unit)
    #                   × credits_per_batch[platform].
    #
    # Flat rate for EVERY platform: 1 credit per 20 accounts analyzed. So 1-20
    # accounts = 1 credit, 21-40 = 2, and so on (100 accounts = 5 credits). The
    # count is the number of accounts actually scored (the user's selection),
    # which is exactly what the analyst reads.
    #
    # THIS WAS 50 AND 50 WAS LOSS-MAKING. At ~2 upstream calls per account and
    # ~$0.005-0.006 per call, 20 credits at 50 accounts each is ~1,000 accounts
    # and ~$11-15 of upstream against $14.26 of net revenue: a ~6% gross margin
    # on X, and negative on the SocialCrawl platforms. 20 accounts per credit is
    # what holds ~70% at full utilisation. See app/core/plans.py for the full
    # arithmetic, and keep this equal to plans.ACCOUNTS_PER_CREDIT and to
    # ACCOUNTS_PER_CREDIT in apps/web/lib/plan.ts.
    #
    # The per-platform knobs below stay because upstream prices differ per
    # platform and can move independently; they are currently equal because the
    # measured per-account cost is within ~20% across X, Reddit and YouTube.
    scan_batch_unit: int = 20
    credits_per_batch_youtube: int = 1
    credits_per_batch_twitter: int = 1
    # Comma-separated list of email addresses auto-promoted to admin on
    # signup. Admins skip credit consumption and see /v1/metrics. Lowercased
    # for comparison.
    super_admin_emails: str = ""
    # Public base URL of the service — needed for Stripe success/cancel
    # redirects. Example: ``https://omisphere.app``
    public_base_url: str = "http://localhost:8000"

    # Stripe — get these from dashboard.stripe.com (use test keys until live).
    # sk_test_… / sk_live_…  SECRET. Never expose to the browser.
    stripe_secret_key: str | None = None
    # whsec_…  The signing secret of THIS endpoint's webhook, from the Stripe dashboard. It is what
    # stops anyone who knows the URL from POSTing themselves credits, so an unset value disables the
    # webhook rather than trusting unverified payloads.
    stripe_webhook_secret: str | None = None
    # price_…  The Stripe Price of the monthly subscription. Created once in the dashboard; the
    # AMOUNT LIVES IN STRIPE, never here — this server never sends an amount, so a bug in our code
    # cannot charge the wrong price.
    stripe_price_id: str | None = None
    # --- Per-tier Stripe Prices -------------------------------------------------------------
    # One recurring Price per plan (see app/core/plans.py for what each grants and why). Created in
    # the dashboard; the AMOUNT LIVES IN STRIPE, so a bug here can advertise the wrong plan but can
    # never charge the wrong number.
    #
    # ``stripe_price_id`` above is the LEGACY single-plan price and is deliberately still honoured:
    # existing subscribers are on it, and their renewal invoices carry that price id forever. It
    # resolves to Starter (see plans.tier_for_price_id). Dropping it would leave every current
    # customer's renewal unable to name a tier, which fails closed to Free — i.e. it would silently
    # downgrade the only people already paying.
    stripe_price_starter: str | None = None
    stripe_price_reporter: str | None = None
    stripe_price_research: str | None = None
    # price_…  A ONE-OFF (mode=payment) Price for a top-up credit pack. Not a subscription: it must
    # never move subscription_status or the renewal date, only add credits.
    stripe_price_topup: str | None = None
    # How many credits one top-up pack grants. The Stripe Price sets what the pack COSTS; this sets
    # what it CONTAINS, and the two are configured in different systems, so they must be kept in
    # agreement by hand. Sized at $1/credit against the Price you create.
    topup_pack_credits: int = 25
    # Comma-separated Checkout payment_method_types (pure API / hosted Checkout).
    # Default "link,card": Link works while Cards are still pending approval; `card` is also what
    # powers Apple Pay / Google Pay wallets on Checkout (they are not separate type strings).
    # Override via OMI_STRIPE_PAYMENT_METHOD_TYPES if needed, e.g. "link" only, or "card,link".
    stripe_payment_method_types: str = "link,card"
    # Display-only. What the UI prints next to the subscribe button; the real charge is whatever the
    # Stripe Price says. Keep them in agreement — this string proves nothing.
    subscription_price_display: str = "$13.99"

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
    # Omi Analyst reasoning layer (OMI_ANALYST_PRODUCTION_WIRING_V1).
    # OFF by default. When enabled, app/reasoning exposes a feature-flagged,
    # async, cached *structured* assessment that INTERPRETS the engine's already-
    # computed evidence (it never runs a detector, recomputes a score, or touches
    # OmiScore). Powered by the model served at the configured endpoint (production
    # runtime model: mistralai/Mistral-7B-Instruct-v0.3) when an endpoint is
    # configured; otherwise the always-on deterministic, schema-valid provider.
    # Config is loaded from the HF registry repo below (local-mirror fallback).
    # The product is fully functional with this off — it is strictly additive.
    # -----------------------------------------------------------------------
    analyst_enabled: bool = False
    analyst_hf_repo: str = "Andrewexiga/omi-analyst-v1"
    analyst_hf_revision: str | None = None
    # The RUNTIME model the inference endpoint serves (informational + diagnostics; the endpoint
    # itself pins the actual weights). Distinct from analyst_hf_repo, which is the Omi contract
    # registry (prompt/schema/config), not the model.
    analyst_model_id: str = "mistralai/Mistral-7B-Instruct-v0.3"
    analyst_endpoint_url: str | None = None
    # The analyst runs in a background worker (off the request hot path) and the UI holds a loading
    # screen while polling (~9 min), so this bounds ONE model generation, not a user request. 500s gives
    # a slow full-investigation GPT-5 generation (up to the completion budget + reasoning tokens) plenty
    # of room to FINISH and be cached as a real result, instead of being cut off and floored (which is
    # what showed the "isn't ready yet" fallback and made re-opens re-run). Env-overridable
    # (OMI_ANALYST_TIMEOUT_SECONDS).
    analyst_timeout_seconds: float = 500.0
    # The free pre-login scan runs its analyst call INLINE (an anonymous scan has no saved
    # investigation to generate against in the background and poll), so a visitor's browser is holding
    # the connection open the whole time. The full 500s budget is right for a signed-in investigation
    # generating in the background; here it would mean an eight-minute hang before the page gave up.
    # One 25-account call at low reasoning effort lands well inside this. OMI_DEMO_ANALYST_TIMEOUT_SECONDS.
    demo_analyst_timeout_seconds: float = 120.0
    analyst_max_retries: int = 2
    # Serving API the deployed endpoint speaks. "generate" (default) posts the raw
    # TGI text-generation body (existing behavior, byte-identical). "messages" posts
    # the OpenAI-compatible /v1/chat/completions body so the endpoint applies Qwen3's
    # chat template server-side. Set this to match the endpoint you deploy; the URL
    # must already point at the right route. No guessing — the operator chooses.
    analyst_endpoint_api: str = "generate"
    # Blended $/1k tokens for the served model, used only to annotate the per-investigation
    # metrics block with a cost estimate. 0.0 -> cost is reported as null (no guess).
    analyst_cost_per_1k_tokens_usd: float = 0.0
    # Phase B — how the analyst SYSTEM prompt is assembled from the HF package.
    #   "registry" (default): the validated base omi_analyst prompt only (current behavior).
    #   "package": base prompt + constitution (governance/reasoning rules) + Knowledge Library,
    #   assembled by app.reasoning.prompt_builder.PromptBuilder. Flipping to "package" CHANGES what
    #   the model receives and MUST be validated against the live endpoint (control-FPR must not
    #   regress) before production — verify via POST /v1/investigations/{slug}/analyst/audit.
    analyst_prompt_assembly: str = "registry"
    # Active prompt version for the AI behavior analyst (None -> registry default / rollback).
    analyst_prompt_version: str | None = None
    # Context Builder mode/budget for AI specialists ("raw" baseline | "structured").
    analyst_context_mode: str = "raw"
    analyst_context_budget: str = "standard"
    # -----------------------------------------------------------------------
    # Reasoning PROVIDER selection (Phase 2 — provider-independent boundary).
    #   "huggingface" (default): the existing HF inference-endpoint path — byte-identical.
    #   "openrouter": route the ONE comprehensive inference through OpenRouter, behind the same
    #                 ReasoningProvider seam. The OPENROUTER_API_KEY secret is read from the
    #                 environment (never a settings field / never persisted), exactly like HF_TOKEN.
    # The runtime, Governor, canonical validation, Floor, persistence, and frontend are unchanged —
    # only the transport differs. No provider switch changes Omi's evidence or output contract.
    analyst_provider: str = "huggingface"
    # The OpenRouter Preset that carries Omi's stable Master Analyst Protocol (system instructions +
    # model + routing) on the OpenRouter dashboard. When set, the per-investigation request references
    # "@preset/<slug>" and sends ONLY the investigation evidence package as the user message. The local
    # compiled system/base prompt is NEVER on the OpenRouter wire — the dashboard preset owns
    # instructions. The repository still records the local master-prompt version/hash it EXPECTS the
    # preset to hold (it does not, and cannot, cryptographically verify the remote preset content).
    openrouter_preset: str | None = None
    # Optional model slug. In preset mode the preset defines the model; set this to intentionally
    # override it (sent as a base model the preset layers onto). Without a preset it is required for
    # routing — the wire still carries evidence only (no local system re-send).
    openrouter_model: str | None = None
    # The model we EXPECT OpenRouter to serve (the omi-master-v1 preset routes to GPT-5 Mini). This is a
    # VERIFICATION expectation, NOT a routing directive: we never send it on the wire, so it can never
    # brick the AI path with a bad slug. After each generation we compare it against the model OpenRouter
    # ACTUALLY reports serving (the response `model` field) and record served_model_verified on the trace,
    # so every scan proves its assessments/OMI scores came from GPT-5 Mini and a silent model swap is
    # flagged loudly. Matching is prefix-tolerant so a dated snapshot (openai/gpt-5-mini-2025-xx-xx) still
    # verifies. Set OMI_OPENROUTER_EXPECTED_MODEL to change the expected model, or "" to disable the check.
    openrouter_expected_model: str | None = "openai/gpt-5-mini"
    openrouter_base_url: str = "https://openrouter.ai/api/v1/chat/completions"
    # Send the canonical ComprehensiveAssessment schema as OpenRouter native structured output
    # (response_format json_schema). Support varies by model; local canonical validation ALWAYS runs
    # regardless, so this never weakens validation.
    openrouter_structured_output: bool = True
    # Optional OpenRouter dashboard attribution headers (HTTP-Referer / X-Title). Not secrets.
    openrouter_referer: str | None = None
    openrouter_title: str | None = None
    # --- Cost guardrails (production, tunable WITHOUT a code deploy) -------------------------------- #
    # The per-investigation output-token budget = base + per_commenter × commenters, clamped to
    # [floor, ceiling]. This is the single biggest lever on OpenRouter spend. The ceiling is the hard
    # per-scan cap: at the default scan size (≤150 commenters) the formula needs ~27k, so 32k finishes a
    # full scan with headroom while capping any single inference. Raise the ceiling only if you also raise
    # OMI_SCAN_MAX_COMMENTERS. All four are env-overridable: OMI_ANALYST_COMPLETION_*.
    # Output-token CAPS (not reservations — billing is on tokens generated), sized generously so a
    # scan never truncates and silently drops per-account results. Reasoning tokens count against the cap.
    analyst_completion_base_tokens: int = 12000
    analyst_completion_per_commenter_tokens: int = 450
    analyst_completion_floor_tokens: int = 50000
    analyst_completion_ceiling_tokens: int = 50000    # equals the floor: every request asks for 50k
    # Batched analyst inference. A single OpenRouter request carries AT MOST this many accounts; a larger
    # selection is split into ≤N-account batches sent as PARALLEL requests, merged first-to-last, and
    # persisted progressively so the UI shows batch 1's accounts while later batches still run.
    # Sized for LATENCY, not just the token budget: one call reasoning over the full per-account
    # protocol (Dossier Loop + audits) for ~50 accounts ran long enough to breach the request timeout
    # and fall to the Floor (which drops all per-account results — reads as a "failed" scan). 25 keeps
    # each call comfortably inside the timeout.
    #
    # Batches run ONE AT A TIME (concurrency 1), deliberately. Firing all of them at once makes every
    # batch contend for the same upstream capacity, so the FIRST 25 accounts land no sooner than the
    # last — the user stares at nothing until the whole scan finishes. Sequentially, batch 1 is a
    # single unshared request: its results appear in the UI at the earliest possible moment, and each
    # later batch reveals as it lands. Total wall-clock is similar; time-to-first-result is far better,
    # and it keeps us to one in-flight OpenRouter request per scan. Env-overridable.
    # `analyst_batch_accounts` is the THRESHOLD: a selection at or below it runs as one request.
    # Above it, the selection is divided into `analyst_batch_count` near-equal batches, so the batch
    # count is a constant a customer can recognise (100 accounts is always four batches of 25, 126 is
    # always 32/32/31/31) instead of a function of how many accounts they happened to select. Raise
    # the COUNT, not the threshold, if per-batch latency ever starts racing OMI_ANALYST_TIMEOUT_SECONDS.
    analyst_batch_accounts: int = 25          # OMI_ANALYST_BATCH_ACCOUNTS
    analyst_batch_count: int = 4              # OMI_ANALYST_BATCH_COUNT
    analyst_batch_concurrency: int = 1        # OMI_ANALYST_BATCH_CONCURRENCY
    # GPT-5-class reasoning effort. Reasoning tokens bill as output AND are the dominant latency driver —
    # with the preset left to decide (its default trends high), a single call reasoned long enough to
    # breach the timeout. The per-account protocol is highly prescriptive (it tells the model exactly how
    # to work each account), so "low" keeps per-account quality while roughly halving generation time —
    # the difference between a real result and a timed-out Floor. Override via OMI_OPENROUTER_REASONING_
    # EFFORT ("minimal" | "low" | "medium" | "high") if you want deeper reasoning and accept the latency.
    openrouter_reasoning_effort: str | None = "low"
    # P3.1.6 — the AI-native Comment Analysis cutover. OFF by default, so the production comment/
    # thread surface is byte-identical to before (the deterministic thread_scan). When ON, every
    # comprehensive investigation runs Comment Analysis through the AI Investigation Runtime and the
    # UI consumes its compatibility output; with no endpoint configured the runtime uses the
    # deterministic Floor, which echoes the same engine number (so the number never destabilizes).
    comment_analysis_enabled: bool = False

    # -----------------------------------------------------------------------
    # Institutional Memory persistence (Sprint 012). OFF by default -> the
    # in-memory store (existing behavior, hermetic tests). When enabled, the
    # memory system persists to PostgreSQL. ``memory_database_url`` points the
    # memory store at a DEDICATED database (e.g. Supabase) separate from the
    # main app DB; unset -> memory shares the main database_url. The URL is a
    # secret supplied via env (OMI_MEMORY_DATABASE_URL) — never committed.
    # -----------------------------------------------------------------------
    memory_persistence_enabled: bool = False
    memory_database_url: str | None = None
    memory_db_pool_size: int = 5
    memory_db_max_overflow: int = 10

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
    # Rate limiting. All env-tunable (OMI_RATE_LIMIT_*) so a traffic spike can be
    # absorbed WITHOUT a code deploy.
    #
    # IMPORTANT SCOPE LIMIT: every limiter here is in-process (app/core/rate_limit.py),
    # so each budget is PER INSTANCE and resets on deploy. One instance, which is what
    # render.yaml provisions today, behaves exactly as configured. Run N instances and
    # the effective ceiling is N × these numbers. Making them global needs a shared
    # store (Redis) behind the same `hit()` interface — the limits below are a real
    # abuse guard, not a billing control. Cost is guarded by credits + the demo's
    # DB-backed per-IP reservations, both of which ARE correct across instances.
    # -----------------------------------------------------------------------
    # Coarse per-IP ceiling on all API routes (GlobalRateLimitMiddleware). Keyed on IP
    # because middleware runs before auth, so a user id here would be an unverified
    # claim an attacker could rotate to escape the limit.
    #
    # 120/min (the previous hardcoded value) is too tight to be safe: one active
    # investigation polls the analyst every few seconds for up to ~9 minutes (~20
    # req/min) on top of monitoring polls and ordinary navigation, so a single power
    # user runs ~40/min. Everyone sharing an office, school, VPN, or mobile carrier NAT
    # shares one key — three such users tripped a limit meant for scrapers, and the
    # product then looks broken for a paying customer. Raised with headroom; still
    # orders of magnitude below what a scraper does.
    rate_limit_global_max: int = 600
    rate_limit_global_window_seconds: float = 60.0

    # Per-USER ceiling on the free compile step (/v1/scan/link/commenters). This one
    # matters disproportionately: compile requires auth but charges NO credits, and it
    # calls the real X / YouTube API. X bills roughly $0.005 per post read, so an
    # account looping "load all" over big posts spends OUR money at no cost to itself.
    # Credits cannot guard it (there are none to spend), so this limiter is the only
    # ceiling. Generous enough for genuine browsing of a large comment section.
    rate_limit_compile_max: int = 30
    rate_limit_compile_window_seconds: float = 60.0

    # Per-USER ceiling on starting paid scans. Credits are the real guard here; this
    # only bounds a burst (a stuck client retrying, or a script racing many scans at
    # once and pinning the background pool).
    rate_limit_scan_max: int = 20
    rate_limit_scan_window_seconds: float = 60.0

    # Daily ceilings on PAID UPSTREAM API CALLS, database-backed (app/core/upstream_budget.py).
    #
    # The limiters above bound a burst; these bound a day, and they are the only spend controls that
    # survive a deploy and are correct across instances. 30 compile requests a minute sustained is
    # ~43,000 provider calls a day from one account, and until this existed nothing recorded that it
    # had happened: the first signal would have been the invoice.
    #
    # THE PER-USER DAILY BUDGET IS NOW A BURST GUARD, NOT THE SPEND CONTROL.
    #
    # It used to be the only thing bounding compile, and it was never sized for that job: at ~$0.006
    # a call, its old 1500/day default is $9 a day, i.e. **$270 a month from one $14.99 subscriber**,
    # reachable without any abuse at all. The real control is now the plan's monthly call ceiling
    # (``PlanTier.monthly_call_ceiling``, enforced by upstream_budget.enforce_period_budget), which
    # is derived from what each tier was priced to afford.
    #
    # What is left for this one to do is stop a single day eating a whole month's allowance to a
    # loop or a stuck client. It is deliberately set just above the largest tier's ceiling divided
    # over a few days rather than at a month's worth. 0 disables.
    # Env: OMI_UPSTREAM_DAILY_CALLS_PER_USER.
    upstream_daily_calls_per_user: int = 4000
    # Deployment-wide circuit breaker, NOT a business limit. It refuses paying customers when it
    # trips (with a 503 that says the fault is ours), so it is set well above any plausible real day
    # and exists only to stop a bug or an attack emptying the API budget overnight. Raise it rather
    # than removing it.
    #
    # Sizing, at ~$0.006 a call: 50,000/day is $300/day, i.e. $9,000 a month, which is far more than
    # the business can absorb and was chosen when a call was a free YouTube quota unit. 12,000/day is
    # $72/day, comfortably above real traffic at launch scale while capping a runaway at something
    # survivable. RAISE IT as paying volume grows: tripping it is an outage, not a saving.
    # Env: OMI_UPSTREAM_DAILY_CALLS_GLOBAL. 0 disables.
    upstream_daily_calls_global: int = 12_000

    # Largest accepted request body (BodySizeLimitMiddleware). Neither Starlette nor uvicorn caps this
    # by default, and ten routes take an unvalidated `payload: dict`, so an oversized JSON body was
    # parsed fully into memory — a cheap way to exhaust a small instance's RAM without an account.
    # 1 MiB is far above anything the product sends: the largest real body is a scan selection, about
    # 30 KB at the 1000-candidate pool cap. Env: OMI_MAX_REQUEST_BODY_BYTES.
    max_request_body_bytes: int = 1_048_576

    # Ceiling on FREE pre-login scans across all visitors per rolling 24h. The 2-per-IP reservation is a
    # fairness control, not a spend control — IPs rotate cheaply through VPNs and mobile carriers — and
    # every free scan is a real model call plus 25 upstream account fetches. Without this, total demo
    # cost is unbounded exactly when marketing traffic arrives. 0 disables the cap.
    # Env: OMI_DEMO_GLOBAL_DAILY_MAX.
    demo_global_daily_max: int = 500

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
