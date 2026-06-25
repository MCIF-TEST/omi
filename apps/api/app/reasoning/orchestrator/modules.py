"""The first Analyst Council — deterministic implementations of the permanent interface.

Each module exposes a ``contract`` and a ``run(view) -> list[Artifact]`` method and talks
ONLY through the blackboard view + typed artifacts (no direct coupling). These deterministic
analysts establish the execution model; a future Qwen/LoRA analyst implements the same
``contract`` + ``run`` and is swapped in without any orchestration change.

This sprint deliberately implements the *framework*, not specialist reasoning: the
deterministic modules echo the engine's evidence into the contract shapes. The Judge and
FloorJudge assemble a Governor-valid Ruling; the Governor (mandatory) validates it
downstream and the Floor is the fallback.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.evidence.bundle import EvidenceBundle

from app.reasoning.contracts import Artifact, Critique, Finding, ReasoningContract, Ruling

from .blackboard import BlackboardView


@runtime_checkable
class AnalystModule(Protocol):
    """The permanent module interface. Any reasoning implementation that satisfies this
    (deterministic today, Qwen-backed tomorrow) plugs into the orchestrator unchanged."""

    contract: ReasoningContract

    def run(self, view: BlackboardView) -> list[Artifact]: ...


# --------------------------------------------------------------------------- #
# Tier 1 — Behavior Analyst (specialist)
# --------------------------------------------------------------------------- #
class BehaviorAnalyst:
    contract = ReasoningContract(
        module="behavior_analyst", tier=1, output_kind="finding", contract_version="v1",
        inputs=("behavioral",),
        constraints=("cite every claim", "supplemental signals are context, never suspicion"),
    )

    def run(self, view: BlackboardView) -> list[Artifact]:
        out: list[Artifact] = []
        for it in view.evidence(facet="behavioral"):
            if it.kind != "contribution" or it.supplemental:
                continue
            verb = {
                "raises": "is consistent with elevated suspicion",
                "lowers": "is consistent with more organic behavior",
            }.get(it.direction, "is contextual")
            out.append(Finding(
                module=self.contract.module, signal=it.originating_detector,
                claim=f"The {it.originating_detector} signal {verb}.",
                direction=it.direction, evidence_refs=[it.id],
            ))
        return out


# --------------------------------------------------------------------------- #
# Tier 2 — Counter-Evidence Analyst (Red Team)
# --------------------------------------------------------------------------- #
class CounterEvidenceAnalyst:
    contract = ReasoningContract(
        module="counter_evidence_analyst", tier=2, output_kind="critique", contract_version="v1",
        inputs=("behavioral", "coordination"),
        constraints=("marshal the strongest exculpatory case", "state what would flip the read"),
    )

    def run(self, view: BlackboardView) -> list[Artifact]:
        exculpatory: list[dict] = []
        for it in view.evidence():
            if it.kind == "contribution" and it.direction == "lowers" and not it.supplemental:
                exculpatory.append({
                    "signal": it.originating_detector,
                    "claim": f"The {it.originating_detector} signal lowers suspicion, "
                             "consistent with more organic behavior.",
                    "evidence_refs": [it.id],
                })
        ep = view.bundle.epistemics
        would_flip = [m.get("what", "") for m in ep.get("missing_evidence", []) if m.get("what")]
        for u in ep.get("unknowns", []):
            if u.get("basis") == "non_discriminative_coordination":
                would_flip.append(
                    "A discriminative coordination link (fingerprint_cluster, co_engagement, "
                    "or co_tag) would corroborate or rule out coordination."
                )
        if not would_flip:
            would_flip = ["Independent corroborating evidence on a later scan."]
        refs = [e["evidence_refs"][0] for e in exculpatory if e.get("evidence_refs")]
        return [Critique(
            module=self.contract.module, targets="leading_suspicion",
            exculpatory=exculpatory, would_flip_if=would_flip, evidence_refs=refs,
        )]


# --------------------------------------------------------------------------- #
# Tier 3 — Judge + FloorJudge (adjudication)
# --------------------------------------------------------------------------- #
_BANDS = {"insufficient": 0, "low": 1, "moderate": 2, "high": 3}


def _engine_band(conf: float) -> str:
    if conf < 0.2:
        return "insufficient"
    if conf < 0.45:
        return "low"
    if conf < 0.7:
        return "moderate"
    return "high"


def _corroboration(bundle: EvidenceBundle) -> dict:
    disc = sorted({
        it.originating_detector for it in bundle.evidence.values()
        if it.kind == "coordination_method" and it.discriminative
    })
    single = any(u.get("basis") == "single_axis" for u in bundle.epistemics.get("unknowns", []))
    return {"discriminative_methods": disc, "single_axis_capped": single, "convergence": len(disc) >= 1}


def _verdict(tier: str, band: str, corr: dict) -> str:
    if band == "insufficient":
        return "inconclusive"
    disc = bool(corr["discriminative_methods"]) and not corr["single_axis_capped"]
    if tier == "high":
        return "likely_inauthentic" if disc else "mixed"
    if tier == "elevated":
        return "likely_inauthentic" if (disc and band in ("high", "moderate")) else "mixed"
    if tier == "moderate":
        return "mixed"
    if tier == "low":
        return "likely_authentic"
    return "inconclusive"


def _coordination_label(bundle: EvidenceBundle, corr: dict) -> str | None:
    methods = [it for it in bundle.evidence.values() if it.kind == "coordination_method"]
    if not methods:
        return None
    if corr["discriminative_methods"] and not corr["single_axis_capped"]:
        return "suspicious"   # gated: discriminative present but not asserting "coordinated" deterministically
    return "mixed"


def build_ruling_assessment(
    bundle: EvidenceBundle,
    *,
    findings: list[Finding] | None = None,
    critique: Critique | None = None,
) -> dict:
    """Assemble a Governor-valid assessment from the bundle (+ optional council artifacts).

    Used by both the council Judge (with findings + critique) and the FloorJudge (bundle
    only). Echoes the engine number, surfaces counter-evidence + uncertainty, stays inside
    the corroboration gate, and remains falsifiable — so it passes the Governor by
    construction."""
    hl = bundle.headline()
    prob = float(hl.get("overall_probability", 0.0) or 0.0)
    tier = str(hl.get("tier", "low") or "low")
    conf = float(hl.get("confidence", 0.0) or 0.0)

    corr = _corroboration(bundle)
    eng_band = _engine_band(conf)
    disc_ok = bool(corr["discriminative_methods"]) and not corr["single_axis_capped"]
    # confidence band: never above the engine band; downgrade without corroboration.
    band = eng_band
    if eng_band in ("high", "moderate") and not disc_ok:
        band = "low" if eng_band == "moderate" else "moderate"
    verdict = _verdict(tier, band, corr)

    # evidence_for: council findings (raises), else bundle raising contributions.
    if findings:
        evidence_for = [
            {"signal": f.signal, "claim": f.claim, "evidence_refs": list(f.evidence_refs)}
            for f in findings if f.direction == "raises"
        ]
    else:
        evidence_for = [
            {"signal": it.originating_detector,
             "claim": f"The {it.originating_detector} signal is consistent with elevated suspicion.",
             "evidence_refs": [it.id]}
            for it in bundle.evidence.values()
            if it.kind == "contribution" and it.direction == "raises" and not it.supplemental
        ]

    # evidence_against: critique exculpatory, else bundle lowering contributions.
    if critique is not None:
        evidence_against = [
            {"signal": e.get("signal", "counter"), "claim": e["claim"],
             "evidence_refs": list(e.get("evidence_refs", []))}
            for e in critique.exculpatory
        ]
        wwc = list(critique.would_flip_if)
    else:
        evidence_against = [
            {"signal": it.originating_detector,
             "claim": f"The {it.originating_detector} signal lowers suspicion, consistent with more organic behavior.",
             "evidence_refs": [it.id]}
            for it in bundle.evidence.values()
            if it.kind == "contribution" and it.direction == "lowers" and not it.supplemental
        ]
        wwc = []

    uncertainty = [u["statement"] for u in bundle.epistemics.get("unknowns", []) if u.get("statement")]
    uncertainty += [m["what"] for m in bundle.epistemics.get("missing_evidence", []) if m.get("what")]
    if not uncertainty:
        uncertainty = ["Single automated pass over one snapshot; treat as a provisional read."]
    if not wwc:
        wwc = ["Independent corroborating evidence on a later scan would sharpen the read."]

    rationale = f"{band} confidence (engine confidence {round(conf * 100)}%)."
    if not evidence_against:
        rationale += " No exculpatory signal was present in the bundle."

    pct = round(prob * 100)
    return {
        "verdict": verdict,
        "suspicion_tier": tier,
        "suspicion_probability": round(prob, 6),
        "confidence_band": band,
        "confidence_rationale": rationale,
        "headline": f"{tier.title()} suspicion (~{pct}%), read probabilistically.",
        "assessment": (
            f"The council places this comment_section at ~{pct}% suspicion ({tier} tier). "
            "The engine's number is echoed, not recomputed; the behavior and counter-evidence "
            "analysts supply the supporting and exculpatory reads. This is a probabilistic "
            "assessment; the human analyst sets the verdict."
        ),
        "evidence_for": evidence_for,
        "evidence_against": evidence_against,
        "uncertainty": uncertainty,
        "what_would_change_this": wwc,
        "corroboration": corr,
        "coordination_label": _coordination_label(bundle, corr),
        "limits_statement": "Probabilistic assessment; the human analyst sets the final verdict.",
    }


class Judge:
    contract = ReasoningContract(
        module="judge", tier=3, output_kind="ruling", contract_version="v1",
        inputs=("*",),
        constraints=("echo the engine number", "respect the corroboration gate",
                     "require counter-evidence + uncertainty + falsifiability"),
    )

    def run(self, view: BlackboardView) -> list[Artifact]:
        findings = [a for a in view.findings() if isinstance(a, Finding)]
        critiques = [a for a in view.critiques() if isinstance(a, Critique)]
        critique = critiques[0] if critiques else None
        assessment = build_ruling_assessment(view.bundle, findings=findings, critique=critique)
        return [Ruling(module=self.contract.module, assessment=assessment,
                       evidence_refs=_ruling_refs(assessment))]


class FloorJudge:
    """The always-valid deterministic Floor judge — the council's fallback. Builds a
    Governor-valid Ruling from the bundle alone (no council artifacts required)."""

    contract = ReasoningContract(
        module="floor_judge", tier=3, output_kind="ruling", contract_version="v1",
        inputs=("*",), constraints=("always Governor-valid by construction",),
    )

    def run(self, view: BlackboardView) -> list[Artifact]:
        assessment = build_ruling_assessment(view.bundle, findings=None, critique=None)
        return [Ruling(module=self.contract.module, assessment=assessment,
                       evidence_refs=_ruling_refs(assessment))]


def _ruling_refs(assessment: dict) -> list[str]:
    refs: list[str] = []
    for key in ("evidence_for", "evidence_against"):
        for item in assessment.get(key, []):
            refs.extend(item.get("evidence_refs", []))
    return refs


def default_council() -> list[AnalystModule]:
    """The Sprint-004 council members (Tier-1 + Tier-2). The Judge runs after; the
    FloorJudge is the fallback. Pass a custom list to the Orchestrator to swap/extend."""
    return [BehaviorAnalyst(), CounterEvidenceAnalyst()]
