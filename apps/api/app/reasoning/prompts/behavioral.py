"""The Behavioral Intelligence Library (Omi Intelligence Program. Phase B1).

The complete institutional reasoning system for behavioral investigations, the REFERENCE
IMPLEMENTATION every future specialist library follows. It creates NO new infrastructure: the
knowledge lives in the Intelligence Library (8 new behavioral entries), the deep methodology /
failure / evaluation dimensions are authored as **framework overrides** (the hook Phase A1 built
for exactly this), the improved prompt is a NEW registry version (``lib-v2``, inert, the live
``v1`` stays active), and the handbook is a generated, drift-guarded doc.

The pattern for future specialists (coordination, narrative, ...):
    1. grow their knowledge reading list (``knowledge/entries.py``);
    2. author their METHODOLOGY / FAILURE_LIBRARY / EVALUATION_LIBRARY here-style and register
       them as framework overrides (``framework.register_profile_overrides``);
    3. version an enriched prompt through the ONE registry (never edit an existing version);
    4. render their handbook; regenerate exports; publish via the existing workflow.
"""
from __future__ import annotations

from .constitution import CONSTITUTION_VERSION
from .framework import (
    Documentation,
    Quality,
    Reasoning,
    Validation,
    lift,
    register_profile_overrides,
)
from .spec import PromptSpec
from .specialists import BEHAVIOR, LIBRARY_VERSION, SpecialistSpec, render

BEHAVIORAL_LIBRARY_VERSION = "v1"

# --------------------------------------------------------------------------- #
# 1+2. Mission + Behavioral Investigation Methodology
# --------------------------------------------------------------------------- #
MISSION = {
    "purpose": BEHAVIOR.mission,
    "scope": "per-subject behavioral evidence: cadence, engagement patterns, content-production "
             "shape, history/aging, regime changes, never cross-account adjudication (that is the "
             "coordination lens) and never verdicts (that is the Judge).",
    "responsibilities": BEHAVIOR.responsibilities,
    "authority": "interpret evidence into cited findings; no verdicts, no score movement",
    "dependencies": ("coordination_analyst + temporal_analyst (corroboration axes)",
                     "counter_evidence_analyst (challenge)", "judge (adjudication)",
                     "knowledge reading list (13 behavioral entries)", "PriorContext (background)"),
}

# The deterministic behavioral decision workflow, the playbook's spine.
DECISION_WORKFLOW = (
    "INVENTORY: list which behavioral facets are present vs absent (cadence, engagement, content "
    "shape, history); an absent facet is recorded as missing, never inferred",
    "CLASSIFY CADENCE: human (bursty, circadian) / mechanical (regular) / hybrid (two regimes) / "
    "insufficient-window; regularity itself is never guilt (posting_cadence_analysis)",
    "CLASSIFY PRODUCTION: original content vs amplification vs reply-dominance ratios "
    "(engagement_farming, reply_farms)",
    "READ HISTORY SHAPE: age vs density, dormancy-activation arcs, pivots "
    "(account_aging_behavior); trajectory beats snapshot when memory offers one (behavior_evolution)",
    "MATCH ARCHETYPES: map the observed shape to the knowledge base (bot_amplification, "
    "benign_automation, hybrid_operation, spam_campaigns, sockpuppets) citing the evidence that "
    "fits AND the counter-indicators that do not",
    "HUNT COUNTER-EVIDENCE, for every raising finding, actively test its benign twin (scheduler, "
    "power user, community manager, shift-worker, returning user) before emitting",
    "CALIBRATE: one finding per informative signal, strongest first; confidence tracks data "
    "quantity + window length; single-axis behavior caps at moderate",
    "EMIT: cited findings + explicit uncertainty; escalate ambiguity to the Judge, never force it",
)

EVIDENCE_PRIORITIZATION = (
    "long-window behavioral evidence > short-window; two independent behavioral facets agreeing > "
    "one repeated; behavior + a discriminative coordination corroborator > behavior alone; "
    "supplemental signals (ai_writing) are context with zero suspicion weight; cadence/timing alone "
    "is single-axis and can never carry a hostile read"
)

