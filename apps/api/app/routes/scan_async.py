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
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import func, select

if TYPE_CHECKING:  # annotations only; the real import stays lazy inside the factories
    from app.core.rate_limit import SlidingWindowLimiter

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
from app.schemas import ComprehensiveScanRequest, ComprehensiveScanResult, Tier
from app.storage.db import get_session
from app.storage.models import CandidateList, CommenterCandidate, DemoScanLog, ScanJob

log = logging.getLogger("omi.scan")

router = APIRouter(prefix="/v1/scan", tags=["scan"])


def _compile_limiter() -> SlidingWindowLimiter:
    """Per-user ceiling on the FREE compile step.

    Compile requires auth but charges no credits, and it calls the real X / YouTube API (X bills per
    post read). Credits therefore cannot guard it — there are none to spend — so without this an
    account looping "load all" over large posts spends our upstream budget for free. Built once,
    lazily, so the limiter is registered for the test-suite reset and reads live settings.
    """
    global _COMPILE_LIMITER
    if _COMPILE_LIMITER is None:
        from app.core.rate_limit import SlidingWindowLimiter

        s = get_settings()
        _COMPILE_LIMITER = SlidingWindowLimiter(
            max_hits=int(s.rate_limit_compile_max),
            per_seconds=float(s.rate_limit_compile_window_seconds),
        )
    return _COMPILE_LIMITER


def _scan_limiter() -> SlidingWindowLimiter:
    """Per-user burst ceiling on starting paid scans. Credits are the real guard; this bounds a
    stuck client retrying, or a script racing many scans at once and pinning the background pool."""
    global _SCAN_LIMITER
    if _SCAN_LIMITER is None:
        from app.core.rate_limit import SlidingWindowLimiter

        s = get_settings()
        _SCAN_LIMITER = SlidingWindowLimiter(
            max_hits=int(s.rate_limit_scan_max),
            per_seconds=float(s.rate_limit_scan_window_seconds),
        )
    return _SCAN_LIMITER


_COMPILE_LIMITER = None
_SCAN_LIMITER = None


def reset_scan_limiters_for_tests() -> None:
    """Drop the memoised limiters so a test can change the settings that size them."""
    global _COMPILE_LIMITER, _SCAN_LIMITER
    _COMPILE_LIMITER = None
    _SCAN_LIMITER = None


def _json_default(o):
    """JSON encoder fallback: the source's comment dicts carry ``created_at`` as a real ``datetime``
    (``_iso_or_none`` -> ``isoparse``), which ``json.dumps`` cannot serialize. Emit ISO-8601 so the
    cached comment round-trips back into a ``Post`` at score time."""
    if isinstance(o, datetime):
        return o.isoformat()
    return str(o)


def _dumps(obj) -> str:
    """datetime-safe ``json.dumps`` for caching commenter meta + comments."""
    return json.dumps(obj, default=_json_default)


def _parse_iso(v):
    """Inverse of ``_json_default`` for timestamps: ISO string -> datetime. The live sources hand the
    orchestrator real ``datetime`` comment timestamps (the coordination detectors call ``.timestamp()``
    on them), so a comment rebuilt from the JSON cache MUST be re-parsed to a datetime or it crashes
    the scan. Returns None for anything unparseable so the caller can drop it."""
    if isinstance(v, datetime):
        return v
    if isinstance(v, str) and v:
        try:
            return datetime.fromisoformat(v)
        except ValueError:
            return None
    return None


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


