# Omi Corpus Audit — COMPLETE (OMI_CORPUS_AUDIT_V1)

> **Full uncapped scan** of every governance-approved source row, streamed line by line through the unified converters (`ml/corpus/audit_full.py`). Read-only: the corpus, normalized dataset, source data, and production are unmodified; no training.

## Scope
- **Full normalized population (this scan): 1,368,094 rows** — what training can draw on.
- Committed sample artifact `data/merged_corpus.parquet`: **36,925 rows** (capped 1,000/file for git; audited by the companion `audit.py`).
- This report supersedes the capped view for every count below.

## 1. Total training examples: **1,368,094** (full population)

## 2. Label distribution
### 2a. Authenticity (normalized)
| class | count | % |
|---|---|---|
| authentic (0) | 151,170 | 11.05 |
| inauthentic (1) | 1,205,564 | 88.12 |
| unknown (null) | 11,360 | 0.83 |

### 2b. Every semantic label
| label | count | % |
|---|---|---|
| state_io | 1,063,990 | 77.77 |
| human | 146,729 | 10.73 |
| bot | 137,014 | 10.01 |
| unknown | 11,360 | 0.83 |
| authentic | 4,441 | 0.32 |
| fake | 3,559 | 0.26 |
| ai_generated | 1,001 | 0.07 |

### 2c. Class imbalance
- Labeled: **1,356,734** → **88.86% positive** (ratio 7.97:1). Majority baseline accuracy **88.86%** → use F1/AUC/Brier, not accuracy.
- **Severe, and IO-driven**: 88.26% of positives are state-IO tweets. **Excluding IO**: 141,574 pos / 151,170 neg = **48.36% positive** (far healthier).

## 3. Dataset contribution (top 30 of 62)
| dataset | rows | % | domain | grain |
|---|---|---|---|---|
| `TwitterData_Joined` | 279,691 | 20.444 | authenticity | tweet |
| `hashed_2020_12_iran_202012_iran_202012_tweets_b` | 183,650 | 13.424 | coordination | tweet |
| `hashed_2020_12_iran_202012_iran_202012_tweets_a` | 178,110 | 13.019 | coordination | tweet |
| `russia_052020_tweets_csv_hashed_2_b` | 161,717 | 11.821 | coordination | tweet |
| `hashed_2020_12_iran_202012_iran_202012_tweets_c` | 144,677 | 10.575 | coordination | tweet |
| `russia_052020_tweets_csv_hashed_2_a` | 144,586 | 10.568 | coordination | tweet |
| `hashed_2020_12_IRA_202012_IRA_202012_tweets` | 68,914 | 5.037 | coordination | tweet |
| `hashed_2020_12_iran_202012_iran_202012_tweets_d` | 54,134 | 3.957 | coordination | tweet |
| `hashed_2020_12_GRU_202012_GRU_202012_tweets` | 26,684 | 1.95 | coordination | tweet |
| `CNHU_0621_tweets_csv_hashed_2021` | 15,635 | 1.143 | coordination | tweet |
| `CNHU_0621_tweets_csv_hashed_2020` | 15,195 | 1.111 | coordination | tweet |
| `RNA_0621_tweets_csv_hashed_2020` | 14,291 | 1.045 | coordination | tweet |
| `activity_botscore` | 11,190 | 0.818 | reference | account |
| `CNCC_0621_tweets_csv_hashed_2013` | 9,159 | 0.669 | coordination | tweet |
| `CNCC_0621_tweets_csv_hashed_2012` | 8,622 | 0.63 | coordination | tweet |
| `CNCC_0621_tweets_csv_hashed_2017` | 6,399 | 0.468 | coordination | tweet |
| `REA_0621_tweets_csv_hashed_2019` | 5,975 | 0.437 | coordination | tweet |
| `CNCC_0621_tweets_csv_hashed_2014` | 5,687 | 0.416 | coordination | tweet |
| `RNA_0621_tweets_csv_hashed_2019` | 4,609 | 0.337 | coordination | tweet |
| `fake_social_media_global_2.0` | 3,000 | 0.219 | authenticity | account |
| `fake_users` | 2,500 | 0.183 | authenticity | account |
| `real_users` | 2,500 | 0.183 | authenticity | account |
| `iran_092020_tweets_csv_hashed` | 2,450 | 0.179 | coordination | tweet |
| `CNCC_0621_tweets_csv_hashed_2020` | 2,236 | 0.163 | coordination | tweet |
| `hashed_2021_12_CNHU_0621_CNHU_0621_users` | 2,047 | 0.15 | coordination | account |
| `ai_vs_human_text_2026` | 2,000 | 0.146 | ai_text | text |
| `REA_0621_tweets_csv_hashed_2020` | 1,586 | 0.116 | coordination | tweet |
| `CNCC_0621_tweets_csv_hashed_2018` | 1,404 | 0.103 | coordination | tweet |
| `ira_092020_tweets_csv_hashed` | 1,368 | 0.1 | coordination | tweet |
| `russia_052020_users_csv_hashed` | 1,153 | 0.084 | coordination | account |

