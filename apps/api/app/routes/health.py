from __future__ import annotations

from sqlalchemy import func, select

from fastapi import APIRouter

from app import __version__
from app.core.config import get_settings
from app.schemas import EngineStatus
from app.storage.db import get_session
from app.storage.models import Account, CommenterEngagement, Scan, VideoScan

router = APIRouter(tags=["health"])


@router.get("/")
def root() -> dict[str, str]:
    """Root landing — explains this is the API and points at the docs."""
    return {
        "service": "OMISPHERE API",
        "version": __version__,
        "docs": "/docs",
        "health": "/health",
    }


@router.get("/health")
def health() -> dict[str, str]:
    """Liveness probe. Also touches the DB so platform health checks
    catch a broken database connection (Render uses this)."""
    try:
        with get_session() as session:
            session.execute(select(func.count(Account.id))).scalar_one()
        db_ok = True
    except Exception:
        db_ok = False
    return {
        "status": "ok" if db_ok else "degraded",
        "version": __version__,
        "db": "ok" if db_ok else "error",
    }


@router.get("/v1/status", response_model=EngineStatus)
def engine_status() -> EngineStatus:
    """Live state of the detection engine. Polled by the UI header so the
    operator can see the fingerprint database growing in real time.

    Cached for 5s in process — every browser tab polls this every 8s, so
    in a multi-tab session the cache eliminates near-duplicate DB scans.
    """
    from app.core.cache import get_cache
    cache = get_cache()
    cached = cache.get("v1.status")
    if cached is not None:
        return cached
    settings = get_settings()
    with get_session() as session:
        total_accounts = session.execute(select(func.count(Account.id))).scalar_one()
        total_scans = session.execute(select(func.count(Scan.id))).scalar_one()
        total_edges = session.execute(
            select(func.count(CommenterEngagement.id))
        ).scalar_one()
        total_video_scans = session.execute(
            select(func.count(VideoScan.id))
        ).scalar_one()
        fingerprints = session.execute(
            select(func.count(Account.id)).where(Account.fingerprint_json.is_not(None))
        ).scalar_one()
        last_scan = session.execute(
            select(func.max(Scan.scanned_at))
        ).scalar_one()
    result = EngineStatus(
        version=__version__,
        env=settings.env,
        total_accounts=int(total_accounts or 0),
        total_scans=int(total_scans or 0),
        total_engagement_edges=int(total_edges or 0),
        total_video_scans=int(total_video_scans or 0),
        fingerprints_stored=int(fingerprints or 0),
        last_scan_at=last_scan,
        youtube_configured=bool(settings.youtube_api_key and settings.youtube_api_key.strip()),
        auth_required=bool(settings.require_auth),
        billing_configured=bool(
            settings.stripe_secret_key and settings.stripe_price_id
        ),
        monthly_credit_grant=int(settings.monthly_credit_grant),
        storage_ephemeral=settings.database_url.startswith("sqlite"),
    )
    cache.set("v1.status", result, ttl_seconds=5)
    return result
