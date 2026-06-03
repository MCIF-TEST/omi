# OmiSphere Trust Dataset — Inventory, Coverage & Acquisition Plan

Tier 2C. The purpose of the Trust Dataset is to be the strongest possible
real-world foundation for calibration, memory anchoring, evaluation, and trust
metrics. This document is the authoritative, *measured* state of that
foundation and the roadmap to expand it. It is derived from an audit of the
committed `datasets/` tree and `datasets/manifest.toml` — not from assumption.

Four categories: **Known Bad**, **Known Good**, **Known Mixed**,
**Known Uncertain**.

---

## 1. Dataset Inventory (what is actually on disk)

### Known Bad — coordination / information operations (STRONG)
Platform-attributed state-IO disclosures. 30-column `io_disclosure` schema
(`userid`, `tweet_text`, `tweet_time`, `account_creation_date`, follower/
following counts, profile fields). **Text-bearing**, one row per tweet.
Governed `validation`, labeled `political_coord` / expected tier `high`.

| Archive | Operation | Size | Files |
|---|---|---|---|
| `2020-05` | Russia (May 2020) | 183 MB | 3 |
| `2020-09` | Iran (Sep 2020) | 1.6 MB | 2 |
| `2021-02` | Iran (Dec 2020) | 319 MB | 5 |
| `Changyu Culture` | China (CNCC) | 15 MB | 12 |
| `East Africa` | E. Africa regional | 5.7 MB | 11 |
| `Datasets/GRU` | Russia GRU | 16 MB | 2 |
| `Datasets/IRA` | Russia IRA + N. Africa | 55 MB | 14 |
| `Datasets/Xinjiang` | China (CNHU) | 15 MB | 4 |
| **Total** | **8 nation-state operations** | **~610 MB** | **53** |

### Known Bad — bots / astroturf (MODERATE)
| Source | Shape | Text? | Status |
|---|---|---|---|
| `astroturf/astroturf.tsv` | OSoMe political bots, `id<TAB>label` | no | validation |
| `cresci-rtbust-2019` | human/bot `id<TAB>label` (+ tweets JSON) | **no** (JSON lacks tweet text) | validation |
| `Datasets/Fake Social Media…/fake_users.csv` | 34-col profile rows | bio only | train |
| `Datasets/…/reddit_dead_internet_analysis_2026.csv` | Reddit bot taxonomy (features) | no | validation |
| `Datasets/activity_botscore.csv` | continuous `bot_score`, no class | no | reference |

### Known Good — real humans (WEAK — this is the priority gap)
| Source | Shape | Text? | Status |
|---|---|---|---|
| `Datasets/Fake Social Media…/real_users.csv` | real-human **profiles** (34 cols) | `description` bio only — **no tweet history** | train |
| `cresci-rtbust-2019` humans | `id<TAB>human` | **no** | validation |

There is **no corpus of active humans with real tweet history and normal
engagement**. Every human negative we have is profile-level. Consequence:
`fingerprint`/`cohort` are validated against real humans (FPR 0.0), but
`style`/`temporal_semantic` have **never been stress-tested against real
humans with text** — and the Tier-2B calibration *up-weights* `style`.

### Known Mixed — legitimate-but-coordination-shaped (NONE)
Zero coverage. No journalists, influencers, political figures, activists,
brands, or organizations. These are the false-positive landmines: a brand's
scheduled social output looks automated; an activist campaign looks
coordinated; a newsroom shares a house style. Precision claims do not
generalize to these until we have them.

### Known Uncertain — ambiguous / contested (NO CATEGORY YET)
No dataset and no handling policy. The schema *can* express it
(`AccountLabel.label = "unclear"`, `confidence = "medium"`), but nothing
populates or governs it.

### Excluded (not part of the Trust Dataset)
- **Quarantine (poison):** `bot_detection_data.csv` (random labels),
  `ai_human_detection_v1.csv` (API-error strings).
