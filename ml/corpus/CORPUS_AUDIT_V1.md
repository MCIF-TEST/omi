# Omi Corpus Audit — COMPREHENSIVE (OMI_CORPUS_AUDIT_V1)

> **Full uncapped streaming scan** of every governance-approved source row, line by line, through the unified converters (`ml/corpus/audit_full.py`). **Strictly read-only** — no source dataset, normalized corpus, or production code was modified; no training. Outputs: this report, `audit_stats.json`, `audit_per_dataset.csv`.

## Scope
- **Total records scanned (full population): 1,368,094** — every approved source row.
- Committed sample `data/merged_corpus.parquet`: 36,925 rows (capped 1,000/file for git; not modified by this audit).
- Datasets scanned: 62; files with issues / excluded: 11.

## 1. Total records scanned: **1,368,094**

## 2. Per-dataset record counts (top 25; full list in `audit_per_dataset.csv`)
| dataset | rows | % | domain | grain | distinct accts |
|---|---|---|---|---|---|
| `TwitterData_Joined` | 279,691 | 20.444 | authenticity | tweet | 92 |
| `hashed_2020_12_iran_202012_iran_202012_tweets_b` | 183,650 | 13.424 | coordination | tweet | 181 |
| `hashed_2020_12_iran_202012_iran_202012_tweets_a` | 178,110 | 13.019 | coordination | tweet | 204 |
| `russia_052020_tweets_csv_hashed_2_b` | 161,717 | 11.821 | coordination | tweet | 240 |
| `hashed_2020_12_iran_202012_iran_202012_tweets_c` | 144,677 | 10.575 | coordination | tweet | 187 |
| `russia_052020_tweets_csv_hashed_2_a` | 144,586 | 10.568 | coordination | tweet | 240 |
| `hashed_2020_12_IRA_202012_IRA_202012_tweets` | 68,914 | 5.037 | coordination | tweet | 24 |
| `hashed_2020_12_iran_202012_iran_202012_tweets_d` | 54,134 | 3.957 | coordination | tweet | 23 |
| `hashed_2020_12_GRU_202012_GRU_202012_tweets` | 26,684 | 1.95 | coordination | tweet | 51 |
| `CNHU_0621_tweets_csv_hashed_2021` | 15,635 | 1.143 | coordination | tweet | 1,247 |
| `CNHU_0621_tweets_csv_hashed_2020` | 15,195 | 1.111 | coordination | tweet | 1,769 |
| `RNA_0621_tweets_csv_hashed_2020` | 14,291 | 1.045 | coordination | tweet | 30 |
| `activity_botscore` | 11,190 | 0.818 | reference | account | 0 |
| `CNCC_0621_tweets_csv_hashed_2013` | 9,159 | 0.669 | coordination | tweet | 1 |
| `CNCC_0621_tweets_csv_hashed_2012` | 8,622 | 0.63 | coordination | tweet | 2 |
| `CNCC_0621_tweets_csv_hashed_2017` | 6,399 | 0.468 | coordination | tweet | 2 |
| `REA_0621_tweets_csv_hashed_2019` | 5,975 | 0.437 | coordination | tweet | 4 |
| `CNCC_0621_tweets_csv_hashed_2014` | 5,687 | 0.416 | coordination | tweet | 1 |
| `RNA_0621_tweets_csv_hashed_2019` | 4,609 | 0.337 | coordination | tweet | 24 |
| `fake_social_media_global_2.0` | 3,000 | 0.219 | authenticity | account | 2,579 |
| `fake_users` | 2,500 | 0.183 | authenticity | account | 939 |
| `real_users` | 2,500 | 0.183 | authenticity | account | 992 |
| `iran_092020_tweets_csv_hashed` | 2,450 | 0.179 | coordination | tweet | 104 |
| `CNCC_0621_tweets_csv_hashed_2020` | 2,236 | 0.163 | coordination | tweet | 11 |
| `hashed_2021_12_CNHU_0621_CNHU_0621_users` | 2,047 | 0.15 | coordination | account | 2,017 |

## 3. Label distribution (complete datasets)
| authenticity | count | % |
|---|---|---|
| authentic (0) | 151,170 | 11.05 |
| inauthentic (1) | 1,205,564 | 88.12 |
| unknown (null) | 11,360 | 0.83 |

| semantic label | count | % |
|---|---|---|
| state_io | 1,063,990 | 77.77 |
| human | 146,729 | 10.73 |
| bot | 137,014 | 10.01 |
| unknown | 11,360 | 0.83 |
| authentic | 4,441 | 0.32 |
| fake | 3,559 | 0.26 |
| ai_generated | 1,001 | 0.07 |

