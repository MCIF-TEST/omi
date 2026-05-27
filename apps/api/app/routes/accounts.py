"""Account-level read routes.

Phase 2 surface — exposes the persisted scan history for a single
account plus a categorical trend over time. The OMISPHERE web app
calls this from `/(app)/accounts/[external_id]` to render the score
curve.

Read-only; no credit cost.
"""

from __future__ import annotations

from datetime import timezone

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.auth import CurrentUser, require_user
from app.detection.trend import analyze_trend
from app.schemas import (
    AccountHistoryResponse,
    HistoricalScan,
    Tier,
    TrendInfo,
)
from app.storage.db import get_session
from app.storage.repository import AccountRepository


router = APIRouter(prefix="/v1/accounts", tags=["accounts"])


def _ensure_utc(dt):
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


@router.get("/{platform}/{external_id}/history", response_model=AccountHistoryResponse)
def account_history(
    platform: str,
    external_id: str,
    limit: int = 50,
    current: CurrentUser = Depends(require_user),
) -> AccountHistoryResponse:
    if limit < 1 or limit > 200:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="limit must be between 1 and 200",
        )

    with get_session() as session:
        repo = AccountRepository(session)
        account, scans = repo.account_history(platform, external_id, limit=limit)
        if account is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No scans on file for {platform}:{external_id}.",
            )

        # Sort oldest → newest for trend analysis
        scans_oldest_first = list(reversed(scans))
        points = [
            (_ensure_utc(s.scanned_at), s.overall_probability)
            for s in scans_oldest_first
            if s.scanned_at is not None
        ]
        trend = analyze_trend(points)

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
            scans=[
                HistoricalScan(
                    scanned_at=_ensure_utc(s.scanned_at),
                    overall_probability=s.overall_probability,
                    confidence=s.confidence,
                    tier=Tier(s.tier),
                    summary=s.summary,
                )
                for s in scans  # newest first for UI
            ],
            trend=TrendInfo(
                direction=trend.direction,
                slope=trend.slope,
                volatility=trend.volatility,
                net_change=trend.net_change,
                sample_size=trend.sample_size,
                summary=trend.summary,
            ),
        )
