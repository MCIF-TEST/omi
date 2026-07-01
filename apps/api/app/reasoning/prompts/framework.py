"""The Specialist Intelligence Framework (Omi Intelligence Program — Phase A1).

The permanent framework every current and future AI specialist inherits. It does NOT replace the
Specialist Library (``specialists.SpecialistSpec`` remains the authored source of each specialist's
mission and thirteen prompt sections) — it EXTENDS it. A :class:`SpecialistProfile` composes the
mandated dimensions:

* IDENTITY      — name, mission, tier, responsibilities, authority, dependencies
* REASONING     — objectives, inputs, outputs, decision workflow, evidence prioritization,
                  counter-evidence workflow, memory/context usage, uncertainty, calibration,
                  escalation, termination
* GOVERNANCE    — Governor compatibility, constitutional requirements, evidence/citation rules,
                  memory boundaries, explainability, hallucination prevention
* TECHNICAL     — prompt version + hash, JSON schema, output contract, context requirements,
                  retrieval strategy, token budget, model compatibility
* QUALITY       — success criteria, failure modes, anti-patterns, edge cases, FP/FN risks
* VALIDATION    — unit tests, benchmark cases, Gold-Corpus coverage, Shadow Mode, replay, regression
* DOCUMENTATION — handbook, examples, counterexamples

``lift()`` derives a COMPLETE profile from an existing ``SpecialistSpec`` (single source of truth —
identity/reasoning/governance come from the authored spec; quality/validation/technical/
documentation are derived by tier + output kind, overridable per specialist), so the thirteen
existing specialists inherit the framework with zero re-authoring and zero duplication.
``new_specialist()`` is the TEMPLATE: a future specialist (e.g. ``strategy_analyst``,
``investigation_planner``) needs only its authored sections; the framework supplies the rest and
registers through the ONE Prompt Registry. Tier-3 ``Governor`` and ``Floor`` are represented
honestly as CODE-BACKED profiles (``execution='deterministic-code'``): they are never prompt- or
model-driven, by constitution.

Content-addressed (``sf:``); serialized into the existing prompt catalog (no parallel metadata
asset); rendered into the contributor handbook. GitHub is the single source of truth.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.evidence.bundle import digest

from .constitution import CONSTITUTION_VERSION, constitution_hash
from .specialists import LIBRARY_VERSION, SPECIALISTS, SPECIALISTS_BY_KEY, SpecialistSpec

FRAMEWORK_VERSION = "v1"

EXECUTION_MODEL = "model"                      # prompt-driven; resolves from the Prompt Registry
EXECUTION_CODE = "deterministic-code"          # code-backed; never prompt- or model-driven
_VALID_EXECUTION = (EXECUTION_MODEL, EXECUTION_CODE)

_AUTHORITY_BY_TIER = {
    1: "interpret evidence into cited artifacts; no verdicts, no score movement",
    2: "challenge, calibrate, and advise; may lower or bound a read, never raise the number",
    3: "adjudicate (Judge) / validate (Governor) / guarantee (Floor); the only tier that rules",
}

# Framework-level derivation tables (tier / output-kind driven; overridable per specialist). ---- #
_ANTI_PATTERNS = {
    "finding": ("verdict smuggling — a finding that reads like a ruling",
                "citing a supplemental signal as raising evidence",
                "restating one observation as many findings (double-counting)"),
    "critique": ("contrarianism without cited exculpatory evidence",
                 "raising suspicion under the guise of caution (precautionary inflation)"),
    "ruling": ("assigning a coordination label beyond the corroboration gate",
               "empty evidence_against with no stated rationale (F5)",
               "prose outside the JSON object"),
    "memory": ("attaching a citable id to a prior (memory-boundary violation)",
               "presenting a past conclusion as present ground truth"),
}
_EDGE_CASES = (
    "thin data — most detectors abstained; correct output is calibrated uncertainty",
    "empty facet — the specialist's lens has no evidence; emit nothing rather than invent",
    "conflicting evidence — raising and lowering signals of similar weight; report both",
    "single-axis-capped bundle — confidence and labels are capped by construction",
)
_FALSE_NEGATIVE_RISKS = (
    "over-gating: demanding corroboration so strict that real coordination is missed",
    "burying a corroborated read under excessive uncertainty",
)
_TOKEN_BUDGET = {"finding": 1024, "critique": 1024, "memory": 512, "ruling": 2048}
_JSON_SCHEMA = {
    "ruling": "schema/analyst_response_schema.json",
    "finding": "council finding artifact contract",
    "critique": "council critique artifact contract",
    "memory": "council memory artifact contract",
}
_EXAMPLES = {
    "finding": ('{"findings":[{"signal":"temporal","claim":"Burst cadence is consistent with '
                'elevated suspicion.","direction":"raises","evidence_refs":["ev:..."]}],'
                '"uncertainty":["only 12 posts observed"]}'),
    "critique": ('{"critiques":[{"target":"temporal finding","challenge":"The burst coincides with '
                 'a real-world event; organic reaction is the leading explanation.",'
                 '"direction":"lowers","evidence_refs":["ev:..."]}],"uncertainty":[]}'),
    "ruling": ("one schema-valid analyst assessment object (verdict, echoed number, evidence_for/"
               "against, uncertainty, what_would_change_this, corroboration)"),
    "memory": ('{"priors":[{"type":"BehavioralArchetype","label":"bursty posting archetype",'
               '"influence":"supports","stability":0.8,"note":"institutional memory — background, '
               'never proof"}],"uncertainty":[]}'),
}
_COUNTEREXAMPLES = {
    "finding": 'a finding citing "ev:fabricated123" — unresolvable ref; whole output invalid → floor',
    "critique": "a critique with direction='raises' — critiques may lower or bound, never raise",
    "ruling": 'a ruling with suspicion_probability != the engine number — Governor REJECT',
    "memory": 'a prior carrying evidence_refs — memory-boundary violation; dropped',
}


@dataclass(frozen=True)
class Identity:
    name: str
    title: str
    mission: str
    tier: int
    responsibilities: tuple[str, ...]
    authority: str
    dependencies: tuple[str, ...]              # interactions + constitutional blocks + knowledge


@dataclass(frozen=True)
class Reasoning:
    objectives: tuple[str, ...]
    inputs: tuple[str, ...]
    outputs: str
    decision_workflow: tuple[str, ...]
    evidence_prioritization: str
    counter_evidence_workflow: str
    memory_usage: str
    context_usage: str
    uncertainty_handling: str
    confidence_calibration: str
    escalation: str
    termination: str


@dataclass(frozen=True)
class Governance:
    governor_compatibility: str
    constitutional_requirements: tuple[str, ...]
    evidence_rules: str
    citation_rules: str
    memory_boundaries: str
    explainability: str
    hallucination_prevention: str


@dataclass(frozen=True)
class Technical:
    prompt_version: str | None                 # None for code-backed specialists
    prompt_hash: str | None
    json_schema: str
    output_contract: str
    context_requirements: tuple[str, ...]
    retrieval_strategy: str
    token_budget: int
    model_compatibility: tuple[str, ...]


@dataclass(frozen=True)
class Quality:
    success_criteria: tuple[str, ...]
    failure_modes: tuple[str, ...]
    anti_patterns: tuple[str, ...]
    edge_cases: tuple[str, ...]
    false_positive_risks: tuple[str, ...]
    false_negative_risks: tuple[str, ...]


@dataclass(frozen=True)
class Validation:
    unit_tests: str
    benchmark_cases: str
    gold_corpus_coverage: tuple[str, ...]
    shadow_mode: str
    replay: str
    regression: str


@dataclass(frozen=True)
class Documentation:
    handbook: str
    example: str
    counterexample: str


@dataclass(frozen=True)
class SpecialistProfile:
    """One specialist's complete framework record — every mandated dimension, one object."""

    key: str
    execution: str                             # model | deterministic-code
    identity: Identity
    reasoning: Reasoning
    governance: Governance
    technical: Technical
    quality: Quality
    validation: Validation
    documentation: Documentation

    def __post_init__(self) -> None:
        if self.execution not in _VALID_EXECUTION:
            raise ValueError(f"unknown execution {self.execution!r}")

    def to_record(self) -> dict:
        """Deterministic, serializable framework record (feeds the catalog + the hash)."""
        return {
            "key": self.key, "execution": self.execution,
            "identity": {"name": self.identity.name, "title": self.identity.title,
                         "mission": self.identity.mission, "tier": self.identity.tier,
                         "responsibilities": list(self.identity.responsibilities),
                         "authority": self.identity.authority,
                         "dependencies": list(self.identity.dependencies)},
            "reasoning": {"objectives": list(self.reasoning.objectives),
                          "inputs": list(self.reasoning.inputs), "outputs": self.reasoning.outputs,
                          "decision_workflow": list(self.reasoning.decision_workflow),
                          "evidence_prioritization": self.reasoning.evidence_prioritization,
                          "counter_evidence_workflow": self.reasoning.counter_evidence_workflow,
                          "memory_usage": self.reasoning.memory_usage,
                          "context_usage": self.reasoning.context_usage,
                          "uncertainty_handling": self.reasoning.uncertainty_handling,
                          "confidence_calibration": self.reasoning.confidence_calibration,
                          "escalation": self.reasoning.escalation,
                          "termination": self.reasoning.termination},
            "governance": {"governor_compatibility": self.governance.governor_compatibility,
                           "constitutional_requirements": list(self.governance.constitutional_requirements),
                           "evidence_rules": self.governance.evidence_rules,
                           "citation_rules": self.governance.citation_rules,
                           "memory_boundaries": self.governance.memory_boundaries,
                           "explainability": self.governance.explainability,
                           "hallucination_prevention": self.governance.hallucination_prevention},
            "technical": {"prompt_version": self.technical.prompt_version,
                          "prompt_hash": self.technical.prompt_hash,
                          "json_schema": self.technical.json_schema,
                          "output_contract": self.technical.output_contract,
                          "context_requirements": list(self.technical.context_requirements),
                          "retrieval_strategy": self.technical.retrieval_strategy,
                          "token_budget": self.technical.token_budget,
                          "model_compatibility": list(self.technical.model_compatibility)},
            "quality": {"success_criteria": list(self.quality.success_criteria),
                        "failure_modes": list(self.quality.failure_modes),
                        "anti_patterns": list(self.quality.anti_patterns),
                        "edge_cases": list(self.quality.edge_cases),
                        "false_positive_risks": list(self.quality.false_positive_risks),
                        "false_negative_risks": list(self.quality.false_negative_risks)},
            "validation": {"unit_tests": self.validation.unit_tests,
                           "benchmark_cases": self.validation.benchmark_cases,
                           "gold_corpus_coverage": list(self.validation.gold_corpus_coverage),
                           "shadow_mode": self.validation.shadow_mode,
                           "replay": self.validation.replay,
                           "regression": self.validation.regression},
            "documentation": {"handbook": self.documentation.handbook,
                              "example": self.documentation.example,
                              "counterexample": self.documentation.counterexample},
            "constitution_version": CONSTITUTION_VERSION,
        }


