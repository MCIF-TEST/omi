# Phase 0 Report — Trustworthy Temporal Foundation + TwitterData Rehabilitation

**Authorization:** Phase 0 GO. Scope limited to foundations; co-retweet /
hashtag-sync / campaign-attribution intentionally **not** started (per constraint).
All evidence below is from the **real on-disk data** through the **production**
discovery → adapter → coalesce → detector path.

---

## 1. Timestamp Foundation Report

### Previous behavior (the defect)
`_to_posts` (`app/ml/public_import.py`) assigned **synthetic** timestamps to every
imported post:
```python
base = now - 30d
created_at = base + timedelta(hours=i)   # one post per hour, forever
```
`PublicRecord.texts` was `list[str]` with **no timestamp channel**, so the real
`tweet_time` (IO) and `Tweet_created_at` (TwitterData) columns were **discarded at
the adapter boundary**. Every imported account — IO, bot, human — received an
identical, perfectly periodic, 24/7 cadence.

### Why it mattered — measured, not assumed
Run `analyze_temporal` over the synthetic cadence vs the real one (19 TwitterData
accounts, ≥8 posts):

| | interval_cov | temporal probability | confidence | distinct prob values |
|---|---|---|---|---|
| **Synthetic (old)** | **0.000** (perfectly regular) | **0.87** (looks automated) | 0.60 | **1** (identical for all) |
| **Real (new)** | 0.47 – 6.64 | mean **0.19**, range 0.04–0.40 | 0.25 | **14 / 19** |

The synthetic stamps were **not neutral** — they injected a uniform *"perfectly
regular, never sleeps → 0.87 automated"* signal into **every** account, bot and
human alike, with **zero discrimination** (one distinct value). The aggregate's
single-axis cap (`scoring.py:183-199`) muted the net verdict when temporal fired
alone — which is why prior Trust-Boundary overalls stayed low — but the temporal
axis itself was biased and non-discriminative, and would **compound** the moment a
second axis co-fires (exactly what TwitterData's real text now makes happen).

### Corrected behavior
- `PublicRecord` gains `post_times: list[datetime | None]`, **index-aligned** with
  `texts` and preserved through `coalesce_records`.
- A shared, tolerant `parse_datetime` (`normalize.py`) reads every corpus format
  (IO `2019-10-23 06:05`, IO creation `2019-10-21`, TwitterData day-first
  `27-11-2016 06:15`, ISO-with-seconds, Twitter-API long form) → tz-aware UTC.
- `io_disclosure` now emits real `tweet_time` per post **and** real
  `account_age_days` from `account_creation_date`.
- `_to_posts` uses the real time when present; synthetic spacing remains **only**
  as a per-post fallback (legacy behavioral-only datasets are unchanged).

**Net:** real tweet timestamps, real temporal ordering (temporal sorts by
`created_at`), and real cadence now flow end-to-end. Synthetic generation is
eliminated wherever real timestamps exist.

---

## 2. TwitterData Rehabilitation Report

A new `twitterdata` adapter ingests the corpus the audit recovered, fixing every
defect it identified:

| Requirement | Fix |
|---|---|
| **Correct label polarity** | `Label 1 = human, 0 = bot` (inverted vs convention). The adapter owns this mapping; the generic adapter would have read `1`→inauthentic and mislabeled all 92 accounts. Verified on real data: @SadiqKhan→human, @MuseumBot/@Horse_ebooks→bot. |
| **Normalize corrupted text** | `_strip_bytes_repr` unwraps the `b'...'` `str(bytes)` artifact (present in `Twitter_Data.csv`). |
| **Preserve account identity** | Group by `Twitter_Account` → tweets collapse to one deep-timeline account. |
| **Preserve timeline** | Real `Tweet_created_at` → `post_times` (100% coverage measured). |

**Governance:** `TwitterData_Joined.csv` (richest: clean text + `Verified` +
`Followers`) promoted `archive → validation`; `TwitterData_FE`/`Twitter_Data` stay
archived so the same 96 accounts aren't triple-counted.

### How Omi should use it
| Use | Plan |
|---|---|
| **Training** | 92 accounts × deep timelines → per-account tuning of `semantic`/`voice`/`temporal`; **not** bulk ML (account-N too small). |
| **Validation** | First **text-bearing both-class** `calibrate --from-db`: do bots tier up, humans stay low — with real text *and* real cadence. |
| **Trust-dataset** | Fills Known-Good-with-text **and** Known-Bad-with-text at once. |
| **Known-Good** | The 45 human accounts → human-baseline neighbor set. |
| **Known-Mixed** | The **14 verified accounts** (tagged `twitterdata_verified_mixed`) → FPR guard cohort. |
| **Memory-validation** | Text makes fingerprints discriminative → seed the neighbor store and re-run `memory_benchmark` against the gate. |

---

## 3. Validation Results (real on-disk data, production path)

| | TwitterData_Joined | IO: Iran 092020 |
|---|---|---|
| adapter / supported | `twitterdata` / ✅ | `io_disclosure` / ✅ |
| rows → accounts | 279,691 → **92** | 2,450 → **104** |
| account labels | **47 bot / 45 human** (balanced) | 104 political_coord |
| Known-Mixed tagged | **14 verified** | — |
| **real-timestamp coverage** | **100%** (4,575/4,575 sampled) | **100%** (1,322/1,322) |
| date range | **2010-05 … 2018-12** | **2020-01 … 2020-07** |
| temporal prob — REAL vs synthetic | mean **0.19** vs 0.87 | mean **0.19** vs 0.87 |
| interval_cov — REAL vs synthetic | 0.79–6.64 vs **0.000** | 0.47–3.19 vs **0.000** |
| polarity spot-check | @SadiqKhan=human, @MuseumBot=bot ✅ | n/a |

**Conclusions demonstrated:**
1. **Timestamps are real** — 100% coverage, real multi-year date ranges, parsed from the source columns.
2. **Temporal features operate on real data** — per-account `interval_cov` now varies across two orders of magnitude (was a constant 0.000); probabilities take 14 distinct values where the synthetic path had 1.
3. **TwitterData ingestion functions correctly** — balanced 47/45 across 92 deep-timeline accounts, correct inverted polarity on real accounts, cleaned text, real timeline, Known-Mixed cohort isolated.

*(Test coverage: `tests/test_timestamp_foundation.py` — parsing, real-vs-synthetic
`_to_posts`, coalesce alignment, the temporal reality check, polarity, b''-strip,
routing/no-collision. Full suite: see commit.)*

---

## 4. Expected Impact on Coordination Detection

Phase 0 does **not** add coordination detectors (deferred by constraint) — it makes
the existing ones *trustworthy*:
- **`temporal_semantic_cliques`** keys coordinated bursts on a 120-second window of
  `created_at`. On synthetic 1-hour stamps that window was meaningless; on **real
  `tweet_time`** it can now find genuine same-minute coordinated bursts across IO
  accounts. **This is the prerequisite that makes Phase 2's IO→engine routing real.**
- **`age_cohort`** consumes account-creation dates; `io_disclosure` now supplies the
  real `account_age_days`, enabling mass-creation-window detection on the campaigns.
- Real per-account cadence variance is the substrate temporal coordination compares
  *across* accounts — impossible when every account shared one fabricated cadence.

**Net:** the coordination engine's temporal and cohort inputs are now real; routing
the IO campaigns into it (Phase 2) will produce meaningful — not fabricated — signal.

## 5. Expected Impact on Memory Readiness

The anchoring gate is **NOT MET** because profile-only fingerprints are
non-discriminative (TRUST_BOUNDARY.md). Phase 0 moves two of the gate's blockers:
- The fingerprint's **temporal dims** (`interval_cov`, `burst_ratio`,
  `quiet_hours`, `peak_hourly_rate`) were computed from synthetic cadence →
  identical across accounts → non-discriminative. With real timestamps they now
  **carry real signal** and vary per account.
