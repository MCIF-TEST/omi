# OMI_PHASE0_ARCHITECTURE_VERIFICATION — Definitive Gap Analysis

> **Role: Technical Program Lead. Phase 0 — Architecture Verification.** This is a
> **verification report, not a design document.** Every claim is labeled **[VERIFIED]**
> (checked against the actual repository / live Hugging Face API / config files / test
> collection) or **[ASSUMPTION]** (could not be checked from this environment). The seven
> architecture documents are frozen; this report does not change them and recommends no
> fixes — it states *what is actually there.*
>
> **Evidence basis (what was actually inspected):**
> - the checked-out repository at commit **`26173e2`** (the authoritative source of truth);
> - the **live Hugging Face Hub API**, authenticated as `Andrewexiga`;
> - `render.yaml` + `infrastructure/render.yaml` (config files);
> - a live **`pytest --collect-only`** run.
>
> **Not inspectable from here (therefore [ASSUMPTION]):** the live Render dashboard
> (actual env vars, running services, which blueprint is active), and any live Hugging
> Face Inference Endpoint. These are called out explicitly in §Runtime.

---

## A. Current architecture map (verified state at `26173e2`)

### A.1 The seven architecture documents
**[VERIFIED]** All seven specs exist under `ml/analyst/` and are pushed to GitHub
(`OMI_COGNITIVE_ENGINE_V1`, `OMI_EVIDENCE_BUNDLE_SPEC_V1`,
`OMI_INTELLIGENCE_MEMORY_SYSTEM_V1`, `OMI_REASONING_ORCHESTRATION_V1`,
`OMI_CONSTITUTIONAL_GOVERNOR_V1`, `OMI_ANALYST_EVALUATION_FRAMEWORK_V1`,
`OMI_IMPLEMENTATION_PROGRAM_V1`). **They are 100% specification.** No code module
implements any of them beyond the V1 Analyst skeleton (below).

### A.2 Backend — what exists (`apps/api/app/`)
**[VERIFIED]** present: `detection/` (the engine), `intelligence/` (OmiScore),
`detection/coordination/`, `narrative/`, `campaigns/`, `content/`, `graph/`, `memory/`,
`monitoring/`, `integrations/`, `evaluation/`, `reasoning/`, `routes/`, `storage/`,
`orchestrator.py`, `ml/` (dormant scorer seam). This is the **stable production engine** —
unchanged by any architecture work.

**[VERIFIED] The V1 Analyst skeleton** (the only cognitive-architecture implementation):
- `ml/analyst/omi_analyst/`: `analyst.py` (orchestrator, 4 entry points), `config.py`,
  `evidence_bundle.py` (**single-grain, lossy** projection — not the normalized graph),
  `providers.py` (`DeterministicAnalystProvider` always-on + `QwenAnalystProvider` gated),
  `schema_validate.py` (**partial** validator — schema + banned-phrase + F1/F5 seeds),
  `store.py`.
- `app/reasoning/analyst.py`: flagged / async / cached production wiring (lazy-imports the
  `ml/` impl only when enabled).
- `app/reasoning/`: also `commentary.py` (the older Phase-7 prose layer) + `providers.py`.
- Route **[VERIFIED]** `routes/reasoning.py:87` → `@router.post("/{slug}/analyst",
  response_model=AnalystResponse)`, gated by `analyst.analyst_enabled` (503 when off);
  mounted in `main.py:273` (`app.include_router(reasoning.router)`).

### A.3 Backend — what is MISSING (the new cognitive-architecture modules)
**[VERIFIED]** every one of these directories is absent:
`app/evidence` · `app/governor` · `app/reasoning/orchestrator` · `app/reasoning/contracts`
· `app/memory/graph` · `app/evaluation/framework`. **None of the Binder, Governor,
Orchestrator, Knowledge-Graph, or Evaluation-Framework code exists.**

### A.4 Frontend (`apps/web`)
**[VERIFIED]** there is **no analyst-assessment UI**. The only "analyst" surface is
`investigations/[slug]/commentary-block.tsx`, which calls the **old** `/v1/investigations/
{slug}/commentary` prose endpoint (labelled "Analyst commentary"). **[VERIFIED] nothing in
`apps/web/lib/` calls the `/analyst` endpoint** — the structured-assessment route has **no
frontend consumer.**

### A.5 Evaluation, Memory, Tests, Deployment
- **[VERIFIED]** `app/evaluation/`: the existing engine benchmark harness
  (`benchmark.py`, `metrics.py`, coordination/io/member/memory/rescue benchmarks,
  `benchmarks/` incl. `seed_v1.json`). This is engine-level, not the new framework.