def validate_profile(profile: SpecialistProfile) -> list[str]:
    """Framework-level completeness check. Empty list == valid. Deterministic; used by CI."""
    issues: list[str] = []
    ident, tech = profile.identity, profile.technical
    if ident.tier not in (1, 2, 3):
        issues.append(f"{profile.key}: tier must be 1..3")
    for label, value in (("mission", ident.mission), ("authority", ident.authority),
                         ("outputs", profile.reasoning.outputs),
                         ("escalation", profile.reasoning.escalation),
                         ("termination", profile.reasoning.termination),
                         ("governor_compatibility", profile.governance.governor_compatibility),
                         ("hallucination_prevention", profile.governance.hallucination_prevention),
                         ("retrieval_strategy", tech.retrieval_strategy),
                         ("unit_tests", profile.validation.unit_tests),
                         ("handbook", profile.documentation.handbook),
                         ("example", profile.documentation.example),
                         ("counterexample", profile.documentation.counterexample)):
        if not value:
            issues.append(f"{profile.key}: {label} is empty")
    for label, seq in (("responsibilities", ident.responsibilities),
                       ("decision_workflow", profile.reasoning.decision_workflow),
                       ("constitutional_requirements", profile.governance.constitutional_requirements),
                       ("success_criteria", profile.quality.success_criteria),
                       ("failure_modes", profile.quality.failure_modes),
                       ("anti_patterns", profile.quality.anti_patterns),
                       ("edge_cases", profile.quality.edge_cases)):
        if not seq:
            issues.append(f"{profile.key}: {label} is empty")
    if tech.token_budget <= 0:
        issues.append(f"{profile.key}: token_budget must be positive")
    if profile.execution == EXECUTION_MODEL:
        if not (tech.prompt_hash or "").startswith("ph:"):
            issues.append(f"{profile.key}: model-backed specialist must carry a registry prompt hash")
    else:
        if tech.prompt_hash is not None or tech.prompt_version is not None:
            issues.append(f"{profile.key}: code-backed specialist must not carry a prompt (never "
                          "prompt- or model-driven)")
    return issues