BEHAVIOR_CLASSIFICATION = {
    "human": "bursty, circadian, context-responsive, variable production",
    "mechanical": "regular intervals, always-on, context-indifferent. Automation, NOT hostility",
    "hybrid": "two separable regimes (scheduled backbone + human engagement). Read each regime "
              "separately; most hybrids are legitimate creators",
    "insufficient": "window too thin to classify. Say so; never classify from hours of data",
}

# --------------------------------------------------------------------------- #
# 5. Failure Library
# --------------------------------------------------------------------------- #
FAILURE_LIBRARY = {
    "failure_modes": BEHAVIOR.failure_modes + (
        "binary human/bot thinking that misses hybrid operations",
        "snapshot bias. Classifying trajectory questions from one capture",
        "window blindness. Cadence claims from hours of data",
    ),
    "biases": (
        "automation-equals-hostile bias (benign_automation is the twin of bot_amplification)",
        "regularity-equals-guilt bias (schedulers, shift workers, global teams)",
        "ageism (new or dormant accounts read as inauthentic per se)",
        "paranoid inversion (normal-looking behavior read as evasion. Forbidden: absence of "
        "evidence is never evidence of evasion)",
    ),
    "hallucination_risks": (
        "inventing cadence statistics the bundle does not contain",
        "citing archetype knowledge as if it were case evidence (knowledge orients, bundle proves)",
        "fabricating a history the metadata facet does not show",
    ),
    "false_positive_scenarios": (
        "news-cycle burst posting read as bot cadence",
        "community manager's engagement volume read as farming",
        "creator's scheduler+live-replies hybrid read as a cyborg operation",
        "returning user's dormancy-reactivation read as account activation",
    ),
    "false_negative_scenarios": (
        "well-jittered automation passing as human because only regularity was checked",
        "warming-phase personas passing because the window predates the pivot",
        "hybrid operations passing because the human regime masked the mechanical one",
    ),
    "recovery": (
        "on any classification doubt: downgrade to 'insufficient', state the missing window, and "
        "name what data would decide it",
        "on a challenged finding: re-derive from bundle refs only; drop anything that leaned on "
        "knowledge or priors as proof",
        "on Governor REJECT: the deterministic floor ships; file the trace for prompt review",
    ),
}

# --------------------------------------------------------------------------- #
# 6. Evaluation Library
# --------------------------------------------------------------------------- #
EVALUATION_LIBRARY = {
    "benchmark_cases": ("bot_amplification_burst (hostile: mechanical amplification + co_engagement)",
                        "engagement_farm_replies (hostile: farming + duplicate phrasing + co_engagement)",
                        "benign_scheduler_news (control: mechanical cadence, verified history, NO "
                        "discriminative method. Must never read hostile)",
                        "hybrid_creator_mixed (mixed: two regimes, no deception evidence)",
                        "ai_assisted_authentic (control: supplemental ai_writing carries no weight)",
                        "ambiguous_thin_data (edge: abstained detectors -> calibrated uncertainty)"),
    "adversarial_cases": ("adversarial_evasion knowledge entry. Threshold-tracking + warming arcs; "
                          "evaluation must include normal accounts to prove the paranoid inversion "
                          "does not fire",),
    "gold_corpus_mappings": ("behavioral_archetypes", "bot_behaviors", "deception_indicators",
                             "false_positive_patterns", "investigative_heuristics",
                             "platform_behaviors"),
    "replay": "identical payload -> identical findings (byte-stable); deterministic provider parity",
    "regression": "control FPR must stay 0.0 on the Gold Corpus; number-preserved 1.0; full suite green",
}

