"""High-level orchestrator: detection engine + memory + persistence.

Route handlers call into here, not directly into ``app.detection.engine``,
when they want the full self-improving flow:

1. Check the persistent cache — if we've scored this account recently, reuse.
2. Otherwise, compute the memory-derived prior from the fingerprint store.
3. Run the detectors with the prior injected as an extra signal.
4. Persist the new fingerprint + scan row, so the next caller benefits.

Keeping this orchestration *out* of the detection package preserves the
invariant that detectors are pure and independently testable.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


def _coerce_dt(v: Any) -> datetime | None:
    """Comment timestamps must be real datetimes for the coordination detectors (they call
    ``.timestamp()``). Live sources already hand us datetimes; a comment rebuilt from a JSON cache
    arrives as an ISO string. Coerce, and return None for anything we can't place in time."""
    if isinstance(v, datetime):
        return v
    if isinstance(v, str) and v:
        try:
            return datetime.fromisoformat(v)
        except ValueError:
            return None
    return None

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.detection.coordination import (
    detect_age_cohorts,
    detect_co_engagement,
    detect_co_tag,
    detect_fingerprint_clusters,
    detect_style_matches,
    detect_temporal_semantic_cliques,
)
from app.detection.coordination._types import CoordinationCluster
from app.detection.coordination.aggregate import aggregate_coordination
from app.detection.coordination.elevate import (
    apply_coordination,
    build_coordination_signal,
    coordination_membership,
)
from app.detection.coordination.cohort import CohortEntry
from app.detection.coordination.co_engagement import EngagementEntry
from app.detection.coordination.co_tag import CoTagEntry, extract_tags
from app.detection.coordination.fingerprint_cluster import FingerprintEntry
from app.detection.coordination.style_match import StyleEntry
from app.detection.coordination.temporal_semantic import CommentEntry
from app.detection.engine import analyze_account, analyze_comments
from app.detection.scoring import _extract_reasons, _infer_intent, aggregate
from app.memory.fingerprint import extract_fingerprint
from app.memory.prior import compute_memory_signal
from app.schemas import Post, Profile, ScanResult, SignalResult, Tier
from app.storage.repository import AccountRepository
from app.integrations.source import Source


@dataclass
class OrchestratedScan:
    result: ScanResult
    from_cache: bool
    matched_neighbors: int  # how many close memory neighbors backed the scan


@dataclass
class _ScannedNeighbor:
    """Duck-types the subset of ``Account`` that ``compute_memory_signal`` reads
    (external_id, fingerprint_json, last_score, last_confidence), so an account
    just scored in this run can be appended to the in-memory neighbor list with
    no DB round-trip."""
    external_id: str
    fingerprint_json: list[float]
    last_score: float
    last_confidence: float


def scan_account_with_memory(
    session: Session,
    *,
    platform: str,
    external_id: str,
    profile: Profile,
    posts: list[Post],
    force_refresh: bool = False,
    neighbors: list | None = None,
) -> OrchestratedScan:
    """Score an account, consulting and updating the persistent fingerprint store.

    ``neighbors`` is the fingerprint candidate set for the memory detector. When
    a caller passes one (the per-commenter loop in :func:`scan_video_full`), it
    is loaded ONCE per scan and reused — and this function appends the
    just-scored account to it — so a large scan no longer re-runs the full-table
    ``all_with_fingerprints()`` load once per commenter (O(commenters × store)).
    Behaviour is identical to the per-call load: later commenters still see
    earlier ones (appended below), exactly as the old DB re-query did. When
    ``neighbors`` is None (single-account endpoints) it is loaded here as before.
    """
    settings = get_settings()
    repo = AccountRepository(session)

    if not force_refresh:
        cached = repo.cached_scan_within(platform, external_id, settings.scan_cache_ttl_days)
        if cached is not None:
            _, scan_row = cached
            from app.schemas import ScanResult as SR, SignalResult, Tier

            cached_signals = [SignalResult(**s) for s in scan_row.signals_json]
            cached_tier = Tier(scan_row.tier)
            intent_code, intent_label = _infer_intent(cached_signals, cached_tier)
            cached_result = SR(
                overall_probability=scan_row.overall_probability,
                confidence=scan_row.confidence,
                tier=cached_tier,
                signals=cached_signals,
                summary=scan_row.summary,
                subject=profile.handle,
                suspected_intent=intent_code,
                intent_label=intent_label,
                reasons=_extract_reasons(cached_signals, cached_tier),
            )
            return OrchestratedScan(result=cached_result, from_cache=True, matched_neighbors=0)

    # Compute a *preliminary* fingerprint from a no-memory run so we can query
    # neighbors. Then re-run with the memory signal included.
    preliminary = analyze_account(profile, posts)
    preliminary_fp = extract_fingerprint(preliminary)

    if neighbors is None:
        neighbors = repo.all_with_fingerprints()
    memory_signal = compute_memory_signal(
        preliminary_fp,
        neighbors,
        k=settings.memory_k,
        distance_threshold=settings.memory_distance_threshold,
        exclude_external_id=external_id,
    )

    final = analyze_account(profile, posts, extra_signals=[memory_signal])

    # ---- Learned re-scoring (ML track) ----
    # No-op unless OMI_USE_ML_SCORER is on and a model artifact is loaded.
    # Runs before fingerprint extraction so the persisted fingerprint still
    # reflects the detector sub-signals (the ML blend only moves the
    # aggregate probability + tier, not the behavioral sub-signals).
    try:
        from app.ml.scorer import get_scorer
        final = get_scorer().rescore(
            final,
            profile=profile,
            post_count=len(posts),
            texts=[p.text for p in posts[:40] if p.text],
            settings=settings,
        )
    except Exception:  # noqa: BLE001 — ML must never break a scan
        pass

    final_fp = extract_fingerprint(final)
    repo.upsert_with_scan(
        platform=platform,
        external_id=external_id,
        profile=profile,
        scan=final,
        fingerprint=final_fp,
    )
    # Persist co-engagement edges so the next full-scan run can use them.
    parent_ids = [p.parent_id for p in posts if p.parent_id]
    if parent_ids:
        repo.record_engagement_edges(
            platform=platform,
            account_external_id=external_id,
            parent_ids=parent_ids,
        )

    # Keep a shared per-scan neighbor list current so later commenters in the
    # same scan see this account — without re-querying the full table (the old
    # behaviour re-loaded the DB, which now reflects this upsert; we mirror that
    # in memory). Harmless when ``neighbors`` was a one-off local load.
    neighbors.append(_ScannedNeighbor(
        external_id=external_id,
        fingerprint_json=final_fp,
        last_score=final.overall_probability,
        last_confidence=final.confidence,
    ))

    matched = int(memory_signal.sub_signals.get("close_neighbors", 0))

    # ---- Phase 8: tier-change alert for any watchlists pointing here ----
    # Best-effort; failure here must never break the scan.
    try:
        from app.monitoring.service import MonitoringService
        MonitoringService(session).note_observation(
            kind="channel",
            target_id=external_id,
            current_tier=final.tier.value,
            current_probability=final.overall_probability,
            platform=platform,
        )
        # Phase 11: dispatch any pending alerts to email/webhook.
        # Fire-and-forget; the worker waits a beat so the outer txn commits.
        from app.core import background as _bg
        _bg.submit(_deliver_pending_after_commit)
    except Exception:  # noqa: BLE001
        pass

    return OrchestratedScan(result=final, from_cache=False, matched_neighbors=matched)


