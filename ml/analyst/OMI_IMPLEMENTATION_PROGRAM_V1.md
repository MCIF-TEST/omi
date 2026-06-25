# OMI_IMPLEMENTATION_PROGRAM_V1 — The Master Engineering Blueprint

> **Status: implementation-program specification only.** This document **concludes the
> Architecture Specification Phase** and becomes the master blueprint for engineering. It
> contains **no implementation** — it sequences, scopes, and gates the work that turns the
> six frozen architecture documents into a production system. It **does not redesign**
> them.
>
> **Frozen architecture (do not redesign):**
> ✅ `OMI_COGNITIVE_ENGINE_V1` ✅ `OMI_EVIDENCE_BUNDLE_SPEC_V1`
> ✅ `OMI_INTELLIGENCE_MEMORY_SYSTEM_V1` ✅ `OMI_REASONING_ORCHESTRATION_V1`
> ✅ `OMI_CONSTITUTIONAL_GOVERNOR_V1` ✅ `OMI_ANALYST_EVALUATION_FRAMEWORK_V1`
>
> **Grounding:** the Phase-1 gap analysis (§B.1 / Appendix 1) is built from the *actual*
> repository state verified for this document — not assumptions.

---

## 0. The governing philosophy: deterministic before AI

The brief mandates the build order, and it is correct:

```
   EVIDENCE  →  INFRASTRUCTURE  →  VALIDATION  →  REASONING  →  OPTIMIZATION
 (the bundle)   (binder, stores)  (Governor)    (the council)  (LoRA / fine-tune)
   ── deterministic, model-free, unit-testable ──    ── fallible, expensive, gated ──
```

> **Build the immune system and the floor before you add the fallible reasoning.** The
> Evidence Bundle (the contract everything consumes), the Governor (the constitutional
> gate), the Deterministic Floor (the always-valid fallback), and the audit system are
> **deterministic, model-free, and exhaustively testable without a GPU** (Governor §L,
> Eval §M). Ship them first and the entire AI layer becomes *safe to add incrementally*:
> every reasoning output is gated by an already-proven Governor and falls back to an
> already-proven Floor. Build AI-first and you have no safety net while you debug the
> hardest, least-deterministic part of the system.

Each phase exists to **de-risk the next**: verify reality → prove the plumbing with the
Floor → build the deterministic foundation → add reasoning behind the gate → add memory
as a governed second input → gate everything through evaluation → only then optimize with
training → wrap it all in progressive deployment. Risk decreases monotonically because the
safety net is built before the thing it catches.

---

## Table of contents (deliverables A–N)

A. Master program → §A · B. Engineering phases → §B · C. Dependency graph → §C ·
D. GitHub plan → §D · E. Hugging Face plan → §E · F. Runtime verification → §F ·
G. Repository evolution → §G · H. Deployment → §H · I. Testing → §I ·
J. Operational → §J · K. Risk analysis → §K · L. Long-term roadmap → §L ·
M. Definition of Done → §M · N. Recommendations → §N.

---

## A. Master implementation program (the eight phases)

| Phase | Name | Philosophy layer | Why it exists | Gate to exit |
|---|---|---|---|---|
| **1** | Architecture Verification | (pre) | Know reality before building — no assumptions | Gap analysis signed off |
| **2** | Runtime Verification | Infrastructure | Prove the *plumbing* end-to-end with the **Floor** before adding intelligence | Floor assessment renders in the UI through the full path |
| **3** | Deterministic Foundation | Evidence + Infra + Validation | Build the contract, the gate, the floor, the audit — all deterministic | 100% unit-tested; Governor green on the benchmark |
| **4** | Cognitive Engine | Reasoning | Add the fallible council **behind** the proven Governor + Floor | Council beats Floor on the eval set; off-by-default |
| **5** | Intelligence Memory | Reasoning (input 2) | Add the governed second input — context, never proof | Memory improves calibration without raising control-FPR |
| **6** | Evaluation | Validation (operationalized) | Make the scientific standard executable + continuous | Promotion pipeline gates a real candidate |
| **7** | AI Development | Optimization | LoRA / fine-tune / embeddings — *only* once gated by Phase 6 | A trained candidate passes the eval gates |
| **8** | Deployment | (wrapper) | Progressive rollout with rollback around all of it | Canary → prod with auto-rollback proven |