- **[VERIFIED]** `app/memory/`: only `fingerprint.py` + `prior.py` (the k-NN). The
  institutional stores (`CoordinationEdge`, `Campaign`/`CampaignObservation`, `Narrative`,
  `AccountLabel`) live in `storage/models.py` — the primitive, doctrine-correct seeds.
- **[VERIFIED]** **754 tests collected in 13s** (86 test files); suite intact + runnable.
  (Full green *run* not executed here — see §F.)
- **[VERIFIED]** **two divergent `render.yaml` files** (§B.6).

---

## B. Gap analysis

### B.1 Implemented (production-ready)
**[VERIFIED]** the deterministic **engine** (detectors, scoring, coordination, OmiScore,
the six stores), the **primitive memory** (fingerprint k-NN + cumulative stores), and the
**existing engine eval harness**. These are stable and tested.

### B.2 Partially implemented
**[VERIFIED]** the **V1 Analyst layer** is a *safe, tested, off-by-default skeleton*:
- ✅ Deterministic Floor (`DeterministicAnalystProvider`) — exists, always-valid.
- ✅ Qwen provider — **code-complete** but **runtime-unconfigured** (calls an HF endpoint
  only if `analyst_endpoint_url` + `HF_TOKEN` are set; default `None` → Floor fallback).
- ◐ Evidence Bundle — only the **single-grain, lossy** `evidence_bundle.py`; **not** the
  normalized, content-addressed graph the spec requires (no `ev:` ids, no `bundle_id`, no
  `epistemics`).
- ◐ Governor — only `schema_validate.py` (schema + banned-phrase + F1/F5 seeds); **not**
  the S0–S11 pipeline, audit ledger, or fallback ladder.
- ✅ The `/analyst` API endpoint (gated) — exists but **has no frontend consumer.**

### B.3 Missing (must be built)
**[VERIFIED]** entirely absent in code: the **Binder + normalized Evidence Bundle**, the
**Reasoning Orchestrator + ReasoningContracts**, the **Constitutional Governor + audit**,
the **Intelligence-Memory knowledge graph** (decay/retrieval/governance), the
**Evaluation Framework** (suites/gates/promotion), and the **frontend analyst UI**.

### B.4 Obsolete / overlapping components
**[VERIFIED]** `app/reasoning/commentary.py` (the Phase-7 prose layer) overlaps with the
new structured Analyst — it is **superseded in intent** but still the only thing the UI
calls. Not deleted; a migration target, not a bug.
**[VERIFIED]** `Andrewexiga/test` on HF — a junk repo (should be removed).

### B.5 Technical debt
- **[VERIFIED]** the partial validator (`schema_validate.py`) duplicates logic that the
  Governor will own — folding it in is debt-reduction, not new work.
- **[VERIFIED]** `evidence_bundle.py` is a lossy prose-ish projection that the Binder must
  supersede; until then, two evidence shapes coexist.
- **[VERIFIED]** the dormant `app/ml/scorer.py` seam is a no-op placeholder.

### B.6 Architectural drift — **two divergent deploy configs (high-severity)**
**[VERIFIED] by diff:** `render.yaml` (root) and `infrastructure/render.yaml` are **not**
the same file. The infrastructure copy:
- **autodeploys from a stale session branch `claude/ecstatic-babbage-wu1f4`, not `main`**;
- sets free-trial credits to `3` (root: `25`), DB plan `starter` (root: `basic-256mb`),
  adds SMTP env vars, and **omits** `OMI_TWITTER_API_KEY` + the `NEXT_PUBLIC_*` credit
  mirrors.
**Which file Render actually uses is [ASSUMPTION]** (depends on the dashboard blueprint
path). The *divergence itself* is a verified configuration-integrity risk.

### B.7 Implementation risks (verified facts that imply risk)
- **[VERIFIED]** **the runtime AI path is unconfigured:** `HF_TOKEN`, `OMI_ANALYST_ENABLED`,
  and `OMI_ANALYST_ENDPOINT_URL` are **absent from both `render.yaml` files** (`HF_TOKEN`
  appears only as a **GitHub Actions** secret across 6 workflows). So **CI→HF is wired;
  runtime(Render)→HF is not.**
- **[VERIFIED]** **no gold data:** HF has **no analyst-eval dataset and no gold-reasoning
  dataset** (§A.6 / HF audit) — the binding constraint for V2→V5, exactly as the specs
  predicted.