# ---------------------------------------------------------------------------
# Full video scan — account + comment-thread + coordination, in one pass
# ---------------------------------------------------------------------------


@dataclass
class CommenterRecord:
    """All the per-commenter data the orchestrator collects in one scan."""

    external_id: str
    handle: str
    display_name: str | None
    avatar_url: str | None
    profile: Profile | None
    posts: list[Post]
    scan_result: ScanResult
    fingerprint: list[float] | None
    from_cache: bool
    matched_neighbors: int
    error: str | None = None
    # This account's own comments under the scanned post, bucketed out of the raw comment stream in
    # Phase 3. Kept on the record so it can be persisted: the stream itself only ever exists inside
    # scan_video_full, and without this nothing downstream can tell when an account commented.
    thread_comments: list[dict] = field(default_factory=list)
    # Filled in after coordination detection
    coordination_adjusted_probability: float | None = None
    coordination_evidence: list[str] = field(default_factory=list)


@dataclass
class FullScanOutput:
    video_id: str
    commenter_records: list[CommenterRecord]
    thread_scan: ScanResult
    coordination_clusters: list[CoordinationCluster]
    coordination_score: float
    coordination_tier: Tier
    quota_used: int
    fresh_count: int
    cached_count: int
    # Every comment under the post, from EVERY author, including those never selected for scoring.
    # Carried out of the orchestrator because it is the only complete view of the thread that ever
    # exists, and the coordination detector's arrival-rate null is meaningless without it: measured
    # over scored accounts alone the rate is under-stated, which over-states significance in the one
    # direction that produces false accusations.
    all_thread_comments: list[dict] = field(default_factory=list)


def _cached_commenter_record(
    cache_hit, c: dict, platform: str, *, profile: Profile | None = None, posts: list | None = None,
) -> CommenterRecord:
    """Build a CommenterRecord from a cache hit — the cached SCORE is reused (no re-scoring, no DB
    writes, no fingerprint churn), but ``profile``/``posts`` carry the freshly-fetched evidence when
    the caller pulled it, so a cached account still reaches the analyst with its real history."""
    acc, scan_row = cache_hit
    cached_signals = [SignalResult(**s) for s in scan_row.signals_json]
    cached_tier = Tier(scan_row.tier)
    intent_code, intent_label = _infer_intent(cached_signals, cached_tier)
    cached_result = ScanResult(
        overall_probability=scan_row.overall_probability,
        confidence=scan_row.confidence,
        tier=cached_tier,
        signals=cached_signals,
        summary=scan_row.summary,
        subject=acc.handle,
        suspected_intent=intent_code,
        intent_label=intent_label,
        reasons=_extract_reasons(cached_signals, cached_tier),
    )
    return CommenterRecord(
        external_id=c["channel_id"],
        handle=(profile.handle if profile is not None else (acc.handle or c["handle"])),
        display_name=(profile.display_name if profile is not None else acc.display_name),
        avatar_url=c.get("avatar_url"),
        # Prefer the freshly-fetched profile when we have one: the stored row keeps only the columns
        # the Account table has (no verified flag), and its counts are as old as the last scan.
        profile=profile or Profile(
            platform=platform,
            handle=acc.handle or c["handle"],
            display_name=acc.display_name,
            bio=acc.bio,
            follower_count=acc.follower_count,
            following_count=acc.following_count,
            created_at=acc.account_created_at,
        ),
        # Posts are the account's own words — the evidence the analyst reads to decide whether this
        # is a person or a purchase. An empty list here must mean "this account has posted nothing",
        # never "we had a cached score so we didn't look" (see scan_reuse_cached_scores).
        posts=list(posts or []),
        scan_result=cached_result,
        fingerprint=acc.fingerprint_json,
        from_cache=True,
        matched_neighbors=0,
    )


def _error_commenter_record(c: dict, error_name: str) -> CommenterRecord:
    return CommenterRecord(
        external_id=c["channel_id"], handle=c["handle"], display_name=None,
        avatar_url=c.get("avatar_url"), profile=None, posts=[],
        scan_result=_empty_scan(c["handle"]),
        fingerprint=None, from_cache=False, matched_neighbors=0,
        error=error_name,
    )