- **Archive (low value/unverified):** `fake_social_media.csv` (99.8% single
  class), `TwitterData_FE/Joined/Twitter_Data` (3 overlapping unverified-label
  variants), `Twitter_Users`, `location_data`, `ai_vs_human_text`,
  `article_discusses_claim`. The `.xlsx` "best behavioral set" remains
  unreadable until exported to CSV.

---

## 2. Coverage Matrix

| Category | Have? | Platform | Text/history | Label quality | Usable now |
|---|---|---|---|---|---|
| Known Bad — IO/coordination | ✅ strong (8 ops) | Twitter/X | ✅ full | gold (state-attributed) | ✅ validation |
| Known Bad — bots/astroturf | ✅ moderate | Twitter/X, Reddit | profile/label | gold-ish | partial |
| Known Good — humans (profile) | ⚠️ weak | Twitter/X | ❌ no history | good | profile-only |
| Known Good — humans (active+text) | ❌ **missing** | — | — | — | ❌ |
| Known Mixed | ❌ **missing** | — | — | — | ❌ |
| Known Uncertain | ❌ **missing** | — | — | — | ❌ |
| **YouTube (Omi's primary surface)** | ❌ **missing** | — | — | — | ❌ |

**Cross-cutting gap:** all ground truth is Twitter/X (+1 Reddit). Omi runs
coordination detection on **YouTube** comments in production, yet has **zero
labeled YouTube ground truth**. Twitter IO is a strong proxy (same detector
feature space, validated in Tier 2A/2B), but the platform gap should be named.

---

## 3. Gap Analysis (ranked)

1. **Known Good, active-human-with-text — CRITICAL.** Blocks a real FPR proof
   for `style`/`temporal_semantic` and is a hard prerequisite for safe memory
   anchoring. Highest priority.
2. **Known Mixed — CRITICAL for trust.** The precision number that matters is
   precision against *legitimate* high-volume/coordinated-looking accounts, not
   against random humans. Without these, "precision 1.0" is unproven on the
   hardest cases.
3. **Known Uncertain — policy gap.** Need a defined category + handling so
   ambiguous accounts neither inflate nor deflate metrics.
4. **Bot-with-text history — MODERATE.** We have bot *profiles* + IO text, but
   not general (non-IO) bots with rich timelines (cresci tweets JSON lacks
   text).
5. **YouTube ground truth — STRATEGIC.** No labeled YouTube set exists publicly;
   build over time via confirmed channel suspensions (`AccountLabel.source =
   "youtube_suspension"` already modeled).

---

## 4. Acquisition Roadmap

| Pri | Target | Candidate source(s) | Difficulty | Expected value |
|---|---|---|---|---|
| **P1** | Known Good + text | **Cresci-2017 `genuine_accounts` + tweets** (same family as existing bot data; real human timelines + label) | Low–Mod | **High** — fills the #1 gap via the existing adapter path |
| P1b | Known Good realism | Curated `twitterapi.io` pull of unambiguous humans (verified individuals) | Mod (API cost + curation) | High (current-platform realism; vouched, not gold) |
| **P2** | Known Mixed | Curated lists via `twitterapi.io`: journalists, verified orgs/brands, political figures, activist networks; public "verified/VIP" account lists | Mod–High | **High** — the real precision test |
| P3 | Bot + text | Cresci-2017 social-spambots (tweets w/ text); TweepFake (human vs machine text) | Low–Mod | Mod–High |
| P4 | Known Uncertain | Derive: reviewer-disagreement accounts + `activity_botscore` rows near 0.5 margin | Low (derive from owned data) | Mod (calibration stress + active learning) |
| P5 | YouTube GT | Accumulate from confirmed takedowns/suspensions; seed with cross-posted IO accounts active on YouTube | High / ongoing | Strategic (closes the platform gap) |

**Sequencing:** P1 + P2 first (they jointly unlock the FPR proof and the memory
anchoring gate). P3/P4 are cheap follow-ons. P5 is a standing background effort.

**Constraint:** no acquisition has been executed — this phase is the plan.
Downloads/curation begin only on authorization, governed by `manifest.toml`
(new sets land as `validation` until reviewed) and the quality gate.

---

## 5. Expected Evaluation Impact
- **Known Good + text** → first real FPR test of the stylometric/temporal
  detectors on humans; converts "precision 1.0 (structural only)" into a
  defensible end-to-end number; enables a PR curve + threshold calibration with
  confidence intervals instead of point estimates.
- **Known Mixed** → hard-negative precision — the trust-critical metric.
- **Larger, balanced N** → statistical tightness (current eval N = 6/5/3 is
  directional only).

## 6. Expected Memory-Anchoring Impact
Anchoring is fingerprint-space nearest-neighbor onto **confirmed labels**. Its
quality is bounded by the density and breadth of the labeled neighborhood:
- More labeled **humans** + **mixed** accounts → a denser, safer neighborhood →
  recall lift *with* bounded FPR.
- **Known Mixed is essential**: without it, anchoring risks over-flagging
  legitimate high-volume accounts whose fingerprints sit near operational
  clusters. Mixed accounts are the negative anchors that keep anchoring honest.

---

## 7. Memory Anchoring Readiness Gate

Memory anchoring is **NOT** implemented and must not be until **all** of the
following hold. (Refines the Tier-2B Phase-4 assessment into explicit GO/NO-GO.)

### Readiness criteria (all required)
1. **De-circularization designed:** anchor target is `AccountLabel`
   (political_coord/bot → 1.0, human → 0.0), *not* the engine's own
   `last_score`. Self-label leakage guard (an account never anchors to its own
   label).
2. **Known Good + text ingested** with fingerprints, labeled, ≥ ~300 accounts.
3. **Known Mixed ingested** with fingerprints, labeled, ≥ ~100 accounts.
4. **Baseline frozen:** current per-account and coordination P/R/FPR captured
   for an honest before/after.

### Validation requirements (all must pass)
1. **No FPR regression** on Known Good *or* Known Mixed vs baseline
   (leave-one-out / held-out evaluation).
2. **Recall lift demonstrated** on held-out Known Bad (IO) accounts *not* in the
   anchor set.
3. **Fingerprint-collision audit:** quantify humans/mixed within
   `distance_threshold` (0.35) of IO clusters; over-anchor rate below an agreed
   ceiling.
4. **Provenance weighting validated:** `imported_dataset` vs `manual` vs
   `youtube_suspension` weights behave as intended.

### Risk assessment
| Risk | Severity | Mitigation |
|---|---|---|
| Circularity (current `last_score` averaging) | **High** if shipped as-is | switch target to labels |
| Fingerprint collision (human near IO) | Med | distance threshold + Known-Mixed validation (req. P1/P2) |
| Over-anchoring legit high-volume accounts | **High** without Known Mixed | gated on P2 acquisition |
| Label staleness / leakage | Med | self-exclusion + provenance weighting |

**Verdict:** Gate is currently **NOT MET** (criteria 2 + 3 unsatisfied). It
opens after P1 + P2 acquisition.

---

## 8. Known Uncertain — handling policy
- **Represent:** `AccountLabel.label = "unclear"`, `confidence = "medium"`;
  reviewer disagreement (two label rows) auto-marks uncertain.
- **Metrics:** excluded from precision/recall denominators — never rewarded or
  punished on genuinely ambiguous cases.
- **Output:** surfaced as a distinct "review / contested" state, not a confident
  tier; the engine should *express low confidence* here.
- **Use:** active-learning queue (prioritize for human review) and calibration
  stress (a well-calibrated model is uncertain here).

---

## 9. Recommended Next Action
1. ✅ Tier-2B calibration merged (PR #41).
2. **Authorize P1 + P2 acquisition** (Cresci-2017 genuine+tweets; curated Known
   Mixed). These jointly unlock the real FPR proof and the memory-anchoring
   gate.
3. **Hold memory anchoring** until the §7 gate is met.

The objective is to strengthen Omi's relationship with reality before expanding
intelligence further. The foundation is strong on Known Bad, thin on Known
Good, and absent on Known Mixed / Known Uncertain — and that is exactly the
order in which to fix it.
