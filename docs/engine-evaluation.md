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

## Recommended next steps (harness-gated)

1. **Expand the benchmark to multi-account / coordination scenarios** so we can
   measure the path the product actually relies on, not just single-account
   heuristics.
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
