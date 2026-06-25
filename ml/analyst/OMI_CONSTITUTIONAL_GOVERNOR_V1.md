# OMI_CONSTITUTIONAL_GOVERNOR_V1 — The Immutable Constitutional Layer

> **Status: canonical engineering specification only.** No implementation, no
> production change, no detector / scoring / OmiScore / model / dataset / deployment
> change. This is document **#5** in the Architecture Specification Phase. It specifies
> the **interior** of the Governor whose *existence and role* are already **frozen** in
> the upstream docs; it **extends**, never redesigns them.
>
> **Frozen upstream (do not redesign):**
> ✅ `OMI_COGNITIVE_ENGINE_V1.md` — names the Governor as the deterministic immune
>    system (§7): resolve every `evidence_ref`, echo-guard, gate/cap/anchor, F1–F12,
>    reject→Deterministic Floor.
> ✅ `OMI_EVIDENCE_BUNDLE_SPEC_V1.md` — the citation system (`ev:NNNN`, `citation_index`,
>    cite-or-be-dropped), content-addressed `bundle_id`, the `epistemics` layer.
> ✅ `OMI_INTELLIGENCE_MEMORY_SYSTEM_V1.md` — the three hard lines, "memory influences
>    but never overrides," `influence_class ∈ {context, exculpatory}`, `memory_revision`.
> ✅ `OMI_REASONING_ORCHESTRATION_V1.md` — the handoff to the Governor `(Ruling,
>    blackboard, citations, corroboration state)`; cache key `(bundle_id +
>    memory_revision + contract_version)`; the two-plane split; the Floor as fallback.
>
> **Roadmap position:** #5 (this) → #6 **Analyst Evaluation Framework** → #7
> **Implementation Roadmap**, then Runtime Verification → GitHub↔HuggingFace↔Render
> validation → Core implementation → AI model integration → Evaluation → Fine-tuning →
> Continuous learning. The Governor is the runtime gate that makes those later phases
> auditable.

---

## 0. The governing idea: a constitutional court, not a reasoner

> **The Governor is a deterministic, model-free constitutional court. It reads the
> assembled assessment and its full deliberation, checks them against a fixed
> constitution, and issues exactly one of two rulings — PERMIT or REJECT (→ fallback) —
> with a written opinion (the audit trace) every time. It never reasons, never edits,
> and never depends on any model.**

Four properties make it the stable layer the brief demands:

1. **Model-free & deterministic.** Zero model calls, zero learned components, zero
   sampling. The same inputs always yield the same verdict. This is *why* it survives
   every future model: it validates **outputs against the constitution**, never models.
2. **Permit-or-reject, never edit.** The Governor is a **gate, not an author.** It may
   not "fix" a Ruling into compliance (that would make it a reasoning participant and
   launder a violation). A non-compliant assessment is **rejected**, and a known-good
   assessment (the Floor) is emitted instead. This keeps the reasoning plane and the
   constitutional plane cleanly separate.
3. **Fail-closed.** Any uncertainty, any unresolved check, any corruption → REJECT →
   deterministic fallback. Abstention over overconfidence, applied to the validator
   itself.
4. **Binds everything that reaches the user equally.** Council output *and* Floor output
   are both validated; there is no privileged, unchecked path to the user.

The Governor is the constitutional embodiment of everything the four frozen docs assert
as doctrine — turned from *principles the reasoning is asked to follow* into *invariants
the system is mechanically forbidden to violate.*

---

## Table of contents (maps to deliverables A–M)

A. Architecture → §A · B. Constitutional principles → §B · C. Validation pipeline → §C ·
D. Failure handling → §D · E. Audit architecture → §E · F. Deterministic fallback → §F ·
G. Scalability → §G · H. Future compatibility → §H · I. Recommendations → §I ·
J. Dependencies → §J · K. Downstream documents → §K · L. Implementation impact → §L ·
M. Open questions → §M.

---

## A. Complete Constitutional Governor architecture

### A.1 Where it sits (the final gate)

