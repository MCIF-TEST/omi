"""The deterministic comparison engine (Sprint 007).

Given the production (deterministic) council result and the shadow (AI-backed) council result,
compute a structured, **deterministic** comparison: agreement / disagreement on the
categorical reads, evidence overlap, citation quality, confidence + uncertainty deltas, and
the Governor outcomes. The comparison is a pure function of the two council *views* (no
wall-clock, no latency) so it is content-addressable and replayable — latency / retries /
provider telemetry live in the report's separate ``diagnostics`` block.

The constitutional invariant the comparison watches: an AI specialist must **never move the
engine number** (``confidence_delta == 0`` ⇒ ``number_preserved``); both councils echo the
engine's probability, so any drift would be a Governor violation, not a silent change.
"""
from __future__ import annotations

from typing import Any

from app.evidence.bundle import digest

# The categorical reads both councils produce; agreement is measured over these.
_CATEGORICAL = ("verdict", "suspicion_tier", "confidence_band", "coordination_label")


def council_view(result: Any) -> dict:
    """A serializable, comparison-ready view of a ``CouncilResult``: the full assessment, a
    trace summary, the Floor-fallback flag, and a deterministic blackboard digest."""
    trace = result.trace
    return {
        "assessment": result.assessment,
        "trace": {
            "permitted": bool(trace.permitted),
            "verdict": trace.verdict,
            "trace_id": trace.trace_id(),
            "violation_codes": list(trace.violation_codes),
        },
        "fallback": bool(result.fallback),
        "blackboard_digest": blackboard_digest(result.blackboard),
    }


def blackboard_digest(blackboard: Any) -> dict:
    """A deterministic summary of a council's posted artifacts — counts by kind, the findings
    (signal / direction / citations), and all cited refs — content-addressed for replay."""
    findings: list[dict] = []
    counts: dict[str, int] = {}
    citations: set[str] = set()
    if blackboard is not None:
        for art in blackboard.artifacts():
            counts[art.kind] = counts.get(art.kind, 0) + 1
            for ref in (getattr(art, "evidence_refs", None) or []):
                citations.add(ref)
            if art.kind == "finding":
                findings.append({
                    "module": art.module, "signal": getattr(art, "signal", ""),
                    "direction": getattr(art, "direction", "neutral"),
                    "evidence_refs": sorted(getattr(art, "evidence_refs", None) or []),
                })
    findings.sort(key=lambda f: (f["signal"], f["direction"], tuple(f["evidence_refs"])))
    core = {"artifact_counts": counts, "findings": findings, "citations": sorted(citations)}
    return {**core, "digest": digest(core, prefix="bb:")}


def _cited_refs(assessment: dict) -> set[str]:
    refs: set[str] = set()
    for key in ("evidence_for", "evidence_against"):
        for item in (assessment.get(key) or []):
            for ref in (item.get("evidence_refs") or []):
                refs.add(ref)
    return refs


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 1.0
    union = len(a | b)
    return round(len(a & b) / union, 4) if union else 1.0


def _ev_ratio(refs: set[str]) -> float:
    """Share of citations that are well-formed bundle ids (``ev:``) — a citation-quality
    proxy. Both councils cite resolvable bundle evidence, so this should be ~1.0."""
    if not refs:
        return 1.0
    return round(sum(1 for r in refs if r.startswith("ev:")) / len(refs), 4)


def compare(production: dict, shadow: dict) -> dict:
    """Compare two council views. Deterministic + pure → carries a ``comparison_id`` content
    hash. ``production`` is the user-facing deterministic result; ``shadow`` is the AI-backed
    result, present for evaluation only."""
    pa, sa = production["assessment"], shadow["assessment"]

    agreement = {f: (pa.get(f) == sa.get(f)) for f in _CATEGORICAL}
    disagreement = {
        f: {"production": pa.get(f), "shadow": sa.get(f)}
        for f in _CATEGORICAL if not agreement[f]
    }

    pe, se = _cited_refs(pa), _cited_refs(sa)
    evidence_overlap = {
        "production_citations": len(pe), "shadow_citations": len(se),
        "shared": sorted(pe & se), "shadow_only": sorted(se - pe),
        "production_only": sorted(pe - se), "jaccard": _jaccard(pe, se),
    }
    citation_quality = {
        "production_wellformed_ratio": _ev_ratio(pe),
        "shadow_wellformed_ratio": _ev_ratio(se),
    }

    conf_delta = round(
        float(sa.get("suspicion_probability") or 0.0) - float(pa.get("suspicion_probability") or 0.0), 6
    )
    pu, su = list(pa.get("uncertainty") or []), list(sa.get("uncertainty") or [])
    uncertainty_delta = {
        "production_count": len(pu), "shadow_count": len(su), "delta": len(su) - len(pu),
        "shadow_only": sorted(set(su) - set(pu)), "production_only": sorted(set(pu) - set(su)),
    }

    governor = {
        "production": {"permitted": production["trace"]["permitted"],
                       "violation_codes": production["trace"]["violation_codes"]},
        "shadow": {"permitted": shadow["trace"]["permitted"],
                   "violation_codes": shadow["trace"]["violation_codes"]},
        "shadow_fell_back_to_floor": shadow["fallback"],
        "both_permitted": production["trace"]["permitted"] and shadow["trace"]["permitted"],
    }

    core = {
        "overall_agreement": all(agreement.values()),
        "agreement": agreement,
        "disagreement": disagreement,
        "evidence_overlap": evidence_overlap,
        "citation_quality": citation_quality,
        "confidence_delta": conf_delta,
        "number_preserved": conf_delta == 0.0,   # constitutional invariant: AI never moves the number
        "uncertainty_delta": uncertainty_delta,
        "blackboard": {
            "production_digest": production["blackboard_digest"]["digest"],
            "shadow_digest": shadow["blackboard_digest"]["digest"],
            "identical": production["blackboard_digest"]["digest"] == shadow["blackboard_digest"]["digest"],
        },
        "governor": governor,
    }
    return {**core, "comparison_id": digest(core, prefix="cmp:")}
