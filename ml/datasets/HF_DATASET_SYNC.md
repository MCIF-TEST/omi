# Dataset Sync Automation (OMI_DATASET_AUTOMATION_V1)

Automatically discovers every governed dataset, classifies it, and incrementally
syncs the uploadable ones from GitHub to the Hugging Face dataset repo
`Andrewexiga/omi-authenticity-dataset`.

Builds on the V1 upload pipeline (`HF_DATASET_UPLOAD.md`) and reuses its tested
validation + card generation. **Upload-only**: no training, no scoring change,
no `apps/api` / `apps/web` change, no deploy. ML/dataset tooling only.

## What it does
1. **Discover** every dataset governed in `datasets/manifest.toml` (both
   `[[file]]` and `[[dir]]` rules; directory archives are aggregated).
2. **Classify** each into one of three buckets with a reason:
   - **uploadable** — `train`/`eval`, account-authenticity, labeled, within the
     size limit;
   - **blocked** — `archive`/`quarantine` (governance veto, never uploaded);
   - **manual review** — everything else (coordination IO archives, text-grain
     sets, reference/no-label sets, oversized files, adapter-pending sets,
     absent intake dirs).
3. **Generate** the inventory (`dataset_inventory.json` + `.md`) and the upload
   manifest (`sync_upload_manifest.toml`, V1-schema, only the uploadable set).
4. **Incrementally upload** the uploadable datasets + an auto dataset card,
   skipping files whose content hash already matches the repo (updates never
   duplicate files; re-runs only push what changed).
5. **Preserve** the train/eval/archive/quarantine classification end-to-end.

## Files
| File | Role |
|---|---|
| `ml/datasets/hf_sync.py` | discovery + classification + incremental sync |
| `ml/datasets/sync_config.toml` | routing thresholds + per-dataset label/target overrides |
| `ml/datasets/dataset_inventory.json` / `.md` | generated inventory (all governed datasets) |
| `ml/datasets/sync_upload_manifest.toml` | generated upload manifest (uploadable only) |
| `ml/datasets/test_hf_sync.py` | stdlib tests (pytest + script runnable) |
| `.github/workflows/hf-sync-datasets.yml` | manual workflow (safe by default) |
| reused: `ml/datasets/hf_upload.py` | validation + card generation (unchanged) |

## Incremental / no-duplication
For each uploadable file the tool computes both the git-blob SHA-1 and the
SHA-256, fetches the repo's file metadata (`repo_info(files_metadata=True)`), and
**skips** the upload when either hash matches the file already at the target
path. Changed/new files are written to the same deterministic `target_path`
(overwrite in place), so updates version a file rather than creating duplicates.
The dataset card is re-uploaded only when its content changed.

## Classification rules (sync_config.toml `[routing]`)
- `archive`/`quarantine` → **blocked** (always).
- provenance `twitter_io_disclosure` → **manual review** (coordination domain).
- provenance in `manual_review_provenance` (astroturf/cresci) → **manual review**
  (needs a headerless adapter).
- `kind = "text"` → **manual review** (different grain).
- `status = "reference"` → **manual review** (no class label).
- directory (multi-file) archive → **manual review**.
- size > `max_upload_size_mb` (default 25) → **manual review**.
- otherwise, with a resolvable label (override or auto-detected) → **uploadable**.

Labels resolve from a `[[override]]` (`label_column` or constant `label_value`)
or, for CSVs, by auto-detecting a known label column. Uploadable datasets with no
resolvable label fall back to **manual review** (add an override to enable them).

## Run it
### CI (primary)
**Actions → hf-sync-datasets → Run workflow**:
- `mode`: `dry-run` (default, no upload) or `sync`.
- `only`: optional single dataset name.
- `create_repo`: create the private repo if missing (sync only).
The job runs both self-test suites, then the sync; `sync` needs a **write-capable**
`HF_TOKEN`.

### Local
```bash
python ml/datasets/hf_sync.py --discover   # write inventory + manifest only
python ml/datasets/hf_sync.py --dry-run    # + validate uploadable + plan (no network)
export HF_TOKEN=hf_...                       # write-capable
python ml/datasets/hf_sync.py --sync [--create-repo] [--only NAME]
```

## Dry-run result (this repo)
`python ml/datasets/hf_sync.py --dry-run` over `datasets/manifest.toml` — **29
governed datasets**:

**Uploadable (4)** — synced to `Andrewexiga/omi-authenticity-dataset`:
| dataset | class | rows | label |
|---|---|---|---|
| `fake_social_media_global_2.0.csv` | TRAIN | 3000 | is_fake 1941/1059 |
| `real_users.csv` | TRAIN | 2500 | real=2500 |
| `fake_users.csv` | TRAIN | 2500 | fake=2500 |
| `reddit_dead_internet_analysis_2026.csv` | EVAL | 500 | is_bot_flag 282/218 |

**Blocked (9)** — governance veto, never uploaded: `bot_detection_data.csv`
(quarantine/poison) + 8 archive sets (`fake_social_media.csv`, the `.xlsx`,
`TwitterData_FE.csv`, `Twitter_Data.csv`, `Twitter_Users.csv`,
`article_discusses_claim`, `location_data.csv`, `ai_vs_human_text.csv`).

**Manual review (16)** — 8 coordination IO archives (Russia/Iran/China/GRU/IRA/
Xinjiang/East Africa — belong in a coordination repo), `TwitterData_Joined.csv`
(102 MB, oversized), `activity_botscore.csv` (reference/no label), 2 AI-vs-human
text sets, `astroturf` + `cresci-rtbust-2019` (need adapters), and `known-good` /
`known-mixed` (declared but not yet present).

## Test results
`ml/datasets/test_hf_sync.py` — **13 passed** (pytest + script); the V1 suite
`test_hf_upload.py` — **13 passed** (regression). Covers each classification
bucket, label auto-detect + override, the git-blob-SHA-1 digest, the incremental
`needs_upload` hash logic, discovery from a temp governance tree, and that the
generated manifest re-parses under the V1 loader.
