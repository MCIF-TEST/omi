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


def coalesce_records(records: list[PublicRecord]) -> list[PublicRecord]:
    """Merge records that describe the same account into one.

    Per-row archives (information-operation disclosures are one row *per
    tweet*) yield many records sharing an ``external_id``. Persisting them
    one-by-one would make each overwrite the last, so an account ends up scored
    on a single post instead of its whole history. Coalescing first means the
    engine sees the account's full text corpus — the temporal and repetition
    detectors only have signal across multiple posts.

    Texts are unioned (order-preserving, de-duplicated, capped to keep a single
    pathological account from dominating). The first occurrence wins for the
    scalar profile/label fields; later occurrences only contribute text and
    fill in any profile field the first row left blank. Records with unique
    ids pass through untouched, so account-per-row datasets are a no-op.
    """
    _TEXT_CAP = 50
    merged: dict[str, PublicRecord] = {}
    order: list[str] = []
    for rec in records:
        key = rec.external_id
        if key not in merged:
            # Copy so we never mutate the caller's records.
            merged[key] = PublicRecord(
                external_id=rec.external_id,
                texts=list(dict.fromkeys(t for t in rec.texts if t and t.strip()))[:_TEXT_CAP],
                is_bot=rec.is_bot,
                follower_count=rec.follower_count,
                following_count=rec.following_count,
                account_age_days=rec.account_age_days,
                handle=rec.handle,
                label=rec.label,
                expected_tier=rec.expected_tier,
                campaign_id=rec.campaign_id,
            )
            order.append(key)
            continue
        acc = merged[key]
        for t in rec.texts:
            if t and t.strip() and t not in acc.texts and len(acc.texts) < _TEXT_CAP:
                acc.texts.append(t)
        # Backfill profile fields the first row left unset.
        if acc.follower_count is None:
            acc.follower_count = rec.follower_count
        if acc.following_count is None:
            acc.following_count = rec.following_count
        if acc.account_age_days is None:
            acc.account_age_days = rec.account_age_days
        if not acc.handle:
            acc.handle = rec.handle
    return [merged[k] for k in order]


def ingest_records(
    session: Session,
    records: list[PublicRecord],
    *,
    dataset_name: str = "public",
    label_confidence: str = "medium",
    user_id: int | None = None,
    allow_textless: bool = False,
    source: str = "imported_dataset",
) -> dict:
    """Run each public record through the real engine, persist the account +
    its scan + fingerprint, and attach a ground-truth label.

    Records sharing an ``external_id`` are coalesced first (see
    :func:`coalesce_records`) so a per-tweet archive becomes one account scored
    on its full post history.

    ``source`` tags the resulting :class:`AccountLabel` provenance. Real public
    archives use the default ``imported_dataset``; the synthetic regression
    corpus passes ``synthetic`` so it stays separable everywhere downstream and
    never silently inflates real-data calibration or training metrics.

    Returns counts. Idempotent per ``external_id`` within the imported
    platform namespace (re-running updates the same account rows).

    ``allow_textless`` lets behavioral-only account datasets (follower /
    following / age + label, no raw post text) through: the account is scored
    on its profile + metadata signals alone, with the text-based detectors
    abstaining (zero confidence). Without this flag such rows are skipped.
    """
    from app.storage.models import Account, AccountLabel

    records = coalesce_records(records)
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
                source=source,
                rationale=rationale,
            ))
        else:
            existing.label = label_kind
            existing.expected_tier = expected
            existing.source = source
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