```
  REASONING PLANE (orchestration §F P5)                CONSTITUTIONAL PLANE (this doc)
  ┌───────────────────────────────┐                   ┌──────────────────────────────────┐
  │ Final Judge → candidate Ruling │ ── handoff ─────► │  CONSTITUTIONAL GOVERNOR          │
  │ + full blackboard + citations  │   (§A.2)          │   deterministic · model-free     │
  └───────────────────────────────┘                   │   PERMIT | REJECT  (never edits)  │
            ▲ inputs it also reads:                    └───────────────┬──────────────────┘
            │  Evidence Bundle (frozen)                       PERMIT    │   REJECT
            │  PriorContext / memory_revision (frozen)         ▼        ▼
            │  corroboration state                       emit to user   FALLBACK LADDER (§F)
            └──────────────────────────────────────────  (+ audit)      Floor → Safe Abstention
                                                                         (each itself validated)
                                          every ruling → IMMUTABLE AUDIT LOG (§E)
```

### A.2 Inputs (the handoff contract, fixed by Orchestration §L)
The Governor validates the **assembled result and its whole deliberation** — not just the
final JSON:

```jsonc
GovernorInput {
  "ruling": { ...analyst_response_schema.json object... },   // the candidate assessment
  "blackboard": [ Finding|Hypothesis|Critique|Calibration|Ruling ... ],  // the full trace
  "evidence_bundle_ref": "bundle_id",        // content-addressed; the Governor resolves citations against it
  "prior_context": [ RankedPrior... ],       // input 2; memory_revision pinned
  "corroboration_state": { discriminative_methods[], single_axis_capped, convergence },
  "version_binding": { bundle_id, memory_revision, constitution_version,
                       contract_versions{}, model_revisions{}, floor_version }
}
```

