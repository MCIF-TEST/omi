# OmiSphere — Dataset Intelligence Audit

**Method:** repository-first. Every figure below was produced by running the
production discovery engine (`app.ml.datasets.discovery.discover`) + governance
manifest over the real on-disk tree, then profiling each file's schema, label
semantics, class balance, and defects directly. Organization was **discovered,
not assumed** — the tree is intentionally messy (campaigns nested under
`Datasets/`, duplicates at root, an Excel file, an XZ blob with no extension).

**Date:** 2026-06-04 · **Branch:** `claude/focused-turing-upy6c` · **Scope:** 70 discovered files.

---

## Executive Summary

**What Omi actually has:**

| Asset class | Volume | Trust | State today |
|---|---|---|---|
| State-IO disclosure campaigns (10 ops: RU/IR/CN/Africa) | **~3,827 accounts**, ~580MB tweets, **30-col coordination schema** | **GOLD** (platform-attributed) | Ingested as text+followers only — **27 of 30 columns dropped** |
| Labeled human+bot **text** corpus (`TwitterData_*`) | 292,626 tweets / **96 deep-timeline accounts**, balanced 51/49 | MEDIUM (now decoded) | **Archived as "unverified"** — actually usable |
| Bot/human label ground truth (astroturf, cresci-rtbust) | 585 + 759 ids (+ cresci **tweets.json** w/ text) | GOLD (academic) | Labels ingested; **cresci text unused** |
| Behavioral fake-account features (FSM) | ~5k profiles + balanced xlsx | MEDIUM | real/fake normalized; **best (xlsx) unreadable** |
| AI-vs-human text | ~3.7k rows | MEDIUM | 1 validation; 1 salvageable; 1 stub |
| Calibration (`activity_botscore`) | 11,191 continuous bot scores | HIGH | reference, **unwired to tiers** |

**The three headline findings:**

1. **The IO archives are a coordination goldmine read as a text blob.** The
   30-column schema carries `tweet_time`, `is_retweet`/`retweet_userid`,
   `in_reply_to_userid`, `hashtags`, `user_mentions`, `urls`,
   `tweet_client_name`, `account_creation_date`, and amplification counts.
   `io_disclosure` extracts **only** `tweet_text` + `userid` + follower/following.
   Every network, temporal, narrative, and automation signal in the highest-trust
   data Omi owns is **discarded at the adapter boundary.** This is the #1 leverage point.

2. **`TwitterData_*` was archived on a false premise.** Decoded: **Label 1 = human
   (@SadiqKhan), 0 = bot (@MuseumBot)** — *inverted* from convention, balanced
   (150,708 / 141,918), 96 accounts with ~3,000 tweets each **including text**.
   The "overlapping variants" are the same data with different corruption
   (b''-wrapped text / float-rounded ids / sci-notation). This is the
   text-bearing human+bot baseline Tier-2C said was missing — already in the repo.

3. **Two quarantines are over-broad.** `ai_human_detection_v1` is only **1.5%
   contaminated** (10/686 rows) yet quarantined whole; the FSM **balanced
   behavioral set exists** but is locked inside an unreadable `.xlsx`.

---

## 1. Dataset Inventory

Trust scale: **GOLD** (platform/academic-verified) · **HIGH** · **MEDIUM** · **LOW** · **POISON**.

### A. State-IO Disclosure Campaigns — *coordination ground truth* (GOLD)

- **Source:** Twitter/X Transparency information-operation takedown archives (hashed).
- **Provenance:** platform-attributed — every account confirmed by the platform as
  part of a state-backed coordinated operation. Highest-confidence inauthentic truth that exists.
- **Format:** per-tweet CSV, **30 columns**; companion 10-col `*_users.csv` roster.
- **Tweets schema (30):** `tweetid, userid, user_display_name, user_screen_name,
  user_reported_location, user_profile_description, user_profile_url,
  follower_count, following_count, account_creation_date, account_language,
  tweet_language, tweet_text, tweet_time, tweet_client_name, in_reply_to_userid,
  in_reply_to_tweetid, quoted_tweet_tweetid, is_retweet, retweet_userid,
  retweet_tweetid, latitude, longitude, quote_count, reply_count, like_count,
  retweet_count, hashtags, urls, user_mentions`.
