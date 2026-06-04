# OmiSphere — Intelligence Extraction Execution Roadmap

**Status:** Audit approved. Acquisition frozen. The repository is the intelligence
universe. This is the *sequenced* plan to extract maximum value — planning only,
no implementation yet. Grounded in the live engine (file:line anchors throughout).

---

## Strategic Thesis (read this first)

Two architectural facts reframe everything:

> **1. Omi already has a working cross-account coordination engine — and the gold
> data never reaches it.** `temporal_semantic_cliques`, `fingerprint_cluster`,
> `age_cohort`, `style_match`, `co_engagement` → `aggregate_coordination` →
> per-account elevation all exist and work (`app/detection/coordination/`,
> `orchestrator.py:288-595`). But they were built for **YouTube video comment
> scans** (`CommentEntry`). The 10 IO campaigns flow through
> `ingest_records → analyze_account` — the **single-account** path only
> (`public_import.py:194-295`). **The highest-trust coordination corpus Omi owns
> has never touched the coordination engine.**

> **2. Memory anchoring is fully implemented but gated** (`app/memory/`,
> `orchestrator.py:71-199`) — blocked only because profile-only fingerprints are
> non-discriminative (TRUST_BOUNDARY.md). Text-bearing data fixes that directly.

So the work is **not** "build coordination from scratch." It is, in order:
**(a)** fix the timestamp-synthesis defect that starves every temporal signal;
**(b)** route the existing engine onto the gold IO data at *campaign* granularity;
**(c)** add the **network detectors (co-retweet, hashtag-sync, reply/mention
graphs)** that the IO data *uniquely* enables and YouTube comments never could;
**(d)** use text-bearing TwitterData/cresci to unblock memory + validate FPR.

**The defect that taxes everything:** `_to_posts` (`public_import.py:86-100`)
assigns `created_at = base + timedelta(hours=i)` — **synthetic 1-hour cadence for
every imported account**. Real `tweet_time` (IO) and `Tweet_created_at`
(TwitterData) are discarded at the `PublicRecord.texts: list[str]` boundary. Until
fixed, `temporal` (`temporal.py`) and `temporal_semantic_cliques` operate on
fabricated time. **Phase 0.**

---

## 1. Opportunity Ranking

Scored 1–5 (5 = best/highest). **ROI = Impact × Coordination ÷ Effort, gated by Risk.**

| Opportunity | Impact | Effort* | Risk | Validation | Coordination | Verdict |
|---|:---:|:---:|:---:|:---:|:---:|---|
| **Timestamp foundation** (Phase 0) | 5 | 2 (S-M) | Low | 5 | 5 | **DO FIRST** — unblocks all temporal/coord |
| **TwitterData rehabilitation** | 4 | 2 (S-M) | Low | 5 | 3 | **Fast ROI** — unblocks memory + 1st text validation |
| **IO coordination extraction** | 5 | 4 (L) | Med | 5 | 5 | **Strategic prize** — campaign detection on gold |
| **Cresci tweet integration** | 3 | 3 (M) | Low | 4 | 2 | Memory anchors + trusted validation |
| **Activity-botscore utilization** | 3 | 1 (S) | Low | 5 | 1 | Free calibration win |
| **FSM xlsx conversion** | 2 | 1 (S) | Low | 3 | 1 | Free behavioral-set win |
| **AI-human salvage** | 2 | 1 (S) | Low | 3 | 0 | Free win (drop 10 rows) |
| **Memory-anchoring support** | 4 | 3 (M) | Med | 4 | 3 | Enabled by TwitterData/cresci; re-gate |
| **Trust-boundary support** | 3 | 2 (S-M) | Low | 5 | 3 | FPR discipline; enabled by TwitterData |

*Effort: S ≈ <1 day, M ≈ 2–4 days, L ≈ 1–2 weeks.

**Two orderings, both true:** by **ROI/speed** → Phase 0 → TwitterData → free wins
→ memory. By **strategic value** → IO coordination is #1. The roadmap runs the fast
track *first* (it de-risks and unblocks the IO track), then the strategic track.

---

## 2. IO Dataset Exploitation Plan — *deep signal assessment*

The 30-column schema, mapped to its role. Legend: ✅ do · 🆕 new build · ◐ partial.

