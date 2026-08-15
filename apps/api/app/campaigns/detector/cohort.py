"""Building the detector's input, from either of the two places it can come from.

Two adapters, one output type. That is the whole anti-divergence design: pass 1 runs inside the
scan where the rich evidence is still in memory, pass 2 runs after the analyst lands where the
70-cut is the customer-visible OMI score, and both hand ``fuse.build_findings`` the identical
``Cohort``. There is exactly one scoring core, so the two passes cannot reach different verdicts
about the same accounts; the later one simply replaces the earlier one's stored result.

THE SCORE SOURCE IS RECORDED, NEVER MIXED. A cohort assembled half from engine probabilities and
half from analyst OMI scores is not a cohort, because the two are different scales measuring
different things. Each run picks one, states which, and the UI prints it.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timezone

from app.campaigns.detector import textsim
from app.campaigns.detector.signals import handle_skeleton
from app.campaigns.detector.types import (
    ActivitySample,
    BatchBackground,
    Cohort,
    CohortAccount,
    ThreadComment,
)

logger = logging.getLogger(__name__)

SOURCE_ANALYST = "analyst"
SOURCE_ENGINE = "engine"

#: The 70 cut, on the 0-100 scale both sources are normalised onto.
SCORE_THRESHOLD = 70.0
#: Below this share of scanned accounts carrying an OMI score, the analyst result is too patchy to
#: define a cohort from and the engine probability is used instead. A cohort assembled from a
#: half-finished batched run would silently omit the accounts whose batch had not landed.
MIN_ANALYST_COVERAGE = 0.60


def _dt(value) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str) and value:
        try:
            out = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return out if out.tzinfo else out.replace(tzinfo=timezone.utc)
    return None


def _f(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------------------------
# Background
# ---------------------------------------------------------------------------------------------
def _background(
    *,
    all_accounts: list[dict],
    thread_comments: list[dict],
    arrivals: list[int] | None = None,
    arrival_total: int = 0,
) -> BatchBackground:
    """The null, drawn from material the 70 filter never touched.

    ``all_accounts`` is EVERY scanned commenter, not just the cohort, and ``thread_comments`` is
    every comment under the post from every author, scanned or not. Narrowing either to the cohort
    would be the exact mistake the whole design is arranged to avoid: a background measured on the
    accounts under test tells you nothing about whether their agreement is surprising.
    """
    bg = BatchBackground()
    bg.scanned_total = len(all_accounts)

    authors_by_text: dict[str, set[str]] = defaultdict(set)
    authors: set[str] = set()
    for c in thread_comments:
        author = str(c.get("author_external_id") or "")
        if author:
            authors.add(author)
        ts = _dt(c.get("created_at"))
        if ts is not None:
            bg.thread_comment_times.append(ts)
        norm = textsim.normalize(c.get("text") or "")
        if norm and author:
            authors_by_text[norm].add(author)
    bg.thread_author_count = len(authors)
    bg.text_author_counts = {k: len(v) for k, v in authors_by_text.items()}

    # Prefer the persisted arrival list. It covers EVERY author under the post, including the ones
    # never selected for scoring, whereas the per-account blocks above only cover scanned accounts.
    # Using the narrower set would under-state the arrival rate and therefore over-state the
    # significance of any co-timing, which is the error that turns a busy comment section into a
    # fake conspiracy.
    if arrivals:
        bg.thread_comment_times = [
            datetime.fromtimestamp(int(t), tz=timezone.utc) for t in sorted(arrivals)
        ]
        bg.thread_arrival_total = max(int(arrival_total or 0), len(arrivals))
        bg.arrivals_complete = True

    for row in all_accounts:
        created = _dt(row.get("account_created_at"))
        if created is not None:
            bg.batch_created_at.append(created)
        sk = handle_skeleton(str(row.get("handle") or ""))
        if sk:
            bg.handle_skeleton_counts[sk] = bg.handle_skeleton_counts.get(sk, 0) + 1

        seen_targets: set[str] = set()
        seen_clients: set[str] = set()
        for sample in row.get("recent_activity") or []:
            if not isinstance(sample, dict):
                continue
            for key in ("parent_id", "reply_to_id", "repost_of_id"):
                tid = sample.get(key)
                if tid:
                    seen_targets.add(str(tid))
            client = sample.get("source_client")
            if client:
                seen_clients.add(str(client).strip())
        for t in seen_targets:
            bg.target_counts[t] = bg.target_counts.get(t, 0) + 1
        for c in seen_clients:
            bg.client_counts[c] = bg.client_counts.get(c, 0) + 1
    return bg


def _activity(row: dict) -> list[ActivitySample]:
    out: list[ActivitySample] = []
    for sample in row.get("recent_activity") or []:
        if not isinstance(sample, dict):
            continue
        out.append(ActivitySample(
            text=str(sample.get("text") or ""),
            created_at=_dt(sample.get("created_at")),
            parent_id=(str(sample["parent_id"]) if sample.get("parent_id") else None),
            source_client=(str(sample["source_client"]).strip()
                           if sample.get("source_client") else None),
            reply_to_id=(str(sample["reply_to_id"]) if sample.get("reply_to_id") else None),
            repost_of_id=(str(sample["repost_of_id"]) if sample.get("repost_of_id") else None),
        ))
    return out


def _thread(row: dict) -> list[ThreadComment]:
    out: list[ThreadComment] = []
    for c in row.get("thread_comments") or []:
        if not isinstance(c, dict):
            continue
        out.append(ThreadComment(
            text=str(c.get("text") or ""),
            created_at=_dt(c.get("created_at")),
            comment_id=(str(c["comment_id"]) if c.get("comment_id") else None),
            parent_comment_id=(str(c["parent_comment_id"])
                               if c.get("parent_comment_id") else None),
        ))
    return out


# ---------------------------------------------------------------------------------------------
# Adapter 1: from the live scan (pass 1)
# ---------------------------------------------------------------------------------------------
def from_scan_rows(
    rows: list[dict],
    thread_comments: list[dict],
    *,
    platform: str,
    threshold: float = SCORE_THRESHOLD,
    arrivals: list[int] | None = None,
    arrival_total: int = 0,
) -> Cohort:
    """Build from serialised ``CommenterScanResult`` dicts using the ENGINE probability.

    Used by pass 1, inside the scan. The engine score is deterministic and available even when the
    analyst is unreachable, which it regularly is: a floored assessment is a documented recurring
    failure and a coordination finding should not disappear with it.
    """
    accounts: list[CohortAccount] = []
    for row in rows:
        prob = _f(row.get("coordination_adjusted_probability"))
        if prob is None:
            prob = _f(row.get("overall_probability"))
        if prob is None:
            continue
        score = prob * 100.0 if prob <= 1.0 else prob
        if score < threshold:
            continue
        accounts.append(CohortAccount(
            external_id=str(row.get("external_id") or ""),
            handle=str(row.get("handle") or ""),
            score=round(score, 2),
            score_source=SOURCE_ENGINE,
            bio=row.get("bio") if "bio" in row else None,
            account_created_at=_dt(row.get("account_created_at")),
            thread_comments=_thread(row),
            activity=_activity(row),
        ))
    accounts = [a for a in accounts if a.external_id]
    accounts.sort(key=lambda a: a.external_id)
    return Cohort(
        accounts=accounts,
        background=_background(
            all_accounts=rows, thread_comments=thread_comments,
            arrivals=arrivals, arrival_total=arrival_total,
        ),
        platform=platform,
        score_source=SOURCE_ENGINE,
        score_threshold=threshold,
    )


# ---------------------------------------------------------------------------------------------
# Adapter 2: from the persisted investigation (pass 2)
# ---------------------------------------------------------------------------------------------
def analyst_scores(payload: dict) -> dict[str, float]:
    """``external_id -> omi_score`` from the persisted assessment, or empty.

    Reads the cache key directly rather than importing the analyst module, so nothing in this
    package depends on the reasoning stack. That is what makes the "no model call" guarantee
    testable at the import level.
    """
    entry = payload.get("analyst_assessment_v1")
    if not isinstance(entry, dict):
        return {}
    assessment = entry.get("assessment")
    if not isinstance(assessment, dict):
        return {}
    out: dict[str, float] = {}
    for row in assessment.get("commenter_assessments") or []:
        if not isinstance(row, dict):
            continue
        ext = row.get("external_id")
        score = _f(row.get("omi_score"))
        if ext and score is not None:
            out[str(ext)] = score
    return out


def from_payload(
    payload: dict,
    *,
    platform: str = "unknown",
    prefer: str = SOURCE_ANALYST,
    threshold: float = SCORE_THRESHOLD,
) -> Cohort:
    """Build from a persisted ``payload_json``.

    ``prefer="analyst"`` uses the customer-visible OMI score when the assessment is present and
    covers enough of the batch, and falls back to the engine probability otherwise. The fallback is
    not a nicety: without it, every investigation whose analyst floored would have no coordination
    result at all, and those are disproportionately the ones an operator is looking at.
    """
    video = payload.get("video") if isinstance(payload.get("video"), dict) else {}
    rows = list((video or {}).get("commenters") or [])
    thread = _thread_comments_from_payload(payload)
    arrivals = [int(t) for t in ((video or {}).get("thread_arrivals") or []) if isinstance(t, (int, float))]
    arrival_total = int((video or {}).get("thread_arrival_total") or 0)

    scores = analyst_scores(payload) if prefer == SOURCE_ANALYST else {}
    coverage = (len(scores) / len(rows)) if rows else 0.0
    use_analyst = bool(scores) and coverage >= MIN_ANALYST_COVERAGE

    if not use_analyst:
        if prefer == SOURCE_ANALYST and scores:
            logger.info(
                "campaign detector: analyst scores covered %.0f%% of %d accounts, "
                "falling back to engine probabilities", coverage * 100, len(rows),
            )
        return from_scan_rows(
            rows, thread, platform=platform, threshold=threshold,
            arrivals=arrivals, arrival_total=arrival_total,
        )

    accounts: list[CohortAccount] = []
    for row in rows:
        ext = str(row.get("external_id") or "")
        if not ext:
            continue
        score = scores.get(ext)
        if score is None or score < threshold:
            continue
        accounts.append(CohortAccount(
            external_id=ext,
            handle=str(row.get("handle") or ""),
            score=round(score, 2),
            score_source=SOURCE_ANALYST,
            bio=row.get("bio") if "bio" in row else None,
            account_created_at=_dt(row.get("account_created_at")),
            thread_comments=_thread(row),
            activity=_activity(row),
        ))
    accounts.sort(key=lambda a: a.external_id)
    return Cohort(
        accounts=accounts,
        background=_background(
            all_accounts=rows, thread_comments=thread,
            arrivals=arrivals, arrival_total=arrival_total,
        ),
        platform=platform,
        score_source=SOURCE_ANALYST,
        score_threshold=threshold,
    )


def _thread_comments_from_payload(payload: dict) -> list[dict]:
    """Reassemble the thread from the per-account blocks the scan persisted.

    The raw comment stream is not stored as a list of its own, so this rebuilds it from each
    account's ``thread_comments``. That covers every scanned account. It does NOT cover authors who
    were never selected for scoring, so the arrival-rate null here is measured over a subset of the
    real thread. Under-counting the rate makes `burst_lockstep` more permissive, so pass 1 (which
    sees the true full stream in memory) is the authoritative timing measurement and pass 2 inherits
    its edges rather than recomputing them. See `run.refine`.
    """
    video = payload.get("video")
    rows = list((video or {}).get("commenters") or []) if isinstance(video, dict) else []
    out: list[dict] = []
    for row in rows:
        ext = row.get("external_id")
        for c in row.get("thread_comments") or []:
            if isinstance(c, dict):
                out.append({**c, "author_external_id": ext})
    return out


def backfill_thread_comments(session, investigation, payload: dict) -> int:
    """Recover thread comments for an investigation persisted before they were carried.

    Reads the compile-step cache (``CommenterCandidate.comments_json``), which holds the raw
    comments with their timestamps for both platforms. Best-effort and read-only: that row is
    per-user, cascade-deleted with its candidate list, and rebuilt on refresh, so it is a
    convenience for existing data rather than something a finding may depend on. Returns how many
    accounts were filled.
    """
    try:
        import json

        from sqlalchemy import select

        from app.storage.models import CandidateList, CommenterCandidate

        video = payload.get("video")
        rows = list((video or {}).get("commenters") or []) if isinstance(video, dict) else []
        if not rows or any(r.get("thread_comments") for r in rows):
            return 0

        target = getattr(investigation, "target_id", None)
        if not target:
            return 0
        lists = session.execute(
            select(CandidateList.id).where(CandidateList.content_id == str(target))
        ).scalars().all()
        if not lists:
            return 0
        cands = session.execute(
            select(CommenterCandidate.external_id, CommenterCandidate.comments_json)
            .where(CommenterCandidate.list_id.in_(lists))
        ).all()

        by_id: dict[str, list[dict]] = {}
        for ext, blob in cands:
            if not blob:
                continue
            try:
                parsed = json.loads(blob)
            except (TypeError, ValueError):
                continue
            if isinstance(parsed, list):
                by_id[str(ext)] = [c for c in parsed if isinstance(c, dict)]

        filled = 0
        for row in rows:
            got = by_id.get(str(row.get("external_id") or ""))
            if got:
                row["thread_comments"] = [
                    {"text": c.get("text") or "", "created_at": c.get("created_at"),
                     "comment_id": c.get("comment_id"),
                     "parent_comment_id": c.get("parent_comment_id")}
                    for c in got
                ]
                filled += 1
        return filled
    except Exception:  # noqa: BLE001 - a backfill that fails just means less evidence
        logger.warning("campaign detector: thread-comment backfill failed", exc_info=True)
        return 0
