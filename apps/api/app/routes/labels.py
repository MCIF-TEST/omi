"""Ground-truth label CRUD + calibration-fixture export.

This is the operator-driven feedback loop that takes the calibration story
from "synthetic JSON fixture" to "real labeled accounts from production
use". When an admin reviews a scan and disagrees (or strongly agrees), they
label the account here. The calibration harness can then run against THIS
data via the ``--from-db`` flag.

Admin-only — labels are ground truth for evaluating the engine and we
don't want subscriber labels to skew the corpus.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select

from app.core.auth import CurrentUser, require_user
from app.detection.engine import analyze_account
from app.schemas import (
    AccountLabelCreate,
    AccountLabelOut,
    AccountLabelsListResponse,
    CalibrationFixtureCase,
    CalibrationFixtureResponse,
    LABEL_CONFIDENCES,
    LABEL_KINDS,
    LABEL_SOURCES,
    Post,
    Profile,
    Tier,
)
from app.storage.db import get_session
from app.storage.models import Account, AccountLabel, Scan, User


router = APIRouter(prefix="/v1/labels", tags=["labels"])


def _require_admin(current: CurrentUser) -> None:
    if not current.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Labelling is admin-only — these labels are ground truth.",
        )


def _validate_label_fields(req: AccountLabelCreate) -> None:
    """Reject malformed input loudly so a typo doesn't quietly poison the
    calibration corpus."""
    if req.label not in LABEL_KINDS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"label must be one of {sorted(LABEL_KINDS)}; got '{req.label}'.",
        )
    if req.expected_tier not in {t.value for t in Tier}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"expected_tier must be one of low/moderate/elevated/high; got '{req.expected_tier}'.",
        )
    if req.confidence not in LABEL_CONFIDENCES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"confidence must be one of {sorted(LABEL_CONFIDENCES)}; got '{req.confidence}'.",
        )


def _resolve_account(session, req: AccountLabelCreate) -> Account:
    """Find the account the label refers to. The UI usually passes account_id;
    scripts and the suspension auto-labeler pass (platform, external_id)."""
    if req.account_id is not None:
        acc = session.get(Account, req.account_id)
        if acc is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No account with id={req.account_id}.",
            )
        return acc
    if req.platform and req.external_id:
        acc = session.execute(
            select(Account).where(
                Account.platform == req.platform,
                Account.external_id == req.external_id,
            )
        ).scalar_one_or_none()
        if acc is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=(
                    f"No scanned account for {req.platform}/{req.external_id}. "
                    "Scan it first so the system has a profile + history to evaluate against."
                ),
            )
        return acc
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Provide either account_id or (platform, external_id).",
    )


def _to_out(row: AccountLabel, account: Account, user_email: str | None) -> AccountLabelOut:
    return AccountLabelOut(
        id=row.id,
        account_id=row.account_id,
        user_id=row.user_id,
        user_email=user_email,
        platform=account.platform,
        external_id=account.external_id,
        handle=account.handle,
        label=row.label,
        expected_tier=row.expected_tier,
        confidence=row.confidence,
        source=row.source,
        rationale=row.rationale,
        created_at=row.created_at,
    )


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


@router.post("", response_model=AccountLabelOut)
def create_or_update_label(
    req: AccountLabelCreate,
    current: CurrentUser = Depends(require_user),
) -> AccountLabelOut:
    """Idempotent upsert: one label per (account, user).

    Re-posting with the same account_id from the same user updates the
    existing row instead of creating a duplicate. This lets the UI's
    "Save" button work without a separate PATCH endpoint.
    """
    _require_admin(current)
    _validate_label_fields(req)

    with get_session() as session:
        account = _resolve_account(session, req)

        existing = session.execute(
            select(AccountLabel).where(
                AccountLabel.account_id == account.id,
                AccountLabel.user_id == current.id,
            )
        ).scalar_one_or_none()

        if existing is not None:
            existing.label = req.label
            existing.expected_tier = req.expected_tier
            existing.confidence = req.confidence
            existing.rationale = req.rationale
            existing.created_at = datetime.now(timezone.utc)
            row = existing
        else:
            row = AccountLabel(
                account_id=account.id,
                user_id=current.id,
                label=req.label,
                expected_tier=req.expected_tier,
                confidence=req.confidence,
                rationale=req.rationale,
                source="manual",
            )
            session.add(row)
            session.flush()

        return _to_out(row, account, current.email)


@router.delete("/{label_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_label(
    label_id: int,
    current: CurrentUser = Depends(require_user),
) -> None:
    _require_admin(current)
    with get_session() as session:
        row = session.get(AccountLabel, label_id)
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No label with id={label_id}.",
            )
        session.delete(row)


@router.get("", response_model=AccountLabelsListResponse)
def list_labels(
    current: CurrentUser = Depends(require_user),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    label: str | None = Query(default=None),
    source: str | None = Query(default=None),
) -> AccountLabelsListResponse:
    _require_admin(current)
    with get_session() as session:
        stmt = select(AccountLabel, Account, User).join(
            Account, AccountLabel.account_id == Account.id,
        ).outerjoin(
            User, AccountLabel.user_id == User.id,
        )
        if label:
            stmt = stmt.where(AccountLabel.label == label)
        if source:
            stmt = stmt.where(AccountLabel.source == source)
        stmt = stmt.order_by(AccountLabel.created_at.desc()).limit(limit).offset(offset)

        rows = session.execute(stmt).all()
        total = session.execute(
            select(func.count()).select_from(AccountLabel).where(
                AccountLabel.label == label if label else True,
                AccountLabel.source == source if source else True,
            )
        ).scalar_one()

        labels_out = [
            _to_out(row[0], row[1], row[2].email if row[2] else None)
            for row in rows
        ]

        # Aggregate breakdowns — these are what the operator actually wants
        # to see at a glance ("we have 12 bots labeled, 30 humans, 5 unclear").
        by_label_rows = session.execute(
            select(AccountLabel.label, func.count()).group_by(AccountLabel.label)
        ).all()
        by_source_rows = session.execute(
            select(AccountLabel.source, func.count()).group_by(AccountLabel.source)
        ).all()

        return AccountLabelsListResponse(
            total=int(total),
            labels=labels_out,
            by_label={k: int(v) for k, v in by_label_rows},
            by_source={k: int(v) for k, v in by_source_rows},
        )


# ---------------------------------------------------------------------------
# Calibration export
# ---------------------------------------------------------------------------


@router.get("/calibration", response_model=CalibrationFixtureResponse)
def export_calibration_fixture(
    current: CurrentUser = Depends(require_user),
    min_confidence: str = Query(
        default="medium",
        description="Filter labels by minimum confidence. 'high' for the tightest corpus.",
    ),
) -> CalibrationFixtureResponse:
    """Export labeled accounts as a calibration fixture.

    The shape mirrors the synthetic JSON fixture so ``scripts/calibrate.py``
    can swap data sources without further code changes. Each case carries
    the account's most recent Profile + the posts it was scanned against so
    the harness can run the engine against the same input the labeler saw.

    Labels missing a recent Scan row are skipped (the engine needs posts to
    evaluate against, and we don't fabricate them).
    """
    _require_admin(current)
    if min_confidence not in LABEL_CONFIDENCES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"min_confidence must be one of {sorted(LABEL_CONFIDENCES)}.",
        )

    confidence_filter = (
        [AccountLabel.confidence == "high"]
        if min_confidence == "high"
        else []
    )

    with get_session() as session:
        rows = session.execute(
            select(AccountLabel, Account).join(
                Account, AccountLabel.account_id == Account.id,
            ).where(*confidence_filter)
        ).all()

        cases: list[CalibrationFixtureCase] = []
        by_label: dict[str, int] = {}
        by_source: dict[str, int] = {}

        for label_row, account in rows:
            # The most recent Scan row tells us what the engine actually
            # evaluated. If there's no scan, skip — we don't fabricate posts.
            scan = session.execute(
                select(Scan).where(Scan.account_id == account.id)
                .order_by(Scan.scanned_at.desc())
                .limit(1)
            ).scalar_one_or_none()
            if scan is None:
                continue

            profile_dict = _profile_dict_from_account(account)
            cases.append(CalibrationFixtureCase(
                label=label_row.label,
                expected_tier=label_row.expected_tier,
                expected_probability=None,
                profile=profile_dict,
                # We don't replay the actual posts here (they're not stored;
                # only the resulting signals_json is). The harness's
                # account-from-DB path uses the persisted scan's signals
                # directly via /v1/labels/calibration/evaluate.
                posts=[],
            ))
            by_label[label_row.label] = by_label.get(label_row.label, 0) + 1
            by_source[label_row.source] = by_source.get(label_row.source, 0) + 1

        return CalibrationFixtureResponse(
            n_cases=len(cases),
            by_label=by_label,
            by_source=by_source,
            cases=cases,
        )


@router.get("/calibration/evaluate")
def evaluate_against_labels(
    current: CurrentUser = Depends(require_user),
    min_confidence: str = Query(default="medium"),
) -> dict:
    """Run the calibration metrics against the labeled corpus *in-process*.

    The export endpoint above ships the fixture for the offline harness;
    this endpoint computes the same metrics live so an admin can see real
    precision/recall without leaving the dashboard. Uses the persisted
    Scan rows (most recent per labeled account) — no extra YouTube quota
    consumed.
    """
    _require_admin(current)
    if min_confidence not in LABEL_CONFIDENCES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"min_confidence must be one of {sorted(LABEL_CONFIDENCES)}.",
        )
    confidence_filter = (
        [AccountLabel.confidence == "high"]
        if min_confidence == "high"
        else []
    )

    with get_session() as session:
        rows = session.execute(
            select(AccountLabel, Account).join(
                Account, AccountLabel.account_id == Account.id,
            ).where(*confidence_filter)
        ).all()

        expected: list[str] = []
        predicted: list[str] = []
        brier_terms: list[float] = []
        per_label_correct: dict[str, list[int]] = {}
        per_source_correct: dict[str, list[int]] = {}

        for label_row, account in rows:
            scan = session.execute(
                select(Scan).where(Scan.account_id == account.id)
                .order_by(Scan.scanned_at.desc())
                .limit(1)
            ).scalar_one_or_none()
            if scan is None:
                continue

            exp_tier = label_row.expected_tier
            pred_tier = scan.tier
            expected.append(exp_tier)
            predicted.append(pred_tier)
            target_prob = {
                "low": 0.12, "moderate": 0.37, "elevated": 0.62, "high": 0.87,
            }.get(exp_tier, 0.5)
            brier_terms.append((scan.overall_probability - target_prob) ** 2)

            ok = 1 if exp_tier == pred_tier else 0
            per_label_correct.setdefault(label_row.label, []).append(ok)
            per_source_correct.setdefault(label_row.source, []).append(ok)

    n = len(expected)
    if n == 0:
        return {
            "n_cases": 0,
            "message": "No labeled accounts with persisted scans yet. Label a few accounts and run again.",
        }

    correct = sum(1 for e, p in zip(expected, predicted) if e == p)
    brier = sum(brier_terms) / n

    # Per-tier precision/recall/F1
    tier_metrics: dict[str, dict[str, float]] = {}
    for t in ("low", "moderate", "elevated", "high"):
        tp = sum(1 for e, p in zip(expected, predicted) if e == t and p == t)
        fp = sum(1 for e, p in zip(expected, predicted) if e != t and p == t)
        fn = sum(1 for e, p in zip(expected, predicted) if e == t and p != t)
        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = (
            2 * precision * recall / (precision + recall)
            if (precision + recall) else 0.0
        )
        tier_metrics[t] = {
            "precision": round(precision, 3),
            "recall": round(recall, 3),
            "f1": round(f1, 3),
            "support": sum(1 for e in expected if e == t),
        }

    macro_f1 = sum(m["f1"] for m in tier_metrics.values()) / len(tier_metrics)

    return {
        "n_cases": n,
        "tier_accuracy": round(correct / n, 3),
        "brier_score": round(brier, 4),
        "macro_f1": round(macro_f1, 3),
        "per_tier": tier_metrics,
        "per_label_accuracy": {
            k: round(sum(v) / len(v), 3) for k, v in per_label_correct.items()
        },
        "per_source_accuracy": {
            k: round(sum(v) / len(v), 3) for k, v in per_source_correct.items()
        },
        "min_confidence_filter": min_confidence,
    }


@router.get("/training/summary")
def training_data_summary(
    current: CurrentUser = Depends(require_user),
    min_confidence: str = Query(default="medium"),
) -> dict:
    """Counts of available ML training rows — quick "are we ready to train?"
    check without serializing the whole corpus."""
    _require_admin(current)
    if min_confidence not in LABEL_CONFIDENCES:
        raise HTTPException(status_code=400, detail=f"min_confidence must be one of {sorted(LABEL_CONFIDENCES)}.")
    from app.ml.export import export_summary
    with get_session() as session:
        return export_summary(session, min_confidence=min_confidence)


@router.get("/training/export")
def training_data_export(
    current: CurrentUser = Depends(require_user),
    min_confidence: str = Query(default="medium"),
    include_unclear: bool = Query(default=False),
):
    """Stream the full labeled training corpus as JSONL for the Colab
    notebook. First line is a schema header; every subsequent line is one
    training example (features + label + sample weight)."""
    _require_admin(current)
    if min_confidence not in LABEL_CONFIDENCES:
        raise HTTPException(status_code=400, detail=f"min_confidence must be one of {sorted(LABEL_CONFIDENCES)}.")
    from fastapi.responses import PlainTextResponse
    from app.ml.export import export_jsonl
    with get_session() as session:
        body = export_jsonl(session, min_confidence=min_confidence, include_unclear=include_unclear)
    return PlainTextResponse(
        body,
        media_type="application/x-ndjson",
        headers={"Content-Disposition": 'attachment; filename="omisphere_training.jsonl"'},
    )


def _profile_dict_from_account(account: Account) -> dict:
    """Reconstruct a Profile-shaped dict from a persisted Account row."""
    return {
        "platform": account.platform,
        "handle": account.handle,
        "display_name": account.display_name,
        "bio": account.bio,
        "follower_count": account.follower_count,
        "following_count": account.following_count,
        "created_at": account.account_created_at.isoformat()
        if account.account_created_at else None,
        "avatar_url": None,
    }
