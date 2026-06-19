# DATASET INVENTORY (Hugging Face organization V1)

> **Documentation only.** No dataset files were moved; no manifest, production, or
> test changes. Every current path is preserved as-is. This inventory classifies
> every dataset (**TRAIN / EVAL / ARCHIVE / QUARANTINE**) and maps it to a
> proposed Hugging Face group (the physical tree lives in
> `HUGGING_FACE_UPLOAD_PLAN.md`; the mapping in `DATASET_MIGRATION_MAP.md`).

Markers derive from `datasets/manifest.toml` where present
(train→TRAIN, validation→EVAL, reference→EVAL/calibration, archive→ARCHIVE,
quarantine→QUARANTINE). Dup/leakage risk flagged per the V1/V2 audits.

## Authenticity (account-grain)
| Path (current) | Marker | Size / rows | Labels | Quality | Dup risk | Leakage risk | Train | Eval | → HF group |
|---|---|---|---|---|---|---|---|---|---|
| `Datasets/Fake Social Media Account Detection Dataset/fake_social_media_global_2.0.csv` | **TRAIN** | 490 KB / 3,000 | `is_fake` (1059/1941) | high (balanced, clean) | low | **high** — ~71% signal is username morphology (V2 audit) | ✅ (baseline) | ✅ | authenticity/mixed_quality |
| `.../real_users.csv` | **TRAIN** | 1.25 MB / 2,500 | filename=real | medium (pre-normalized) | med (overlaps fake/real set) | low | ✅ (neg) | ✅ | authenticity/human_accounts |
| `.../fake_users.csv` | **TRAIN** | 1.07 MB / 2,500 | filename=fake | medium (pre-normalized) | med | low | ✅ (pos) | ✅ | authenticity/bot_accounts |
| `.../reddit_dead_internet_analysis_2026.csv` | **EVAL** | 38 KB | bot taxonomy | medium | low | low | – | ✅ | authenticity/mixed_quality |
| `Datasets/TwitterData_Joined.csv` | **EVAL** | 102 MB / 308k rows·96 accts | `Label` 1=human | high (timelines+text) | **high** (FE/Twitter_Data are variants) | low | ⚠️ (small accts) | ✅ | authenticity/mixed_quality |
| `Datasets/activity_botscore.csv` | **EVAL** (reference) | 669 KB | continuous `bot_score`, no class | medium | low | low | – | ✅ calibration | evaluation/calibration_sets |
| `ai vs human text/ai_human_detection_v1.csv` | **EVAL** | 1.6 MB / ~17,052 | `human_or_ai` (text-grain) | medium (manifest note says 686 — **drift**) | low | n/a (not authenticity label) | – | ✅ (ai_writing) | authenticity/mixed_quality |
| `ai vs human text/ai_vs_human_text_2026.csv` | **EVAL** | 697 KB / ~2,000 | `label` (text) | medium (~51% dup) | **high** | n/a | – | ✅ | authenticity/mixed_quality |
| `cresci-rtbust-2019/` (`*.tsv` + `*_tweets.json`) | **EVAL** | ~1.1 MB | human/bot | high (known benchmark) | low | low | – | ✅ (needs adapter) | authenticity/bot_accounts |
| `Datasets/Fake Social Media Account Detection Dataset/bot_detection_data.csv` | **QUARANTINE** | 7.4 MB / ~50,000 | `Bot Label` ≈ noise | ☆ poison | low | n/a | ❌ | ❌ | authenticity/quarantined |

## Coordination (network / cluster grain)
| Path (current) | Marker | Size | Labels | Quality | Leakage | → HF group |
|---|---|---|---|---|---|---|
| `2020-05/` (Russia) | **EVAL** | ~183 MB | IO-disclosed coordinated (positive) | ★★★★★ platform-attributed | low | coordination/state_actor |
| `2020-09/` (Iran) | **EVAL** | ~1.6 MB | IO positive | ★★★★★ | low | coordination/state_actor |
| `2021-02/` (Iran, Dec-2020) | **EVAL** | ~318 MB | IO positive | ★★★★★ | low | coordination/state_actor |
| `Changyu Culture/` (China) | **EVAL** | ~18 MB | IO positive | ★★★★★ | low | coordination/state_actor |
| `East Africa/` | **EVAL** | ~14 MB | IO positive | ★★★★★ | low | coordination/state_actor |
| `Datasets/GRU/` (Russia) | **EVAL** | ~16 MB / 77 users | IO positive | ★★★★★ | low | coordination/state_actor |
| `Datasets/IRA/` (+ `North Africa/`) | **EVAL** | ~44 MB | IO positive | ★★★★★ | low | coordination/state_actor |
| `Datasets/Xinjiang/` (China) | **EVAL** | ~15 MB / 2,065 users | IO positive | ★★★★★ | low | coordination/state_actor |
| `astroturf/astroturf.tsv` | **EVAL** | 17 KB | political astroturf bots | ★★★ (needs adapter) | low | coordination/campaign_data |
| `apps/api/app/content/featured_campaigns.json` *(in-place, prod asset)* | **EVAL** (demo) | 9.6 KB | engine-derived scores | ☆ as label (derived) | **high** (engine output) | coordination/campaign_data |
| Narrative store (`Narrative`/`NarrativeMembership`, runtime) | **EVAL** (on export) | runtime | engine-derived clusters | — | — | coordination/narrative_data |
| `known-mixed/` *(declared in manifest, **absent on disk**)* | **EVAL** (control) | 0 | legitimate-coordination controls | — | low | coordination/coordination_controls |
| `known-good/` *(declared, **absent**)* | **EVAL** | 0 | genuine accounts + text | — | low | authenticity/human_accounts |

