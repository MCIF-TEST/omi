# OMI Behavioral Model V2 — Data Audit

> Offline investigation + experiment (in `ml/`). No deployment, no Hugging Face
> change, no production/scorer modification. Reproduce:
> `python ml/evaluation/behavioral_v2_audit/audit.py` (seed 42; full numbers in
> `results.json`). Builds on `omi-behavioral-v1`.

## Setup
Three models, identical pipeline (XGBoost `hist` + isotonic calibration), same
stratified 25% hold-out + 5-fold CV, on `fake_social_media_global_2.0`
(3,000; 1,059 inauthentic / 1,941 authentic):
**v1_full** (25 feats) · **no_username** (19 feats; username morphology removed)
· **username_only** (6 username feats — the shortcut probe).

---

## A. Feature Dependence Analysis
Gain share by category (v1_full):

| Category | Gain share |
|---|---|
| **username** | **70.9%** |
| profile_shape | 12.4% |
| platform_context | 5.9% |
| engagement | 4.6% |
| temporal | 3.1% |
| content_semantic | 3.1% |
| **coordination** | **0.0%** |

The model leans overwhelmingly on **username morphology** (`username_length`,
`digits_count`, `digit_ratio`, `special_char_count`, `repeat_char_count`,
`username_randomness`). Every genuine-behavior category is minor, and
**coordination is 0%** — this is a single-account dataset with no cross-account
signal at all.

## B. Shortcut-Learning Analysis
A subset of "easy" features fully accounting for performance is the definition of
a shortcut. Here the **username-only** model (6 features) **matches or beats the
full model**:

| Model | acc | F1 | ROC-AUC |
|---|---|---|---|
| v1_full (25) | 0.916 | 0.876 | 0.982 |
| **username_only (6)** | **0.925** | **0.899** | **0.985** |

→ The 19 non-username features add **nothing** on top of the handle string. The
username features encode **how this synthetic dataset generated fake handles** (a
label-generation artifact), not a transferable authenticity signal — and a real
adversary evades it for free by choosing a normal-looking handle. **Confirmed
shortcut learning.**

## C. Retraining Results — remove username features (behavior-first candidate)
Held-out test (n=750):

| model | acc | precision | recall | F1 | ROC-AUC | Brier | ECE | FPR |
|---|---|---|---|---|---|---|---|---|
| v1_full | 0.916 | 0.914 | 0.842 | 0.876 | 0.982 | 0.051 | 0.019 | 0.043 |
| **no_username** | **0.647** | **0.000** | **0.000** | **0.000** | **0.546** | 0.227 | 0.003 | 0.000 |
| username_only | 0.925 | 0.864 | 0.936 | 0.899 | 0.985 | 0.045 | 0.021 | 0.080 |

With username features removed the model **collapses to the majority class**:
accuracy 0.647 = the authentic base rate (1941/3000), precision/recall/F1 = 0
(**catches zero inauthentic accounts**), ROC-AUC 0.546 (≈ random), FPR 0.000
(predicts everyone authentic). The low ECE is meaningless — it's calibrated to a
single constant. **The genuine behavioral features in this dataset carry almost
no authenticity signal.**

## D. Recommendation for Behavioral Model V2
1. **Do not ship a model trained on this dataset's features.** Its accuracy is a
   non-transferable, trivially-gameable username artifact.
2. **V2 must be behavior-first on the `omi_v1` 42-dim engine features**
   (the documented bridge): run Omi's production detectors offline over **real
   timelines** — IO-disclosure accounts as positives (genuine coordinated
   behavior), genuine / `known-mixed` accounts as negatives — and train on the
   fingerprint + detector signals (cadence, semantic repetition, engagement,
   coordination).
3. **Exclude raw username-string features** (or hard-cap them). Omi's fingerprint
   already bounds `handle_entropy` to 1 of 21 dims — keep it bounded; never let
   handle morphology dominate.
4. **Add coordination features** (cross-account) — entirely absent here and a core
   part of Omi's value.
5. Gate with `known-mixed` control-FPR + analyst-verdict labels before any
   promotion (unchanged from the NN/label plans).

## E. Continue current datasets, or prioritize new label collection?
**Prioritize new label / feature collection.** The evidence is unambiguous: the
current *cleanest* labeled set produces a behavior-only AUC of **0.546 (random)**
once the username artifact is removed, and contributes **zero** coordination
signal. It cannot be the foundation of a behavior-first authenticity model.

Collect/build instead, in priority order:
1. **`omi_v1` 42-dim engine features over real timelines** (IO positives +
   genuine/`known-mixed` negatives) — the only path to behavioral signal.
2. **`known-mixed` legitimate-coordination controls** — to measure the precision
   frontier.
3. **Analyst-verdict gold labels** (export `Investigation.verdict` / `AccountLabel`).

Keep the pre-engineered profile-feature datasets (`global_2.0`,
`fake_users`/`real_users`) only as **sanity/negative checks** and a
username-morphology cross-reference — **not** as the primary training source.
The raw-timeline sources (IO disclosures, `TwitterData_Joined`) + offline engine
extraction are the way forward.

**Bottom line:** V1's headline metrics were a mirage — 71% of its gain, and
effectively *all* of its discrimination, came from a username-string artifact.
The current datasets do **not** contain enough genuine behavioral information to
train a behavior-first model; the next investment is data (engine-feature
extraction over real timelines + controls + analyst labels), not modeling.

*Investigation + offline experiment only — no deployment, HF, production, or
scorer changes.*
