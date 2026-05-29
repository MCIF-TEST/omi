# Dataset ingestion & continuous training

How OMISPHERE turns files dropped into [`datasets/`](../datasets) into a
continuously growing training corpus and a learned detector — and how to keep
feeding it new data over time.

This is the operational companion to [`engine-evaluation.md`](./engine-evaluation.md),
which covers the rule-engine accuracy harness.

---

## The idea in one paragraph

Drop a CSV into `datasets/`. An **adapter** recognizes it by its column
signature (with the filename as a label hint) and maps each row to a canonical
record. **Account** rows are run through the *real* detector engine so they
land in the exact same feature space as a live YouTube scan — no train/serve
skew. **Text** rows (AI-vs-human) feed the AI-writing track. A **content-hash
ledger** means re-running ingestion only touches new or changed files, so you
can keep adding datasets indefinitely. Imported rows live in the database
alongside the labels OMISPHERE captures from its own scans, operator review,
and YouTube moderation actions; exporting the union produces the **brand-new
corpus** the two form together — which the trainer turns into a model the
serving path blends into every scan.

```
datasets/*.csv ──▶ adapter ──▶ canonical record
                                   │
        ┌──────────────────────────┴───────────────────────────┐
   accounts                                                    text
        │                                                        │
  detector engine                                      AI-writing benchmark
  (same features as live scan)                         + text-head corpus
        │                                                        │
   AccountLabel(source=imported_dataset)              datasets/_generated/
        │                                              omi_corpus_text_*.jsonl
        ▼
  export ── union with captured labels ──▶ omi_corpus_accounts_*.jsonl
        │
   train_model ──▶ omi_model.joblib ──▶ app.ml.scorer (blended at serve time)
```

---

## What's wired up for the current uploads

| File | Adapter | Kind | Notes |
|------|---------|------|-------|
| `ai vs human text/ai_vs_human_text.csv` | `ai_vs_human_text_v1` | text | `label = AI-generated / Human-written` |
| `ai vs human text/ai_vs_human_text_2026.csv` | `ai_vs_human_text_2026` | text | `text_content` + `label = ai / human` |
| `ai vs human text/ai_human_detection_v1.csv` | `ai_human_detection_v1` | text | multi-line cells; ~686 records |
| `Fake.../fake_social_media.csv` | `fake_social_media` | accounts | behavioral features + `is_fake` |
| `Fake.../fake_users.csv` + `real_users.csv` | `twitter_user_features` | accounts | label from **filename** |
| `Fake.../reddit_dead_internet_analysis_2026.csv` | `reddit_dead_internet` | accounts | `is_bot_flag` + account age |
| `Fake.../*.xlsx` | — | — | skipped (no `openpyxl`); export to CSV to ingest |

Account datasets here carry **no raw post text**, so ingestion runs them on
their profile + behavioral signals alone (the text detectors abstain). This is
deliberate — see `allow_textless` in `app/ml/public_import.py`.

---

## Commands

All from `apps/api`:

```bash
# What's in the folder and what would be ingested (no DB, no writes)
python -m scripts.datasets status

# Ingest: accounts → DB (via the engine), text → collected.
# Incremental by default — only new/changed files are processed.
python -m scripts.datasets ingest
python -m scripts.datasets ingest --all                 # re-ingest everything
python -m scripts.datasets ingest --text-out text.jsonl # also dump text rows

# Measure the rule AI-writing detector against the labeled text corpus
python -m scripts.datasets benchmark-text

# Build the combined training corpus → datasets/_generated/
python -m scripts.datasets export

# Train the learned tabular detector on the exported corpus
python -m scripts.train_model --corpus datasets/_generated/omi_corpus_accounts_<date>.jsonl

# Activate the model in the API
#   USE_ML_SCORER=true ML_MODEL_PATH=datasets/_generated/omi_model.joblib
```

---

## Adding a new dataset later

1. **Drop the file** into `datasets/` (any subfolder).
2. Run `python -m scripts.datasets status`. If it shows an adapter and `OK`,
   you're done — run `ingest`. The ledger guarantees only the new file is
   processed.
3. If it shows `--` (no adapter), you have two options:
   - **Rename / shape it** so the generic sniffers catch it: a text file needs
     a text-ish column (`text`, `content`, `body`, …) plus an AI/human label
     column; an account file needs a bot/fake label column plus a behavioral
     column (`followers`, `following`, `account_age_days`) or a text column.
     Per-class splits can encode the label in the filename (`fake_*` / `real_*`).
   - **Add a 15-line adapter** in `app/ml/datasets/adapters.py` and register it.
     Give a purpose-built adapter a `match` score `>= 10` so it beats the
     sniffers.

The feature contract (`app/ml/features.py`) is **append-only and versioned**.
Re-export and re-train after ingesting new data; the scorer refuses any model
whose `feature_schema_version` doesn't match.

---

## Measured baseline (2026-05-29)

**Account model** (smoke-trained on a 879-row slice — 575 bot / 304 human —
of the uploaded behavioral datasets, HistGradientBoosting, 25% held out):

| metric | value |
|--------|-------|
| held-out ROC-AUC | **0.826** |
| held-out accuracy | 0.723 |
| held-out Brier | 0.187 |

**AI-writing rule detector vs the full text corpus** (3,686 labeled samples):

| metric | value | reading |
|--------|-------|---------|
| coverage | **5.4%** | only long-form text clears the 120-word floor |
| overall accuracy | 0.549 | just past the 0.545 majority baseline |
| AI precision | **1.00** | when it says "AI", it is right |
| AI recall | 0.010 | …but it almost never says so |

The honest finding: **the rule AI-writing detector is high-precision but
near-blind to short social comments.** That is exactly the gap the learned
text head is meant to close, and the exported `omi_corpus_text_*.jsonl` is the
labeled data to train it on. The gate in
`tests/test_ai_writing_benchmark.py` ratchets this baseline so a regression
that starts mislabeling human text as AI trips CI.

---

## Where the code lives

| Path | Role |
|------|------|
| `app/ml/datasets/registry.py` | adapter registry + specificity-ranked auto-detection |
| `app/ml/datasets/adapters.py` | concrete + generic adapters |
| `app/ml/datasets/normalize.py` | tolerant label / count / header parsing |
| `app/ml/datasets/ledger.py` | content-hash ledger (incremental ingestion) |
| `app/ml/datasets/discovery.py` | walk folder, detect adapter, read records |
| `app/ml/datasets/ingest.py` | orchestration: plan + ingest a directory |
| `app/ml/datasets/text_corpus.py` | load / export the labeled text corpus |
| `app/ml/public_import.py` | account row → engine → persisted scan + label |
| `app/ml/export.py` | union of imported + captured labels → training JSONL |
| `app/ml/scorer.py` | load model, blend into serving scans |
| `app/evaluation/ai_writing_benchmark.py` | rule-detector-vs-corpus metrics |
| `scripts/datasets.py` | operator CLI (status / ingest / benchmark / export) |
| `scripts/train_model.py` | train the tabular model from the corpus |
