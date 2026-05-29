"""Phase 7 — OmiScore intelligence endpoints.

Exposes the unified intelligence engine (:mod:`app.intelligence`) over HTTP:

* ``POST /v1/intelligence/score`` — score a raw profile+posts payload and
  return the full OmiScore envelope. Pure-compute, mirrors
  ``/v1/analyze/account`` but returns intelligence dimensions instead of the
  flat ScanResult. No platform fetching, no quota.

* ``POST /v1/intelligence/comments`` — score a batch of comments (content
  perspective: semantic + AI-writing) into an OmiScore.

* ``GET /v1/intelligence/account/{platform}/{external_id}`` — compute the
  OmiScore for an already-scanned account, reconstructed from its most recent
  persisted scan. This is the cheap read path for dashboards: no re-scan, no
  API calls, just the intelligence view over what we already know.

The engine is purely additive: it consumes the rule engine's ScanResult (and
any ML re-ranking already baked into it) and composes the dimensions. The
existing ``/v1/analyze`` and ``/v1/scan`` endpoints are untouched.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.auth import CurrentUser, require_user
from app.detection.engine import analyze_account, analyze_comments
from app.detection.scoring import _extract_reasons, _infer_intent
from app.intelligence import OmiScore, compute_omiscore
from app.schemas import (
    AccountAnalysisRequest,
    CommentAnalysisRequest,
    ScanResult,
    SignalResult,
    Tier,
)
from app.storage.db import get_session
from app.storage.models import Account, Scan

router = APIRouter(prefix="/v1/intelligence", tags=["intelligence"])


@router.post("/score", response_model=OmiScore)
def post_score_account(req: AccountAnalysisRequest) -> OmiScore:
    """Compute the OmiScore for a supplied profile + posts payload.

    Runs the rule engine on the supplied data only (no platform fetch, no
    memory prior — that's the orchestrator's job) and composes the result
    into the intelligence envelope.
    """
    scan = analyze_account(req.profile, req.posts)
    return compute_omiscore(scan)


@router.post("/comments", response_model=OmiScore)
def post_score_comments(req: CommentAnalysisRequest) -> OmiScore:
    """Compute the OmiScore for a batch of comments (content perspective)."""
    scan = analyze_comments(req.comments)
    return compute_omiscore(scan)


@router.get("/account/{platform}/{external_id}", response_model=OmiScore)
def get_account_omiscore(
    platform: str,
    external_id: str,
    _: CurrentUser = Depends(require_user),
) -> OmiScore:
    """Compute the OmiScore for an already-scanned account.

    Reconstructs the most recent persisted scan (no re-scan, no quota) and
    composes its intelligence view. 404 if we've never scanned this account.
    """
    with get_session() as session:
        account = session.query(Account).filter(
            Account.platform == platform,
            Account.external_id == external_id,
        ).first()
        if account is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No scanned account {platform}:{external_id}. Run a scan first.",
            )
        scan_row = (
            session.query(Scan)
            .filter(Scan.account_id == account.id)
            .order_by(Scan.scanned_at.desc())
            .first()
        )
        if scan_row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Account {platform}:{external_id} has no scan history yet.",
            )
        scan = _reconstruct_scan(scan_row, account.handle)
    return compute_omiscore(scan)


def _reconstruct_scan(scan_row: Scan, handle: str | None) -> ScanResult:
    """Rehydrate a ScanResult from a persisted Scan row.

    Mirrors the reconstruction the orchestrator does on cache hits so the
    OmiScore over a stored scan matches a fresh one byte-for-byte.
    """
    signals = [SignalResult(**s) for s in (scan_row.signals_json or [])]
    tier = Tier(scan_row.tier)
    intent_code, intent_label = _infer_intent(signals, tier)
    return ScanResult(
        overall_probability=scan_row.overall_probability,
        confidence=scan_row.confidence,
        tier=tier,
        signals=signals,
        summary=scan_row.summary or "",
        subject=handle,
        suspected_intent=intent_code,
        intent_label=intent_label,
        reasons=_extract_reasons(signals, tier),
    )