def scan_video_full(
    session: Session,
    *,
    platform: str,
    video_id: str,
    commenters_meta: list[dict[str, Any]],
    all_comments_under_video: list[dict[str, Any]],
    fetch_profile,
    fetch_history,
    stats,
    force_refresh: bool = False,
    fetch_concurrency: int = 1,
) -> FullScanOutput:
    """The unified scan: account-level + comment-thread + coordination.

    ``fetch_profile(channel_id) -> Profile | None`` and
    ``fetch_history(channel_id, max_comments) -> list[Post]`` are injected
    so this function stays platform-agnostic and easy to test with fakes.

    ``fetch_concurrency`` (declared by the Source) parallelizes ONLY the
    read-only per-commenter network fetch; scoring + all DB writes stay
    sequential on the single session. >1 only for sources with a thread-safe
    client (Twitter/httpx); YouTube keeps 1 (shared googleapiclient Resource).
    """
    settings = get_settings()
    repo = AccountRepository(session)

    import logging as _logging
    import time as _time
    _log = _logging.getLogger("omi.scan")

    fresh = 0
    cached = 0
    errored = 0
    slots: list[CommenterRecord | None] = [None] * len(commenters_meta)

    # Load the fingerprint candidate set ONCE for the whole batch instead of
    # re-querying the full table per commenter (was O(commenters × store) DB
    # loads — the dominant DB cost on large scans, growing with the moat).
    # scan_account_with_memory appends each freshly-scored account, so later
    # commenters still see earlier ones exactly as the old per-call reload did.
    scan_neighbors = repo.all_with_fingerprints()

    # --- Phase 0: classify cached vs needs-fetch (sequential, cheap DB reads) ---
    to_fetch: list[tuple[int, dict]] = []
    cache_hits: dict[int, Any] = {}
    for idx, c in enumerate(commenters_meta):
        cache_hit = None
        if not force_refresh:
            cache_hit = repo.cached_scan_within(
                platform, c["channel_id"], settings.scan_cache_ttl_days
            )
        if cache_hit is not None:
            cached += 1
            if settings.scan_refetch_evidence_for_cached:
                # Reuse the cached SCORE but still pull this account's profile + history, because
                # that history is the evidence the analyst reads. Skipping the fetch made a cached
                # account arrive at the model with an empty post list, indistinguishable from an
                # account that has never posted — and with a 7-day TTL that is precisely the
                # repeat-offender the memory is supposed to catch.
                cache_hits[idx] = cache_hit
                to_fetch.append((idx, c))
            else:
                slots[idx] = _cached_commenter_record(cache_hit, c, platform)
        else:
            to_fetch.append((idx, c))

    # --- Phase 1: prefetch (profile, posts) — bounded-concurrent, NETWORK ONLY ---
    # Read-only HTTP; touches no DB/session, so it is safe to parallelize for a
    # source whose client is thread-safe (fetch_concurrency>1). Turns the wall
    # cost of ~N sequential round-trips into ~N/concurrency. Scoring (Phase 2)
    # stays sequential on the single session.
    prefetched: dict[int, tuple] = {}

    def _prefetch(item):
        idx, c = item
        cid = c["channel_id"]
        try:
            profile = fetch_profile(cid)
            posts = (fetch_history(cid, settings.scan_max_history_per_commenter)
                     if profile is not None else [])
            return idx, profile, posts, None
        except Exception as e:  # noqa: BLE001 — surfaced as an error record in Phase 2
            return idx, None, [], e

    t0 = _time.perf_counter()
    if to_fetch:
        if fetch_concurrency > 1 and len(to_fetch) > 1:
            from concurrent.futures import ThreadPoolExecutor
            workers = min(fetch_concurrency, len(to_fetch))
            with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="omi-fetch") as ex:
                for idx, profile, posts, err in ex.map(_prefetch, to_fetch):
                    prefetched[idx] = (profile, posts, err)
        else:
            for item in to_fetch:
                idx, profile, posts, err = _prefetch(item)
                prefetched[idx] = (profile, posts, err)
    prefetch_seconds = _time.perf_counter() - t0

    # --- Phase 2: scoring — SEQUENTIAL (DB writes + neighbor append, in order) ---
    t0 = _time.perf_counter()
    for idx, c in to_fetch:
        channel_id = c["channel_id"]
        profile, posts, err = prefetched.get(idx, (None, [], None))
        cache_hit = cache_hits.get(idx)
        if cache_hit is not None:
            # Cached score + whatever evidence the fetch returned. A fetch failure here is not an
            # error record: we still hold a valid cached scan, so degrade to the stored profile
            # rather than throwing away a result the user already has.
            slots[idx] = _cached_commenter_record(
                cache_hit, c, platform,
                profile=(profile if err is None else None),
                posts=(posts if err is None else []),
            )
            continue
        if err is not None:
            slots[idx] = _error_commenter_record(c, type(err).__name__)
            errored += 1
            continue
        if profile is None:
            slots[idx] = _error_commenter_record(c, "channel_not_found")
            errored += 1
            continue
        try:
            orch = scan_account_with_memory(
                session,
                platform=platform,
                external_id=channel_id,
                profile=profile,
                posts=posts,
                force_refresh=force_refresh,
                neighbors=scan_neighbors,
            )
            slots[idx] = CommenterRecord(
                external_id=channel_id,
                handle=profile.handle,
                display_name=profile.display_name,
                avatar_url=c.get("avatar_url"),
                profile=profile,
                posts=posts,
                scan_result=orch.result,
                fingerprint=extract_fingerprint(orch.result),
                from_cache=orch.from_cache,
                matched_neighbors=orch.matched_neighbors,
            )
            if orch.from_cache:
                cached += 1
            else:
                fresh += 1
        except Exception as e:  # noqa: BLE001
            slots[idx] = _error_commenter_record(c, type(e).__name__)
            errored += 1
    score_seconds = _time.perf_counter() - t0

    records: list[CommenterRecord] = [r for r in slots if r is not None]
    _log.info(
        "scan_video_full: platform=%s commenters=%d fresh=%d cached=%d errored=%d "
        "prefetch_s=%.2f score_s=%.2f concurrency=%d",
        platform, len(commenters_meta), fresh, cached, errored,
        prefetch_seconds, score_seconds, fetch_concurrency,
    )

    # --- Phase 2: thread-level scan (treat all comments as one corpus) ---
    # A single malformed comment (missing id/author/timestamp — possible from a cached compile that
    # round-tripped through JSON) must not crash the whole scan; skip it and keep the rest.
    thread_posts: list[Post] = []
    for item in all_comments_under_video:
        try:
            thread_posts.append(Post(
                id=item["comment_id"],
                author_handle=item["author_external_id"],
                text=item.get("text", "") or "",
                created_at=item["created_at"],
                parent_id=video_id,
            ))
        except (KeyError, TypeError, ValueError) as _e:
            _log.warning("skipping malformed comment in thread corpus: %s", _e)
    thread_scan = analyze_comments(thread_posts)

    # --- Phase 2.5/9: narrative ingestion offloaded to a background thread.
    # Embedding can take 5-30s for 150+ comments — way too long to block
    # the HTTP response on. Background queue is bounded so a flood can't
    # OOM us.
    try:
        from app.narrative.service import IngestItem
        narrative_items = [
            IngestItem(
                text=item["text"],
                platform=platform,
                account_external_id=item["author_external_id"],
                parent_id=video_id,
                # The real post time. Without it every temporal statistic over narrative
                # membership measures the scanner instead of the accounts, and one scan looks
                # like a perfect burst. `_coerce_dt` returns None for a timestamp we cannot
                # place, which is the honest value: the column is nullable and the statistics
                # skip it.
                posted_at=_coerce_dt(item.get("created_at")),
            )
            for item in all_comments_under_video
            if item.get("text")
        ]
        if narrative_items:
            from app.core import background
            background.submit(_ingest_narratives_async, narrative_items)
    except Exception:  # noqa: BLE001
        pass

    # --- Phase 3: cross-account coordination detectors -------------------
    clusters: list[CoordinationCluster] = []

    # Temporal-semantic clique on all top-level comments under the video. The detector calls
    # .timestamp() on created_at, so coerce to a real datetime (a comment rebuilt from a JSON cache
    # arrives as an ISO string) and skip any comment we can't place in time.
    ts_entries: list[CommentEntry] = []
    for i in all_comments_under_video:
        created = _coerce_dt(i.get("created_at"))
        if created is None:
            continue
        ts_entries.append(CommentEntry(
            comment_id=i.get("comment_id"),
            author_external_id=i.get("author_external_id"),
            text=i.get("text", "") or "",
            created_at=created,
        ))
    if ts_entries:
        ts_finding = detect_temporal_semantic_cliques(ts_entries)
        clusters.extend(ts_finding.clusters)
    else:
        ts_finding = None

    # Bucket the raw stream onto each commenter's record so the timestamps survive the scan. They
    # were always collected and always discarded here; every downstream reader (the persisted
    # payload, the analyst's evidence, the cohort coordination detector) has been blind to when an
    # account actually commented. Cheap: this is a regroup of a list already in memory.
    _by_author: dict[str, list[dict]] = {}
    for i in all_comments_under_video:
        aid = str(i.get("author_external_id") or "")
        if aid:
            _by_author.setdefault(aid, []).append(i)
    for r in records:
        r.thread_comments = _by_author.get(r.external_id, [])

    # Fingerprint clustering across all commenters who have a fingerprint.
    fp_entries = [
        FingerprintEntry(
            external_id=r.external_id,
            handle=r.handle,
            fingerprint=r.fingerprint,
            individual_probability=r.scan_result.overall_probability,
        )
        for r in records if r.fingerprint
    ]
    fp_finding = detect_fingerprint_clusters(fp_entries)
    clusters.extend(fp_finding.clusters)

    # Account-age cohort.
    cohort_entries = [
        CohortEntry(
            external_id=r.external_id,
            handle=r.handle,
            created_at=r.profile.created_at if r.profile else None,
        )
        for r in records
    ]
    cohort_finding = detect_age_cohorts(cohort_entries)
    clusters.extend(cohort_finding.clusters)

    # Style match — use whatever history we fetched this session (cached
    # commenters won't contribute, which is fine; style match needs fresh text).
    style_entries = [
        StyleEntry(
            external_id=r.external_id,
            handle=r.handle,
            texts=[p.text for p in r.posts if p.text],
        )
        for r in records if r.posts
    ]
    style_finding = detect_style_matches(style_entries)
    clusters.extend(style_finding.clusters)

    # Co-engagement — load engagement sets from the persistent store.
    engagement_sets = repo.load_engagement_sets(
        platform=platform,
        account_external_ids=[r.external_id for r in records],
    )
    co_entries = [
        EngagementEntry(
            external_id=r.external_id,
            handle=r.handle,
            engaged_video_ids=engagement_sets.get(r.external_id, set()) - {video_id},
        )
        for r in records
    ]
    co_finding = detect_co_engagement(co_entries)
    clusters.extend(co_finding.clusters)

    # Co-tag — shared hashtags / amplified handles across commenters' history.
    # The cleanest IO-vs-human separation measured to date (Phase 3, real
    # disclosure data: Iran 75% / Xinjiang 51% / GRU 21% vs legitimate humans
    # 0%). Discriminative in DETECTOR_RELIABILITY / DISCRIMINATIVE_DETECTORS.
    # I/O-free — text comes from the same per-account history style_match uses,
    # so no extra fetch. Returns a silent finding (confidence 0) on YouTube
    # commenters who don't use hashtags/mentions; the aggregator handles that
    # cleanly (a zero-confidence detector contributes no positive evidence and
    # cannot drag the score).
    co_tag_entries = [
        CoTagEntry(
            external_id=r.external_id,
            handle=r.handle,
            tags=extract_tags([p.text for p in r.posts if p.text]),
        )
        for r in records if r.posts
    ]
    co_tag_finding = detect_co_tag(co_tag_entries) if co_tag_entries else None
    if co_tag_finding is not None:
        clusters.extend(co_tag_finding.clusters)

    # --- Phase 4: cross-inject coordination evidence into each commenter --
    # Shared, pure elevation logic (app.detection.coordination.elevate) so the
    # rescue benchmark measures exactly what production runs here.
    by_member = coordination_membership(clusters)
    for r in records:
        cl_for = by_member.get(r.external_id, [])
        if not cl_for:
            continue
        coord_signal = build_coordination_signal(cl_for)
        # Re-aggregate WITHOUT mutating the persisted scan: just compute the
        # what-if for the response. Cache stays clean.
        adjusted = apply_coordination(r.scan_result, cl_for)
        r.coordination_adjusted_probability = adjusted.overall_probability
        r.coordination_evidence = coord_signal.evidence if coord_signal else []

    # --- Phase 4.5: persist coordination edges (cross-scan graph) ----------
    # Promote per-scan clusters into the persistent CoordinationEdge table
    # so /v1/graph/* can serve a cumulative coordination graph.
    # Best-effort — failures here must never break a scan.
    try:
        from app.graph.store import GraphStore
        gstore = GraphStore(session)
        for cl in clusters:
            gstore.upsert_cluster(
                platform=platform,
                members=cl.members,
                method=cl.method,
                cluster_score=cl.score,
                parent_id=video_id,
            )
    except Exception:  # noqa: BLE001
        pass

    # --- Phase 5: video-level coordination score -------------------------
    # Tier-2B calibration: reliability-weighted consensus, lifted by a
    # positive-evidence noisy-OR so two strong corroborating signatures
    # (e.g. fingerprint + style) are no longer diluted by detectors that
    # abstain on this data shape. See app.detection.coordination.aggregate.
    findings = [f for f in [ts_finding, fp_finding, cohort_finding,
                            style_finding, co_finding, co_tag_finding] if f is not None]
    coord = aggregate_coordination(findings)
    coord_score = coord.score
    coord_tier = _tier_for(coord_score)

    # --- Phase 5.5: persist detected campaigns (first-class, evolving) ------
    # Materialize the coordinated clusters as durable Campaign records — the
    # object the pipeline used to discard. Gated on the corroboration-aware
    # verdict (>= 0.5) so clean scans never manufacture campaigns (Phase 3
    # precision discipline). Best-effort: must never break a scan.
    if coord_score >= 0.5 and clusters:
        try:
            from app.campaigns.service import CampaignService
            texts_by_author: dict[str, list[str]] = {}
            for c in all_comments_under_video:
                aid = str(c.get("author_external_id") or "")
                txt = c.get("text")
                if aid and txt:
                    texts_by_author.setdefault(aid, []).append(txt)
            handles = {}
            for m in commenters_meta:
                aid = str(m.get("external_id") or m.get("channel_id") or m.get("author_external_id") or "")
                if aid:
                    handles[aid] = str(m.get("handle") or m.get("display_name") or "")
            # SAVEPOINT-isolated: a failure here rolls back ONLY the campaign
            # writes, never the scan's own transaction (best-effort persistence
            # must not corrupt the shared session or the scan result).
            with session.begin_nested():
                CampaignService(session).record_clusters(
                    platform=platform, context_id=video_id, clusters=clusters,
                    coordination_score=coord_score, confidence=coord.weighted_mean,
                    texts_by_account=texts_by_author, handles=handles,
                )
        except Exception:  # noqa: BLE001
            pass

    return FullScanOutput(
        video_id=video_id,
        commenter_records=records,
        thread_scan=thread_scan,
        coordination_clusters=clusters,
        coordination_score=coord_score,
        coordination_tier=coord_tier,
        all_thread_comments=all_comments_under_video,
        quota_used=stats.quota_used,
        fresh_count=fresh,
        cached_count=cached,
    )


