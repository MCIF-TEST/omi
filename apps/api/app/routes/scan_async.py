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

import json
import logging
import secrets
from datetime import datetime, timedelta, timezone

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
from app.storage.models import CandidateList, CommenterCandidate, ScanJob

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


class ScanEstimateOut(BaseModel):
    """Pre-scan cost preview. Mirrors what ``/link/start`` will actually charge
    and process, computed from the SAME helpers (classify_link → cap →
    compute_scan_credits) so the displayed estimate can never drift from the
    real charge."""

    platform: str  # "youtube" | "x" | "unknown"
    kind: str
    recognized: bool
    requested_max_commenters: int
    effective_max_commenters: int  # after the server-side cap
    max_commenters_cap: int
    credits: int | None  # None when the link isn't a recognizable target


# --------------------------------------------------------------------------- #
# Select-then-scan — the FREE "compile" step: list + cache a post's commenters.
# --------------------------------------------------------------------------- #
class CommenterCandidateOut(BaseModel):
    external_id: str
    handle: str | None = None
    comment: str | None = None
    comment_count: int = 1
    avatar_url: str | None = None
    scanned: bool = False


class CommenterListOut(BaseModel):
    platform: str
    content_id: str
    url: str | None = None
    commenters: list[CommenterCandidateOut]
    total: int
    has_more: bool          # more commenters can still be pulled ("add 25/50 more")
    fetched_now: int = 0     # how many NEW commenters this call added


def _source_for_platform(platform: str, settings: Settings) -> Source:
    """Build the platform Source using the SAME client factories the scan routes use (so a test override
    or a missing-key 503 behaves identically to a real scan)."""
    if platform == "x":
        factory = scan_mod._twitter_client_factory_override or (lambda: scan_mod._resolve_twitter_client(settings))
        return TwitterSource(factory())
    factory = scan_mod._client_factory_override or (lambda: scan_mod._resolve_client(settings))
    return YouTubeSource(factory())


