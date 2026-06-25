# OMI_ANALYST_EVALUATION_FRAMEWORK_V1 — The Scientific Standard for OmiSphere

> **Status: canonical engineering specification only.** No implementation, no
> production change, no detector / scoring / OmiScore / model / dataset / deployment
> change. This is document **#6** in the Architecture Specification Phase — the
> objective standard by which **every** future change to OmiSphere is judged. It
> **extends** the five frozen documents; it does not redesign them.
>
> **Frozen upstream (do not redesign):**
> ✅ `OMI_COGNITIVE_ENGINE_V1.md` — the Council, the V1→V5 roadmap, the F1–F12 failure
>    catalog, the Deterministic Floor (the eval baseline), "build the eval set first."
> ✅ `OMI_EVIDENCE_BUNDLE_SPEC_V1.md` — content-addressed bundles as **replayable
>    eval/training artifacts**; the `epistemics` layer.
> ✅ `OMI_INTELLIGENCE_MEMORY_SYSTEM_V1.md` — the precision-frontier FPR **hard gate**,
>    `LegitimateCoordinationControl`s, engine-independent targets, grouped splits.
> ✅ `OMI_REASONING_ORCHESTRATION_V1.md` — **ReasoningContracts are the unit this
>    framework tests**; the Budget Controller consumes eval-measured lift.
> ✅ `OMI_CONSTITUTIONAL_GOVERNOR_V1.md` — the `violation_codes` become **labeled eval
>    failures**; "the Governor's checks ARE the acceptance gates the eval set measures."
>
> **Roadmap position:** #6 (this) → #7 **Implementation Roadmap**, then Runtime
> Verification (GitHub↔HuggingFace↔Render↔Qwen) → Core Implementation → AI Integration →
> Validation → Fine-tuning → Continuous Learning. **This framework is the gate every one
> of those later phases must pass through.**

---

## 0. The two ideas that govern this framework

Every design choice below follows from two principles — and both are lessons OmiSphere
has already paid for.

> **(1) GATES BEFORE GRADES.** Constitutional compliance and the precision frontier are
> **hard gates** that *no amount of predictive performance can buy past*. A model that
> violates the constitution **fails evaluation regardless of its accuracy** (the brief's
> explicit requirement). Only *after* the gates pass do graded quality metrics matter.
>
> **(2) HONESTY OVER ACCURACY.** OmiSphere does **not** optimize for verdict accuracy.
> It optimizes for **faithfulness + calibration + not-over-calling.** Accuracy is a
> mirage on this domain — the behavioral-V2 audit proved it: a model scored AUC **0.982**
> while **71% of its discrimination came from a username-string artifact**, and
> behavior-only AUC collapsed to **0.546** (random) once the shortcut was removed. A
> framework that rewards headline accuracy would have *promoted* that model. So this
> framework is **shortcut-aware by construction** and ranks honesty metrics above
> predictive ones.

One line: **the Evaluation Framework is a two-stage instrument — inviolable
constitutional/precision gates first, then honesty-weighted graded improvement — that
promotes a change only when it is *measurably, reproducibly, and significantly* better
without ever becoming less trustworthy.**

---

## Table of contents (maps to deliverables A–N)

A. Architecture → §A · B. Benchmark architecture → §B · C. Evaluation hierarchy → §C ·
D. Metric definitions → §D · E. Human review → §E · F. Regression framework → §F ·
G. Promotion criteria → §G · H. Rollback → §H · I. Scalability → §I ·
J. Future compatibility → §J · K. Dependencies → §K · L. Downstream → §L ·
M. Implementation impact → §M · N. Open questions → §N.

---

## A. Complete Evaluation Framework architecture

### A.1 The two-stage instrument

