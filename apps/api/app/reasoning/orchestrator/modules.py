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

from typing import Any, Protocol, runtime_checkable

from app.evidence.bundle import EvidenceBundle
from app.memory.graph import retrieve

from app.reasoning.contracts import Artifact, Critique, Finding, Memory, ReasoningContract, Ruling

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
# Tier 1 — Memory Analyst (institutional memory as a council specialist)
# --------------------------------------------------------------------------- #
class MemoryAnalyst:
    """Institutional memory participating in the council as a specialist (Sprint 005).

    Retrieves PriorContext from the knowledge graph and publishes a structured ``Memory``
    artifact — context, never proof. It never raises suspicion; exculpatory priors may lower
    via the Judge's evidence_against, supporting priors are context only. Replaceable by a
    Qwen-backed implementation behind the same contract with **no orchestration change**."""

    def __init__(self, store: Any, *, now: Any | None = None, top_k: int = 5) -> None:
        self._store = store
        self._now = now
        self._top_k = top_k
        self.contract = ReasoningContract(
            module="memory_analyst", tier=1, output_kind="memory", contract_version="v1",
            inputs=("*",),
            constraints=(
                "memory is context, never proof",
                "never raises suspicion (no evidence_for)",
                "cite bundle evidence; ko ids are provenance",
                "exculpatory priors may lower, never raise",
            ),
        )

    def run(self, view: BlackboardView) -> list[Artifact]:
        priors = retrieve(self._store, view.bundle, top_k=self._top_k, now=self._now)
        supporting: list[dict] = []
        contradicting: list[dict] = []
        uncertainty: list[str] = []
        refs: list[str] = []
        for p in priors:
            note = ("a known legitimate-coordination control — exculpatory context"
                    if p.is_control else "context, not proof")
            item = {
                "ko_id": p.ko_id, "type": p.type, "label": p.label,
                "confidence": p.confidence, "stability": p.stability_score,
                "influence_class": p.influence_class, "evidence_refs": list(p.evidence_refs),
                "claim": (f"Current evidence resembles '{p.label}' ({p.type}), seen in prior "
                          f"investigations (confidence {round(p.confidence * 100)}%, "
                          f"stability {round(p.stability_score * 100)}%) — {note}."),
            }
            refs.extend(p.evidence_refs)
            if p.influence_class == "exculpatory":
                contradicting.append(item)
            else:
                supporting.append(item)
            if p.stability_score < 0.5 or p.confidence < 0.3:
                uncertainty.append(
                    f"Prior '{p.label}' matched at low confidence/stability — weak context only."
                )
        return [Memory(
            module=self.contract.module, evidence_refs=list(dict.fromkeys(refs)),
            supporting=supporting, contradicting=contradicting, uncertainty=uncertainty,
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


def _coordination_label(bundle: EvidenceBundle, corr: dict, verdict: str) -> str | None:
    """The coordination read, kept CONSISTENT with the authenticity read (Sprint 020). A
    discriminative coordination method is 'suspicious' only when the final verdict is hostile
    (``likely_inauthentic``); on an authentic / mixed / inconclusive subject the same coordination is
    at least as consistent with organic or legitimate behaviour, so it is 'mixed' (never 'suspicious',
    which would contradict the verdict and false-positive on organic viral events). ``None`` when
    there is no coordination signal."""
    methods = [it for it in bundle.evidence.values() if it.kind == "coordination_method"]
    if not methods:
        return None
    disc = bool(corr["discriminative_methods"]) and not corr["single_axis_capped"]
    if disc and verdict == "likely_inauthentic":
        return "suspicious"
    return "mixed"


def _exculpatory_controls(memories: "list | None") -> list[dict]:
    """Known legitimate-coordination CONTROL priors among the exculpatory memory (Sprint 019) —
    the strongest exculpatory signal a coordination read can carry. Controls are exculpatory: they
    may LOWER the read, never raise it, so reasoning from them is constitutional."""
    out: list[dict] = []
    for mem in (memories or []):
        for c in getattr(mem, "contradicting", []):
            if "Control" in str(c.get("type", "")):
                out.append(c)
    return out


def _legitimate_hypothesis(corr: dict, control_priors: list) -> str | None:
    """The explicit legitimate-coordination hypothesis (analyst spec §13): for any coordination
    read, name the benign alternative and state whether the evidence distinguishes hostile from
    benign coordination. ``None`` only when there is no coordination signal to contextualize."""
    methods = corr.get("discriminative_methods") or []
    if not methods:
        return None
    joined = "+".join(methods)
    if control_priors:
        match = (control_priors[0].get("claim") or control_priors[0].get("label")
                 or "a known legitimate-coordination control")
        return (f"The {joined} coordination matches {match} — institutional memory holds this pattern "
                "as legitimate (e.g. a newsroom, fandom, or official on-message accounts). The available "
                "evidence does not distinguish hostile coordination from this benign pattern, so the "
                "coordinated read is downgraded to mixed.")
    return (f"Legitimate-coordination hypothesis: the {joined} coordination could reflect a newsroom, "
            "fan community, official on-message accounts, or benign automation rather than a hostile "
            "campaign; the discriminative methods are present but not anchored to human/platform ground "
            "truth, so the coordinated read stays provisional.")


def build_ruling_assessment(
    bundle: EvidenceBundle,
    *,
    findings: list[Finding] | None = None,
    critique: Critique | None = None,
    memories: list[Memory] | None = None,
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
    # Institutional memory — CONTEXT ONLY. Exculpatory priors (controls / contradicting
    # history) may lower via evidence_against; supporting priors are reported as context and
    # NEVER enter evidence_for or change the echoed number / tier / corroboration.
    for mem in (memories or []):
        for c in getattr(mem, "contradicting", []):
            evidence_against.append({
                "signal": f"memory:{c.get('type', 'prior')}",
                "claim": c.get("claim", ""),
                "evidence_refs": list(c.get("evidence_refs", [])),
            })
        for sp in getattr(mem, "supporting", []):
            uncertainty.append(f"Institutional memory (context, not proof): {sp.get('claim', '')}")
        uncertainty.extend(getattr(mem, "uncertainty", []))
    if not uncertainty:
        uncertainty = ["Single automated pass over one snapshot; treat as a provisional read."]
    if not wwc:
        wwc = ["Independent corroborating evidence on a later scan would sharpen the read."]

    rationale = f"{band} confidence (engine confidence {round(conf * 100)}%)."
    if not evidence_against:
        rationale += " No exculpatory signal was present in the bundle."

    # Sprint 019 — legitimate-coordination reasoning. A KNOWN legitimate-coordination control in
    # institutional memory is exculpatory: it LOWERS the read (constitutional — memory may lower,
    # never raise). When present with a discriminative coordination read it downgrades the analyst's
    # *interpretation* (verdict) from hostile to mixed and yields the explicit legitimate hypothesis.
    # The engine number, tier, confidence band, and the corroboration gate are untouched.
    control_priors = _exculpatory_controls(memories)
    legitimate_hypothesis = _legitimate_hypothesis(corr, control_priors)
    if control_priors and corr["discriminative_methods"] and verdict == "likely_inauthentic":
        verdict = "mixed"
        rationale += " A known legitimate-coordination control in memory makes the benign reading at least as likely."
        wwc = [f"Ground-truth confirmation that the {'+'.join(corr['discriminative_methods'])} "
               "coordination is hostile (not the known legitimate control) would restore the elevated read."] + wwc

    # Sprint 020 — the coordination read must be CONSISTENT with the authenticity read: a
    # discriminative method is 'suspicious' only when the final verdict is hostile (likely_inauthentic).
    # On an authentic / mixed / inconclusive subject the same co-engagement is at least as consistent
    # with organic or legitimate coordination, so it is 'mixed', never 'suspicious' — which previously
    # false-positived on organic viral events (a likely_authentic subject labeled suspicious).
    coordination_label = _coordination_label(bundle, corr, verdict)

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
        "coordination_label": coordination_label,
        "legitimate_hypothesis": legitimate_hypothesis,
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
        memories = [a for a in view.memories() if isinstance(a, Memory)]
        critique = critiques[0] if critiques else None
        assessment = build_ruling_assessment(
            view.bundle, findings=findings, critique=critique, memories=memories,
        )
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
