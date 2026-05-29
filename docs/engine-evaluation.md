# Detection-Engine Evaluation

> How we measure whether the omi detection engine is actually good — and the
> findings that measurement produced. This is the backbone of the
> "intelligence-grade, continuously improving" mandate: accuracy is a tracked
> number, not an assumption.

## The harness

`apps/api/app/evaluation/` runs the live engine over a labeled benchmark and
scores it. One metric implementation (`metrics.py`) is shared by three callers
so they can never disagree:

| Caller | Purpose |
|---|---|
| `tests/test_evaluation_benchmark.py` | CI **gate** — fails the build on regression |
| `GET /v1/intelligence/benchmark` (admin) | In-product **scoreboard** |
| `python -m scripts.calibrate` | Operator **CLI** (pretty output, `--from-db`, `--check`) |

Metrics: Brier score, tier accuracy, macro-F1, per-tier precision/recall/F1,
confusion matrix, per-detector influence, and the majority-class baseline the
engine must beat.

### Run it

```bash
cd apps/api
python -m scripts.calibrate                 # seed benchmark, pretty report
python -m scripts.calibrate --json          # machine-readable
python -m scripts.calibrate --from-db       # real labeled accounts vs persisted scans
python -m pytest tests/test_evaluation_benchmark.py
```

## The benchmark

`app/evaluation/benchmarks/seed_v1.json` — 65 curated single-account
archetypes spanning every tier (22 low, 15 moderate, 14 elevated, 14 high) and
every detector. The schema is documented in `benchmark.py`.

As real ground truth accumulates (YouTube suspensions auto-captured, analyst
labels via the LabelWidget), export it into additional benchmark files with
the same schema and the harness measures the engine against reality. The gate
constants in the test are a **ratchet** — tighten them as accuracy improves.

## Baseline (seed_v1, hashing-embedder backend)

| Metric | Value |
|---|---|
| Brier score | 0.116 |
| Tier accuracy | **38.5%** (majority-class baseline: 33.8%) |
| Macro-F1 | 0.23 |

Per-tier recall: low **1.00**, moderate **0.07**, elevated **0.00**, high **0.14**.

The engine barely beats "always guess low." It systematically **under-flags**:
13/14 elevated and 14/15 moderate accounts are scored LOW. This was invisible
before the harness — the unit tests only assert *ordering* (bot > human), never
absolute calibration.

## Root cause (harness-driven)

Two candidate fixes were tested against the harness and **rejected**:

1. **Raise the prior.** A sweep (0.15 → 0.45) made accuracy *worse* at every
   step — it lifts the 22 clean accounts into false positives without
   strengthening real signals. The prior is not the lever.
2. **Per-detector weight tuning on the seed set.** Rejected as overfitting: 65
   synthetic archetypes encode the fixture author's judgments, not real
   outcomes. Tuning to them corrupts the benchmark's value as ground truth.

The actual mechanism: on subtle/mixed accounts the **discriminating detectors
emit high probability but low confidence** — e.g. `voice p0.80/c0.17`,
`ai_writing p0.72/c0.41`, `temporal p0.55/c0.04`. Log-odds aggregation scales
each signal's push by `confidence × weight`, so these genuine alarms are
attenuated to near-nothing and the posterior stays pinned at the 0.15 prior.

Low confidence is itself **by design and partly correct**: temporal needs ~30+
posts, voice ~800 words, ai_writing ~600 words. Typical YouTube commenters have
a handful of comments, so the per-account detectors are data-starved. The rule
engine is conservative under scarcity — it prefers a miss to a false accusation.

A second structural limit: **the seed benchmark is single-account**, so it
cannot exercise the engine's real strength — cross-account **coordination** and
**memory**, which need no per-account history depth (their influence is 0 on
this benchmark). The product flags coordinated campaigns via clusters on a
video; the current benchmark doesn't measure that path at all.

## Coordination benchmark (coordination_v1)

`app/evaluation/benchmarks/coordination_v1.json` — 13 video scenarios exercising
the five cross-account detectors (age_cohort, co_engagement, style_match,
temporal_semantic, fingerprint_cluster).  The seed_v1 benchmark scores all
of these at **zero influence** because they require a peer batch.

