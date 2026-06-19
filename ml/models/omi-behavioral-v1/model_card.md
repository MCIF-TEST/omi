# Model Card — `omi-behavioral-v1`

> **Offline baseline. NOT for production.** Trained and evaluated entirely inside
> `ml/`, disconnected from `apps/`. `use_ml_scorer` remains OFF; no blending, no
> deployment, no user impact. The artifact's feature schema is *not* the one the
> serving scorer expects, so it cannot be loaded into production even by accident.

## Overview
| | |
|---|---|
| Name | `omi-behavioral-v1` |
| Task | Account authenticity (binary): predict `inauthentic` (is_fake=1) |
| Output | `authenticity_probability = 1 − P(inauthentic)` (calibrated) |
| Model | **XGBoost** (`hist`, CPU) + isotonic calibration (`CalibratedClassifierCV`, 5-fold) |
| Trained | CPU-only, ~1.3 s, seed 42 |
| Feature schema | `dataset_native_v0` (25 features) — **not** the 42-dim `omi_v1` engine vector |
| Reproduce | `python ml/training/behavioral_v1/train.py && python ml/evaluation/behavioral_v1/evaluate.py` |

## Training data
`datasets/Datasets/Fake Social Media Account Detection Dataset/fake_social_media_global_2.0.csv`
(manifest `status=train`). 3,000 accounts — **1,059 inauthentic / 1,941 authentic**.
Labels are **engine-independent** (dataset-native `is_fake`), so there is no
leakage from Omi's own scoring (`label_source = dataset_label`,
OMI_LABEL_SCHEMA_V1). Features are the dataset's own engineered behavioral
columns (profile shape, posting cadence, semantic-similarity, engagement-spam,
username morphology) + platform one-hot. Class imbalance (~1.83:1) handled via
`scale_pos_weight`.

## Results

**Held-out test (25%, n=750):**
| acc | precision (inauth) | recall (inauth) | F1 | ROC-AUC | PR-AUC | Brier | ECE | **FPR** |
|---|---|---|---|---|---|---|---|---|
| 0.916 | 0.914 | 0.842 | 0.876 | 0.982 | 0.969 | 0.051 | 0.019 | **0.043** |

Confusion: TN 464 · FP 21 · FN 42 · TP 223.

**5-fold stratified CV (n=3,000):**
| acc | precision | recall | F1 | ROC-AUC | PR-AUC | Brier | ECE | FPR |
|---|---|---|---|---|---|---|---|---|
| 0.904 | 0.853 | 0.879 | 0.866 | 0.974 | 0.956 | 0.060 | 0.012 | 0.083 |

**Calibration:** ECE ≈ 0.01–0.02 — well-calibrated; the reliability table is in
`metrics.json`. **Discrimination** is strong (AUC ≈ 0.97–0.98), **FPR** low
(4–8%).

## ⚠️ Critical limitation — read before trusting the metrics
**~89% of the model's gain comes from username-string morphology**
(`username_length` 0.23, `digits_count` 0.17, `special_char_count` 0.14,
`digit_ratio` 0.12, `repeat_char_count` 0.04). The genuinely behavioral columns
(spam/follow-unfollow rates, caption/content similarity, cadence) contribute
little. **This model is largely a "random / digit-heavy handle" detector** — an
artifact of how this synthetic dataset was generated, not a deep behavioral
signal. The headline accuracy **likely overstates** real-world authenticity
discrimination, and it would not transfer to accounts whose handles look normal.
(It overlaps with — but is far narrower than — Omi's `handle_entropy` fingerprint
feature.)

Other limits:
- **Feature-schema gap:** `dataset_native_v0` ≠ the 42-dim `omi_v1` the serving
  scorer requires → structurally not loadable into production.
- **One synthetic source**, IG/FB/X mix; **no real IO/timeline data**, **no
  legitimate-coordination controls (`known-mixed`)**, **no analyst-verdict
  labels** → generalization and the precision-frontier are unproven.

## Intended use
An offline **baseline**: it stands up the train→evaluate loop on real,
governed, engine-independent labels and establishes a metric floor. It is **not**
a production detector and is **not** evidence about any real account.

## Promotion status: **BLOCKED** (shadow-only path documented separately)
Fails the promotion gate from `OMI_NEURAL_NETWORK_V1` / `OMI_LABEL_SCHEMA_V1`:
(1) wrong feature schema for serving; (2) control-FPR unmeasurable (no
`known-mixed`); (3) username-artifact dominance. `use_ml_scorer` stays OFF.

*Aligns with Omi's principles: probabilistic + calibrated output, every claim
traceable, limitations stated plainly (transparency over certainty).*