# --------------------------------------------------------------------------- #
# lift() — derive a complete profile from an authored SpecialistSpec (the inheritance path)
# --------------------------------------------------------------------------- #
def _knowledge_reading_list(key: str) -> tuple[int, tuple[str, ...]]:
    """(entry count, categories) from the Intelligence Library — lazily, never raising."""
    try:
        from app.reasoning.knowledge import default_library, specialist_dependencies

        lib = default_library()
        ids = specialist_dependencies(lib).get(key, [])
        cats = sorted({lib.get(i).category for i in ids})
        return len(ids), tuple(cats)
    except Exception:  # noqa: BLE001 — knowledge layer optional at import time
        return 0, ()


def _decision_workflow(spec: SpecialistSpec) -> tuple[str, ...]:
    common = ("read the Evidence Bundle facet(s) this contract permits",
              "retrieve the knowledge reading list + PriorContext (background, never proof)")
    if spec.tier == 1:
        return common + ("form one candidate claim per informative signal",
                         "test each claim against its counter-indicators before emitting",
                         "emit cited artifacts, strongest first; record uncertainty")
    if spec.tier == 2:
        return common + ("enumerate the benign/mixed hypotheses the evidence also supports",
                         "challenge every under-supported raising claim with cited exculpation",
                         "emit critiques; recommend calibration, never a verdict")
    return common + ("weigh all posted findings against critiques and calibration advice",
                     "assign the strongest label the corroboration gate permits, no higher",
                     "emit ONE schema-valid ruling; the Governor validates it")


