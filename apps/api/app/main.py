"""OMISPHERE API entrypoint.

This is the omi detection engine exposed as a FastAPI service. The
Next.js frontend (apps/web) is the only human-facing surface; this
module serves JSON exclusively.

In dev, Next.js rewrites /api/* to this service so the browser sees a
single origin. In production both services live behind the same custom
domain on Render.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from app import __version__
from app.core import background
from app.core.config import get_settings
from app.core.middleware import (
    BodySizeLimitMiddleware,
    GlobalRateLimitMiddleware,
    MetricsMiddleware,
    RequestIdMiddleware,
    SecurityHeadersMiddleware,
)
from app.monitoring import lifespan_monitoring
from app.routes import (
    accounts, activity, analyze, auth, billing, bulk, campaigns, channels, content, coordination,
    feedback, graph, health, improvement, intelligence, investigations, labels, learning, memory,
    metrics, monitoring, narratives, reasoning, reports, scan, scan_async, shadow, usage,
    waitlist, watchlists,
)
from app.storage.db import init_db


logger = logging.getLogger("omi")


@asynccontextmanager
async def lifespan(app: FastAPI):
    _configure_logging()
    # Before anything else that can fail, so a boot-time error is itself reported. No-op unless a DSN
    # is configured (app/core/observability.py).
    from app.core.observability import init_error_tracking
    init_error_tracking(get_settings().env, release=__version__)
    init_db()
    from app.content.seed import seed_example_content
    seed_example_content()
    _log_optional_feature_state()
    # Ask the gateway one question, in the background, so a renamed preset or a revoked key is an
    # ERROR in the deploy log instead of every scan silently serving the deterministic Floor until a
    # customer complains. Never blocks boot, never fails it, no-ops without a credential.
    from app.reasoning.boot_preflight import schedule_boot_preflight
    schedule_boot_preflight()
    async with lifespan_monitoring(app):
        try:
            yield
        finally:
            # Drain in-flight background tasks before shutdown so a deploy
            # doesn't lose narrative ingestion / fan-out work.
            background.shutdown()


def _log_optional_feature_state() -> None:
    """Loudly announce which optional features (LLM, SMTP, billing) are wired.

    Saves operators from having to guess why an alert never arrived: if
    SMTP isn't configured, the boot log says so explicitly. Same for the
    other gracefully-degrading features.
    """
    s = get_settings()
    parts: list[str] = []
    parts.append(f"YouTube ingestion: {'on' if s.youtube_api_key else 'OFF — no scans will work'}")
    from app.integrations.twitter import httpx_available
    if not s.twitter_api_key:
        tw_state = "off (no OMI_TWITTER_API_KEY)"
    elif not httpx_available():
        tw_state = ("DEGRADED — key set but httpx is NOT installed; every Twitter "
                    "scan will fail. Add httpx to the production dependencies.")
    else:
        tw_state = "on"
    parts.append(f"Twitter/X ingestion: {tw_state}")
    parts.append("Investigation commentary: deterministic presentation (Anthropic 2nd reasoning engine retired — P3.4)")
    parts.append(f"SMTP email alerts: {'on (' + s.smtp_host + ')' if s.smtp_host else 'off — webhook delivery still works'}")
    parts.append(f"Stripe billing: {'on' if s.stripe_secret_key and s.stripe_price_id else 'off (free tier only)'}")
    parts.append(f"Background monitoring: {'on' if s.enable_monitoring else 'off'}")
    from app.core.observability import error_tracking_enabled
    parts.append(
        "Error tracking: on" if error_tracking_enabled()
        else "Error tracking: OFF — production failures will only appear in the log stream (set SENTRY_DSN)"
    )
    # The analyst's canonical validator, reported at BOOT. When it cannot run, every model response is
    # discarded and every investigation serves the deterministic Floor, with no exception raised
    # anywhere to say so — the product looks like it is running an analyst and silently produces no
    # written analysis. That state used to be invisible until somebody read a page. One line here turns
    # it into the first thing the deploy log says.
    parts.append(f"Analyst canonical validator: {_validator_state()}")
    logger.info("Optional features: %s", " | ".join(parts))

    # Its OWN line, at WARNING when active, because this one changes who can use the product at all.
    # Buried in the features list it would be read past; the failure it prevents is an operator
    # wondering for an hour why every customer is being refused, or the reverse, a lockdown quietly
    # outliving its launch date. Either way nobody should have to guess which mode is live.
    from app.core import lockdown

    if lockdown.is_locked(s):
        logger.warning(lockdown.boot_line(s))
    else:
        logger.info(lockdown.boot_line(s))


def _validator_state() -> str:
    """Whether canonical validation can actually run, proven by validating a known-good object rather
    than by importing something and assuming. Never raises: a boot report must not break the boot."""
    try:
        from app.governor.canonical_validate import validate_analyst_response

        errs = validate_analyst_response(
            {"headline": "x"}, schema={"type": "object", "properties": {"headline": {"type": "string"}}})
        if any("unavailable" in str(e) for e in errs):
            return "BROKEN — reports itself unavailable; EVERY scan will fall back to the Floor"
        return "ok"
    except Exception as exc:  # noqa: BLE001
        return (f"BROKEN ({type(exc).__name__}) — EVERY scan will fall back to the Floor and produce "
                "no written analysis")


def _configure_logging() -> None:
    """JSON-line logger when OMI_ENV=production; readable text in dev."""
    settings = get_settings()
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    # Idempotent: clear handlers so reloads don't multiply lines.
    root = logging.getLogger()
    for h in list(root.handlers):
        root.removeHandler(h)
    handler = logging.StreamHandler()
    if settings.env == "production":
        handler.setFormatter(_JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)-5s %(name)s · %(message)s",
            datefmt="%H:%M:%S",
        ))
    root.addHandler(handler)
    root.setLevel(level)


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        import json
        payload = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


_DEV_SESSION_SECRET = "dev-only-change-me-please-12345678901234567890"
_MIN_SESSION_SECRET_LENGTH = 32
# The only accepted values for OMI_ENV. Anything else is a configuration error, never a silent
# downgrade to development — see _validate_production_config.
_KNOWN_ENVS = frozenset({"production", "development", "test"})


# A Clerk DEVELOPMENT instance is always hosted on this suffix; a production instance lives on the
# customer's own domain (here, clerk.omisphere.online).
_CLERK_DEV_HOST_SUFFIX = ".clerk.accounts.dev"


def _clerk_instance_problem() -> str | None:
    """Refuse a production deploy that verifies sessions against a Clerk DEVELOPMENT instance.

    This is the one production misconfiguration in this file that produced a *live* outage rather
    than a hypothetical one, and it is worth understanding why nothing else caught it.

    The API derives its JWKS URL and its expected issuer by base64-decoding the publishable key
    (``clerk_auth._issuer``). The browser gets its own copy of that key, on the *other* Render
    service, and nothing at runtime reconciles the two. So switching the web app to the production
    Clerk keys while the API still held the development ones produced a state where sign-in
    succeeded, a valid session JWT was issued by ``clerk.omisphere.online``, and the API rejected
    every request bearing it because it was still expecting ``*.clerk.accounts.dev``.

    The failure is silent by construction: :func:`verify_session_token` swallows every verification
    error and returns ``None``, because "this token is not valid" is normally just an anonymous
    request. There is no log line, no 500, no failed health check. The only symptom is a customer
    who is signed in to Clerk and has no workspace.

    Returns a problem string, or ``None`` if the pairing looks right.

    An ABSENT key is deliberately not a problem here: Clerk is optional in this codebase (the legacy
    cookie session path still authenticates), and ``render.yaml`` commits the publishable key as a
    value, so absence is not a state a real deploy of this blueprint reaches.
    """
    import os

    pk = (os.environ.get("NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY")
          or os.environ.get("CLERK_PUBLISHABLE_KEY") or "").strip()
    if not pk:
        return None

    # CLERK_ISSUER overrides the key-derived issuer (clerk_auth._issuer), so when it is set it, not
    # the key, is what the API actually verifies against.
    issuer = (os.environ.get("CLERK_ISSUER") or "").strip().rstrip("/")
    if issuer:
        if not issuer.endswith(_CLERK_DEV_HOST_SUFFIX):
            return None
        named = f"CLERK_ISSUER is {issuer}"
    else:
        if not pk.startswith("pk_test_"):
            return None
        named = "the Clerk publishable key is a pk_test_ (development instance) key"

    return (
        f"{named}. In production that means this API verifies session JWTs against a Clerk "
        "DEVELOPMENT instance. If the web app is on the production instance the two never agree: "
        "every user signs in successfully and then has no workspace, because verify_session_token "
        "silently returns None for a token from the other issuer. Set CLERK_PUBLISHABLE_KEY to the "
        "pk_live_ key, byte-identical to NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY on the web service, and "
        "redeploy BOTH (the issuer and JWKS client are cached per process)."
    )


class ProductionConfigError(RuntimeError):
    """Raised at boot when production environment is misconfigured.

    Hard-failing the deploy is the only honest signal: an API service that
    starts but can't perform its primary function (scan / store / sign cookies)
    silently strands users behind a green health check.
    """


def _validate_production_config(settings) -> None:
    """Refuse to start a production deploy that would lose data or strand users.

    Every check here represents a class of failure we've actually paid for:

    * SQLite on Render's ephemeral disk wipes ALL user accounts and saved
      investigations on every redeploy.
    * A missing YouTube key turns every scan into a silent 503 — the service
      is up but the product doesn't work.
    * The dev session secret is published in this file; leaving it in prod
      means anyone can forge admin cookies.
    * A short or default secret is functionally equivalent to no secret.

    Set ``OMI_ALLOW_DEGRADED_PRODUCTION=true`` to downgrade these to logged
    warnings — only intended for break-glass debugging.
    """
    # An UNRECOGNISED env is refused rather than treated as development. Every check below is gated
    # on `env == "production"` by exact string, so `prod`, `Production`, or a missing OMI_ENV silently
    # bought CORS `*` plus a total skip of the production checks — SQLite storage accepted, the
    # committed dev session secret accepted, missing API key accepted. A typo is a plausible way to
    # deploy a hardened service with all its hardening off, so the closed set is enforced here.
    if settings.env not in _KNOWN_ENVS:
        raise ProductionConfigError(
            f"OMI_ENV is {settings.env!r}, which is not one of {sorted(_KNOWN_ENVS)}. Refusing to "
            f"start: an unrecognised environment is treated as NON-production, which disables the "
            f"production safety checks and opens CORS to '*'. Set OMI_ENV=production for a live "
            f"deploy (exact lowercase)."
        )

    if settings.env != "production":
        return

    import os
    allow_degraded = os.environ.get("OMI_ALLOW_DEGRADED_PRODUCTION", "").lower() in (
        "1", "true", "yes",
    )
    problems: list[str] = []

    # --- 0. Authentication --------------------------------------------------
    # The most dangerous default in the codebase. `require_auth` is False by default, and when it is
    # False `require_user()` does not reject the request — it RETURNS a synthetic user with id=0,
    # is_admin=True and unlimited credits (app/core/auth.py). Nothing downstream distinguishes that
    # from a real admin, so a single absent OMI_REQUIRE_AUTH turned the whole API, including every
    # admin router, into an unauthenticated surface. Previously this was not checked at all: the
    # session-secret block below is gated on `if settings.require_auth`, so auth being OFF skipped its
    # own validation. Fail closed.
    if not settings.require_auth:
        problems.append(
            "OMI_REQUIRE_AUTH is not true. In production this is an AUTHENTICATION BYPASS, not a "
            "relaxed setting: every unauthenticated request is served as user id=0 with "
            "is_admin=True and unlimited credits, which exposes the admin routes, /v1/metrics, and "
            "all other users' data. Set OMI_REQUIRE_AUTH=true."
        )

    # --- 1. Persistent storage ----------------------------------------------
    if settings.database_url.startswith("sqlite"):
        problems.append(
            "OMI_DATABASE_URL is unset or points at SQLite. On Render the "
            "container filesystem is ephemeral — every redeploy will WIPE all "
            "user accounts, credits, subscriptions, and saved investigations. "
            "Provision the Postgres service from render.yaml and set "
            "OMI_DATABASE_URL to its internal connection string."
        )

    # --- 2. Session integrity -----------------------------------------------
    if settings.require_auth:
        if settings.session_secret == _DEV_SESSION_SECRET:
            problems.append(
                "OMI_SESSION_SECRET is the dev default. That secret is "
                "checked into the repo — anyone could forge a session cookie "
                "for any user, including admins. Set OMI_SESSION_SECRET to a "
                "random 64+ char string (Render's Blueprint generates this "
                "automatically when generateValue:true)."
            )
        elif len(settings.session_secret) < _MIN_SESSION_SECRET_LENGTH:
            problems.append(
                f"OMI_SESSION_SECRET is only {len(settings.session_secret)} "
                f"characters long. Use at least {_MIN_SESSION_SECRET_LENGTH} "
                "(a Python `secrets.token_urlsafe(64)` is the safe default)."
            )

    # --- 3. YouTube ingestion (the product's primary function) --------------
    yt_key = (settings.youtube_api_key or "").strip()
    if not yt_key:
        problems.append(
            "OMI_YOUTUBE_API_KEY is unset. Every scan endpoint will return "
            "503; the product is non-functional without this key. Create a "
            "YouTube Data API v3 key at console.cloud.google.com and set it "
            "as a Render environment variable."
        )

    # --- 4. Clerk instance pairing ------------------------------------------
    clerk_problem = _clerk_instance_problem()
    if clerk_problem:
        problems.append(clerk_problem)

    if not problems:
        return

    # Format a tidy error block so the deploy logs make the problem obvious.
    banner = "=" * 72
    body = "\n\n".join(f"  · {p}" for p in problems)
    block = (
        f"\n{banner}\n"
        f"OMISPHERE refused to start: production configuration is incomplete.\n"
        f"{banner}\n\n"
        f"{body}\n\n"
        f"If you absolutely must boot in a degraded state (e.g. recovery), "
        f"set OMI_ALLOW_DEGRADED_PRODUCTION=true and restart. This is unsafe.\n"
        f"{banner}"
    )

    if allow_degraded:
        logger.critical("Production config check OVERRIDDEN by OMI_ALLOW_DEGRADED_PRODUCTION.%s", block)
        return

    logger.critical("%s", block)
    raise ProductionConfigError(
        f"Production configuration incomplete ({len(problems)} issue"
        f"{'s' if len(problems) != 1 else ''}). See logs for the full list."
    )


def create_app() -> FastAPI:
    settings = get_settings()
    _validate_production_config(settings)

    app = FastAPI(
        title="OMISPHERE API",
        description=(
            "YouTube comment-section authenticity intelligence. "
            "Powered by the omi detection engine."
        ),
        version=__version__,
        docs_url="/docs",
        redoc_url=None,
        lifespan=lifespan,
    )

    # ---- Middleware stack (order matters; outermost first) ----
    # 1. CORS — tight in prod, loose in dev
    # (TrustedHostMiddleware removed: Render's edge handles host routing, and
    # the internal proxy sets Host: omisphere-api:10000 which doesn't match
    # *.onrender.com — causing 400 on every proxied request.)
    if settings.env == "production":
        origins = [settings.public_base_url] if settings.public_base_url else []
    else:
        origins = ["*"]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 2. Security headers (HSTS, CSP, frame, COOP, …)
    app.add_middleware(SecurityHeadersMiddleware)

    # 3. Request body cap — refuse oversized payloads before anything parses them. Added before the
    # rate limiter so the limiter ends up OUTSIDE it (Starlette makes the last-added the outermost):
    # a flood should be throttled first, then each surviving request size-checked.
    app.add_middleware(BodySizeLimitMiddleware)

    # 4. Global per-IP rate limit (scanners / abuse). Auth routes have stricter limiters.
    app.add_middleware(GlobalRateLimitMiddleware)

    # 4. Compression — Cuts scan-response payloads by ~70%.
    app.add_middleware(GZipMiddleware, minimum_size=1024)

    # 5. Per-request observability
    app.add_middleware(MetricsMiddleware)
    app.add_middleware(RequestIdMiddleware)

    # ---- Routers ----
    app.include_router(health.router)
    # Public and admin halves of the waitlist. The public one must stay reachable while the
    # product is locked (app/core/lockdown.OPEN_PREFIXES); it is the only thing a visitor can
    # do before launch.
    app.include_router(waitlist.router)
    app.include_router(waitlist.admin_router)
    app.include_router(analyze.router)
    app.include_router(intelligence.router)
    app.include_router(scan.router)
    app.include_router(scan_async.router)
    app.include_router(feedback.router)
    app.include_router(accounts.router)
    app.include_router(channels.router)
    app.include_router(narratives.router)
    app.include_router(coordination.admin_router)
    app.include_router(campaigns.router)
    app.include_router(campaigns.campaign_public_router)
    app.include_router(content.router)
    app.include_router(graph.router)
    app.include_router(investigations.router)
    app.include_router(reasoning.router)
    app.include_router(shadow.admin_router)
    app.include_router(improvement.admin_router)
    app.include_router(memory.admin_router)
    app.include_router(reports.share_router)
    app.include_router(reports.public_router)
    # Dispute queue + admin takedown. Admin-gated inside the handlers, like the other admin routers.
    app.include_router(reports.admin_router)
    # Upstream spend readout. Same admin gating.
    app.include_router(usage.router)
    app.include_router(monitoring.router)
    app.include_router(watchlists.router)
    app.include_router(learning.router)
    app.include_router(learning.admin_router)
    app.include_router(labels.router)
    app.include_router(activity.router)
    app.include_router(bulk.router)
    app.include_router(metrics.router)
    app.include_router(auth.router)
    app.include_router(billing.router)

    return app


app = create_app()
