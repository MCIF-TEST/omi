"""Admin view of paid upstream API spend.

The ledger exists so a runaway cannot happen unnoticed; this is the half that makes it noticed. A
budget with no readout tells you only that you were refused, never how close you are, which of your
users is heavy, or whether today is normal. That is the same mistake the dispute queue made by
shipping routes with no interface.

Admin only, because it exposes per-user activity volumes.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.auth import CurrentUser, require_user
from app.core.upstream_budget import usage_snapshot
from app.storage.db import get_session

router = APIRouter(prefix="/v1/admin/usage", tags=["admin-usage"])


@router.get("")
def upstream_usage(
    days: int = Query(14, ge=1, le=90),
    current: CurrentUser = Depends(require_user),
) -> dict:
    """Today's upstream spend against both budgets, the recent daily trend, and today's heaviest users.

    ``api_calls`` is the number that bills (twitterapi.io charges per call), not the number of
    requests this product served. One compile can page the provider several times.
    """
    if not current.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admins only.")
    with get_session() as session:
        return usage_snapshot(session, days=days)
