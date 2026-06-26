"""PostgreSQL-backed memory store (Sprint 012).

Implements the same interface as the in-memory ``MemoryStore`` (Sprint 005), so the Memory
Analyst, the extractor, and ``retrieve`` work against it **unchanged** — the Council never knows
whether memory lives in Postgres, Supabase, or RAM. Persistence is **append-only** (observations
are inserted, never updated or deleted; supersession is a status flag), and every read
reconstructs the Sprint-005 **domain** ``KnowledgeObject`` so confidence / contradiction /
epistemic status are recomputed from the ledger — never read from a stored column. Signature
tokens are indexed for candidate lookup at scale.
"""
from __future__ import annotations

from typing import Any, Callable, Iterable

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.storage.models import (
    KnowledgeObjectRow,
    KnowledgeObjectSignatureRow,
    MemoryRevisionRow,
    ObservationLedgerRow,
)

from .objects import KnowledgeObject, ObservationLedgerEntry
from .retrieval import bundle_signature
from .store import jaccard

SessionFactory = Callable[[], Any]   # a context manager yielding a Session


def _to_domain(row: KnowledgeObjectRow, session: Session) -> KnowledgeObject:
    """Reconstruct the Sprint-005 domain object so all constitutional logic runs unchanged."""
    entries = [
        ObservationLedgerEntry(
            investigation=o.investigation, stance=o.stance, evidence_refs=list(o.evidence_refs or []),
            independence_key=o.independence_key or "", at=o.at or "", human_anchor=o.human_anchor,
            memory_influence=o.memory_influence or "none",
        )
        for o in sorted(row.observations, key=lambda x: x.seq)
    ]
    revs = session.execute(
        select(MemoryRevisionRow).where(MemoryRevisionRow.ko_id == row.id).order_by(MemoryRevisionRow.rev)
    ).scalars().all()
    return KnowledgeObject(
        id=row.id, type=row.type, family=row.family, label=row.label,
        signature=list(row.signature or []), attributes=dict(row.attributes or {}), ledger=entries,
        is_control=bool(row.is_control), influence_class=row.influence_class,
        superseded_by=row.superseded_by, half_life_days=row.half_life_days,
        retirement_floor=row.retirement_floor,
        version_history=[{"rev": r.rev, "change": r.change, "at": r.at, "investigation": r.investigation}
                         for r in revs],
        platform_scope=list(row.platform_scope or []),
    )


