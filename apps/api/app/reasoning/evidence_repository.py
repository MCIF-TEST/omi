"""The Evidence Repository (frozen architecture) — the ONE read-facade for investigation evidence.

The Repository is the single place the reasoning path reads evidence. It owns evidence and the
relationships between it; it performs NO reasoning, computes no score, calls no model, and writes
nothing. It composes an immutable, content-addressed :class:`EvidenceSnapshot` — an ephemeral
projection of the durable stores (the scan payload, the canonical Evidence Bundle, institutional
memory) — that the reasoning path consumes. Only the snapshot's ``snapshot_id`` is durable (recorded
into the forensic manifest for traceability); the snapshot body itself is ephemeral.

Simplicity is a requirement: the snapshot is an immutable projection, NOT a behavioral subsystem. The
Repository adds no new store — durability stays in the stores it reads. It never learns; writing and
cross-investigation accumulation stay with the Evidence Engine and the memory pipeline.

Phase R1 is behavior-preserving: :meth:`EvidenceRepository.snapshot` performs exactly the reads the
reasoning path performed inline before the Repository existed (the governance bind, the prior-context
retrieval, the InvestigationContext assembly), in the same modes — so no verdict, number, or governance
outcome changes. Later phases consolidate those reads (bind-once), decouple the evidence read-schema
from the response DTO, and resolve identity — all behind this now-stable seam.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from app.evidence.bundle import digest


@dataclass(frozen=True)
class EvidenceSnapshot:
    """An immutable, content-addressed projection of one investigation's evidence at read time.

    Holds the raw scan payload (the ingest format, read-only), the canonical governance Evidence
    Bundle (the Governor's echo source), the assembled InvestigationContext (the projection the
    Composer bundles from), and the frozen institutional-memory priors (context, never proof).

    Content-addressed by ``snapshot_id`` — a pure function of the evidence identity (the bundle id +
    the context id + the priors), excluding wall-clock — so any assessment can name exactly which
    evidence it reasoned from. ``retrieved_at`` records WHEN the read happened and is deliberately NOT
    part of the content address. The body is ephemeral; only the id is recorded downstream.
    """

    payload: dict
    ref: str
    platform: str
    grain: str
    gov_bundle: Any                      # app.evidence.bundle.EvidenceBundle — the governance bundle
    context: Any                         # app.reasoning.context.InvestigationContext
    prior_context: tuple[dict, ...]      # frozen institutional-memory priors (context, never proof)
    retrieved_at: str                    # wall-clock of the read — NOT part of the content address
    snapshot_id: str = ""

    def headline(self) -> dict:
        """The engine's echoed numbers (overall_probability / tier / confidence) — sourced from the
        governance bundle, exactly as the Governor reads them. The Repository echoes; it never
        recomputes."""
        return self.gov_bundle.headline()


class EvidenceRepository:
    """The ONE read-facade for investigation evidence. Composes an immutable
    :class:`EvidenceSnapshot` from the durable stores. Reads only — no reasoning, no scoring, no
    model, no writes."""

    def snapshot(
        self,
        payload: dict,
        *,
        ref: str,
        platform: str = "unknown",
        grain: str = "comment_section",
        settings: Any = None,
        store: Any = None,
        now: Any = None,
    ) -> EvidenceSnapshot:
        """Read an investigation's evidence ONCE and freeze it into an immutable snapshot.

        Behavior-preserving (Phase R1): performs exactly the reads the reasoning path performed inline
        — the governance ``Binder`` bind, the institutional-memory prior retrieval, and the
        InvestigationContext assembly — in the same modes and order-independent because every read is a
        pure, side-effect-free projection. Never raises for the caller (context assembly degrades a
        section to empty rather than failing).
        """
        # Lazy imports keep the Repository free of a load-time cycle with the reasoning modules that
        # (later) import it, and keep the ``evidence`` layer free of a reasoning dependency.
        from app.evidence import Binder
        from app.reasoning.analyst import _retrieve_prior_context
        from app.reasoning.context import build_investigation_context

        payload = payload or {}
        gov_bundle = Binder().bind(payload, grain=grain, subject_ref=ref, platform=platform)
        priors = tuple(_retrieve_prior_context(store, gov_bundle, now=now))
        context = build_investigation_context(
            payload, ref=ref, platform=platform, settings=settings, store=store, now=now, grain=grain,
        )
        snapshot_id = digest(
            {"gov": gov_bundle.bundle_id(), "ctx": context.context_id,
             "priors": [{"type": p.get("type"), "label": p.get("label"),
                         "confidence": p.get("confidence")} for p in priors]},
            prefix="es:",
        )
        return EvidenceSnapshot(
            payload=payload, ref=ref, platform=platform, grain=grain,
            gov_bundle=gov_bundle, context=context, prior_context=priors,
            retrieved_at=datetime.now(timezone.utc).isoformat(), snapshot_id=snapshot_id,
        )


__all__ = ["EvidenceSnapshot", "EvidenceRepository"]