def lift(spec: SpecialistSpec, **overrides) -> SpecialistProfile:
    """Derive a COMPLETE framework profile from an authored ``SpecialistSpec``.

    Identity/reasoning/governance come from the authored spec (single source of truth); quality,
    validation, technical, and documentation are framework defaults derived by tier + output kind.
    Any dimension can be overridden by keyword (``quality=...``) — the template hook future
    specialists use. Never edits the spec; never duplicates authored content."""
    from .registry import default_registry

    ps = default_registry().resolve(spec.key, LIBRARY_VERSION)
    n_know, know_cats = _knowledge_reading_list(spec.key)
    return _lift_with(spec, ps, n_know, know_cats, **overrides)


# --------------------------------------------------------------------------- #
# Tier-3 code-backed profiles — Governor + Floor are never prompt- or model-driven
# --------------------------------------------------------------------------- #
def _code_backed(key: str, title: str, mission: str, responsibilities: tuple[str, ...],
                 outputs: str, workflow: tuple[str, ...]) -> SpecialistProfile:
    return SpecialistProfile(
        key=key, execution=EXECUTION_CODE,
        identity=Identity(name=key, title=title, mission=mission, tier=3,
                          responsibilities=responsibilities, authority=_AUTHORITY_BY_TIER[3],
                          dependencies=("constitution:governor_constraints",)),
        reasoning=Reasoning(
            objectives=(mission,), inputs=("the council ruling + the Evidence Bundle",),
            outputs=outputs, decision_workflow=workflow,
            evidence_prioritization="rule-based; no interpretation",
            counter_evidence_workflow="not applicable — validation, not reasoning",
            memory_usage="none; operates only on the ruling + bundle",
            context_usage="none beyond the ruling + bundle",
            uncertainty_handling="deterministic: a rule either fires or it does not",
            confidence_calibration="not applicable — binary validation",
            escalation="REJECT hands the case to the deterministic Floor" if key == "governor"
            else "none — the Floor is the terminal guarantee",
            termination="always terminates with a deterministic result",
        ),
        governance=Governance(
            governor_compatibility="IS the enforcement layer" if key == "governor"
            else "always Governor-valid by construction",
            constitutional_requirements=(f"constitution {CONSTITUTION_VERSION}", "mandatory, never skipped"),
            evidence_rules="enforced in code (citation resolution, corroboration gate)",
            citation_rules="verifies every evidence_ref resolves against the bundle",
            memory_boundaries="rejects any prior cited as evidence",
            explainability="emits a ValidationTrace (vt:) with violation codes"
            if key == "governor" else "fully deterministic and replayable",
            hallucination_prevention="cannot hallucinate — no generation, code only",
        ),
        technical=Technical(prompt_version=None, prompt_hash=None,
                            json_schema=_JSON_SCHEMA["ruling"], output_contract="validation_trace"
                            if key == "governor" else "analyst_assessment",
                            context_requirements=("ruling", "bundle"),
                            retrieval_strategy="none — pure function of ruling + bundle",
                            token_budget=0 or 1, model_compatibility=()),
        quality=Quality(
            success_criteria=("every ruling validated; zero ungoverned outputs ship",),
            failure_modes=("misconfiguration disabling the gate (prevented: mandatory in the "
                           "Orchestrator, no bypass path)",),
            anti_patterns=("softening validation to raise permit rates",),
            edge_cases=_EDGE_CASES,
            false_positive_risks=("over-rejection would only ever degrade to the Floor — safe",),
            false_negative_risks=("an under-specified rule missing a violation class",),
        ),
        validation=Validation(
            unit_tests=f"tests must cover: every violation class fires; '{key}' cannot be bypassed",
            benchmark_cases="Governor verdict asserted on every Gold-Corpus evaluation",
            gold_corpus_coverage=("all categories — the gate runs on every case",),
            shadow_mode="validates both production and shadow rulings identically",
            replay="pure function: identical input -> identical trace",
            regression="any permit/reject flip on the corpus is a regression",
        ),
        documentation=Documentation(
            handbook=f"{title} — Tier 3, CODE-BACKED. {mission} Never prompt- or model-driven.",
            example="Governor.validate(ruling, bundle) -> ValidationTrace(permit)" if key == "governor"
            else "FloorJudge.run(view) -> always-valid deterministic Ruling",
            counterexample="a prompt-driven governor — unconstitutional; validation must be code",
        ),
    )