_Full per-dataset table (all 62): `audit_per_dataset.csv`._

By domain: coordination 1,063,990 (77.8%), authenticity 287,691 (21.0%), reference 11,190 (0.8%), ai_text 2,686 (0.2%), bot 2,537 (0.2%)

## 4. Feature completeness (% of all rows populated)
| field | % populated |
|---|---|
| `record_id` | 100.0 |
| `dataset` | 100.0 |
| `source_path` | 100.0 |
| `domain` | 100.0 |
| `grain` | 100.0 |
| `text` | 98.21 |
| `author_id` | 98.86 |
| `created_at` | 98.5 |
| `lang` | 67.59 |
| `authenticity_label` | 99.17 |
| `label_raw` | 99.18 |
| `label_source` | 100.0 |
| `numeric_features_json` | 79.21 |
| `governance_status` | 100.0 |
| `schema_version` | 100.0 |

**Sparse / mostly-empty fields:** `lang` (67.59%), `numeric_features_json` (79.21%).
- `text` is null for account/comment grains by source design; `lang` only the IO/AI sets carry it; `created_at` absent for profile sets.
- **Engine detector/fingerprint features are 0% present** — no source carries them; this is the single largest feature gap for an authenticity model.

### Numeric feature coverage (top 18 by frequency)
| feature | rows | % | min | max | mean | negatives | nonfinite |
|---|---|---|---|---|---|---|---|
| `follower_count` | 1,063,989 | 77.77 | 0.0 | 2883076.0 | 75235.7793 | 0 | 0 |
| `following_count` | 1,063,989 | 77.77 | 0.0 | 99855.0 | 1724.7654 | 0 | 0 |
| `activity` | 11,190 | 0.82 | 0.0003 | 851.735 | 15.9193 | 0 | 0 |
| `age` | 11,190 | 0.82 | 3077.0 | 4370.0 | 3326.4066 | 0 | 0 |
| `bot_score_english` | 11,190 | 0.82 | 0.0021 | 0.997 | 0.1835 | 0 | 0 |
| `count` | 11,190 | 0.82 | 1.0 | 2700672.0 | 53572.9749 | 0 | 0 |
| `user_id` | 11,190 | 0.82 | 953.0 | 4928654909.0 | 2051304803.4784 | 0 | 0 |
| `verified` | 7,663 | 0.56 | 0.0 | 1.0 | 0.172 | 0 | 0 |
| `default_profile` | 5,000 | 0.37 | 0.0 | 7.0945 | 0.4929 | 0 | 0 |
| `default_profile_image` | 5,000 | 0.37 | 0.0 | 2.2445 | 0.0019 | 0 | 0 |
| `favourites_count` | 5,000 | 0.37 | 0.0 | 60892.1733 | 183.1129 | 0 | 0 |
| `followers_count` | 5,000 | 0.37 | -0.0 | 796096.3842 | 321.9153 | 0 | 0 |
| `friends_count` | 5,000 | 0.37 | 0.0 | 16878.4745 | 315.3582 | 0 | 0 |
| `geo_enabled` | 5,000 | 0.37 | 0.0 | 6.4497 | 0.1792 | 0 | 0 |
| `listed_count` | 5,000 | 0.37 | 0.0 | 915.6267 | 2.1248 | 0 | 0 |
| `profile_background_tile` | 5,000 | 0.37 | 0.0 | 5.8691 | 0.1284 | 0 | 0 |
| `profile_use_background_image` | 5,000 | 0.37 | 0.0 | 6.2371 | 0.785 | 0 | 0 |
| `protected` | 5,000 | 0.37 | 0.0 | 0.0 | 0.0 | 0 | 0 |

## 5. Duplicate analysis
- **Exact duplicates** (identical content): **33,690** (2.46%).
- **Near-duplicate text** (normalized: lowercased, URLs/@mentions/`RT` stripped, whitespace collapsed): **230,140** of 1,304,900 text rows (**17.64%**) — retweet/boilerplate echoes, overwhelmingly in the IO streams.
- **Duplicate accounts**: 1,352,448 authored rows across **10,239** distinct accounts → mean **132.09 rows/account** (max 302,649). Accounts appearing across >1 source file: 600,535 — mostly **intra-campaign IO file splits** (each campaign ships as several yearly/part files sharing the same accounts), not cross-campaign identity collisions.
- **Implication:** the corpus is row-rich but **account-poor**; tweet-grain training MUST split by account (group-aware) or effective sample size collapses to the ~10,239 accounts and near-dup echoes inflate metrics.

