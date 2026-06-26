"""Evidence-gated memory extractor — the write loop from settled bundles into memory.

Closes the institutional-memory loop: Sprint 005 built the read side (store + retrieval);
this turns a **settled** Evidence Bundle into structural ``KnowledgeObject`` candidates and
ingests them as append-only observations. The hard guarantees are enforced here, in code:

- **Patterns, never verdicts.** A candidate is the set of detectors/methods that fired
  together (a structural regularity) — never "this is coordinated". The engine's number is
  not stored; only *what was observed*.
- **Evidence-gated.** Candidates are derived solely from bundle ``EvidenceItem``s (+ the
  caller-supplied settlement) — the LLM is never a write source.
- **Loop-breaker.** An observation whose signature was *primed* by retrieved memory is
  flagged ``memory_influence="primed"`` so it cannot count as independent corroboration:
  memory can never confirm itself.
- **Gate-respecting.** Only **discriminative** coordination methods form a coordination
  signature; non-probative coordination is never memorized as one.

A bundle is a *snapshot*; "settled" is a property of the investigation the caller asserts —
this module never decides settlement on its own.
"""
from __future__ import annotations

from typing import Iterable

from app.evidence.bundle import EvidenceBundle

from .objects import KnowledgeObject
from .store import MemoryStore


def _behavioral_signature(bundle: EvidenceBundle) -> list[str]:
    """The non-supplemental RAISING behavioral contributions — the suspicion pattern that
    fired (the thing memory can recognize later). Deterministic (sorted, de-duped)."""
    return sorted({
        it.originating_detector for it in bundle.evidence.values()
        if it.facet == "behavioral" and it.kind == "contribution"
        and not it.supplemental and it.direction == "raises"
    })


def _coordination_signature(bundle: EvidenceBundle) -> list[str]:
    """The discriminative coordination methods only — non-probative (gated) coordination is
    never memorized as a signature."""
    return sorted({
        it.originating_detector for it in bundle.evidence.values()
        if it.kind == "coordination_method" and it.discriminative and not it.supplemental
    })


def _refs_for(bundle: EvidenceBundle, signature: Iterable[str]) -> list[str]:
    """Content digests of the EvidenceItems that characterize ``signature`` — evidence, not
    opinion; durable across bundles (the same evidence content hashes the same)."""
    sig = set(signature)
    return sorted({
        it.content_digest() for it in bundle.evidence.values()
        if it.originating_detector in sig
    })


def _attributes(bundle: EvidenceBundle) -> dict:
    return {"grain": bundle.grain, "platform": bundle.subject.get("platform", "unknown")}


def extract_candidates(bundle: EvidenceBundle, *, is_control: bool = False) -> list[dict]:
    """Derive structural ``KnowledgeObject`` candidates from a **settled** Evidence Bundle.

    Patterns, never verdicts. A confirmed-legitimate settlement (``is_control``) yields only
    the ``LegitimateCoordinationControl`` (so legit cases never pollute memory as suspicion
    archetypes); otherwise the behavioral archetype + the (discriminative) coordination
    signature. A pure, deterministic function of the bundle."""
    attrs = _attributes(bundle)
    if is_control:
        csig = _coordination_signature(bundle)
        if not csig:
            return []
        return [{
            "type": "LegitimateCoordinationControl", "family": "coordination",
            "label": "legitimate coordination control: " + "+".join(csig),
            "signature": csig, "is_control": True, "attributes": attrs,
        }]

    out: list[dict] = []
    bsig = _behavioral_signature(bundle)
    if bsig:
        out.append({
            "type": "BehavioralArchetype", "family": "patterns_signatures",
            "label": "behavioral archetype: " + "+".join(bsig),
            "signature": bsig, "attributes": attrs,
        })
    csig = _coordination_signature(bundle)
    if csig:
        out.append({
            "type": "CoordinationSignature", "family": "coordination",
            "label": "coordination signature: " + "+".join(csig),
            "signature": csig, "attributes": attrs,
        })
    return out


def record_settled_investigation(
    store: MemoryStore, bundle: EvidenceBundle, *,
    investigation: str, independence_key: str, at: str,
    stance: str = "supports", is_control: bool = False,
    primed_signatures: Iterable[str] = (), human_anchor: dict | None = None,
) -> list[KnowledgeObject]:
    """Close the memory write loop: extract structural candidates from a settled bundle and
    ingest each as an append-only observation. Returns the affected ``KnowledgeObject``s.

    ``stance`` ("supports" | "contradicts") is the settled investigation's conclusion about
    each pattern — a contradiction lowers a pattern's confidence over time, so memory
    self-corrects (controls always record "supports"). ``primed_signatures`` are the
    detector/method names of priors the council surfaced for *this* read; any candidate whose
    signature overlaps them is flagged ``memory_influence='primed'`` so it CANNOT count as
    independent corroboration — the loop-breaker, end to end.

    Call only for **settled** investigations: this is the evidence-gated write path; the LLM
    is never a write source."""
    primed = set(primed_signatures)
    effective_stance = "supports" if is_control else stance
    affected: list[KnowledgeObject] = []
    for cand in extract_candidates(bundle, is_control=is_control):
        influence = "primed" if (set(cand["signature"]) & primed) else "none"
        ko = store.ingest(
            candidate=cand, investigation=investigation, stance=effective_stance,
            evidence_refs=_refs_for(bundle, cand["signature"]),
            independence_key=independence_key, at=at,
            human_anchor=human_anchor, memory_influence=influence,
        )
        affected.append(ko)
    return affected