- **Users schema (10):** `userid, display_name, screen_name, reported_location,
  profile_description, profile_url, follower_count, following_count,
  account_creation_date, account_language`.
- **Labeling quality:** GOLD for the *coordination* verdict (implicit: 100% positive class).
- **Adapter:** `io_disclosure` (tweets → `political_coord`/`high`). `*_users.csv`: **no adapter.**

| Campaign | State | Accounts | Tweet volume | Path |
|---|---|---:|---|---|
| russia_052020 | Russia | 1,153 | ~175 MB (2 parts) | `2020-05/` |
| iran_092020 | Iran | 105 | 1.5 MB | `2020-09/` |
| iran_202012 | Iran | 238 | ~304 MB (4 parts) | `2021-02/` |
| CNCC_0621 (Changyu Culture) | China | 112 | ~14 MB (by year) | `Changyu Culture/` |
| GRU_202012 | Russia (GRU) | 70 | 15.2 MB | `Datasets/GRU/` |
| IRA_092020 | Russia (IRA) | 5 | 1.0 MB | `Datasets/IRA/2020-09/` |
| IRA_202012 | Russia (IRA) | 31 | 41.0 MB | `Datasets/IRA/2021-02/` |
| RNA_0621 (North Africa) | Russia/IRA | 50 | ~11 MB (by year) | `Datasets/IRA/North Africa/` |
| CNHU_0621 (Xinjiang) | China | 2,047 | ~14 MB (by year) | `Datasets/Xinjiang/` |
| REA_0621 | East Africa | 16 | ~5.7 MB (by year) | `East Africa/` |
| **Total** | **4 actors** | **~3,827** | **~580 MB** | |

### B. Behavioral Fake-Account Features (`Datasets/Fake Social Media Account Detection Dataset/`)

- **`real_users.csv` / `fake_users.csv`** — 34-col classic Twitter profile schema, ~2,500 each,
  filename-labeled. **Source:** MIB/Cresci-lineage. **Trust:** MEDIUM. **Caveat:** values are
  **normalized/perturbed floats** (e.g. `statuses_count=2125.68`, `followers_count=0.0/87.57`),
  not raw counts → limited for raw-feature use. **Adapter:** `twitter_user_features` (matched). No text.
- **`fake_social_media.csv`** — 18-col behavioral (`username_randomness, follower_following_ratio,
  caption_similarity_score, content_similarity_score, follow_unfollow_rate, spam_comments_rate, …`),
  3,000 rows, **is_fake = 2,993/7 (99.8% one class)** → untrainable. **Adapter:** `fake_social_media`. **Status:** archive.
- **`fake_social_media_global_2.0_with_missing.xlsx`** — the **balanced** set (1,941/1,059) per prior
  review, but **unreadable as `.xlsx`** by the CSV pipeline. **Status:** train-blocked.
- **`bot_detection_data.csv`** — 11-col, 50,000 rows; text is **Faker word-salad**
  ("Station activity person against natural majority…"), label **uncorrelated with features** (random). **POISON.**
- **`reddit_dead_internet_analysis_2026.csv`** — 11-col, 500 rows, **cross-platform (Reddit)**:
  `account_age_days, user_karma, reply_delay_seconds, sentiment_score, avg_word_length,
  contains_links, is_bot_flag, bot_type_label, bot_probability`. **Adapter:** `reddit_dead_internet`
  (reads only `is_bot_flag`+age — drops reply-delay/type/probability). **Trust:** MEDIUM. **Status:** validation.

### C. Labeled Human+Bot **Text** Corpus (`Datasets/TwitterData_*`)

- **Decoded label semantics:** `Label 1 = human, 0 = bot` (**inverted** — @SadiqKhan=1, @MuseumBot=0).
- **`TwitterData_FE.csv`** — 23 cols, **292,626 tweets / 96 accounts**, balanced (150,708/141,918),
  **clean text** + engineered features (`Word_Count, Url_Count, Retweet, Mentions_Count, Hashtags_Count,
  POS counts, sentiment ratios`). **Best variant.**