| Signal | Extract | Feature (→fingerprint) | Detector | Graph relationship | Memory input | Impact |
|---|:---:|---|---|---|:---:|:---:|
| **tweet_time** | ✅ → real `Post.created_at` | ✅ interval-cov, burst, quiet-hours (already 4 fp dims) | ✅ `temporal` + `temporal_semantic_cliques` (cross-account bursts) | ✅ co-burst time windows | ✅ | **VERY HIGH** (correctness + unlock) |
| **is_retweet / retweet_userid / retweet_tweetid** | ✅ | ✅ retweet ratio = amplifier signal | 🆕 **co-retweet detector** | ✅ **account→account retweet edges** | ✅ new dim | **VERY HIGH** (amplification networks) |
| **in_reply_to_userid / tweetid** | ✅ (also `Post.parent_id`) | ✅ reply ratio | 🆕 reply-brigade detector | ✅ reply graph | ◐ | **MED-HIGH** |
| **hashtags** | ✅ | ✅ hashtag repetition/entropy | 🆕 **hashtag-sync / campaign detector** | ✅ **account×hashtag bipartite** | ✅ narrative fp | **HIGH** (hashtag campaigns) |
| **user_mentions** | ✅ | ✅ mention dispersion | 🆕 mention-target coordination | ✅ mention graph | ◐ | **MED-HIGH** |
| **urls** | ✅ | ✅ domain repetition | 🆕 link-sync (narrative) | ✅ account×domain bipartite | ◐ | **MED** (narrative coordination) |
| **tweet_client_name** | ✅ | ✅ client mix = automation tell | ◐ client-anomaly (feature) | — | ✅ new dim | **MED** |
| **account_creation_date** | ✅ → real `Profile.created_at` | ✅ age/activity ratio | ✅ **`age_cohort` (EXISTS)** | ✅ creation-time cohorts | ✅ | **HIGH** (mass-creation; detector already built) |
| **like/retweet/reply/quote_count** | ✅ | ✅ amplification ratios (low-organic/high-amplified) | ◐ amplification-anomaly | — | ◐ | **MED** |
| **tweet_language / account_language** | ✅ | ✅ language mismatch | ◐ | — | ◐ | **LOW-MED** (multilingual ops) |
| **latitude / longitude** | ✅ | ◐ | ◐ geo-cluster | ◐ geo cohort | — | **LOW** |

**Answers to the 5 mandated questions:**
1. **Extract:** `tweet_time`, `account_creation_date` (replace the two synthetic
   values — correctness), plus retweet/reply/mention/hashtag/url/client as
   structured fields on an extended record.
2. **Become features (per-account → fingerprint):** retweet-ratio, reply-ratio,
   hashtag-repetition, client-mix, amplification-ratio, language-mismatch. These
   make fingerprints **discriminative for IO** (the dims profile-only lacked).
3. **Become detectors:** route to **existing** `temporal_semantic`, `age_cohort`,
   `style_match`, `fingerprint_cluster`; **build new** co-retweet, hashtag-sync,
   reply-brigade, mention-target.
4. **Become graph relationships:** retweet edges, mention edges, reply edges,
   account×hashtag + account×url bipartite, creation-time cohorts. **This is the
   campaign-detection substrate Omi does not yet have.**
5. **Become memory inputs:** extend the 23-dim fingerprint
   (`fingerprint.py:52-69`, append-only) with retweet-ratio / client / hashtag /
   amplification dims → IO accounts cluster tightly → `fingerprint_cluster`
   coordination + memory anchoring both sharpen.

**Expected impact:** today IO scores via single-account detectors only (the audit's
"text blob"). Routed through the coordination engine + new network detectors, the 10
campaigns (~3,827 accounts) become a **measurable coordination-recall benchmark** and
the training/validation substrate for **artificial-amplification and
narrative-coordination** detection — capabilities Omi currently cannot claim.

---

## 3. TwitterData Exploitation Plan — *deep assessment*

292,626 tweets / **96 deep-timeline accounts**, balanced (150,708 human / 141,918
bot), **Label 1 = human, 0 = bot** (inverted), with text + `Tweet_created_at` +
features; `TwitterData_Joined` adds `Verified`.

| Dimension | Value | How Omi uses it |
|---|:---:|---|
| **Training** | MED (96 accts, deep) | Per-account supervised check of `semantic`/`voice`/`ai_writing`/`temporal` — text makes them *fire* (unlike profile-only). Use for fingerprint seeding + detector tuning, **not** bulk ML (account-N too small). |
| **Validation** | **VERY HIGH** | **First text-bearing both-class `calibrate.py --from-db`**: do bots tier ELEVATED/HIGH and humans LOW? Measures real recall **and** FPR — impossible on the profile-only sets. |
| **Trust-dataset** | **HIGH** | Fills Known-Good-with-text **and** Known-Bad-with-text simultaneously (the Tier-2C gap). |
| **Known-Good** | HIGH | The 48 human accounts (esp. high-volume) → the human-baseline neighbor set for memory. |
| **Known-Mixed** | **HIGH** | `Verified=1` accounts (e.g. @SadiqKhan) = legitimate high-profile coordination → the **FPR guard** cohort (must stay LOW). |
| **Coordination** | MED | No edge graph (counts, not edges) — but bot accounts should form `style_match`/`fingerprint_cluster` clusters while humans must **not**. A labeled test of those two detectors + a negative control. |

