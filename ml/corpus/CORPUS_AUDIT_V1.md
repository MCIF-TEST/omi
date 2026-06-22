# Omi Corpus Audit (OMI_CORPUS_AUDIT_V1)

> Read-only audit of `ml/corpus/data/merged_corpus.parquet` (`ml/corpus/audit.py`). No data modified, no training, no production change.

## 1. Total rows: **36,925**

## 2. Label distribution
### Authenticity (normalized)
| class | rows | % |
|---|---|---|
| authentic(0) | 3,516 | 9.52 |
| inauthentic(1) | 32,239 | 87.31 |
| unknown(null) | 1,170 | 3.17 |

### Requested semantic buckets
| label | rows | % |
|---|---|---|
| human | 1,845 | 5.0 |
| bot | 2,547 | 6.9 |
| fake | 1,329 | 3.6 |
| authentic | 1,671 | 4.53 |
| unknown | 1,170 | 3.17 |
| ai_generated | 661 | 1.79 |
| state_io | 27,702 | 75.02 |

_human/authentic → authenticity 0; bot/fake/ai_generated/state_io → 1; unknown → null. ai_generated & state_io are the additional labels._

## 3. Dataset contribution
| dataset | rows | % |
|---|---|---|
| `russia_052020_tweets_csv_hashed_2_a` | 1,000 | 2.71 |
| `russia_052020_tweets_csv_hashed_2_b` | 1,000 | 2.71 |
| `russia_052020_users_csv_hashed` | 1,000 | 2.71 |
| `iran_092020_tweets_csv_hashed` | 1,000 | 2.71 |
| `hashed_2020_12_iran_202012_iran_202012_tweets_a` | 1,000 | 2.71 |
| `hashed_2020_12_iran_202012_iran_202012_tweets_b` | 1,000 | 2.71 |
| `CNCC_0621_tweets_csv_hashed_2014` | 1,000 | 2.71 |
| `hashed_2020_12_iran_202012_iran_202012_tweets_c` | 1,000 | 2.71 |
| `hashed_2020_12_iran_202012_iran_202012_tweets_d` | 1,000 | 2.71 |
| `CNCC_0621_tweets_csv_hashed_2012` | 1,000 | 2.71 |
| `CNCC_0621_tweets_csv_hashed_2013` | 1,000 | 2.71 |
| `fake_social_media_global_2.0` | 1,000 | 2.71 |
| `CNCC_0621_tweets_csv_hashed_2018` | 1,000 | 2.71 |
| `CNCC_0621_tweets_csv_hashed_2017` | 1,000 | 2.71 |
| `hashed_2020_12_IRA_202012_IRA_202012_tweets` | 1,000 | 2.71 |
| `hashed_2020_12_GRU_202012_GRU_202012_tweets` | 1,000 | 2.71 |
| `real_users` | 1,000 | 2.71 |
| `CNCC_0621_tweets_csv_hashed_2020` | 1,000 | 2.71 |
| `ira_092020_tweets_csv_hashed` | 1,000 | 2.71 |
| `fake_users` | 1,000 | 2.71 |
| `ai_vs_human_text_2026` | 1,000 | 2.71 |
| `REA_0621_tweets_csv_hashed_2020` | 1,000 | 2.71 |
| `REA_0621_tweets_csv_hashed_2019` | 1,000 | 2.71 |
| `TwitterData_Joined` | 1,000 | 2.71 |
| `RNA_0621_tweets_csv_hashed_2020` | 1,000 | 2.71 |
| _… 37 more_ | | |

## 4. Feature availability (% of rows populated)
| field | % populated |
|---|---|
| `record_id` | 100.0 |
| `dataset` | 100.0 |
| `source_path` | 100.0 |
| `domain` | 100.0 |
| `grain` | 100.0 |
| `text` | 82.3 |
| `author_id` | 90.84 |
| `created_at` | 83.11 |
| `lang` | 69.77 |
| `authenticity_label` | 96.83 |
| `label_raw` | 97.29 |
| `label_source` | 100.0 |
| `numeric_features_json` | 87.21 |
| `governance_status` | 100.0 |
| `schema_version` | 100.0 |

**Grain-aware completeness:** text present in 95.88% of text-grain rows; numeric features in 83.12% of account-grain rows; labels on 96.83% of all rows.

**Mostly-missing / absent:** `lang` (69.77%); engine detector/score features are **entirely absent** (the engine was never run over these accounts) — the single biggest feature gap.