- **`TwitterData_Joined.csv`** — 29 cols = FE **+ `Following, Followers, Verified, Location, Real_Location`**.
  **Richest** (profile + verified flag → Known-Mixed extraction). `accounts_generic` matches but would
  **mislabel** (treats `1`→bot). Tweet ids sci-notation-corrupted (irrelevant; we group by account).
- **`Twitter_Data.csv`** — 7 cols; full-precision tweet ids **but text is b''-wrapped** (`str(bytes)` defect). Redundant.
- **`Twitter_Users.csv`** — 96-account roster (`name, Following, Followers, Verified, Link, Location`).
- **`location_data.csv`** — 57 rows, `account, location, lat/long, label`. Auxiliary.
- **Source:** unknown compiler; accounts are real public Twitter (verified figures + named bots).
  **Trust:** MEDIUM (small account-N, but deep, decodable, balanced). **Status:** all archive → **upgrade candidates.**

### D. AI-vs-Human Text (`ai vs human text/`)

- **`ai_vs_human_text_2026.csv`** — 9 cols, ~2,000 rows, `label(human/ai), source_model, domain,
  text_content, generation_method`. **Adapter:** `ai_vs_human_text_2026`. Dedupe (~51% dup). **Status:** validation.
- **`ai_human_detection_v1.csv`** — 11 cols, **686 rows**, `human_or_ai, source_model, prompt, edit_level…`.
  **Only 1.5% (10 rows) contaminated** with "Error 400". **Adapter:** `ai_human_detection_v1`. **Status:** quarantine → **salvageable.**
- **`ai_vs_human_text.csv`** — 6 cols, ~1,000 rows, **100% templated stub** text. **Adapter:** `ai_vs_human_text_v1`. **Status:** archive.

### E. Bot/Human Label Ground Truth

- **`astroturf/astroturf.tsv`** — headerless `id<TAB>political_Bot`, **585 ids**. **Source:** OSoMe.
  **Trust:** GOLD (confirmed political bots). **Adapter:** `astroturf` → bot. Label-only (no text).
- **`cresci-rtbust-2019/cresci-rtbust-2019.tsv`** — headerless `id<TAB>human|bot`, **759 ids**.
  **`cresci-rtbust-2019_tweets.json`** — **full Twitter API tweet objects** (text, profile, timestamps) for
  these accounts, **currently unused.** **Source:** Cresci et al. academic. **Trust:** GOLD. **Adapter:** `cresci_rtbust` (labels only).

### F. Calibration / Reference

- **`Datasets/activity_botscore.csv`** — `user_id, age, count, activity, bot_score_english` (continuous 0–1),
  **11,191 rows**, no class label. **Trust:** HIGH (Botometer-derived). **Adapter:** none. **Status:** reference —
  ideal for **bot_score → Omi-tier calibration**, currently unwired.

### G. Investigate / Other

- **`Datasets/article_discusses_claim`** — **XZ-compressed binary** (magic `FD 37 7A 58 5A`), no extension;
  prior note "fact-check domain, unpicklable". **Action:** `xz -d` to confirm; possible narrative/claim corpus.

---

## 2. Dataset Intelligence Matrix

Use-case codes: **BD** bot-detect · **CD** coordination · **CAMP** campaign · **IO** influence-op ·
**NAR** narrative · **STY** style · **FP** fingerprint · **TR** trust · **HB** human-baseline ·
**MA** memory-anchor · **CAL** calibration · **VAL** validation.