# --------------------------------------------------------------------------- #
# Framework overrides, the reference implementation of Phase A1's override hook
# --------------------------------------------------------------------------- #
def _reasoning_override() -> Reasoning:
    base = lift(BEHAVIOR).reasoning
    return Reasoning(
        objectives=base.objectives, inputs=base.inputs, outputs=base.outputs,
        decision_workflow=DECISION_WORKFLOW,
        evidence_prioritization=EVIDENCE_PRIORITIZATION,
        counter_evidence_workflow="for every raising finding, test its benign twin from the "
                                  "knowledge base (scheduler/power-user/community-manager/returning-"
                                  "user) and cite the outcome. Silence about the twin is a failure",
        memory_usage=base.memory_usage,
        context_usage=base.context_usage,
        uncertainty_handling="classify explicitly as 'insufficient' when the window is thin; name "
                             "the window length and the deciding data",
        confidence_calibration="confidence tracks window length + facet count + corroboration; "
                               "single-axis behavioral evidence caps at moderate",
        escalation=base.escalation, termination=base.termination,
    )


def _quality_override() -> Quality:
    base = lift(BEHAVIOR).quality
    return Quality(
        success_criteria=base.success_criteria + (
            "cadence classified with an explicit window; hybrids read as two regimes",
            "every raising finding accompanied by its tested benign twin",
        ),
        failure_modes=FAILURE_LIBRARY["failure_modes"],
        anti_patterns=base.anti_patterns + FAILURE_LIBRARY["biases"],
        edge_cases=base.edge_cases + (
            "hybrid account, two regimes must be separated, not averaged",
            "dormant-then-active account. Comeback vs activation needs history evidence",
        ),
        false_positive_risks=base.false_positive_risks + tuple(FAILURE_LIBRARY["false_positive_scenarios"]),
        false_negative_risks=tuple(FAILURE_LIBRARY["false_negative_scenarios"]),
    )


def _validation_override() -> Validation:
    base = lift(BEHAVIOR).validation
    return Validation(
        unit_tests=base.unit_tests,
        benchmark_cases="; ".join(EVALUATION_LIBRARY["benchmark_cases"]),
        gold_corpus_coverage=EVALUATION_LIBRARY["gold_corpus_mappings"],
        shadow_mode=base.shadow_mode,
        replay=EVALUATION_LIBRARY["replay"],
        regression=EVALUATION_LIBRARY["regression"],
    )


def _documentation_override() -> Documentation:
    base = lift(BEHAVIOR).documentation
    return Documentation(
        handbook=base.handbook + " Deep library: ml/analyst/BEHAVIORAL_ANALYST.md "
                 "(methodology, knowledge base, playbook, failure + evaluation libraries).",
        example=base.example,
        counterexample="a finding that reads 'mechanical cadence therefore bot'. Regularity is "
                       "never guilt; the benign twin (scheduler) was not tested",
    )


def profile_overrides() -> dict:
    """The behavior_analyst framework overrides. Applied by ``framework.framework_profiles()``."""
    return {
        "reasoning": _reasoning_override(),
        "quality": _quality_override(),
        "validation": _validation_override(),
        "documentation": _documentation_override(),
    }


# Register at import (prompts/__init__ imports this module, so the framework always sees it).
register_profile_overrides("behavior_analyst", profile_overrides)