def _ingest_narratives_async(items) -> None:
    """Background worker — opens its own DB session, ingests, commits."""
    from app.narrative.service import NarrativeService
    from app.storage.db import get_session as _gs
    with _gs() as session:
        NarrativeService(session).ingest_batch(items)


def _deliver_pending_after_commit() -> None:
    """Background worker — small delay so the outer scan's transaction has
    committed, then deliver any pending watchlist alerts. Safe to call
    repeatedly; deliver_pending_alerts() is idempotent."""
    import time
    try:
        time.sleep(0.5)
        from app.notifications.delivery import deliver_pending_alerts
        deliver_pending_alerts()
    except Exception:  # noqa: BLE001
        pass


def _empty_scan(handle: str) -> ScanResult:
    return ScanResult(
        overall_probability=0.5,
        confidence=0.0,
        tier=Tier.LOW,
        signals=[],
        summary="Scan unavailable for this commenter.",
        subject=handle,
    )


def _tier_for(p: float) -> Tier:
    if p < 0.25:
        return Tier.LOW
    if p < 0.50:
        return Tier.MODERATE
    if p < 0.75:
        return Tier.ELEVATED
    return Tier.HIGH


# ---------------------------------------------------------------------------
# Comprehensive scan — account + video + comments + cross-links in one pass
# ---------------------------------------------------------------------------


