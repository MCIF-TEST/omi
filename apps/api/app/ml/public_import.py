"""Bootstrap labels from a public bot dataset.

The chosen strategy: use a public (mostly Twitter) bot dataset as a baseline,
then *apply the same behavioral principles to YouTube in a practical manner*.
We do that by NOT importing platform-specific quirks (Twitter retweet
mechanics, @-mention graphs) and instead reducing every public row to the
platform-agnostic behavioral signals OMISPHERE already models: the account's
posts (text) and profile shape (followers/following/age). We then run those
through the real detector engine, so the imported account gets a genuine
fingerprint + detector outputs in the *same* feature space as live YouTube
scans. The public label rides along as ground truth tagged
``source="imported_dataset"`` and down-weighted at train time.

Expected input: a CSV/JSONL where each row has at least
  * a text field (one representative post, or several joined by newlines)
  * a binary bot/human label
and optionally follower/following/age columns.

This module is import-format-agnostic: the caller maps their dataset's column
names to the canonical keys below, then calls :func:`ingest_records`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.detection.engine import analyze_account
from app.memory.fingerprint import extract_fingerprint
from app.schemas import Post, Profile
from app.storage.repository import AccountRepository

_log = logging.getLogger("omi.ml.public_import")

_IMPORT_PLATFORM = "imported"


@dataclass
class PublicRecord:
    """One row from a public dataset, reduced to platform-agnostic fields.

    The binary ``is_bot`` flag is the lowest-common-denominator label every
    public dataset carries. Richer corpora (coordinated influence-operation
    archives, the synthetic persona generator) additionally set ``label`` and
    ``expected_tier`` to assert a *specific* ground-truth category — e.g. a
    state-backed amplifier is ``political_coord``/``high``, while a genuine
    non-native-English commenter is ``human``/``low`` even though a naive bot
    detector might mistake their phrasing for automation. When ``label`` /
    ``expected_tier`` are unset they fall back to the ``is_bot`` mapping, so the
    existing binary datasets keep working unchanged.
    """
    external_id: str            # stable id from the source dataset
    texts: list[str]            # one or more posts authored by the account
    is_bot: bool                # the source's ground-truth label
    follower_count: int | None = None
    following_count: int | None = None
    account_age_days: int | None = None
    handle: str | None = None
    # Optional explicit ground truth — overrides the is_bot-derived defaults.
    label: str | None = None            # one of schemas.LABEL_KINDS
    expected_tier: str | None = None    # one of "low|moderate|elevated|high"
    # Provenance for coordinated-operation rows: which campaign this account
    # belongs to. Recorded in the label rationale so the corpus stays auditable.
    campaign_id: str | None = None


def _to_profile(rec: PublicRecord) -> Profile:
    created = None
    if rec.account_age_days is not None:
        created = datetime.now(timezone.utc) - timedelta(days=max(0, rec.account_age_days))
    return Profile(
        # Profile.platform is a constrained literal; "imported" isn't a real
        # platform, so present it as "unknown" to the engine. The persisted
        # Account row keeps the "imported" namespace (a free-text column).
        platform="unknown",
        handle=rec.handle or rec.external_id,
        follower_count=rec.follower_count,
        following_count=rec.following_count,
        created_at=created,
    )


def _to_posts(rec: PublicRecord) -> list[Post]:
    base = datetime.now(timezone.utc) - timedelta(days=30)
    posts: list[Post] = []
    for i, text in enumerate(rec.texts):
        if not text or not text.strip():
            continue
        posts.append(Post(
            id=f"{rec.external_id}:{i}",
            author_handle=rec.handle or rec.external_id,
            text=text.strip(),
            # Spread synthetic timestamps so the temporal detector has
            # something to chew on without implying a real cadence.
            created_at=base + timedelta(hours=i),
        ))
    return posts


def _expected_tier(is_bot: bool) -> str:
    return "high" if is_bot else "low"


def _label_kind(is_bot: bool) -> str:
    return "bot" if is_bot else "human"


# Valid value sets, imported lazily-by-reference to avoid a heavy schemas import
# at module load. Populated on first use by _resolve_ground_truth.
_VALID_TIERS = ("low", "moderate", "elevated", "high")


def _resolve_ground_truth(rec: "PublicRecord") -> tuple[str, str]:
    """Decide the (label_kind, expected_tier) this record asserts.

    Honors an explicit ``rec.label`` / ``rec.expected_tier`` when present and
    valid, otherwise falls back to the binary ``is_bot`` mapping. Invalid
    explicit values are rejected loudly rather than silently poisoning the
    ground-truth corpus — a typo'd label is worse than no label.
    """
    from app.schemas import LABEL_KINDS

    label_kind = rec.label if rec.label is not None else _label_kind(rec.is_bot)
    expected = rec.expected_tier if rec.expected_tier is not None else _expected_tier(rec.is_bot)
    if label_kind not in LABEL_KINDS:
        raise ValueError(
            f"PublicRecord.label='{label_kind}' is not a valid label kind "
            f"(expected one of {sorted(LABEL_KINDS)})."
        )
    if expected not in _VALID_TIERS:
        raise ValueError(
            f"PublicRecord.expected_tier='{expected}' is not a valid tier "
            f"(expected one of {list(_VALID_TIERS)})."
        )
    return label_kind, expected


def ingest_records(
    session: Session,
    records: list[PublicRecord],
    *,
    dataset_name: str = "public",
    label_confidence: str = "medium",
    user_id: int | None = None,
    allow_textless: bool = False,
) -> dict:
    """Run each public record through the real engine, persist the account +
    its scan + fingerprint, and attach an ``imported_dataset`` label.

    Returns counts. Idempotent per ``external_id`` within the imported
    platform namespace (re-running updates the same account rows).

    ``allow_textless`` lets behavioral-only account datasets (follower /
    following / age + label, no raw post text) through: the account is scored
    on its profile + metadata signals alone, with the text-based detectors
    abstaining (zero confidence). Without this flag such rows are skipped.
    """
    from app.storage.models import Account, AccountLabel

    repo = AccountRepository(session)
    n_ok = 0
    n_skipped = 0
    n_bot = 0

    for rec in records:
        posts = _to_posts(rec)
        if not posts and not allow_textless:
            n_skipped += 1
            continue
        profile = _to_profile(rec)
        scan = analyze_account(profile, posts)
        fp = extract_fingerprint(scan)

        ext_id = f"{dataset_name}:{rec.external_id}"
        repo.upsert_with_scan(
            platform=_IMPORT_PLATFORM,
            external_id=ext_id,
            profile=profile,
            scan=scan,
            fingerprint=fp,
        )

        account = session.query(Account).filter(
            Account.platform == _IMPORT_PLATFORM,
            Account.external_id == ext_id,
        ).first()
        if account is None:
            n_skipped += 1
            continue

        label_kind, expected = _resolve_ground_truth(rec)
        rationale = f"Imported from public dataset '{dataset_name}'."
        if rec.campaign_id:
            rationale += f" Campaign: {rec.campaign_id}."

        existing = session.query(AccountLabel).filter(
            AccountLabel.account_id == account.id,
            AccountLabel.user_id == user_id,
        ).first()
        if existing is None:
            session.add(AccountLabel(
                account_id=account.id,
                user_id=user_id,
                label=label_kind,
                expected_tier=expected,
                confidence=label_confidence,
                source="imported_dataset",
                rationale=rationale,
            ))
        else:
            existing.label = label_kind
            existing.expected_tier = expected
            existing.source = "imported_dataset"
            existing.rationale = rationale

        n_ok += 1
        # "bot" in the count sense = any inauthentic ground truth, not just the
        # literal "bot" label — so coordinated/spam/farm rows count too.
        if rec.is_bot or expected in ("elevated", "high"):
            n_bot += 1

    return {
        "ingested": n_ok,
        "skipped_no_text": n_skipped,
        "bots": n_bot,
        "humans": n_ok - n_bot,
        "dataset": dataset_name,
    }
