# OmiSphere — Gap Execution Notes

> Running log of things worth remembering as we close gaps one at a time.
> Appended after each gap. Not a roadmap — this is the "what changed, what you
> now own operationally, and what we deliberately deferred" record.

**Branch:** `claude/ecstatic-babbage-wu1f4`

Legend for each entry:
- **Shipped** — what now exists in the product.
- **⚙️ Operational** — things that must happen in the *environment* (not code) to get full value. These are on you, not the compiler.
- **🎛 New knobs** — config/flags introduced, and their safe defaults.
- **🧭 Decisions** — choices made and why, so we don't relitigate them.
- **⏳ Deferred / data-dependent** — intentionally left for later, with the trigger that unblocks it.
- **✅ Baseline** — test count after the gap, so a future regression is obvious.

---

## GAP-01 — Ground Truth Dataset  ✅ done

**Shipped**
- Label-aware ingestion: `PublicRecord` carries explicit `label` / `expected_tier` / `campaign_id`; `ingest_records` validates them and writes `AccountLabel`s.
- Synthetic ground-truth corpus generator (`app/ml/datasets/synthetic.py`) — 6 personas incl. the false-positive guards (ESL, AI-assisted-human).
- IO-disclosure adapter — drop a Twitter/X transparency CSV into `datasets/` and it ingests as `political_coord`/high, aggregated per account.
- Distinct `synthetic` label source, excluded from training export by default.