| Dataset | Purpose | Trust | Omi Use Cases | Train | Valid | Adapter | Priority |
|---|---|---|---|---|---|---|---|
| **IO campaigns (tweets, 10 ops)** | Coordination ground truth | GOLD | CD·CAMP·IO·NAR·FP·TR·STY·MA | ★★★★★ | ★★★★★ | exists (under-reads) → **extend** | **P0** |
| IO campaigns (`*_users`) | Account roster/profile | GOLD | FP·TR·MA·HB(neg) | ★★ | ★★★ | **new (S)** | P3 |
| **TwitterData_FE / Joined** | Human+bot text baseline | MEDIUM | HB·BD·STY·FP·VAL·MA | ★★★★ | ★★★★ | **new (S-M)** + clean | **P0** |
| cresci-rtbust `.tsv` + `tweets.json` | Bot/human truth +text | GOLD | BD·HB·STY·FP·VAL | ★★★★ | ★★★★ | exists+**extend (M)** | **P1** |
| astroturf | Political-bot ids | GOLD | BD·VAL | ★★★ | ★★★★ | exists | P2 |
| real_users / fake_users | Labeled profiles | MEDIUM | BD·TR·HB·MA(neg) | ★★★ | ★★★ | exists | P2 |
| fake_social_media **xlsx** (balanced) | Behavioral features | MEDIUM | BD·FP·TR | ★★★★ | ★★★ | **convert+new (S)** | P1 |
| fake_social_media.csv | Behavioral (imbalanced) | LOW | (feature schema ref) | ✗ | ★ | exists | archive |
| reddit_dead_internet | Cross-platform bot taxonomy | MEDIUM | BD·CAL·VAL·FP | ★★ | ★★★★ | exists→**extend (S)** | P2 |
| activity_botscore | Score→tier calibration | HIGH | CAL·TR·VAL | ✗ | ★★★★ | **new (S)** | P1 |
| ai_vs_human_text_2026 | AI-content benchmark | MEDIUM | STY·VAL·HB | ★★ | ★★★★ | exists | P2 |
| ai_human_detection_v1 | AI/human text | MEDIUM | STY·VAL | ★★ | ★★★ | exists (filter) | P2 (salvage) |
| bot_detection_data | Synthetic noise | POISON | VAL(neg control only) | ✗ | ★ | none | quarantine |
| ai_vs_human_text.csv | Templated stub | LOW | (format test) | ✗ | ✗ | exists | archive |
| location_data | Geo auxiliary | LOW | (geo join) | ✗ | ★ | none | archive |
| article_discusses_claim | Unknown (XZ) | ? | NAR? | ? | ? | none | investigate |

---

## 3. Intelligence Opportunity Matrix — *"what capability could Omi gain?"*

> *A dataset need not be a bot dataset to improve bot/campaign detection.*

| Dataset | Non-obvious intelligence capability unlocked |
|---|---|
| **IO tweets** | **Co-retweet / co-mention / co-hashtag graphs** (network coordination); **temporal burst** fingerprints from `tweet_time`; **client-mix automation** signal (`tweet_client_name`); **cross-campaign narrative** clustering (`hashtags`/`urls`/text); **mass-creation** cohorts (`account_creation_date`); **amplification** ratios (like/RT/reply) → trains CD·CAMP·IO·NAR·FP simultaneously. |
| **TwitterData (verified subset)** | The `Verified=1` accounts (e.g. @SadiqKhan) are a **Known-Mixed** cohort → measure FPR of coordination on legitimate high-profile coordination, with **real text** for `style`/`temporal`. |
| **TwitterData (bot subset, deep timelines)** | ~3,000 tweets/account → **per-account style & rhythm fingerprints** that single-tweet data can't build. |
| **real_users / IO users (profile)** | *Negative result is the asset*: profile metadata overlaps across humans/bots/IO (Trust Boundary finding) → the **guardrail** proving memory-anchoring must not key on profile alone. |
| **activity_botscore** | A **second opinion** distribution to calibrate Omi tier thresholds and detect score drift — without any labels. |
| **reddit_dead_internet** | `reply_delay_seconds` = **automation-timing** signal; `bot_type_label` = a **taxonomy** to enrich Omi's verdict vocabulary; **cross-platform** generalization check. |
| **ai_vs_human_text_2026** | Human social rows = a **micro human-style reference**; AI rows = drift test for `ai_content`. |
| **cresci tweets.json** | Trusted **text-bearing** human accounts → the FPR control `style`/`temporal` currently lack. |
| **bot_detection_data (noise)** | **Adversarial negative control**: Omi should find *no* coordination in random gibberish — a false-positive stress test. |
| **location_data / IO lat-long** | **Geographic clustering** of coordinated accounts (geo-coordination probe). |

---

## 4. Adapter Roadmap