## Explainability (runtime stores — no committed files; export targets)
| Source | Marker | → HF group |
|---|---|---|
| `Investigation.payload_json` (runtime) | EVAL | explainability/investigations |
| `Investigation.verdict` + `AccountLabel` (runtime, **gold labels**) | TRAIN/EVAL | explainability/analyst_verdicts |
| Generated reports (runtime) | EVAL | explainability/reports |
| Engine `score_breakdown`/`contributions`/evidence (mostly not persisted) | EVAL | explainability/evidence_chains |

## Evaluation (benchmarks + holdouts)
| Path (current) | Marker | Size | → HF group |
|---|---|---|---|
| `apps/api/app/evaluation/benchmarks/seed_v1.json` *(prod, in-place)* | **EVAL** | 163 KB / 65 | evaluation/benchmark_sets |
| `.../coordination_v1.json`, `coordination_rescue_v1.json`, `memory_v1.json` *(prod)* | **EVAL** | 41/19/3.9 KB | evaluation/benchmark_sets |
| `ml/models/omi-behavioral-v1/holdout.joblib` *(git-ignored, regenerable)* | **EVAL** | 726 KB | evaluation/holdout_sets |
| `Datasets/activity_botscore.csv` (also above) | **EVAL** | 669 KB | evaluation/calibration_sets |

## Archive (low value / duplicate / wrong domain)
| Path (current) | Marker | Reason | → HF group |
|---|---|---|---|
| `Datasets/Fake Social Media Account Detection Dataset/fake_social_media.csv` | **ARCHIVE** | 99.8% single class | archive/deprecated |
| `ai vs human text/ai_vs_human_text.csv` | **ARCHIVE** | templated stub text | archive/deprecated |
| `Datasets/article_discusses_claim` | **ARCHIVE** | wrong domain (fact-check) | archive/deprecated |
| `.../fake_social_media_global_2.0_with_missing.xlsx` | **ARCHIVE** | superseded by CSV (.xlsx unreadable) | archive/deprecated |
| `Datasets/TwitterData_FE.csv` | **ARCHIVE** | overlapping variant of Joined | archive/duplicates |
| `Datasets/Twitter_Data.csv` | **ARCHIVE** | overlapping variant | archive/duplicates |
| `Datasets/Twitter_Users.csv` | **ARCHIVE** | tiny aux account list | archive/duplicates |
| `Datasets/location_data.csv` | **ARCHIVE** | tiny aux (acct+location) | archive/low_trust |

## Not datasets (preserved, not classified)
`datasets/` also holds governance + report docs (`manifest.toml`, `INTAKE.md`,
`TRUST_DATASET.md`, `DATASET_INTELLIGENCE_AUDIT.md`, `PHASE*_*.md`, `TRUST_*`) and
the `ml/datasets/` scaffold READMEs — left in place.

## Summary counts
- **TRAIN:** 3 (global_2.0, real_users, fake_users)
- **EVAL:** 8 IO archives + astroturf + cresci + reddit + TwitterData_Joined + ai-text×2 + activity_botscore + 4 benchmarks (+ runtime/absent: known-good, known-mixed, narratives, analyst-verdicts)
- **ARCHIVE:** 8
- **QUARANTINE:** 1 (bot_detection_data.csv)

**Key risk flags:** `global_2.0` carries high *shortcut-learning* leakage (username morphology — V2 audit); featured_campaigns scores are engine-derived (leakage as labels); TwitterData_FE/Twitter_Data are duplicates of Joined; the IO archives are X/Twitter-only (no YouTube authenticity labels); `known-mixed` controls and analyst-verdict gold labels are absent.
