# Trust Boundary — Tracked Items

Living register of trust-boundary problems surfaced by evaluation but **not yet
scheduled for implementation**. Each item records current findings, future work,
and expected impact, so the signal is preserved without derailing the active phase.

---

## Tier 3B — Legitimate Automation vs Manipulation

**Status:** Tracked (not implemented). Opened from Phase 1; reinforced by Phase 2.

**The boundary.** Omi's labels and detectors conflate *form* with *intent*. An
account can be **automated** (a bot) or **coordination-shaped** (posts like a group)
without being **manipulative**. The trust verdict that matters is manipulation;
automation and coordination are only proxies — and on real data they misfire in both
directions.

**Current findings (measured):**
- **Phase 1 (single-account):** the TwitterData "bots" are benign novelty automation
  (MuseumBot posts museum art; Horse_ebooks posts surreal text). They carry
  `expected_tier = "high"` (inherited from the binary bot/human convention), but they
  do not manipulate — 21/47 correctly score LOW, which *reads* as a 40% recall miss.
  The label taxonomy, not the engine, is wrong here.
- **Phase 2 (coordination):** the engine **correctly rejects lone automation** as
  coordination — independent novelty bots score 0.33 (FPR 8.5%). But it **falsely
  flags legitimate coordination**: unrelated professional/broadcast humans
  (politicians, journalists) cluster via `style_match` and score **1.00**, identical
  to a real IO campaign (73% account-level FPR). Shared *professional style* is read
  as *coordination*.
- **Net:** two distinct confusions live on this boundary —
  (a) **automation ≠ manipulation** (a scheduled art bot is not a threat), and
  (b) **legitimate coordination ≠ manipulation** (a newsroom house style / on-message
  party is not a hostile operation).

**Future work (when scheduled):**
1. **A manipulation-intent layer** distinct from automation/coordination *shape* —
   keyed on narrative/deception/targeting signals (e.g. `narrative` detector,
   astroturf language, amplification asymmetry), not on similarity alone.
2. **`expected_tier` taxonomy revision** — separate "automated / benign" from
   "manipulative," so benign automation has a truthful target tier and recall numbers
   stop being distorted by it.
3. **A legitimacy prior for coordination** — verified / institutional / public-figure
   cohorts (the `twitterdata_verified_mixed` tag already isolates 14) as a precision
   anchor so legitimate coordination is not scored as an operation.

**Expected impact.** Cuts the dominant false-positive sources on both the
single-account (Phase 1: 24% legit FPR) and coordination (Phase 2: ~73% legit FPR)
paths, and makes the verdict *actionable* — "coordinated **and** manipulative" rather
than merely "looks similar." This is the precision frontier; it gates trustworthy
deployment of both the trust score and the coordination score.

**Related (Phase 2 engineering, recommended for Phase 3, not this item):** a precision
gate on `aggregate_coordination` (no single non-discriminative detector reaches 1.0
alone) and the IO-native network detector — see `PHASE2_COORDINATION_REPORT.md` §5.
Those are mechanism fixes; Tier 3B is the conceptual boundary they serve.
