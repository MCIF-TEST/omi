# Data Quality Report (OMI_DATASET_DISCOVERY_AND_NORMALIZATION_V1)

Files: **72** (72 parseable, 0 unparseable). Approx total source rows: **2,901,743**.

## Formats
| format | files |
|---|---|
| csv | 68 |
| json | 1 |
| tsv | 2 |
| xlsx | 1 |

## Governance breakdown
| status | files |
|---|---|
| archive | 7 |
| quarantine | 1 |
| reference | 1 |
| train | 3 |
| validation | 60 |

## Missing values (top offenders, sampled)
| file | miss% | top columns |
|---|---|---|
| `datasets/Datasets/IRA/North Africa/RNA_0621_tweets_csv_hashed_2012.csv` | 31.11 | user_reported_location, user_profile_description, user_profile_url, in_reply_to_userid, in_reply_to_tweetid |
| `datasets/Datasets/IRA/North Africa/RNA_0621_tweets_csv_hashed_2013.csv` | 30.19 | user_reported_location, user_profile_description, user_profile_url, quoted_tweet_tweetid, retweet_userid |
| `datasets/Datasets/Xinjiang/hashed_2021_12_CNHU_0621_CNHU_0621_users.csv` | 29.86 | user_profile_url, user_reported_location, user_profile_description |
| `datasets/Changyu Culture/hashed_2021_12_CNCC_0621_CNCC_0621_users.csv` | 28.66 | user_profile_url, user_reported_location, user_profile_description |
| `datasets/Datasets/IRA/North Africa/RNA_0621_tweets_csv_hashed_2014.csv` | 27.41 | user_reported_location, user_profile_description, user_profile_url, quoted_tweet_tweetid, retweet_userid |
| `datasets/Datasets/IRA/North Africa/RNA_0621_tweets_csv_hashed_2015.csv` | 26.67 | user_reported_location, user_profile_description, user_profile_url, in_reply_to_userid, in_reply_to_tweetid |
| `datasets/East Africa/REA_0621_tweets_csv_hashed_2012.csv` | 26.67 | user_profile_description, user_profile_url, tweet_language, quoted_tweet_tweetid, retweet_userid |
| `datasets/Datasets/Xinjiang/CNHU_0621_tweets_csv_hashed_2019.csv` | 26.6 | user_reported_location, user_profile_url, in_reply_to_userid, in_reply_to_tweetid, quoted_tweet_tweetid |
| `datasets/Datasets/Xinjiang/CNHU_0621_tweets_csv_hashed_2020.csv` | 26.54 | user_reported_location, user_profile_url, retweet_userid, retweet_tweetid, in_reply_to_userid |
| `datasets/East Africa/REA_0621_tweets_csv_hashed_2013.csv` | 25.83 | user_profile_description, user_profile_url, in_reply_to_tweetid, quoted_tweet_tweetid, retweet_userid |

## Duplicate rows (top offenders, sampled)
| file | dup% |
|---|---|
| _none > 5%_ | |

## Unparseable / not normalized (req 9)
| file | format | reason |
|---|---|---|
| `datasets/Changyu Culture/2021_12_CNCC_0621_CNCC_0621_users.csv` | csv | no converter (family=unknown); not normalized |
| `datasets/Datasets/Fake Social Media Account Detection Dataset/bot_detection_data.csv` | csv | no converter (family=bot_detection); not normalized |
| `datasets/Datasets/Fake Social Media Account Detection Dataset/fake_social_media_global_2.0_with_missing.xlsx` | xlsx | no converter (family=xlsx); not normalized |
| `datasets/Datasets/Twitter_Users.csv` | csv | no converter (family=generic_account); not normalized |
| `datasets/Datasets/location_data.csv` | csv | no converter (family=generic_account); not normalized |
| `datasets/ai vs human text/ai_vs_human_text.csv` | csv | no converter (family=unknown); not normalized |

## Merged corpus
- Rows: **36,925** from 63 files (cap 1000/file; 9 files skipped).
- By grain: {'tweet': 26769, 'account': 7970, 'text': 1686, 'comment': 500}
- By domain: {'coordination': 27702, 'authenticity': 4000, 'bot': 2537, 'ai_text': 1686, 'reference': 1000}
- Labeled: 35,755 (balance 0/1 = {'1': 32239, '0': 3516}); unlabeled: 1,170