- **TwitterData provides text-bearing Known-Good + Known-Bad** fingerprints — the
  exact anchor set the gate said was missing.

**Next (Phase 1 memory step, not yet done):** ingest TwitterData + cresci, seed the
neighbor store, re-run `evaluation/memory_benchmark.py`, and re-decide the gate.
Phase 0 makes that re-evaluation meaningful; it does not itself flip the gate.

## 6. Updated Roadmap Assessment

| Roadmap item | Status after Phase 0 |
|---|---|
| P0 Timestamp foundation | ✅ **Done** (this report) |
| TwitterData rehab (adapter) | ✅ **Done** — ingests via `twitterdata`, validated |
| TwitterData ingest→DB + `calibrate --from-db` | ⏭ **Next** (Phase 1) — run the first text-bearing calibration |
| Memory re-gate | ⏭ Phase 1 — seed store + `memory_benchmark` |
| Free wins (FSM xlsx / AI-salvage / botscore) | ⏭ Phase 1, parallel |
| IO coordination extraction + campaign-scan | 🔓 **Unblocked** — temporal/cohort inputs now real (Phase 2) |
| Co-retweet / hashtag-sync / attribution | ⛔ Held per constraint until foundations land |

**Assessment:** the critical-path prerequisite (P0) is complete and *verified on real
data*. The temporal layer is no longer fabricated; the highest-value text corpus is
ingestible with correct semantics. The roadmap's sequencing holds — proceed to the
Phase 1 validation/memory steps next, then the IO coordination routing.

---

### Changed files
- `app/ml/datasets/normalize.py` — `parse_datetime`, `days_since`.
- `app/ml/public_import.py` — `PublicRecord.post_times`; real-timestamp `_to_posts`; aligned `coalesce_records`.
- `app/ml/datasets/adapters.py` — `io_disclosure` real time+age; new `twitterdata` adapter (inverted polarity, b''-strip, Known-Mixed tag).
- `datasets/manifest.toml` — `TwitterData_Joined` → validation.
- `tests/test_timestamp_foundation.py` — new.

> Foundation first: real time, real cadence, correct labels — *before* expansion.