@router.post("/link/commenters", response_model=CommenterListOut)
def list_commenters(
    payload: dict,
    settings: Settings = Depends(get_settings),
    current: CurrentUser = Depends(require_user),
) -> CommenterListOut:
    """FREE compile step of the select-then-scan flow: fetch (and cache) the commenters on a post so the
    user can pick which to actually scan. NO histories, NO detection, NO AI, NO credits.

    Re-opening a post returns its cached list instantly. Pass ``fetch`` > 0 to pull the NEXT page of
    commenters ("add 25/50 more"); it continues from the saved pagination cursor. ``refresh`` rebuilds
    the list from scratch. The commenter's raw ``commenters_meta`` + comments are cached so the later
    score step can run on ONLY the selected accounts without re-fetching the list."""
    url = (payload.get("url") or "").strip() if isinstance(payload, dict) else ""
    if not url:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="url is required.")
    classification = classify_link(url)
    platform = classification.get("platform", "unknown")
    content_id = classification.get("tweet_id") or classification.get("video_id")
    if platform == "unknown" or not content_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Paste a YouTube video or an X (Twitter) post URL to list its commenters.",
        )
    refresh = bool(payload.get("refresh"))
    uid = current.id if current.id != 0 else None
    cap = settings.scan_max_commenters

    with get_session() as session:
        cond = [CandidateList.platform == platform, CandidateList.content_id == content_id]
        cond.append(CandidateList.user_id.is_(None) if uid is None else CandidateList.user_id == uid)
        cl = session.execute(select(CandidateList).where(*cond)).scalar_one_or_none()
        if cl is None:
            cl = CandidateList(user_id=uid, platform=platform, content_id=content_id, content_url=url)
            session.add(cl)
            session.flush()

        existing = list(session.execute(
            select(CommenterCandidate)
            .where(CommenterCandidate.list_id == cl.id)
            .order_by(CommenterCandidate.seq)
        ).scalars().all())

        if refresh and existing:
            for row in existing:
                session.delete(row)
            existing = []
            cl.next_cursor = None
            cl.exhausted = False
            session.flush()

        # How many NEW commenters to pull on THIS call: default to a first page when the list is empty,
        # otherwise fetch only when the client explicitly asks ("add more").
        raw_fetch = payload.get("fetch")
        if raw_fetch is None:
            fetch_n = 0 if existing else 25
        else:
            try:
                fetch_n = max(0, min(int(raw_fetch), cap))
            except (TypeError, ValueError):
                fetch_n = 25

        fetched_now = 0
        if fetch_n > 0 and not cl.exhausted:
            source = _source_for_platform(platform, settings)
            try:
                commenters_meta, all_comments, next_cursor = source.fetch_content_engagers(
                    content_id, max_commenters=fetch_n, max_comments=fetch_n * 3,
                    start_page_token=cl.next_cursor,
                )
            except (TwitterClientError, YouTubeClientError) as exc:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"Could not fetch the commenters: {exc}",
                ) from exc

            comments_by_author: dict[str, list[dict]] = {}
            for c in all_comments:
                comments_by_author.setdefault(str(c.get("author_external_id") or ""), []).append(c)

            seen = {row.external_id for row in existing}
            next_seq = (max((row.seq for row in existing), default=-1) + 1)
            for meta in commenters_meta:
                ext = str(meta.get("channel_id") or meta.get("handle") or "").strip()
                if not ext or ext in seen:
                    continue
                cmts = comments_by_author.get(ext, [])
                exemplar = next((str(c.get("text")) for c in cmts if c.get("text")), None)
                session.add(CommenterCandidate(
                    list_id=cl.id, external_id=ext, handle=meta.get("handle"),
                    avatar_url=meta.get("avatar_url"), comment_text=exemplar,
                    comment_count=max(1, len(cmts)), seq=next_seq,
                    meta_json=json.dumps(meta), comments_json=json.dumps(cmts),
                ))
                seen.add(ext)
                next_seq += 1
                fetched_now += 1
            cl.next_cursor = next_cursor
            cl.exhausted = not next_cursor
            session.flush()

        rows = list(session.execute(
            select(CommenterCandidate)
            .where(CommenterCandidate.list_id == cl.id)
            .order_by(CommenterCandidate.seq)
        ).scalars().all())
        commenters = [
            CommenterCandidateOut(
                external_id=r.external_id, handle=r.handle, comment=r.comment_text,
                comment_count=r.comment_count, avatar_url=r.avatar_url, scanned=r.scanned,
            )
            for r in rows
        ]
        return CommenterListOut(
            platform=platform, content_id=content_id, url=cl.content_url or url,
            commenters=commenters, total=len(commenters),
            has_more=not cl.exhausted, fetched_now=fetched_now,
        )


@router.post("/estimate", response_model=ScanEstimateOut)
def estimate_scan(
    payload: dict,
    settings: Settings = Depends(get_settings),
    current: CurrentUser = Depends(require_user),
) -> ScanEstimateOut:
    """Preview a link scan's credit cost and the number of commenters it will
    actually process. Pure URL classification — no external calls, no charge.

    Deliberately recomputes via the exact path ``/link/start`` charges on
    (``classify_link`` → clamp to ``scan_max_commenters`` → ``compute_scan_credits``),
    so the UI's "≈ N credits" can never disagree with the real deduction.
    """
    url = (payload.get("url") or "").strip()
    try:
        requested = int(payload.get("max_commenters", 25) or 25)
    except (TypeError, ValueError):
        requested = 25
    cap = settings.scan_max_commenters
    effective = max(1, min(requested, cap))
    classification = classify_link(url) if url else {"platform": "unknown", "kind": "unknown"}
    platform = classification.get("platform", "unknown")
    kind = classification.get("kind", "unknown")
    recognized = platform != "unknown" and kind != "unknown"
    credits = compute_scan_credits(platform, effective, settings) if recognized else None
    return ScanEstimateOut(
        platform=platform,
        kind=kind,
        recognized=recognized,
        requested_max_commenters=requested,
        effective_max_commenters=effective,
        max_commenters_cap=cap,
        credits=credits,
    )