**Use sequence:** rehab adapter (decode `Label` polarity, strip `b''` wrapper, real
`Tweet_created_at`) → ingest → `calibrate --from-db` (text validation) → seed the
memory store with **discriminative** fingerprints (humans = Known-Good anchors, bots
= Known-Bad anchors) → **re-evaluate the anchoring gate** → run the Verified subset as
the Known-Mixed FPR guard. **TwitterData is the key that unlocks memory.**

---

## 4. Coordination Detection Roadmap — *the spine*

Every initiative answers: *coordinated actors? campaigns? influence ops? artificial
amplification? narrative coordination?*

| Layer | Build | Coordinated actors | Campaigns | Influence ops | Amplification | Narrative |
|---|---|:---:|:---:|:---:|:---:|:---:|
| **0. Route IO → engine** | campaign-scan driver + entry adapters | ✅ via existing clique/style/fp/cohort | ✅ per-campaign score | ✅ recall on 10 ops | — | — |
| **1. Co-retweet** 🆕 | account→account RT graph + community detect | ✅ | ✅ | ✅ | ✅✅ **direct** | ◐ |
| **2. Hashtag-sync** 🆕 | account×hashtag bipartite + burst-in-window | ✅ | ✅✅ **direct** | ✅ | ◐ | ✅✅ **direct** |
| **3. Reply/mention graph** 🆕 | directed graphs + brigade clusters | ✅ | ✅ | ✅ | ✅ | ◐ |
| **4. Cross-campaign attribution** 🆕 | fingerprint/style match *across* the 10 ops | ✅ | ✅ | ✅✅ | ◐ | ✅ |
| **5. FPR guard** | run all over TwitterData-verified + cresci-human | ✅ (precision) | ✅ | ✅ | ✅ | ✅ |

**Reuse first:** 4 of 5 existing coordination detectors run on IO with only entry
adaptation — `temporal_semantic_cliques` (tweetid→comment_id, userid→author,
tweet_text→text, tweet_time→created_at), `age_cohort` (account_creation_date),
`style_match` (per-author texts), `fingerprint_cluster` (ingest fingerprints). Only
`co_engagement` (YouTube-specific) is replaced by the new **co-retweet** detector —
the IO-native analog of shared-engagement.

---

## 5. Memory Support Roadmap

Code exists (`memory/fingerprint.py`, `memory/prior.py`, orchestrator integration);
the gate is data-bound, not code-bound.

1. **Make fingerprints discriminative** — ingest TwitterData + cresci (text) so
   `semantic`/`voice`/`ai_writing`/`temporal` dims carry real signal (today the
   gate fails on profile-only overlap).
2. **Seed a labeled neighbor store** — humans (Known-Good) + bots/IO (Known-Bad)
   with text-bearing fingerprints.
3. **Re-run `memory_benchmark.py`** — the learning-curve + FPR-guard harness already
   exists; re-evaluate the TRUST_BOUNDARY gate against the *new* anchor set.
4. **Extend fingerprint with IO network dims** (retweet-ratio, client, hashtag) —
   append-only (`FINGERPRINT_DIM`), so backward-compatible.
5. **Gate decision** — flip anchoring on only if FPR guard (Known-Mixed verified)
   holds. Coordination value: memory makes a *previously-seen* IO fingerprint
   elevate a new lone account → cross-scan campaign memory.

---

## 6. Intelligence Extraction Roadmap (30 / 60 / 90)

Focus: coordination · trust · memory · campaign intelligence. **Not** platform expansion.

### 30-Day — Foundation + Fast Validation + Free Wins
- **P0 Timestamp foundation:** extend `PublicRecord` with per-post times; populate
  from `tweet_time`/`Tweet_created_at`; `_to_posts` uses real times. *Correctness
  fix unblocking all temporal/coordination work.*
- **TwitterData rehab + ingest + first text-bearing `calibrate --from-db`.**
- **Free wins:** FSM `xlsx→csv`; salvage `ai_human_detection_v1` (drop 10 rows);
  wire `activity_botscore` into tier calibration.
