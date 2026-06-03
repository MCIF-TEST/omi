"""Async single-link scan: run a comprehensive scan as a background job.

The synchronous ``POST /v1/scan/link`` (in ``scan.py``) holds one HTTP
connection open for the ENTIRE scan — fetch commenters, pull every history,
run the engine, persist. A large batch can outlast an upstream proxy's read
timeout (Render's load balancer, the Next.js ``/api`` rewrite, any CDN in
front): the connection is cut after the status line, the UI reaches "the last
step" and then shows no result — even though the investigation often finished
saving server-side.

This module decouples scan duration from any HTTP timeout:

* ``POST /v1/scan/link/start`` validates + classifies the URL, builds the
  platform Source, charges credits, and mints the investigation slug
  synchronously (so a bad link 400s and an out-of-credits user 402s up front,
  exactly like ``/link``), then submits the scan to the background pool and
  returns a job id + slug immediately (202).
* ``GET /v1/scan/link/status/{job_id}`` is polled until status is ``"done"``
  or ``"failed"``; on ``"done"`` the slug resolves to a saved investigation.

The heavy lifting (the scan, the all-commenters-failed guard, persistence) is
reused verbatim from ``scan.py`` so the async path and the synchronous path
stay byte-for-byte consistent.
"""

from __future__ import annotations

import logging
import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select

import app.routes.scan as scan_mod
from app.core import background
from app.core.auth import (
    CurrentUser,
    compute_scan_credits,
    consume_credits,
    refund_credits,
    require_user,
)
from app.core.config import Settings, get_settings
from app.integrations.source import Source, TwitterSource, YouTubeSource, classify_link
from app.integrations.twitter_errors import TwitterClientError
from app.integrations.youtube_errors import YouTubeClientError
from app.schemas import ComprehensiveScanRequest, Tier
from app.storage.db import get_session
from app.storage.models import ScanJob

log = logging.getLogger("omi.scan")

router = APIRouter(prefix="/v1/scan", tags=["scan"])


class LinkScanJobOut(BaseModel):
    """Async single-link scan job, returned by ``/link/start`` and
    ``/link/status/{job_id}``. ``status`` is the job lifecycle state; the other
    fields are filled in as the job completes."""

    job_id: str
    status: str  # "queued" | "running" | "done" | "failed"
    platform: str = ""
    url: str = ""
    investigation_slug: str | None = None
    tier: Tier | None = None
    overall_probability: float | None = None
    error: str | None = None


def _link_job_result(
    *, url: str, platform: str, status: str, slug: str | None,
    tier: str | None = None, probability: float | None = None,
    error: str | None = None,
) -> dict:
    """The single bookkeeping dict stored in ``ScanJob.results_json[0]``."""
    return {
        "url": url, "platform": platform, "status": status, "slug": slug,
        "tier": tier, "probability": probability, "error": error,
    }


def _link_job_out(job: ScanJob) -> LinkScanJobOut:
    """``ScanJob`` row → ``LinkScanJobOut`` (reads the single stored result
    dict). The outward status is the job lifecycle state."""
    results = job.results_json or []
    r = results[0] if results else {}
    return LinkScanJobOut(
        job_id=job.job_id,
        status=job.status,
        platform=r.get("platform") or "",
        url=r.get("url") or ((job.urls_json or [""])[0] if job.urls_json else ""),
        investigation_slug=r.get("slug"),
        tier=r.get("tier"),
        overall_probability=r.get("probability"),
        error=r.get("error"),
    )