### A.3 Division of labor — not a duplicate of per-module validation
Orchestration already validates each **artifact locally** (schema/citation/lint) before
it reaches the blackboard (Orchestration §E). The Governor is different and complementary:
- **Per-module validation = local correctness** ("is this one artifact well-formed?").
- **The Governor = global constitutional compliance** ("does the *assembled* assessment
  honor the constitution end-to-end, and is the whole deliberation sound?").

The Governor **re-checks citations on the final Ruling** (defense in depth — it never
trusts that upstream validation ran) and adds the cross-cutting checks that can *only* be
evaluated on the assembled result against the bundle + PriorContext (echo-guard, gate,
memory-boundary, confidence-vs-engine, contradiction-completeness, falsifiability).

### A.4 The two-layer constitution (stability where it matters, tunability where it's safe)
- **Immutable Core** — inviolable principles that can **never** be amended (evidence-not-
  verdict, echo-never-recompute, the corroboration gate, no-LLM-writes-to-memory,
  falsifiability, no-PII). Changing one is, by definition, a *fundamental architectural
  flaw* review — not a routine amendment.
- **Configurable Periphery** — tunable parameters under governance (banned-phrase lists,
  confidence-band thresholds, length bounds, sampling-N). Versioned via
  `constitution_version`; every change is audited and re-evaluated (doc #6).

This split is the answer to "remain stable while models/strategies/contracts change": the
**Core is frozen**; only the periphery flexes, and only under governance.

---

## B. Constitutional principles

Each principle is an **immutable statement** *and* a **machine-checkable invariant** over
the structured handoff. A principle the Governor cannot mechanically decide from the
artifacts is not enforceable and is not a constitutional rule — so the value here is the
**translation from doctrine to decidable predicate.** (Core = ★; periphery = ☆.)

| # | Principle | Machine-checkable invariant (what the Governor actually checks) | Decided from |
|---|---|---|---|
| P1 ★ | **Evidence over assertions** | every claim in `evidence_for`/`evidence_against`/`assessment` carries ≥1 `evidence_ref` | Ruling |
| P2 ★ | **Every claim references resolvable evidence** | every `evidence_ref` resolves in the bundle `citation_index` or `PriorContext`; quotes match a `sample_text` item | Ruling + Bundle + Priors |
| P3 ★ | **Current evidence precedes memory** | `suspicion_probability`/`tier` derive only from the bundle; no `ko:` ref appears as a driver of the number | Ruling + version binding |
| P4 ★ | **Memory is context, never proof** | no `ko:` ref in `evidence_for` with `influence_class != exculpatory`; no prior in `corroboration.discriminative_methods` | Ruling + Priors |
| P5 ★ | **LLMs never create evidence** | every cited id pre-exists in the (deterministically-built) bundle/PriorContext; no Ruling-introduced ids | Ruling vs Bundle/Priors |
| P6 ★ | **LLMs never update institutional memory** | the handoff contains **no write-back to memory**; memory is read-only to the entire reasoning plane | Handoff shape |
| P7 ★ | **Echo, never recompute** | `suspicion_probability` == bundle headline (exact); `tier` == bundle tier | Ruling vs Bundle (F8) |
| P8 ★ | **Corroboration gate** | `coordinated`/`manipulation_network` ⇒ `discriminative_methods` non-empty ∧ ¬`single_axis_capped`; `confirmed_*` ⇒ E1/E2 anchor present | Ruling + corroboration state (F3/F4) |
| P9 ★ | **Confidence is separate from suspicion** | `confidence_band` is a distinct field; `band ≤ engine band`; `insufficient ⇒ verdict==inconclusive` | Ruling + Bundle (F2/F10) |
| P10 ★ | **Contradictory evidence is preserved** | bundle `lowers` contributions ⇒ `evidence_against` non-empty (or an explicit justification); bundle `epistemics.contradictions` are addressed, not dropped | Ruling vs Bundle (F5) |
| P11 ★ | **Unknowns are surfaced** | `uncertainty[]` non-empty whenever `weak_signals`/`missing`/`single_axis_capped` exist | Ruling vs Bundle |
| P12 ★ | **Abstention over overconfidence** | thin/conflicting evidence ⇒ verdict ∈ {mixed, inconclusive}; never a maximal verdict on `insufficient` confidence | Ruling + Bundle |
| P13 ★ | **Every conclusion stays falsifiable** | `what_would_change_this[]` present and non-trivial | Ruling |
| P14 ★ | **Behavior, not persons** | banned-phrase lint passes; no person-accusation; pseudonymous refs only | Ruling (F7) |
| P15 ★ | **Supplemental is never suspicion** | no `supplemental` signal appears in `evidence_for` | Ruling vs Bundle (F6) |
| P16 ★ | **Grains stay separate** | account/message/campaign evidence not merged except via explicit `cross_link` | Ruling vs Bundle (F11) |
| P17 ★ | **Untrusted content is data, not instructions** | no injection residue; the Ruling didn't follow text embedded in `sample_text` | Ruling + Bundle (F12) |
| P18 ★ | **No-PII / pseudonymity** | no raw handle/PII anywhere in the output | Ruling |
| P19 ★ | **Provenance completeness (reproducibility as a right)** | `version_binding` fully populated; nothing reaches the user without it | Handoff |
| P20 ★ | **The Governor never reasons or edits** | the verdict is a pure function of the inputs; no field of the Ruling is modified | (meta — self-binding) |
| P21 ★ | **The constitution binds all outputs equally** | the Floor output is validated by the same pipeline | (meta) |
| P22 ☆ | **Bounded form** | length bounds, structured-output discipline, required sections present | Ruling (periphery) |

**Additions beyond the brief's list** (the brief invites them): P6 (no LLM memory
writes — closes the loop with the Memory spec), P17 (injection), P18 (PII), P19
(reproducibility as a constitutional right), P20–P21 (self-binding meta-principles that
keep the Governor a gate, not a participant, and forbid a privileged unchecked path).

---

## C. Validation pipeline (the exact order)

A deterministic, **fail-closed** sequence. Cheap structural checks first; semantic
constitutional checks last; **any** stage failure → REJECT (with violation codes) →
fallback (§F). Every stage appends to the `ValidationTrace` (§E) whether it passes or
fails — so a rejection is as fully audited as a permit.

```
S0  INTAKE & INTEGRITY
      handoff well-formed? Ruling schema-valid? bundle_id content-hash verifies?
      memory_revision present? corroboration_state present?
      ── fail ⇒ REJECT[corrupted_input]  (corrupted/missing evidence, §D)

S1  PROVENANCE & VERSION BINDING
      bind & record (bundle_id, memory_revision, constitution_version,
      contract_versions, model_revisions, floor_version)        [reproducibility seal, P19]

S2  CITATION RESOLUTION                                          [P1, P2, P5 — F1]
      every evidence_ref in the Ruling + cited artifacts resolves in citation_index/Priors;
      quotes match sample_text items; NO Ruling-introduced ids
      ── fail ⇒ REJECT[fabrication]

S3  EVIDENCE INTEGRITY / NO-FABRICATION                          [P1, P5 — F1, F9]
      every claim traces to a real EvidenceItem/KnowledgeObject; no assumption-filling

S4  ECHO-GUARD (engine override)                                 [P7 — F8]
      suspicion_probability == bundle headline (exact); tier == bundle tier
      ── fail ⇒ REJECT[engine_override]

S5  CORROBORATION-GATE ENFORCEMENT                               [P8 — F3, F4]
      coordinated/manipulation_network ⇒ discriminative methods in THIS bundle ∧ ¬single_axis;
      confirmed_* ⇒ E1/E2 anchor
      ── fail ⇒ REJECT[gate_breach]

S6  MEMORY-BOUNDARY ENFORCEMENT                                  [P3, P4, P6]
      no ko: prior as discriminative/driver; influence_class respected; memory didn't move
      the number (cross-check S4); subject-derived priors flagged; no memory write-back
      ── fail ⇒ REJECT[memory_overreach]

S7  CONFIDENCE CALIBRATION                                       [P9 — F2, F10]
      band ≤ engine band; insufficient ⇒ inconclusive; confidence ⊥ suspicion (distinct fields)
      ── fail ⇒ REJECT[confidence_violation]

S8  UNCERTAINTY & CONTRADICTION COMPLETENESS                     [P10, P11 — F5]
      uncertainty[] non-empty when warranted; evidence_against reflects bundle `lowers`
      (or justified); epistemics.contradictions addressed not dropped
      ── fail ⇒ REJECT[suppressed_counter_evidence]

S9  POLICY LINTS                                                 [P14–P18 — F6, F7, F11, F12]
      banned-phrase; supplemental-as-suspicion; grain-bleed; injection residue; PII
      ── fail ⇒ REJECT[policy_violation]

S10 FALSIFIABILITY                                               [P13]
      what_would_change_this[] present + non-trivial
      ── fail ⇒ REJECT[non_falsifiable]

S11 CONSTITUTIONAL VERDICT
      all stages pass ⇒ PERMIT (emit + audit)
      any stage failed ⇒ REJECT(violation_codes) ⇒ FALLBACK LADDER (§F)
      (then re-enter the pipeline to validate the fallback output itself — P21)
```

**Order rationale:** integrity before meaning (don't interpret corrupted input);
citation before semantics (a claim must exist before it can be judged); echo/gate/memory
(the *number's* legitimacy) before confidence/uncertainty (the *qualification* of the
number) before lints (surface policy) before falsifiability (the closing guarantee). The
order is itself part of the constitution (`constitution_version`), so audits are
comparable across time.

---

## D. Failure handling

Every failure class maps to a deterministic response. The Governor's prime directive:
**fail closed, degrade gracefully, always emit a constitutional answer (§F).**

| Failure class | Detection | Response |
|---|---|---|
| **Validation failure** (any stage) | stage predicate false | REJECT[code] → fallback ladder |
| **Citation failure** (unresolvable ref) | S2 resolution miss | REJECT[fabrication] → Floor |
| **Corrupted evidence** (hash mismatch) | S0 `bundle_id` verify fails | REJECT[corrupted_input] → **Safe Abstention** (can't trust the Floor either) |
| **Missing evidence** (absent facet/field) | S0/S3 | REJECT[insufficient] → Floor (which is built to handle thin data) |
| **Inconsistent reasoning** (Ruling ⟂ blackboard) | cross-check Ruling vs artifacts | REJECT[inconsistent] → Floor |
| **Conflicting analysts** (unresolved discriminative conflict) | corroboration + epistemics show conflict but Ruling forced a side | REJECT[forced_verdict] → Floor (→ mixed/inconclusive) |
| **Unsupported conclusion** (verdict exceeds evidence) | S5/S7 | REJECT[gate_breach|confidence] → Floor |
| **Hallucination** (uncited/invented claim or number drift) | S2/S3/S4 | REJECT[fabrication|engine_override] → Floor |
| **Degraded operation** (partial council, missing modules) | version binding shows missing contracts | PERMIT only if the Ruling's confidence already reflects the gap (Orchestration §G); else REJECT |
| **Total failure** (no valid Ruling, no Floor) | both unavailable | **Safe Abstention** — "insufficient evidence to assess" (the ultimate floor) |

Two invariants: (1) **the Governor never repairs** — it rejects and lets the fallback
produce a clean output; (2) **a single failed check is sufficient for rejection** (fail-
closed) — there is no "mostly compliant" pass.

---

## E. Audit architecture

Every Governor decision produces an **immutable, append-only, content-addressed audit
record** — the substrate of "every assessment fully reproducible months or years later."
Consistent with the platform's "records evolve / never overwrite" discipline (the
Evidence Bundle revisions + Memory Observation Ledgers).

### E.1 The `ValidationTrace` (one per decision)
```jsonc
ValidationTrace {
  "trace_id": "vt:<sha256>",                 // content-addressed
  "decided_at": "ISO-8601",
  "verdict": "permit | reject",
  "violation_codes": ["gate_breach", ...],   // empty on permit
  "version_binding": { bundle_id, memory_revision, constitution_version,
                       contract_versions{}, model_revisions{}, floor_version },
  "input_digest": "sha256(handoff)",         // exact inputs validated
  "stage_results": [ { "stage":"S5","pass":false,"detail":"coordinated w/o discriminative method",
                       "evidence_refs":["ev:0300"] }, ... ],   // EVERY stage, pass or fail
  "emitted_output_digest": "sha256(final output that reached the user)",
  "fallback_path": "none | floor | safe_abstention",
  "lineage_root": "bundle_id"                 // entry point to full evidence lineage (E.3)
}
```

### E.2 The immutable audit log
Append-only, content-addressed, tiered (hot recent / cold archive — never deleted within
the retention horizon). Each trace is sealed by `trace_id` (its own hash) and chained
(optional `prev_trace` Merkle-style) so tampering is detectable. The log is the system's
**constitutional record**: every permit and every rejection, forever.

### E.3 Replay & reproducibility (the core promise)
Because every input is **content-addressed and version-pinned**, an assessment is
reconstructable years later:
- **The Governor's verdict is *perfectly* reproducible** — it is a deterministic function
  of pinned inputs; re-running the pipeline on the stored `(bundle_id, memory_revision,
  constitution_version, Ruling)` yields the identical verdict and trace.
- **The reasoning is replayable from the stored artifacts** — even though a model is not
  bit-reproducible, the audit stores the *actual* blackboard + Ruling that were produced,
  so an auditor inspects exactly what the model said and why the Governor permitted or
  rejected it. (Re-*running* the model is reproducible only up to sampling: pinned
  `model_revision` + low temperature + seed; the constitution does not depend on this.)
- **Evidence lineage** is end-to-end: Ruling claim → `evidence_ref` → `EvidenceItem` →
  `traceability_path` → pseudonymous raw observation (Evidence Bundle §E). The trace's
  `lineage_root` is the entry point.
- **Version tracking**: `model_revisions` + `memory_revision` + `constitution_version` are
  recorded on **every** decision, so a model regression or a memory drift is *detectable
  in audit* even though the Governor's behavior never changed.

### E.4 Constitutional-violation records
Each REJECT emits typed `violation_codes` that feed three consumers: (a) the audit log;
(b) the **Analyst Evaluation Framework (doc #6)** as labeled negatives (the failure-mode
catalog F1–F12 maps onto the codes — Appendix 4); (c) **model-regression detection** (a
rising rejection rate for a `model_revision` is a regression signal).

---

## F. Deterministic fallback strategy (the ladder)

The Governor guarantees the user **always** receives a constitutional answer, via a
strict ladder — each rung itself validated by the same pipeline (P21):

```
1. COUNCIL RULING        — if it PERMITs, emit it.
        │ reject
        ▼
2. DETERMINISTIC FLOOR   — the always-valid DeterministicAnalystProvider output
   (frozen). Rule-built, so it passes the constitution by construction — but it is
   STILL run through the full pipeline (no privileged path, P21). Emit if PERMIT.
        │ reject (only if inputs themselves are corrupt)
        ▼
3. SAFE ABSTENTION       — "Insufficient evidence to produce a constitutional
   assessment." The ultimate floor: a fixed, evidence-free, maximally-cautious output
   that is trivially constitutional (no claims ⇒ no citations needed; verdict =
   inconclusive; confidence = insufficient). Always available.
```

**Fallback eligibility** is a constitutional check itself: the Floor is eligible only if
the bundle integrity verified (S0); if the bundle is corrupt, the system skips to Safe
Abstention rather than trusting a Floor built on corrupt evidence. The ladder is **total**
— there is no input for which the Governor cannot emit a constitutional output.

This realizes the frozen "Deterministic Floor under everything" (Cognitive Engine §1,
Orchestration §G) as a *constitutional guarantee*, not just an engineering convenience.

---

## G. Scalability strategy

The Governor is the **cheapest** component in the stack and is never the bottleneck:
- **Pure deterministic checks**, O(claims + citations); no model calls, no network to a
  model — runs in microseconds-to-milliseconds, like the existing deterministic Floor.
- **Cacheable by `(input_digest, constitution_version)`** — re-validating an identical
  output under the same constitution reuses the verdict (idempotent).
- **Parallelizable** — stages S2–S10 are independent given S0/S1; can fan out.
- **Inline or async** — cheap enough to run inline before emit; the audit write is the
  only I/O and is async/append-only.
- **Audit log at millions of investigations** — the real scaling surface is storage:
  content-addressing gives free dedup; tiered hot/cold; a retention horizon for cold
  archive (constitutional traces are kept for the reproducibility window, never silently
  dropped). Same backend posture as the Memory ledgers (§G of that doc).

---

## H. Future compatibility

The Governor validates **outputs, not models** — so every required future is absorbed
with **zero change to constitutional behavior**:

| Future | Why the Governor is unaffected |
|---|---|
| **Qwen → future reasoning models** | it checks the `(Ruling, blackboard, citations)` handoff; the model that produced it is irrelevant to the checks (only recorded for audit) |
| **LoRA specialists / ensembles** | same handoff shape; ensemble disagreement surfaces as lower confidence, which the Governor validates normally |
| **Distributed reasoning** | the Governor validates the assembled result; distribution is upstream |
| **Future Cognitive-Engine upgrades** | new modules/contracts still terminate in a Ruling + blackboard; the constitution is unchanged |
| **New constitution needs** | only the **periphery** flexes under governance + re-eval (doc #6); the **Core is immutable** (§A.4) |

The constitution is the **stable contract**; models, strategies, and prompt contracts
churn beneath it. A model regression is *detectable* (rising rejection rate per
`model_revision`) precisely because the Governor's bar never moves.

---

## I. Recommendations

1. **Keep the Governor strictly deterministic and model-free** — the moment it calls a
   model, it stops being a constitution and becomes another fallible reasoner. This is
   the non-negotiable design line.
2. **Gate, never edit.** Reject-to-fallback, never "repair" — repair launders violations
   and entangles the planes.
3. **Translate every principle into a decidable predicate** (§B) — a principle that can't
   be mechanically checked from the artifacts isn't enforceable; if a desired rule isn't
   decidable, fix the *artifact schema* (upstream) so it becomes decidable, rather than
   asking the Governor to "judge."
4. **Two-layer constitution** — immutable Core, governed periphery — gives stability and
   tunability without compromising either.
5. **The fallback ladder is constitutional, not optional** — Council → Floor → Safe
   Abstention, each validated; the system is *provably* always able to answer
   constitutionally.
6. **Audit everything, content-addressed** — make reproducibility a *right* (P19), so the
   GitHub↔HuggingFace↔Render chain and every future model are auditable by construction.

---

## J. Dependencies

- **`OMI_REASONING_ORCHESTRATION_V1`** — supplies the handoff (§A.2) and the Floor
  fallback path. (Hard.)
- **`OMI_EVIDENCE_BUNDLE_SPEC_V1`** — the `citation_index`, `bundle_id` integrity, the
  `epistemics` layer the Governor checks against. (Hard.)
- **`OMI_INTELLIGENCE_MEMORY_SYSTEM_V1`** — `PriorContext`, `influence_class`,
  `memory_revision`; the memory-boundary checks (S6). (Hard.)
- **`OMI_COGNITIVE_ENGINE_V1`** — the F1–F12 catalog, the Deterministic Floor, the
  Governor's frozen role. (Hard.)
- **The Deterministic Floor** (frozen `DeterministicAnalystProvider`) — the fallback
  output the Governor emits and re-validates. (Hard.)

---

## K. Downstream documents

| # | Document | Interface from this doc |
|---|---|---|
| 6 | **Analyst Evaluation Framework** | consumes the `violation_codes` as labeled negatives + the per-stage pass/fail as eval metrics; the Governor's checks *are* the acceptance gates the eval set measures against |
| 7 | **Implementation Roadmap** | §L impact; build order (Floor + Governor + audit log first — they are deterministic and model-free, so they ship before any model integration) |
| — | **Runtime Verification phase** | the Governor is the runtime gate; its audit log is the verification record |
| — | **GitHub↔HuggingFace↔Render validation** | the `version_binding` (esp. `model_revision` = the pinned HF revision that served, on the Render deployment, from the GitHub commit) makes the deploy chain auditable end-to-end |

---

## L. Implementation impact (for the later build phase — not now)

- **New components:** the Governor (a deterministic validator library), the
  `ValidationTrace` + immutable audit log, the Safe-Abstention output. All **additive**;
  zero change to the frozen engine/scoring/bundle/memory.
- **Built first, model-free:** because the Governor + Floor + audit log are fully
  deterministic, they can be **implemented and fully unit-tested before any model
  integration** (each principle → a unit test; each failure class → a rejection test).
  They are the safe foundation the model integration later plugs into.
- **Safety posture preserved:** off-by-default council, async, cached, SAVEPOINT-isolated
  audit writes, Floor fallback — exactly the existing `app/reasoning/analyst.py` posture.
- **Testability is intrinsic:** the constitution is a test suite. The Governor's
  correctness is decidable and exhaustively testable without a GPU.
- **Gates (when built):** backend full suite green; web typecheck; match surrounding
  style; no fabricated metrics (Platform Guardian §4).

---

## M. Open architectural questions (none blocks this spec)

1. **Amendment process for the periphery** — who governs `constitution_version` bumps,
   and the re-eval bar (hand to doc #6) before a new periphery ships.
2. **Trace retention horizon** — how long cold-archived `ValidationTrace`s are kept for
   reproducibility vs storage cost (recommend: long, since traces are small and
   content-addressed).
3. **Inline vs async placement** — run the Governor inline (cheap, blocks emit) vs async
   with an emit-hold; recommend inline given its microsecond cost.
4. **Justified-empty `evidence_against`** — the exact predicate for an acceptable
   justification in S8 (when *no* exculpatory signal genuinely exists).
5. **Model-regression alarm thresholds** — what rejection-rate delta per `model_revision`
   triggers a regression review (hand to doc #6).
6. **Merkle-chaining the audit log** — whether to chain traces for tamper-evidence now or
   defer to the storage layer.
7. **Constitution as data vs code** — express the principle set as a versioned data
   manifest (hot-swappable periphery) vs compiled checks (recommend: Core compiled +
   immutable, periphery as governed data).

---

*Canonical engineering specification only. No production code, scoring, detector, model,
dataset, or deployment was changed by this document. The Constitutional Governor is a
deterministic, model-free validation layer that PERMITs or REJECTs assessments against an
immutable constitution, never reasons, never edits, fails closed to a constitutional
fallback, and records an immutable, reproducible audit of every decision — extending,
never redesigning, the four frozen architecture documents.*