- **Memory:** seed text fingerprints; re-run `memory_benchmark`; re-assess gate.
- **Exit:** Omi validated against real human+bot **text**; memory gate re-decided;
  3 datasets unlocked; temporal signals no longer synthetic.

### 60-Day — Route the Gold IO Into the Coordination Engine
- **IO coordination extractor** (`CoordinationCorpus`): parse the 30-col files into
  per-account features + the coordination entry types.
- **Campaign-scan driver:** run the **existing** `temporal_semantic`/`age_cohort`/
  `style_match`/`fingerprint_cluster` over each campaign's accounts.
- **Measure coordination recall** on all 10 campaigns; calibrate
  `aggregate_coordination` priors against gold.
- **Exit:** the coordination engine finally scores the gold data; per-campaign
  coordination scores + recall benchmark exist.

### 90-Day — Native Network Detectors + Campaign Intelligence
- **Build co-retweet + hashtag-sync** (then reply/mention graphs) — the
  amplification + narrative-coordination capabilities Omi lacks.
- **Cross-campaign attribution** — fingerprint/style match across the 10 ops.
- **FPR guard** — TwitterData-verified + cresci-human must stay LOW.
- **Exit:** Omi detects **coordinated campaigns** (not just suspicious accounts),
  validated on gold IO with precision held on Known-Mixed.

---

## 7. Recommended Execution Order (dependency-sequenced)

```
P0  Timestamp foundation ─────────────┐ (unblocks temporal + coordination)
        │                              │
        ▼                              ▼
P1  TwitterData rehab            (free wins: FSM xlsx, AI-salvage, botscore)
        │  └─► text validation (calibrate --from-db)
        ▼
P2  Memory: seed fingerprints → re-run benchmark → re-gate
        │
        ▼
P3  IO extractor (CoordinationCorpus)  ◄── needs P0 timestamps
        │
        ▼
P4  Campaign-scan driver → route IO into EXISTING coordination detectors
        │  └─► coordination-recall benchmark on 10 campaigns
        ▼
P5  NEW network detectors: co-retweet → hashtag-sync → reply/mention
        │
        ▼
P6  Cross-campaign attribution + FPR guard (Known-Mixed)
```
**Critical path:** P0 → P3 → P4 → P5. **Parallelizable off P0:** P1/P2 + free wins.

---

## 8. Top 10 Highest-Leverage Improvements

| # | Improvement | Why it's leverage | Coord value | Effort |
|---|---|---|:---:|:---:|
| 1 | **Real per-post timestamps** through `PublicRecord` | Every temporal/burst signal is fake until fixed; unblocks P3-P5 | ★★★★★ | S-M |
| 2 | **Route IO into the existing coordination engine** (campaign-scan) | Gold data finally reaches built detectors; instant recall benchmark | ★★★★★ | M |
| 3 | **Co-retweet detector** (RT graph) | Direct artificial-amplification detection; IO-native | ★★★★★ | M |
| 4 | **Hashtag-sync detector** (account×hashtag) | Direct campaign + narrative-coordination detection | ★★★★★ | M |
| 5 | **TwitterData rehab + ingest** | First text-bearing validation; seeds memory | ★★★ | S-M |
| 6 | **Memory fingerprints made discriminative** (text) | Flips the anchoring gate; cross-scan campaign memory | ★★★ | M |
| 7 | **Extend fingerprint with IO network dims** | Tightens `fingerprint_cluster` on real coordination | ★★★★ | S |
| 8 | **Cross-campaign attribution** | Detect one actor across 10 ops; transfer to unseen | ★★★★ | M |
| 9 | **FPR guard on Known-Mixed** (verified/cresci-human) | Keeps precision while recall rises; trust discipline | ★★★ | S |
| 10 | **activity_botscore tier calibration** | Independent second opinion → threshold tuning | ★★ | S |

---

### Guardrails (carry through every phase)
- **Precision before recall:** each coordination layer ships with its Known-Mixed
  FPR guard (TwitterData-verified, cresci-human). Legitimate coordination
  (politicians on-message, newsroom house-style) must **not** trip thresholds.
- **Append-only fingerprints** keep memory backward-compatible.
- **Validation-first governance:** IO/TwitterData promote `validation → train` only
  after a reviewed calibration (manifest already encodes this).
- **No acquisition:** every line above runs on data already in the repo.

> The objective was never more data. Omi owns a working coordination engine and a
> 30-column, 4-actor, 3,800-account record of real influence operations that the
> engine has never seen. The roadmap connects the two — and builds the
> amplification/narrative detectors the IO data uniquely makes possible.
