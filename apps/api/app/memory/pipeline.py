"""The live investigation ↔ institutional memory connector + impact measurement (Sprint 015).

Sprints 005-014 built the memory system and tested it in isolation; this module is the missing
connective tissue that runs the **complete loop over a real investigation** and *measures whether
memory actually improved reasoning*:

    Investigation → Evidence Bundle → Governor → Retrieval → Council → Shadow Evaluation
                 → Memory Candidate → (Background Consolidation → Supabase → Future Retrieval)

``measure_memory_impact`` does this for one real payload, deterministically:

1. **Retrieval** — what memory surfaces for this bundle (with the learned usefulness ranking).
2. **Council A/B** — runs the real Shadow pipeline twice, *with* and *without* memory, so memory's
   effect is isolated (the only changed variable). The user-facing **engine number is
   constitutionally preserved** — memory is context, never proof — which this verifies, it never
   assumes.
3. **Feedback** — records Governor-gated retrieval feedback for the surfaced priors (ranking only).
4. **Learning** — writes the Governor-gated memory candidate from the settled bundle (a rejected
   ruling teaches nothing).

It returns a ``MemoryImpact`` of verified measurements (retrieved / used / false retrievals /
governor acceptance / analyst agreement / engine-number delta / AI-uncertainty delta / evidence
overlap / retrieval latency / council latency delta). No new storage: the durable signal lives in
the existing ``retrieval_feedback`` + memory tables. Nothing here changes OmiScore or the Governor.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.evidence import Binder

from .learning import (
    learn_from_investigation,
    record_retrieval_feedback,
    retrieve_with_feedback,
)


def _cited_refs(assessment: dict) -> set[str]:
    """The bundle evidence ids the council actually cited (evidence_for + evidence_against)."""
    refs: set[str] = set()
    for key in ("evidence_for", "evidence_against"):
        for item in (assessment.get(key) or []):
            for ref in (item.get("evidence_refs") or []):
                refs.add(ref)
    return refs


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 0.0
    union = len(a | b)
    return round(len(a & b) / union, 4) if union else 0.0


@dataclass
class MemoryImpact:
    """Verified measurements of memory's effect on ONE real investigation. Measurement only —
    nothing here is a verdict, and the engine number is constitutionally preserved."""

    investigation: str
    bundle_id: str
    memory_revision: str
    retrieved: int                          # priors memory surfaced
    used: int                               # surfaced priors whose evidence the council actually cited
    false_retrievals: int                   # retrieved − used (surfaced but not reflected in reasoning)
    retrieval_precision: float              # used / retrieved
    governor_accepted: bool                 # with-memory production ruling permitted
    analyst_agreed: bool                    # deterministic vs AI council agreed (with memory)
    engine_number_delta: float              # production suspicion number: with − without memory
    number_preserved: bool                  # engine_number_delta == 0 (constitutional invariant)
    ai_uncertainty_delta: int               # AI council uncertainty items: with − without memory
    citations_changed: bool                 # did the cited-evidence set change when memory was added?
    evidence_overlap: float                 # jaccard(surfaced priors' refs, investigation citations)
    retrieval_latency_ms: float             # retrieval engine latency (no full scan)
    retrieval_scan_fraction: float          # share of corpus scanned (proves index path)
    council_latency_delta_ms: float         # council wall-time: with − without memory
    learned: list = field(default_factory=list)        # ko ids written back (Governor-gated)
    feedback_recorded: int = 0
    priors: list = field(default_factory=list)         # [{ko_id,type,label,score,tier,usefulness,used}]
    ran_at: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def measure_memory_impact(
    payload: dict, *, ref: str, store: Any, platform: str = "youtube",
    grain: str = "comment_section", settings: Any = None, now: datetime | None = None,
    learn: bool = True, stance: str = "supports", is_control: bool = False,
) -> MemoryImpact:
    """Run the full loop over one real investigation and measure memory's effect. Deterministic
    given ``(payload, store state, now)``. Runs the real Shadow pipeline twice (with/without memory)
    to isolate memory as the single changed variable, then closes the loop (feedback + Governor-gated
    learning). ``learn=False`` measures without writing (a pure read probe)."""
    from app.reasoning.shadow import run_shadow          # local import: avoids any import-time coupling

    at = (now or datetime.now(timezone.utc)).isoformat()
    bundle = Binder().bind(payload, grain=grain, subject_ref=ref, platform=platform)

    # 1. Retrieval — what memory surfaces (with the learned usefulness ranking applied).
    res = retrieve_with_feedback(store, bundle, now=now)
    retrieved = res.priors

    # 2. Council A/B — the real Shadow pipeline, with and without memory (memory is the only change).
    base = run_shadow(payload, ref=ref, platform=platform, grain=grain, settings=settings,
                      store=None, now=now)
    withmem = run_shadow(payload, ref=ref, platform=platform, grain=grain, settings=settings,
                         store=store, now=now)

    base_assess = base.production["assessment"]
    mem_assess = withmem.production["assessment"]
    cited = _cited_refs(mem_assess) | _cited_refs(withmem.shadow["assessment"])
    base_cited = _cited_refs(base_assess) | _cited_refs(base.shadow["assessment"])

    used_priors = [p for p in retrieved if set(p.evidence_refs) & cited]
    permitted = bool(withmem.production["trace"]["permitted"])
    agreed = bool(withmem.comparison["overall_agreement"])

    engine_delta = round(
        float(mem_assess.get("suspicion_probability") or 0.0)
        - float(base_assess.get("suspicion_probability") or 0.0), 6
    )
    ai_unc_delta = (len(withmem.shadow["assessment"].get("uncertainty") or [])
                    - len(base.shadow["assessment"].get("uncertainty") or []))

    prior_refs: set[str] = set()
    for p in retrieved:
        prior_refs.update(p.evidence_refs)

    # 3 + 4. Close the loop — Governor-gated feedback (ranking only) + Governor-gated learning.
    # ``learn=False`` is a pure read-only probe: it measures impact but writes nothing.
    feedback: list = []
    learned: list = []
    if learn:
        feedback = record_retrieval_feedback(
            store, retrieved, investigation=ref, permitted=permitted, analyst_agreed=agreed, at=at,
            influenced_ids=[p.ko_id for p in used_priors],
        )
        learned = [k.id for k in learn_from_investigation(
            store, bundle, permitted=permitted, investigation=ref,
            independence_key=ref, at=at, stance=stance, is_control=is_control,
        )]

    used_ids = {p.ko_id for p in used_priors}
    return MemoryImpact(
        investigation=ref, bundle_id=withmem.bundle_id, memory_revision=withmem.memory_revision,
        retrieved=len(retrieved), used=len(used_priors), false_retrievals=len(retrieved) - len(used_priors),
        retrieval_precision=round(len(used_priors) / len(retrieved), 4) if retrieved else 0.0,
        governor_accepted=permitted, analyst_agreed=agreed,
        engine_number_delta=engine_delta, number_preserved=(engine_delta == 0.0),
        ai_uncertainty_delta=ai_unc_delta, citations_changed=(cited != base_cited),
        evidence_overlap=_jaccard(prior_refs, cited),
        retrieval_latency_ms=res.latency_ms, retrieval_scan_fraction=res.plan.scan_fraction,
        council_latency_delta_ms=round(
            withmem.diagnostics["wall_ms"] - base.diagnostics["wall_ms"], 2),
        learned=learned, feedback_recorded=len(feedback),
        priors=[{"ko_id": p.ko_id, "type": p.type, "label": p.label, "score": p.score,
                 "tier": p.tier, "usefulness": p.usefulness, "used": p.ko_id in used_ids}
                for p in retrieved],
        ran_at=at,
    )


__all__ = ["MemoryImpact", "measure_memory_impact"]
