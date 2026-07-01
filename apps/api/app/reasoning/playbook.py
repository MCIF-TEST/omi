"""The Investigation Playbook (AI Readiness — Phase 4).

The permanent, machine-readable methodology for how OmiSphere investigates a subject — the reasoning
workflow of a world-class OSINT analyst, encoded as ordered stages. Each stage names its purpose,
inputs, methods, the specialists that own it, its outputs, and the pitfalls to avoid. The playbook
is the shared script the council follows: it sequences evidence gathering, hypothesis generation,
counter-evidence search, the per-lens analyses, risk, calibration, and final judgment.

This is content, not control flow. The deterministic Orchestrator already sequences modules in tier
order; the playbook documents the *investigative intent* behind that sequence so the future model
reasons like a disciplined analyst rather than a pattern-matcher. Content-addressed for drift
detection; consumed as reference text, never as a second execution engine.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.evidence.bundle import digest

PLAYBOOK_VERSION = "v1"


@dataclass(frozen=True)
class PlaybookStage:
    """One stage of the investigative methodology. Immutable + content-addressed via the parent."""

    id: str
    name: str
    purpose: str
    inputs: tuple[str, ...]
    methods: tuple[str, ...]
    specialists: tuple[str, ...]
    outputs: tuple[str, ...]
    pitfalls: tuple[str, ...]


PLAYBOOK: tuple[PlaybookStage, ...] = (
    PlaybookStage(
        id="evidence_gathering", name="1. Evidence gathering",
        purpose="Assemble the read-only Evidence Bundle: the single, immutable ground truth for the "
                "whole investigation. Nothing that follows may rest on anything outside it.",
        inputs=("Investigation payload (engine ComprehensiveScanResult).",
                "Detector contributions, coordination clusters, intelligence/authenticity facets."),
        methods=("Bind the payload into the canonical bundle (stable evidence ids).",
                 "Inventory which detectors fired, which abstained, and which are supplemental.",
                 "Note data quantity (posts, members, distinct authors) — it caps confidence later."),
        specialists=("behavior_analyst", "metadata_analyst"),
        outputs=("A bound Evidence Bundle with citable ids.",
                 "An explicit map of present vs missing signals."),
        pitfalls=("Treating an abstained detector as an exculpatory or incriminating signal.",
                  "Importing any fact not present in the bundle."),
    ),
    PlaybookStage(
        id="memory_lookup", name="2. Memory lookup",
        purpose="Orient with institutional memory before forming a view — prior archetypes, past "
                "legitimate/hostile reads, k-NN neighbors — as background that calibrates priors.",
        inputs=("The bundle signature.", "The institutional memory store (KnowledgeObjects)."),
        methods=("Retrieve the most relevant, stable priors.",
                 "Label each prior's influence (supports / contradicts / neutral).",
                 "Let a legitimate-coordination prior RAISE the bar for a hostile read."),
        specialists=("memory_analyst",),
        outputs=("Labeled PriorContext (background, never proof, no citable id)."),
        pitfalls=("Citing memory as evidence (boundary violation).",
                  "Feeding a past conclusion back as present ground truth (self-reinforcement)."),
    ),
    PlaybookStage(
        id="hypothesis_generation", name="3. Hypothesis generation",
        purpose="State the candidate explanations explicitly before analyzing — so the investigation "
                "tests hypotheses rather than rationalizing the first impression.",
        inputs=("The bundle headline (engine probability + tier).", "PriorContext."),
        methods=("Frame the primary hypothesis the engine number suggests.",
                 "Name the grain (account / comment_section / campaign / narrative)."),
        specialists=("behavior_analyst", "coordination_analyst"),
        outputs=("A primary hypothesis stated as a testable proposition."),
        pitfalls=("Anchoring on the most alarming reading.",
                  "Skipping straight to a verdict without a hypothesis to test."),
    ),
    PlaybookStage(
        id="alternative_hypotheses", name="4. Alternative hypotheses",
        purpose="Enumerate the benign and mixed explanations the same evidence is consistent with — "
                "organic virality, legitimate coordination, benign automation, mixed authenticity.",
        inputs=("The primary hypothesis.", "The full bundle, including lowering signals."),
        methods=("List each plausible alternative and what evidence would confirm it.",
                 "Keep every alternative live until the evidence uniquely rules it out."),
        specialists=("counter_evidence_analyst", "campaign_analyst"),
        outputs=("A set of competing hypotheses, each with its discriminating evidence."),
        pitfalls=("Treating alternatives as a formality.",
                  "Collapsing to one explanation prematurely."),
    ),
    PlaybookStage(
        id="behavior_analysis", name="5. Behavior analysis",
        purpose="Interpret per-subject behavioral signals into cited, probabilistic findings, "
                "weighing raising and lowering behavior equally.",
        inputs=("Behavioral contributions (temporal cadence, engagement, semantic repetition).",),
        methods=("Emit one finding per informative signal, strongest first.",
                 "Keep supplemental signals (ai_writing) as zero-weight context."),
        specialists=("behavior_analyst", "language_analyst", "metadata_analyst"),
        outputs=("Cited behavioral findings with direction and evidence_refs."),
        pitfalls=("Over-reading one non-discriminative behavior.",
                  "Presenting a one-sided (raising-only) read."),
    ),
    PlaybookStage(
        id="narrative_analysis", name="6. Narrative analysis",
        purpose="Assess whether the message is spreading organically or being coordinated and "
                "amplified — at the narrative (message) grain, distinct from account campaigns.",
        inputs=("Narrative facet: inauthenticity_score, distinct_authors, narrative signals.",),
        methods=("Weigh author breadth against templated repetition.",
                 "Treat organic breadth as counter-evidence to amplification."),
        specialists=("narrative_analyst", "language_analyst"),
        outputs=("A narrative-grain coordination read (organic / mixed / suspicious)."),
        pitfalls=("Confusing a message cluster with an account campaign.",
                  "Reading virality as inauthenticity."),
    ),
    PlaybookStage(
        id="coordination_analysis", name="7. Coordination analysis",
        purpose="Determine whether accounts are acting together, and whether that coordination is "
                "inauthentic — through the corroboration gate. The platform's core question.",
        inputs=("Coordination facet: methods, clusters, single_axis_capped, convergence.",
                "Network structure (edges, clusters).", "Member authenticity/history."),
        methods=("Classify each method discriminative vs non-discriminative.",
                 "Require a discriminative, non-single-axis method before any 'coordinated' read.",
                 "Separate the fact of coordination from the question of authenticity."),
        specialists=("coordination_analyst", "network_analyst", "temporal_analyst", "campaign_analyst"),
        outputs=("A gated coordination label tied to the methods and members that fired."),
        pitfalls=("Single-axis inflation.",
                  "Equating coordination with hostility.",
                  "Labelling legitimate open coordination as a manipulation network."),
    ),
    PlaybookStage(
        id="counter_evidence_search", name="8. Counter-evidence search",
        purpose="Deliberately build the strongest benign case and challenge every incriminating "
                "finding the evidence does not uniquely support. Exculpation is mandatory.",
        inputs=("All posted findings.", "Authenticity/history facets.", "Legitimate priors."),
        methods=("Cite exculpatory evidence others under-weighted.",
                 "Attack corroboration gaps, single-axis caps, supplemental-as-suspicion errors."),
        specialists=("counter_evidence_analyst", "risk_analyst"),
        outputs=("Cited critiques that lower or neutralize weak incriminating findings."),
        pitfalls=("Reflexive contrarianism with no cited evidence.",
                  "Missing the benign explanation entirely."),
    ),
    PlaybookStage(
        id="risk_analysis", name="9. Risk analysis",
        purpose="Weigh the decision risk — false-positive cost on the precision frontier vs "
                "false-negative cost — WITHOUT inflating suspicion to justify caution.",
        inputs=("The assembled read, its confidence, and the subject's grain/prominence.",),
        methods=("Argue that high-stakes reads demand stronger corroboration.",
                 "Counsel restraint when consequence is high and evidence thin."),
        specialists=("risk_analyst",),
        outputs=("A risk-calibrated recommendation on how much corroboration to require."),
        pitfalls=("Precautionary inflation (raising suspicion to avoid a miss).",
                  "Treating prominence as guilt."),
    ),
    PlaybookStage(
        id="calibration", name="10. Calibration",
        purpose="Ensure stated confidence matches evidence strength and quantity — flag both over- "
                "and under-confidence — without changing the substantive findings.",
        inputs=("All findings + critiques with confidence.", "The corroboration facet."),
        methods=("Map corroboration + data quantity to a justified confidence band.",
                 "Demand a discriminative, non-single-axis method for a 'high' band."),
        specialists=("calibration_analyst",),
        outputs=("A recommended, evidence-justified confidence band."),
        pitfalls=("Rubber-stamping over-confident single-axis reads.",
                  "Burying a corroborated read under excessive doubt."),
    ),
    PlaybookStage(
        id="final_judgment", name="11. Final judgment",
        purpose="Adjudicate everything into ONE cited, probabilistic, schema-valid ruling a human "
                "can act on, cite, or overturn — echoing the engine number, gate-honoring.",
        inputs=("Every posted finding and critique.", "The bundle + corroboration + headline."),
        methods=("Weigh raising findings against counter-evidence, risk, and calibration.",
                 "Assign the strongest label the corroboration gate permits, no higher.",
                 "Echo the engine probability/tier; produce mandatory evidence_for / _against / "
                 "uncertainty / what_would_change_this."),
        specialists=("judge",),
        outputs=("A Governor-valid Ruling; the deterministic floor replaces it on any violation."),
        pitfalls=("Over-strong label beyond the gate.",
                  "Empty counter-evidence with no rationale.",
                  "Moving the engine number."),
    ),
)

PLAYBOOK_BY_ID: dict[str, PlaybookStage] = {s.id: s for s in PLAYBOOK}


def render_stage(stage: PlaybookStage) -> str:
    def _b(items: tuple[str, ...]) -> str:
        return "\n".join(f"  - {it}" for it in items)
    return (
        f"### {stage.name}\n"
        f"Purpose: {stage.purpose}\n"
        f"Inputs:\n{_b(stage.inputs)}\n"
        f"Methods:\n{_b(stage.methods)}\n"
        f"Specialists: {', '.join(stage.specialists)}\n"
        f"Outputs:\n{_b(stage.outputs)}\n"
        f"Pitfalls:\n{_b(stage.pitfalls)}"
    )


def render_playbook() -> str:
    """The full playbook as reference text — a disciplined OSINT investigation, stage by stage."""
    header = ("# OMI INVESTIGATION PLAYBOOK\n"
              "The reasoning workflow of a world-class OSINT analyst. Evidence before hypothesis; "
              "alternatives before conclusions; counter-evidence throughout; the engine owns the "
              "number; the Governor owns the gate.\n")
    return header + "\n\n".join(render_stage(s) for s in PLAYBOOK)


def playbook_hash() -> str:
    """Content address of the whole playbook — so a methodology edit is detectable + versionable."""
    return digest(
        {"version": PLAYBOOK_VERSION,
         "stages": [{"id": s.id, "name": s.name, "purpose": s.purpose, "inputs": list(s.inputs),
                     "methods": list(s.methods), "specialists": list(s.specialists),
                     "outputs": list(s.outputs), "pitfalls": list(s.pitfalls)} for s in PLAYBOOK]},
        prefix="pb:",
    )


__all__ = [
    "PLAYBOOK_VERSION", "PlaybookStage", "PLAYBOOK", "PLAYBOOK_BY_ID",
    "render_stage", "render_playbook", "playbook_hash",
]