@router.post(
    "/link/start",
    response_model=LinkScanJobOut,
    status_code=status.HTTP_202_ACCEPTED,
)
def scan_link_start(
    payload: dict,
    settings: Settings = Depends(get_settings),
    current: CurrentUser = Depends(require_user),
) -> LinkScanJobOut:
    """Kick off a comprehensive scan in the background; return a job id at once.

    Validates + classifies the URL, charges credits, and mints the investigation
    slug SYNCHRONOUSLY — so a bad link 400s and an out-of-credits user 402s up
    front, exactly like ``/link``. The scan itself runs on the background pool;
    poll ``GET /link/status/{job_id}`` until status is "done", then load the
    investigation by slug. A failed scan refunds the full charge.
    """
    url = (payload.get("url") or "").strip() if isinstance(payload, dict) else ""
    if not url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="url is required.",
        )
    classification = classify_link(url)
    platform = classification.get("platform", "unknown")
    if platform == "unknown" or classification.get("kind") == "unknown":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Unrecognized link. Paste a YouTube video/channel URL or an "
                "X (Twitter) profile or tweet URL."
            ),
        )

    try:
        requested_commenters = int(payload.get("max_commenters", 25) or 25)
    except (TypeError, ValueError):
        requested_commenters = 25
    max_commenters = max(1, min(requested_commenters, settings.scan_max_commenters))
    force_refresh = bool(payload.get("force_refresh", False))
    start_token = payload.get("start_page_token") or None
    requested_slug = payload.get("investigation_slug")

    # Build the creq + platform Source BEFORE charging — a mis-config (e.g. a
    # missing API key → 503) must never bill the user, exactly as /link does.
    # The Source is constructed here on the request thread and handed to the
    # worker, which is its sole user (no concurrent access across threads). The
    # test factory overrides live on the scan module, so look them up there at
    # runtime (they are reassigned by set_client_factory_for_tests).
    if platform == "x":
        creq = ComprehensiveScanRequest(
            video_url_or_id=classification.get("tweet_id"),
            account_url_or_handle=classification.get("handle"),
            comments_text=None, max_commenters=max_commenters,
            force_refresh=force_refresh, start_page_token=start_token,
        )
        tw_factory = scan_mod._twitter_client_factory_override or (
            lambda: scan_mod._resolve_twitter_client(settings)
        )
        source: Source = TwitterSource(tw_factory())
    else:
        creq = ComprehensiveScanRequest(
            video_url_or_id=classification.get("video_id"),
            account_url_or_handle=classification.get("account_input"),
            comments_text=None, max_commenters=max_commenters,
            force_refresh=force_refresh, start_page_token=start_token,
        )
        yt_factory = scan_mod._client_factory_override or (
            lambda: scan_mod._resolve_client(settings)
        )
        source = YouTubeSource(yt_factory())

    # Charge up front (the worker refunds on ANY failure) so an out-of-credits
    # user gets an immediate 402 instead of discovering it after a poll.
    cost = compute_scan_credits(platform, max_commenters, settings)
    consume_credits(
        current.id, cost,
        platform=platform, scan_type="link",
        target_input=url[:500], settings=settings,
    )

    # Mint the slug now so we can return it immediately — the worker persists
    # under exactly this slug, and a continuation batch (requested_slug owned by
    # the caller) merges into the existing investigation.
    try:
        slug = scan_mod._resolve_investigation_slug(
            requested_slug=requested_slug, user_id=current.id,
        )
        job_id = f"link_{secrets.token_hex(10)}"
        with get_session() as session:
            job = ScanJob(
                job_id=job_id,
                user_id=current.id,
                urls_json=[url],
                results_json=[_link_job_result(
                    url=url, platform=platform, status="pending", slug=slug,
                )],
                status="queued",
                total=1,
                completed=0,
                failed_count=0,
                credits_estimate=cost,
                credits_used=cost,
                max_commenters=max_commenters,
            )
            session.add(job)
            session.flush()
            db_id = job.id
        fut = background.submit(
            _run_link_scan_job,
            db_id=db_id, user_id=current.id, url=url, platform=platform,
            classification=classification, slug=slug, cost=cost,
            creq=creq, source=source,
        )
    except Exception:
        refund_credits(current.id, cost, reason="scan_start_error")
        raise

    if fut is None:
        # The background executor is unavailable — the scan would never run.
        # Refund, mark the job failed, and surface a clean 503.
        refund_credits(current.id, cost, reason="scan_start_error")
        with get_session() as session:
            job = session.get(ScanJob, db_id)
            if job:
                job.status = "failed"
                job.failed_count = 1
                job.credits_used = 0
                job.results_json = [_link_job_result(
                    url=url, platform=platform, status="failed", slug=slug,
                    error="The scan service is busy. Your credit was refunded — please try again.",
                )]
                session.flush()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The scan service is busy. Your credit was refunded — please try again.",
        )

    return LinkScanJobOut(
        job_id=job_id, status="queued", platform=platform, url=url,
        investigation_slug=slug,
    )


