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
    MetricsMiddleware, RequestIdMiddleware, SecurityHeadersMiddleware,
)
from app.monitoring import lifespan_monitoring
from app.routes import (
    accounts, analyze, auth, billing, content, graph, health, investigations,
    metrics, monitoring, narratives, reasoning, reports, scan, watchlists,
)
from app.storage.db import init_db


logger = logging.getLogger("omi")


@asynccontextmanager
async def lifespan(app: FastAPI):
    _configure_logging()
    init_db()
    from app.content.seed import seed_example_content
    seed_example_content()
    async with lifespan_monitoring(app):
        try:
            yield
        finally:
            # Drain in-flight background tasks before shutdown so a deploy
            # doesn't lose narrative ingestion / fan-out work.
            background.shutdown()


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
    if settings.env != "production":
        return

    import os
    allow_degraded = os.environ.get("OMI_ALLOW_DEGRADED_PRODUCTION", "").lower() in (
        "1", "true", "yes",
    )
    problems: list[str] = []

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

    # 2. Security headers
    app.add_middleware(SecurityHeadersMiddleware)

    # 3. Compression — Cuts scan-response payloads by ~70%.
    app.add_middleware(GZipMiddleware, minimum_size=1024)

    # 4. Per-request observability
    app.add_middleware(MetricsMiddleware)
    app.add_middleware(RequestIdMiddleware)

    # ---- Routers ----
    app.include_router(health.router)
    app.include_router(analyze.router)
    app.include_router(scan.router)
    app.include_router(accounts.router)
    app.include_router(narratives.router)
    app.include_router(content.router)
    app.include_router(graph.router)
    app.include_router(investigations.router)
    app.include_router(reasoning.router)
    app.include_router(reports.share_router)
    app.include_router(reports.public_router)
    app.include_router(monitoring.router)
    app.include_router(watchlists.router)
    app.include_router(metrics.router)
    app.include_router(auth.router)
    app.include_router(billing.router)

    return app


app = create_app()
