"""High-level monitoring API used by routes + the scheduler."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.monitoring.anomalies import (
    AnomalyHit, alert_already_open, detect_high_tier_surge, detect_narrative_spikes,
)
from app.storage.models import Alert, Watchlist


_TIER_RANK = {"low": 1, "moderate": 2, "elevated": 3, "high": 4}


@dataclass
class TickReport:
    anomalies_found: int
    alerts_written: int
    watchlists_checked: int
    watchlists_alerted: int


class MonitoringService:
    def __init__(self, session: Session, settings: Settings | None = None):
        self.session = session
        self.settings = settings or get_settings()

    # ---- Read API -----------------------------------------------------

    def recent_feed(self, *, hours: int = 24, limit: int = 30) -> list[Alert]:
        """All recent alerts — global + per-user — newest first.

        Callers filter by user in their route handler if multi-tenant.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        return list(self.session.execute(
            select(Alert)
            .where(Alert.created_at >= cutoff)
            .order_by(Alert.created_at.desc())
            .limit(limit)
        ).scalars())

    def user_alerts(self, user_id: int, *, unread_only: bool = False,
                    limit: int = 50) -> list[Alert]:
        stmt = (
            select(Alert)
            .where((Alert.user_id == user_id) | (Alert.user_id.is_(None)))
            .order_by(Alert.created_at.desc())
            .limit(limit)
        )
        rows = list(self.session.execute(stmt).scalars())
        if unread_only:
            rows = [r for r in rows if r.read_at is None]
        return rows

    def unread_count(self, user_id: int) -> int:
        return sum(1 for _ in self.user_alerts(user_id, unread_only=True))

    def mark_read(self, alert_id: int, user_id: int) -> bool:
        a = self.session.get(Alert, alert_id)
        if a is None:
            return False
        # Only owner (or recipient of a broadcast) can mark read.
        if a.user_id is not None and a.user_id != user_id:
            return False
        if a.read_at is None:
            a.read_at = datetime.now(timezone.utc)
        return True

    # ---- Anomaly pass -------------------------------------------------

    def run_anomaly_pass(self) -> TickReport:
        """Detect anomalies and persist as Alert rows. Idempotent within
        a short window (won't double-alert the same entity)."""
        hits: list[AnomalyHit] = []
        hits.extend(detect_narrative_spikes(self.session, settings=self.settings))
        hits.extend(detect_high_tier_surge(self.session, settings=self.settings))

        written = 0
        for hit in hits:
            # Dedup key per anomaly kind
            if hit.kind == "narrative_spike":
                if alert_already_open(
                    self.session, "narrative_spike",
                    "narrative_id", hit.payload.get("narrative_id"),
                    within_minutes=120,
                ):
                    continue
            elif hit.kind == "high_tier_surge":
                if alert_already_open(
                    self.session, "high_tier_surge",
                    "last_hour", hit.payload.get("last_hour"),
                    within_minutes=60,
                ):
                    continue
            self.session.add(Alert(
                user_id=None,
                kind=hit.kind,
                severity=hit.severity,
                message=hit.message,
                payload_json=hit.payload,
            ))
            written += 1
        return TickReport(
            anomalies_found=len(hits),
            alerts_written=written,
            watchlists_checked=0,
            watchlists_alerted=0,
        )

    # ---- Watchlists ---------------------------------------------------

    def add_watchlist(
        self, *, user_id: int, kind: str, target_id: str,
        label: str = "", alert_threshold_tier: str = "moderate",
    ) -> Watchlist:
        # Idempotent: same (user_id, kind, target_id) returns existing.
        existing = self.session.execute(
            select(Watchlist).where(
                Watchlist.user_id == user_id,
                Watchlist.kind == kind,
                Watchlist.target_id == target_id,
            )
        ).scalar_one_or_none()
        if existing is not None:
            return existing
        w = Watchlist(
            user_id=user_id,
            kind=kind,
            target_id=target_id,
            label=label or target_id,
            alert_threshold_tier=alert_threshold_tier,
        )
        self.session.add(w)
        self.session.flush()
        return w

    def list_watchlists(self, user_id: int) -> list[Watchlist]:
        return list(self.session.execute(
            select(Watchlist).where(Watchlist.user_id == user_id)
            .order_by(Watchlist.created_at.desc())
        ).scalars())

    def delete_watchlist(self, *, watchlist_id: int, user_id: int) -> bool:
        w = self.session.get(Watchlist, watchlist_id)
        if w is None or w.user_id != user_id:
            return False
        self.session.delete(w)
        return True

    def note_observation(
        self,
        *,
        kind: str,
        target_id: str,
        current_tier: str,
        current_probability: float,
        platform: str = "youtube",
    ) -> int:
        """Update any matching watchlists with the latest tier; fire alert
        if it crossed the threshold or changed direction. Called after a
        manual scan, so users see watchlist alerts immediately.

        Returns count of alerts created.
        """
        rows = list(self.session.execute(
            select(Watchlist).where(
                Watchlist.kind == kind,
                Watchlist.target_id == target_id,
            )
        ).scalars())
        if not rows:
            return 0

        now = datetime.now(timezone.utc)
        cur_rank = _TIER_RANK.get(current_tier, 0)
        alerts = 0
        for w in rows:
            prev_tier = w.last_seen_tier
            _TIER_RANK.get(prev_tier or "low", 0)
            threshold_rank = _TIER_RANK.get(w.alert_threshold_tier, 2)
            # Fire if tier changed AND current is at-or-above threshold
            if prev_tier != current_tier and cur_rank >= threshold_rank:
                msg = _build_change_message(
                    target_id=target_id,
                    label=w.label,
                    prev=prev_tier,
                    current=current_tier,
                    prob=current_probability,
                )
                self.session.add(Alert(
                    user_id=w.user_id,
                    watchlist_id=w.id,
                    kind="tier_change",
                    severity=current_tier if current_tier in ("moderate", "elevated", "high") else "info",
                    message=msg,
                    payload_json={
                        "target_id": target_id,
                        "kind": kind,
                        "previous_tier": prev_tier,
                        "current_tier": current_tier,
                        "current_probability": current_probability,
                    },
                ))
                w.last_alert_at = now
                alerts += 1
            w.last_seen_tier = current_tier
            w.last_seen_probability = current_probability
            w.last_checked_at = now
        return alerts


def _build_change_message(*, target_id, label, prev, current, prob) -> str:
    if prev is None:
        return (
            f"{label} first observed at {current.upper()} tier "
            f"({int(round(prob * 100))}% probability)."
        )
    return (
        f"{label} tier changed: {prev.upper()} → {current.upper()} "
        f"({int(round(prob * 100))}% probability)."
    )