## Leakage & integrity warnings (req D)
1. **Cross-grain merge is intentional but must be filtered**: the corpus mixes account/tweet/comment/text rows; train per-grain by filtering `grain`/`domain` — do NOT train one model across grains.
2. **Username-morphology shortcut present** in `fsm_profile` numeric features (digit_ratio, digits_count, repeat_char_count, special_char_count, username, username_length, username_randomness) — V2 audit shortcut. Preserved here for fidelity but **must be dropped before training** (the NN dataset builder already does).
3. **Source↔label confound**: `real_users`(0)/`fake_users`(1) are labeled by file origin; IO sets are labeled implicitly (=1). Origin differences are confounded with the label.
4. **No engine-output circularity**: no dataset carries engine detector/score outputs, so none leak into features.
5. **Caps applied**: large files are capped at 1000 rows in the committed corpus (sampling) — see merged-file table below; full normalization is reproducible by raising `--max-rows`.
6. **Duplicates**: per-file duplicate rates are sampled above; the per-grain NN builders dedup on the feature vector before splitting.
7. **Merged class imbalance**: labeled balance 0/1 = {'1': 32239, '0': 3516} (~90% inauthentic), driven by the many IO tweet files (all label=1, each capped). Per-domain balance differs — rebalance or filter by `domain` before training.