Phases 1–3 are **deterministic and safe**; 4–5 add reasoning behind the gate; 6 makes
improvement measurable; 7 is the only training phase; 8 wraps operations. **Phases 1–3 +
6 (the deterministic + evaluation spine) are the critical path; everything AI rides on
them.**

---

## B. Engineering phases (detail, with Definition of Done)

### Phase 1 — Architecture Verification (the grounded gap analysis)

**Why:** the Guardian's "ground truth before building." A wrong assumption here
compounds through every later phase.

**B.1 Gap analysis — what EXISTS vs what must CHANGE (verified, not assumed):**

| Architecture doc | Exists today (grounded) | Gap → action |
|---|---|---|
| **Evidence Bundle** | `ml/analyst/omi_analyst/evidence_bundle.py` — a **single-grain, lossy** projection (`project_account/campaign/narrative/investigation`); no ids, no normalization, no content-addressing | **Generalize → the Binder + normalized evidence graph** (`ev:NNNN`, `citation_index`, `bundle_id`, `epistemics`). Major new build. |
| **Cognitive Engine** | `app/reasoning/analyst.py` (flagged/async/cached wiring), `omi_analyst` (Deterministic + Qwen providers, lazy), route `POST /v1/investigations/{slug}/analyst`, `AnalystResponse` schema, tests; **Floor exists** (`DeterministicAnalystProvider`) | **The Floor + skeleton exist and are safe (off).** Build the Council/Orchestrator on top. |
| **Reasoning Orchestration** | nothing (single-pass only) | **Build** the control plane + ReasoningContracts. |
| **Constitutional Governor** | `omi_analyst/schema_validate.py` — a partial validator (schema + banned-phrase + F1/F5 seeds) | **Fold + extend → the full Governor** (S0–S11, audit, fallback ladder). |
| **Intelligence Memory** | `app/memory/` (fingerprint k-NN, `prior.py`), `CoordinationEdge`, `Campaign`/`CampaignObservation`, `Narrative`, `AccountLabel` — the **primitive, doctrine-correct seeds** | **Unify → the knowledge graph** + decay/contradiction/retrieval governance. |
| **Evaluation Framework** | `app/evaluation/*` (engine benchmarks, `seed_v1.json` = 65 cases) | **Generalize → the two-stage, multi-level, constitutional framework** + benchmark suites + promotion pipeline. |
| **Runtime AI path** | **Render has NO `OMI_ANALYST_ENABLED` / `HF_TOKEN` / `OMI_ANALYST_ENDPOINT_URL`**; 5 analyst settings exist but off, no endpoint/revision pinned; **no frontend assessment UI**; HF repo `Andrewexiga/omi-analyst-v1` = card + `base_model` pointer, **no weights**; `hf-analyst-register`/`-pull` workflows exist | **Wire the AI path** (HF Inference Endpoint + Render env + frontend) — Phase 2. |
| **Repo hygiene** | **two `render.yaml`** (root + `infrastructure/`) — the stale duplicate | **Reconcile/delete one** (single source of truth). |

**Audit procedures (HF / Render / Qwen / ML pipeline):** (a) HF — confirm
`Andrewexiga/omi-analyst-v1` card + `base_model: Qwen/Qwen3-4B-Thinking-2507-FP8`, no
weights, the register/pull workflow status; (b) Render — confirm the API/web/Postgres
services + the **absent** analyst env vars; (c) Qwen — there is **no live inference
endpoint** yet (the Qwen provider falls back to Floor when `analyst_endpoint_url` is None,
which is the current state); (d) ML pipeline — `ml/` is offline R&D, the dormant
`app/ml/scorer.py` seam is a no-op. **DoD:** the gap table above is reviewed and accepted;
no later phase proceeds on an unverified assumption.

### Phase 2 — Runtime Verification (prove the path with the Floor, before the model)

