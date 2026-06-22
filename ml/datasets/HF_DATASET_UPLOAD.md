# Dataset Upload Pipeline (OMI_DATASET_UPLOAD_V1)

The first production-safe GitHub → Hugging Face dataset upload pipeline. Reads a
manifest, validates each dataset, generates a dataset card, and (only when
explicitly told) uploads eligible datasets to the target HF dataset repo
`Andrewexiga/omi-authenticity-dataset`.

**Upload-only.** Does NOT train, modify production scoring, touch `apps/api` /
`apps/web`, or deploy. ML-folder only (`ml/`) + the required workflow file.

## Files
| File | Role |
|---|---|
| `ml/datasets/upload_manifest.toml` | the manifest (what may upload + how to validate/card it) |
| `ml/datasets/hf_upload.py` | the pipeline: validate → card → (`--upload`) push |
| `ml/datasets/test_hf_upload.py` | stdlib tests (pytest + script runnable) |
| `.github/workflows/hf-dataset-upload.yml` | manual workflow (safe by default) |

## Safety model (production-safe by design)
1. **Upload requires `--upload`.** Default is validate/dry-run — you cannot
   upload by accident. The workflow's default `mode` is `validate`.
2. **Only `train`/`eval` are eligible.** `archive`/`quarantine` are never uploaded.
3. **`datasets/manifest.toml` is authoritative for exclusion.** Any dataset
   governed there as `quarantine`/`archive` is force-excluded even if the upload
   manifest says `train`/`eval` — **fail-closed on poison** (the
   `bot_detection_data.csv` noise set can never leak out).
4. **All-or-nothing validation.** If any eligible dataset fails validation,
   nothing is uploaded.
5. `HF_TOKEN` is read from the environment and never printed.

## 1. Manifest schema (`upload_manifest.toml`)
`[target]`: `repo_id`, `repo_type`, `private`, `governance_manifest`, `pretty_name`.
Each `[[dataset]]`:

| field | meaning |
|---|---|
| `name` | dataset name |
| `source_path` | path in this repo (relative to repo root) |
| `format` | `csv` \| `parquet` \| `json` (inferred from extension if omitted) |
| `label_type` | e.g. `binary_authenticity`, `account_authenticity` |
| `label_column` *or* `label_value` | in-file label column, or a constant (filename-labeled sets) |
| `intended_use` | free text |
| `trust_level` | `high` \| `medium` \| `low` \| `poison` |
| `status` | `train` \| `eval` \| `archive` \| `quarantine` |
| `target_path` | destination path inside the HF dataset repo |
| `notes` | caveats (e.g. leakage) carried into the card |

## 2. Validation (every eligible dataset)
- **exists** — `source_path` is a real file (else FAIL).
- **labels detected** — distribution of `label_column` (or the constant
  `label_value`); a declared-but-missing column FAILS; a `train` set with no
  label FAILS.
- **row count** — number of data rows (`0` FAILS).
- **schema summary** — column names + inferred types (`int`/`float`/`str`).

## 3. Supported formats
`csv` and `json` use the standard library (no extra deps). `parquet` uses
`pyarrow` (installed by the workflow). JSON accepts a top-level list of records
or `{ "data": [...] }` / `rows` / `records`.

## 4. Dataset card (auto-generated)
A `README.md` with HF YAML frontmatter is generated from the manifest +
validation results and uploaded with the data. It always carries the governance
note (labels = observations, not verdicts; quarantine/archive never uploaded;
private repo) and per-dataset rows/labels/schema/trust/caveats.

## 5. Verification instructions
### CI (primary)
1. `HF_TOKEN` secret must exist; **write-capable** for `mode=upload`
   (an existing repo, or use `create_repo`).
2. **Actions → hf-dataset-upload → Run workflow**:
   - `mode`: `validate` (default, no upload) or `upload`.
   - `only`: optional single dataset name.
   - `create_repo`: create the private repo if missing (upload only).
3. The job runs the self-test, then the pipeline; output shows per-dataset
   OK/SKIP/INVALID and a ✅/❌ step summary.

### Local
```bash
python ml/datasets/hf_upload.py --validate     # exists/labels/rows/schema, no network
python ml/datasets/hf_upload.py --dry-run      # + print the upload plan & card
export HF_TOKEN=hf_...                          # write-capable
python ml/datasets/hf_upload.py --upload [--create-repo] [--only NAME]
```

## 6. Pass/fail output
`--validate` against the real manifest (no token needed):
```
OK    fake_social_media_global_2.0       rows=3000 cols=24 labels[0=1941, 1=1059]
OK    real_users                         rows=2500 cols=34 labels[real=2500]
OK    fake_users                         rows=2500 cols=34 labels[fake=2500]
OK    reddit_dead_internet_analysis_2026 rows=500  cols=11 labels[False=282, True=218]
SKIP  fake_social_media                  governance veto: datasets/manifest.toml status=archive
SKIP  bot_detection_data                 governance veto: datasets/manifest.toml status=quarantine
VALIDATE OK: 4 eligible dataset(s) ready (no upload).
```
FAIL examples: `FAIL: HF_TOKEN is not set …` · `INVALID  <name> declared label_column '…' not in columns` → `FAIL: N eligible dataset(s) failed validation — nothing uploaded.`

## 7. Test results
`ml/datasets/test_hf_upload.py` — **13 passed** (pytest and script mode):
eligibility by status, governance veto (file + dir-prefix) overriding `train`,
CSV/JSON validation, constant `label_value`, missing-file / missing-label /
no-label failures, card field coverage, dry-run excludes quarantine (no network),
invalid-eligible aborts the run, and upload-without-token fails safely.
