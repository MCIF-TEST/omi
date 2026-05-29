# OMISPHERE — Session Handoff (2026-05-29)

## Where we left off

All code is complete and tested. The only outstanding problem is a **403 on every git push** — the proxy write token lapsed between sessions and never recovered. The new session needs to push one commit and then fix the investigate feature.

---

## CRITICAL: Push this commit first

```bash
cd /home/user/omi
git push -u origin claude/ecstatic-babbage-wu1f4
```

- Local HEAD: `9249a81` — "Continuous dataset ingestion + training: turn datasets/ into a learning loop"
- Remote branch: `claude/ecstatic-babbage-wu1f4` (still at `a010dbdf`)
- 20 files, 1,936 insertions — the full dataset training subsystem

If `git push` 403s again, try the GitHub MCP tool `mcp__github__push_files`. The last two sessions both hit 403 on both paths (proxy and MCP). Hopefully write auth is restored in the new session.

---

## What was built (commit `9249a81`)

OMISPHERE now has a continuous dataset training pipeline. Drop a CSV into `datasets/`, run one command, the model updates. Incremental by default — only new/changed files are processed.

### New files

| Path | What it does |
|------|-------------|
| `apps/api/app/ml/datasets/__init__.py` | Package exports |
| `apps/api/app/ml/datasets/records.py` | `TextRecord`, re-exports `PublicRecord` |
| `apps/api/app/ml/datasets/normalize.py` | Tolerant label/count/header parsing |
| `apps/api/app/ml/datasets/registry.py` | Specificity-ranked adapter auto-detection |
| `apps/api/app/ml/datasets/adapters.py` | 8 adapters (named + 2 generic sniffers) |
| `apps/api/app/ml/datasets/ledger.py` | Content-hash ledger for incremental ingest |
| `apps/api/app/ml/datasets/discovery.py` | Walk folder, detect adapter, read records |
| `apps/api/app/ml/datasets/ingest.py` | Orchestration: plan + ingest a directory |
| `apps/api/app/ml/datasets/paths.py` | `default_datasets_dir()` — anchors to repo root |
| `apps/api/app/ml/datasets/text_corpus.py` | Load/export labeled text corpus |
| `apps/api/app/evaluation/ai_writing_benchmark.py` | Rule detector vs corpus metrics |
| `apps/api/scripts/datasets.py` | CLI: `status / ingest / benchmark-text / export` |
| `apps/api/scripts/train_model.py` | Train tabular model from corpus → joblib |
| `apps/api/tests/test_dataset_adapters.py` | 11 adapter tests |
| `apps/api/tests/test_dataset_ledger.py` | 2 ledger tests |
| `apps/api/tests/test_ai_writing_benchmark.py` | 4 benchmark tests (real-corpus ratchet) |
| `docs/dataset-training.md` | Operator guide |

### Modified files

| Path | Change |
|------|--------|
| `apps/api/app/ml/public_import.py` | Added `allow_textless=False` param so behavioral-only account rows (no post text) ingest without being skipped |
| `apps/api/app/evaluation/__init__.py` | Exports `evaluate_ai_writing`, `evaluate_ai_writing_default` |
| `.gitignore` | Ignores ledger JSON, `_generated/` dir, `*.joblib` |

### Verified results (end-to-end test run)

- 7/7 uploaded datasets auto-detected by correct adapter
- 879 account rows ingested (575 bot / 304 human)
- Model: HistGradientBoosting, held-out ROC-AUC **0.826**, accuracy 0.723, Brier 0.187
- Scorer blends model into every scan
- Re-run: all 7 files skipped (ledger working)
- Full test suite: **343 passed**

---

## Operator commands (from `apps/api/`)

```bash
# See what's in datasets/ and what would be ingested
python -m scripts.datasets status

# Ingest new/changed files into DB
python -m scripts.datasets ingest
python -m scripts.datasets ingest --all   # force re-ingest everything

# Measure AI-writing rule detector vs labeled text corpus
python -m scripts.datasets benchmark-text

# Export training corpus to datasets/_generated/
python -m scripts.datasets export

# Train the learned detector
python -m scripts.train_model --corpus datasets/_generated/omi_corpus_accounts_<date>.jsonl

# Activate the model in the API (env vars)
USE_ML_SCORER=true ML_MODEL_PATH=datasets/_generated/omi_model.joblib
```

---

## Next task: Fix the investigate feature

The user reported: **"the investigate feature isn't working — when I click investigate and put in a YouTube URL it scans and gets to the last step and then quits and doesn't show a result."**

Suspected cause: Phase 4 refactor in `apps/api/app/orchestrator.py` importing from `app.detection.coordination.elevate` — an import that may not exist after the refactor. Start by checking:

```bash
cd /home/user/omi/apps/api
grep -r "elevate" app/ --include="*.py" -l
grep -r "from app.detection" app/orchestrator.py
python -c "from app import orchestrator"  # fast import-error check
```

---

## Repository info

- Repo: `mcif-test/omi`
- Branch: `claude/ecstatic-babbage-wu1f4`
- Working dir: `/home/user/omi`
- All dev goes on the branch above; never push to main without the user asking

---

## Uploaded datasets (in `datasets/`)

| File | Adapter | Kind |
|------|---------|------|
| `ai vs human text/ai_vs_human_text.csv` | `ai_vs_human_text_v1` | text |
| `ai vs human text/ai_vs_human_text_2026.csv` | `ai_vs_human_text_2026` | text |
| `ai vs human text/ai_human_detection_v1.csv` | `ai_human_detection_v1` | text |
| `Fake.../fake_social_media.csv` | `fake_social_media` | accounts |
| `Fake.../fake_users.csv` + `real_users.csv` | `twitter_user_features` | accounts |
| `Fake.../reddit_dead_internet_analysis_2026.csv` | `reddit_dead_internet` | accounts |
| `Fake.../*.xlsx` | — | skipped (no openpyxl) |

---

## AI-writing detector baseline (documented in `docs/dataset-training.md`)

| metric | value |
|--------|-------|
| coverage | 5.4% (only long-form text clears 120-word floor) |
| overall accuracy | 0.549 |
| AI precision | **1.00** |
| AI recall | 0.010 |

High-precision, near-blind to short social comments. The learned text head is the gap-filler. The exported `omi_corpus_text_*.jsonl` is the training data for it.