```
   CANDIDATE  (a new model / prompt / LoRA / module / detector / orchestration / memory rev)
        │  pinned: (model_revision, contract_versions, memory_revision,
        │           constitution_version, eval_set_revision, engine_version)
        ▼
  ┌──────────────────────────────────────────────────────────────────────────┐
  │ STAGE 1 — CONSTITUTIONAL & PRECISION GATES   (binary · non-negotiable)     │
  │   • 100% Governor-compliant on the benchmark (any violation_code = FAIL)   │
  │   • FPR on legitimate-coordination controls does NOT regress (precision    │
  │     frontier — the hard gate)                                              │
  │   • honesty ratchets do not regress (citation integrity, counter-evidence  │
  │     recall, abstention-correctness)                                        │
  │   ── ANY gate fails ⇒ REJECT (predictive performance is irrelevant)        │
  └───────────────────────────────┬──────────────────────────────────────────┘
                                  │ all gates pass
                                  ▼
  ┌──────────────────────────────────────────────────────────────────────────┐
  │ STAGE 2 — GRADED IMPROVEMENT   (honesty-weighted scorecard · pre-registered)│
  │   beats current production by a pre-registered, statistically-significant   │
  │   margin on the honesty-led scorecard; within runtime/cost budget;          │
  │   ships a model card                                                        │
  │   ── meets margin ⇒ PROMOTE   ·   else ⇒ HOLD                              │
  └───────────────────────────────┬──────────────────────────────────────────┘
                                  ▼
            dev → SHADOW → candidate → PRODUCTION   (pinned revision; never `latest`)
                                  │
                       every run → IMMUTABLE, CONTENT-ADDRESSED EVAL RECORD (reproducible)
```

### A.2 Components
1. **Benchmark Suites** — the governed, content-addressed datasets (§B).
2. **The Evaluation Hierarchy** — per-level evaluators, detector → end-to-end (§C).
3. **The Metric Engine** — computes the canonical metrics deterministically (§D).
4. **The Constitutional Gate** — the **frozen Governor run as an evaluator** over the
   whole benchmark; its `violation_codes` are eval failures (§G, Governor-integration).
5. **The Human Review System** — ground-truth authoring + adjudication + appeal (§E).
6. **The Regression Harness** — continuous, paired, version-comparison (§F).
7. **The Promotion Decision Function** — the deterministic two-stage decision (§G).
8. **The Rollback Controller** — triggers + the kill-switch (§H).
9. **The Eval Ledger** — immutable, content-addressed records; reuses the Governor's
   audit substrate so every eval is replayable years later.

