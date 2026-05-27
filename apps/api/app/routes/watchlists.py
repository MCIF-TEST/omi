"""Watchlists CRUD — Phase 8."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.auth import CurrentUser, require_user
from app.monitoring.service import MonitoringService
from app.schemas import WatchlistIn, WatchlistOut, WatchlistsResponse
from app.storage.db import get_session
from app.storage.models import Watchlist


router = APIRouter(prefix="/v1/watchlists", tags=["watchlists"])


def _to_out(w: Watchlist) -> WatchlistOut:
    return WatchlistOut(
        id=w.id,
        kind=w.kind,
        target_id=w.target_id,
        label=w.label,
        alert_threshold_tier=w.alert_threshold_tier,
        last_seen_tier=w.last_seen_tier,
        last_seen_probability=w.last_seen_probability,
        last_checked_at=w.last_checked_at,
        last_alert_at=w.last_alert_at,
        created_at=w.created_at,
    )


@router.get("", response_model=WatchlistsResponse)
def list_watchlists(
    current: CurrentUser = Depends(require_user),
) -> WatchlistsResponse:
    if current.id == 0:
        return WatchlistsResponse(watchlists=[])
    with get_session() as session:
        svc = MonitoringService(session)
        return WatchlistsResponse(
            watchlists=[_to_out(w) for w in svc.list_watchlists(current.id)],
        )


@router.post("", response_model=WatchlistOut)
def add_watchlist(
    payload: WatchlistIn,
    current: CurrentUser = Depends(require_user),
) -> WatchlistOut:
    if current.id == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Watchlists require an authenticated user.",
        )
    target = (payload.target_id or "").strip()
    if not target:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="target_id is required.",
        )
    with get_session() as session:
        svc = MonitoringService(session)
        w = svc.add_watchlist(
            user_id=current.id,
            kind=payload.kind,
            target_id=target,
            label=(payload.label or target).strip(),
            alert_threshold_tier=payload.alert_threshold_tier,
        )
        return _to_out(w)


@router.delete("/{watchlist_id}")
def delete_watchlist(
    watchlist_id: int,
    current: CurrentUser = Depends(require_user),
) -> dict:
    if current.id == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found.")
    with get_session() as session:
        ok = MonitoringService(session).delete_watchlist(
            watchlist_id=watchlist_id, user_id=current.id,
        )
        if not ok:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found.")
    return {"ok": True}