def _fetch_and_cache_commenters(
    session, cl: CandidateList, existing: list, *, fetch_n: int, settings: Settings, source_factory
) -> int:
    """Pull up to ``fetch_n`` NEW commenters for ``cl`` from the platform source and persist them as
    ``CommenterCandidate`` rows (exemplar comment + cached meta/comments for the later score step).
    Returns how many new commenters were added. The source is built lazily via ``source_factory`` — only
    when there is actually work to do — so a fetch-nothing call never touches (or 503s on) the platform.

    Shared verbatim by the signed-in compile step and the free demo compile so both produce
    byte-identical candidate rows and a single fetch/caching code path."""
    if fetch_n <= 0 or cl.exhausted:
        return 0
    source = source_factory()
    # Best-effort: capture the post's real title once, so a saved investigation reads "Xandr's launch
    # video" not "Scan of https://…". Never blocks the list.
    if not cl.content_title:
        try:
            title = source.fetch_content_title(cl.content_id)
            if title:
                cl.content_title = title.strip()[:500]
        except Exception:  # noqa: BLE001 — titling is cosmetic, never fatal
            pass
    # Sample enough comments to actually surface that many commenters (never fewer than the configured
    # floor), since a comment section has more comments than unique authors.
    comment_budget = max(settings.candidate_min_comments, fetch_n * 3)
    try:
        commenters_meta, all_comments, next_cursor = source.fetch_content_engagers(
            cl.content_id, max_commenters=fetch_n, max_comments=comment_budget,
            start_page_token=cl.next_cursor,
        )
    except (TwitterClientError, YouTubeClientError) as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Could not fetch the commenters: {exc}",
        ) from exc
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 — never surface a raw 500 to the compile step
        log.warning(
            "list_commenters fetch failed platform=%s content_id=%s: %s",
            cl.platform, cl.content_id, exc,
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=(
                "Could not read this post's commenters. The source may be rate-limiting, or "
                "the post may be private or unavailable — please try again in a moment."
            ),
        ) from exc

    comments_by_author: dict[str, list[dict]] = {}
    for c in all_comments:
        comments_by_author.setdefault(str(c.get("author_external_id") or ""), []).append(c)

    seen = {row.external_id for row in existing}
    next_seq = (max((row.seq for row in existing), default=-1) + 1)
    fetched_now = 0
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
            meta_json=_dumps(meta), comments_json=_dumps(cmts),
        ))
        seen.add(ext)
        next_seq += 1
        fetched_now += 1
    cl.next_cursor = next_cursor
    cl.exhausted = not next_cursor
    session.flush()
    return fetched_now


def _candidate_list_for(session, platform: str, content_id: str, uid: int | None):
    """THE candidate list for one (platform, content, owner), tolerating duplicates. None if absent.

    Deliberately NOT ``.scalar_one_or_none()``, which is what this replaced at every call site.
    ``CandidateList`` carries ``UniqueConstraint("user_id", "platform", "content_id")``, which LOOKS
    like it makes a second row impossible. Two separate reasons it can fail to:

    * **``user_id IS NULL`` rows.** SQL treats NULLs as DISTINCT (in PostgreSQL, which is production,
      and in SQLite), so the constraint is silently inert for them. The anonymous demo bucket is
      entirely NULL-owned by design, and local mode (``OMI_REQUIRE_AUTH=false``, the id=0 user) maps
      its owner to NULL too.
    * **Databases predating the constraint.** ``create_all`` leaves existing tables alone and the boot
      upgrade pass only backfills columns and ``table.indexes``; a ``UniqueConstraint`` lives in
      ``table.constraints``, so it is never added to a ``candidate_lists`` that already existed. On
      such a database duplicates are possible for REAL user ids as well.

    Either way two concurrent compiles of one post both see "no list yet" and both insert, and
    ``scalar_one_or_none()`` then raised ``MultipleResultsFound`` straight out of the route as a raw
    HTTP 500 — permanently, since the rows persist, and for the anonymous bucket globally, since every
    visitor shares it. That shipped as a 500 on the front page's only free sample.

    When duplicates exist, prefer the row that already holds cached commenters: those were paid for
    with a real upstream fetch, and settling on an empty duplicate would silently re-fetch on every
    compile. Ties break on the lowest id so concurrent callers converge on the same row.
    """
    owner = CandidateList.user_id.is_(None) if uid is None else CandidateList.user_id == uid
    rows = list(session.execute(
        select(CandidateList).where(
            CandidateList.platform == platform,
            CandidateList.content_id == content_id,
            owner,
        ).order_by(CandidateList.id)
    ).scalars().all())
    if len(rows) <= 1:
        return rows[0] if rows else None

    counts = dict(session.execute(
        select(CommenterCandidate.list_id, func.count(CommenterCandidate.id))
        .where(CommenterCandidate.list_id.in_([r.id for r in rows]))
        .group_by(CommenterCandidate.list_id)
    ).all())
    keep = max(rows, key=lambda r: (counts.get(r.id, 0), -r.id))
    log.warning(
        "duplicate candidate lists: %d for %s/%s owner=%s (ids=%s); using id=%s with %d cached "
        "commenters", len(rows), platform, content_id, uid if uid is not None else "anonymous",
        [r.id for r in rows], keep.id, counts.get(keep.id, 0),
    )

    # Collapse the leftovers so the post stops being ambiguous, but only ones holding NO commenters —
    # deleting a populated list would cascade its candidates away and throw out a paid fetch. Strictly
    # best-effort: recovery already succeeded above, and tidying must never fail the request.
    try:
        for row in rows:
            if row.id != keep.id and counts.get(row.id, 0) == 0:
                session.delete(row)
        session.flush()
    except Exception:  # noqa: BLE001 — cleanup is a bonus, never the caller's problem
        log.warning("could not collapse duplicate candidate lists for %s/%s", platform, content_id,
                    exc_info=True)
    return keep


