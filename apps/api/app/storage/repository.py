"""High-level repository helpers around the SQLAlchemy models.

Keeps SQL out of the engine + route layers and makes the cache / similarity
operations easy to mock in tests.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.schemas import Profile, ScanResult
from app.storage.models import Account, CommenterEngagement, Scan, VideoScan


class AccountRepository:
    def __init__(self, session: Session):
        self.session = session

    # ---- Account lookups ----

    def get(self, platform: str, external_id: str) -> Account | None:
        stmt = select(Account).where(
            Account.platform == platform, Account.external_id == external_id
        )
        return self.session.execute(stmt).scalar_one_or_none()

    def all_with_fingerprints(self) -> list[Account]:
        """Return every account that has a fingerprint vector. Brute-force
        nearest-neighbor source; swap for pgvector when the table grows."""
        stmt = select(Account).where(Account.fingerprint_json.is_not(None))
        return list(self.session.execute(stmt).scalars())

    # ---- Investigations ----  (Phase 5)

    def create_investigation(
        self,
        *,
        user_id: int,
        slug: str,
        label: str,
        input_url: str,
        target_id: str | None,
        kind: str,
        overall_probability: float,
        overall_tier: str,
        summary: str,
        quota_used: int,
        payload_json: dict,
    ):
        from app.storage.models import Investigation
        inv = Investigation(
            user_id=user_id,
            slug=slug,
            label=label[:280],
            input_url=input_url[:500],
            target_id=target_id,
            kind=kind,
            overall_probability=overall_probability,
            overall_tier=overall_tier,
            summary=summary,
            quota_used=quota_used,
            payload_json=payload_json,
            batch_count=1,
        )
        self.session.add(inv)
        self.session.flush()
        return inv

    def list_user_investigations(self, user_id: int, limit: int = 50):
        from app.storage.models import Investigation
        stmt = (
            select(Investigation)
            .where(Investigation.user_id == user_id)
            .order_by(Investigation.created_at.desc())
            .limit(limit)
        )
        return list(self.session.execute(stmt).scalars())

    def get_investigation(self, slug: str, user_id: int | None = None):
        from app.storage.models import Investigation
        stmt = select(Investigation).where(Investigation.slug == slug)
        if user_id is not None:
            stmt = stmt.where(Investigation.user_id == user_id)
        return self.session.execute(stmt).scalar_one_or_none()

    def update_investigation_payload(
        self, inv, *, payload_json: dict, quota_used_delta: int = 0,
        overall_probability: float | None = None,
        overall_tier: str | None = None,
        summary: str | None = None,
    ):
        from datetime import datetime, timezone
        inv.payload_json = payload_json
        inv.quota_used = (inv.quota_used or 0) + quota_used_delta
        inv.batch_count = (inv.batch_count or 1) + 1
        if overall_probability is not None:
            inv.overall_probability = overall_probability
        if overall_tier is not None:
            inv.overall_tier = overall_tier
        if summary is not None:
            inv.summary = summary
        inv.updated_at = datetime.now(timezone.utc)
        return inv

    # ---- Scan history ----

    def account_history(
        self, platform: str, external_id: str, *, limit: int = 50
    ) -> tuple[Account | None, list[Scan]]:
        """Return the account row + all stored scans (newest first, capped).

        Backs the /v1/accounts/{platform}/{external_id}/history endpoint —
        callers use this to compute trend (rising/falling/stable/volatile)
        over an account's lifetime.
        """
        account = self.get(platform, external_id)
        if account is None:
            return None, []
        stmt = (
            select(Scan)
            .where(Scan.account_id == account.id)
            .order_by(Scan.scanned_at.desc())
            .limit(limit)
        )
        scans = list(self.session.execute(stmt).scalars())
        return account, scans

    # ---- Cache check ----

    def cached_scan_within(
        self, platform: str, external_id: str, ttl_days: int
    ) -> tuple[Account, Scan] | None:
        account = self.get(platform, external_id)
        if account is None or account.last_scanned_at is None:
            return None
        # SQLite strips tzinfo on round-trip; treat stored timestamps as UTC.
        last = account.last_scanned_at
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        if last < datetime.now(timezone.utc) - timedelta(days=ttl_days):
            return None
        latest = (
            self.session.execute(
                select(Scan)
                .where(Scan.account_id == account.id)
                .order_by(Scan.scanned_at.desc())
                .limit(1)
            )
            .scalars()
            .first()
        )
        if latest is None:
            return None
        return account, latest

    # ---- Upsert ----

    def upsert_with_scan(
        self,
        *,
        platform: str,
        external_id: str,
        profile: Profile,
        scan: ScanResult,
        fingerprint: list[float] | None,
    ) -> tuple[Account, Scan]:
        account = self.get(platform, external_id)
        now = datetime.now(timezone.utc)
        if account is None:
            account = Account(
                platform=platform,
                external_id=external_id,
                handle=profile.handle,
                display_name=profile.display_name,
                bio=profile.bio,
                follower_count=profile.follower_count,
                following_count=profile.following_count,
                account_created_at=profile.created_at,
                first_seen_at=now,
            )
            self.session.add(account)
            self.session.flush()  # populate account.id
        else:
            # Keep the latest snapshot of mutable fields.
            account.handle = profile.handle
            account.display_name = profile.display_name
            account.bio = profile.bio
            account.follower_count = profile.follower_count
            account.following_count = profile.following_count
            account.account_created_at = profile.created_at

        account.last_scanned_at = now
        account.last_score = scan.overall_probability
        account.last_tier = scan.tier.value
        account.last_confidence = scan.confidence
        account.fingerprint_json = fingerprint

        scan_row = Scan(
            account_id=account.id,
            scanned_at=now,
            overall_probability=scan.overall_probability,
            confidence=scan.confidence,
            tier=scan.tier.value,
            summary=scan.summary,
            signals_json=[_signal_to_dict(s) for s in scan.signals],
        )
        self.session.add(scan_row)
        self.session.flush()
        return account, scan_row

    # ---- Video scans ----

    def record_video_scan(
        self,
        *,
        platform: str,
        video_id: str,
        commenter_count: int,
        fresh_count: int,
        cached_count: int,
        quota_used: int,
        tier_counts: dict[str, int],
        coordination_score: float | None = None,
    ) -> VideoScan:
        row = VideoScan(
            platform=platform,
            video_id=video_id,
            commenter_count=commenter_count,
            fresh_count=fresh_count,
            cached_count=cached_count,
            quota_used=quota_used,
            high_count=tier_counts.get("high", 0),
            elevated_count=tier_counts.get("elevated", 0),
            moderate_count=tier_counts.get("moderate", 0),
            low_count=tier_counts.get("low", 0),
            coordination_score=coordination_score,
        )
        self.session.add(row)
        self.session.flush()
        return row

    # ---- Co-engagement edges (for the "fellow travelers" detector) ----

    def record_engagement_edges(
        self,
        *,
        platform: str,
        account_external_id: str,
        parent_ids: list[str],
    ) -> int:
        """Upsert (account, parent_id) edges. Returns how many were new.

        Uses sqlite's ``INSERT OR IGNORE`` semantics for portability; the
        same conflict on Postgres is handled by the unique constraint and
        ``ON CONFLICT DO NOTHING`` (handled by sqlalchemy generically).
        """
        unique_parents = sorted({p for p in parent_ids if p})
        if not unique_parents:
            return 0
        inserted = 0
        for pid in unique_parents:
            stmt = sqlite_insert(CommenterEngagement).values(
                platform=platform,
                account_external_id=account_external_id,
                parent_id=pid,
            ).on_conflict_do_nothing(
                index_elements=["platform", "account_external_id", "parent_id"]
            )
            result = self.session.execute(stmt)
            inserted += result.rowcount or 0
        return inserted

    def load_engagement_sets(
        self, *, platform: str, account_external_ids: list[str]
    ) -> dict[str, set[str]]:
        if not account_external_ids:
            return {}
        stmt = select(CommenterEngagement).where(
            CommenterEngagement.platform == platform,
            CommenterEngagement.account_external_id.in_(account_external_ids),
        )
        out: dict[str, set[str]] = defaultdict(set)
        for row in self.session.execute(stmt).scalars():
            out[row.account_external_id].add(row.parent_id)
        return dict(out)


def _signal_to_dict(signal: Any) -> dict[str, Any]:
    # Use Pydantic's dump so we keep schema fidelity (sub_signals included).
    return signal.model_dump() if hasattr(signal, "model_dump") else dict(signal)