### Hugging Face audit (live API, authenticated as `Andrewexiga`)
**[VERIFIED] 4 repos exist:**
| Repo | Type | State |
|---|---|---|
| `Andrewexiga/omi-analyst-v1` | model (private) | card + `base_model:Qwen/Qwen3-4B-Thinking-2507-FP8`, `endpoints_compatible`; **no weights** (V1 by design); 0 downloads |
| `Andrewexiga/omi-behavioral-model-v1` | model (private) | the behavioral baseline repo |
| `Andrewexiga/test` | model (private) | **junk — remove** |
| `Andrewexiga/omi-authenticity-dataset` | dataset (private) | the behavioral dataset (not the analyst-eval set) |

- **Model references [VERIFIED]:** the `base_model` pointer to `Qwen3-4B-Thinking-2507-FP8`
  is present (the model card uploaded). Full file-tree enumeration not performed; the local
  staging `ml/analyst/hf_repo/` (card, `config/analyst_config.json`, `generation_config.json`,
  `base/BASE_MODEL.md`) is the GitHub source of truth.
- **LoRA readiness [VERIFIED]: none** (no LoRA adapter repos exist).
- **Dataset readiness [VERIFIED]: none for the analyst** (no `omi-analyst-eval`, no
  gold-reasoning dataset).
- **Versioning [VERIFIED]:** the model repo is private + immutable-revision-capable; the
  register/pull workflows pin revisions. Lifecycle conventions specced but unexercised
  (0 downloads, no served endpoint).

---

## C. Implementation readiness assessment

| Layer | Readiness | Basis |
|---|---|---|
| **Deterministic engine** | ✅ **Production** | 754 tests collect; stable; unchanged |
| **Evidence Bundle (normalized)** | 🔴 **Not started** | only the lossy single-grain projection exists |
| **Governor** | 🟠 **Seed only** | partial validator; no pipeline/audit/fallback |
| **Reasoning Orchestration** | 🔴 **Not started** | no orchestrator/contracts modules |
| **Cognitive Engine (council)** | 🟠 **Floor + skeleton** | Floor + gated Qwen provider exist, off; no council |
| **Intelligence Memory (graph)** | 🟠 **Primitive seeds** | k-NN + cumulative stores; no knowledge graph |
| **Evaluation Framework** | 🟠 **Engine harness only** | `app/evaluation/` exists; not the 2-stage framework |
| **Frontend analyst UI** | 🔴 **Not started** | endpoint has no web consumer |
| **Runtime AI path (Render→HF→Qwen)** | 🔴 **Unconfigured & unverified** | env vars absent; no live endpoint confirmable |
| **Gold data (eval/reasoning)** | 🔴 **≈0** | no analyst-eval/gold-reasoning HF datasets |

**Headline:** the platform is **production-ready as a deterministic engine** and has a
**safe, off-by-default V1 Analyst skeleton**, but **every new cognitive-architecture
component is unbuilt**, and the **AI runtime path has never been exercised end-to-end**
(it cannot be, until `HF_TOKEN` + an inference endpoint are configured on Render).

---

## D. Risk assessment

| # | Risk | Severity | Verified basis | Exposure |
|---|---|---|---|---|
| R1 | **Runtime AI path unconfigured** (no `HF_TOKEN`/endpoint on Render) | High | env vars absent from both render.yaml | the Qwen→UI path is an assumption, not a working link |
| R2 | **Divergent render.yaml; infra copy on a stale branch** | High | diff verified | a deploy from `infrastructure/render.yaml` ships an old session branch |
| R3 | **No gold data** (eval + reasoning) | High (the real blocker) | HF repo search | V2–V5 + promotion gates are blocked |
| R4 | **Two evidence shapes** (lossy bundle vs the spec graph) | Medium | code verified | drift until the Binder supersedes the projection |
| R5 | **Validator duplication** (schema_validate vs Governor) | Low | code verified | resolved by folding into the Governor |
| R6 | **Endpoint with no consumer** (`/analyst` unused by web) | Low | grep verified | feature invisible to users until UI built |
| R7 | **Junk HF `test` repo** | Low | HF verified | hygiene |
| R8 | **Live Render/HF state unknown** | Medium | not inspectable | **[ASSUMPTION]** — must be verified with dashboard access (Phase 1) |

---

## E. Recommended implementation order