GOVERNOR_PROFILE = _code_backed(
    "governor", "OMI GOVERNOR",
    "Validate every council ruling against the constitution — mandatory, deterministic, unskippable.",
    ("re-check citations, number echo, corroboration gate, counter-evidence, banned phrasing",
     "PERMIT or REJECT with an auditable ValidationTrace",
     "on REJECT, route to the deterministic Floor"),
    "ValidationTrace (vt:) — permit/reject + violation codes",
    ("receive the ruling + bundle", "run every constitutional check in code",
     "emit the trace; REJECT -> Floor"),
)

FLOOR_PROFILE = _code_backed(
    "floor", "OMI FLOOR",
    "Guarantee a valid, governed assessment exists no matter what fails above — the deterministic "
    "always-on judge of last resort.",
    ("produce a schema-valid, echo-preserving assessment from the bundle alone",
     "serve as the fallback for provider failure, invalid output, or Governor REJECT"),
    "a deterministic, schema-valid analyst assessment (Ruling)",
    ("receive the bundle view", "generate the deterministic assessment",
     "return it (itself Governor-validated)"),
)


# --------------------------------------------------------------------------- #
# The template for FUTURE specialists + the worked example
# --------------------------------------------------------------------------- #
def new_specialist(spec: SpecialistSpec, *, registry=None, **overrides) -> SpecialistProfile:
    """THE TEMPLATE. A future specialist (strategy_analyst, investigation_planner, ...) authors ONE
    ``SpecialistSpec`` (its thirteen sections); the framework derives everything else. Pass a
    ``registry`` to also version its prompt through the ONE Prompt Registry (inert — it activates
    nothing). Returns the complete, validated profile; raises on incompleteness so an unfinished
    specialist cannot enter the system."""
    from .specialists import to_prompt_spec

    if spec.key in SPECIALISTS_BY_KEY:                 # already a library specialist
        profile = lift(spec, **overrides)
    else:                                              # brand-new: derive from its rendered prompt
        ps = to_prompt_spec(spec)
        if registry is not None:
            registry.register(ps, activate=False)
        n_know, know_cats = _knowledge_reading_list(spec.key)
        profile = _lift_with(spec, ps, n_know, know_cats, **overrides)
    issues = validate_profile(profile)
    if issues:
        raise ValueError(f"incomplete specialist {spec.key!r}: {issues[:5]}")
    return profile