Top numeric feature keys (inside `numeric_features_json`):
| key | rows | % of corpus |
|---|---|---|
| `follower_count` | 27,701 | 75.02 |
| `following_count` | 27,701 | 75.02 |
| `verified` | 2,903 | 7.86 |
| `default_profile` | 2,000 | 5.42 |
| `default_profile_image` | 2,000 | 5.42 |
| `favourites_count` | 2,000 | 5.42 |
| `followers_count` | 2,000 | 5.42 |
| `friends_count` | 2,000 | 5.42 |
| `geo_enabled` | 2,000 | 5.42 |
| `listed_count` | 2,000 | 5.42 |
| `profile_background_tile` | 2,000 | 5.42 |
| `profile_use_background_image` | 2,000 | 5.42 |
| `protected` | 2,000 | 5.42 |
| `statuses_count` | 2,000 | 5.42 |
| `utc_offset` | 2,000 | 5.42 |

## 5. Duplicate analysis
- Exact full-row duplicates: **367**
- Content duplicates (same dataset/grain/text/author/label/features): **504** (1.36%)
- `record_id` collisions: 0
- Authored rows: 33,544 across **6,970** distinct authors → mean 4.81 rows/author (max 3,416). Authors in >1 dataset: 1757.
- **Implication:** heavy author repetition (IO tweet streams) → any tweet-grain training MUST use group-aware (by-author) splits to avoid leakage.

## 6. Class imbalance
- Labeled rows: **35,755** (32,239 inauthentic / 3,516 authentic) → **90.17% positive**, ratio 9.17:1.
- Majority-class baseline accuracy = **90.17%** → accuracy is misleading; use balanced metrics (F1/AUC/Brier).
- **85.93% of positives are IO** (27,702 state_io tweets). **Excluding IO**, the labeled slice is 4,537 pos / 3,516 neg = **56.34% positive — near-balanced.**

### Balance by domain
| domain | authentic(0) | inauthentic(1) | unknown |
|---|---|---|---|
| coordination | 0 | 27,702 | 0 |
| authenticity | 1,671 | 2,329 | 0 |
| bot | 990 | 1,547 | 0 |
| reference | 0 | 0 | 1,000 |
| ai_text | 855 | 661 | 170 |

### Balance by grain
| grain | authentic(0) | inauthentic(1) | unknown |
|---|---|---|---|
| tweet | 340 | 26,429 | 0 |
| account | 2,039 | 4,931 | 1,000 |
| comment | 282 | 218 | 0 |
| text | 855 | 661 | 170 |

## 7. Datasets / slices to EXCLUDE before training
1. **`activity_botscore` (reference, 1,000 rows, no labels)** — unlabeled; exclude from supervised training (calibration only).
2. **Coordination / IO tweets (27,702 rows, all label=1, tweet grain, no in-domain negatives)** — exclude from any account-authenticity model: wrong grain, drives the 90% imbalance, and cannot train IO-vs-legitimate without legitimate-coordination negatives (the `known-mixed` gap).
3. **AI-text unlabeled rows (~170)** — drop rows with null label.
4. **`real_users` / `fake_users` (source↔label confound + degraded, partly-zeroed metadata)** — use with strong caution or hold out; never expose `source`/origin as a feature.
5. **Username-morphology features** (present in 1,000 rows' `numeric_features_json`) — drop before training (V2 audit shortcut).

## 8. Recommendation — is the corpus ready for V1 training?
**Not ready as a single cross-grain authenticity model; conditionally usable per-grain.**

| candidate model | usable slice | verdict |
|---|---|---|
| One model over the whole corpus | — | ❌ No — mixes account/tweet/comment/text grains and is 90% IO-positive |
| Account-authenticity V1 | ~3,000 labeled account rows (fsm + user dumps) | ⚠️ Marginal — metadata-only, source-confounded, shortcut-laden |
| Coordination/IO | 27.7k IO tweets, **0 negatives** | ❌ No — needs legitimate-coordination negatives |
| AI-text classifier | ~1,516 labeled (855 human / 661 ai) | ✅ Baseline-viable (small, near-balanced) |
| Bot classifier | ~2,537 labeled (990 human / 1,547 bot) | ✅ Baseline-viable |

**Bottom line:** the corpus is a sound, well-governed *standardized substrate*, but **not** ready for a production V1 authenticity model. Train **per-grain**, exclude the slices in §7, use **group-aware (by-author) splits** and **balanced metrics**, and note the encouraging finding that the **non-IO labeled slice is near-balanced**. The highest-value unlocks remain unchanged from prior audits: **engine-derived features** (populate the absent detector/fingerprint signal) and **engine-independent labels + legitimate-coordination negatives**.