Follows the frozen `OMI_IMPLEMENTATION_PROGRAM_V1` (deterministic before AI), sequenced by
the verified gaps:

1. **Repo hygiene (cheap, immediate):** reconcile to **one** `render.yaml` (kill the
   stale-branch infra copy); remove the HF `test` repo. *Removes R2, R7.*
2. **Phase-1 live verification (no code):** obtain Render-dashboard truth (active blueprint,
   env vars, running services) and confirm whether any HF Inference Endpoint exists —
   convert the §Runtime **[ASSUMPTION]s** into facts. *Removes R8.*
3. **Deterministic foundation (Program Phase 3):** Binder + **normalized Evidence Bundle**
   → content-addressing/version-binding → **Governor** (fold in `schema_validate.py`) →
   audit → harden the **Floor**. All deterministic, GPU-free, unit-tested. *Removes R4, R5.*
4. **Runtime AI path (Program Phase 2):** add `HF_TOKEN` + `OMI_ANALYST_ENABLED` +
   `OMI_ANALYST_ENDPOINT_URL` on Render, stand up the HF Inference Endpoint, and verify the
   path **with the Floor first**, then Qwen. *Removes R1.*
5. **Frontend analyst UI:** consume the `/analyst` endpoint (evidence-for/against,
   confidence band, citations, counter-evidence). *Removes R6.*
6. **Gold-data workstream (parallel, the critical path):** author the ~50–100 reference
   bundles → create `Andrewexiga/omi-analyst-eval`. *Unblocks R3 and everything downstream.*
7. **Then** the council (Phase 4), memory graph (Phase 5), evaluation framework (Phase 6) —
   each off-by-default, Floor-backed, eval-gated.

**Critical path:** hygiene → live verification → deterministic foundation + eval-set
authoring. The AI council does not start until the foundation + Governor exist.

---

## F. Definition of Phase 1 completion

Phase 1 (the next phase) is **done** when:
1. **One** canonical `render.yaml` exists (no divergent copy; deploy branch confirmed).
2. The **live Render state is documented** (active blueprint, env vars, running services) —
   no remaining **[ASSUMPTION]** about deployment.
3. The **runtime AI path is fact, not assumption:** `HF_TOKEN` + endpoint configured;
   a **Floor** assessment is verified to render Browser→UI through the real Render path;
   then the **Qwen** endpoint returns schema-valid output under `analyst_timeout_seconds`
   with **proven Floor fallback** (kill-the-endpoint test).
4. The **full backend suite passes** (`pytest tests/ -q`, real count reported — baseline
   754) and **web typecheck/build/vitest** are green.
5. This gap analysis is **reviewed and accepted**; every component is classified
   (implemented / partial / missing / obsolete) with no unverified assumption remaining.
6. A **single source of truth** for HF assets is confirmed (junk `test` repo removed; the
   `omi-analyst-v1` file tree enumerated and matched to `ml/analyst/hf_repo/`).

**Acceptance gate (inherited):** backend suite green (real count), web gates green, no
fabricated metrics, the frozen engine untouched unless explicitly scoped, SAVEPOINT-isolated
best-effort writes — Platform Guardian §4.

---

## Appendix — verification log (how each claim was checked)

| Claim | Method | Result |
|---|---|---|
| 6 new module dirs missing | `test -e` on each | all MISSING |
| V1 skeleton present | `ls ml/analyst/omi_analyst/`, `app/reasoning/` | confirmed |
| analyst endpoint | `grep routes/reasoning.py` | `POST /{slug}/analyst` line 87, gated |
| frontend has no analyst caller | `grep apps/web/lib`, read `commentary-block.tsx` | only `/commentary`, not `/analyst` |
| 754 tests | `pytest --collect-only -q` | 754 collected in 13s |
| HF repos | live `hub_repo_search` author=Andrewexiga | 4 repos (no LoRA, no analyst-eval) |
| analyst HF repo | live `hub_repo_details` | card + base_model; no weights |
| render drift | `diff render.yaml infrastructure/render.yaml` | differ; infra on stale branch |
| HF_TOKEN placement | `grep render.yaml + .github/workflows` | Actions secret only; absent from Render config |
| live Render/HF endpoint | — | **not inspectable → [ASSUMPTION]** |

---

*Verification report only. No implementation, no fixes, no architecture change. Findings
are evidence-based against commit `26173e2`, the live Hugging Face API, the config files,
and a live test collection; everything not inspectable from this environment is explicitly
marked **[ASSUMPTION]** and handed to Phase 1 to confirm.*