### A.3 Continuity — it generalizes the existing harness
This is **not greenfield**: `apps/api/app/evaluation/` already runs deterministic offline
benchmarks (`benchmark.py`, `metrics.py`, `coordination_benchmark.py`, `memory_benchmark.py`,
`ai_writing_benchmark.py`, frozen `benchmarks/*.json` incl. `seed_v1.json` = 65 cases).
This framework **generalizes that engine-level harness into a multi-level, constitutional,
honesty-first evaluation of the entire cognitive system** — same discipline ("never
commit on a red/uninspected suite," report real counts), wider scope.

---

## B. Benchmark architecture

### B.1 The eval unit is a frozen Evidence Bundle + a human-anchored reference
Each benchmark case = a **content-addressed Evidence Bundle** (frozen Bundle spec — it is
*designed* to be a replayable eval artifact) **+** a **human-authored reference target**
(engine-independent, valid against `analyst_response_schema.json`) **+** the
`PriorContext`/`memory_revision` it was evaluated under. The bundle being content-addressed
is what makes an eval result reproducible.

### B.2 The twelve suites, organized by epistemic role (not a flat list)
| Role | Suites | What it measures |
|---|---|---|
| **Positive controls** | known-manipulation (state-actor disclosures, confirmed rings), coordination, campaign | detection recall / FNR — *can it find real ops?* |
| **Negative controls** | **benign-coordination** (newsrooms, fandoms, official on-message), organic discussions | **FPR — the precision frontier (the most important suite)** |
| **Platform suites** | YouTube, X, Reddit, multi-platform | cross-platform robustness / domain-shift |
| **Grain suites** | narrative, coordination, campaign, multi-platform investigation | grain-correct reasoning; no grain-bleed (F11) |
| **Honesty traps** | ambiguous (must abstain), thin-data, single-axis, **F1–F12 failure-mode traps** | calibration, abstention, constitutional compliance |
| **Adversarial** | prompt-injection, evidence-poisoning, **shortcut-bait** | robustness; shortcut-resistance (the V2 lesson) |
| **Edge cases** | grain boundaries, missing facets, corrupted/partial bundles | graceful degradation; the fallback ladder |

**Design rule:** every suite carries *both* directions — a manipulation suite is
meaningless without a matched benign-coordination suite, because the metric that matters
is **discrimination at fixed FPR**, not raw recall. (Flagging everything scores perfect
recall and fails the platform.)

### B.3 Shortcut & leakage defenses (the scientific-rigor core)
- **Grouped splits.** No account / campaign / IO-operation / time-window spans
  dev and test (the corpus-audit discipline — 1.37M rows behind ~10k accounts means naive
  splits collapse effective sample size).
- **Global dedup** before splitting (exact + near-duplicate bundles).
- **Sealed held-out test set.** Tuning happens on *dev*; promotion is judged on a **sealed
  test set the candidate never trains or tunes on** — and which the eval harness reveals
  only at promotion. This is the anti-Goodhart guard: you cannot overfit a benchmark you
  cannot see.
- **Ablation / shortcut probes.** For any candidate, re-run with the suspected shortcut
  feature removed (e.g., handle morphology); a large performance drop is a **shortcut
  flag**, not a pass. The V2 audit becomes a *standing test*, not a one-time finding.

### B.4 How benchmarks evolve
Append-only, governed by `datasets/manifest.toml` (train/validation/test/quarantine;
poison never enters), **versioned by `eval_set_revision`**. New cases enter via the
human-review pipeline (§E); **production regressions and Governor rejections become new
benchmark cases** (the system learns from its mistakes — §H). Periodic re-review retires
stale/contested cases (soft-retire, audit-kept). As the platform improves, **harder cases
are added** (benchmark-rot policy) so the bar keeps rising — but the sealed test set is
re-sealed each revision so historical comparisons remain valid.

---

## C. Evaluation hierarchy

A regression can hide at any level, so **every level is gated independently *and* the
end-to-end is gated holistically.** Each module level uses its **ReasoningContract**
(Orchestration §E) as the unit of evaluation.

| Level | Unit | Ground truth | Primary metrics | A regression looks like |
|---|---|---|---|---|
| **1 Detector** | a single detector's output | labeled accounts/clusters (engine-independent) | precision/recall/FPR, calibration | a detector flags more benign controls |
| **2 Evidence Bundle** | the Binder's projection | the source engine outputs | completeness, citation-resolvability, no-PII, integrity hash | evidence missing/duplicated; a citation can't resolve |
| **3 Memory retrieval** | `PriorContext` for a bundle | relevant-prior set | retrieval precision/recall, control-surfacing, **memory-influence delta** | a relevant control isn't surfaced; an incriminating prior over-ranks |
| **4 Specialist analyst** | a `Finding[]` vs its contract | reference findings | faithfulness, citation integrity, lens-compliance | uncited claim; uses a prohibited input |
| **5 Counter-Evidence (Red Team)** | a `Critique` | reference exculpatory case | **counter-evidence recall**, would-flip quality | misses a present exculpatory signal (F5) |
| **6 Judge** | a `Ruling` | reference assessment | verdict-bound compliance, echo-exactness, calibration | verdict exceeds the gate (F3/F4); number drifts (F8) |
| **7 Governor** | PERMIT/REJECT decisions | constitutional truth (decidable) | gate precision/recall (does it catch every violation?) | a violation slips through; a valid output is wrongly rejected |
| **8 Cognitive Engine** | the full Council assembly | reference assessment | end-to-end honesty + detection at fixed FPR | the assembled result regresses vs the parts |
| **9 End-to-end investigation** | input URL → final assessment | human reference verdict | all of the above + runtime/cost/trust | any of the above, in production conditions |

**Level 7 is special:** the Governor itself is evaluated (does it catch every constitutional
violation, and never wrongly reject a compliant output?). A regression in the Governor is
the most dangerous of all, so it has its own adversarial suite of known-violating outputs.

---

## D. Metric definitions

The eight categories the brief requires, with the 18 design-goal measures mapped in.
**Honesty metrics are primary; predictive metrics are subordinate and always reported with
the precision-frontier FPR beside them.** Full catalog in Appendix 1.

| Category | Canonical metrics (precise) |
|---|---|
| **Scientific (honesty — PRIMARY)** | **Faithfulness** = % claims whose `evidence_refs` resolve (target ~100, Governor-enforced); **Citation precision/recall** vs the bundle; **Counter-evidence recall** = % of cases-with-`lowers` that have non-empty `evidence_against`; **Abstention-correctness** = % of thin/ambiguous cases correctly `inconclusive`; **Faithfulness-under-ablation** (shortcut probe) |
| **Calibration** | **ECE** (expected calibration error) + reliability diagram + **Brier** — applied to **`confidence_band` vs actual correctness** (suspicion is *echoed*, not recomputed, so what we calibrate is the *confidence*); over/under-confidence rate |
| **Detection (predictive — SUBORDINATE)** | precision, recall, **FPR**, FNR, **AUC at fixed FPR**, discrimination at a benign-control-anchored threshold — *never* reported as a bare headline |
| **Trust** | analyst **accept / edit / reject** rate (the V4/V5 feedback signal); user-trust survey; "would you sign this?" rate |
| **Explainability** | citation density, evidence-completeness, reasoning-trace legibility, lineage-resolvability |
| **Governor compliance** | violation rate by `violation_code` (must be 0 to pass), schema-validity rate (≥99%) |
| **Memory influence** | **Δ in calibration/FPR from PriorContext** (does memory help calibration *without* raising control-FPR? does it ever push past the gate? — a memory rev that raises control-FPR **fails**) |
| **Reasoning consistency** | self-consistency variance across samples; inter-module agreement; verdict stability under paraphrase/reordering |
| **Cross-platform robustness** | per-platform metric parity (YouTube/X/Reddit); domain-shift gap |
| **Longitudinal stability** | same-case same-assessment over time (under pinned versions); production metric drift |
| **Operational** | latency (p50/p95), tokens/investigation, council-vs-Floor cost, throughput |
| **Business** | $/investigation, council-invocation rate, analyst-time saved |

### D.1 How metrics combine into a decision
A **deterministic two-stage function** (Appendix 2), not a single blended score:
- **Stage 1 (gates):** any constitutional violation, any control-FPR regression, any
  honesty-ratchet regression ⇒ **REJECT**. Binary. Predictive metrics are not consulted.
- **Stage 2 (graded):** an **honesty-weighted scorecard** — faithfulness + calibration +
  counter-evidence recall dominate; detection quality is a minority weight — compared to
  current production by a **pre-registered margin** with a **paired significance test**.
  No p-hacking: the metric + margin + test are declared *before* the run.

> A change can have *better detection numbers* and still be **rejected** — for raising
> control-FPR, for a constitutional violation, or for a shortcut-driven gain. That is the
> framework working as designed.

---

## E. Human review system

Ground truth is the **binding constraint** (gold reasoning labels = 0 today — same honest
blocker as every prior doc). The framework specifies how it is created and governed.

- **Reference-target authoring.** Human analysts author **engine-independent** reference
  assessments over bundles, **blind to the engine headline** where feasible (anti-
  anchoring — the same discipline the fine-tuning doc mandates). A target must itself pass
  every constitutional check (a bad target poisons the benchmark).
- **Label governance.** Source precedence `analyst_verdict > platform_disclosure >
  dataset_label`; provenance-weighted (the `AccountLabel` discipline — a YouTube
  suspension outranks a manual guess); governed by `manifest.toml`; pseudonymous.
- **Disagreement resolution & consensus.** ≥2 independent reviewers per gold case;
  inter-rater agreement (Cohen's/Fleiss' **κ**) tracked; **disagreement is itself a
  signal** (`AccountLabel`'s "disagreement = the case is genuinely ambiguous") → the case
  moves to the *ambiguous* suite and its reference answer may legitimately be
  `inconclusive`. Adjudication by a senior reviewer builds consensus.
- **Expert review** for high-stakes labels: attribution, and especially the
  **`LegitimateCoordinationControl`** set (a wrong control suppresses real detections, so
  controls carry the highest review bar).
- **Appeal process.** A contested benchmark label can be appealed → re-adjudicated →
  the benchmark is **versioned** (falsifiability applied to the ground truth itself; the
  benchmark is revisable, like every record on this platform).
- **Benchmark maintenance.** Append-only, versioned, governed; periodic re-review;
  retire stale/contested cases (soft-retire, audit-kept). The human-review queue is fed
  by production disagreements and Governor rejections (§H).

---

## F. Regression framework

- **Continuous regression testing.** Every candidate runs the **full benchmark**;
  CI-gated, generalizing the existing `pytest tests/` + "never commit on a red suite"
  discipline to "**never promote on a red or uninspected eval**."
- **Paired version comparison.** Candidate vs current production on the **same sealed test
  set**, with **all versions pinned** (model/contract/memory/constitution/eval-set), using
  a **paired per-case delta + significance test** (bootstrap CI / sign test) against a
  **pre-registered margin**.
- **Honesty ratchets (monotone).** Citation integrity, counter-evidence recall, and
  **control-FPR may never regress** — these only ratchet up. Predictive metrics may trade
  off only within declared bounds.
- **Shadow-mode regression.** Before promotion, the candidate runs in **shadow** on live
  traffic (generate + log, do **not** surface — the frozen `shadow → candidate →
  production` lifecycle), and its shadow metrics are compared to production. Live
  disagreement becomes benchmark fuel.

---

## G. Promotion criteria & Governor integration

The deterministic promotion decision (Appendix 2). **Governor integration is the spine:**

> **A Governor violation is an automatic, non-negotiable evaluation failure. A model that
> violates a constitutional principle never passes evaluation, regardless of its
> predictive performance** (the brief's explicit requirement). The Governor is run as the
> Stage-1 evaluator over the entire benchmark; any `violation_code` on any case ⇒ REJECT.

**Stage 1 — Hard gates (all must hold):**
1. **100% constitutional compliance** on the benchmark (0 Governor violations).
2. **≥99% schema-valid**, **0 fabrication**, **0 banned phrases**.
3. **Control-FPR does not regress** (precision frontier — the hard gate).
4. **Counter-evidence recall does not regress**; **abstention-correctness** holds on
   thin/ambiguous cases.
5. **No shortcut flag** (ablation probe, §B.3).

**Stage 2 — Graded improvement (only if Stage 1 passes):**
6. Beats production on the **honesty-weighted scorecard** by a **pre-registered,
   statistically-significant margin**.
7. No regression on any honesty ratchet; within **runtime/cost budget**.
8. **Ships a model card** (data, metrics, limits, failure modes, intended use).

**Lifecycle:** `dev → shadow → candidate → production`, pinned revision, never `latest`
(the frozen HF lifecycle). **A new version becomes production *only* if it demonstrates
measurable, reproducible, significant improvement AND violates no constitutional gate.**

---

## H. Rollback strategy

- **Triggers (post-promotion, continuously monitored):** a constitutional-violation /
  Governor-rejection spike in production; a **control-FPR regression** detected on live
  controls; calibration drift; a **trust-signal drop** (analyst reject-rate spike); a
  runtime/cost blowout.
- **Mechanism — the frozen kill switch.** Re-pin the prior `model_revision` / flip the
  enable flag — the **same env-flip rollback the scorer and Cognitive Engine already use**
  (no redeploy, instant). The **Deterministic Floor is the ultimate fallback** under
  everything (frozen).
- **Canary / staged rollout.** Promote to a fraction of traffic first; **auto-rollback on
  any gate breach** before full rollout.
- **Learn from the regression.** The failing version's eval record + the production
  incident become **new benchmark cases** (Governor `violation_codes` → labeled negatives,
  closing the loop the Governor spec opened).

---

## I. Scalability strategy

- **Tiered evaluation:** a fast **smoke suite** on every commit (cheap, deterministic
  gates); the **full benchmark** on promotion; **shadow** on sampled live traffic.
- **The gates are cheap** (the deterministic Governor + metric engine run in
  ms/case); the **expensive, bottleneck resource is human ground-truth authoring** — so
  the framework **prioritizes high-value cases** (precision-frontier controls, F1–F12
  traps, adversarial) over raw volume. *Quality of the benchmark over size.*
- **Parallel & content-addressed:** cases are independent (fan out); eval records are
  content-addressed (dedup + replay).
- **Live monitoring at millions of investigations:** sample-based (not every investigation
  is human-reviewed) + the full benchmark only at promotion; production metrics
  (control-FPR, Governor-rejection rate, trust signals) are streamed for rollback triggers.

---

## J. Future compatibility

Because the framework evaluates **the ReasoningContract output + the Governor handoff**,
*not the model*, every required future evaluates identically — **zero framework change:**

| Future | How it's evaluated |
|---|---|
| **Qwen → future reasoning models** | a new candidate behind the same contracts; same benchmark, same gates |
| **LoRA specialists** | per-contract (level 4–6); promoted only if it improves its module **without** regressing end-to-end |
| **Model ensembles / distributed reasoning** | evaluated on the assembled output; consistency metrics already cover ensemble disagreement |
| **Future Cognitive-Engine versions** | new levels added to the hierarchy (§C); the gates are unchanged |
| **New social platforms** | add a platform suite (same bundle shape); cross-platform robustness is a standing metric |
| **Future detectors / orchestration strategies** | detector-level (level 1) + end-to-end regression; must not regress control-FPR |

The benchmark + the gates are the **stable scientific contract**; what is evaluated churns
beneath. The framework **outlives any model generation** — the same posture as the
Governor.

---

## K. Dependencies

- **`OMI_CONSTITUTIONAL_GOVERNOR_V1`** — run as the Stage-1 evaluator; its `violation_codes`
  are the hard-gate failures. (Hard.)
- **`OMI_EVIDENCE_BUNDLE_SPEC_V1`** — content-addressed bundles are the eval units;
  reproducibility rides on it. (Hard.)
- **`OMI_INTELLIGENCE_MEMORY_SYSTEM_V1`** — controls, memory-influence measurement, the
  precision-frontier gate. (Hard.)
- **`OMI_REASONING_ORCHESTRATION_V1`** — ReasoningContracts are the module-level eval
  units; the Budget Controller consumes the lift this framework measures. (Hard.)
- **`OMI_COGNITIVE_ENGINE_V1`** — the F1–F12 traps, the Floor baseline, the V2 eval-set
  prerequisite. (Hard.)
- **Existing `apps/api/app/evaluation/` harness** — the seed this generalizes. (Soft.)
- **Human reviewers / gold labels** — the binding constraint (≈0 today). (Hard, external.)

---

## L. Downstream documents

| # | Document | Interface from this doc |
|---|---|---|
| 7 | **Implementation Roadmap** | the eval gates **are** the definition-of-done for each build increment; build order (Floor + Governor + metric engine + smoke suite are deterministic → ship before any model); the eval-set authoring is the near-term critical path (the V2 prerequisite, buildable now) |
| — | **Runtime Verification (GH↔HF↔Render↔Qwen)** | this framework **is** the verification standard; the eval record's version binding ties a result to the exact commit/HF-revision/Render-deploy that produced it |
| — | **Fine-tuning** | every V3/V4 candidate is gated here (engine-independent targets, grouped splits, precision-frontier gate) |
| — | **Continuous Learning** | the eval framework is the loop's gate; production disagreements + Governor rejections feed §E |

---

## M. Implementation impact (for the later build phase — not now)

- **New components:** benchmark store, metric engine, the Governor-as-evaluator harness,
  human-review tooling, the regression harness, the promotion decision function, the eval
  ledger. **Additive**, built *on* the existing `app/evaluation/` harness; zero change to
  the frozen engine/scoring/bundle/memory.
- **Deterministic core, testable without a model:** the gates, the metric engine, and the
  promotion function are deterministic → fully unit-testable; only ground-truth authoring
  needs humans. They can be built **before** any model integration (same posture as the
  Governor).
- **Discipline generalized:** "never commit on a red/uninspected suite" → "**never promote
  on a red/uninspected eval**"; report **real** metrics, **no fabricated numbers**
  (Platform Guardian §4 — the V2 audit is the cautionary tale).
- **Honest binding constraint:** the **eval set / gold ground truth is ≈0 rows today.** The
  single highest-value near-term workstream is authoring the ~50–100 reference bundles
  (precision-frontier + F1–F12 traps first) — the V2 prerequisite and the gate for
  everything downstream. The framework makes the *most* of ground truth; it cannot
  manufacture it.

---

## N. Open architectural questions (none blocks this spec)

1. **Pre-registered margin sizes** — how much improvement is "significant" per metric
   (and the exact paired test: bootstrap CI vs sign test).
2. **Honesty-vs-predictive weighting** in the Stage-2 scorecard (recommend honesty ≥ 70%).
3. **Inter-rater κ threshold** + reviewer-pool size for a gold label to count.
4. **Shadow-traffic sampling rate** for live regression detection.
5. **Benchmark-rot policy** — cadence of adding harder cases + re-sealing the test set.
6. **Cross-platform robustness** — a hard gate or a graded metric? (recommend: graded
   until a platform has enough gold, then a gate).
7. **Control-FPR budget** — the exact non-regression tolerance (recommend: 0 increase,
   strict, given the precision frontier's primacy).

---

*Canonical engineering specification only. No production code, scoring, detector, model,
dataset, or deployment was changed by this document. The Evaluation Framework is a
two-stage instrument — inviolable constitutional and precision-frontier gates first, then
honesty-weighted graded improvement on a sealed, grouped, shortcut-aware benchmark — that
promotes a change only when it is measurably, reproducibly, and significantly better
without ever becoming less trustworthy. It extends, never redesigns, the five frozen
architecture documents, and turns the Governor's constitution into the objective standard
by which every future improvement to OmiSphere is judged.*