| Metric | Value |
|---|---|
| Cluster recall | **0.857** (6/7 planted clusters matched) |
| Member precision | **1.000** (zero false positives on current fixture) |
| Member recall | **0.837** (one burst-bot member at cluster edge) |
| Clean pass rate | **1.000** (6/6 organic-only scenarios correctly silent) |

The one miss (cluster recall < 1): `mixed_bot_ring_with_organic_noise` has 6 bots
in 26 accounts = 23% share, 2 points below the age_cohort detector's 25% threshold.
This is expected behavior — the detector is deliberately conservative under sparse
signal — and is now a documented baseline, not a silent failure.

Callers:

| Caller | Purpose |
|---|---|
| `tests/test_coordination_benchmark.py` | CI gate — 4 accuracy + 4 invariant tests |
| `GET /v1/intelligence/benchmark/coordination` (admin) | In-product coordination scoreboard |

## Coordination rescue (coordination_rescue_v1) — the end-to-end thesis

The two benchmarks above measure the halves in isolation. This one measures the
**bridge** that is the entire product value proposition: when a sparse-history
bot the single-account engine scores LOW sits inside a detected coordination
cluster, the coordination signal lifts it into the correct tier.

The elevation logic was inline in the orchestrator's full-scan path (Phase 4);
it is now extracted to `app/detection/coordination/elevate.py` (`pure`,
unit-tested) so the orchestrator and this benchmark run **the same code** —
what CI measures is exactly what production does. The runner drives the real
path end-to-end: `analyze_account` (standalone) → coordination detectors →
`apply_coordination`.

`app/evaluation/benchmarks/coordination_rescue_v1.json` — 3 scenarios (temporal
burst, fingerprint family, age cohort), 21 sparse-history bots + 9 organics.

| Metric | Value | Meaning |
|---|---|---|
| standalone_bot_recall | **0.000** | the engine *alone* catches none of the bots |
| adjusted_bot_recall | **0.952** | coordination catches 95% of them |
| recall_lift | **+0.952** | the headline: miss → catch |
| rescue_rate | **1.000** | every under-flagged in-cluster bot lifted |
| mean_prob_lift | **+0.488** | average probability jump |
| organic_false_lift | **0.000** | zero clean accounts wrongly escalated |

This is the empirical answer to the root-cause finding above: the single-account
engine under-flags sparse YouTube commenters *by design*, but that is not the
product's failure mode, because the product scans **videos** — and on a video,
coordination rescues the recall the per-account path gives up, surgically
(no organic escalation).

Callers:

| Caller | Purpose |
|---|---|
| `tests/test_rescue_benchmark.py` | CI gate — recall lift, rescue rate, no organic escalation |
| `tests/test_coordination_elevate.py` | unit contract for the shared elevation logic |
| `GET /v1/intelligence/benchmark/rescue` (admin) | In-product rescue scoreboard |

## Recommended next steps (harness-gated)

1. ~~**Expand the benchmark to multi-account / coordination scenarios**~~ — **DONE.**
   `coordination_v1.json` (13 scenarios, 5 detector types). Gate: 10 tests in
   `tests/test_coordination_benchmark.py`. Scoreboard: `GET /v1/intelligence/benchmark/coordination`.
2. **Collect real ground-truth labels** (the LabelWidget + auto-captured
   YouTube suspensions already feed `AccountLabel`) and build a real benchmark
   from them via `--from-db`.
3. **Activate the dormant ML scorer** (`app/ml/`) trained on the real corpus —
   a learned model can combine weak, low-confidence signals jointly in a way the
   hand-weighted log-odds aggregator cannot. Gate it on beating this baseline.
4. **Recalibrate per-detector confidence** only as harness-gated work validated
   on held-out *real* labels — never by fitting the synthetic seed set.

Every one of these is now measurable: the number moves, the gate ratchets, and
"becomes smarter as more videos are analyzed" becomes provable rather than
asserted.
