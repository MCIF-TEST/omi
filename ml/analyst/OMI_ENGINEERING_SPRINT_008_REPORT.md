# OMI_ENGINEERING_SPRINT_008 — Intelligence Optimization (report)

> **Engineering sprint.** Moved from building AI infrastructure to **improving AI intelligence**
> through a repeatable, version-controlled workflow — without touching the architecture or any
> constitutional guarantee (the Governor is unchanged). Every AI-backed analyst now executes
> from a **versioned, content-addressed prompt** resolved out of a registry rather than embedded
> text, so reasoning quality can be evolved, benchmarked, A/B-tested, and rolled back as
> configuration. Shadow Mode records the full provenance of every run, and a gold evaluation
> corpus scores prompts against human labels — with the legitimate-coordination **control FPR**
> as the gate.

## A. GitHub commits

One commit on `claude/stoic-edison-2ueecx`. Two new packages
(`app/reasoning/prompts/`, `app/reasoning/evaluation/`), one new benchmark module + admin
endpoints, one new test pair, and small additive edits (the embedded behavior prompt becomes a
registered version; one new optional setting; shadow runner records versioning). **Zero**
changes to the engine, scoring, OmiScore, the Binder, the Evidence Bundle, the **Governor**, the
Blackboard, the Contracts, or the Orchestrator control plane. Sprint 002–007 paths run
untouched; the behavior analyst's *behavior* is unchanged (v1 prompt is byte-identical to the
embedded text it replaces).

## B. Prompt Registry (`app/reasoning/prompts/`)

- **`PromptSpec`** — an immutable, versioned prompt with a **content-addressed `prompt_hash`**
  (over template + constraints + output contract, so metadata edits don't churn the hash but a
  real instruction change does), plus the metadata the charter requires: analyst, version,
  creation date, author, model compatibility, reasoning objectives, constraints, expected output
  contract.
- **`PromptRegistry`** — versioned store with a config-driven **active** selection per analyst:
  `register` / `resolve` (active or explicit) / `set_active` / **`rollback`** / `versions` /
  `records` (the listing the API exposes, with the active version flagged).
- **`default_registry()`** seeds the shipped prompts: behavior `v1` (the exact Sprint-006 prompt,
  now versioned) is the conservative active default; `v2` is a refined variant available for A/B.
- **AI analysts execute from the registry, not embedded text:** `ai_behavior_analyst` resolves a
  `PromptSpec` (explicit `prompt_version` → `OMI_ANALYST_PROMPT_VERSION` → registry active) and
  stamps the `RemoteAnalyst` with `prompt_meta = {analyst, version, hash}`.

## C. Intelligence Optimization Framework (workflow)

The repeatable loop, all behind the existing contracts + Governor:
- **versioning + registry + metadata** (B); **rollback** (`set_active` to a prior version, or
  unset the config); **comparison** (`compare_prompts` — a deterministic metadata/template/hash
  diff); **experiments** (`PromptExperiment`).
- **Specialist preparation** — the workflow a future AI specialist follows *without
  architectural change*: (1) keep its deterministic analyst as the fallback, (2) register its
  prompt version(s) in the registry, (3) wrap with the generic `RemoteAnalyst` (same pattern as
  `ai_behavior_analyst`). No new specialists were implemented (per the charter); the path is
  established and proven by the behavior analyst.

## D. Benchmark infrastructure (`app/reasoning/shadow/`)

- **Full provenance per investigation:** every `ShadowReport` now carries a `versioning` block —
  **prompt** (version + hash), **model revision**, **bundle id + bundle version**
  (`version_binding`), **memory revision**, and **governor revision** — so any result is
  attributable to an exact configuration and is replayable (Sprint 007 replay still holds).
- **A/B evaluation** (`ab_evaluate`) runs the shadow pipeline once per prompt variant (each
  pinning its version) and compares the two AI-backed reads with the Sprint-007 deterministic
  comparison engine, alongside the prompt diff. Deterministic given deterministic providers.

## E. Evaluation corpus support (`app/reasoning/evaluation/`)

- **`GoldCase` / `GoldCorpus`** — curated, human-reviewed investigations with benchmark labels
  (`expected_verdict` / `expected_coordination_label` / `is_control`) + reviewer + notes.
  **Evaluation only — never training.**
- **`evaluate_corpus`** runs the shadow pipeline over every case and scores against the labels:
  per-case label agreement (production + shadow), and the **control false-positive rate** for
  both paths — a legitimate, on-message group read as hostile coordination (Platform Guardian
  §3, the precision frontier). Deterministic, so re-running is a **regression test** and running
  under a different `prompt_version` is a **prompt comparison**.

## F. Test results

`cd apps/api && python -m pytest tests/ -q` → **877 passed** (was 859; **+18**), 0
regressions. `tests/test_prompt_registry.py` + `tests/test_intelligence_optimization.py` cover:
- **prompt hashing** (content-addressed: metadata/version don't change it, template/constraints
  do), **selection**, **version rollback**, registry listing, **prompt comparison**;
- **versioned execution** (the AI analyst runs the registry template, not embedded text) and
  **config-driven selection**;
- **benchmark execution** — the full versioning block recorded per investigation;
- **A/B** between v1/v2 producing different reads with each pinned to its version, the number
  preserved on both;
- **evaluation corpus** — label scoring, **control FPR**, and **replay/regression determinism**;
- **regression safety** — production is **independent of prompt version**; the admin routes
  (`/prompts`, `/ab/{slug}`) behave (and degrade to the prompt diff offline).

## G. Engineering readiness

- **Optimization workflow: ready and exercised.** Prompts are versioned, hashed, selectable by
  config, rollback-able, comparable, and A/B-testable; every run is fully attributable;
  promotion can be gated on corpus metrics including control FPR. This is a *complete* loop.
- **Signal: still gated on live inference.** As in Sprint 007, with no HF endpoint the AI analyst
  falls back to deterministic, so A/B and corpus runs over the *live model* are null by
  construction today. The harness is proven with deterministic providers; real prompt-quality
  signal needs the endpoint.
- **Constitution: intact.** The Governor is unchanged; v1 is byte-identical to the prior prompt;
  production is prompt-independent; the number is never moved; citations stay resolvable. Prompt
  evolution cannot weaken a constitutional guarantee — those live in the Governor + contracts,
  below the prompt layer.

## H. Recommendation for Sprint 009

1. **Provision the endpoint and run the corpus.** Curate a real gold corpus (human-reviewed,
   controls included), then run `evaluate_corpus` and `ab_evaluate(v1, v2)` against the live
   model. Promote `v2` only if it **raises label agreement without raising control FPR** — the
   first evidence-based prompt promotion.
2. **Persist registry + benchmark history and add a second specialist via the established
   workflow.** Make prompt selection + experiment results durable (not just in-memory), then take
   the **Counter-Evidence Analyst** AI-backed following the 3-step specialist workflow — the
   first use of the framework to *grow* the council, still gated on corpus + control-FPR evidence
   before anything reaches production users.

---

*Long-term architecture over short-term sophistication. Intelligence improves through
measurable, version-controlled prompt evolution — not architectural change. The constitution
held: the Governor is untouched, production is prompt-independent, the number is echoed not
moved, citations stay resolvable, and the control FPR gates promotion. No engine / scoring /
OmiScore change. Gates green at commit time (877 backend tests). GitHub remains the source of
truth; Hugging Face remains the source of AI assets.*