## 6. Data quality analysis
- **Missing values**: text missing in 693/1,343,234 text-grain rows; author missing in 12,960/1,365,408 author-grain rows.
- **Invalid values**: labels outside {0,1,null}: 0; verified/boolean fields out of {0,1}: 2,113; negative count-like features: see the numeric table above.
- **Dataset with quality concerns — `real_users` / `fake_users`**: boolean profile fields are noised/continuous (e.g. `default_profile` max 7.0945, `geo_enabled` max 6.4497 — should be 0/1) and counts are non-integer / partly zeroed. Treat their metadata as **low-trust**, and remember their labels come from file origin (confound).
- **Parsing issues / unparseable timestamps**: 1/1,347,635 present `created_at` values (0.0%) failed standard date parsing.
- **Governance breakdown (all discovered files):** archive=7, quarantine=1, reference=1, train=3, validation=60.

### Files with quality concerns / not normalized
| file | format | issue |
|---|---|---|
| `datasets/2020-09/iran_092020_tweets_csv_hashed.csv` | csv | 1 source rows not emitted (skipped/blank) |
| `datasets/2020-09/iran_092020_users_csv_hashed.csv` | csv | 1 source rows not emitted (skipped/blank) |
| `datasets/Changyu Culture/2021_12_CNCC_0621_CNCC_0621_users.csv` | csv | no converter (family=unknown); not normalized |
| `datasets/Datasets/Fake Social Media Account Detection Dataset/bot_detection_data.csv` | csv | no converter (family=bot_detection); not normalized |
| `datasets/Datasets/Fake Social Media Account Detection Dataset/fake_social_media.csv` | csv | governance=archive (excluded from training) |
| `datasets/Datasets/Fake Social Media Account Detection Dataset/fake_social_media_global_2.0_with_missing.xlsx` | xlsx | no converter (family=xlsx); not normalized |
| `datasets/Datasets/TwitterData_FE.csv` | csv | governance=archive (excluded from training) |
| `datasets/Datasets/Twitter_Data.csv` | csv | governance=archive (excluded from training) |
| `datasets/Datasets/Twitter_Users.csv` | csv | no converter (family=generic_account); not normalized |
| `datasets/Datasets/location_data.csv` | csv | no converter (family=generic_account); not normalized |
| `datasets/ai vs human text/ai_vs_human_text.csv` | csv | no converter (family=unknown); not normalized |

## 7. Training-readiness assessment
**Strengths**
- Large, governed, schema-unified (1,368,094 rows); poison/archive excluded by manifest.
- Strong, platform-attributed **coordination** ground truth (state-IO) at scale.
- **Excluding IO, the labeled authenticity/bot/text slices are near-balanced** (141,574/151,170).
- Clean lineage: every row carries `dataset`/`label_source`/`grain` provenance.

**Weaknesses**
- **No engine features** (fingerprint/detector blocks 0% populated) — an account-authenticity model would train on bare metadata.
- **Severe label imbalance** (88.86% positive) and **grain mixing** (account/tweet/comment/text) — one model cannot span them.
- **Account-poor**: only ~10,239 distinct accounts behind 1,368,094 rows; **17.64% near-duplicate text** → leakage risk without by-account splitting.
- **Confounds**: real/fake_users labeled by file origin (+ degraded metadata); IO is 100% positive with **no in-domain negatives**.

**Biggest-impact improvements (ranked)**
1. **Run the engine over the accounts** to populate fingerprint/detector features — turns bare metadata into Omi's real signal (largest lift).
2. **Add legitimate-coordination negatives** (`known-mixed`) so the IO data becomes a trainable coordination set rather than an all-positive pile.
3. **Adopt by-account group splits + class rebalancing/weighting** to kill the near-dup leakage and the imbalance distortion.
4. **Resolve the real/fake_users origin confound** (mix sources per class or drop).
5. **Per-grain framing** (separate authenticity / coordination / ai-text / bot models) rather than one corpus-wide model.

## 8. Final recommendation

| target | verdict |
|---|---|
| Single corpus-wide V1 model | **❌ Not ready** (grain mixing + 90% IO imbalance) |
| Account-authenticity V1 (the headline OmiBehavioralNet) | **❌ Not ready** — needs engine features + confound fixes |
| AI-text classifier (per-grain) | **🟡 Ready with minor improvements** (dedup + balance; ~1.5k labeled) |
| Bot classifier (per-grain) | **🟡 Ready with minor improvements** (~2.5k labeled) |
| Coordination/IO model | **❌ Not ready** — no legitimate-coordination negatives |

**Overall: NOT READY for V1 training as a single authenticity corpus.** It is an excellent standardized *substrate* and is *ready-with-minor-improvements* for narrow per-grain text/bot baselines, but the headline account-authenticity model is blocked on engine features and the confound/imbalance/account-scarcity issues above. Address improvements #1–#3 first.

_Artifacts: this report, `audit_stats.json` (machine-readable), `audit_per_dataset.csv` (per-dataset supporting stats)._