@dataclass
class ComprehensiveOutput:
    focus_account: dict | None
    video_output: FullScanOutput | None
    comments_scan: ScanResult | None
    cross_links: list[dict]
    convergence_score: float
    overall_probability: float
    overall_tier: Tier
    summary: str
    matrix_rows: list[dict]
    matrix_methods: list[str]
    inputs_provided: list[str]
    quota_used: int
    next_page_token: str | None = None
    video_id: str | None = None
    # Raw interaction items fetched for the scanned video/content, in the shape
    # ContentIntelligenceService.record_batch consumes. Surfaced so the route
    # layer can persist content intelligence (the Content DB) the same way the
    # /youtube/full path does. Empty when no content was scanned.
    all_comments: list[dict] = field(default_factory=list)


def _parse_pasted_comments(text: str) -> list[Post]:
    """One line = one comment. Blank lines and leading bullet/quote chars are stripped.

    Pasted comments come without timestamps, so we synthesize a sequence at
    1-minute intervals starting now. The temporal detector won't fire
    meaningfully but the semantic + AI-writing layers will.
    """
    from datetime import datetime, timedelta, timezone
    lines = [l.strip().lstrip("•>- ").strip() for l in text.splitlines()]
    lines = [l for l in lines if len(l) >= 2]
    base = datetime.now(timezone.utc)
    return [
        Post(
            id=f"pasted_{i}",
            author_handle=f"pasted_{i}",
            text=l,
            created_at=base + timedelta(minutes=i),
        )
        for i, l in enumerate(lines)
    ]


