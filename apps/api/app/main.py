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
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app import __version__
from app.core import background
from app.core.config import get_settings
from app.core.middleware import (
    MetricsMiddleware, RequestIdMiddleware, SecurityHeadersMiddleware,
)
from app.monitoring import lifespan_monitoring
from app.routes import (
    accounts, analyze, auth, billing, graph, health, investigations,
    metrics, monitoring, narratives, reasoning, reports, scan, watchlists,
)
from app.storage.db import init_db


logger = logging.getLogger("omi")


@asynccontextmanager
async def lifespan(app: FastAPI):
    _configure_logging()
    init_db()
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


def _verify_production_config(settings) -> None:
    """Guard against the dev session secret leaking into production.

    The dev default would let anyone forge cookies — instead of failing the
    deploy (which strands a running service), we override the in-memory
    secret with a fresh random one and log a CRITICAL warning. Sessions
    won't survive restarts until OMI_SESSION_SECRET is properly set.
    """
    if settings.env != "production":
        return
    if settings.require_auth and settings.session_secret == _DEV_SESSION_SECRET:
        import secrets as _secrets
        settings.session_secret = _secrets.token_urlsafe(64)
        logger.critical(
            "OMI_SESSION_SECRET is unset in production — using a random "
            "process-local value. Sessions will invalidate on every restart. "
            "Set OMI_SESSION_SECRET in the Render dashboard or redeploy from "
            "the Blueprint (generateValue:true) to fix permanently."
        )


def create_app() -> FastAPI:
    settings = get_settings()
    _verify_production_config(settings)

    app = FastAPI(
        title="OMISPHERE API",
        description=(
            "Probabilistic social authenticity intelligence. "
            "Powered by the omi detection engine."
        ),
        version=__version__,
        docs_url="/docs",
        redoc_url=None,
        lifespan=lifespan,
    )

    # ---- Middleware stack (order matters; outermost first) ----
    # 1. Trusted hosts in production (drop traffic to unexpected Hosts)
    if settings.env == "production" and settings.public_base_url:
        from urllib.parse import urlparse
        host = urlparse(settings.public_base_url).hostname
        if host:
            # Allow the configured host, plus *.onrender.com for direct probes.
            app.add_middleware(
                TrustedHostMiddleware,
                allowed_hosts=[host, "*.onrender.com"],
            )

    # 2. CORS — tight in prod, loose in dev
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

    # 3. Security headers
    app.add_middleware(SecurityHeadersMiddleware)

    # 4. Compression — Cuts scan-response payloads by ~70%.
    app.add_middleware(GZipMiddleware, minimum_size=1024)

    # 5. Per-request observability
    app.add_middleware(MetricsMiddleware)
    app.add_middleware(RequestIdMiddleware)

    # ---- Routers ----
    app.include_router(health.router)
    app.include_router(analyze.router)
    app.include_router(scan.router)
    app.include_router(accounts.router)
    app.include_router(narratives.router)
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