Effort: **S** ≈ <1h / ~15 lines · **M** ≈ few hours · **L** ≈ day+ (touches `PublicRecord`/engine).

**Exists, no change:** `io_disclosure` (tweets), `twitter_user_features`, `fake_social_media`,
`reddit_dead_internet`, `astroturf`, `cresci_rtbust` (labels), `ai_vs_human_text_2026/v1`,
`text/accounts_generic`, `labeled_tweets`.

**Extend:**
- **`io_disclosure` → coordination-aware (L).** The architectural crux: `PublicRecord` is account-centric
  (texts+profile) so the 27 dropped columns have nowhere to go. Recommend a **parallel
  `CoordinationCorpus` extractor** that reads the raw 30-col CSVs into (a) per-account temporal/client/
  amplification features and (b) account×account edges (retweet/mention/reply) + shared-hashtag/url
  bipartite tables — consumed by the coordination detector. Lightly extend `PublicRecord` with optional
  `post_times`/`client` for temporal use. **Highest payoff.**
- **`cresci_rtbust` → join `tweets.json` (M).** Add a JSON reader that attaches text+timestamps to the
  labeled ids → text-bearing human/bot accounts.
- **`reddit_dead_internet` (S).** Surface `reply_delay_seconds`, `bot_type_label`, `bot_probability`.

**New:**
- **`twitterdata` (S-M).** `Twitter_Account`→handle, `Tweet_text`→text, **`Label` with inverted polarity
  (1=human, 0=bot)**, collapse per account. Must NOT reuse `accounts_generic` (wrong polarity). + cleanup pass.
- **`io_users` (S).** 10-col profile roster → canonical account list / profile backfill.
- **`activity_botscore` (S).** Continuous-score reference loader for calibration (no class label).
- **xlsx → csv (S, external).** Convert the balanced FSM set, then `fake_social_media` adapter ingests it.

---

## 5. Training Roadmap

1. **Coordination features from IO** (P0) — the only large GOLD-labeled coordination training signal; requires the extractor (§4).
2. **TwitterData human+bot text** (P0) — after cleanup+adapter: 96 deep-timeline accounts for style/fingerprint/bot models (small N, high depth — use for per-account models, not account-count-hungry ones).
3. **Balanced FSM behavioral** (P1) — after xlsx→csv: the one clean balanced profile-feature set.
4. **cresci human/bot +text** (P1) — trusted text-bearing both-class anchor.
5. **Profiles (real/fake_users)** (P2) — labeled profile negatives/positives, with the normalization caveat.

> Account-N is the scarce resource (96 + ~5k profiles + ~3.8k IO). Favor **per-account / behavioral**
> models and **transfer**, not architectures needing 10⁵ accounts.

## 6. Validation Roadmap

1. **IO recall** — does Omi flag the ~3,827 confirmed accounts? (already partially measured: ~67% on text-bearing IO.)
2. **Known-Mixed FPR** — TwitterData verified figures + high-volume legitimate accounts must stay low-tier.
3. **Cross-platform** — `reddit_dead_internet` (does bot signal generalize off Twitter?).
4. **AI-content** — `ai_vs_human_text_2026` (deduped).
5. **Negative control** — `bot_detection_data` gibberish must yield *no* coordination.
6. **Calibration** — `activity_botscore` distribution vs Omi tiers.

## 7. Coordination Detection Roadmap

The IO archives make Omi's coordination story end-to-end — *if* §4's extractor lands:

1. **Network layer** — co-retweet (`retweet_userid`), co-mention (`user_mentions`), reply graphs
   (`in_reply_to_userid`) → detect account clusters acting in concert.
2. **Content-sync layer** — shared `hashtags`/`urls` + near-duplicate `tweet_text` within windows
   → message-coordination (the legit-vs-illegit discriminator vs newsroom/brand house-style).
3. **Temporal layer** — `tweet_time` burst & rhythm synchrony across accounts.
4. **Automation layer** — `tweet_client_name` mix + `account_creation_date` mass-creation cohorts.
5. **Cross-campaign** — fingerprint the 10 ops against each other → attribution + transfer to unseen ops.
6. **FPR guard** — run the same pipeline over TwitterData-verified + high-volume humans; legitimate
   coordination (politicians on-message) must **not** trip illegit-coordination thresholds.