class PostgresMemoryStore:
    """Durable, append-only memory store backed by a SQLAlchemy session factory."""

    def __init__(self, session_factory: SessionFactory) -> None:
        self._sf = session_factory

    # -- read ----------------------------------------------------------------- #
    def _load(self, session: Session, where) -> list[KnowledgeObject]:
        rows = session.execute(
            select(KnowledgeObjectRow).where(where)
            .options(selectinload(KnowledgeObjectRow.observations))
            .order_by(KnowledgeObjectRow.id)
        ).scalars().all()
        return [_to_domain(r, session) for r in rows]

    def get(self, ko_id: str) -> KnowledgeObject | None:
        with self._sf() as s:
            objs = self._load(s, KnowledgeObjectRow.id == ko_id)
            return objs[0] if objs else None

    def all(self, *, include_superseded: bool = False) -> list[KnowledgeObject]:
        with self._sf() as s:
            where = func.coalesce(KnowledgeObjectRow.superseded_by, "") == "" if not include_superseded \
                else KnowledgeObjectRow.id.isnot(None)
            return self._load(s, where)

    def __len__(self) -> int:
        with self._sf() as s:
            return int(s.execute(select(func.count()).select_from(KnowledgeObjectRow)).scalar() or 0)

    # -- typed + similarity lookups (deterministic retrieval seams) ----------- #
    def candidates_for(self, bundle: Any) -> list[KnowledgeObject]:
        """Narrow to non-superseded objects sharing a signature token with the bundle — the
        index-assisted candidate set ``retrieve`` then scores. Equivalent to ranking all objects
        (any match with containment >= threshold shares >= 1 token), but scalable."""
        tokens = bundle_signature(bundle)
        if not tokens:
            return []
        with self._sf() as s:
            ids = list(s.execute(
                select(KnowledgeObjectSignatureRow.ko_id)
                .where(KnowledgeObjectSignatureRow.token.in_(tokens)).distinct()
            ).scalars().all())
            if not ids:
                return []
            return self._load(s, (KnowledgeObjectRow.id.in_(ids))
                              & (func.coalesce(KnowledgeObjectRow.superseded_by, "") == ""))

    def find_by_type(self, type_: str) -> list[KnowledgeObject]:
        with self._sf() as s:
            return self._load(s, (KnowledgeObjectRow.type == type_)
                              & (func.coalesce(KnowledgeObjectRow.superseded_by, "") == ""))

    def find_controls(self) -> list[KnowledgeObject]:
        with self._sf() as s:
            return self._load(s, (KnowledgeObjectRow.is_control.is_(True))
                              & (func.coalesce(KnowledgeObjectRow.superseded_by, "") == ""))

    def find_contradicted(self) -> list[KnowledgeObject]:
        with self._sf() as s:
            ids = list(s.execute(
                select(ObservationLedgerRow.ko_id).where(ObservationLedgerRow.stance == "contradicts").distinct()
            ).scalars().all())
            if not ids:
                return []
            return self._load(s, (KnowledgeObjectRow.id.in_(ids))
                              & (func.coalesce(KnowledgeObjectRow.superseded_by, "") == ""))

    # -- write (append-only, transactional) ----------------------------------- #
    def ingest(
        self, *, candidate: dict, investigation: str, stance: str, evidence_refs: list[str],
        independence_key: str, at: str, human_anchor: dict | None = None,
        memory_influence: str = "none", match_threshold: float = 0.5,
    ) -> KnowledgeObject:
        """Evidence-gated write path (mirrors the in-memory store). Match by type + signature
        Jaccard else create, then append the observation. One transaction; no LLM write source."""
        with self._sf() as s:
            row = self._best_match(s, candidate["type"], candidate.get("signature", []), match_threshold)
            if row is None:
                row = self._create(s, candidate)
            self._observe(s, row, investigation, stance, evidence_refs, independence_key, at,
                          human_anchor, memory_influence)
            s.flush()
            return _to_domain(row, s)

    def supersede(self, old_id: str, new_id: str) -> None:
        with self._sf() as s:
            row = s.get(KnowledgeObjectRow, old_id)
            if row is not None:
                row.superseded_by = new_id
                self._revision(s, old_id, f"superseded_by:{new_id}")

    # -- helpers -------------------------------------------------------------- #
    def _new_id(self, s: Session, type_: str) -> str:
        n = int(s.execute(select(func.count()).select_from(KnowledgeObjectRow)).scalar() or 0)
        return f"ko:{type_.lower()}:{n + 1:04d}"

    def _create(self, s: Session, candidate: dict) -> KnowledgeObjectRow:
        is_control = bool(candidate.get("is_control", False))
        row = KnowledgeObjectRow(
            id=self._new_id(s, candidate["type"]), type=candidate["type"],
            family=candidate.get("family", "patterns_signatures"),
            label=candidate.get("label", candidate["type"]),
            signature=list(candidate.get("signature", [])), attributes=candidate.get("attributes") or {},
            is_control=is_control,
            influence_class=("exculpatory" if is_control else candidate.get("influence_class", "context")),
            platform_scope=list(candidate.get("platform_scope") or []),
        )
        s.add(row)
        for token in dict.fromkeys(candidate.get("signature", [])):
            s.add(KnowledgeObjectSignatureRow(ko_id=row.id, token=token))
        s.add(MemoryRevisionRow(ko_id=row.id, rev=1, change="created"))
        s.flush()
        return row

    def _observe(self, s, row, investigation, stance, evidence_refs, independence_key, at,
                 human_anchor, memory_influence) -> None:
        seq = int(s.execute(select(func.count()).select_from(ObservationLedgerRow)
                            .where(ObservationLedgerRow.ko_id == row.id)).scalar() or 0) + 1
        s.add(ObservationLedgerRow(
            ko_id=row.id, seq=seq, investigation=investigation, stance=stance,
            evidence_refs=list(evidence_refs), independence_key=independence_key, at=at,
            human_anchor=human_anchor, memory_influence=memory_influence,
        ))
        self._revision(s, row.id, f"observed:{stance}", investigation=investigation, at=at)

    def _revision(self, s, ko_id, change, *, investigation=None, at=None) -> None:
        rev = int(s.execute(select(func.count()).select_from(MemoryRevisionRow)
                            .where(MemoryRevisionRow.ko_id == ko_id)).scalar() or 0) + 1
        s.add(MemoryRevisionRow(ko_id=ko_id, rev=rev, change=change, investigation=investigation, at=at))

    def _best_match(self, s, type_: str, signature: Iterable[str], threshold: float) -> KnowledgeObjectRow | None:
        sig = list(dict.fromkeys(signature))
        if sig:
            ids = list(s.execute(
                select(KnowledgeObjectSignatureRow.ko_id)
                .where(KnowledgeObjectSignatureRow.token.in_(sig)).distinct()
            ).scalars().all())
            if not ids:
                return None
            where = (KnowledgeObjectRow.type == type_) & (KnowledgeObjectRow.id.in_(ids)) \
                & (func.coalesce(KnowledgeObjectRow.superseded_by, "") == "")
        else:
            where = (KnowledgeObjectRow.type == type_) & (func.coalesce(KnowledgeObjectRow.superseded_by, "") == "")
        rows = s.execute(select(KnowledgeObjectRow).where(where).order_by(KnowledgeObjectRow.id)).scalars().all()
        best: KnowledgeObjectRow | None = None
        best_j = threshold
        for r in rows:
            j = jaccard(r.signature, signature)
            if j >= best_j:
                best_j, best = j, r
        return best
