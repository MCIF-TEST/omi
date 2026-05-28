"""Bulk scan queue — submit a list of URLs, get results back asynchronously.

Each POST creates a ScanJob row and starts a FastAPI BackgroundTask that
processes URLs sequentially. The client polls GET /{job_id} until
status == "done". Credits are consumed per URL; failed items are refunded.
"""

from __future__ import annotations

import logging
import secrets
import traceback
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy import select

from app.core.auth import CurrentUser, consume_credits, refund_credits, require_user
from app.core.config import get_settings
from app.integrations.youtube_errors import YouTubeClientError
from app.schemas import (
    BulkScanJobResponse,
    BulkScanJobResult,
    BulkScanJobSummary,
    BulkScanJobsListResponse,
    BulkScanRequest,
)
from app.storage.db import get_session
from app.storage.models import ScanJob

log = logging.getLogger("omi.bulk")

router = APIRouter(prefix="/v1/scan/bulk", tags=["bulk"])

_MAX_CONCURRENT_JOBS = 3  # per-user soft cap


@router.post("", response_model=BulkScanJobResponse, status_code=status.HTTP_202_ACCEPTED)
def create_bulk_job(
    body: BulkScanRequest,
    background_tasks: BackgroundTasks,
    current: CurrentUser = Depends(require_user),
) -> BulkScanJobResponse:
    """Submit a list of up to 20 YouTube URLs for sequential background scanning.

    Returns immediately with a job_id. Poll GET /v1/scan/bulk/{job_id} for
    progress. Each URL costs 1 credit; failed items are refunded automatically.
    """
    urls = [u.strip() for u in body.urls if u.strip()]
    if not urls:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="At least one non-empty URL is required.",
        )
    if len(urls) > 20:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Maximum 20 URLs per bulk job.",
        )

    # Check for too many active jobs.
    with get_session() as session:
        active_count = session.execute(
            select(ScanJob).where(
                ScanJob.user_id == current.id,
                ScanJob.status.in_(["queued", "running"]),
            )
        ).scalars().all()
        if len(active_count) >= _MAX_CONCURRENT_JOBS:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"You have {len(active_count)} active jobs. Wait for them to finish first.",
            )

        credits_needed = len(urls)
        if current.credits_remaining < credits_needed:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail=f"This job needs {credits_needed} credits; you have {current.credits_remaining}.",
            )

        job_id = f"job_{secrets.token_hex(10)}"
        initial_results = [
            {"url": u, "status": "pending", "slug": None, "tier": None, "probability": None, "error": None}
            for u in urls
        ]
        job = ScanJob(
            job_id=job_id,
            user_id=current.id,
            urls_json=urls,
            results_json=initial_results,
            status="queued",
            total=len(urls),
            completed=0,
            failed_count=0,
            credits_estimate=credits_needed,
            credits_used=0,
            max_commenters=body.max_commenters,
        )
        session.add(job)
        session.flush()
        db_id = job.id

    background_tasks.add_task(_run_job, db_id, current.id, urls, body.max_commenters)
    return BulkScanJobResponse(
        job=_job_summary(job_id, "queued", len(urls), 0, 0, credits_needed, 0,
                         job.created_at, None, None),
        results=[BulkScanJobResult(**r) for r in initial_results],
    )


@router.get("", response_model=BulkScanJobsListResponse)
def list_bulk_jobs(
    limit: int = Query(20, ge=1, le=50),
    current: CurrentUser = Depends(require_user),
) -> BulkScanJobsListResponse:
    """List the current user's recent bulk jobs, newest first."""
    with get_session() as session:
        rows = list(session.execute(
            select(ScanJob)
            .where(ScanJob.user_id == current.id)
            .order_by(ScanJob.created_at.desc())
            .limit(limit)
        ).scalars())
    return BulkScanJobsListResponse(jobs=[_row_to_summary(r) for r in rows])


@router.get("/{job_id}", response_model=BulkScanJobResponse)
def get_bulk_job(
    job_id: str,
    current: CurrentUser = Depends(require_user),
) -> BulkScanJobResponse:
    """Poll a bulk job's status and partial results."""
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
                detail=f"No job '{job_id}'.",
            )
        return BulkScanJobResponse(
            job=_row_to_summary(job),
            results=[BulkScanJobResult(**r) for r in (job.results_json or [])],
        )


# ---------------------------------------------------------------------------
# Background worker
# ---------------------------------------------------------------------------


