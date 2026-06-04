# Phase 1 Report — Text-Bearing Validation + Free Wins

**Scope (authorized):** Validation + free wins. The **memory anchoring re-gate is
held** for a separate explicit decision. No coordination detectors touched.
All evidence is from the real on-disk data through the production
discovery → adapter → `ingest_records` → engine → `compute_report` path.

---

## 1. First text-bearing calibration (centerpiece)

**Setup.** `TwitterData_Joined` ingested via the `twitterdata` adapter into a fresh
SQLite DB (`ingest_records`), then scored with the same `compute_report` the CLI and
CI use. This is the **first time Omi has been measured against real, text-bearing
human *and* bot accounts** — the gap every prior phase flagged.

**Result (92 accounts: 47 bot / 45 human):**

| Ground truth | low | moderate | elevated | high | flagged (elev+high) |
|---|---:|---:|---:|---:|---:|
| **human** (expect low) | 13 | 21 | 9 | 2 | **11 / 45 = 24% FPR** |
| **bot** (expect high) | 21 | 7 | 8 | 11 | **19 / 47 = 40% recall** |

Official: **Brier 0.233 · tier-accuracy 26% · macro-F1 0.174** (low P=0.38 R=0.29;
high P=0.85 R=0.23). Detectors now firing on real text (confidence > 0.25):
`semantic` 92, `engagement` 92, `profile` 92, `voice` 71, `ai_writing` 66.

**The finding that matters — text-less evaluation hid the FPR.** The earlier
Trust-Boundary eval reported "coordination FPR = 0/14" on human/mixed groups, but
that was on **text-less** data where `semantic`/`voice`/`ai_writing` *abstained*
(zero confidence). With real text they fire — and reveal that Omi **escalates 24% of
legitimate, active/broadcast accounts** (a politician, journalists, brands; 14 of
these are the verified Known-Mixed cohort). The clean 0% was an artifact of missing
text, not real precision. **This is the single most important thing Phase 1 surfaced.**

**External anchor.** The independent Botometer reference (`activity_botscore`,
11,190 accounts) flags only **11.5%** of a general population as bot-like (mean score
0.183). Omi escalating **24%** of a *legitimate* subset is, against that anchor, a
strong over-flagging signal — the thresholds and the active/broadcast-account
treatment need precision work.

**Honest interpretation (both directions):**
- **Over-flagging legitimate accounts (precision):** active, promotional, broadcast
  voices (politicians/journalists/brands) trip `engagement`/`voice`/`semantic`. They
  are authentic, so these are false positives. This is the Known-Mixed problem, now
  *measurable* for the first time — and the priority it points to is **precision**,
  not more recall.
- **Under-catching benign novelty bots (label nuance):** the "bots" here are
  MuseumBot, Horse_ebooks and kin — automated but **not manipulative**; their text
  isn't spammy/coordinated, so 21/47 score LOW. `expected_tier="high"` (inherited
  from the binary bot/human convention) is arguably too strict for benign automation,
  which depresses the apparent recall. Worth a deliberate decision (next phase): is
  "automated-but-harmless" a HIGH, or its own lower tier?

**Net:** validation did its job — it produced an unflattering, *true* number that
the text-less pipeline could not. Omi's real text-bearing FPR is ~24% on this
legitimate set; that, not recall, is the calibration target.

---

## 2. Free wins (all merged-ready)

| Win | What changed | Effect |
|---|---|---|
| **AI-set salvage** | `_parse_text_detection_v1` skips the ~6 `Error: 4xx Client Error` rows; manifest `quarantine → validation`. | `ai_human_detection_v1` (686 rows) recovered as an AI/human **validation** set instead of discarded for ~1% contamination. |
| **FSM xlsx → csv** | Exported the balanced `fake_social_media_global_2.0` (is_fake **1941/1059**) to CSV; manifest: CSV `train`, xlsx `archive`. | The one **clean balanced** behavioral-feature set is now ingestible (matches `fake_social_media`). |
| **botscore reference** | New `app/ml/datasets/botscore_reference.py` + `datasets botscore-ref` CLI. | External base-rate anchor (**11.5%** bot-like) wired in for tier-threshold sanity checks — already used above. |

---

## 3. What this means (recommendations — not yet implemented)

The validation reframes priorities. Surfacing for decision, not acting (memory + any
threshold/label change are out of this scope):
1. **Precision is the bottleneck, not recall.** The 24% FPR on legitimate accounts is
   the number to drive down — directly relevant to *coordination* (legitimate
   coordination must not trip thresholds).
2. **Re-examine `expected_tier` for benign automation.** A novelty bot ≠ a
   manipulation campaign; forcing it to `high` distorts both recall and the label
   taxonomy. Candidate: a distinct lower-tier expectation for harmless automation.
3. **Thresholds look aggressive vs the external anchor** (24% vs 11.5%). The
   `activity_botscore` reference now exists to calibrate against.
4. **The Known-Mixed cohort is ready.** 14 verified accounts are tagged
   `twitterdata_verified_mixed` — the isolated FPR-guard set for any future precision
   or coordination work.

## 4. Roadmap update

| Item | Status |
|---|---|
| Phase 0 foundation | ✅ merged |
| **TwitterData ingest + text-bearing calibrate** | ✅ **done** — first real FPR/recall measured |
| Free wins (AI-salvage / FSM xlsx / botscore) | ✅ **done** |
| Memory anchoring re-gate | ⏸ **held** (your call) — note: the FPR finding *raises* the precision risk the gate already flagged; seed + re-evaluate only after precision is addressed |
| IO → coordination engine (Phase 2) | 🔓 unblocked by Phase 0; not started |
| Co-retweet / hashtag-sync / attribution | ⛔ held per constraint |

**Assessment:** Phase 1 delivered the validation it promised and the free unlocks.
The headline is a precision problem (24% FPR on legitimate accounts) that text-less
evaluation had hidden — a more useful result than a clean pass. It also *strengthens*
the case for keeping the memory gate closed until precision is addressed: anchoring
on an engine that over-flags legitimate accounts would propagate that error across
scans.

---

### Changed files
- `app/ml/datasets/adapters.py` — `_parse_text_detection_v1` skips API-error rows.
- `app/ml/datasets/botscore_reference.py` — **new** external base-rate reference.
- `scripts/datasets.py` — **new** `botscore-ref` CLI command.
- `datasets/manifest.toml` — AI-set `quarantine→validation`; FSM CSV `train`, xlsx `archive`.
- `datasets/Datasets/.../fake_social_media_global_2.0.csv` — **new** (xlsx export).
- `tests/test_phase1_free_wins.py` — **new**; `test_dataset_governance.py` — salvage assertion updated.

> Validation over vanity: the number that matters is the 24% FPR text-bearing data
> revealed — and the precision work it points to.
