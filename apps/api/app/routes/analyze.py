from __future__ import annotations

from fastapi import APIRouter

from app.detection import analyze_account, analyze_comments
from app.schemas import (
    AccountAnalysisRequest,
    CommentAnalysisRequest,
    ScanResult,
)

router = APIRouter(prefix="/v1/analyze", tags=["analyze"])


@router.post("/account", response_model=ScanResult)
def post_analyze_account(req: AccountAnalysisRequest) -> ScanResult:
    """Score a single account given a normalized profile + posts payload.

    This endpoint runs *only* on supplied data — it does not fetch from any
    platform API. Platform fetching lives in the (not yet built)
    ``app/integrations`` layer and will be wired into a separate
    ``/v1/scan/by-url`` endpoint.
    """
    return analyze_account(req.profile, req.posts)


@router.post("/comments", response_model=ScanResult)
def post_analyze_comments(req: CommentAnalysisRequest) -> ScanResult:
    """Score a batch of comments for AI-likelihood and coordination signals."""
    return analyze_comments(req.comments)