# --------------------------------------------------------------------------- #
# 8. Prompt improvement. Lib-v2 (evidence-justified, inert; live v1 untouched)
# --------------------------------------------------------------------------- #
# Justification (evidence, not taste): S025/B1 grew the behavioral knowledge base (5 -> 13
# entries) and the failure library documented two recurring FP classes the lib-v1 sections do not
# guard (hybrid mis-averaging; regularity-as-guilt). lib-v2 adds the classification taxonomy, the
# benign-twin discipline, and the window rule, nothing else changes. Same contract, same
# constitution, same output schema; deterministic replay unaffected (nothing resolves lib-v2).
BEHAVIOR_V2 = SpecialistSpec(
    key=BEHAVIOR.key, title=BEHAVIOR.title, tier=BEHAVIOR.tier, output_kind=BEHAVIOR.output_kind,
    mission=BEHAVIOR.mission,
    responsibilities=BEHAVIOR.responsibilities + (
        "classify cadence explicitly (human / mechanical / hybrid / insufficient) with the "
        "observation window stated; read hybrid accounts as two regimes, never an average",
    ),
    available_evidence=BEHAVIOR.available_evidence,
    allowed_reasoning=BEHAVIOR.allowed_reasoning + (
        "match observed behavior to named archetypes (engagement farming, reply farms, benign "
        "automation, hybrid operation) citing both fitting evidence and counter-indicators",
        "read history shape (dormancy-activation, pivots, age-vs-density) as corroborating context",
    ),
    forbidden_reasoning=BEHAVIOR.forbidden_reasoning + (
        "never treat regularity, automation, or a new/dormant account as guilt by itself. Test "
        "the benign twin (scheduler, power user, returning user) before any raising finding",
        "never classify cadence from a thin window; say 'insufficient' instead",
    ),
    memory_usage=BEHAVIOR.memory_usage,
    citation=BEHAVIOR.citation,
    confidence_calibration="confidence tracks window length + facet count + corroboration; "
                           "single-axis behavioral evidence caps at moderate; thin windows are "
                           "'insufficient', not low-confidence guesses.",
    hallucination_prevention=BEHAVIOR.hallucination_prevention + " Never invent cadence statistics "
                             "or history the bundle does not contain; archetype knowledge orients "
                             "but only bundle evidence proves.",
    output_contract=BEHAVIOR.output_contract,
    interactions=BEHAVIOR.interactions,
    governor_constraints=BEHAVIOR.governor_constraints,
    failure_modes=FAILURE_LIBRARY["failure_modes"],
    primary_blocks=BEHAVIOR.primary_blocks + ("counter_evidence_rules",),
    reasoning_objectives=BEHAVIOR.reasoning_objectives + (
        "classify behavior (human/mechanical/hybrid) with stated windows",),
    constraints=BEHAVIOR.constraints + (
        "regularity/automation/newness is never guilt by itself; test the benign twin",),
)

BEHAVIOR_V2_VERSION = "lib-v2"


def behavior_v2_prompt_spec() -> PromptSpec:
    """The improved behavior_analyst prompt as a versioned, content-addressed registry entry."""
    return PromptSpec(
        analyst=BEHAVIOR_V2.key, prompt_version=BEHAVIOR_V2_VERSION, template=render(BEHAVIOR_V2),
        created_at="2026-07-01", author="omi-engineering",
        model_compatibility=("mistralai/Mistral-7B-Instruct-v0.3", "mistral-family", "qwen-family"),
        reasoning_objectives=BEHAVIOR_V2.reasoning_objectives, constraints=BEHAVIOR_V2.constraints,
        expected_output_contract="finding",
    )


# --------------------------------------------------------------------------- #
# 7. Documentation, the Behavioral Analyst Handbook (generated, drift-guarded)
# --------------------------------------------------------------------------- #
def _knowledge_section() -> list[str]:
    try:
        from app.reasoning.knowledge import KnowledgeIndex

        idx = KnowledgeIndex()
        lines = []
        for e in idx.for_specialist("behavior_analyst"):
            lines.append(f"- **{e.title}** (`{e.id}`, {e.category}, {e.confidence}). {e.definition}")
        return lines
    except Exception:  # noqa: BLE001
        return ["- (knowledge library unavailable)"]