### Merged files (rows in / source rows / capped)
| file | family | rows in corpus | source rows | capped |
|---|---|---|---|---|
| `datasets/2020-05/russia_052020_tweets_csv_hashed_2_a.csv` | io_tweets | 1000 | 199953 | yes |
| `datasets/2020-05/russia_052020_tweets_csv_hashed_2_b.csv` | io_tweets | 1000 | 217352 | yes |
| `datasets/2020-05/russia_052020_users_csv_hashed.csv` | io_users | 1000 | 1153 | yes |
| `datasets/2020-09/iran_092020_tweets_csv_hashed.csv` | io_tweets | 1000 | 2451 | yes |
| `datasets/2020-09/iran_092020_users_csv_hashed.csv` | io_users | 104 | 105 | no |
| `datasets/2021-02/hashed_2020_12_iran_202012_iran_202012_tweets_a.csv` | io_tweets | 1000 | 499988 | yes |
| `datasets/2021-02/hashed_2020_12_iran_202012_iran_202012_tweets_b.csv` | io_tweets | 1000 | 350001 | yes |
| `datasets/2021-02/hashed_2020_12_iran_202012_iran_202012_tweets_c.csv` | io_tweets | 1000 | 349998 | yes |
| `datasets/2021-02/hashed_2020_12_iran_202012_iran_202012_tweets_d.csv` | io_tweets | 1000 | 54134 | yes |
| `datasets/2021-02/hashed_2020_12_iran_202012_iran_202012_users.csv` | io_users | 238 | 238 | no |
| `datasets/Changyu Culture/CNCC_0621_tweets_csv_hashed_2012.csv` | io_tweets | 1000 | 8622 | yes |
| `datasets/Changyu Culture/CNCC_0621_tweets_csv_hashed_2013.csv` | io_tweets | 1000 | 9159 | yes |
| `datasets/Changyu Culture/CNCC_0621_tweets_csv_hashed_2014.csv` | io_tweets | 1000 | 5687 | yes |
| `datasets/Changyu Culture/CNCC_0621_tweets_csv_hashed_2015.csv` | io_tweets | 701 | 701 | no |
| `datasets/Changyu Culture/CNCC_0621_tweets_csv_hashed_2016.csv` | io_tweets | 954 | 954 | no |
| `datasets/Changyu Culture/CNCC_0621_tweets_csv_hashed_2017.csv` | io_tweets | 1000 | 6399 | yes |
| `datasets/Changyu Culture/CNCC_0621_tweets_csv_hashed_2018.csv` | io_tweets | 1000 | 1404 | yes |
| `datasets/Changyu Culture/CNCC_0621_tweets_csv_hashed_2019.csv` | io_tweets | 204 | 204 | no |
| `datasets/Changyu Culture/CNCC_0621_tweets_csv_hashed_2020.csv` | io_tweets | 1000 | 2236 | yes |
| `datasets/Changyu Culture/CNCC_0621_tweets_csv_hashed_2021.csv` | io_tweets | 558 | 558 | no |
| `datasets/Changyu Culture/hashed_2021_12_CNCC_0621_CNCC_0621_users.csv` | io_users | 112 | 112 | no |
| `datasets/Datasets/Fake Social Media Account Detection Dataset/fake_social_media_global_2.0.csv` | fsm_profile | 1000 | 3000 | yes |
| `datasets/Datasets/Fake Social Media Account Detection Dataset/fake_users.csv` | userdump | 1000 | 2500 | yes |
| `datasets/Datasets/Fake Social Media Account Detection Dataset/real_users.csv` | userdump | 1000 | 2500 | yes |
| `datasets/Datasets/Fake Social Media Account Detection Dataset/reddit_dead_internet_analysis_2026.csv` | reddit_comment | 500 | 500 | no |
| `datasets/Datasets/GRU/hashed_2020_12_GRU_202012_GRU_202012_tweets.csv` | io_tweets | 1000 | 26684 | yes |
| `datasets/Datasets/GRU/hashed_2020_12_GRU_202012_GRU_202012_users.csv` | io_users | 70 | 70 | no |
| `datasets/Datasets/IRA/2020-09/ira_092020_tweets_csv_hashed.csv` | io_tweets | 1000 | 1368 | yes |
| `datasets/Datasets/IRA/2020-09/ira_092020_users_csv_hashed.csv` | io_users | 5 | 5 | no |
| `datasets/Datasets/IRA/2021-02/hashed_2020_12_IRA_202012_IRA_202012_tweets.csv` | io_tweets | 1000 | 68914 | yes |
| `datasets/Datasets/IRA/2021-02/hashed_2020_12_IRA_202012_IRA_202012_users.csv` | io_users | 31 | 31 | no |
| `datasets/Datasets/IRA/North Africa/RNA_0621_tweets_csv_hashed_2012.csv` | io_tweets | 3 | 3 | no |
| `datasets/Datasets/IRA/North Africa/RNA_0621_tweets_csv_hashed_2013.csv` | io_tweets | 18 | 18 | no |
| `datasets/Datasets/IRA/North Africa/RNA_0621_tweets_csv_hashed_2014.csv` | io_tweets | 18 | 18 | no |
| `datasets/Datasets/IRA/North Africa/RNA_0621_tweets_csv_hashed_2015.csv` | io_tweets | 1 | 1 | no |
| `datasets/Datasets/IRA/North Africa/RNA_0621_tweets_csv_hashed_2016.csv` | io_tweets | 0 | 0 | no |
| `datasets/Datasets/IRA/North Africa/RNA_0621_tweets_csv_hashed_2017.csv` | io_tweets | 5 | 5 | no |
| `datasets/Datasets/IRA/North Africa/RNA_0621_tweets_csv_hashed_2018.csv` | io_tweets | 13 | 13 | no |
| `datasets/Datasets/IRA/North Africa/RNA_0621_tweets_csv_hashed_2019.csv` | io_tweets | 1000 | 4609 | yes |
| `datasets/Datasets/IRA/North Africa/RNA_0621_tweets_csv_hashed_2020.csv` | io_tweets | 1000 | 14291 | yes |
| `datasets/Datasets/IRA/North Africa/hashed_2021_12_RNA_0621_RNA_0621_users.csv` | io_users | 50 | 50 | no |
| `datasets/Datasets/TwitterData_Joined.csv` | twitterdata | 1000 | 308584 | yes |
| `datasets/Datasets/Xinjiang/CNHU_0621_tweets_csv_hashed_2019.csv` | io_tweets | 439 | 439 | no |
| `datasets/Datasets/Xinjiang/CNHU_0621_tweets_csv_hashed_2020.csv` | io_tweets | 1000 | 15195 | yes |
| `datasets/Datasets/Xinjiang/CNHU_0621_tweets_csv_hashed_2021.csv` | io_tweets | 1000 | 15635 | yes |
| `datasets/Datasets/Xinjiang/hashed_2021_12_CNHU_0621_CNHU_0621_users.csv` | io_users | 1000 | 2047 | yes |
| `datasets/Datasets/activity_botscore.csv` | reference | 1000 | 11190 | yes |
| `datasets/East Africa/REA_0621_tweets_csv_hashed_2012.csv` | io_tweets | 1 | 1 | no |
| `datasets/East Africa/REA_0621_tweets_csv_hashed_2013.csv` | io_tweets | 4 | 4 | no |
| `datasets/East Africa/REA_0621_tweets_csv_hashed_2014.csv` | io_tweets | 8 | 8 | no |
| `datasets/East Africa/REA_0621_tweets_csv_hashed_2015.csv` | io_tweets | 3 | 3 | no |
| `datasets/East Africa/REA_0621_tweets_csv_hashed_2016.csv` | io_tweets | 1 | 1 | no |
| `datasets/East Africa/REA_0621_tweets_csv_hashed_2017.csv` | io_tweets | 5 | 5 | no |
| `datasets/East Africa/REA_0621_tweets_csv_hashed_2018.csv` | io_tweets | 117 | 117 | no |
| `datasets/East Africa/REA_0621_tweets_csv_hashed_2019.csv` | io_tweets | 1000 | 5975 | yes |
| `datasets/East Africa/REA_0621_tweets_csv_hashed_2020.csv` | io_tweets | 1000 | 1586 | yes |
| `datasets/East Africa/REA_0621_tweets_csv_hashed_2021.csv` | io_tweets | 23 | 23 | no |
| `datasets/East Africa/hashed_2021_12_REA_0621_REA_0621_users.csv` | io_users | 16 | 16 | no |
| `datasets/ai vs human text/ai_human_detection_v1.csv` | ai_text_v1 | 686 | 686 | no |
| `datasets/ai vs human text/ai_vs_human_text_2026.csv` | ai_text_2026 | 1000 | 2000 | yes |
| `datasets/astroturf/astroturf.tsv` | bot_tsv | 585 | 584 | no |
| `datasets/cresci-rtbust-2019/cresci-rtbust-2019.tsv` | bot_tsv | 759 | 759 | no |
| `datasets/cresci-rtbust-2019/cresci-rtbust-2019_tweets.json` | cresci_json | 693 | 693 | no |
