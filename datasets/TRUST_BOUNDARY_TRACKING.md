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

### Phase 3 update — lessons learned

The two mechanism fixes shipped (corroboration gate + `co_tag`; see
`PHASE3_REPORT.md`) and the boundary moved:
- **Legitimate coordination vs manipulation is now separable at the verdict level.**
  Requiring *corroboration by a discriminative lens* cleanly split legitimate humans
  (gated to 0.49) from real campaigns (1.00) — the score-level human FPR went 100% → 0%
  with no recall loss. **Lesson:** "looks similar" (style) is not coordination; a
  *shared-target network* signal (`co_tag`) is, and it is what actually separates
  legitimate from manipulative coordination on real data (IO fires, humans silent).
- **Automation vs manipulation held up:** lone novelty automation still does not
  cluster as a campaign (0.30), confirming the engine isn't conflating the two.

### Remaining risks (post-Phase-3)
1. **Member-level elevation still uncorroborated** — the gate caps the batch verdict,
   but per-account elevation reads each cluster's own score, so a human in a
   `style_match`-only cluster (member FPR ~0.73) could still be elevated individually.
   This is the **highest-priority remaining precision gap**.
2. **No manipulation-intent signal yet** — corroboration separates *coordinated* from
   *not*, but a legitimately coordinated cohort (a campaign team, a newsroom on a live
   story) that *also* trips a discriminative lens would not be distinguished from a
   hostile op. Intent (deception/targeting/narrative) is still unmeasured.
3. **`expected_tier` taxonomy** for benign automation remains unrevised (Phase 1).

### Future work
- **Propagate the corroboration gate into per-account elevation** (closes risk #1; the
  immediate next step recommended in `PHASE3_REPORT.md`).
- **Manipulation-intent layer** (risk #2) — the conceptual core of Tier 3B: separate
  coordinated-and-legitimate from coordinated-and-manipulative using the `narrative` /
  astroturf-language / amplification-asymmetry signals, plus the
  `twitterdata_verified_mixed` legitimacy anchor.
- **`expected_tier` revision** so benign automation has a truthful target tier.

**Expected impact (unchanged, now partly realized):** Phase 3 removed the dominant
*coordination-score* false positives; the per-account propagation + intent layer would
remove the residual member-level ones and make the verdict say *coordinated **and**
manipulative*, not merely *similar*.