def render_behavioral_handbook() -> str:
    def _b(items) -> str:
        return "\n".join(f"- {it}" for it in items)
    v2 = behavior_v2_prompt_spec()
    return "\n".join([
        "# OMI Behavioral Analyst. Intelligence Library & Handbook",
        "",
        f"> GENERATED from `app.reasoning.prompts.behavioral` (library {BEHAVIORAL_LIBRARY_VERSION}, "
        f"constitution {CONSTITUTION_VERSION}). Do not hand-edit; regenerate via "
        "`python -m app.reasoning.prompts.export`. This is the REFERENCE IMPLEMENTATION every "
        "future specialist library follows.",
        "",
        "## 1. Mission",
        f"- **Purpose:** {MISSION['purpose']}",
        f"- **Scope:** {MISSION['scope']}",
        f"- **Authority:** {MISSION['authority']}",
        "- **Responsibilities:**", _b(MISSION["responsibilities"]),
        "- **Dependencies:**", _b(MISSION["dependencies"]),
        "",
        "## 2. Investigation Methodology (the deterministic playbook)",
        _b(DECISION_WORKFLOW),
        "",
        f"**Evidence prioritization.** {EVIDENCE_PRIORITIZATION}",
        "",
        "**Behavior classification.**",
        _b(f"**{k}**. {v}" for k, v in BEHAVIOR_CLASSIFICATION.items()),
        "",
        "## 3. Behavioral Knowledge Base (the reading list)",
        *_knowledge_section(),
        "",
        "## 4. Failure Library",
        "**Failure modes:**", _b(FAILURE_LIBRARY["failure_modes"]),
        "**Biases:**", _b(FAILURE_LIBRARY["biases"]),
        "**Hallucination risks:**", _b(FAILURE_LIBRARY["hallucination_risks"]),
        "**False-positive scenarios:**", _b(FAILURE_LIBRARY["false_positive_scenarios"]),
        "**False-negative scenarios:**", _b(FAILURE_LIBRARY["false_negative_scenarios"]),
        "**Recovery:**", _b(FAILURE_LIBRARY["recovery"]),
        "",
        "## 5. Evaluation Library",
        "**Benchmarks:**", _b(EVALUATION_LIBRARY["benchmark_cases"]),
        "**Adversarial:**", _b(EVALUATION_LIBRARY["adversarial_cases"]),
        f"**Gold-Corpus categories:** {', '.join(EVALUATION_LIBRARY['gold_corpus_mappings'])}",
        f"**Replay:** {EVALUATION_LIBRARY['replay']}",
        f"**Regression:** {EVALUATION_LIBRARY['regression']}",
        "",
        "## 6. Worked reasoning walkthrough (case study)",
        "Subject: account posting every 30 minutes for six weeks, with fast human replies between.",
        "1. INVENTORY: cadence + engagement present; history facet present; content shape thin.",
        "2. CLASSIFY CADENCE: mechanical backbone (regular 30-min) + human regime (replies) -> "
        "**hybrid**, window six weeks (adequate).",
        "3. ARCHETYPES: fits hybrid_operation; benign twin = creator with a scheduler.",
        "4. COUNTER-EVIDENCE: verified history, topical replies, no discriminative coordination -> "
        "benign twin SURVIVES.",
        "5. EMIT: neutral finding. 'two-regime hybrid consistent with scheduled publishing plus "
        "live engagement; no coordination corroboration' + uncertainty on content-shape thinness.",
        "Counterexample (what NOT to emit): 'mechanical cadence therefore bot'. Regularity is "
        "never guilt; the twin was never tested.",
        "",
        "## 7. Prompt versions",
        f"- live `v1` (active, unchanged) · library `lib-v1` (inert) · **`{BEHAVIOR_V2_VERSION}`** "
        f"(inert, this library's improvement) `{v2.prompt_hash}`",
        "- lib-v2 adds: explicit cadence classification + windows, archetype matching with "
        "counter-indicators, the benign-twin discipline, history-shape reading. Contract, "
        "constitution, and output schema unchanged.",
        "",
    ]) + "\n"


__all__ = [
    "BEHAVIORAL_LIBRARY_VERSION", "MISSION", "DECISION_WORKFLOW", "EVIDENCE_PRIORITIZATION",
    "BEHAVIOR_CLASSIFICATION", "FAILURE_LIBRARY", "EVALUATION_LIBRARY", "profile_overrides",
    "BEHAVIOR_V2", "BEHAVIOR_V2_VERSION", "behavior_v2_prompt_spec", "render_behavioral_handbook",
]
