"""Admin-only metrics endpoint — Phase 9.

Combines:
* The in-process metrics registry (counters + latency histograms).
* Database-level rollups (totals, lifetime YouTube quota, total reasoning
  tokens — both proxies for cost).

Cardinality is intentionally low — this is for operations dashboards,
not a Prometheus replacement.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select

from app.core.auth import CurrentUser, require_user
from app.core.cache import get_cache
from app.core.metrics import get_registry
from app.storage.db import get_session
from app.storage.models import (
    Account, Alert, Investigation, Scan, User, Watchlist,
)


router = APIRouter(prefix="/v1", tags=["metrics"])


@router.get("/metrics")
def metrics(current: CurrentUser = Depends(require_user)) -> dict:
    if not current.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Admin only.",
        )

    reg = get_registry()
    with get_session() as session:
        totals = {
            "users":          int(session.execute(select(func.count(User.id))).scalar_one()),
            "active_subs":    int(session.execute(
                select(func.count(User.id)).where(User.subscription_status == "active")
            ).scalar_one()),
            "accounts":       int(session.execute(select(func.count(Account.id))).scalar_one()),
            "scans":          int(session.execute(select(func.count(Scan.id))).scalar_one()),
            "investigations": int(session.execute(select(func.count(Investigation.id))).scalar_one()),
            "watchlists":     int(session.execute(select(func.count(Watchlist.id))).scalar_one()),
            "alerts":         int(session.execute(select(func.count(Alert.id))).scalar_one()),
            "alerts_unread":  int(session.execute(
                select(func.count(Alert.id)).where(Alert.read_at.is_(None))
            ).scalar_one()),
        }
        cost = {
            "youtube_quota_lifetime": int(
                session.execute(select(func.coalesce(func.sum(Investigation.quota_used), 0))).scalar_one()
            ),
            "reasoning_tokens_lifetime": int(
                session.execute(
                    select(func.coalesce(func.sum(Investigation.commentary_tokens_used), 0))
                ).scalar_one()
            ),
        }

    return {
        "totals": totals,
        "cost": cost,
        "process": reg.snapshot(),
        "cache": get_cache().stats(),
    }