def _reconstruct_injected(rows: list) -> tuple[list[dict], list[dict], list[str]]:
    """Rebuild the injected-scan inputs from cached ``CommenterCandidate`` rows: the selected commenters'
    raw meta and their comments (each comment's ISO timestamp re-parsed to a real ``datetime`` — the
    evidence compiler + coordination detectors REQUIRE datetimes, so a comment whose timestamp can't be
    parsed is dropped rather than crashing the scan). Returns ``(injected_commenters, injected_comments,
    selected_ids)``. Shared by the paid score step and the free demo score."""
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
                parsed = json.loads(r.comments_json)
            except (TypeError, ValueError):
                parsed = []
            for c in parsed:
                if not isinstance(c, dict):
                    continue
                dt = _parse_iso(c.get("created_at"))
                if dt is None:
                    continue
                injected_comments.append({**c, "created_at": dt})
    return injected_commenters, injected_comments, selected_ids


@router.post("/link/commenters", response_model=CommenterListOut)
def list_commenters(
    payload: dict,
    request: Request,
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

    # Per-user ceiling, applied AFTER validation (a malformed URL shouldn't spend budget) and BEFORE
    # any upstream fetch. Admins are exempt, mirroring how they skip credit consumption.
    if not current.is_admin:
        from app.core.rate_limit import enforce, user_key

        enforce(_compile_limiter(), user_key(uid, request), what="commenter-list")

    # The compile list mirrors the whole comment section (browse + pick), so it uses the generous
    # candidate-pool caps, NOT the smaller per-scan analysis cap.
    pool_max = settings.candidate_pool_max
    page_max = settings.candidate_page_max
    first_page = settings.candidate_first_page

    with get_session() as session:
        # Duplicate-tolerant on purpose; see _candidate_list_for.
        cl = _candidate_list_for(session, platform, content_id, uid)
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

        # How many NEW commenters to pull on THIS call: a big first page when the list is empty,
        # otherwise only when the client asks ("add more"). Each call is bounded (page_max) so it stays
        # fast; the list grows across calls up to the whole-post pool cap. "Load all" just repeats this.
        room = max(0, pool_max - len(existing))
        raw_fetch = payload.get("fetch")
        if raw_fetch is None:
            fetch_n = 0 if existing else first_page
        else:
            try:
                fetch_n = max(0, int(raw_fetch))
            except (TypeError, ValueError):
                fetch_n = first_page
        fetch_n = min(fetch_n, page_max, room)

        # _source_for_platform raises HTTPException(503) when a platform key is missing — let that
        # through unchanged so the UI shows the real "key not configured" message.
        fetched_now = _fetch_and_cache_commenters(
            session, cl, existing, fetch_n=fetch_n, settings=settings,
            source_factory=lambda: _source_for_platform(platform, settings),
        )

        # Always record this post in the content DB — even if the user never scans it. Every X post /
        # YouTube video that the system loads is persisted, not just the selected ones. Idempotent +
        # best-effort: a failure here never affects the free commenter list.
        try:
            from app.content.service import ContentIntelligenceService
            ContentIntelligenceService(session).get_or_create_entity(
                platform=platform, content_id=content_id,
                kind=("video" if platform == "youtube" else "post"),
                title=cl.content_title, canonical_url=cl.content_url or url,
            )
        except Exception:  # noqa: BLE001 — content bookkeeping must never break the list
            pass

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
        # More to pull only if the source has more AND we're under the whole-post pool cap.
        has_more = (not cl.exhausted) and len(commenters) < pool_max
        return CommenterListOut(
            platform=platform, content_id=content_id, url=cl.content_url or url,
            commenters=commenters, total=len(commenters),
            has_more=has_more, fetched_now=fetched_now,
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


def scan_job_budget_seconds(max_commenters: int | None, settings: Settings) -> int:
    """How long a scan job of this size is allowed to run before the watchdog calls it dead.

    Scaled by the account count, because that is what the work is: every selected account costs a
    profile fetch, a history fetch, and a detection pass. A flat budget sized for a small scan
    guarantees that big ones are killed while still healthy — and a false reap is expensive in a way
    a late reap is not. It refunds and tells the user their scan failed AFTER the upstream calls have
    been paid for, and (because the worker persists the investigation before it reports success) it can
    do that for a scan whose results are already saved and sitting in their history.
    """
    n = max(1, int(max_commenters or 1))
    scaled = float(settings.scan_job_timeout_per_account_seconds) * n
    return int(min(
        float(settings.scan_job_timeout_max_seconds),
        max(float(settings.scan_job_timeout_seconds), scaled),
    ))


def _as_utc(dt: datetime) -> datetime:
    """Rows written through SQLite come back naive; the budget arithmetic below needs an aware value."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def reap_stale_scan_jobs(
    settings: Settings, *, user_id: int | None = None, job_id: str | None = None
) -> int:
    """Mark scan jobs stuck in queued/running past THEIR OWN budget as failed + refund.

    The safety net for the cases the worker can't self-report: a worker killed mid-scan (OOM /
    redeploy) that never wrote a terminal status. Without this a job polls forever and the credit is
    stranded. Each job is judged against a budget scaled to its account count
    (``scan_job_budget_seconds``) rather than one flat number, so a 100-account scan isn't declared
    dead at the five-minute mark a 5-account scan is sized for. Idempotent and transition-guarded (row
    lock + status check) so the credit is refunded exactly once, even racing a late-finishing worker.
    Returns the count reaped. Scope to a user/job to keep the per-request sweep cheap.
    """
    now = datetime.now(timezone.utc)
    # Cheap pre-filter in SQL at the smallest possible budget; the per-job budget is applied below.
    floor_cutoff = now - timedelta(seconds=settings.scan_job_timeout_seconds)
    with get_session() as session:
        q = select(ScanJob).where(
            ScanJob.status.in_(["queued", "running"]),
            ScanJob.created_at < floor_cutoff,
        )
        if user_id is not None:
            q = q.where(ScanJob.user_id == user_id)
        if job_id is not None:
            q = q.where(ScanJob.job_id == job_id)
        candidate_ids = [
            j.id for j in session.execute(q).scalars()
            if (now - _as_utc(j.created_at)).total_seconds()
            >= scan_job_budget_seconds(j.max_commenters, settings)
        ]

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
        log.warning(
            "reaped %d stale scan job(s) past their size-scaled budget (floor %ds, %.1fs/account, "
            "ceiling %ds)", reaped, settings.scan_job_timeout_seconds,
            settings.scan_job_timeout_per_account_seconds, settings.scan_job_timeout_max_seconds,
        )
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
    reap_stale_scan_jobs(settings, user_id=current.id)

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
    reap_stale_scan_jobs(settings, user_id=current.id, job_id=job_id)
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
    request: Request,
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

    # Burst ceiling before any credit is charged or worker claimed. Credits are the real cost guard;
    # this stops a stuck client's retry loop or a script racing scans from pinning the pool.
    if not current.is_admin:
        from app.core.rate_limit import enforce, user_key

        enforce(_scan_limiter(), user_key(uid, request), what="scan")

    # Reconstruct the scan input for ONLY the selected commenters from the cache (no re-fetch of the list).
    with get_session() as session:
        cl = _candidate_list_for(session, platform, content_id, uid)
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
        injected_commenters, injected_comments, selected_ids = _reconstruct_injected(rows)
        cl_id = cl.id
        existing_slug = cl.investigation_slug
        content_url = cl.content_url or url
        content_title = cl.content_title

    if not selected_ids:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No scannable selection.")

    reap_stale_scan_jobs(settings, user_id=current.id)

    # Build creq (with the injected selection) + Source BEFORE charging, so a mis-config never bills.
    creq = ComprehensiveScanRequest(
        video_url_or_id=content_id, account_url_or_handle=None, comments_text=None,
        # max_commenters is unused on the injected path (the selection replaces the fetch); keep it in
        # the schema's [5, 500] range. The real charge is computed below from the selection count.
        max_commenters=min(500, max(5, len(selected_ids))), force_refresh=False,
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
            candidate_list_id=cl_id, selected_ids=selected_ids, content_title=content_title,
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
    content_title: str | None = None,
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
                if job is not None and state == "done":
                    # The watchdog called this job dead while it was still working, and it has now
                    # finished successfully. The investigation IS saved (persistence happens before
                    # this call), so the user has their results and their refund — but they were told
                    # the scan failed. That means the budget is too tight for scans this size: raise
                    # scan_job_timeout_per_account_seconds.
                    log.error(
                        "scan job %s finished OK after being reaped — investigation %s is saved but "
                        "was reported as failed. The size-scaled budget is too tight for %s accounts.",
                        db_id, slug, creq.max_commenters,
                    )
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
        url=url, payload=result_payload, label_override=content_title,
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


# --------------------------------------------------------------------------- #
# Free anonymous demo — the SAME select-then-scan flow the signed-in workspace
# uses (compile the repliers → pick who to analyze → run the REAL engine +
# OpenRouter analyst), but X-only, capped at 25 repliers, and limited to TWO
# full scans per IP address, ever. No auth, no credits.
# --------------------------------------------------------------------------- #
DEMO_FREE_SCANS_PER_IP = 2

_DEMO_LIMIT_MSG = (
    "You've used both of your free scans. Create a free account to keep scanning, "
    "pick more accounts, save your results, and unlock the full platform."
)


def _demo_ip_hash(request: Request) -> str:
    """Hashed client IP — the free-scan budget key. Reuses the scan module's helpers so the demo and any
    other IP bookkeeping hash identically."""
    return scan_mod._hash_ip(scan_mod._client_ip(request))


# How long an in-flight reservation counts against the budget. Long enough to cover the slowest real
# scan (fetch every account's history + one model call), short enough that a row orphaned by a crash
# or a redeploy frees itself instead of locking that visitor out for good.
DEMO_RESERVATION_TTL = timedelta(minutes=20)


def _demo_scans_used(session, ip_hash: str) -> int:
    """How much of this IP's free budget is spoken for: scans that SUCCEEDED, plus scans that are
    running right now (un-expired reservations).

    Counting in-flight reservations is what makes the limit real. Checking only completed scans left a
    wide time-of-check/time-of-use window — a demo scan takes minutes, so firing N requests at once
    meant all N passed the check before any of them had written a row, and one IP got N free scans for
    the price of the limit's ignorance. Reservations are written before the work starts, so a
    concurrent request sees them."""
    cutoff = datetime.now(timezone.utc) - DEMO_RESERVATION_TTL
    rows = session.execute(
        select(DemoScanLog.id).where(
            DemoScanLog.ip_hash == ip_hash,
            (DemoScanLog.success == 1) | (DemoScanLog.created_at >= cutoff),
        ).limit(DEMO_FREE_SCANS_PER_IP)
    ).all()
    return len(rows)


def _reserve_demo_scan(ip_hash: str, content_id: str, user_agent: str) -> int | None:
    """Claim one of the IP's free scans BEFORE the work starts. Returns the reservation's row id, which
    the caller must either confirm (``_confirm_demo_scan``) or release (``_release_demo_scan``)."""
    try:
        with get_session() as session:
            row = DemoScanLog(
                ip_hash=ip_hash, video_id=str(content_id)[:60],
                user_agent_snippet=(user_agent or "")[:200],
                success=0,
            )
            session.add(row)
            session.flush()
            row_id = row.id
            session.commit()
            return row_id
    except Exception:  # noqa: BLE001 — never fail a scan because bookkeeping failed
        log.exception("demo: could not reserve a free scan")
        return None


def _confirm_demo_scan(row_id: int | None) -> None:
    """The scan succeeded — the reservation becomes a permanently spent free scan."""
    if row_id is None:
        return
    try:
        with get_session() as session:
            row = session.get(DemoScanLog, row_id)
            if row is not None:
                row.success = 1
            session.commit()
    except Exception:  # noqa: BLE001
        log.exception("demo: could not confirm free scan %s", row_id)


def _release_demo_scan(row_id: int | None) -> None:
    """The scan failed — hand the free scan back. A visitor must never lose one to our error."""
    if row_id is None:
        return
    try:
        with get_session() as session:
            row = session.get(DemoScanLog, row_id)
            if row is not None:
                session.delete(row)
            session.commit()
    except Exception:  # noqa: BLE001
        log.exception("demo: could not release free scan %s", row_id)


def _demo_classify_x_post(url: str) -> str:
    """Validate + classify a free-scan URL. The free scan is X-only, on a specific post. Returns the
    tweet id, or raises the appropriate 400."""
    if not url:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="url is required.")
    classification = classify_link(url)
    if classification.get("platform") != "x" or classification.get("kind") != "tweet":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The free scan works on X (Twitter) posts. Paste a link like "
                   "https://x.com/<user>/status/<id>.",
        )
    tweet_id = classification.get("tweet_id")
    if not tweet_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Couldn't read that X post link. Paste the full URL to a specific post "
                   "(it contains /status/).",
        )
    return tweet_id


@router.post("/demo/commenters", response_model=CommenterListOut)
def scan_demo_commenters(
    payload: dict,
    request: Request,
    settings: Settings = Depends(get_settings),
) -> CommenterListOut:
    """FREE anonymous COMPILE step — the same first move as the signed-in workspace, X-only and capped at
    25 repliers. Lists (and caches) a post's repliers so the visitor can pick who to analyze. No auth, no
    credits. An IP that has already spent both free scans is turned away here too."""
    url = (payload.get("url") or "").strip() if isinstance(payload, dict) else ""
    content_id = _demo_classify_x_post(url)
    ip_hash = _demo_ip_hash(request)

    with get_session() as session:
        if _demo_scans_used(session, ip_hash) >= DEMO_FREE_SCANS_PER_IP:
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=_DEMO_LIMIT_MSG)

        # Anonymous candidate lists live in the shared user_id=None bucket, keyed by the post — two
        # visitors scanning the same post reuse one cached replier list (one X fetch, not two).
        # Duplicate-tolerant on purpose; see _candidate_list_for.
        cl = _candidate_list_for(session, "x", content_id, None)
        if cl is None:
            cl = CandidateList(user_id=None, platform="x", content_id=content_id, content_url=url)
            session.add(cl)
            session.flush()

        existing = list(session.execute(
            select(CommenterCandidate).where(CommenterCandidate.list_id == cl.id)
            .order_by(CommenterCandidate.seq)
        ).scalars().all())

        # A single bounded page: fetch the first (up to) 25 repliers when the list is empty; re-compiling
        # the same post returns the cached rows with no new X call.
        fetch_n = 0 if existing else scan_mod.DEMO_MAX_COMMENTERS
        _fetch_and_cache_commenters(
            session, cl, existing, fetch_n=fetch_n, settings=settings,
            source_factory=lambda: _source_for_platform("x", settings),
        )

        rows = list(session.execute(
            select(CommenterCandidate).where(CommenterCandidate.list_id == cl.id)
            .order_by(CommenterCandidate.seq)
        ).scalars().all())[: scan_mod.DEMO_MAX_COMMENTERS]
        commenters = [
            CommenterCandidateOut(
                external_id=r.external_id, handle=r.handle, comment=r.comment_text,
                comment_count=r.comment_count, avatar_url=r.avatar_url,
                # The demo never marks candidates scanned (the shared anonymous bucket must not leak one
                # visitor's picks to the next), so every replier stays selectable.
                scanned=False,
            )
            for r in rows
        ]
        return CommenterListOut(
            platform="x", content_id=content_id, url=cl.content_url or url,
            commenters=commenters, total=len(commenters),
            has_more=False, fetched_now=len(commenters),
        )


def _demo_assessment(result, settings: Settings) -> dict | None:
    """Run the REAL Omi Analyst over a finished free scan and return its assessment.

    Same runtime, same prompt, same governance as a signed-in investigation — the free scan is a
    genuine read, not a canned one. It runs INLINE here (a signed-in scan generates in the background
    and the client polls ``/v1/investigations/{slug}/analyst``, but an anonymous scan has no saved
    investigation to poll), which is affordable precisely because the free tier is capped at 25
    accounts: exactly ONE model call, the same unit the batching is sized around.

    Best-effort by contract: ``assess_payload`` never raises and returns None when the analyst is
    disabled, unconfigured, or the call fails. The visitor still gets the full deterministic result —
    every per-account score on screen is the engine's, and never the model's, either way.
    """
    from app.reasoning import analyst as _analyst

    if not _analyst.analyst_enabled(settings):
        return None
    try:
        payload = scan_mod._serialize_result(result)
    except Exception:  # noqa: BLE001 — the assessment is a bonus; never break a good scan over it
        log.exception("demo: could not serialise the payload for the analyst")
        return None
    # A visitor's browser is holding this connection, so cap the model call well below the budget a
    # background generation gets (see demo_analyst_timeout_seconds).
    demo_settings = settings.model_copy(update={
        "analyst_timeout_seconds": float(settings.demo_analyst_timeout_seconds),
    })
    try:
        assessment = _analyst.assess_payload(
            payload, ref="demo", platform="x", settings=demo_settings,
        )
    except Exception:  # noqa: BLE001 — documented never to raise; belt-and-braces, since by this
        # point the scan has SUCCEEDED and already spent the visitor's free scan.
        log.exception("demo: analyst call raised")
        return None
    if assessment is None:
        log.info("demo: analyst returned no assessment (disabled, unconfigured, or call failed)")
    return assessment


@router.post("/demo/score", response_model=ComprehensiveScanResult)
def scan_demo_score(
    payload: dict,
    request: Request,
    settings: Settings = Depends(get_settings),
) -> ComprehensiveScanResult:
    """FREE anonymous ANALYZE step — runs the REAL engine (histories + detection + the OpenRouter analyst)
    on the visitor's SELECTED repliers, exactly like the signed-in scan, but synchronously and capped at
    25. Consumes ONE of the IP's two free scans on success; a failed attempt does not."""
    url = (payload.get("url") or "").strip() if isinstance(payload, dict) else ""
    content_id = _demo_classify_x_post(url)

    raw_sel = payload.get("selected") or payload.get("external_ids") or []
    selected = [str(s).strip() for s in raw_sel if str(s).strip()] if isinstance(raw_sel, list) else []
    if not selected:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Select at least one replier to analyze.",
        )
    selected = selected[: scan_mod.DEMO_MAX_COMMENTERS]

    ip_hash = _demo_ip_hash(request)
    with get_session() as session:
        if _demo_scans_used(session, ip_hash) >= DEMO_FREE_SCANS_PER_IP:
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=_DEMO_LIMIT_MSG)

        cl = _candidate_list_for(session, "x", content_id, None)
        if cl is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Compile this post's repliers first, then pick who to analyze.",
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
                detail="None of the selected repliers are in this post's list.",
            )
        injected_commenters, injected_comments, selected_ids = _reconstruct_injected(rows)

    if not selected_ids:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No scannable selection.")

    creq = ComprehensiveScanRequest(
        video_url_or_id=content_id, account_url_or_handle=None, comments_text=None,
        max_commenters=min(500, max(5, len(selected_ids))), force_refresh=False,
        injected_commenters=injected_commenters, injected_comments=injected_comments,
    )
    source = _source_for_platform("x", settings)
    # Synthetic anonymous user just for the call signature — id=0 skips credit logic + persistence.
    anon = CurrentUser(
        id=0, email="demo@omi.local", credits_remaining=999,
        subscription_status="demo", subscription_renews_at=None, is_admin=False,
    )

    # Claim the free scan BEFORE the (minutes-long) work, so a burst of concurrent requests from one
    # IP can't all pass the budget check while none of them has written a row yet.
    reservation = _reserve_demo_scan(ip_hash, content_id, request.headers.get("user-agent") or "")

    succeeded = False
    try:
        result = scan_mod._run_comprehensive(
            creq, settings, anon, _charge_credit=False, source=source,
        )
        # A result where EVERY replier errored is a systemic failure, not a read — don't spend a free
        # scan on it, and surface a clean error instead of a uniformly-empty result.
        if scan_mod._all_commenters_failed(result):
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Could not analyze any of the selected repliers. Please try again.",
            )
        # The scan itself is what the free budget pays for. Mark it spent here, BEFORE the analyst:
        # the assessment is a best-effort extra, and a model hiccup must not hand back a scan whose
        # (real, billable) X fetches and detection work already happened.
        succeeded = True
        result.analyst_assessment = _demo_assessment(result, settings)
    except TwitterClientError as e:
        raise scan_mod._handle_twitter_error(
            e, user_id=anon.id, credits_to_refund=0, target_input=content_id,
        )
    except HTTPException:
        raise
    except Exception:
        log.exception("demo score failed for %s", url[:120])
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The scan failed unexpectedly. Please try again.",
        )
    finally:
        # Confirm the reservation on success; hand the free scan back on any failure, so a visitor
        # never loses one to our error.
        if succeeded:
            _confirm_demo_scan(reservation)
        else:
            _release_demo_scan(reservation)

    return result