def _lift_with(spec: SpecialistSpec, ps, n_know: int, know_cats: tuple[str, ...], **overrides,
               ) -> SpecialistProfile:
    """Core derivation given an explicit rendered PromptSpec (no registry dependency)."""
    identity = Identity(
        name=spec.key, title=spec.title, mission=spec.mission, tier=spec.tier,
        responsibilities=spec.responsibilities, authority=_AUTHORITY_BY_TIER[spec.tier],
        dependencies=tuple(spec.interactions) + tuple(f"constitution:{b}" for b in spec.primary_blocks)
        + ((f"knowledge:{n_know} entries",) if n_know else ()),
    )
    reasoning = Reasoning(
        objectives=spec.reasoning_objectives, inputs=spec.available_evidence,
        outputs=spec.output_contract, decision_workflow=_decision_workflow(spec),
        evidence_prioritization="discriminative + corroborated > discriminative single-axis > "
                                "non-discriminative; supplemental signals never raise suspicion",
        counter_evidence_workflow="weigh the leading benign explanation before any hostile claim; "
                                  "an empty exculpatory column must be stated, never silent",
        memory_usage=spec.memory_usage,
        context_usage="structured evidence via the projected bundle; prior_context as labeled "
                      "background; knowledge reading list as expertise — none of it citable proof",
        uncertainty_handling="name what is unknown, what data was thin, and what would change the "
                             "read; indistinguishability is itself a finding",
        confidence_calibration=spec.confidence_calibration,
        escalation="surface ambiguity to the Judge as explicit uncertainty — never force a call; "
                   "a Governor REJECT escalates to the deterministic Floor",
        termination="emit a valid artifact or nothing; on any failure the council degrades "
                    "gracefully (drop artifact -> judge -> floor), never a malformed output",
    )
    governance = Governance(
        governor_compatibility=spec.governor_constraints,
        constitutional_requirements=(f"constitution {CONSTITUTION_VERSION} ({constitution_hash()})",)
        + tuple(spec.primary_blocks),
        evidence_rules="cite only bundle evidence; discriminative vs non-discriminative is gated; "
                       "supplemental carries zero suspicion weight",
        citation_rules=spec.citation,
        memory_boundaries="priors carry no citable id; memory orients, never proves, never moves "
                          "the score",
        explainability="every claim traces to a resolvable evidence id; every ruling carries a "
                       "Governor trace id + content-addressed prompt hash",
        hallucination_prevention=spec.hallucination_prevention,
    )
    technical = Technical(
        prompt_version=ps.prompt_version, prompt_hash=ps.prompt_hash,
        json_schema=_JSON_SCHEMA[spec.output_kind], output_contract=ps.expected_output_contract,
        context_requirements=spec.available_evidence,
        retrieval_strategy=f"KnowledgeIndex.for_specialist('{spec.key}') ({n_know} entries) + "
                           "memory retrieve() PriorContext; both constant-time, off the hot path",
        token_budget=_TOKEN_BUDGET[spec.output_kind],
        model_compatibility=ps.model_compatibility,
    )
    quality = Quality(
        success_criteria=("every emitted claim carries >=1 resolvable evidence_ref",
                          "output validates against the contract on first parse",
                          "Governor PERMIT on well-formed input; zero fabricated citations")
        + spec.reasoning_objectives,
        failure_modes=spec.failure_modes, anti_patterns=_ANTI_PATTERNS[spec.output_kind],
        edge_cases=_EDGE_CASES,
        false_positive_risks=("reading legitimate coordination / benign automation as hostile "
                              "(the precision frontier)",),
        false_negative_risks=_FALSE_NEGATIVE_RISKS,
    )
    validation = Validation(
        unit_tests=f"tests must cover: contract shape, citation resolution, supplemental gating, "
                   f"and graceful fallback for '{spec.key}'",
        benchmark_cases="at least one hostile and one control Gold-Corpus case exercising this lens",
        gold_corpus_coverage=know_cats or ("coordination_techniques", "false_positive_patterns"),
        shadow_mode="evaluate via run_shadow comparison against production before any activation",
        replay="deterministic replay: identical payload -> identical artifact (byte-stable)",
        regression="full backend suite green; control FPR non-increasing on the Gold Corpus",
    )
    documentation = Documentation(
        handbook=f"{spec.title} — Tier {spec.tier} {spec.output_kind} specialist. {spec.mission}",
        example=_EXAMPLES[spec.output_kind], counterexample=_COUNTEREXAMPLES[spec.output_kind],
    )
    fields = {"identity": identity, "reasoning": reasoning, "governance": governance,
              "technical": technical, "quality": quality, "validation": validation,
              "documentation": documentation}
    fields.update(overrides)
    return SpecialistProfile(key=spec.key, execution=EXECUTION_MODEL, **fields)


