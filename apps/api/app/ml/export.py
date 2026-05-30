"""Build labeled training rows from the live database.

Joins ``AccountLabel`` → ``Account`` → most-recent ``Scan``, reconstructs the
engine's ScanResult from the persisted ``signals_json``, runs it through the
shared feature contract, and pairs the feature vector with the operator's
ground-truth label + expected tier.

The output is JSONL — one training example per line — which the Colab
notebook consumes directly. Nothing here imports heavy ML libraries; it's
pure stdlib + SQLAlchemy so it can run inside the API process or a one-off
script.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Iterator

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ml.features import FEATURE_NAMES, FEATURE_SCHEMA_VERSION, build_feature_vector
from app.schemas import Profile, ScanResult, SignalResult, Tier
from app.storage.models import Account, AccountLabel, Scan


# Map a categorical label → the binary "inauthentic" target most useful for
# the meta-classifier. ``expected_tier`` is the multi-class target. The label
# also rides along so the notebook can train an intent head if desired.
_INAUTHENTIC_LABELS = {
    "bot", "commercial_spam", "political_coord", "engagement_farm",
    "ai_content", "suspended",
}
_AUTHENTIC_LABELS = {"human"}

# Source provenance → a sample weight. YouTube's own moderation actions are
# the highest-quality ground truth; manual operator labels next; imported
# public-dataset rows are useful for volume but get down-weighted because
# they're cross-platform and noisier.
_SOURCE_WEIGHT = {
    "youtube_suspension": 1.5,
    "manual": 1.0,
    "imported_dataset": 0.6,
    # Synthetic rows are known-answer regression fixtures, not real signal.
    # They are excluded from training by default (see ``include_synthetic``);
    # the weight applies only when an operator deliberately opts them in.
    "synthetic": 0.3,
}


@dataclass
class TrainingRow:
    account_external_id: str
    platform: str
    label: str
    expected_tier: str
    inauthentic: int            # binary target: 1 inauthentic, 0 authentic, -1 unclear
    source: str
    label_confidence: str       # "high" | "medium"
    sample_weight: float
    features: list[float]
    # Raw comment text, newline-joined, for the DistilBERT text head. Empty
    # when no posts were retained for the account.
    text: str = ""


def _binary_target(label: str) -> int:
    if label in _INAUTHENTIC_LABELS:
        return 1
    if label in _AUTHENTIC_LABELS:
        return 0
    return -1  # "unclear" — kept for the multi-class head, dropped for binary


def _reconstruct_scan(scan_row: Scan, handle: str) -> ScanResult:
    """Rebuild a ScanResult from a persisted Scan row.

    Only the fields the feature contract reads are needed (signals + the two
    aggregate scalars), so we don't recompute summaries / intent.
    """
    signals = [SignalResult(**s) for s in (scan_row.signals_json or [])]
    return ScanResult(
        overall_probability=scan_row.overall_probability,
        confidence=scan_row.confidence,
        tier=Tier(scan_row.tier),
        signals=signals,
        summary="",
        subject=handle,
    )


_KNOWN_PLATFORMS = {"x", "youtube", "reddit", "telegram", "tiktok", "instagram", "unknown"}


def _profile_from_account(account: Account) -> Profile:
    # Account.platform is free text (e.g. "imported"); Profile.platform is a
    # constrained literal. Normalize anything unrecognized to "unknown".
    platform = account.platform if account.platform in _KNOWN_PLATFORMS else "unknown"
    return Profile(
        platform=platform,  # type: ignore[arg-type]
        handle=account.handle,
        display_name=account.display_name,
        bio=account.bio,
        follower_count=account.follower_count,
        following_count=account.following_count,
        created_at=account.account_created_at,
        verified=None,
    )


def iter_training_rows(
    session: Session,
    *,
    min_confidence: str = "medium",
    include_unclear: bool = False,
    include_synthetic: bool = False,
) -> Iterator[TrainingRow]:
    """Yield one TrainingRow per labeled account that has a persisted scan.

    Synthetic ground truth (``source="synthetic"``) is excluded by default: it
    is a deterministic regression fixture, and training a model on its toy
    distribution would teach shortcuts that don't transfer to real accounts.
    Pass ``include_synthetic=True`` only for deliberate experiments.
    """
    filters = []
    if min_confidence == "high":
        filters.append(AccountLabel.confidence == "high")
    if not include_synthetic:
        filters.append(AccountLabel.source != "synthetic")

    rows = session.execute(
        select(AccountLabel, Account)
        .join(Account, AccountLabel.account_id == Account.id)
        .where(*filters)
    ).all()

    for label_row, account in rows:
        scan_row = session.execute(
            select(Scan)
            .where(Scan.account_id == account.id)
            .order_by(Scan.scanned_at.desc())
            .limit(1)
        ).scalar_one_or_none()
        if scan_row is None:
            continue  # no scan → no features; don't fabricate

        binary = _binary_target(label_row.label)
        if binary == -1 and not include_unclear:
            continue

        scan = _reconstruct_scan(scan_row, account.handle)
        profile = _profile_from_account(account)
        # post_count isn't persisted per-scan; approximate from the temporal
        # detector's evidence is unreliable, so use 0 (the metadata block
        # degrades gracefully). The fingerprint already encodes cadence.
        features = build_feature_vector(scan, profile=profile, post_count=0)

        weight = _SOURCE_WEIGHT.get(label_row.source, 1.0)
        if label_row.confidence == "high":
            weight *= 1.25

        yield TrainingRow(
            account_external_id=account.external_id,
            platform=account.platform,
            label=label_row.label,
            expected_tier=label_row.expected_tier,
            inauthentic=binary,
            source=label_row.source,
            label_confidence=label_row.confidence,
            sample_weight=round(weight, 4),
            features=features,
            text="",
        )


def export_jsonl(session: Session, *, min_confidence: str = "medium",
                 include_unclear: bool = False,
                 include_synthetic: bool = False) -> str:
    """Return a JSONL string. First line is a header record describing the
    feature schema so the notebook can assert compatibility."""
    lines: list[str] = []
    header = {
        "_meta": True,
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "feature_names": FEATURE_NAMES,
        "n_features": len(FEATURE_NAMES),
    }
    lines.append(json.dumps(header))
    n = 0
    for row in iter_training_rows(session, min_confidence=min_confidence,
                                  include_unclear=include_unclear,
                                  include_synthetic=include_synthetic):
        lines.append(json.dumps(asdict(row)))
        n += 1
    return "\n".join(lines) + "\n"


def export_summary(session: Session, *, min_confidence: str = "medium",
                   include_synthetic: bool = False) -> dict:
    """Counts only — quick way to check whether there's enough data to train
    without serializing the whole corpus."""
    by_label: dict[str, int] = {}
    by_source: dict[str, int] = {}
    by_target = {"inauthentic": 0, "authentic": 0, "unclear": 0}
    total = 0
    for row in iter_training_rows(session, min_confidence=min_confidence, include_unclear=True,
                                  include_synthetic=include_synthetic):
        total += 1
        by_label[row.label] = by_label.get(row.label, 0) + 1
        by_source[row.source] = by_source.get(row.source, 0) + 1
        if row.inauthentic == 1:
            by_target["inauthentic"] += 1
        elif row.inauthentic == 0:
            by_target["authentic"] += 1
        else:
            by_target["unclear"] += 1
    return {
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "n_features": len(FEATURE_NAMES),
        "n_training_rows": total,
        "by_label": by_label,
        "by_source": by_source,
        "by_target": by_target,
        "ready_to_train": total >= 200 and by_target["inauthentic"] >= 50 and by_target["authentic"] >= 50,
    }