def scan_comprehensive(
    session: Session,
    *,
    account_url_or_handle: str | None,
    video_url_or_id: str | None,
    comments_text: str | None,
    max_commenters: int,
    force_refresh: bool,
    source: Source,
    start_page_token: str | None = None,
    injected_commenters: list[dict] | None = None,
    injected_comments: list[dict] | None = None,
) -> ComprehensiveOutput:
    """Run whatever the user supplied + cross-link the results.

    Platform-agnostic: every fetch goes through the injected :class:`Source`
    (the only platform-specific seam). YouTube, Twitter, etc. each provide a
    Source; the detector / coordination / memory / OmiScore stack below is
    shared and consumes the normalized Profile / Post objects unchanged.
    """
    settings = get_settings()
    AccountRepository(session)
    inputs_provided: list[str] = []

    # ---- 1. Pasted comments scan (no API quota) ----
    comments_scan: ScanResult | None = None
    pasted_posts: list[Post] = []
    if comments_text and comments_text.strip():
        pasted_posts = _parse_pasted_comments(comments_text)
        if pasted_posts:
            comments_scan = analyze_comments(pasted_posts)
            inputs_provided.append("comments")

    # ---- 2. Focus account scan ----
    focus_dict: dict | None = None
    focus_external_id: str | None = None
    focus_profile: Profile | None = None
    focus_posts: list[Post] = []
    focus_fingerprint: list[float] | None = None
    focus_scan: ScanResult | None = None
    if account_url_or_handle and account_url_or_handle.strip():
        channel_id = source.resolve_account_id(account_url_or_handle)
        if channel_id:
            focus_external_id = channel_id
            focus_profile = source.fetch_account_profile(channel_id)
            if focus_profile is not None:
                focus_posts = source.fetch_account_posts(
                    channel_id, settings.scan_max_history_per_commenter
                )
                orch = scan_account_with_memory(
                    session,
                    platform=source.platform,
                    external_id=channel_id,
                    profile=focus_profile,
                    posts=focus_posts,
                    force_refresh=force_refresh,
                )
                focus_scan = orch.result
                focus_fingerprint = extract_fingerprint(focus_scan)
                # Build activity samples for non-low tiers (mirrors _activity_payload in routes/scan)
                _samples: list[dict] = []
                if focus_scan.tier != Tier.LOW:
                    for p in focus_posts[:10]:
                        text = (p.text or "").strip()
                        if len(text) > 280:
                            text = text[:280] + "…"
                        _samples.append({
                            "text": text,
                            "created_at": p.created_at.isoformat() if p.created_at else None,
                            "parent_id": p.parent_id,
                            "like_count": p.like_count,
                        })
                focus_dict = {
                    "external_id": channel_id,
                    "handle": focus_profile.handle,
                    "display_name": focus_profile.display_name,
                    "avatar_url": focus_profile.avatar_url,
                    "bio": focus_profile.bio,
                    "follower_count": focus_profile.follower_count,
                    "account_created_at": focus_profile.created_at,
                    "overall_probability": focus_scan.overall_probability,
                    "confidence": focus_scan.confidence,
                    "tier": focus_scan.tier,
                    "summary": focus_scan.summary,
                    "signals": list(focus_scan.signals),
                    "from_cache": orch.from_cache,
                    "matched_prior_neighbors": orch.matched_neighbors,
                    "history_size": len(focus_posts),
                    "suspected_intent": focus_scan.suspected_intent,
                    "intent_label": focus_scan.intent_label,
                    "reasons": list(focus_scan.reasons or []),
                    "recent_activity": _samples,
                    "activity_total": len(focus_posts),
                }
                inputs_provided.append("account")

    # ---- 3. Video full scan ----
    video_output: FullScanOutput | None = None
    next_page_token: str | None = None
    resolved_video_id: str | None = None
    all_comments: list[dict] = []
    if video_url_or_id and video_url_or_id.strip():
        video_id = source.parse_content_id(video_url_or_id)
        if video_id:
            resolved_video_id = video_id
            if injected_commenters is not None:
                # Select-then-scan: score EXACTLY the commenters the user picked from the cached compile
                # step — do NOT re-fetch the content's commenters. The list was already gathered (and
                # paid for with nothing); scoring runs only on this selection.
                commenters_meta = injected_commenters
                all_comments = injected_comments or []
                next_page_token = None
            else:
                commenters_meta, all_comments, next_page_token = source.fetch_content_engagers(
                    video_id,
                    max_commenters=max_commenters,
                    max_comments=max_commenters * 3,
                    start_page_token=start_page_token,
                )

            video_output = scan_video_full(
                session,
                platform=source.platform,
                video_id=video_id,
                commenters_meta=commenters_meta,
                all_comments_under_video=all_comments,
                fetch_profile=source.fetch_account_profile,
                fetch_history=source.fetch_account_posts,
                stats=source.stats,
                force_refresh=force_refresh,
                fetch_concurrency=getattr(source, "fetch_concurrency", 1),
            )
            inputs_provided.append("video")

    # ---- 4. Cross-link computation (the interconnection layer) ----
    cross_links = _compute_cross_links(
        session=session,
        platform=source.platform,
        focus_external_id=focus_external_id,
        focus_fingerprint=focus_fingerprint,
        focus_posts=focus_posts,
        focus_scan=focus_scan,
        video_output=video_output,
        pasted_posts=pasted_posts,
        comments_scan=comments_scan,
    )

    # ---- 5. Coordination matrix (rows × detector flags) ----
    matrix_rows, matrix_methods = _build_matrix(
        video_output=video_output,
        focus_external_id=focus_external_id,
        focus_dict=focus_dict,
    )

    # ---- 6. Overall synthesis ----
    overall_prob, overall_tier, summary, convergence = _synthesize(
        focus_dict=focus_dict,
        focus_scan=focus_scan,
        video_output=video_output,
        comments_scan=comments_scan,
        cross_links=cross_links,
        inputs_provided=inputs_provided,
    )

    return ComprehensiveOutput(
        focus_account=focus_dict,
        video_output=video_output,
        comments_scan=comments_scan,
        cross_links=cross_links,
        convergence_score=convergence,
        overall_probability=overall_prob,
        overall_tier=overall_tier,
        summary=summary,
        matrix_rows=matrix_rows,
        matrix_methods=matrix_methods,
        inputs_provided=inputs_provided,
        quota_used=source.quota_used,
        next_page_token=next_page_token,
        video_id=resolved_video_id,
        all_comments=all_comments,
    )