## 4. Feature completeness (% of rows populated)
| field | % |
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

**Sparse fields:** `lang` (67.59%), `numeric_features_json` (79.21%). **Engine fingerprint/detector features: 0% present** (largest gap).

Numeric coverage (top 12): min / median / mean / p99 / max / negatives / nonfinite
| feature | rows | % | min | median | mean | p99 | max | neg | nonfin |
|---|---|---|---|---|---|---|---|---|---|
| `follower_count` | 1,063,989 | 77.77 | 0.0 | 5292.0 | 75235.7793 | 834415.0 | 2883076.0 | 0 | 0 |
| `following_count` | 1,063,989 | 77.77 | 0.0 | 126.0 | 1724.7654 | 26749.0 | 99855.0 | 0 | 0 |
| `activity` | 11,190 | 0.82 | 0.0003 | 4.381 | 15.9193 | 220.1997 | 851.735 | 0 | 0 |
| `age` | 11,190 | 0.82 | 3077.0 | 3199.0 | 3326.4066 | 4002.0 | 4370.0 | 0 | 0 |
| `bot_score_english` | 11,190 | 0.82 | 0.0021 | 0.0731 | 0.1835 | 0.9744 | 0.997 | 0 | 0 |
| `count` | 11,190 | 0.82 | 1.0 | 14466.0 | 53572.9749 | 726994.89 | 2700672.0 | 0 | 0 |
| `user_id` | 11,190 | 0.82 | 953.0 | 2198556176.0 | 2051304803.4784 | 4867621145.63 | 4928654909.0 | 0 | 0 |
| `verified` | 7,663 | 0.56 | 0.0 | 0.0 | 0.172 | 1.0 | 1.0 | 0 | 0 |
| `default_profile` | 5,000 | 0.37 | 0.0 | 0.0 | 0.4929 | 3.9701 | 7.0945 | 0 | 0 |
| `default_profile_image` | 5,000 | 0.37 | 0.0 | 0.0 | 0.0019 | 0.0 | 2.2445 | 0 | 0 |
| `favourites_count` | 5,000 | 0.37 | 0.0 | 0.0 | 183.1129 | 3743.9591 | 60892.1733 | 0 | 0 |
| `followers_count` | 5,000 | 0.37 | -0.0 | 0.0 | 321.9153 | 2445.4932 | 796096.3842 | 0 | 0 |

## 5. Exact duplicate detection
- Exact duplicates (identical content): **36,721** (2.68%).
- Of which **cross-dataset: 4,683**, **cross-domain: 0**.

## 6. Near-duplicate detection
Method: normalize text (lowercase, strip URLs/@mentions/`RT`, collapse whitespace), hash, count repeats.
- Near-duplicate texts: **230,140** of 1,304,900 text rows (**17.64%**); cross-dataset near-dups: **90,179** — retweet/boilerplate echoes, mostly IO.

## 7. Duplicate account analysis
- 1,352,448 authored rows across **10,239** distinct accounts → mean **132.09 rows/account** (max 302,649).
- **Row-rich, account-poor** → tweet-grain training MUST use by-account (group) splits or effective sample size collapses and near-dup echoes inflate metrics.

## 8. Missing & invalid values
- Missing text (text grains): 693/1,343,234; missing author (author grains): 12,960/1,365,408.
- Invalid labels (outside 0/1/null): 0; boolean fields out of {0,1}: **4,871** (real/fake_users noised booleans).
- Unparseable timestamps: 1/1,347,635 (0.0%).

## 9. Schema inconsistencies
Source families whose files do not share one schema:
| family | distinct schemas | example diff |
|---|---|---|
| unknown | 2 | +['date', 'id', 'label', 'model', 'prompt', 'text'] -['accountCreationDate', 'accountLanguage', 'followerCount', 'followingCount', 'userDisplayName', 'userProfileDescription', 'userProfileUrl', 'userReportedLocation'] |
| fsm_profile | 2 | +['digit_ratio', 'digits_count', 'repeat_char_count', 'special_char_count', 'username', 'username_length'] -[] |
| twitterdata | 3 | +['Followers', 'Following', 'Link', 'Location', 'Real_Location', 'Verified'] -[] |
| generic_account | 2 | +['Latitude', 'Longitude', 'Twitter Account', 'label'] -['Followers', 'Following', 'Link', 'Real_Location', 'Twitter_User_Name', 'Verified'] |

**Casing/format variants** (same columns, different naming — e.g. camelCase vs snake_case IO exports):
- variants: `datasets/Changyu Culture/2021_12_CNCC_0621_CNCC_0621_users.csv`, `datasets/2020-05/russia_052020_users_csv_hashed.csv`

