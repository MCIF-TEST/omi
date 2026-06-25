# OMI_REASONING_ORCHESTRATION_V1 — How Omi's Cognitive Engine Actually Reasons

> **Status: canonical engineering specification only.** No implementation, no
> production change, no detector / scoring / OmiScore / model / dataset / deployment
> change. This is document **#4** in the Architecture Specification Phase. It defines the
> **orchestration layer** — the control plane that coordinates every reasoning module —
> over the three **frozen** approved documents. It **extends**, never redesigns them.
>
> **Frozen upstream (do not redesign):**
> ✅ `OMI_COGNITIVE_ENGINE_V1.md` — the Analyst Council, tiers, typed artifacts, the
>    Evidence-Anchored Blackboard, the Deterministic Floor, the Governor's existence,
>    confidence-as-clamp, tiered escalation.
> ✅ `OMI_EVIDENCE_BUNDLE_SPEC_V1.md` — the normalized evidence graph, `EvidenceItem`
>    (`ev:NNNN`), the citation system, views, batch grains, the Binder.
> ✅ `OMI_INTELLIGENCE_MEMORY_SYSTEM_V1.md` — the institutional knowledge graph,
>    deterministic Retrieval → `PriorContext`, the three hard lines, the exculpatory
>    asymmetry, memory-influence quarantine.
>
> **Roadmap position:** after this (#4 Reasoning Orchestration) come #5 **Governor**
> (validation internals — this doc defines the *handoff*, not the Governor's interior),
> #6 **Analyst Evaluation Framework**, #7 **Implementation Roadmap**, then Runtime
> Verification → Implementation → Evaluation → Fine-tuning → Continuous Learning.

---

## 0. The governing idea: two planes

The brief's hardest requirement — *"deterministic enough to audit while remaining
flexible enough to improve over time"* — is satisfied by one structural decision that
runs through the whole document:

> **Separate the deterministic CONTROL PLANE from the swappable REASONING PLANE, joined
> only by stable, model-agnostic reasoning contracts.**
>
> - The **control plane** (the Orchestrator) is fully deterministic and auditable: it
>   decides *which* module runs, *when*, on *what* information, *how* failures are
>   handled, and *when* to stop. It never reasons.
> - The **reasoning plane** (the model behind each module) is where intelligence lives
>   and improves: Qwen today, LoRA specialists / ensembles / future reasoning models
>   tomorrow — swapped **without touching the orchestration**, because they meet the
>   same contract.

Determinism lives in the control plane (so the *process* is auditable and reproducible);
improvement lives in the reasoning plane (so the *intelligence* compounds). Every other
section is an application of this split. It also preserves every frozen invariant:
evidence sovereignty, echo-never-recompute, the corroboration gate, citation, the
Deterministic Floor, and "memory influences but never overrides."

---

## Table of contents (maps to deliverables A–N)

A. Reasoning Orchestration architecture → §A · B. Analyst hierarchy → §B ·
C. Information visibility matrix → §C · D. Retrieval architecture → §D ·
E. Prompt contract architecture → §E · F. Reasoning lifecycle → §F ·
G. Failure handling → §G · H. Scalability → §H · I. Future compatibility → §I ·
J. Recommendations → §J · K. Dependencies → §K · L. Downstream documents → §L ·
M. Implementation impact → §M · N. Open questions → §N.

---

## A. Complete Reasoning Orchestration architecture

The **Orchestrator** is a deterministic DAG/state-machine executor sitting between the
two frozen inputs and the frozen modules, producing a candidate `Ruling` that the
Governor (doc #5) validates.

```
   ┌── INPUT 1: Evidence Bundle (frozen) ──┐     ┌── INPUT 2: Intelligence Memory (frozen) ──┐
   │  current evidence, content-addressed   │     │  PriorContext, retrieved deterministically │
   └───────────────┬────────────────────────┘     └───────────────┬───────────────────────────┘
                   │                                               │
        ┌──────────▼───────────────────────────────────────────────▼──────────┐
        │  CONTROL PLANE — THE ORCHESTRATOR  (deterministic · auditable)        │
        │                                                                       │
        │  1 Budget Controller / Triage   — how much council to convene (§H)    │
        │  2 Router (Evidence + Memory)   — per-module lens views (§C/§D)       │
        │  3 Scheduler / DAG Executor     — phase order + parallelism (§F)      │
        │  4 Blackboard  (frozen artifacts: Finding/Hypothesis/Critique/…)      │
        │  5 Debate Controller            — adversarial turns + round caps (§F) │
        │  6 Stopping / Convergence Ctrl  — when to halt (§F.7)                 │
        │  7 Failure Supervisor           — retry · degrade · Floor (§G)        │
        └──────────┬───────────────────────────────────────────────┬──────────┘
                   │ dispatches module calls via ReasoningContracts │ collects artifacts
        ┌──────────▼───────────────────────────────────────────────▼──────────┐
        │  REASONING PLANE  (swappable models behind ModelRunner — §I)         │
        │  Tier-1 specialists ║ Tier-2 synthesis ║ Tier-3 Judge                │
        └──────────┬────────────────────────────────────────────────────────────┘
                   │ candidate Ruling + full blackboard + citations
                   ▼
        GOVERNOR (doc #5)  ──reject──►  DETERMINISTIC FLOOR (frozen; always-valid; ships)
                   │ pass
                   ▼
        assessment cached by (bundle_id + memory_revision) · async · off the hot path
```

**The orchestrator owns seven responsibilities** (control only — never reasoning):
budgeting, routing, scheduling, the blackboard, debate control, stopping, and failure
handling. The modules own the reasoning. The Governor owns validation. The Floor owns
the guarantee that the product always answers.

---

## B. Analyst hierarchy

Extends the **frozen** `OMI_COGNITIVE_ENGINE_V1.md` §3 tiers. **One addition the brief
authorizes:** a **Strategy Analyst** in Tier 2 (flagged ⊕). It alters **no** frozen
module's contract; it adds a synthesis lens. All modules run behind the §E contracts.

| Tier | Module | Role |
|---|---|---|
| 0 (deterministic) | Binder · Memory Retrieval | produce the two inputs (frozen) |
| 1 — Specialists (parallel, blind) | Behavioral · Language · Coordination · Narrative · Graph · Metadata · Memory | characterize one facet each |
| 2 — Synthesis (sequential, adversarial) | Hypothesis Generator · **Strategy ⊕** · Counter-Evidence/Red Team · Risk & Calibration | competing explanations, playbook frame, falsification, confidence |
| 3 — Adjudication | Final Judge → **Governor (doc #5)** | one constrained Ruling → validation |

For each analyst: **objective · required inputs · prohibited inputs · output (artifact)
· confidence duty · uncertainty duty · citation · memory access.** (Artifact types are
frozen, `OMI_COGNITIVE_ENGINE_V1.md` §6.)

### Tier 1 — Specialists (emit `Finding`; blind to each other and to the engine headline)

**Behavioral Analyst** — *Obj:* characterize posting/engagement behavior (cadence,
bursts, lifecycle). *Required:* `behavioral` facet view (`contributions`,
`score_breakdown`, fingerprint dims). *Prohibited:* other facets, engine headline
number, other specialists' Findings, raw PII, handle-morphology as a driver (V2
username-shortcut audit). *Output:* `Finding[]`. *Confidence:* per-finding strength
only (never the bundle confidence). *Uncertainty:* name abstained temporal/engagement
detectors. *Citation:* every claim cites `ev:` ids. *Memory:* `BehavioralArchetype`
priors, labeled similarity-context.

**Language Analyst** — *Obj:* characterize writing/stylometry, templating, AI-assist.
*Required:* `language` facet, cited `sample_text` items. *Prohibited:* treating
`ai_writing` (supplemental) as suspicion (F6); other facets; headline. *Output:*
`Finding[]`. *Confidence:* per-finding. *Uncertainty:* thin text, language coverage.
*Citation:* quote = cite a `sample_text` id (never paste). *Memory:*
`LinguisticFingerprint`/`NarrativeTemplate` priors.

**Coordination Analyst** — *Obj:* characterize what binds accounts and whether it is
**discriminative**. *Required:* `coordination` facet + the **gate state**. *Prohibited:*
declaring `coordinated` when only non-discriminative methods fired; other facets;
headline. *Output:* `Finding[]` incl. an explicit gate read. *Confidence:* per-finding.
*Uncertainty:* single-axis/gated state. *Citation:* cluster/method `ev:` ids. *Memory:*
`CoordinationFingerprint`/`ManipulationTechnique` priors.

**Narrative Analyst** — *Obj:* characterize *what is said* and organic-vs-amplified
spread (message grain). *Required:* `narrative` facet (8 signals), `sample_text`.
*Prohibited:* topical truth/falsity (not a truth machine); merging into account grain
(F11); headline. *Output:* `Finding[]`. *Confidence/Uncertainty:* spread sufficiency.
*Citation:* signal + sample ids. *Memory:* `NarrativeTemplate` priors.

**Graph Analyst** — *Obj:* characterize network shape (hubs, pods, bridges, density).
*Required:* `graph` facet (edges, centrality, components). *Prohibited:* identity claims
from topology; other facets; headline. *Output:* `Finding[]`. *Citation:* `graph_edge`/
`graph_metric` ids. *Memory:* `GraphFingerprint` priors.

**Metadata Analyst** — *Obj:* account-age cohorts, creation timing, platform lifecycle.
*Required:* `metadata` facet. *Prohibited:* `age_cohort` as discriminative (color only);
headline. *Output:* `Finding[]`. *Citation:* metadata ids. *Memory:* `PlatformBehavior`
priors (so a platform norm isn't read as an anomaly).

**Memory Analyst** — *Obj:* interpret how the subject relates to **institutional
precedent** — *the specialist for input 2.* *Required:* the full `PriorContext`.
*Prohibited:* treating a prior as a verdict or as discriminative evidence; using a prior
flagged subject-derived without flagging it (circular-reasoning guard, §C). *Output:*
`Finding[]` strictly tagged `influence_class ∈ {context, exculpatory}`. *Confidence:*
must report each prior's `stability_score` + contradiction ratio. *Uncertainty:* decayed
/ low-stability priors. *Citation:* `ko:`/`evd:` ids. *Memory:* full (it is the memory
lens) — **read-only**.

### Tier 2 — Synthesis (sequential; see Tier-1 Findings; still evidence-bound)

**Hypothesis Generator** (frozen) — *Obj:* enumerate a small set (≤3–4) of competing
explanations. *Required:* all Findings + `controls`. *Prohibited:* the engine verdict
label (no back-rationalizing). *Output:* `Hypothesis[]`, **must include the benign /
legitimate-coordination hypothesis**. *Uncertainty:* explanatory gaps. *Citation:*
`explains[]` → Finding ids. *Memory:* controls prominent (exculpatory asymmetry).

**Strategy Analyst ⊕ (addition)** — *Obj:* map observed behavior to a **known
playbook/technique frame** ("this pattern *resembles* hashtag-hijack amplification"),
**bounded to evidence + cited memory techniques**. *Required:* Findings,
`ManipulationTechnique`/`Campaign` priors. *Prohibited:* **inventing motive/intent not
supported by evidence (F9)** — every strategic claim either cites a `ManipulationTechnique`
prior or is explicitly flagged `speculative`; account-level psychology; the headline.
*Output:* a `Hypothesis`-typed `strategy_frame` (reuses the frozen artifact — no new
type) with mandatory `speculative` flags. *Confidence:* must down-rate any frame not
backed by a stable technique prior. *Uncertainty:* state when the strategic read is
under-determined. *Citation:* technique-prior + Finding ids. *Memory:*
`ManipulationTechnique`/`Campaign`/`ThreatActor` (conservative, context only).
*Guardrail:* Strategy is the highest motive-fabrication risk; it is **structurally
capped at "resembles technique X (cited)"**, never "intends Y."

**Counter-Evidence / Red Team** (frozen) — *Obj:* try to **falsify** the leading
suspicious hypothesis. *Required:* the leading hypothesis + full bundle + controls.
*Prohibited:* **anyone's confidence values** (argue on merits — anti-sycophancy).
*Output:* `Critique` with `exculpatory[]` + `would_flip_if[]`. *Confidence:* n/a (it
attacks, doesn't rate). *Uncertainty:* surfaces it as the product. *Citation:* every
exculpatory point cites `ev:`/`ko:`. *Memory:* controls **most** prominent here.

**Risk & Calibration** (frozen) — *Obj:* own **confidence** (separate from suspicion).
*Required:* engine `confidence`, `weak_signals`, the bundle `epistemics`, inter-module
agreement, self-consistency variance, memory `stability`/contradiction. *Prohibited:*
**the suspicion magnitude** (keep the two numbers ⊥). *Output:* `Calibration` (band +
rationale). *Confidence duty:* the whole job; **band ≤ engine band**, council signals
are clamps only. *Uncertainty duty:* enumerate every limiter. *Citation:* each caveat
cites its source. *Memory:* stability/contradiction tallies only.

### Tier 3 — Adjudication

**Final Judge** (frozen) — *Obj:* emit **one** candidate `Ruling`. *Required:* all
artifacts **+ the engine headline**. *Prohibited:* inventing weight; exceeding the gate;
recomputing the score; stepping outside the Deterministic Floor's allowed verdict set.
*Output:* the `Ruling` (the `analyst_response_schema.json` object). *Confidence:* copies
Risk's band (may only lower). *Uncertainty:* carries it into the output. *Citation:*
echoes (and cites) the engine number; must address the benign hypothesis + any control.
*Memory:* may cite priors as context; **cannot** let them change the number or the gate.

**Governor (doc #5)** — validates; not designed here. Handoff contract in §L.

---

## C. Information visibility matrix

Realizes and extends the frozen §4.3 matrix with the **memory dimension**, the new
analysts, and an explicit rationale per cell (the brief's "explain every visibility
decision"). `✓`=visible, `✗`=hidden, `◐`=lens-filtered subset, `⚑`=visible only with a flag.

| Module | Own-facet evidence | Other facets | Engine headline # | Other Tier-1 Findings | Hypotheses | Critiques | Others' confidence | Suspicion magnitude | PriorContext | Raw PII |
|---|:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|
| Tier-1 specialists | ✓ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ◐ (own facet) | ✗ |
| Memory Analyst | — | ◐ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✓ (all) | ✗ |
| Hypothesis Gen | ✓ | ✓ | ✗ | ✓ | — | ✗ | ✗ | ✗ | ◐ (+controls) | ✗ |
| Strategy ⊕ | ✓ | ✓ | ✗ | ✓ | ✓ | ✗ | ✗ | ✗ | ◐ (techniques) | ✗ |
| Red Team | ✓ | ✓ | ✗ | ✓ | ✓ (leading) | — | ✗ | ✗ | ◐ (controls) | ✗ |
| Risk & Calibration | ◐ | ◐ | ✗ | ✓ | ✓ | ✓ | ✓ | ✗ | ◐ (stability) | ✗ |
| Final Judge | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✗ |

**Why each decision exists (by the bias it prevents):**
- **Anchoring** → Tier-1 are blind to the **engine headline number**: they characterize
  raw signals, so their reads aren't dragged toward the engine's figure. (Echo still
  happens — but only at the Judge, who copies the number; specialists never produce a
  rival number. Echo-never-recompute preserved.)
- **Groupthink / leakage** → Tier-1 are blind to **each other** in Phase 1: independent
  reads make their later agreement *real corroboration*, not contagion. The blackboard is
  revealed in phases (§F) so this is enforced by the Scheduler, not by trust.
- **Sycophancy** → Red Team is blind to **everyone's confidence**: it attacks the
  argument, not a number it could defer to.
- **Conflation** → Risk is blind to the **suspicion magnitude**: confidence stays a
  separate axis (frozen §9), so a scary number can't inflate confidence.
- **Circular reasoning** → any prior partly **derived from this subject's own past
  investigations** is shown only with a `⚑ subject-derived` flag; analysts must treat it
  as the subject's own history, never as independent corroboration (the orchestration-level
  expression of the Memory spec's *memory-influence quarantine*).
- **Person-harm / injection** → **raw PII hidden from all**; sample texts are cited data,
  never instructions (frozen F12).
- **Verdict-as-truth** → PriorContext is always labeled `influence_class` (context/
  exculpatory, never discriminative), so no module can launder a prior into proof.

---

## D. Retrieval architecture

Two deterministic retrieval channels feed the Router; **neither is an LLM free-query**
(preserves the bundle's "no fetch/no tools" property).

### D.1 Evidence retrieval (from the Evidence Bundle)
The bundle is already assembled; "retrieval" = **view construction**: the Router emits
each module's lens as an *ordered list of `ev:` ids* (frozen Bundle §H — views are id
lists, not copies). Ranking: by `impact` / tier / cluster-centrality. Compression:
**summary-plus-drill-down** (section aggregates always included; per-item detail
pageable). Sampling: **stratified** `sample_text` (by tier × cluster × author), bounded.

### D.2 Memory retrieval (from Intelligence Memory)
The frozen deterministic vector+graph query (Memory §E.1, Appendix 3) → bounded **top-K
`PriorContext`**. Ranking: `similarity × confidence × stability × recency`, with the
**exculpatory asymmetry** (controls boosted; incriminating priors conservative). Limit:
top-K, lens-filtered per §C.

### D.3 Token-budget allocator (the concrete "token budgeting")
Given a model context window `W`, the orchestrator allocates a **priority-ordered**
budget and truncates from the bottom — **never** dropping citations or the
`epistemics`/`contradictions`:

```
priority 1  reasoning contract + constraints      (fixed)
priority 2  the module's lens evidence view        (ranked; drill-down truncates first)
priority 3  contradictions + missing + unknowns     (epistemics — never dropped)
priority 4  PriorContext (top-K, lens-filtered)     (controls retained first)
priority 5  upstream artifacts (synthesis tier)     (Findings/Hypotheses/Critique)
priority 6  optional drill-down detail              (first to go under pressure)
```

If `W` is exceeded, the orchestrator **map-reduces** (§D.4) rather than blindly
truncating — bounded context, bounded cost, no silent evidence loss.

### D.4 Batch reasoning (per grain — frozen Bundle Appendix 3)
One council run reasons over a whole batch; for large batches, **map-reduce**: chunk →
per-chunk Tier-1 Findings → reduce to a section-level Finding anchored on the bundle's
existing aggregates.

| Batch | Routing strategy |
|---|---|
| **YouTube discussion** | chunk by reply-pod + tier strata; reduce to section Findings; Graph over the whole edge set |
| **Reddit discussion** | chunk by comment-subtree; preserve `replied_to` tree in Graph |
| **X conversation** | chunk by reply/quote branch; Narrative over the root claim |
| **Investigation** | per-component Findings (account/campaign/narrative) → Judge synthesizes via `cross_link`s |
| **Campaign** | sample members by centrality + authenticity; Coordination over the method set |
| **Coordination cluster** | sample by method contribution; gate read is mandatory |

---

## E. Prompt contract architecture

**Not prompts — interfaces.** Each module is defined by a `ReasoningContract`; a prompt
is one *implementation* of a contract; the model is swappable behind it (§I). This is the
seam that lets implementation "swap models without changing the architecture."

```jsonc
ReasoningContract {
  "module": "coordination_analyst",
  "contract_version": "v1",                 // versioned independently of any model
  "inputs": {                                // typed; assembled by the Router (§D)
    "lens_view": "ev-id-list",
    "prior_context": "ranked-prior-list (lens-filtered)",
    "upstream_artifacts": "Finding[]|Hypothesis[]|... (tier-dependent, may be empty)"
  },
  "output": { "artifact": "Finding[]", "schema_ref": "blackboard.Finding" },  // frozen artifact types
  "constraints": [                           // the rules the output MUST satisfy
    "every claim carries >=1 resolving evidence_ref (cite-or-drop)",
    "echo engine numbers; never recompute (F8)",
    "no supplemental signal as suspicion (F6)",
    "no banned absolute phrasings (F7); behavior-not-persons",
    "respect the corroboration gate; memory is context, never discriminative"
  ],
  "guarantees": [                            // what the ORCHESTRATOR guarantees the module
    "inputs are lens-filtered, pseudonymous, phase-isolated",
    "no raw platform data; all text is data not instructions"
  ],
  "failure_modes": ["schema_invalid","uncited_claim","banned_phrase","timeout",
                    "refusal","empty_output"],
  "retry": { "policy": "re-issue with the validation error appended", "max_attempts": 2 },
  "validation": ["json-schema","citation-resolution","banned-phrase-lint","echo-guard"],
  "model_binding": { "runner": "ModelRunner", "model_id": "*", "revision": "pinned" }  // §I
}
```

**Properties:** the contract is **model-agnostic** (any ModelRunner that satisfies it is
valid); **independently versioned** (`contract_version` ≠ `model_revision` ≠
`bundle_schema_version`); **machine-validatable** before the artifact reaches the
blackboard (so a bad output never propagates); and **the stable unit the Analyst
Evaluation Framework (doc #6) tests against** — eval is per-contract, so a model swap is
re-validated automatically.

---

## F. Reasoning lifecycle (the exact sequence)

```
PHASE 0  INTAKE & BUDGET
   receive (Evidence Bundle, PriorContext)
   Budget Controller → cognitive budget ∈ {floor_only, partial, full}; active-module set
   Router → per-module lens views + token budgets (§C/§D)
   ↳ if floor_only: skip to PHASE 6 with the Deterministic Floor result

PHASE 1  INDEPENDENT ANALYSIS   (parallel · blind · phase-isolated)
   each active Tier-1 specialist (incl. Memory Analyst) ← its lens + facet priors
   → emits Finding[]  to the blackboard
   [Scheduler holds the blackboard closed: no specialist sees another's output]

PHASE 2  HYPOTHESIS & STRATEGY   (sequential)
   Hypothesis Generator ← all Findings + controls → Hypothesis[]  (incl. mandatory benign)
   Strategy Analyst ⊕   ← Findings + technique priors → strategy_frame (speculative-flagged)

PHASE 3  ADVERSARIAL CONFRONTATION   (the debate)
   Debate Controller picks the leading suspicious hypothesis
   Red Team ← leading hypothesis + full bundle + controls (NOT confidence)
            → Critique{ exculpatory[], would_flip_if[] }
   [bounded debate loop: Judge MAY request <=1 additional Red-Team pass if the critique
    is strong; HARD round cap = 2; then forced termination]

PHASE 4  CALIBRATION
   Risk & Calibration ← Findings + Critique + epistemics + inter-module agreement
                      + self-consistency variance + memory stability/contradiction
                      → Calibration{ band (≤ engine), rationale }   [clamps only]

PHASE 5  SYNTHESIS & ADJUDICATION
   Final Judge ← ALL artifacts + engine headline
       • echo suspicion_probability/tier (cite the headline id)        [no recompute]
       • EVIDENCE FUSION: explain the engine's score_breakdown net; never re-net it
       • apply the §6 verdict mapping; enforce gate / single-axis cap / E1-E2 anchor
       • require non-empty evidence_against; address the benign hypothesis + any control
       • CONTRADICTION HANDLING: name both sides (raises vs lowers, cross-grain); never net silently
       → candidate Ruling   [self-consistency sample N× for high-stakes; divergence → abstain/lower confidence]

PHASE 6  VALIDATION & STOP
   Governor (doc #5) ← candidate Ruling + full blackboard + citations
       → pass:  emit + cache by (bundle_id + memory_revision)
       → fail:  reject → Deterministic Floor ships (frozen)
```

**Maps the brief's lifecycle items:** hypothesis generation = P2; competing hypotheses =
P2 (≥ benign + suspicious); counter-reasoning = P3; confidence estimation = P4;
uncertainty estimation = P4 + every module's uncertainty duty; contradiction handling =
routed from bundle `epistemics` + cross-module conflict, addressed in P3/P4 and **named,
never netted** in P5; evidence fusion = P5 (the Judge explains `score_breakdown`, never
re-nets — frozen); final synthesis = P5.

### F.7 Stopping conditions (when reasoning halts)
The Stopping Controller halts on the **first** of: (1) **budget exhausted** → emit
best-available at lowered confidence, or fall back; (2) **convergence** → blind
specialists + Red Team agree and no open contradiction remains → proceed straight to
adjudication; (3) **forced abstention** → confidence `insufficient` ⇒ `inconclusive`
(frozen F10), no further rounds; (4) **debate round cap** reached (§F P3); (5)
**escalation** → genuine unresolved discriminative conflict ⇒ stop at `mixed`/
`inconclusive` + flag for human review (never force a side); (6) **Governor reject** →
terminal → Floor. Halting is always a *defined state with a defined output*, never an
open loop.

---

## G. Failure handling

Every failure degrades gracefully toward the always-valid Floor; the product never fails
to answer (frozen).

| Failure | Orchestrator response |
|---|---|
| Module output **schema-invalid** | retry with the error appended (≤2); then drop the artifact, record a `missing_finding`, continue |
| **Uncited** claim | suppress the claim (cite-or-drop); if load-bearing, reject the artifact |
| Module **timeout / model unavailable** | run **partial council**; Risk **clamps confidence down** proportional to missing coverage |
| Module **refusal / safety stop** | treat as abstention; record in `uncertainty` |
| **Banned phrase** | reject + retry once; then drop to a safe templated claim |
| **Budget exhausted** mid-run | stop at last valid phase; emit with lowered confidence, or Floor |
| **Whole-council** failure / **Governor reject** | **Deterministic Floor** ships (frozen) |

**Principles:** (a) a single module failing **never** crashes the run — it becomes a
recorded gap that *lowers confidence* (honesty-first); (b) partial-council operation is
first-class — the orchestrator supports any subset; (c) the Floor is the floor — there is
no path where Omi returns nothing.

---

## H. Scalability strategy

Reuses + extends frozen Cognitive Engine §10 / Bundle §H:
- **Tiered escalation (Budget Controller):** most cases get the **Floor** (sub-ms,
  free); the **full council is the exception**, earned per-case by the eval-measured
  lift (doc #6).
- **Parallel Tier-1 fan-out**; the debate is the only serial stretch and is **round-
  capped**.
- **Batch amortization + map-reduce** (§D.4): one run over a whole section/campaign.
- **Cache by `(bundle_id + memory_revision + contract_version)`** — *the memory revision
  must be in the key*: the same evidence under a newer institutional memory is a
  different (and legitimately re-runnable) reasoning. New, vs the frozen bundle-only key.
- **Distributed reasoning:** modules are independent dispatched jobs over a model-serving
  fleet; the orchestrator is a coordinator (swap target: the existing worker pool →
  Dramatiq+Redis).
- **Model-tier routing:** cheap model for Tier-1 Findings; the Thinking model for Red
  Team + Judge.

---

## I. Future compatibility

The control-plane/reasoning-plane split (the §0 idea) makes every required future a
**reasoning-plane swap behind a contract — zero orchestration change:**

| Future | Absorbed by |
|---|---|
| **Qwen → future reasoning models** | a new `ModelRunner` binding on the same `ReasoningContract` |
| **LoRA specialists** | per-module adapter over a shared base; the Router binds module→adapter; contract unchanged (ties to Cognitive Engine §11 V3 + Memory §H) |
| **Model ensembles** | a contract satisfied by N models reconciled behind one interface; self-consistency sampling is the degenerate case |
| **Distributed reasoning** | modules as independent jobs; orchestrator dispatches |
| **Future Cognitive-Engine upgrades** | new module → new node in the DAG + a new contract; existing modules/contracts untouched |

`ModelRunner` interface: `run(contract, assembled_inputs) → artifact` with
`{model_id, revision, params}`. The orchestration **outlives any model generation** — the
same posture as the Memory spec's model-agnostic `PriorContext`.

---

## J. Recommendations

1. **Adopt the two-plane split as the load-bearing decision** — determinism in control,
   improvement in reasoning, stable contracts as the seam. It is what makes the system
   simultaneously auditable and improvable.
2. **Build the control plane, contracts, and Floor first** (cheap, safe, model-agnostic);
   improve the reasoning plane (models/LoRA/ensembles) behind them — the frozen "build
   the frame, earn the council" recommendation, applied to orchestration.
3. **Make the Budget Controller the adoption lever** — full council only where it beats
   the Floor on the eval set (doc #6). Most traffic stays on the Floor.
4. **Key the cache by `(bundle_id + memory_revision + contract_version)`** so reasoning
   is reproducible *and* legitimately refreshable when memory or a contract advances.
5. **Keep the Strategy Analyst structurally capped** at "resembles cited technique X,"
   never "intends Y" — it is the highest motive-fabrication risk and must be the most
   tightly bounded module.
6. **Every failure lands on the Floor; every gap lowers confidence** — honesty-first
   degradation is non-negotiable.

---

## K. Dependencies

- **`OMI_EVIDENCE_BUNDLE_SPEC_V1`** — input 1; the citation system, views, batch grains,
  `epistemics`. (Hard dependency.)
- **`OMI_INTELLIGENCE_MEMORY_SYSTEM_V1`** — input 2; Retrieval/`PriorContext`, the three
  hard lines, the exculpatory asymmetry, memory-influence quarantine. (Hard.)
- **`OMI_COGNITIVE_ENGINE_V1`** — the module set, tiers, artifact types, the blackboard,
  the Deterministic Floor, confidence-as-clamp, the Governor's existence. (Hard.)
- **Governor (doc #5)** — consumes this doc's handoff (§L); its internals are out of
  scope here.
- **A model-serving layer / `ModelRunner`** — implementation-phase dependency (§I).
- **Analyst Evaluation Framework (doc #6)** — the contracts (§E) are what it tests; the
  Budget Controller (§H) depends on its lift measurements.

---

## L. Downstream documents

| # | Document | What this doc hands it |
|---|---|---|
| 5 | **Governor** | the **handoff contract**: `(candidate Ruling, full blackboard, all citations, corroboration state)`; the Governor designs the *interior* — F1–F12 enforcement, citation resolution, echo/gate/anchor checks, and the reject→Floor path. This doc fixes the *interface*, not the *implementation*. |
| 6 | **Analyst Evaluation Framework** | the per-`ReasoningContract` validation targets + the lift metric the Budget Controller consumes; the eval set gates model/LoRA swaps. |
| 7 | **Implementation Roadmap** | §M impact + §I model-binding sequence (Floor → control plane → Qwen council → LoRA specialists). |
| (opt) | **Retrieval Contract** | deepens §D ranking math / compression policy. |
| (opt) | **Binder Normalization Contract** | the engine-output → `EvidenceItem` projection rules (Bundle-side). |

---

## M. Implementation impact (for the later build phase — not now)

- **New components:** Orchestrator (control plane), Router, Budget Controller, Debate
  Controller, Stopping Controller, Failure Supervisor, `ModelRunner` abstraction. All
  **additive** — like today's `app/reasoning/` layer.
- **Zero change** to the frozen engine / scoring / OmiScore / Evidence Bundle / Memory.
- **Safety posture preserved:** off by default, async, cached (SAVEPOINT-isolated),
  Floor-fallback, no request-hot-path cost — exactly the existing `app/reasoning/analyst.py`
  posture.
- **Testability is a feature of the split:** the control plane is **deterministic →
  unit-testable with no model** (sequence, routing, isolation, failure paths); the
  reasoning plane is **contract-tested** against the eval set (doc #6). The two test on
  different axes.
- **Gates (when built):** backend full suite green; web typecheck; match surrounding
  style; no fabricated metrics (Platform Guardian §4).

---

## N. Open architectural questions (none blocks this spec)

1. **Debate round cap** — is 2 the right hard cap for Red-Team↔Judge, or grain-dependent?
2. **Strategy Analyst boundary** — the exact lint that keeps "resembles technique X" from
   drifting into motive (candidate: require a cited `ManipulationTechnique` prior or a
   `speculative` flag on *every* strategy claim).
3. **Cache-key granularity** — confirm `(bundle_id + memory_revision + contract_version)`;
   does `model_revision` belong in the key or in provenance only?
4. **Budget Controller policy** — the precise trigger for `full` vs `partial` (tier
   threshold? open-contradiction count? analyst request only at first?).
5. **Self-consistency N** and the ensemble reconciliation rule (majority? Judge-of-judges?).
6. **Specialist granularity** — V1 may collapse Behavior+Metadata+Memory into one
   "Account" specialist (frozen Cognitive Engine Appendix); the orchestrator must support
   both the collapsed and the full DAG behind the same contracts.
7. **Partial-council → confidence clamp** — the exact function mapping missing coverage to
   a confidence reduction (hand to doc #6 to calibrate).

---

*Canonical engineering specification only. No production code, scoring, detector, model,
dataset, or deployment was changed by this document. It defines a deterministic
orchestration control plane over a swappable reasoning plane, extending — never
redesigning — the three frozen architecture documents. Reasoning remains evidence-bound,
cited, adversarial, and bounded by the Deterministic Floor; the Governor (doc #5)
validates the result.*
