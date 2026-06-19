# OMI Neural Network V1 — Architecture Plan

> **Status: architecture only.** This document is a plan. It does **not** train a
> model, does **not** modify production scoring, and adds no runtime code. It
> designs how a learned model would be built in the decoupled `ml/` foundation
> and, *only when proven*, promoted through the existing dormant seam
> `apps/api/app/ml/scorer.py` — behind its flag, as a corroborating signal, never
> an override.

## 0. Framing & a necessary honesty about "neural network"

The hard constraints — **CPU-only, < $50/month, commodity hardware, fully
explainable, integrate with the heuristic engine** — and the data reality from
the Dataset Intelligence Audit (low thousands of cleanly-labeled accounts,
X-only positives, no analyst-verdict gold labels yet, missing legitimate-
coordination controls) point firmly **away from a deep neural network** and
toward a **shallow, glass-box, calibrated model**.

A deep net is the wrong tool here: it is data-hungry, opaque (conflicts directly
with *fully explainable* and Omi's *transparency over certainty* principle), and
its CPU/cost advantage over a gradient-boosted model is negative at this scale.

**Decision — V1 model:** a **calibrated gradient-boosted decision tree**
(`sklearn.ensemble.HistGradientBoostingClassifier`, already in core deps) over
the engine's own signals + behavioral features, with **monotonic constraints**
and **per-prediction attribution (SHAP)**. A **2-layer monotonic MLP** is
specified in §4 as the literal "neural" alternative (also CPU-trivial here), but
GBT is the recommended V1 for calibration + glass-box explainability.

Either way, V1 is **the long-dormant learned scorer** (`app/ml/scorer.py`),
entering the rule engine as **one additional independent axis / prior** — exactly
like the `memory` detector — subject to the same corroboration gate, single-axis
cap, and decorrelation. **It augments the heuristic engine; it never replaces it.**

---

## 1. Training pipeline (offline, in `ml/training/`)

Reproducible, config-driven, CPU. No network, no `apps/api` imports, no writes to
any production store.

```
governed datasets (datasets/manifest.toml: train/validation only)
   └─ ingest (reuse app/ml/datasets adapters, offline)        ← excludes quarantine/poison
   └─ FEATURE EXTRACTION  → ml/features/  (cached parquet, the heavy step, run once)
        • engine-signal features: run the 8 detectors over each account's raw
          profile+timeline OFFLINE to get feature parity with production
        • behavioral features: from the engineered datasets (global_2.0 etc.)
   └─ assemble matrix  → validate against ml/schemas/feature_v1
   └─ join labels      → ml/datasets/analyst_verdicts + source labels (§3)
   └─ SPLIT: grouped-by-account, time-aware (no account or time leakage)
   └─ FIT (sklearn HGBT) + class weights + monotonic constraints
   └─ CALIBRATE (isotonic / Platt on a held-out calibration fold)
   └─ EVALUATE (§5)  → ml/evaluation/ report
   └─ EMIT artifact + model card → ml/models/<name>-<version>/
```

Each run records dataset versions, feature-set version, hyperparameters, seed,
and the resulting model version → fully reproducible from its config. A run that
touches `validation`/`test` for fitting is a hard error.

---

## 2. Feature schema (`ml/schemas/feature_v1`)

A single account-level vector. Two families, both versioned and null-aware.

**A. Engine-signal features (feature parity + native explainability).** For each
production detector, its `(probability, confidence)` as computed by the live
engine (`app/detection/scoring.py`): `temporal`, `semantic`, `profile`, `voice`,
`engagement`, `memory`, `coordination`, `narrative`, `community`, plus
`ai_writing` (carried as **context-only**, mirroring its supplemental status — it
must never raise suspicion). Using these keeps the model speaking the engine's
own vocabulary, so an attribution reads as "the cadence signal drove this."

**B. Raw behavioral features (from the audited datasets).** Canonicalized across
sources: `account_age_days, followers, following, follower_following_ratio,
posts, posts_per_day, statuses/favourites/listed counts, default_profile,
verified, bio_length, username_randomness, url_rate, mention_rate, hashtag_rate,
caption_similarity, content_similarity, follow_unfollow_rate,
spam/generic_comment_rate, suspicious_links_in_bio`.

Rules: every feature declares dtype + null policy + provenance; **no PII / no
raw handle / no platform-identifying id**; a shared canonical subset spans X and
YouTube with a `platform` slice key (not a feature) so per-domain performance is
measurable. Missing engine-signals fall back to the detector's neutral/abstain
value (never imputed as suspicious).

---

## 3. Label schema (`ml/schemas/label_v1`)

Target: **binary authenticity** `y ∈ {0 = authentic, 1 = inauthentic}` with
`label_source` and `label_confidence`.

`label_source` precedence (highest-trust wins on conflict):
1. `analyst_verdict` — human gold (`Investigation.verdict`; **not yet exported** — the
   eventual eval anchor).
2. `io_disclosure` — platform-attributed coordinated accounts (the IO archives;
   positive, `political_coord`).
3. `dataset_label` — filename/column labels (`is_fake`, `real/fake_users`,
   `TwitterData_Joined.Label`).
4. `heuristic_threshold` — e.g. `activity_botscore` thresholded (lowest trust;
   reference/calibration only).

Auxiliary (for later multi-task, not V1 head): ordinal `tier`, cluster-level
`coordination` label. Class imbalance handled via class weights + threshold
calibration, **not** synthetic oversampling of disclosure text (avoids leakage).
**Hard dependency:** authentic-class quality is gated on the legitimate-
coordination controls (`known-mixed`, currently absent) — see §6.

---

## 4. Model architecture

**Recommended V1 — Calibrated Gradient-Boosted Trees (glass-box).**
`HistGradientBoostingClassifier`: ~100–300 shallow trees (max_depth 3–4),
`early_stopping`, L2, `class_weight` balanced, **monotonic_cst** so
suspicion-increasing features can only push the score up (and exculpatory
features down) — encoding the same directionality the rule engine enforces.
Wrapped in `CalibratedClassifierCV` (isotonic). Output: calibrated
`P(inauthentic)` + `model_confidence` (abstains to neutral when feature coverage
is thin). Explainability: exact per-feature **SHAP** attributions (CPU-cheap at
this depth/width).

**"Neural" alternative — Monotonic MLP.** If a neural net is required by mandate:
standardized inputs → Dense(32, ReLU) → Dense(16, ReLU) → Dense(1, sigmoid),
L2 + dropout, class weights, early stopping; **monotonicity** enforced via
non-negative weight constraints on suspicion-increasing inputs; attribution via
**Integrated Gradients**. Trains in seconds on CPU at this scale. Rejected as the
default only because GBT calibrates better and is more transparent here.

**Integration (the critical part).** The chosen model populates
`app/ml/scorer.py:get_scorer()`. Its calibrated probability enters
`detection/scoring.py` aggregation as **one additional independent axis** (a
learned prior, peer to `memory`), so:
- it is subject to the **corroboration gate + single-axis cap + decorrelation** —
  the model alone can never drive a maximal/HIGH verdict;
- the rule engine remains authoritative and is the fallback when the model
  abstains or is low-confidence;
- production scoring code is **unchanged by this document** — the seam already
  exists; wiring is a later, separately-gated task.

---

## 5. Evaluation methodology (`ml/evaluation/`)

Held-out by **account + time** (grouped, time-ordered). Primary metric is
**calibration** — probabilities must mean what they say — because Omi sells
honest probabilities, not labels.

- **Brier score + reliability curve + ECE** (primary).
- ROC-AUC / PR-AUC (discrimination), tier accuracy / macro-F1 vs `seed_v1.json`.
- **Precision-frontier gate (decisive):** false-positive rate on
  **legitimate-coordination controls** (`known-mixed`) and on `real_users` — a
  model that lifts recall by raising control FPR **fails**.
- **Baseline comparison:** must beat the rule engine's own Brier on the same
  held-out set (reuse `app/evaluation/benchmarks/{seed_v1,coordination_v1,
  coordination_rescue_v1,memory_v1}.json` offline).
- **Slice metrics:** by `platform` (X vs YouTube) and by `label_source`, to expose
  the X-only / domain-shift risk the audit flagged.
- Stratified group k-fold CV; a single touch of the locked test set at the end.

---

## 6. Promotion criteria (gate before the seam is enabled)

All must hold, or the artifact stays inert in `ml/models/`:
1. **Beats the rule baseline** on validation Brier by a pre-registered margin.
2. **Does not regress control FPR** (`known-mixed` + `real_users`) — hard gate;
   **blocked until `known-mixed` is populated** (audit gap).
3. **Calibration:** ECE below threshold; reliability curve near-diagonal.
4. **Corroboration preserved:** with the model wired as an axis, no single-axis
   maximal verdict appears on the legitimate controls.
5. **Model card present** (data, metrics, limits, failure modes, intended use).
6. Passes once on the locked test set.

**Promotion path:** load artifact into `app/ml/scorer.py` behind its existing
flag → **shadow mode** (compute + log, do not affect the served score; compare to
live) → if shadow holds for N scans, enable as a corroborating prior. **Rollback
= flip the flag.** Given the audit's *PARTIALLY-ready* verdict, V1 is expected to
live in shadow mode until analyst verdicts + `known-mixed` controls exist.

---

## 7. CPU-only training strategy

Tractable because the *modeling* data is small (thousands of accounts); the cost
is feature extraction, done once.
- **Aggregate, then model:** collapse the large IO tweet CSVs (e.g. IRA 104k
  tweets) to **per-account** feature rows; cache to parquet in `ml/features/`.
  Chunked CSV reads (the ingest pipeline is already content-hash incremental) keep
  memory bounded.
- **No embeddings by default:** semantic/text features use TF-IDF (CPU-cheap);
  `sentence-transformers` is the optional `ml` extra — if used, **precompute
  offline once** and cache vectors; never at request time.
- **Model fit:** sklearn HGBT/MLP at this scale trains in seconds–minutes on one
  commodity core; deterministic seeds.
- **Artifact:** a small (<10 MB) `joblib`/ONNX file — trivial to load and to run
  (sub-millisecond matrix op).

---

## 8. GitHub folder structure (the existing `/ml` scaffold)

V1 maps onto the foundation already created (each folder has a README); files
below are *planned*, not created here.

```
ml/
├── OMI_NEURAL_NETWORK_V1.md          ← this plan
├── schemas/feature_v1.(py|json)      feature contract (§2)
├── schemas/label_v1.(py|json)        label contract (§3)
├── datasets/{accounts,campaigns,analyst_verdicts,...}/   governed inputs (audit)
├── features/extract_engine_signals.* offline detector-feature extraction (§7)
│   └── (cached feature matrices, parquet, versioned)
├── training/train_v1.* + config.yaml reproducible pipeline (§1)
├── models/<name>-<ver>/{model.joblib, model_card.md}     inert artifacts (§4,6)
├── evaluation/eval_v1.* + reports/   calibration/FPR/baseline (§5)
└── inference/{batch_score.*, contract.md}   batch + the promotion contract (§6)
```

Decoupling invariant: nothing in `ml/` imports `apps/`; the only crossing point
is the documented contract in `ml/inference/` → `app/ml/scorer.py`.

---

## 9. Render deployment strategy (< $50/month, CPU)

- **Training is offline**, never in the request path: run locally, or as a
  **Render one-off / Cron Job** for periodic retrain. It is not part of the web or
  api web service.
- **Inference is in-process:** the api service (already on Render per
  `render.yaml`: `omisphere-api` starter) loads the small artifact at startup via
  the scorer seam and scores with a CPU matrix op — **zero new service, zero GPU,
  ~zero marginal cost.**
- **Artifact delivery:** commit the small artifact to `ml/models/` (or pull from
  object storage at boot via an env-pointed path) — no model server, no vector DB.
- **Budget:** stays inside the existing 3-service starter footprint; an optional
  monthly retrain Cron Job is a few cents of CPU. No autoscaling, no inference
  endpoint, no GPU instance.

---

## 10. Explainability layer (non-negotiable)

Explainable by construction (engine-vocabulary features) **and** by attribution.
- **Per-prediction:** SHAP (GBT) / Integrated Gradients (MLP) → "which features
  moved the learned prior, and by how much," in the same direction language the UI
  already uses (▲ raises / ▼ lowers, with magnitude).
- **Feeds existing surfaces, closing the explainability-audit gaps:** the model's
  contribution joins the engine's `contributions` + the currently-discarded
  `score_breakdown`; it appears as a labeled, corroborating axis with its own
  confidence — **never a bare number**, always with evidence-for/against and the
  "what would move it" rationale.
- **Auditable & challengeable:** every promoted model ships a model card +
  evaluation report; per-account attributions are exportable. The learned prior is
  presented as *one more piece of corroborating evidence the analyst can weigh*,
  consistent with VISION: evidence-first, probabilistic, explainable,
  analyst-controlled, transparency over certainty. A model output that cannot be
  attributed is suppressed rather than shown.

---

## Dependencies, risks, and sequencing (honest status)

- **Ready now:** stack (`scikit-learn`, `numpy` in core deps), governed labeled
  data for a v1 baseline (`fake_social_media_global_2.0` balanced + IO positives +
  `real_users` negatives), held-out benchmarks (`seed_v1` etc.), and the `ml/`
  scaffold + dormant seam.
- **Blocks production promotion (from the Dataset Audit — *PARTIALLY ready*):**
  no exported **analyst verdicts**; **`known-mixed` legitimate-coordination
  controls absent** (can't measure the control-FPR gate); **X-only positives / no
  YouTube-domain labels**; feature-parity extraction not yet built.
- **Therefore V1 sequencing:** (1) build offline feature extraction + caches;
  (2) train + calibrate a **shadow** v1 on existing data; (3) populate
  `known-mixed` + export analyst verdicts; (4) only then evaluate against the
  promotion gate and consider enabling the seam.

This plan deliberately keeps the model **small, explainable, cheap, and
subordinate to the corroboration-gated rule engine** — the opposite of a black-box
detector, and faithful to what OmiSphere is.