def _compute_cross_links(
    *,
    session: Session,
    platform: str,
    focus_external_id: str | None,
    focus_fingerprint: list[float] | None,
    focus_posts: list[Post],
    focus_scan: ScanResult | None,
    video_output: FullScanOutput | None,
    pasted_posts: list[Post],
    comments_scan: ScanResult | None,
) -> list[dict]:
    """The core interconnection logic.

    Builds a list of CrossLink records describing how the user's inputs
    relate to each other. Multiple links converging on the same entity is
    what makes the system more confident than any one source could be alone.
    """
    from app.detection.coordination.style_match import _style_vector, _euclid

    links: list[dict] = []
    repo = AccountRepository(session)

    # ----- A↔V links (account meets video) ---------------------------------
    if focus_external_id and video_output is not None:
        commenter_records_by_id = {r.external_id: r for r in video_output.commenter_records}

        # A1: Direct membership — is the focus account a commenter on this video?
        if focus_external_id in commenter_records_by_id:
            r = commenter_records_by_id[focus_external_id]
            links.append({
                "kind": "focus_in_video",
                "severity": "info",
                "summary": f"Focus account is among the {video_output.commenter_count if hasattr(video_output, 'commenter_count') else len(video_output.commenter_records)} scanned commenters on this video.",
                "evidence": [
                    f"Standalone probability {r.scan_result.overall_probability:.2f} ({r.scan_result.tier.value} suspicion)."
                ],
                "related_entities": [focus_external_id],
                "metadata": {"video_position_probability": r.scan_result.overall_probability},
            })

        # A2: Cluster membership — focus is INSIDE one of the video's clusters
        for cluster in video_output.coordination_clusters:
            if focus_external_id in cluster.members:
                severity = "high" if cluster.score >= 0.7 else "elevated"
                links.append({
                    "kind": "focus_in_cluster",
                    "severity": severity,
                    "summary": f"Focus account is in a {cluster.method.replace('_', ' ')} coordination cluster with {len(cluster.members) - 1} other commenter(s).",
                    "evidence": list(cluster.evidence),
                    "related_entities": [m for m in cluster.members if m != focus_external_id],
                    "metadata": {"cluster_score": cluster.score, "cluster_size": float(len(cluster.members))},
                })

        # A3: Fingerprint resemblance to cluster centroid (even if not a member)
        if focus_fingerprint is not None:
            fps_by_id = {r.external_id: r.fingerprint for r in video_output.commenter_records if r.fingerprint}
            for cluster in video_output.coordination_clusters:
                if focus_external_id in cluster.members:
                    continue  # already covered by A2
                member_fps = [fps_by_id[m] for m in cluster.members if m in fps_by_id]
                if len(member_fps) < 2:
                    continue
                # Centroid = average vector
                dim = len(member_fps[0])
                centroid = [sum(v[i] for v in member_fps) / len(member_fps) for i in range(dim)]
                try:
                    from app.memory.fingerprint import euclidean
                    d = euclidean(focus_fingerprint, centroid)
                except Exception:
                    continue
                if d <= 0.35:
                    severity = "elevated" if d < 0.25 else "moderate"
                    links.append({
                        "kind": "focus_resembles_cluster",
                        "severity": severity,
                        "summary": f"Focus account's behavioral fingerprint matches the centroid of a {cluster.method.replace('_', ' ')} cluster (distance {d:.2f}) — same template even though it isn't a member.",
                        "evidence": [
                            f"Cluster has {len(cluster.members)} members; fingerprint distance to centroid {d:.2f} (threshold 0.35)."
                        ],
                        "related_entities": list(cluster.members),
                        "metadata": {"centroid_distance": d, "cluster_score": cluster.score},
                    })

        # A4: Fellow-traveler (co-engagement) with video's commenters
        commenter_ids = [r.external_id for r in video_output.commenter_records]
        engagement_sets = repo.load_engagement_sets(platform=platform, account_external_ids=commenter_ids + [focus_external_id])
        focus_videos = engagement_sets.get(focus_external_id, set())
        if focus_videos:
            for cid in commenter_ids:
                if cid == focus_external_id:
                    continue
                cset = engagement_sets.get(cid, set())
                shared = focus_videos & cset
                if len(shared) >= 3:
                    j = len(shared) / max(1, len(focus_videos | cset))
                    links.append({
                        "kind": "fellow_traveler",
                        "severity": "elevated" if len(shared) >= 5 else "moderate",
                        "summary": f"Focus account is a fellow-traveler of a commenter here — they've appeared on {len(shared)} of the same videos.",
                        "evidence": [
                            f"Shared videos: {len(shared)}; Jaccard overlap {j:.2f}. Random users almost never co-appear; coordinated networks do."
                        ],
                        "related_entities": [cid],
                        "metadata": {"shared_videos": float(len(shared)), "jaccard": j},
                    })

    # ----- A↔C links (account ↔ pasted comments) --------------------------
    if focus_posts and pasted_posts:
        focus_style = _style_vector([p.text for p in focus_posts])
        pasted_style = _style_vector([p.text for p in pasted_posts])
        if focus_style is not None and pasted_style is not None:
            d = _euclid(focus_style, pasted_style)
            if d <= 0.15:
                severity = "high" if d < 0.08 else "elevated"
                links.append({
                    "kind": "account_style_matches_comments",
                    "severity": severity,
                    "summary": "Pasted comments share a writing-style fingerprint with the focus account's recent posts.",
                    "evidence": [
                        f"Style-fingerprint distance {d:.3f} (threshold 0.15). Patterns consistent with the same author."
                    ],
                    "related_entities": [focus_external_id or ""],
                    "metadata": {"style_distance": d},
                })

    # ----- V↔C links (video ↔ pasted comments) ----------------------------
    if video_output is not None and pasted_posts:
        # For each cluster in the video, check semantic overlap between pasted
        # comments and the cluster's members' comments.
        comment_texts_by_author: dict[str, list[str]] = {}
        for r in video_output.commenter_records:
            comment_texts_by_author[r.external_id] = [p.text for p in r.posts if p.text]

        for cluster in video_output.coordination_clusters:
            cluster_texts: list[str] = []
            for m in cluster.members:
                cluster_texts.extend(comment_texts_by_author.get(m, []))
            if not cluster_texts:
                continue
            shared = _ngram_overlap_share([p.text for p in pasted_posts], cluster_texts)
            if shared >= 0.20:
                links.append({
                    "kind": "comments_match_cluster",
                    "severity": "elevated" if shared >= 0.35 else "moderate",
                    "summary": f"Pasted comments echo content from a {cluster.method.replace('_', ' ')} cluster on this video.",
                    "evidence": [
                        f"Mean 5-gram overlap {shared:.2f} between your pasted comments and this cluster's recent comments."
                    ],
                    "related_entities": list(cluster.members),
                    "metadata": {"ngram_overlap": shared, "cluster_score": cluster.score},
                })

    return links


