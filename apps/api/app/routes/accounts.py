"""Account-level read routes.

Exposes persisted scan history, per-detector signal breakdown, and
LLM-generated behavioural analysis for a single account.

Read-only; no credit cost.
"""

from __future__ import annotations

from datetime import timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.auth import CurrentUser, require_user
from app.detection.trend import analyze_trend
from app.schemas import (
    AccountAnalysisResponse,
    AccountHistoryResponse,
    AccountSearchResponse,
    AccountSearchResult,
    HistoricalScan,
    SignalResult,
    Tier,
    TrendInfo,
)
from app.storage.db import get_session
from app.storage.repository import AccountRepository


router = APIRouter(prefix="/v1/accounts", tags=["accounts"])


@router.get("/search", response_model=AccountSearchResponse)
def search_accounts(
    q: str = Query(min_length=2, max_length=100, description="Handle, display name, or channel ID prefix."),
    platform: str = Query(default="youtube"),
    limit: int = Query(default=20, ge=1, le=50),
    current: CurrentUser = Depends(require_user),
) -> AccountSearchResponse:
    """Cross-scan account search. Searches every account in the intelligence
    database by handle, display name, or external ID. No credit cost — reads
    only data you've already contributed to the shared fingerprint store."""
    with get_session() as session:
        repo = AccountRepository(session)
        accounts = repo.search_accounts(q, platform=platform, limit=limit)

    results = [
        AccountSearchResult(
            external_id=a.external_id,
            platform=a.platform,
            handle=a.handle,
            display_name=a.display_name,
            tier=Tier(a.last_tier) if a.last_tier else None,
            overall_probability=a.last_score,
            last_scanned_at=_ensure_utc(a.last_scanned_at),
            first_seen_at=_ensure_utc(a.first_seen_at),
            follower_count=a.follower_count,
        )
        for a in accounts
    ]
    return AccountSearchResponse(query=q, platform=platform, results=results)


def _ensure_utc(dt):
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def _signals_from_json(signals_json: list[dict] | None) -> list[SignalResult]:
    if not signals_json:
        return []
    out = []
    for s in signals_json:
        try:
            out.append(SignalResult(**s))
        except Exception:
            pass
    return out


@router.get("/{platform}/{external_id}/history", response_model=AccountHistoryResponse)
def account_history(
    platform: str,
    external_id: str,
    limit: int = 500,
    current: CurrentUser = Depends(require_user),
) -> AccountHistoryResponse:
    if limit < 1 or limit > 1000:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="limit must be between 1 and 1000",
        )

    with get_session() as session:
        repo = AccountRepository(session)
        account, scans = repo.account_history(platform, external_id, limit=limit)
        if account is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No scans on file for {platform}:{external_id}.",
            )
        total_scans = repo.count_scans(account.id)

        scans_oldest_first = list(reversed(scans))
        points = [
            (_ensure_utc(s.scanned_at), s.overall_probability)
            for s in scans_oldest_first
            if s.scanned_at is not None
        ]
        trend = analyze_trend(points)

        historical: list[HistoricalScan] = []
        for i, s in enumerate(scans):  # newest first
            # Include full signal breakdown for every historical scan so the
            # UI can expand any row to see what fired (not just the latest).
            signals = _signals_from_json(s.signals_json)
            historical.append(HistoricalScan(
                scanned_at=_ensure_utc(s.scanned_at),
                overall_probability=s.overall_probability,
                confidence=s.confidence,
                tier=Tier(s.tier),
                summary=s.summary,
                signals=signals,
            ))

        return AccountHistoryResponse(
            platform=platform,  # type: ignore[arg-type]
            external_id=external_id,
            handle=account.handle,
            display_name=account.display_name,
            bio=account.bio,
            follower_count=account.follower_count,
            account_created_at=_ensure_utc(account.account_created_at),
            first_seen_at=_ensure_utc(account.first_seen_at),
            last_scanned_at=_ensure_utc(account.last_scanned_at),
            scans=historical,
            total_scans=total_scans,
            trend=TrendInfo(
                direction=trend.direction,
                slope=trend.slope,
                volatility=trend.volatility,
                net_change=trend.net_change,
                sample_size=trend.sample_size,
                summary=trend.summary,
            ),
        )


@router.get("/{platform}/{external_id}/analysis", response_model=AccountAnalysisResponse)
def account_analysis(
    platform: str,
    external_id: str,
    current: CurrentUser = Depends(require_user),
) -> AccountAnalysisResponse:
    """Generate an LLM (or template) behavioural analysis for an account.

    Uses the latest stored scan signals + trend data. Falls back gracefully
    to a template paragraph when no Anthropic key is configured.
    """
    with get_session() as session:
        repo = AccountRepository(session)
        account, scans = repo.account_history(platform, external_id, limit=50)
        if account is None or not scans:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No scans on file for {platform}:{external_id}.",
            )

        latest = scans[0]
        scans_oldest_first = list(reversed(scans))
        points = [
            (_ensure_utc(s.scanned_at), s.overall_probability)
            for s in scans_oldest_first
            if s.scanned_at is not None
        ]
        trend = analyze_trend(points)
        signals_json = latest.signals_json or []

    from app.reasoning.commentary import synthesize_account_analysis
    result = synthesize_account_analysis(
        handle=account.handle,
        platform=platform,
        overall_probability=latest.overall_probability,
        tier=latest.tier,
        confidence=latest.confidence,
        summary=latest.summary,
        signals=signals_json,
        trend_direction=trend.direction,
        trend_summary=trend.summary,
        scan_count=len(scans),
        reasons=[],
        weak_signals=[],
    )

    return AccountAnalysisResponse(
        platform=platform,
        external_id=external_id,
        handle=account.handle,
        analysis=result.text,
        provider=result.provider,
    )
