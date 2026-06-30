# OMI_ENGINEERING_SPRINT_011 — Continuous Improvement Engine (report)

> **Engineering sprint.** Turned Omi from a system that can *evaluate* itself into one that can
> *improve* itself — through **deterministic, evidence-backed recommendations** under full human
> control. The engine consumes the existing measurement stack (Shadow Mode, replay, benchmarks,
> prompt registry, gold corpus, context + evidence metrics, Governor stats) and emits
> recommendations, each carrying its supporting metrics; it **never recommends without evidence**
> and **never changes production**. A deterministic promotion workflow (candidate → recommended →
> approved → production, + rejected / rolled_back) records human decisions; applying a change is a
> separate, deliberate human step. The Governor and every constitutional guarantee are untouched.

## A. GitHub commits

One commit on `claude/stoic-edison-2ueecx`. One new package (`app/reasoning/improvement/`), one
admin route module, three test files, and a small additive extension to `evaluate_corpus`
(context/evidence levers + it now returns the full reports). **Zero** changes to the engine,
scoring, OmiScore, the Evidence Bundle, the **Governor**, the Blackboard, the Contracts, the
Orchestrator, or any production path. The Continuous Improvement Engine is a pure analysis layer
over outputs that already exist — it has no side effects on the running system.

## B. Continuous Improvement Engine (`app/reasoning/improvement/`)

- **`snapshot.py` — `build_snapshot(corpus, config, …)`** folds a gold-corpus evaluation under one
  configuration (`prompt_version` × `context_mode` × `enrich` × `budget`) into a single flat
  metrics dict: corpus label agreement + control FPR + number-preserved (the constitutional
  invariant), shadow aggregate stats (latency, fallback, citation-failure, Governor permit/floor),
  and average context + evidence quality. Deterministic given a deterministic provider — the basis
  for **reproducible** recommendations.
- It consumes exactly the charter's inputs: Shadow Mode + replay (via `run_shadow`/`aggregate_stats`),
  benchmark results (the comparisons), the prompt registry, the gold corpus, and context / evidence /
  Governor metrics.

## C. Recommendation system (`app/reasoning/improvement/recommend.py`)

`recommend(baseline, candidate)` runs deterministic detectors and returns `Recommendation`s,
ordered most-severe first. Detected opportunities (each only when a metric crosses a threshold,
**always with the metrics attached**):
- **prompt / context / evidence improvement** (agreement up *without* control-FPR up → `promote`)
  and **regression** (agreement down → `rollback`);
- **control_fpr_increase** and **calibration_drift** (number_preserved < 1.0) → **critical**
  `rollback` (the precision + constitutional frontiers);
- **latency_regression**, **citation_regression**, **hallucination_increase** (fabricated-citation
  rate up), **governor_violation_increase**.
Each `Recommendation` is **content-addressed** (`rec:…`) so identical inputs yield an identical id
(reproducible). When there is no actionable difference, the engine returns nothing — discipline by
construction.

## D. Promotion workflow (`app/reasoning/improvement/promotion.py`)

A deterministic state machine: `candidate → recommended → approved → production`, plus `rejected`
and `rolled_back`. The `PromotionLedger` records recommendations + their transitions with a
**required actor** (promotions are attributable, never automatic) in an **append-only history**.
Illegal transitions raise; recording is idempotent by id. **Rollback** is a recommended action when
a regression is detected, and a state a human can move a production entry into — never automatic.
The ledger has **no side effects**: it records decisions; it does not touch settings, the registry,
or any config. *The engine recommends; humans approve; applying is a separate human step.*

## E. Engineering reports (`app/reasoning/improvement/report.py`)

`engineering_report(snapshots, …)` is a deterministic roll-up: **best-performing prompt**, **best
context mode**, **best evidence mode** (by agreement, tie-broken by control FPR then latency),
**agreement trend**, **control FPR** + **latency** by config, **Governor statistics**, **replay
stability** (number-preserved across configs), and a **benchmark + recommendation/promotion
summary**. Pure function of its inputs.

## F. Test results

`cd apps/api && python -m pytest tests/ -q` → **936 passed** (was 913; **+23**), 0
regressions. The three suites cover:
- **recommendation generation** — every detector (prompt/context/evidence improvement +
  regression; control-FPR; calibration; latency; citation; hallucination; Governor), severity
  ordering, **mandatory supporting metrics**, the no-difference case, **determinism + reproducible
  ids**;
- **promotion workflow** — full path to production, illegal-transition + required-actor guards,
  reject (terminal), **rollback**, idempotent recording, history, summary;
- **integration** — `build_snapshot` from the corpus is **deterministic / replay-stable**, the
  **engineering report** selects best + trends, recommendations over real snapshots, and the admin
  routes (`/recommend`, `/report`, bad-body 400).

## G. Engineering readiness

- **The improvement loop is complete and human-gated.** Omi can now produce reproducible,
  evidence-backed recommendations across every lever it can vary (prompt / context / evidence), with
  a promotion workflow that keeps every production change a human decision. The apparatus is tested
  end-to-end.
- **Signal is still gated on live inference.** Offline, every config falls back to the same
  deterministic read, so cross-config recommendations are empty by construction (correct — no
  evidence, no recommendation). The detectors, workflow, reports, and reproducibility are fully
  proven with synthetic + corpus-derived snapshots; real promotions await the endpoint.
- **Constitution: intact.** The engine changes nothing — no Governor change, no auto-deploy, no
  production mutation. It recommends; humans approve. Calibration drift and control-FPR increases are
  surfaced as **critical** so a constitutional or precision regression can never be silently promoted.

## H. Recommendation for Sprint 012

1. **Provision the endpoint and run the first real improvement cycle.** Build snapshots for the
   live model across `prompt_version` × `context_mode` × `enrich` × `budget` over the gold corpus,
   run `recommend` + `engineering_report`, and walk the **first evidence-based promotion** through
   the ledger (recommended → approved → production by a named engineer) — applying it as a config
   change only after the control-FPR gate clears.
2. **Persist the ledger + recommendation/snapshot history.** Make the `PromotionLedger` and the
   per-cycle snapshots durable (a store behind the same interface) so the improvement history is a
   permanent, reproducible record — the audit trail for every promotion, regression, and rejected
   recommendation, and the substrate for trend analysis across cycles.

---

*Long-term architecture over short-term sophistication. Omi can now improve itself scientifically
while every production change stays under human control: deterministic, evidence-backed
recommendations; a human-gated promotion workflow with no automatic deployment; reproducible,
content-addressed recommendations. The constitution held — Governor untouched, nothing mutated,
critical regressions surfaced not promoted. No engine / scoring / OmiScore change. Gates green at
commit time (936 backend tests). GitHub remains the source of truth; Hugging Face remains the source
of AI assets.*
