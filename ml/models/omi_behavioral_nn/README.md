# Omi Behavioral Neural Network — V1 Foundation

> **Status: architecture only. No training, no weights, no production wiring.**
> PyTorch, CPU-only. No scoring/`use_ml_scorer` change, no deployment, no Hugging
> Face training, no model upload. This establishes the structure the first real
> Omi neural network will train inside.

Omi's first PyTorch model: a small MLP over the canonical **42-dim
OMI_FEATURE_SCHEMA_V1** account vector → `P(inauthentic)`. It is framed as an
additive *re-aggregator* over the engine's own signals (consistent with the
dormant serving seam `apps/api/app/ml/scorer.py`), but is **not** connected to it.

## A. Folder structure
```
ml/models/omi_behavioral_nn/
├── README.md              # this file (folder + architecture + schema + status)
├── model.py               # OmiBehavioralNet (PyTorch MLP) + ModelConfig + save/load
├── dataset_builder.py     # OMI_FEATURE_SCHEMA_V1 -> ordered 42-dim vector (torch-free)
├── train_nn.py            # CPU training loop — defined but NOT run (gated)
├── evaluate_nn.py         # pure-numpy metrics + torch-lazy model evaluator
├── predict_nn.py          # feature dict -> vector -> P(inauthentic) inference path
└── test_nn_foundation.py  # architecture tests (torch-free always; model tests skip w/o torch)
```
`dataset_builder.py`, `train_nn.py`, `evaluate_nn.py`, `predict_nn.py` import
torch **lazily**, so everything except `model.py` imports and is testable without
PyTorch installed.

## B. Neural network architecture
`OmiBehavioralNet` (`model.py`) — configurable MLP, CPU-only:

```
input x ∈ ℝ⁴²  (OMI_FEATURE_SCHEMA_V1, normalized [0,1])
   │  LayerNorm(42)                      # stabilize blocks + engine-prior dims
   ├─ Linear(42→128) → GELU → Dropout(0.2)
   ├─ Linear(128→64) → GELU → Dropout(0.2)
   ├─ Linear(64→32)  → GELU → Dropout(0.2)
   └─ Linear(32→1)                       # single logit
output: logit → sigmoid = P(inauthentic) ∈ [0,1]
```
- **Config** (`ModelConfig`): `input_dim=42`, `hidden_dims=(128,64,32)`,
  `dropout=0.2`, `activation="gelu"|"relu"`, `input_norm=True`,
  `feature_schema_version=1`. ~16k parameters (tiny; sub-ms CPU inference).
- **Loss / optimizer (for future training):** `BCEWithLogitsLoss` + `Adam`
  (`weight_decay=1e-4`) — defined in `train_nn.py`, not executed.
- **Guards:** rejects any `input_dim != 42` and any forward input whose width
  isn't 42; deterministic via `set_seed`. `predict_proba` runs under `no_grad`.
- **Artifact bundle** (`save`/`load`): `{kind: "pytorch_mlp",
  feature_schema_version, config, state_dict, metrics, created_at}` — shaped to
  parallel the scorer convention and **refuses a mismatched feature schema**, but
  is **not** loaded by any production path.

### Why an MLP / why these inputs
The 42-dim contract is already normalized, bounded, append-only, and stored on
every account; it includes the engine's prior (`fp_overall_probability` + the
detector block) so the network learns a *residual re-aggregation* rather than a
from-scratch detector. Coordination (pair/cluster) and narrative (message)
signals live at different grains and belong to **separate** future models — they
are intentionally excluded here.

## C. Input schema (OMI_FEATURE_SCHEMA_V1)
Authoritative contract: `ml/features/OMI_FEATURE_SCHEMA_V1.md` (==
`apps/api/app/ml/features.py:build_feature_vector`, `FEATURE_SCHEMA_VERSION = 1`).
`dataset_builder.py` is the in-model mirror; the ordered 42 dims are:

| Block | Dims | Members | Default if absent |
|---|---|---|---|
| **fingerprint** (A1) | 21 | `fp_*` (interval_cov … overall_probability, confidence), normalized [0,1] via documented ranges | `0.0` |
| **detectors** (A2) | 16 | `det_<d>_{probability,confidence}` for `[temporal, semantic, ai_writing, voice, engagement, profile, memory, coordination]` | prob `0.5`, conf `0.0` |
| **metadata** (A3) | 5 | `meta_log_followers`, `meta_log_following`, `meta_log_account_age_days`, `meta_verified`, `meta_log_post_count` | `0.0` |

- **Order is fixed and append-only** — reorder/remove breaks artifacts; a new
  feature appends and bumps the version.
- **Label (future target):** binary `authenticity` (1=inauthentic, 0=authentic),
  source precedence `analyst_verdict > io_disclosure > dataset_label > heuristic`,
  **engine-independent** (never the engine's own tier) to avoid circularity.
- `build_vector(features: dict)` assembles the ordered vector applying the
  defaults above; `normalize_fingerprint(raw)` min-max normalizes raw fingerprint
  values into [0,1]; `synthetic_batch()` produces schema-shaped **random** data
  for wiring checks only (never training).

## Usage (when labels exist — see schema §C/§D for the blocker)
```bash
python ml/models/omi_behavioral_nn/train_nn.py              # build + forward smoke (NO training)
python ml/models/omi_behavioral_nn/predict_nn.py --random-init   # verify inference path (untrained)
python ml/models/omi_behavioral_nn/evaluate_nn.py          # metric functions (defined, unit-tested)
# real training is gated:
python ml/models/omi_behavioral_nn/train_nn.py --run --data <labeled.npz>   # refuses until labels exist
```

## Constraints honored
No training run · no weights produced · CPU-only · no production integration · no
scoring or `use_ml_scorer` change · no deployment · no Hugging Face training · no
model upload. ML-folder only.

## E. Test results
`test_nn_foundation.py` — architecture tests (no training):

- **With PyTorch (torch 2.12.1, CPU / `cuda=False`): 13 passed, 0 skipped.**
- Without PyTorch: **7 passed, 6 skipped** (the model tests skip cleanly; the
  torch-free schema/vector/metric tests still run). All six modules `py_compile`
  cleanly without torch.

Covered: schema is 42-dim + block membership, `build_vector` order/defaults
(absent detector → 0.5/0.0), fingerprint normalization, `vectorize_many` /
`synthetic_batch` shapes, the metric functions, forward shape `(N,42)→(N,1)`,
`input_dim != 42` + bad-width guards, seed determinism, save/load round-trip, and
the `predict_one` inference path.

Wiring smokes (build + forward only, **no training**):
```
Model: OmiBehavioralNet  input_dim=42  params=15957
Forward smoke: logits (8, 1) -> probs (8, 1) in [0.478, 0.489]
ARCHITECTURE-ONLY: training intentionally NOT run.
```