## 10. Parsing failures / not normalized
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

## 11. Dataset-specific quality issues
- **`real_users` / `fake_users`**: boolean profile fields are noised/continuous (`default_profile` max 7.0945, `geo_enabled` max 6.4497, `protected` max 0.0 — should be 0/1) and counts are non-integer/partly-zeroed → **low-trust metadata**; labels come from file origin (confound).
- **IO campaigns** ship as many per-year/part files sharing accounts → heavy intra-campaign duplication; treat a campaign as one unit, not per-file.
- **`TwitterData_Joined`**: ~20% of all rows but only ~96 accounts (tweet grain) — dominates the non-IO balance; strong per-account concentration.
- **camelCase IO users variant** + **`.xlsx`** + **quarantine/archive** sets are not normalized (see §9/§10).

## 12. Class imbalance analysis
- Labeled **1,356,734**, **88.86% positive** (ratio 7.97:1); majority baseline acc **88.86%** → use F1/AUC/Brier.
- **88.26% of positives are IO**. Excluding IO: 141,574 pos / 151,170 neg = **48.36% positive** (but that balance is concentrated in TwitterData_Joined's ~96 accounts).
By domain: coordination 1,063,990, authenticity 287,691, bot 2,537, reference 11,190, ai_text 2,686.

## 13. Potential cross-dataset data leakage
- Exact content shared **across datasets**: 4,683 (across **domains**: 0).
- Near-duplicate text shared across datasets: 90,179.
- Accounts appearing in >1 source file: 600,535 (mostly intra-campaign IO splits); in **>1 domain: 0** (the real leakage signal — same account labeled in different domains).
- **Mitigation:** dedupe globally before splitting; split by account AND keep whole campaigns/domains on one side; never mix the same account across train/eval.

Top dataset pairs sharing exact content:
| dataset A | dataset B | shared |
|---|---|---|
| `russia_052020_tweets_csv_hashed_2_a` | `russia_052020_tweets_csv_hashed_2_b` | 3,670 |
| `hashed_2020_12_iran_202012_iran_202012_tweets_b` | `hashed_2020_12_iran_202012_iran_202012_tweets_c` | 329 |
| `hashed_2020_12_iran_202012_iran_202012_tweets_b` | `hashed_2020_12_iran_202012_iran_202012_tweets_d` | 186 |
| `hashed_2020_12_iran_202012_iran_202012_tweets_c` | `hashed_2020_12_iran_202012_iran_202012_tweets_d` | 157 |
| `hashed_2020_12_iran_202012_iran_202012_tweets_a` | `hashed_2020_12_iran_202012_iran_202012_tweets_b` | 133 |
| `hashed_2020_12_iran_202012_iran_202012_tweets_a` | `hashed_2020_12_iran_202012_iran_202012_tweets_c` | 81 |
| `CNCC_0621_tweets_csv_hashed_2012` | `CNCC_0621_tweets_csv_hashed_2013` | 80 |
| `CNCC_0621_tweets_csv_hashed_2015` | `CNCC_0621_tweets_csv_hashed_2017` | 13 |

## 14. Outlier detection (IQR, on per-feature reservoir samples)
| feature | median | p99 | max | IQR-outlier % |
|---|---|---|---|---|
| `follower_count` | 5292.0 | 834415.0 | 2883076.0 | 2.66% |
| `following_count` | 126.0 | 26749.0 | 99855.0 | 8.46% |
| `activity` | 4.381 | 220.1997 | 851.735 | 5.87% |
| `age` | 3199.0 | 4002.0 | 4370.0 | 0.11% |
| `bot_score_english` | 0.0731 | 0.9744 | 0.997 | 4.08% |
| `count` | 14466.0 | 726994.89 | 2700672.0 | 5.93% |
| `user_id` | 2198556176.0 | 4867621145.63 | 4928654909.0 | 0.0% |
| `verified` | 0.0 | 1.0 | 1.0 | 17.2% |
| `default_profile` | 0.0 | 3.9701 | 7.0945 | 8.82% |
| `default_profile_image` | 0.0 | 0.0 | 2.2445 | 0.14% |
| `favourites_count` | 0.0 | 3743.9591 | 60892.1733 | 22.18% |
| `followers_count` | 0.0 | 2445.4932 | 796096.3842 | 11.38% |
| `friends_count` | 0.0 | 2918.838 | 16878.4745 | 4.4% |
| `geo_enabled` | 0.0 | 3.1345 | 6.4497 | 11.32% |

Extreme right-tail skew (huge max vs median, e.g. follower/count features) is expected for social data → apply log1p before training.

## 15. Visualizations (ASCII; matplotlib unavailable)

`follower_count` distribution (reservoir n=50,000):
```text
  [        0.00,    83441.50)   33,401 |########################################
  [    83441.50,   166883.00)   15,267 |##################
  [   166883.00,   250324.50)        0 |
  [   250324.50,   333766.00)        0 |
  [   333766.00,   417207.50)        0 |
  [   417207.50,   500649.00)        0 |
  [   500649.00,   584090.50)        0 |
  [   584090.50,   667532.00)        0 |
  [   667532.00,   750973.50)        0 |
  [   750973.50,   834415.00)    1,332 |#
```

`following_count` distribution (reservoir n=50,000):
```text
  [        0.00,     7501.00)   47,709 |########################################
  [     7501.00,    15002.00)    1,147 |
  [    15002.00,    22503.00)      628 |
  [    22503.00,    30004.00)       19 |
  [    30004.00,    37505.00)      259 |
  [    37505.00,    45006.00)        0 |
  [    45006.00,    52507.00)        0 |
  [    52507.00,    60008.00)        0 |
  [    60008.00,    67509.00)        0 |
  [    67509.00,    75010.00)      238 |
```

`activity` distribution (reservoir n=11,190):
```text
  [        0.00,       85.17)   10,856 |########################################
  [       85.17,      170.35)      185 |
  [      170.35,      255.52)       56 |
  [      255.52,      340.69)       38 |
  [      340.69,      425.87)       36 |
  [      425.87,      511.04)       11 |
  [      511.04,      596.21)        4 |
  [      596.21,      681.39)        1 |
  [      681.39,      766.56)        0 |
  [      766.56,      851.74)        3 |
```

`bot_score_english` distribution (reservoir n=11,190):
```text
  [        0.00,        0.10)    6,199 |########################################
  [        0.10,        0.20)    1,851 |###########
  [        0.20,        0.30)      936 |######
  [        0.30,        0.40)      462 |##
  [        0.40,        0.50)      364 |##
  [        0.50,        0.60)      355 |##
  [        0.60,        0.70)      238 |#
  [        0.70,        0.80)      253 |#
  [        0.80,        0.90)      193 |#
  [        0.90,        1.00)      339 |##
```

## 16. Recommendations for preprocessing before training
1. **Filter by grain/domain first** — train separate models (authenticity / coordination / ai-text / bot); never one model across grains.
2. **Global dedup** — drop the 33k+ exact and 230k+ near-duplicate texts before splitting (they inflate metrics and leak across splits).
3. **By-account group splits** — partition on `author_id` (and keep whole campaigns/domains on one side) so no account spans train/eval.
4. **Rebalance** — the labeled set is 89% positive; use class weights / downsample IO / report F1·AUC·Brier, not accuracy.
5. **log1p-transform skewed counts** (follower/following/status/favourite/count) and **clip outliers** to robust bounds (see §14).
6. **Normalize the noised real/fake_users booleans** to {0,1} (or drop those fields); resolve the source↔label origin confound (mix sources per class or hold out).
7. **Drop username-morphology features** (V2 shortcut) and **unlabeled rows** (reference + ~unjoined) from supervised training.
8. **Populate engine features** (fingerprint/detector) — the highest-value step; without them an account model trains on bare metadata.
9. **Add legitimate-coordination negatives** so the IO data becomes trainable rather than all-positive.

## 17. Training-readiness assessment
**Strengths:** large, governed, schema-unified; strong state-IO coordination ground truth; clean per-row provenance; non-IO labels near-balanced.
**Weaknesses:** no engine features; 89% positive + grain mixing; only ~10,239 distinct accounts behind 1,368,094 rows with 17.64% near-dup text; real/fake origin confound + noised booleans; IO has no in-domain negatives.

| target | verdict |
|---|---|
| Single corpus-wide model | **❌ Not ready** (grain mixing + IO imbalance) |
| Account-authenticity V1 (headline) | **❌ Not ready** — needs engine features + confound/imbalance/dedup fixes |
| AI-text classifier (per-grain) | **🟡 Ready with preprocessing** (dedup+balance) |
| Bot classifier (per-grain) | **🟡 Ready with preprocessing** |
| Coordination/IO model | **❌ Not ready** — no legitimate-coordination negatives |

**Overall: NOT READY for full-corpus model training.** It is an excellent standardized *substrate* and is *ready-with-preprocessing* for narrow per-grain ai-text/bot baselines once §16 steps 1–5 are applied. The headline account-authenticity model is blocked on engine features (§16.8) and the confound/imbalance/account-scarcity issues above. **Address §16 #1–#3 and #8 first.**

_Artifacts: this report · `audit_stats.json` · `audit_per_dataset.csv`._