def example_investigation_planner() -> SpecialistProfile:
    """The worked TEMPLATE EXAMPLE — a future Tier-2 specialist built with ``new_specialist``.

    INERT by construction: not registered in the default registry, not in the council, not
    activated, not exported. It exists so a contributor can see exactly how little a new
    specialist requires: author the thirteen sections; the framework supplies the rest."""
    spec = SpecialistSpec(
        key="investigation_planner", title="OMI INVESTIGATION PLANNER", tier=2, output_kind="critique",
        mission="Plan the investigation: decide which lenses matter for THIS subject, what evidence "
                "would be decisive, and what to collect next — advising, never ruling.",
        responsibilities=("rank the open hypotheses by decisiveness of available evidence",
                          "identify the single most informative next collection step",
                          "flag lenses whose evidence is missing so their silence is not misread"),
        available_evidence=("the full bundle inventory (which facets are present vs absent)",
                            "the corroboration state", "PriorContext (background only)"),
        allowed_reasoning=("prioritize discriminative evidence gaps over volume",
                           "recommend the cheapest test that separates the leading hypotheses"),
        forbidden_reasoning=("never assert a verdict or move the number",
                             "never treat a planned-but-uncollected signal as evidence"),
        memory_usage="priors suggest which hypotheses deserve testing first; background only.",
        citation="cite only present bundle evidence; a plan cites what exists, not what it hopes for.",
        confidence_calibration="plan confidence reflects how decisively the recommended step would "
                               "separate hypotheses.",
        hallucination_prevention="only reference facets and detectors that actually exist in the "
                                 "bundle inventory.",
        output_contract='One JSON object: {"critiques":[{"target":"investigation plan",'
                        '"challenge":"<the decisive gap / next step>","direction":"neutral",'
                        '"evidence_refs":["ev:..."]}],"uncertainty":["..."]}. Output only the JSON.',
        interactions=("advises every Tier-1 specialist on where evidence is thin",
                      "the Judge weighs the plan when recommending what_would_change_this"),
        governor_constraints="plans are critiques: neutral or lowering, never raising; the Governor "
                             "rejects a plan that smuggles suspicion.",
        failure_modes=("recommending collection for its own sake (busywork plans)",
                       "treating a missing signal as incriminating"),
        primary_blocks=("shared_investigation_rules", "uncertainty_rules", "evidence_rules"),
        reasoning_objectives=("identify the most decisive next evidence step",),
        constraints=("cite only provided bundle evidence ids; never fabricate",
                     "never assert a verdict or move the engine number",
                     "prior context is background, never proof"),
    )
    return new_specialist(spec)


# --------------------------------------------------------------------------- #
# The framework surface
# --------------------------------------------------------------------------- #
def framework_profiles() -> list[SpecialistProfile]:
    """Every governed specialist's framework profile: the 13 library specialists (lifted — zero
    re-authoring) + the 2 code-backed Tier-3 guarantees. Deterministic order by key."""
    lifted = [lift(s) for s in SPECIALISTS]
    return sorted(lifted + [GOVERNOR_PROFILE, FLOOR_PROFILE], key=lambda p: p.key)


def validate_framework() -> list[str]:
    """Framework-wide integrity: every profile complete; keys unique; tiers covered."""
    profiles = framework_profiles()
    issues: list[str] = []
    for p in profiles:
        issues.extend(validate_profile(p))
    keys = [p.key for p in profiles]
    if len(keys) != len(set(keys)):
        issues.append("duplicate profile keys")
    tiers = {p.identity.tier for p in profiles}
    if tiers != {1, 2, 3}:
        issues.append(f"tier coverage incomplete: {sorted(tiers)}")
    return issues