**⚙️ Operational**
- To grow real ground truth: download public IO archives (Stanford Internet Observatory, Twitter/X IO disclosures) and drop the CSVs in `datasets/`, then `python -m scripts.datasets ingest`. *(Requires network — can't be done from the sandbox.)*
- Generate the synthetic regression corpus anytime: `python -m scripts.datasets synthetic --n 60`.
- Operator annotation in-flow (analysts labeling from the threat breakdown, not just the account page) is **not yet built** — labels today come from the account page widget + imports.

**🎛 New knobs**
- `scripts.datasets synthetic` flags: `--n`, `--seed`, `--persona`, `--confidence`, `--dry-run`.

**🧭 Decisions**
- Synthetic data is tagged `source="synthetic"` and **excluded from model training by default** (`include_synthetic=True` to opt in). It's regression ground truth, not real signal.
- IO adapter collapses a user's many tweets into one account scored on its full (deduped, capped-at-50) post history.

**⏳ Deferred / data-dependent**
- Real archive ingestion (network), and in-flow analyst annotation UI.

**✅ Baseline:** 402 backend tests (after the GAP-01 risk fixes).

---

## GAP-02 — Overconfident Composite Scores (signal decorrelation)  ✅ done

**Shipped**
- Decorrelated log-odds aggregation: correlated detectors (`semantic`+`ai_writing`; `temporal`+`engagement`+`coordination`) are discounted so shared evidence isn't double-counted.
- Convergence bonus & single-signal HIGH cap now count **independent axes**, not raw detector counts.
- `ScanResult.score_adjustments` — plain-language record of every adjustment, surfaced in the UI under "How this score was calibrated."
- **Learned correlation model**: `scripts/fit_correlation.py` measures real pairwise detector correlations and writes an artifact the scorer loads; falls back to hand-tuned defaults when absent.
- **Empirical-Bayes shrinkage**: low/no-support cells fall back to the curated prior instead of asserting independence.

**⚙️ Operational  ← most important thing to remember for this gap**
- The learned correlation model is **only as good as the accounts scanned.** Re-run the fitter periodically as real (especially cross-account full-scan) data accumulates:
  ```
  cd apps/api
  python -m scripts.fit_correlation --dry-run     # preview the matrix
  python -m scripts.fit_correlation               # write the artifact
  ```
- The artifact path is `apps/api/models/signal_correlation.json` and is **gitignored** — a dev-fit must not be committed (it would silently change scoring). Deploy it via the environment when you have a validated one.
- `coordination` correlations stay at the curated prior until enough **cross-account full scans** exist (single-account/synthetic data never fires it). Watch `pair_support` in the fitter output to know when a cell is trustworthy.

**🎛 New knobs** (all have safe defaults; out-of-the-box behavior is unchanged)
- `OMI_DECORRELATION_REDUNDANCY_CONTENT` (0.55), `OMI_DECORRELATION_REDUNDANCY_TIMING` (0.65) — `1.0` disables discount for that group.
- `OMI_CORRELATION_MODEL_PATH` (`models/signal_correlation.json`) — where the learned artifact is loaded from.
- `fit_correlation` flags: `--all` (use every scanned account vs. labeled only), `--min-pairs`, `--strength`, `--floor`, `--axis-threshold`, `--shrink-k` (prior pseudo-count, default 30), `--no-prior`, `--dry-run`.

**🧭 Decisions**
- No artifact is committed → default behavior is byte-for-byte unchanged; the learned model is opt-in via the environment.
- `coordination` grouped with the timing detectors **by default**, but the learned model can split it out if the data disagrees — it's no longer a hardcoded assumption.
- Shrinkage starts the learned model *equal to* the curated defaults and moves toward measured reality one well-supported cell at a time.

**⏳ Deferred / data-dependent**
- A fully data-driven matrix (incl. `coordination`) is gated on accumulated cross-account scan volume. Mechanism is done; only the data needs to arrive.

**✅ Baseline:** 429 backend tests, 11 frontend tests, `tsc` clean.

---

## GAP-03 — AI-writing is not evidence of inauthenticity  ✅ done

**Shipped (the demotion)**
- First-class **supplemental signal** concept: `SUPPLEMENTAL_DETECTORS = {"ai_writing"}` in `app/detection/scoring.py`. A supplemental detector is computed and shown for context but structurally excluded from every suspicion path — the weighted log-odds sum, convergence-axis count, single-axis HIGH cap, intent inference, the "why flagged" reasons, the summary's primary-signals line, and the weak-signal penalty. It still rides along in `signals` with its real probability/confidence, stamped `supplemental=True`.
- Intelligence layer: `ai_generation_probability` is now a **contextual** dimension (`DimensionSpec.is_contextual`) — reported and fully explainable, but excluded from the composite omi_score, primary-threat selection, and the top-evidence roll-up. `THREAT_DIMENSIONS` is derived as `is_risk AND NOT is_contextual`. Removed `ai_writing` from `authenticity_score` (penalising AI-assisted phrasing as "inauthentic" was the core harm).
- `weight_ai_writing` default `0.8 → 0.0` as a mechanical backstop; the supplemental exclusion is the authoritative one.
- Frontend: AI generation renders as a neutral "Context · not counted toward risk" section (dashed border), and supplemental signal rows are tagged "context · not scored" and never coloured as risk.

**Shipped (the remaining-risk resolution — rebuild recall the RIGHT way)**
Demoting `ai_writing` unmasked an elevated/high **recall gap** (macro-F1 had fallen to 0.182) because some of the engine's prior recall was `ai_writing` flagging legitimate ESL/formal/Grammarly writers. We rebuilt that recall through legitimate **behavioral** detection instead of stylometric tells:
- **Engagement detector overhaul** (`app/detection/engagement.py`):
  - Combine spam axes **disjunctively** (noisy-OR) instead of a convex weighted-average, so a single blatant behavior (e.g. 100% affiliate links) actually registers instead of being averaged down to ~0.3.
  - Axes are **correlation-grouped** before combining (link + bait + self-promo = one "promotional CTA" group; emoji + bursts = one "emoji-spam" group; shill is its own), each capped at the ELEVATED ceiling — so one promo behavior reads *elevated* and it takes a **second independent axis** to reach *high* (same anti-double-counting principle as GAP-02, applied inside the detector).
  - **New coverage**: follow-bait / DM-bait (`follow me`, `comment 'X' below`, `I'll DM you`), self-promotion / traffic redirection (`link in bio`, `on my channel`, `my course`), and crypto/financial shilling (cashtags + pump language).
  - **Strength-aware confidence**: blatant, consistent spam across even a handful of posts is a confident call, not a low-confidence one gated purely on volume.
  - **Link precision** (false-positive guard): a URL counts toward the spam-link axis only when it's a shortener/affiliate domain or posted alongside promo framing — so journalists/researchers citing `reuters.com` or public documents are **not** flagged.
- **Semantic detector** (`app/detection/semantic.py`): added a **3-gram template-skeleton** supplement (catches "fill-in-the-blank" template spam where one word varies per post — invisible to the 5-gram overlap and understated by the fallback TF-IDF embedder) plus the same **strength-aware confidence**. Stays ~0 on varied human text, so no new false positives.

**🧭 Decisions**
- AI-assisted writing is **not** suspicion evidence and never raises a tier — only context. This is a permanent contract pinned by `tests/test_ai_writing_demotion.py`.
- Recall is recovered through **observable behavior** (promo/bait/shill/templating), never by reinstating stylometric AI tells.
- The single-axis HIGH cap (GAP-02) is **not** weakened. A pure single-axis case (e.g. an account whose only anomaly is templated comments) is intentionally capped at ELEVATED; lifting those to HIGH is owned by the confidence-calibration gap, not by content-style detection.

**🎛 New knobs**
- None added as config. Engagement thresholds/slopes and the group-ceiling (0.72) are in-code constants with documented rationale.

**📊 Benchmark impact** (seed_v1, fallback embedder — deterministic, matches CI)
- Brier `0.1107 → 0.0588`, tier accuracy `0.415 → 0.646`, macro-F1 `0.182 → 0.583` — macro-F1 now **far above** the pre-GAP-03 0.230, achieved without the harmful signal.
- **Zero** new false positives on the clean/ESL/edge/human archetypes (journalist-with-links and genuine-crypto-discussion are explicit regression guards).
- Gates ratcheted in `tests/test_evaluation_benchmark.py`: `GATE_MAX_BRIER 0.120 → 0.070`, `GATE_MIN_ACCURACY 0.38 → 0.60`, `GATE_MIN_MACRO_F1 0.17 → 0.52`.

**⏳ Deferred / out-of-scope (owned by later gaps)**
- The residual benchmark misses are **temporal / profile / coordination / voice** archetypes (scheduler bots, profile-age cohorts, light astroturf, broadcast voice). Those are systematic under-confidence in *other* detectors and belong to **GAP-05 (confidence calibration)** and **GAP-07 (community anchor / false positives)** — deliberately not touched here to avoid destabilising GAP-02's decorrelation/cap work.
- Two template archetypes still under-shoot on tier because they're genuinely single-axis (semantic only) and the GAP-02 corroboration cap holds them below HIGH — correct by design; tier recovery there is a GAP-05 calibration question.

**✅ Baseline:** 467 backend tests (8 new engagement/semantic hardening tests + ratcheted gate).

---

## BILLING-01 — Batch-based scan credit pricing  ✅ done

**Shipped**
- `compute_scan_credits(platform, max_commenters, settings) → int` in `app/core/auth.py`.
  Formula: `ceil(max_commenters / scan_batch_unit) × credits_per_batch[platform]`, minimum 1.
- Wired into all batch-scan endpoints: `scan_link`, `scan_youtube_video`, `scan_youtube_video_full`, `scan_comprehensive_endpoint`. `scan_youtube_account` stays at 1 credit (single-account, not a batch).
- Error-path refunds in `_handle_youtube_error` now pass the computed cost, so refunds match what was actually charged.
- 15 unit tests (`tests/test_batch_pricing.py`) covering YouTube/Twitter math, edge cases, and formula regression guard.

**🎛 New knobs** (all in config, safe defaults)
- `OMI_SCAN_BATCH_UNIT` (50) — commenters per billing unit.
- `OMI_CREDITS_PER_BATCH_YOUTUBE` (1) — credits per 50 YouTube commenters.
- `OMI_CREDITS_PER_BATCH_TWITTER` (10) — credits per 50 Twitter commenters.

**🧭 Decisions**
- YouTube is cheap (free quota), so 1 credit/50 is essentially unchanged from the old flat rate for most scans (≤50 commenters = 1 credit, ≤100 = 2 credits).
- Twitter is metered at $0.005/read; 50 commenters × 10 posts of history ≈ $3.50 cost; 10 credits × $0.50/credit = $5.00 revenue → ~30% margin.
- Unknown platforms fall back to the YouTube rate (conservative, not penalizing).

**✅ Baseline:** 482 backend tests.

---

## GAP-04 — Hybrid operation detection  ✅ done

**Shipped**
- **Narrative detector** (`app/detection/narrative.py`) — new detector scanning for political/disinformation astroturf language drawn from public IO disclosures (Twitter/X transparency reports, DFRLab, Stanford IO Observatory). 11 compiled regex patterns covering: mainstream-media delegitimisation, establishment fear-framing, amplification CTAs ("spread this everywhere before they delete it"), deep-state/globalist conspiracy markers, media-corruption tropes, hidden-truth framing, DYOR, silencing/censorship claims, narrative-collapse celebration. Probability: logistic on the fraction of posts containing markers (centred at 30%). Confidence: product of absolute count and corpus-size components — a single suspicious post on a tiny account doesn't look like an operation.
- **Voice broadcast exception** (`app/detection/voice.py`) — zero first-person pronouns across a non-trivial corpus (≥ MIN_WORDS_FOR_VOICE) now triggers a confidence boost via the broadcast exception, even when individual posts are short. The existing `length_factor` guard was calibrated for conversational text, not news-brief summaries; broadcast accounts are intentionally impersonal. Confidence now scales from 0.35 to 0.75 with corpus size.
- **Profile fresh-account compound signal** (`app/detection/profile.py`) — `_fresh_account_signal()` fires on accounts <90 days old that exhibit a cluster of ≥2 suspicious attributes: auto-generated handle (long numeric tail), sparse social graph (<10 total connections), and minimal bio (<3 words). Any single attribute on a new account is too common to signal on; the cluster is not. Returns up to 0.90 suspicion for the full three-attribute pattern.
- **Temporal strength-aware confidence** (`app/detection/temporal.py`) — machine-precision scheduling (CoV < 5%) is essentially impossible in human posting (requires machine-controlled interval timing). When CoV < 0.05 AND cov_prob ≥ 0.90, confidence is boosted to 0.25–0.60 regardless of post count. Typical automated content bots with Gaussian jitter (CoV ≥ 0.10) are NOT boosted — keeping them at MODERATE as expected.
- **Single-axis cap fix** (`app/detection/scoring.py`) — the "no HIGH without corroboration" cap now counts only *suspicious* confident signals (probability > 0.40 AND confidence > 0.30) as independent axes. Previously, clean-scoring high-confidence detectors (e.g. engagement p=0.000 conf=0.320) were falsely counted as axes and bypassed the cap, allowing single-axis accounts to reach HIGH.
- **Narrative wired into the engine** (`app/detection/engine.py`, `app/detection/scoring.py`, `app/detection/correlation.py`) — `analyze_narrative` added to `analyze_account`; weight 0.8; added to `_WEAK_REASON`, `_DETECTOR_HEADLINES`, `_infer_intent` (coordinated_campaign path); added to `DETECTORS` tuple in the correlation module.
- **23 new detector tests** (`tests/test_gap04_detectors.py`) covering all four improvements end-to-end.

**📊 Benchmark impact** (seed_v1, fallback embedder)
- Brier `0.0588 → 0.0345` (**41% improvement** — by far the largest single-gap improvement).
- Macro-F1 `0.583 → 0.588` (slight improvement; narrative catches astroturf archetypes).
- Tier accuracy `0.646 → 0.631` (slight dip — explained by the single-axis cap fix correctly classifying `engagement_farm_high` as ELEVATED rather than HIGH; one suspicious axis alone should be ELEVATED, not HIGH).
- Gates ratcheted in `tests/test_evaluation_benchmark.py`: `GATE_MAX_BRIER 0.070 → 0.045`, `GATE_MIN_ACCURACY 0.60 → 0.62`, `GATE_MIN_MACRO_F1 0.52 → 0.57`.

**🧭 Decisions**
- Narrative patterns are conservative by design: each pattern requires the characteristic *combination* of phrases that makes them specific to influence operations (not just any reference to "media"). Single incidental occurrences never raise confidence above 0.15.
- The CoV < 0.05 threshold for temporal boosting was chosen because 5% interval variation requires sub-minute scheduling precision — humans on any posting platform never achieve this. The threshold is deliberately NOT applied to typical automation (CoV 0.10–0.50) to avoid false positives on podcast auto-posts or social media schedulers with natural jitter.
- The fresh-account signal requires ≥2 attributes. A new account with only a numeric handle, or only no followers, is common enough (new users, dormant early adopters) to be benign. The three-attribute cluster is the sockpuppet setup pattern.
- The single-axis cap change is a **bug fix**, not a policy change. The original intent was "HIGH requires multiple independent axes." The old implementation was incorrectly counting clean detectors as axes.

**🎛 New knobs** (all in config with safe defaults)
- `OMI_WEIGHT_NARRATIVE` (0.8) — weight of the narrative detector in the composite.

**⏳ Deferred**
- The `engagement_farm_high` benchmark case now lands at ELEVATED (probability 0.740) because engagement is the only suspicious axis. This is correct by the single-axis policy. Reaching HIGH would require a second independent signal — e.g. coordination evidence from a cross-account scan, or profile signals. That is owned by GAP-10 (cross-account) and GAP-07 (community anchor), not this gap.
- Narrative patterns are English-only. Multi-language astroturf detection is out of scope for this gap.

**✅ Baseline:** 505 backend tests (23 new GAP-04 detector tests, ratcheted benchmark gate).

---

## Cross-cutting things to remember

- **Push flow:** pushes go to `claude/ecstatic-babbage-wu1f4`. (The sandbox proxy blocks push; a PAT is used transiently and the proxy remote restored immediately — never committed.)
- **Pre-existing lint:** there are two pre-existing `ruff` E741 (`l` variable) findings in `scripts/datasets.py` and `app/routes/scan.py` that predate this work; left untouched to avoid scope creep.
- **Test commands:** backend `cd apps/api && python -m pytest -q`; frontend `cd apps/web && npx vitest run && npx tsc --noEmit`.
- **Gitignored artifacts:** `apps/api/models/signal_correlation.json` (fitted model) — environment-specific, never commit a dev fit.