@router.get("/link/status/{job_id}", response_model=LinkScanJobOut)
def scan_link_status(
    job_id: str,
    current: CurrentUser = Depends(require_user),
) -> LinkScanJobOut:
    """Poll an async link-scan job. Terminal states are "done" and "failed"; on
    "done" the investigation_slug resolves to a fully saved investigation."""
    with get_session() as session:
        job = session.execute(
            select(ScanJob).where(
                ScanJob.job_id == job_id,
                ScanJob.user_id == current.id,
            )
        ).scalar_one_or_none()
        if job is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No scan job '{job_id}'.",
            )
        return _link_job_out(job)


def _run_link_scan_job(
    *, db_id: int, user_id: int, url: str, platform: str,
    classification: dict, slug: str, cost: int,
    creq: ComprehensiveScanRequest, source: "Source",
) -> None:
    """Background worker for /link/start. Mirrors scan_link's body: run the
    comprehensive scan with the Source built by the caller, persist the
    investigation under the pre-minted slug, and record terminal status on the
    ScanJob row. A failed scan refunds the full charge — a failed scan must
    never cost a credit."""
    settings = get_settings()

    def _finish(state: str, *, tier=None, probability=None, error=None,
                refund: bool = False) -> None:
        if refund:
            try:
                refund_credits(user_id, cost, reason="scan_failed")
            except Exception:
                log.exception("refund failed for link job %s", db_id)
        with get_session() as session:
            job = session.get(ScanJob, db_id)
            if job is None:
                return
            job.status = state
            job.completed = 1
            job.failed_count = 1 if state == "failed" else 0
            job.credits_used = 0 if state == "failed" else cost
            job.completed_at = datetime.now(timezone.utc)
            job.results_json = [_link_job_result(
                url=url, platform=platform,
                status=("ok" if state == "done" else "failed"),
                slug=slug, tier=tier, probability=probability, error=error,
            )]
            session.flush()

    # Mark running.
    with get_session() as session:
        job = session.get(ScanJob, db_id)
        if job is None:
            try:
                refund_credits(user_id, cost, reason="scan_job_missing")
            except Exception:
                log.exception("refund failed for missing link job %s", db_id)
            return
        job.status = "running"
        job.started_at = datetime.now(timezone.utc)
        session.flush()

    fake_user = CurrentUser(
        id=user_id, email="", credits_remaining=999,
        subscription_status=None, subscription_renews_at=None, is_admin=False,
    )

    try:
        result = scan_mod._run_comprehensive(
            creq, settings, fake_user, _charge_credit=False, source=source,
        )
    except (YouTubeClientError, TwitterClientError) as e:
        msg = getattr(e, "detail", None) or str(e) or "The scan failed. Your credit was refunded."
        log.warning("async link scan failed for %s: %s", url[:120], msg)
        _finish("failed", error=str(msg)[:300], refund=True)
        return
    except HTTPException as e:
        _finish("failed", error=str(e.detail)[:300], refund=True)
        return
    except Exception:
        log.exception("async comprehensive scan crashed for %s", url[:120])
        _finish(
            "failed",
            error="The scan failed unexpectedly and your credit was refunded. Please try again.",
            refund=True,
        )
        return

    # A scan where EVERY commenter errored is a systemic failure, not a result.
    if scan_mod._all_commenters_failed(result):
        _finish(
            "failed",
            error=("The scan reached the platform but could not analyze any commenters. "
                   "Your credit was refunded — please try again."),
            refund=True,
        )
        return

    # Persist under the pre-minted slug (same as scan_link Phase 5).
    result.investigation_slug = slug
    try:
        result_payload = scan_mod._serialize_result(result)
    except Exception:
        log.exception("could not serialise investigation payload for %s", slug)
        _finish(
            "failed",
            error="The scan completed but its result could not be saved. Your credit was refunded.",
            refund=True,
        )
        return

    saved = scan_mod._persist_investigation(
        slug=slug, user_id=user_id, classification=classification,
        url=url, payload=result_payload,
    )
    if not saved:
        log.error("async investigation %s could not be persisted", slug)
        _finish(
            "failed",
            error="The scan completed but could not be saved. Your credit was refunded.",
            refund=True,
        )
        return

    tier = result.overall_tier.value if hasattr(result.overall_tier, "value") else str(result.overall_tier)
    _finish("done", tier=tier, probability=result.overall_probability)