def framework_hash() -> str:
    """Content address of the entire framework — drift-detectable, versionable."""
    return digest({"version": FRAMEWORK_VERSION,
                   "profiles": [p.to_record() for p in framework_profiles()]}, prefix="sf:")


def render_handbook() -> str:
    """The Specialist Handbook + contributor documentation — generated from the framework so it can
    never drift from code. GitHub-side engineering doc (committed, drift-guarded)."""
    profiles = framework_profiles()
    lines = [
        "# OMI Specialist Intelligence Framework — Handbook",
        "",
        f"> GENERATED from `app.reasoning.prompts.framework` (framework {FRAMEWORK_VERSION}, "
        f"`{framework_hash()}`, constitution {CONSTITUTION_VERSION}). Do not hand-edit; "
        "regenerate via `python -m app.reasoning.prompts.export`.",
        "",
        "Every AI specialist inherits this framework. Authored content lives in ONE place (the "
        "specialist's `SpecialistSpec` — its thirteen prompt sections); the framework derives "
        "identity, reasoning workflow, governance, technical, quality, validation, and "
        "documentation dimensions from it. GitHub is the single source of truth; Hugging Face "
        "receives the synchronized catalog through the existing publish workflow.",
        "",
        "## Creating a new specialist (the template)",
        "",
        "1. Author a `SpecialistSpec` in `app/reasoning/prompts/specialists.py` (13 sections).",
        "2. Add it to `SPECIALISTS`; the library registers it in the ONE Prompt Registry as "
        "`lib-v1` (inert — nothing activates).",
        "3. `framework.lift(spec)` now yields its complete profile automatically; override any "
        "derived dimension by keyword if the defaults do not fit.",
        "4. Add its knowledge reading list (entries in `app/reasoning/knowledge/entries.py` naming "
        "the new key in `specialists`).",
        "5. Write the unit tests its validation profile names; run the full suite.",
        "6. Regenerate exports (`python -m app.reasoning.prompts.export`); commit; the existing "
        "GitHub Actions publish workflow synchronizes Hugging Face.",
        "",
        "A worked example lives in `framework.example_investigation_planner()` (inert). "
        "Counterexample: a prompt-driven Governor — validation is code, never generation.",
        "",
        "## Directory conventions",
        "",
        "- Authored specs: `app/reasoning/prompts/specialists.py` (+ constitution blocks in "
        "`constitution.py`)",
        "- Framework: `app/reasoning/prompts/framework.py` (this module)",
        "- Knowledge: `app/reasoning/knowledge/entries.py`",
        "- Exports (HF-synchronized): `ml/analyst/hf_repo/prompts/` via `export.py`",
        "- Tests: `apps/api/tests/test_specialist_framework.py` + per-specialist suites",
        "",
        "## Profiles",
        "",
    ]
    for p in profiles:
        t = p.technical
        lines += [
            f"### {p.identity.title} (`{p.key}`) — Tier {p.identity.tier} · {p.execution}",
            "",
            f"- **Mission:** {p.identity.mission}",
            f"- **Authority:** {p.identity.authority}",
            f"- **Output:** {p.reasoning.outputs[:160]}",
            f"- **Prompt:** {t.prompt_version or 'none (code-backed)'}"
            + (f" `{t.prompt_hash}`" if t.prompt_hash else ""),
            f"- **Schema:** {t.json_schema} · **Token budget:** {t.token_budget}",
            f"- **Retrieval:** {t.retrieval_strategy}",
            f"- **Escalation:** {p.reasoning.escalation}",
            f"- **Validation:** {p.validation.unit_tests}",
            f"- **Handbook:** {p.documentation.handbook}",
            f"- **Counterexample:** {p.documentation.counterexample}",
            "",
        ]
    return "\n".join(lines) + "\n"


__all__ = [
    "FRAMEWORK_VERSION", "EXECUTION_MODEL", "EXECUTION_CODE",
    "Identity", "Reasoning", "Governance", "Technical", "Quality", "Validation", "Documentation",
    "SpecialistProfile", "validate_profile", "lift", "new_specialist",
    "GOVERNOR_PROFILE", "FLOOR_PROFILE", "example_investigation_planner",
    "framework_profiles", "validate_framework", "framework_hash", "render_handbook",
]
