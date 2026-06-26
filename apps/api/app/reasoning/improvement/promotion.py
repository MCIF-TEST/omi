"""The promotion workflow (Sprint 011) — human-controlled, no automatic deployment.

A deterministic state machine over recommendations: ``candidate → recommended → approved →
production``, plus ``rejected`` and ``rolled_back``. The ``PromotionLedger`` records
recommendations and their transitions with an actor + note, maintaining an **append-only
history**. Critically, the ledger has **no side effects on the running system** — it records
decisions; applying a config change to production is a separate, deliberate human step. The
engine recommends; humans approve; nothing here ever changes production behavior.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

STATES = ("candidate", "recommended", "approved", "production", "rejected", "rolled_back")

# Allowed transitions. Promotion advances one step; rejection is always available pre-production;
# only a production entry can be rolled back. Terminal states have no outgoing transitions.
_TRANSITIONS: dict[str, set[str]] = {
    "candidate": {"recommended", "rejected"},
    "recommended": {"approved", "rejected"},
    "approved": {"production", "rejected"},
    "production": {"rolled_back"},
    "rejected": set(),
    "rolled_back": set(),
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class PromotionLedger:
    """Append-only record of recommendations + their human-driven state transitions."""

    def __init__(self) -> None:
        self._entries: dict[str, dict] = {}

    def record(self, recommendation: Any, *, state: str = "recommended") -> dict:
        """Add a recommendation (idempotent by its content-addressed id). Records initial state
        + a history entry. Does not change any production config."""
        rec = recommendation.to_dict() if hasattr(recommendation, "to_dict") else dict(recommendation)
        rid = rec["id"]
        if rid not in self._entries:
            self._entries[rid] = {
                "recommendation": rec, "state": state,
                "history": [{"to": state, "actor": "engine", "note": "recorded", "at": _now()}],
            }
        return self._entries[rid]

    def transition(self, rec_id: str, to_state: str, *, actor: str, note: str = "") -> dict:
        """Advance a recommendation's state (human-driven). Validates the transition; raises on an
        illegal move. ``actor`` is required — promotions are attributable, never automatic."""
        if rec_id not in self._entries:
            raise KeyError(f"unknown recommendation {rec_id!r}")
        if to_state not in STATES:
            raise ValueError(f"unknown state {to_state!r}")
        if not actor:
            raise ValueError("an actor is required: promotions are human-controlled")
        current = self._entries[rec_id]["state"]
        if to_state not in _TRANSITIONS.get(current, set()):
            raise ValueError(f"illegal transition {current!r} -> {to_state!r}")
        self._entries[rec_id]["state"] = to_state
        self._entries[rec_id]["history"].append(
            {"from": current, "to": to_state, "actor": actor, "note": note, "at": _now()}
        )
        return self._entries[rec_id]

    def reject(self, rec_id: str, *, actor: str, note: str = "") -> dict:
        return self.transition(rec_id, "rejected", actor=actor, note=note)

    def get(self, rec_id: str) -> dict | None:
        return self._entries.get(rec_id)

    def state(self, rec_id: str) -> str | None:
        entry = self._entries.get(rec_id)
        return entry["state"] if entry else None

    def history(self, rec_id: str) -> list[dict]:
        entry = self._entries.get(rec_id)
        return list(entry["history"]) if entry else []

    def all(self, *, state: str | None = None) -> list[dict]:
        entries = sorted(self._entries.values(), key=lambda e: e["recommendation"]["id"])
        return [e for e in entries if state is None or e["state"] == state]

    def summary(self) -> dict:
        counts: dict[str, int] = {s: 0 for s in STATES}
        for e in self._entries.values():
            counts[e["state"]] = counts.get(e["state"], 0) + 1
        return {"total": len(self._entries), "by_state": counts}
