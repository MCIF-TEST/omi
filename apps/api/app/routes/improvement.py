"""Continuous Improvement Engine engineering APIs (Sprint 011) — admin only.

Exposes the deterministic recommendation engine and the engineering-report generator over
evaluation snapshots an engineer supplies (built with ``build_snapshot`` from the gold corpus).
These endpoints **recommend** only — they never change production. Promotion stays a human
decision recorded in the ledger; applying a change is a separate, deliberate step.
"""
from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException, status

from app.core.auth import CurrentUser, require_user
from app.reasoning.improvement import engineering_report, recommend

admin_router = APIRouter(prefix="/v1/admin/improvement", tags=["admin-improvement"])


def _require_admin(current: CurrentUser) -> None:
    if not current.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only.")


@admin_router.post("/recommend")
def recommend_route(
    body: dict = Body(..., description="{'baseline': <snapshot>, 'candidate': <snapshot>}"),
    current: CurrentUser = Depends(require_user),
) -> dict:
    """Run the recommendation engine over a baseline + candidate snapshot. Deterministic and
    evidence-backed; returns recommendations only (no production change)."""
    _require_admin(current)
    baseline, candidate = body.get("baseline"), body.get("candidate")
    if not isinstance(baseline, dict) or not isinstance(candidate, dict):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Provide 'baseline' and 'candidate' snapshot objects.")
    recs = recommend(baseline, candidate)
    return {"recommendations": [r.to_dict() for r in recs], "count": len(recs)}


@admin_router.post("/report")
def report_route(
    body: dict = Body(..., description="{'snapshots': [<snapshot>...], 'recommendations': [...]}"),
    current: CurrentUser = Depends(require_user),
) -> dict:
    """Generate the structured engineering report over a set of evaluation snapshots."""
    _require_admin(current)
    snapshots = body.get("snapshots")
    if not isinstance(snapshots, list):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Provide a 'snapshots' list.")
    return engineering_report(snapshots, recommendations=body.get("recommendations"))
