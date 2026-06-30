"""Retrieval feedback — measurement that improves ranking, never scores (Sprint 014).

Records WHY a memory was retrieved and what happened to it: whether it influenced reasoning,
whether the Governor accepted the ruling that used it, and whether the analyst agreed. The
feedback is append-only and content-addressed; its aggregate (reuse count, usefulness rate, last
validated) is a **measurement** that nudges future retrieval **ranking only**. It never changes an
investigation's score, the Governor, OmiScore, or a memory's confidence.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.evidence.bundle import digest


@dataclass(frozen=True)
class RetrievalFeedback:
    """One feedback event for a retrieved memory. ``useful`` ⇔ it influenced reasoning AND the
    Governor accepted the ruling AND the analyst agreed."""

    ko_id: str
    investigation: str
    selected_because: str = ""
    influenced: bool = False
    governor_accepted: bool = False
    analyst_agreed: bool = False
    at: str = ""

    @property
    def id(self) -> str:
        return digest({
            "ko_id": self.ko_id, "investigation": self.investigation, "influenced": self.influenced,
            "governor_accepted": self.governor_accepted, "analyst_agreed": self.analyst_agreed,
            "at": self.at,
        }, prefix="rfb:")

    @property
    def useful(self) -> bool:
        return self.influenced and self.governor_accepted and self.analyst_agreed

    def to_dict(self) -> dict:
        return {
            "id": self.id, "ko_id": self.ko_id, "investigation": self.investigation,
            "selected_because": self.selected_because, "influenced": self.influenced,
            "governor_accepted": self.governor_accepted, "analyst_agreed": self.analyst_agreed,
            "at": self.at, "useful": self.useful,
        }


def aggregate_feedback(rows: list[RetrievalFeedback]) -> dict[str, dict]:
    """Per-knowledge-object feedback aggregate — deterministic. ``usefulness`` is the share of
    retrievals that were genuinely useful (influenced + governor-accepted + analyst-agreed)."""
    agg: dict[str, dict] = {}
    for fb in rows:
        a = agg.setdefault(fb.ko_id, {"reuse_count": 0, "useful": 0, "last_validated": None})
        a["reuse_count"] += 1
        if fb.useful:
            a["useful"] += 1
            if fb.at and (a["last_validated"] is None or fb.at > a["last_validated"]):
                a["last_validated"] = fb.at
    for a in agg.values():
        a["usefulness"] = round(a["useful"] / a["reuse_count"], 4) if a["reuse_count"] else 0.0
    return agg


def usefulness_map(rows: list[RetrievalFeedback]) -> dict[str, float]:
    """{ko_id: usefulness_rate} — the ranking signal fed to retrieval."""
    return {ko_id: a["usefulness"] for ko_id, a in aggregate_feedback(rows).items()}