def _run_job(db_id: int, user_id: int, urls: list[str], max_commenters: int) -> None:
    """Sequential URL processor. Runs in a FastAPI BackgroundTask (in-process).

    Errors on individual URLs refund the credit and mark that result as
    'failed'. The job continues with remaining URLs regardless.
    """
    now = datetime.now(timezone.utc)
    with get_session() as session:
        job = session.get(ScanJob, db_id)
        if job is None:
            return
        job.status = "running"
        job.started_at = now
        session.flush()

    settings = get_settings()

    for i, url in enumerate(urls):
        _process_one_url(db_id=db_id, user_id=user_id, url=url, idx=i,
                         max_commenters=max_commenters, settings=settings)

    # Mark done.
    with get_session() as session:
        job = session.get(ScanJob, db_id)
        if job:
            job.status = "done"
            job.completed_at = datetime.now(timezone.utc)
            session.flush()


def _process_one_url(
    *, db_id: int, user_id: int, url: str, idx: int,
    max_commenters: int, settings,
) -> None:
    try:
        consume_credits(user_id, 1, reason=f"bulk:{url[:80]}")
    except Exception as e:
        _update_result(db_id, idx, {"url": url, "status": "failed",
                                     "error": f"credit error: {e}"})
        return

    try:
        result = _scan_url(url, max_commenters=max_commenters, user_id=user_id, settings=settings)
        with get_session() as session:
            job = session.get(ScanJob, db_id)
            if job:
                _set_result(job, idx, result)
                job.completed = (job.completed or 0) + 1
                job.credits_used = (job.credits_used or 0) + 1
                session.flush()
    except Exception as exc:
        log.warning("bulk job %s url %s failed: %s", db_id, url[:80], exc)
        try:
            refund_credits(user_id, 1, reason=f"bulk_fail:{url[:60]}")
        except Exception:
            pass
        with get_session() as session:
            job = session.get(ScanJob, db_id)
            if job:
                err_msg = str(exc)[:200]
                _set_result(job, idx, {"url": url, "status": "failed",
                                        "error": err_msg, "slug": None,
                                        "tier": None, "probability": None})
                job.completed = (job.completed or 0) + 1
                job.failed_count = (job.failed_count or 0) + 1
                session.flush()


def _scan_url(url: str, *, max_commenters: int, user_id: int, settings) -> dict:
    """Run a comprehensive scan for one URL. Credit already consumed by caller."""
    from app.integrations.youtube import classify_url
    from app.routes.scan import scan_comprehensive_endpoint
    from app.schemas import ComprehensiveScanRequest

    url_type = classify_url(url)
    if url_type == "channel":
        req = ComprehensiveScanRequest(
            account_url_or_handle=url, max_commenters=max_commenters
        )
    else:
        req = ComprehensiveScanRequest(
            video_url_or_id=url, max_commenters=max_commenters
        )

    from app.core.auth import CurrentUser as _CU
    fake_user = _CU(id=user_id, email="", credits_remaining=999,
                     subscription_status=None, subscription_renews_at=None,
                     is_admin=False)

    result = scan_comprehensive_endpoint(req, settings, current=fake_user, _charge_credit=False)

    slug = result.investigation_slug
    tier = result.overall_tier.value if hasattr(result.overall_tier, "value") else str(result.overall_tier)
    return {
        "url": url,
        "status": "ok",
        "slug": slug,
        "tier": tier,
        "probability": result.overall_probability,
        "error": None,
    }


def _set_result(job: ScanJob, idx: int, result: dict) -> None:
    results = list(job.results_json or [])
    if idx < len(results):
        results[idx] = result
    else:
        results.append(result)
    job.results_json = results


def _update_result(db_id: int, idx: int, result: dict) -> None:
    with get_session() as session:
        job = session.get(ScanJob, db_id)
        if job:
            _set_result(job, idx, result)
            job.completed = (job.completed or 0) + 1
            job.failed_count = (job.failed_count or 0) + 1
            session.flush()


def _row_to_summary(job: ScanJob) -> BulkScanJobSummary:
    return _job_summary(
        job.job_id, job.status, job.total, job.completed, job.failed_count,
        job.credits_estimate, job.credits_used,
        job.created_at, job.started_at, job.completed_at,
    )


def _job_summary(
    job_id, status, total, completed, failed_count,
    credits_estimate, credits_used,
    created_at, started_at, completed_at,
) -> BulkScanJobSummary:
    return BulkScanJobSummary(
        job_id=job_id,
        status=status,
        total=total,
        completed=completed,
        failed_count=failed_count,
        credits_estimate=credits_estimate,
        credits_used=credits_used,
        created_at=created_at,
        started_at=started_at,
        completed_at=completed_at,
    )
