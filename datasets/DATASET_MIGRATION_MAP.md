# DATASET MIGRATION MAP (Hugging Face organization V1)

> **No files were moved in this change** (per decision: structure + docs only,
> preserve all current paths, no production/manifest/test changes). This map is
> the authoritative current-path → proposed-HF-group mapping plus the exact
> blockers that make a *physical* move a coordinated, separately-authorized step.

## Why nothing was physically moved
A physical `git mv` of the governed corpora cannot be done without editing
production code + tests + the safety manifest:

| Blocker | What it pins | Moving would require |
|---|---|---|
| `apps/api/app/evaluation/member_elevation.py:267` (**production**) | reads `datasets/Datasets/TwitterData_Joined.csv` by path | editing production code (constraint 9) |
| `datasets/manifest.toml` (**safety**: gates poison) | governs nearly every corpus by path; quarantines `bot_detection_data.csv` | rewriting manifest paths or **silently un-gating poison** |
| `tests/test_dataset_governance.py` | asserts exact manifest paths (quarantine/validation) | editing tests |
| `tests/test_phase1_free_wins.py` | `Datasets/.../fake_social_media_global_2.0.csv`, `ai vs human text/ai_human_detection_v1.csv` | editing tests |
| `tests/test_ai_writing_benchmark.py` | `ai vs human text/` dir | editing tests |

So the safe deliverable is the **logical** reorganization (this map + the
inventory + the HF upload plan); the physical move is deferred to a single
coordinated change (recipe below) that touches those references together.

## Mapping: current path → proposed HF group · marker
### → `authenticity/`
- `human_accounts/` ← `Datasets/.../real_users.csv` (**TRAIN**); `known-good/` (**EVAL**, absent)
- `bot_accounts/` ← `Datasets/.../fake_users.csv` (**TRAIN**); `cresci-rtbust-2019/` (**EVAL**)
- `mixed_quality/` ← `Datasets/.../fake_social_media_global_2.0.csv` (**TRAIN**); `reddit_dead_internet_analysis_2026.csv` (**EVAL**); `Datasets/TwitterData_Joined.csv` (**EVAL**); `ai vs human text/ai_human_detection_v1.csv` + `ai_vs_human_text_2026.csv` (**EVAL**)
- `quarantined/` ← `Datasets/.../bot_detection_data.csv` (**QUARANTINE**)

### → `coordination/`
- `state_actor/` ← `2020-05/`, `2020-09/`, `2021-02/`, `Changyu Culture/`, `East Africa/`, `Datasets/GRU/`, `Datasets/IRA/` (+`North Africa/`), `Datasets/Xinjiang/` (all **EVAL**)
- `campaign_data/` ← `astroturf/` (**EVAL**); `apps/api/app/content/featured_campaigns.json` (**EVAL**, in-place prod asset — *pointer only*)
- `narrative_data/` ← `Narrative`/`NarrativeMembership` runtime export (**EVAL**)
- `coordination_controls/` ← `known-mixed/` (**EVAL**, absent — to collect)

### → `explainability/`
- `investigations/` ← `Investigation.payload_json` (runtime export)
- `analyst_verdicts/` ← `Investigation.verdict` + `AccountLabel` (runtime export — gold labels)
- `reports/` ← generated reports (runtime export)
- `evidence_chains/` ← engine `score_breakdown`/`contributions`/evidence (export)

### → `evaluation/`
- `benchmark_sets/` ← `apps/api/app/evaluation/benchmarks/*.json` (**EVAL**, in-place prod — *pointer only*)
- `holdout_sets/` ← `ml/models/omi-behavioral-v1/holdout.joblib` (**EVAL**, regenerable)
- `calibration_sets/` ← `Datasets/activity_botscore.csv` (**EVAL**/reference)

### → `archive/`
- `deprecated/` ← `fake_social_media.csv`, `ai_vs_human_text.csv`, `article_discusses_claim`, `fake_social_media_global_2.0_with_missing.xlsx` (**ARCHIVE**)
- `duplicates/` ← `TwitterData_FE.csv`, `Twitter_Data.csv`, `Twitter_Users.csv` (**ARCHIVE**)
- `low_trust/` ← `location_data.csv` (**ARCHIVE**)

## In-place exceptions (never move — production-loaded)
- `apps/api/app/evaluation/benchmarks/*.json` — loaded by the benchmark endpoints.
- `apps/api/app/content/featured_campaigns.json` — loaded by `seed_featured_campaigns`.
These are represented in the HF structure by reference, not relocation.

## Safe future-execution recipe (when a physical move is authorized)
One atomic change, gated by the full backend suite + a manifest-resolves check:
1. `git mv` each corpus to its target group (paths above), preserving files.
2. Update `datasets/manifest.toml` `[[dir]]`/`[[file]]` paths to the new locations
   (keep every status identical — **poison stays QUARANTINE**).
3. Update the 3 references: `member_elevation.py` base path, and the path
   constants in `test_phase1_free_wins.py` + `test_dataset_governance.py`
   (+ `test_ai_writing_benchmark.py` dir).
4. Run `cd apps/api && python -m pytest tests/ -q` (must stay green) **and** a
   manifest-resolves assertion (every declared path exists; no orphaned rule).
5. Only then commit. Rollback = `git revert` (git mv is reversible).

*This change made no moves and touched no production code, manifest, or tests.*