def _link_job_result(
    *, url: str, platform: str, status: str, slug: str | None,
    tier: str | None = None, probability: float | None = None,
    error: str | None = None, telemetry: dict | None = None,
) -> dict:
    """The single bookkeeping dict stored in ``ScanJob.results_json[0]``.

    ``telemetry`` persists the measured investigation cost (api calls, runtime,
    commenters, peak RSS, outcome) on the job row so it can be analyzed later —
    the observability sink, alongside the structured log line.
    """
    return {
        "url": url, "platform": platform, "status": status, "slug": slug,
        "tier": tier, "probability": probability, "error": error,
        "telemetry": telemetry or {},
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


def reap_stale_scan_jobs(
    timeout_seconds: int, *, user_id: int | None = None, job_id: str | None = None
) -> int:
    """Mark scan jobs stuck in queued/running past the budget as failed + refund.

    The safety net for the cases the worker can't self-report: a scan slower than
    the budget, or a worker killed mid-scan (OOM / redeploy) that never wrote a
    terminal status. Without this a job polls forever and the credit is stranded.
    Idempotent and transition-guarded (row lock + status check) so the credit is
    refunded exactly once, even racing a late-finishing worker. Returns the count
    reaped. Scope to a user/job to keep the per-request sweep cheap.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=timeout_seconds)
    with get_session() as session:
        q = select(ScanJob).where(
            ScanJob.status.in_(["queued", "running"]),
            ScanJob.created_at < cutoff,
        )
        if user_id is not None:
            q = q.where(ScanJob.user_id == user_id)
        if job_id is not None:
            q = q.where(ScanJob.job_id == job_id)
        candidate_ids = [j.id for j in session.execute(q).scalars()]

    reaped = 0
    for cid in candidate_ids:
        refund_amt = 0
        uid = None
        with get_session() as session:
            job = session.get(ScanJob, cid, with_for_update=True)
            if job is None or job.status not in ("queued", "running"):
                continue  # finished or reaped by someone else first
            job.status = "failed"
            job.completed = 1
            job.failed_count = 1
            refund_amt = int(job.credits_estimate or 0)
            uid = job.user_id
            job.credits_used = 0
            job.completed_at = datetime.now(timezone.utc)
            existing = (job.results_json or [{}])
            r = dict(existing[0]) if existing else {}
            r["status"] = "failed"
            r["error"] = (
                "This scan ran past its time budget and was stopped. Your credit "
                "was refunded — try a smaller batch, or retry."
            )
            r["telemetry"] = {**(r.get("telemetry") or {}), "outcome": "failed", "reaped": True}
            job.results_json = [r]
            session.flush()
        if refund_amt and uid is not None:
            try:
                refund_credits(uid, refund_amt, reason="scan_timeout_reap")
            except Exception:
                log.exception("refund failed reaping scan job id=%s", cid)
        reaped += 1
    if reaped:
        log.warning("reaped %d stale scan job(s) past %ds budget", reaped, timeout_seconds)
    return reaped


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

    # Reap any of this user's jobs stuck past the budget (refund + clear stale
    # 'running' rows) before kicking off a new one.
    reap_stale_scan_jobs(settings.scan_job_timeout_seconds, user_id=current.id)

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
    settings: Settings = Depends(get_settings),
    current: CurrentUser = Depends(require_user),
) -> LinkScanJobOut:
    """Poll an async link-scan job. Terminal states are "done" and "failed"; on
    "done" the investigation_slug resolves to a fully saved investigation.

    Reaps this job first if it's stuck past the time budget, so a hung/dead scan
    returns a clean failed+refunded status here instead of polling forever.
    """
    reap_stale_scan_jobs(
        settings.scan_job_timeout_seconds, user_id=current.id, job_id=job_id
    )
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


@router.post("/link/score", response_model=LinkScanJobOut, status_code=status.HTTP_202_ACCEPTED)
def score_selection(
    payload: dict,
    settings: Settings = Depends(get_settings),
    current: CurrentUser = Depends(require_user),
) -> LinkScanJobOut:
    """Score the SELECTED commenters from a post's cached compile list — the paid step of the
    select-then-scan flow. Runs history + detection + AI on ONLY the picked accounts, charges credits per
    selected, and grows the post's investigation (later selections continue into the same one). Async:
    poll ``GET /link/status/{job_id}``; on "done" load the investigation by slug."""
    url = (payload.get("url") or "").strip() if isinstance(payload, dict) else ""
    if not url:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="url is required.")
    raw_sel = payload.get("selected") or payload.get("external_ids") or []
    selected = [str(s).strip() for s in raw_sel if str(s).strip()] if isinstance(raw_sel, list) else []
    if not selected:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Select at least one commenter to scan.",
        )
    classification = classify_link(url)
    platform = classification.get("platform", "unknown")
    content_id = classification.get("tweet_id") or classification.get("video_id")
    if platform == "unknown" or not content_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Paste a YouTube video or an X (Twitter) post URL.",
        )
    uid = current.id if current.id != 0 else None

    # Reconstruct the scan input for ONLY the selected commenters from the cache (no re-fetch of the list).
    with get_session() as session:
        cond = [CandidateList.platform == platform, CandidateList.content_id == content_id]
        cond.append(CandidateList.user_id.is_(None) if uid is None else CandidateList.user_id == uid)
        cl = session.execute(select(CandidateList).where(*cond)).scalar_one_or_none()
        if cl is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No commenter list for this post yet — list its commenters first.",
            )
        rows = list(session.execute(
            select(CommenterCandidate).where(
                CommenterCandidate.list_id == cl.id,
                CommenterCandidate.external_id.in_(selected),
            ).order_by(CommenterCandidate.seq)
        ).scalars().all())
        if not rows:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="None of the selected commenters are in this post's list.",
            )
        injected_commenters: list[dict] = []
        injected_comments: list[dict] = []
        selected_ids: list[str] = []
        for r in rows:
            try:
                injected_commenters.append(json.loads(r.meta_json))
            except (TypeError, ValueError):
                continue
            selected_ids.append(r.external_id)
            if r.comments_json:
                try:
                    injected_comments.extend(json.loads(r.comments_json))
                except (TypeError, ValueError):
                    pass
        cl_id = cl.id
        existing_slug = cl.investigation_slug
        content_url = cl.content_url or url

    if not selected_ids:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No scannable selection.")

    reap_stale_scan_jobs(settings.scan_job_timeout_seconds, user_id=current.id)

    # Build creq (with the injected selection) + Source BEFORE charging, so a mis-config never bills.
    creq = ComprehensiveScanRequest(
        video_url_or_id=content_id, account_url_or_handle=None, comments_text=None,
        # max_commenters is unused on the injected path (the selection replaces the fetch); keep it valid
        # for the schema. The real charge is computed below from the selection count.
        max_commenters=max(5, len(selected_ids)), force_refresh=False,
        injected_commenters=injected_commenters, injected_comments=injected_comments,
    )
    source = _source_for_platform(platform, settings)

    # Charge per SELECTED commenter (the free list cost nothing). Worker refunds on any failure.
    cost = compute_scan_credits(platform, len(selected_ids), settings)
    consume_credits(
        current.id, cost, platform=platform, scan_type="link_select",
        target_input=content_url[:500], settings=settings,
    )
    try:
        slug = scan_mod._resolve_investigation_slug(requested_slug=existing_slug, user_id=current.id)
        job_id = f"link_{secrets.token_hex(10)}"
        with get_session() as session:
            job = ScanJob(
                job_id=job_id, user_id=current.id, urls_json=[content_url],
                results_json=[_link_job_result(
                    url=content_url, platform=platform, status="pending", slug=slug,
                )],
                status="queued", total=1, completed=0, failed_count=0,
                credits_estimate=cost, credits_used=cost, max_commenters=len(selected_ids),
            )
            session.add(job)
            session.flush()
            db_id = job.id
        fut = background.submit(
            _run_link_scan_job,
            db_id=db_id, user_id=current.id, url=content_url, platform=platform,
            classification=classification, slug=slug, cost=cost, creq=creq, source=source,
            candidate_list_id=cl_id, selected_ids=selected_ids,
        )
    except Exception:
        refund_credits(current.id, cost, reason="scan_start_error")
        raise

    if fut is None:
        refund_credits(current.id, cost, reason="scan_start_error")
        with get_session() as session:
            job = session.get(ScanJob, db_id)
            if job:
                job.status = "failed"
                job.failed_count = 1
                job.credits_used = 0
                job.results_json = [_link_job_result(
                    url=content_url, platform=platform, status="failed", slug=slug,
                    error="The scan service is busy. Your credit was refunded — please try again.",
                )]
                session.flush()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The scan service is busy. Your credit was refunded — please try again.",
        )

    return LinkScanJobOut(
        job_id=job_id, status="queued", platform=platform, url=content_url,
        investigation_slug=slug,
    )


def _run_link_scan_job(
    *, db_id: int, user_id: int, url: str, platform: str,
    classification: dict, slug: str, cost: int,
    creq: ComprehensiveScanRequest, source: "Source",
    candidate_list_id: int | None = None, selected_ids: list[str] | None = None,
) -> None:
    """Background worker for /link/start. Mirrors scan_link's body: run the
    comprehensive scan with the Source built by the caller, persist the
    investigation under the pre-minted slug, and record terminal status on the
    ScanJob row. A failed scan refunds the full charge — a failed scan must
    never cost a credit."""
    settings = get_settings()
    import time as _time
    t0 = _time.perf_counter()

    def _telemetry(state: str, *, commenters: int = 0) -> dict:
        """Measured investigation cost. api_calls = upstream provider calls
        (single provider per scan = the platform); max_rss_mb is process-wide
        peak (a high-water mark, not strictly per-scan under concurrency)."""
        rss_mb = 0.0
        try:
            import resource
            rss_mb = round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1)
        except Exception:
            pass
        return {
            "platform": platform,
            "outcome": state,
            "api_calls": int(getattr(source, "quota_used", 0) or 0),
            "commenters": int(commenters or 0),
            "runtime_s": round(_time.perf_counter() - t0, 2),
            "max_rss_mb": rss_mb,
        }

    def _finish(state: str, *, tier=None, probability=None, error=None,
                refund: bool = False, commenters: int = 0) -> None:
        telemetry = _telemetry(state, commenters=commenters)
        log.info("scan telemetry job=%s %s", db_id, telemetry)
        transitioned = False
        with get_session() as session:
            # Row-lock + terminal guard: if the reaper (or anyone) already
            # terminalized this job, do NOT overwrite or double-refund. Only the
            # caller that performs the queued/running → terminal transition
            # owns the (single) refund.
            job = session.get(ScanJob, db_id, with_for_update=True)
            if job is None or job.status in ("done", "failed"):
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
                telemetry=telemetry,
            )]
            session.flush()
            transitioned = True
        if transitioned and refund:
            try:
                refund_credits(user_id, cost, reason="scan_failed")
            except Exception:
                log.exception("refund failed for link job %s", db_id)

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

    # Select-then-scan: record which cached candidates were scored (for the UI's 'scanned' flag) and pin
    # this post's investigation so later selections grow the SAME one.
    if candidate_list_id is not None:
        try:
            with get_session() as session:
                cl = session.get(CandidateList, candidate_list_id)
                if cl is not None:
                    cl.investigation_slug = slug
                if selected_ids:
                    for cand in session.execute(
                        select(CommenterCandidate).where(
                            CommenterCandidate.list_id == candidate_list_id,
                            CommenterCandidate.external_id.in_(selected_ids),
                        )
                    ).scalars().all():
                        cand.scanned = True
                session.flush()
        except Exception:
            log.exception("could not mark candidates scanned for list %s", candidate_list_id)

    tier = result.overall_tier.value if hasattr(result.overall_tier, "value") else str(result.overall_tier)
    commenters = result.video.commenter_count if getattr(result, "video", None) else (
        1 if getattr(result, "focus_account", None) else 0
    )
    _finish("done", tier=tier, probability=result.overall_probability, commenters=commenters)