**Why:** verify *plumbing* before *intelligence*. The full path
`Browser → Frontend → Backend → Render → HF_TOKEN → HF → omi-analyst-v1 → Qwen →
Inference → Analyst → UI` has ~10 failure points; debugging them *with a deterministic
Floor in the model's place* isolates infrastructure bugs from reasoning bugs.

**Procedure:** stand up the path end-to-end with `OMI_ANALYST_ENABLED=true` but **no
endpoint** (so the Qwen provider degrades to the Floor) → confirm a *Floor* assessment
flows Browser→UI. Then add the **HF Inference Endpoint** + `HF_TOKEN` +
`OMI_ANALYST_ENDPOINT_URL` on Render and confirm the *Qwen* path produces a schema-valid
assessment that the Floor would otherwise have produced. Verify each hop independently
(§F has the full procedure + acceptance criteria + diagnostics). **DoD:** a Floor
assessment renders in the UI through the real Render path; then the Qwen endpoint returns
schema-valid output under `analyst_timeout_seconds`, with graceful Floor fallback proven
by killing the endpoint.

### Phase 3 — Deterministic Foundation (the safety net first)

**Implementation order (each step deterministic, model-free, unit-tested before the
next):**
1. **Evidence Bundle + Binder** — the normalized graph + the projection from existing
   engine outputs (generalize `evidence_bundle.py`). *Everything downstream consumes
   this, so it is literally first.*
2. **Content-addressing + version binding** — `bundle_id`, digests, the
   `(bundle_id, memory_revision, constitution_version, contract_versions, model_revision)`
   seal. *Reproducibility from day one.*
3. **Reasoning Contracts** — the model-agnostic I/O interfaces (as code + JSON schemas).
4. **Governor + Validation Pipeline (S0–S11)** — fold/extend `schema_validate.py`; the
   constitutional gate. *The immune system before the body.*
5. **Audit System** — the immutable, content-addressed `ValidationTrace` ledger.
6. **Deterministic Floor** — harden the existing `DeterministicAnalystProvider` as the
   always-valid, Governor-passing baseline.

**Why this order:** the bundle is the contract (1), made reproducible (2), described by
contracts (3), gated by the Governor (4), recorded by audit (5), with the Floor (6) as
the guaranteed output. After Phase 3 the system can already produce **gated, audited,
reproducible Floor assessments** — with zero AI. **DoD:** 100% unit-test coverage of the
deterministic components; the Governor is green on the benchmark; the Floor always passes;
no engine/scoring change.

### Phase 4 — Cognitive Engine (reasoning behind the gate)

**Incremental rollout (each increment off-by-default, gated, Floor-backed):**
1. Orchestrator control plane + the blackboard (deterministic; runs the Floor as the
   only "module" first).
2. **One specialist** (e.g., Coordination Analyst) behind its contract → Governor-gated →
   compared to Floor on the eval set.
3. The remaining specialists (parallel, blind) + Memory Analyst.
4. Synthesis tier: Hypothesis Generator → **Strategy Analyst** → Counter-Evidence/Red
   Team → Risk & Calibration.
5. The Judge + self-consistency.
6. **Batch reasoning** (map-reduce over sections/campaigns).