---

## 8. Top 20 Highest-Leverage Opportunities

| # | Opportunity | Capability | Effort | Depends |
|---|---|---|---|---|
| 1 | **IO coordination extractor** (temporal+network+hashtag+client from 30-col files) | CD·CAMP·IO·FP·NAR | L | — |
| 2 | **Rehabilitate TwitterData** (decode polarity, strip b'', dedupe, adapter) | HB·BD·STY·FP·VAL | S-M | — |
| 3 | **cresci `tweets.json` join** → text-bearing human/bot truth | HB·STY·BD·VAL | M | — |
| 4 | **Co-retweet/co-hashtag graphs** per campaign | CD·CAMP | M | 1 |
| 5 | **xlsx→csv** balanced FSM behavioral set | BD·FP | S | — |
| 6 | **activity_botscore → tier calibration** | CAL·TR | S | — |
| 7 | **Temporal burst fingerprints** from `tweet_time` | CD·FP·STY | M | 1 |
| 8 | **Client-mix automation signal** (`tweet_client_name`) | BD·IO | S | 1 |
| 9 | **Known-Mixed cohort** from TwitterData `Verified=1` | TR·VAL | S | 2 |
| 10 | **Cross-campaign narrative clustering** (hashtags/urls/text) | NAR·CAMP·IO | M | 1 |
| 11 | **reddit reply-delay + bot_type + probability** | BD·CAL·VAL | S | — |
| 12 | **IO users roster adapter** (few-tweet accounts, profile backfill) | FP·TR | S | — |
| 13 | **AI-text human-style reference** (2026 set) | STY·VAL | S | — |
| 14 | **Salvage ai_human_detection_v1** (drop 1.5% Error rows) | STY·VAL | S | — |
| 15 | **Profile non-discrimination → anchoring guardrail** (IO users + FSM) | MA·TR | S | — |
| 16 | **Combined bot-recall set** (astroturf + cresci ids) | BD·VAL | S | — |
| 17 | **Synthetic-noise negative control** (bot_detection_data) | VAL | S | — |
| 18 | **Account-age mass-creation cohorts** (`account_creation_date`) | CD·IO | S | 1 |
| 19 | **Geo-coordination probe** (IO lat/long + location_data) | CD | M | 1 |
| 20 | **Investigate `article_discusses_claim`** (xz -d → narrative?) | NAR | S | — |

---

## Strategic Recommendations

**1. Highest-value datasets:** the **10 IO campaigns** (the only GOLD coordination corpus, currently
90%-untapped) and **TwitterData_FE/Joined** (the missing human+bot *text* baseline, wrongly archived).

**2. Most underutilized:** **IO 30-col schema** (27 columns dropped at ingest); **cresci `tweets.json`**
(text discarded); **activity_botscore** (calibration sitting idle); **reddit** extra columns; the
**balanced FSM xlsx** (locked by format).

**3. Quarantine (keep out of training):** `bot_detection_data.csv` (random labels + synthetic text) —
retain *only* as a negative control. `ai_vs_human_text.csv` (templated stub) — archive.

**4. Validation-only:** `ai_vs_human_text_2026`, `reddit_dead_internet`, `activity_botscore`, the
TwitterData **verified** subset, and all IO data **until** the coordination extractor is calibrated
(promote IO to train only after the first reviewed eval).

**5. Training priorities (in order):** (1) IO coordination features → (2) cleaned TwitterData text →
(3) balanced FSM behavioral → (4) cresci text. Reclassify these four out of `archive`/blocked once
§4's adapters land.

**Two free wins, no new code:** un-quarantine `ai_human_detection_v1` after dropping 10 rows; convert
the FSM `.xlsx` to CSV. **One false belief corrected:** `TwitterData_*` is not "unverified noise" —
it is labeled, balanced, text-bearing human+bot data (polarity 1=human/0=bot).

> The objective was never more data. Omi already owns a 30-column, 4-actor,
> 3,800-account record of real coordinated influence operations. The work is to
> **stop throwing 27 of those 30 columns away.**
