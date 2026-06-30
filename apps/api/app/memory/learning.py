"""The live institutional learning loop — Governor-gated, feedback-closed (Sprint 014).

This is the operational spine that turns settled investigations into institutional knowledge and
feeds that knowledge back into future reasoning, end to end:

    Investigation → Evidence Bundle → Governor Validation → Memory Candidate
                 → Background Distillation → Institutional Knowledge → Future Retrieval

Three deterministic seams live here; none of them touches an investigation's score, the Governor,
or OmiScore:

1. ``retrieve_with_feedback`` — retrieval with the *learned* usefulness signal applied to
   **ranking only** (priors the institution has found useful surface earlier; nothing is added,
   removed, or rescored).
2. ``learn_from_investigation`` — the **Governor-gated** write. Memory candidates are recorded
   ONLY when the Constitutional Governor PERMITTED the ruling. A rejected ruling fell back to the
   Deterministic Floor; its conclusions are not constitutional evidence and must never be learned.
3. ``record_retrieval_feedback`` — closes the loop: for each surfaced prior, record whether it
   influenced reasoning, whether the Governor accepted the ruling, and whether the analyst agreed
   (``useful`` ⇔ all three). Feedback improves future **ranking only**.

Everything here is a pure, replayable function of its inputs; the LLM is never a write source.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Iterable

from .feedback import RetrievalFeedback, usefulness_map
from .graph.extract import record_settled_investigation
from .graph.objects import KnowledgeObject
from .retrieval_engine import RetrievalResult, retrieve_priors


def retrieve_with_feedback(
    store: Any, bundle: Any, *, budget: int = 5, now: datetime | None = None, **kwargs: Any,
) -> RetrievalResult:
    """Retrieve PriorContext with the institution's learned usefulness signal applied to RANKING.

    Reads the accumulated retrieval feedback, derives a ``{ko_id: usefulness_rate}`` map, and hands
    it to the tier-aware retrieval engine as a bounded ranking bonus. The usefulness signal can
    only reorder which priors surface first — it never adds evidence, removes a tier filter, or
    changes a score. Deterministic given ``(store, bundle, now)`` + the stored feedback."""
    rows = store.feedback() if hasattr(store, "feedback") else []
    umap = usefulness_map(rows)
    return retrieve_priors(store, bundle, budget=budget, now=now, usefulness=umap, **kwargs)


def learn_from_investigation(
    store: Any, bundle: Any, *, permitted: bool, investigation: str, independence_key: str, at: str,
    stance: str = "supports", is_control: bool = False,
    primed_signatures: Iterable[str] = (), human_anchor: dict | None = None,
) -> list[KnowledgeObject]:
    """The Governor-gated memory write. Structural memory candidates from a **settled** bundle are
    recorded ONLY if the Constitutional Governor PERMITTED the ruling (``permitted=True``). On
    REJECT nothing is written — memory must never learn from a ruling the constitution refused.

    Wraps the Sprint-005 evidence-gated write loop (patterns not verdicts, evidence-gated, with the
    primed≠independent loop-breaker). Deterministic; the LLM is never a write source. Returns the
    ``KnowledgeObject``s written (empty when not permitted)."""
    if not permitted:
        return []
    return record_settled_investigation(
        store, bundle, investigation=investigation, independence_key=independence_key, at=at,
        stance=stance, is_control=is_control, primed_signatures=primed_signatures,
        human_anchor=human_anchor,
    )


def _ko_id_of(prior: Any) -> str | None:
    if isinstance(prior, dict):
        return prior.get("ko_id")
    return getattr(prior, "ko_id", None)


def _basis_of(prior: Any) -> str:
    if isinstance(prior, dict):
        return prior.get("match_basis", "")
    return getattr(prior, "match_basis", "") or ""


def record_retrieval_feedback(
    store: Any, priors: Iterable[Any], *, investigation: str, permitted: bool,
    analyst_agreed: bool, at: str, influenced_ids: Iterable[str] | None = None,
) -> list[RetrievalFeedback]:
    """Close the retrieval-feedback loop for one investigation. For each prior the council
    surfaced, append a ``RetrievalFeedback`` event recording whether it influenced reasoning,
    whether the Governor accepted the ruling that used it (``permitted``), and whether the analyst
    agreed. ``useful`` ⇔ all three — that is the only thing that lifts a memory's future ranking.

    Feedback is append-only and improves retrieval **ranking only**; it never changes an
    investigation's score, a memory's confidence, the Governor, or OmiScore. ``influenced_ids``
    optionally narrows which surfaced priors actually shaped reasoning (default: all surfaced
    priors are treated as having been placed in the council's context). Deterministic."""
    influenced = set(influenced_ids) if influenced_ids is not None else None
    out: list[RetrievalFeedback] = []
    for p in priors:
        ko_id = _ko_id_of(p)
        if ko_id is None:
            continue
        fb = RetrievalFeedback(
            ko_id=ko_id, investigation=investigation, selected_because=_basis_of(p),
            influenced=(True if influenced is None else ko_id in influenced),
            governor_accepted=bool(permitted), analyst_agreed=bool(analyst_agreed), at=at,
        )
        store.record_feedback(fb)
        out.append(fb)
    return out