**Why incremental:** each module is added only when it passes its contract and the
end-to-end doesn't regress (Eval §C levels). The council never ships unless it **beats the
Floor on the eval set** (the Budget Controller's adoption lever). **DoD:** the full council
passes the constitutional gates and beats the Floor by the pre-registered margin; remains
off-by-default with Floor fallback.

### Phase 5 — Intelligence Memory (the governed second input)

**Order:** (1) project the existing stores into the `KnowledgeObject`/ledger schema
(read-only — the M1 unification); (2) deterministic Retrieval → `PriorContext`
(vector + graph); (3) the evidence-gated write path + decay/contradiction/memory-influence
quarantine (M2); (4) campaign/narrative/behavior/cross-platform knowledge; (5)
graph-DB/vector backend at scale (M3). **DoD:** memory improves calibration on the eval
set **without raising control-FPR** (the precision-frontier gate); writes only from
evidence + human anchors; never changes the echoed number or satisfies the gate.

### Phase 6 — Evaluation (the scientific standard, executable)

**Order:** (1) the benchmark store (content-addressed bundles + references), seeded from
`seed_v1.json` + the ~50–100 hand-built reference bundles (the V2 prerequisite, the
critical-path gold-data workstream); (2) the metric engine (deterministic); (3) the
Governor-as-evaluator gate; (4) the regression harness + promotion decision function; (5)
human-review tooling + appeal; (6) continuous/shadow evaluation. **DoD:** the promotion
pipeline gates a real candidate end-to-end (Stage-1 gates + Stage-2 margin), with grouped
splits + sealed test + ablation probes live.

### Phase 7 — AI Development (optimization, gated by Phase 6)

The HF roadmap (V1→V5, Memory M1→M5): V1 base+prompt (now) → V2 prompt+memory+eval-set →
**V3 LoRA adapters per role** → **V4 fine-tuned reasoning (DPO/RLAIF)** → V5 continuous
learning; plus **embedding models** (retrieval), **evaluation datasets** (gold), **model
cards**, **prompt repositories** (model-paired), **behavioral models** (the dormant
scorer). **Every trained asset is gated by Phase 6** (engine-independent targets, grouped
splits, precision-frontier gate). **DoD:** a trained candidate passes the eval gates and a
model card ships; **blocked until** the gold reasoning dataset exists.

### Phase 8 — Deployment (progressive, with rollback)

`dev → shadow (generate+log, don't surface) → canary (fraction of traffic, auto-rollback
on gate breach) → production (pinned revision)`. **DoD:** a candidate is promoted via
canary with auto-rollback demonstrated; the env-flip kill switch + Floor fallback proven;
monitoring + DR live (§H/§J).

---

## C. Dependency graph

```
                 Phase 1 (Verify) ─────────────────────────────────────────────┐
                       │                                                        │
                       ▼                                                        │
   Evidence Bundle + Binder ──► Version binding ──► Reasoning Contracts         │
       (Phase 3.1)                 (3.2)                  (3.3)                  │
            │                                              │                    │
            └──────────────► Governor + Validation (3.4) ◄─┘                    │
                                   │                                            │
                                   ▼                                            │
                          Audit (3.5) + Deterministic Floor (3.6)              │
                                   │                                            │
            Phase 2 (Runtime: prove the path with the Floor) ◄─────────────────┘
                                   │
                                   ▼
        Cognitive Engine (Phase 4) ◄──── Intelligence Memory (Phase 5, input 2)
                                   │
                                   ▼
                       Evaluation (Phase 6)  ◄── gates everything above
                                   │
                                   ▼
                       AI Development (Phase 7)  ── trained assets, gated by 6
                                   │
                                   ▼
                       Deployment (Phase 8)  ── wraps all in dev→shadow→canary→prod
```

**Critical path:** `Bundle → Governor → Floor → Runtime-verified path → Eval`. The council
(4), memory (5), and training (7) are all *downstream* of this deterministic+evaluation
spine and cannot be trusted before it exists. **Hard rule:** nothing from Phases 4/5/7
ships to production without passing Phase 6.

---

## D. GitHub implementation plan (spec → modules)

| Spec | Existing modules | New / refactor (GitHub) |
|---|---|---|
| Evidence Bundle | `ml/analyst/omi_analyst/evidence_bundle.py` (single-grain) | **new** `app/evidence/` (Binder, normalized graph, content-addressing); **new** schemas in `packages/shared` |
| Cognitive Engine | `app/reasoning/analyst.py`, `omi_analyst/{providers,analyst}.py`, route, `AnalystResponse` | **new** `app/reasoning/orchestrator/` (control plane, blackboard, specialists, debate); keep the Floor |
| Orchestration | — | **new** `app/reasoning/contracts/` (ReasoningContracts as code+schema); `ModelRunner` abstraction |
| Governor | `omi_analyst/schema_validate.py` | **new** `app/governor/` (pipeline S0–S11, audit ledger, fallback ladder) |
| Memory | `app/memory/`, `CoordinationEdge`, `Campaign*`, `Narrative`, `AccountLabel` | **new** `app/memory/graph/` (KnowledgeObject, ledger, retrieval, decay); **new** vector/graph store adapter |
| Evaluation | `app/evaluation/*`, `benchmarks/*.json` | **new** `app/evaluation/framework/` (suites, metric engine, promotion fn, regression); `eval/` benchmark store |
| Frontend | `investigations/[slug]/{commentary-block,verdict-widget}.tsx` | **new** analyst-assessment UI (evidence-for/against columns, confidence band, citations, counter-evidence) |
| Runtime | `render.yaml` (engine only) | **edit**: add `OMI_ANALYST_ENABLED`/`HF_TOKEN`/`OMI_ANALYST_ENDPOINT_URL`; **delete** the duplicate `infrastructure/render.yaml` |
| CI | `tests.yml`, `hf-*` workflows | **new** `eval.yml` (regression gate), `governor.yml` (constitutional gate), `shadow.yml` |

**New tests:** per-ReasoningContract contract tests; Governor S0–S11 unit + adversarial
suite; Binder projection tests; memory decay/quarantine tests; the full benchmark
regression. **New APIs:** the assessment endpoint already exists; add batch + memory-query
read endpoints (off by default). **New packages:** `packages/shared` evidence/contract
types shared API↔web.

---

## E. Hugging Face implementation plan

**Division of responsibility:** **GitHub = code + contracts + governance + manifests
(source of truth).** **HF = weights + datasets + model-paired artifacts (registry/store).**

| HF asset | Repo (pattern) | Versioning |
|---|---|---|
| **Base model pointer + config** | `Andrewexiga/omi-analyst-v1` (exists) | immutable HF revision; pin, never `latest` |
| **LoRA adapters (V3+)** | `Andrewexiga/omi-analyst-lora-<role>` | per-role adapter revisions over the pinned base |
| **Fine-tuned checkpoints (V4)** | `Andrewexiga/omi-analyst-v<N>` | immutable revision + model card |
| **Embedding model** | `Andrewexiga/omi-embed-v1` | for similarity retrieval |
| **Eval datasets (gold)** | `Andrewexiga/omi-analyst-eval` (private) | governed, grouped-split, revisioned |
| **Gold reasoning dataset (V3 SFT)** | `Andrewexiga/omi-reasoning-gold` (private) | the blocker; engine-independent targets |
| **Versioned system prompts** | inside the model repo, paired with each revision | prompt_version ↔ model_revision |
| **Behavioral model** | `Andrewexiga/omi-behavioral-*` | the dormant scorer's checkpoints |

**GitHub ↔ HF workflow (extend the existing pattern):** GitHub holds manifests
(`hf_repo_manifest.toml`, `upload_manifest.toml`); CI (`hf-analyst-register`,
`hf-analyst-pull`, `hf-sync-datasets`, `hf-dataset-upload`) syncs to HF with pinned
revisions; the **pull verifier** (`hf_analyst_pull_check.py`) confirms Render can fetch
the pinned revision. **Future training pipeline:** datasets in HF → train (HF/Colab/modest
GPU) → checkpoint to an HF repo → eval-gate (Phase 6) → promote revision. **Future
publishing:** only the model card + pointer are public; weights/datasets stay private
until governance approves. **Render reads HF** at serve time via the Inference Endpoint
(the `OMI_ANALYST_ENDPOINT_URL`), authenticated by `HF_TOKEN`.

---

## F. Runtime verification plan (the Phase-2 detail)

| Hop | Verification | Acceptance | Failure diagnostic |
|---|---|---|---|
| Browser → Frontend | load the investigation page | assessment panel renders (Floor) | check `OMI_API_ORIGIN`, CORS |
| Frontend → Backend | `POST /v1/investigations/{slug}/analyst` | 200 cached / 202 background / 503 off | check `analyst_enabled`, auth |
| Backend → Render | request reaches the API service | health `/health` green | Render logs, build command |
| Render → HF_TOKEN | env present | `HF_TOKEN` set on `omisphere-api` | **currently absent — must add** |
| HF_TOKEN → HF → omi-analyst-v1 | pull verifier | `snapshot_download` of the pinned revision succeeds | `hf-analyst-pull` workflow |
| HF → Qwen → Inference | endpoint call | schema-valid JSON under `analyst_timeout_seconds` | endpoint logs; **timeout → Floor fallback (proven by killing the endpoint)** |
| Inference → Analyst → UI | Governor-validated assessment | PERMIT + renders with citations | Governor `ValidationTrace`; reject → Floor |

**Core acceptance:** at every step, **disabling the AI must degrade to a clean Floor
assessment** — the path is correct only if it is correct *with the model off*. Verify the
Floor path first, then layer the Qwen endpoint.

---

## G. Repository evolution

The monorepo grows by **addition**, not disruption: new top-level `app/` packages
(`evidence/`, `governor/`, `memory/graph/`, `reasoning/orchestrator/`,
`reasoning/contracts/`, `evaluation/framework/`), a new `eval/` benchmark store, shared
types in `packages/shared`, the analyst UI under the existing `investigations/` route, and
new CI workflows. The frozen engine (`app/detection/`, `app/intelligence/`) is **untouched
unless explicitly scoped**. `ml/` stays the offline R&D + HF-asset staging tree. The
single-source-of-truth `render.yaml` replaces the duplicate.

---

## H. Deployment strategy

`dev → shadow → canary → production`, mirroring the frozen HF lifecycle + the Eval
framework: **shadow** (council runs, logs, does not surface — compare to Floor/production);
**canary** (a fraction of traffic, **auto-rollback on any constitutional/control-FPR gate
breach**); **production** (pinned revision). **Rollback** = the env-flip kill switch
(`OMI_ANALYST_ENABLED` / re-pin `analyst_hf_revision`) + the always-on Floor — instant, no
redeploy. **Monitoring**: Governor rejection-rate, control-FPR on live controls,
calibration drift, analyst accept/edit/reject, latency/cost (§J). **Disaster recovery**:
Postgres on a **paid** tier with daily backups (the only irreplaceable data —
investigations/fingerprints/labels); HF revisions are immutable; bundles + audit traces
are content-addressed and replayable; the Floor guarantees the product answers even if all
AI infrastructure is down.

---

## I. Testing strategy

Layered, mapping to the Eval hierarchy: **unit** (deterministic components — Binder,
Governor S0–S11, Floor, decay); **contract** (each ReasoningContract vs its schema —
model-swappable); **integration** (the orchestrated path with a stub model);
**constitutional** (the Governor's adversarial suite of known-violating outputs);
**evaluation/regression** (the full benchmark, the promotion gate). The Guardian gates
hold throughout: backend `pytest tests/ -q` green (report the real count), web
`typecheck` + `build` + vitest, **never commit on a red/uninspected suite**, **never
promote on a red/uninspected eval**, no fabricated metrics. The deterministic core is
**fully testable without a GPU** — the model is the *last* dependency, not the first.

---

## J. Operational strategy

**Metrics** (streamed for rollback triggers): Governor rejection-rate, **control-FPR**,
calibration (ECE), council-invocation rate + cost, latency p50/p95, analyst accept/edit/
reject (trust), tokens + $/investigation. **On-call** signals: any constitutional-violation
spike, control-FPR regression, or trust-drop → auto-rollback. **Cost control**: the Budget
Controller keeps most traffic on the Floor (sub-ms, free); the council is the exception;
cache by `(bundle_id + memory_revision + contract_version)`. **Governance**:
`datasets/manifest.toml` discipline, pseudonymity end-to-end, pinned revisions.

---

## K. Risk analysis

| Risk | Severity | Mitigation |
|---|---|---|
| **AI ships before the safety net** | critical | Phase order forces Governor + Floor (3) before the council (4); CI gate blocks |
| **Gold ground truth ≈ 0** (eval set + reasoning labels) | high (the real blocker) | Phase 6 prioritizes the ~50–100 reference bundles; V3/V4 explicitly blocked until gold exists |
| **Self-reinforcing memory** | high | the frozen quarantine + evidence-only writes + decay; control-FPR gate |
| **Shortcut/leakage mirage** (the V2 lesson) | high | grouped splits + sealed test + ablation probes (Eval §B.3) |
| **Runtime AI path unproven** | medium | Phase 2 verifies the path with the Floor *before* the model; absent Render env vars are a known, scoped gap |
| **Cost/latency of the council** | medium | tiered escalation (most traffic = Floor); cache; batch amortization |
| **Duplicate `render.yaml` drift** | low | reconcile to one source of truth in Phase 1 |
| **Engine regression from new work** | medium | the frozen engine is untouched unless scoped; full-suite gate |

---

## L. Long-term roadmap (sequencing)

- **Now → near term (deterministic spine):** Phases 1–3 + the Phase-6 benchmark seed +
  the eval-set authoring (the gold-data critical path). All deterministic/safe; ships
  Floor assessments, gated and audited.
- **Mid term (reasoning):** Phase 2 runtime AI path (HF endpoint + Render env + frontend)
  → Phase 4 council incrementally → Phase 5 memory unification (M1/M2). Off-by-default,
  Floor-backed, eval-gated.
- **Long term (optimization, V3→V5 / M3→M5):** Phase 7 LoRA → fine-tune → continuous
  learning, each behind Phase 6; Phase 5 graph/vector backend at scale; Phase 8 full
  canary/auto-rollback. **Every step gated by the eval framework + the precision frontier.**

The binding constraint across the whole horizon is unchanged and honest: **human-anchored
gold data** (analyst verdicts, disclosures, legitimate-coordination controls) — ≈0 today.
The program is sequenced so the deterministic value (gated, audited, reproducible Floor
assessments) ships *without* waiting on gold data, while the gold-data workstream runs in
parallel to unlock reasoning + training.

---

## M. Definition of Done (per phase)

| Phase | Done when |
|---|---|
| 1 | Gap table reviewed + accepted; no unverified assumptions remain |
| 2 | Floor assessment renders Browser→UI via Render; Qwen endpoint returns schema-valid output with proven Floor fallback |
| 3 | Deterministic components 100% unit-tested; Governor green on the benchmark; Floor always passes; engine untouched |
| 4 | Full council passes constitutional gates + beats Floor by the pre-registered margin; off-by-default |
| 5 | Memory improves calibration without raising control-FPR; writes evidence-only; never overrides current evidence |
| 6 | Promotion pipeline gates a real candidate (Stage-1 + Stage-2); grouped splits + sealed test + ablation live |
| 7 | A trained candidate passes the eval gates + ships a model card (blocked until gold data exists) |
| 8 | Canary→prod promotion with auto-rollback demonstrated; kill switch + Floor proven; monitoring + DR live |

**Every phase additionally inherits the Guardian gates:** full backend suite green (real
count), web typecheck/build/vitest, no fabricated metrics, no engine/scoring change unless
explicitly scoped, SAVEPOINT-isolated best-effort writes.

---

## N. Recommendations

1. **Hold the line on deterministic-before-AI.** Build the Governor + Floor + Evidence
   Bundle + audit (Phase 3) and the eval seed (Phase 6) *first*; they are cheap, safe,
   testable, and they make everything after safe. Resist the pull to wire Qwen first.
2. **Make the eval set the top near-term workstream.** Gold ground truth is the binding
   constraint for the entire AI program; authoring the ~50–100 reference bundles unblocks
   V2→V5. Start it in parallel with Phase 3.
3. **Verify the runtime path with the Floor before the model** (Phase 2) — separate
   infrastructure bugs from reasoning bugs.
4. **Keep the V1 skeleton's safety posture everywhere:** off-by-default, async, cached,
   Floor fallback, SAVEPOINT-isolated, no engine change. It is why this can be built
   incrementally without risk.
5. **One `render.yaml`.** Reconcile the duplicate immediately (Phase 1) to prevent
   deploy-config drift.
6. **Treat GitHub as code/governance truth and HF as the weights/datasets registry**, synced
   by CI with pinned revisions — never serve `latest`.
7. **Promotion is the only door to production** (Phase 6 gates), for every model, prompt,
   LoRA, module, detector, orchestration, and memory change — no exceptions.

---

*Implementation-program specification only. No production code, scoring, detector, model,
dataset, or deployment was changed by this document. It concludes the Architecture
Specification Phase and sequences the engineering that turns the six frozen architecture
documents into a production system — deterministic foundation and constitutional safety
net first, fallible reasoning behind the gate second, optimization last, every step gated
by the evaluation framework and bounded by the Deterministic Floor.*