def _ngram_overlap_share(left: list[str], right: list[str], n: int = 5) -> float:
    """Cheap mean Jaccard of word 5-grams between two text sets."""
    import re
    word_re = re.compile(r"\w+", re.UNICODE)

    def shingles(text: str):
        tokens = [t.lower() for t in word_re.findall(text)]
        if len(tokens) < n:
            return {tuple(tokens)} if tokens else set()
        return {tuple(tokens[i:i + n]) for i in range(len(tokens) - n + 1)}

    L = [shingles(t) for t in left if t]
    R = [shingles(t) for t in right if t]
    L = [s for s in L if s]
    R = [s for s in R if s]
    if not L or not R:
        return 0.0
    total = 0.0
    pairs = 0
    for a in L:
        for b in R:
            u = len(a | b)
            if u:
                total += len(a & b) / u
                pairs += 1
    return total / pairs if pairs else 0.0


def _build_matrix(
    *,
    video_output: FullScanOutput | None,
    focus_external_id: str | None,
    focus_dict: dict | None,
) -> tuple[list[dict], list[str]]:
    """Account × detector matrix for the visualization."""
    methods = ["temporal_semantic_clique", "fingerprint_cluster",
               "age_cohort", "style_match", "co_engagement"]

    rows: list[dict] = []
    if video_output is None and focus_dict is None:
        return rows, methods

    # Build a map: external_id -> set[method] (which detectors flagged them)
    flagged_by_method: dict[str, set[str]] = {}
    if video_output is not None:
        for cluster in video_output.coordination_clusters:
            for m in cluster.members:
                flagged_by_method.setdefault(m, set()).add(cluster.method)

    # Add commenters from the video
    if video_output is not None:
        for r in video_output.commenter_records:
            flags = flagged_by_method.get(r.external_id, set())
            rows.append({
                "external_id": r.external_id,
                "handle": r.handle,
                "is_focus": r.external_id == focus_external_id,
                "tier": r.scan_result.tier,
                "probability": r.scan_result.overall_probability,
                "coordination_adjusted_probability": r.coordination_adjusted_probability,
                "detector_flags": {m: (m in flags) for m in methods},
                "convergence_count": len(flags),
            })

    # If focus account exists and isn't already in the matrix, add it
    if focus_dict and not any(r["external_id"] == focus_external_id for r in rows):
        flags = flagged_by_method.get(focus_external_id or "", set())
        rows.append({
            "external_id": focus_external_id,
            "handle": focus_dict["handle"],
            "is_focus": True,
            "tier": focus_dict["tier"],
            "probability": focus_dict["overall_probability"],
            "coordination_adjusted_probability": None,
            "detector_flags": {m: (m in flags) for m in methods},
            "convergence_count": len(flags),
        })

    # Sort: focus first, then by convergence count desc, then by probability desc
    rows.sort(key=lambda r: (
        not r["is_focus"],
        -r["convergence_count"],
        -(r.get("coordination_adjusted_probability") or r["probability"]),
    ))
    return rows, methods


def _synthesize(
    *,
    focus_dict: dict | None,
    focus_scan: ScanResult | None,
    video_output: FullScanOutput | None,
    comments_scan: ScanResult | None,
    cross_links: list[dict],
    inputs_provided: list[str],
) -> tuple[float, Tier, str, float]:
    """Combine all sources into one top-level probability + summary."""
    parts: list[tuple[float, float]] = []  # (prob, weight)
    if focus_scan is not None:
        parts.append((focus_scan.overall_probability, 1.0 + 0.4 * focus_scan.confidence))
    if video_output is not None:
        # Video's overall = mean commenter probability (coordination-adjusted when present)
        if video_output.commenter_records:
            vmean = sum(
                (r.coordination_adjusted_probability or r.scan_result.overall_probability)
                for r in video_output.commenter_records
            ) / len(video_output.commenter_records)
        else:
            vmean = 0.5
        parts.append((vmean, 0.8))
        # Coordination score itself is a separate input
        parts.append((video_output.coordination_score, 1.0))
    if comments_scan is not None:
        parts.append((comments_scan.overall_probability, 0.7 + 0.3 * comments_scan.confidence))

    # Convergence amplifies: each high-severity cross-link adds weight to the
    # consensus probability.
    severity_lifts = {"info": 0.0, "moderate": 0.05, "elevated": 0.10, "high": 0.15}
    total_lift = sum(severity_lifts.get(l["severity"], 0) for l in cross_links)
    convergence_score = min(1.0, total_lift / 0.45)  # ~3 high-severity links = full

    if not parts:
        return 0.5, Tier.LOW, "No inputs provided.", 0.0

    weighted = sum(p * w for p, w in parts) / sum(w for _, w in parts)
    overall = min(0.99, weighted + total_lift * (1 - weighted))
    tier = _tier_for(overall)

    # Build the summary
    summary_parts: list[str] = []
    if inputs_provided:
        summary_parts.append(
            f"Comprehensive scan over: {', '.join(inputs_provided)}."
        )
    summary_parts.append(
        f"Overall {tier.value} suspicion ({int(overall * 100)}% combined probability)."
    )
    if cross_links:
        high_count = sum(1 for l in cross_links if l["severity"] in ("elevated", "high"))
        summary_parts.append(
            f"{len(cross_links)} cross-link(s) detected"
            + (f", {high_count} elevated or high severity" if high_count else "")
            + ". Multiple independent signals agreeing strengthens the verdict."
        )
    summary_parts.append("All output is probabilistic and evidence-bearing — never a definitive judgement about the account or person behind it.")

    return overall, tier, " ".join(summary_parts), convergence_score
