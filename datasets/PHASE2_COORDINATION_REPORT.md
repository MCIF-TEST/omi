# Phase 2 Report — Real Campaigns Through the Existing Coordination Engine

**Scope (authorized):** route the IO disclosure campaigns + legitimate controls
through the **existing** coordination detectors (`age_cohort`, `style_match`,
`fingerprint_cluster`, `temporal_semantic`, `co_engagement`), preserve Phase 0's
real timestamps, and **measure** precision/recall/FPR + per-detector contribution.
**No new detectors** (per directive). The harness reuses the synthetic
coordination benchmark's machinery (`AccountEntry` → `_run_detectors` →
`aggregate_coordination`) on real accounts.

> Bottom line: the engine **has real recall** on cohesive campaigns (Xinjiang 78%,
> GRU 60%) — and a **catastrophic precision problem**: legitimate human accounts
> score **identically to IO (1.00)**. `fingerprint_cluster` is the only
> discriminative detector; `style_match` + the disjunctive aggregation manufacture
> the false positives.

---

## 1. Coordination Evaluation Results

Each campaign/control = one "scan": real accounts scored through the engine, then
the cross-account detectors + aggregate. Sampled (cap ≤100 accounts/scenario).

| Scenario | kind | n | **agg score** | flagged % | **recall** | **FPR** |
|---|---|---:|---:|---:|---:|---:|
| Russia GRU | IO | 45 | **1.00** | 60% | **0.60** | — |
| Russia IRA (202012) | IO | 22 | 0.34 | 14% | 0.14 | — |
| Iran 092020 | IO | 100 | **1.00** | 20% | 0.20 | — |
| China Xinjiang (CNHU) | IO | 100 | **1.00** | 78% | **0.78** | — |
| China Changyu (CNCC) | IO | sparse | — | — | — | under the ≥3-account / data floor* |
| **CONTROL — TwitterData humans** | legit | 45 | **1.00** | 73% | — | **0.73** |
| CONTROL — independent novelty bots | bots | 47 | 0.33 | 8.5% | — | 0.085 |

\* Changyu's per-year files are tweet-concentrated (a few prolific accounts), so a
sampled slice falls below the detectors' minimum account count — a data-shape
caveat, not an engine result. China is represented by Xinjiang.

**The precision crisis, quantified.** IO scores {1.00, 0.34, 1.00, 1.00} vs the
legitimate human control **1.00**. **At any score threshold the human control is
flagged exactly as hard as a real IO campaign** — campaign-level coordination FPR on
legitimate accounts is effectively **100%**. The earlier text-less Trust-Boundary
"0/14 FPR" was an artifact of `style`/`temporal` abstaining without text; with real
text they fire, and the score no longer separates coordinated from legitimate.

**What *does* separate:** only `fingerprint_cluster` — IO {0.84, 0.59, 0.71, 1.00}
vs humans 0.27, novelty-bots 0.46.

---

## 2. Detector Contribution Analysis

Per-detector, from the aggregate's signed breakdown (score · confidence ·
reliability · positive-evidence), across the scenarios:

| Detector | On IO campaigns | On legit humans | Verdict |
|---|---|---|---|
| **fingerprint_cluster** | 0.59–1.00, real clusters | **0.27, no cluster** | **Strongest — the only discriminator** (recall *and* precision) |
| **style_match** | 1.00 (GRU/Iran/Xinjiang) | **1.00, 5 clusters (73%)** | High recall, **no precision** — the FPR driver |
| **age_cohort** | fired Xinjiang 0.86 (mass-creation); else low/abstain | abstains | Suggestive but sparse; needs creation dates |
| **temporal_semantic_clique** | floored **0.23**, 0 clusters (account-history) | floored 0.23 | **Weakest contribution here**; event-stream probe fired only on Xinjiang (3 clusters, score 0.607, 10 authors) |
| **co_engagement** | **never runs** (no IO engagement analog) | n/a | Structural gap → missing capability |

- **Strongest detector:** `fingerprint_cluster` — separates IO from legitimate.
- **Weakest (precision):** `style_match` — clusters unrelated professional/broadcast
  writers (journalists, politicians) as "same author / coordinated."
- **Weakest (contribution) / redundant:** `temporal_semantic` at account granularity
  — perpetually floored; it is the canonical signal only on *dense comment bursts*
  (the supplementary real-event-stream probe confirms it can fire — Xinjiang — but
  the sampled IO histories rarely have same-120-second near-duplicate posting).
- **Missing capability:** the **IO-native network detector** (co-retweet / co-hashtag
  / co-mention) — the discriminative analog `co_engagement` provides on YouTube,
  which Phase 0's extracted columns (`retweet_userid`, `hashtags`, `user_mentions`)
  would enable; **and** a precision gate (below).

**Confidence behavior.** On real text-rich campaigns every text detector reports
confidence 1.0 (plenty of data); confidence collapses to 0 only on sparse scenarios
(Changyu). Because the aggregate is `max(weighted_mean, corroboration)` and
corroboration is a **noisy-OR that only adds positive evidence**, a *single* confident
detector at score 1.0 (`style_match`, evidence 1.0) drives the aggregate to ~1.0 by
itself. The aggregation that helps *recall* (disjunctive — catch ops that light up
only some lenses) is exactly what converts `style_match`'s non-discrimination into
campaign-level **false positives**.

---

## 3. Precision / Recall / FPR (summary)

- **Recall (IO):** strong on cohesive ops — Xinjiang **0.78**, GRU **0.60**; weaker
  where the sample is small/diverse (Iran 0.20, IRA 0.14). Driven by
  `fingerprint_cluster` + `style_match` clustering.
- **FPR (legitimate humans):** **0.73 at account level, ~1.0 at campaign-score
  level.** Unacceptable as-is. Driven by `style_match`.
- **Precision separation:** none at the aggregate score; **only `fingerprint_cluster`
  is usable as a discriminator** on real data.
- **Good news control:** independent novelty bots (automated but not a campaign)
  correctly score low (0.33, FPR 8.5%) — the engine does *not* mistake lone
  automation for coordination. The failure is specifically **legitimate humans with
  shared professional style.**

---

## 4. What Phase 2 proves

The objective was to prove what the current coordination system can do on real
campaigns. It can:
1. **Detect cohesive state campaigns** — fingerprint + style clustering recovers
   60–78% of members on tight ops (GRU, Xinjiang) with high aggregate score.
2. **Reject lone automation** — independent novelty bots aren't mistaken for a campaign.

It cannot, as-is:
3. **Distinguish a campaign from unrelated legitimate professionals** — humans score
   1.00, identical to IO, because `style_match` is non-discriminative on real text and
   the noisy-OR aggregation amplifies it. **The aggregate coordination score is not
   currently usable for precision; only `fingerprint_cluster` is.**

---

## 5. Recommendation for next action

The measurement points to a clear, ordered Phase 3 — **fix precision before adding
breadth** (and these are builds, not part of Phase 2):
1. **Precision gate on the aggregation** — a single non-discriminative detector
   (`style_match`) must not reach score 1.0 alone; require corroboration from a
   discriminative lens (`fingerprint_cluster` or the new network detector). This
   directly attacks the ~100% campaign-level human FPR.
2. **Build the IO-native network detector** (co-retweet / co-hashtag / co-mention)
   from Phase 0's extracted columns — expected to be discriminative like
   `fingerprint`, and the genuinely missing capability.
3. **Re-weight `style_match`** toward "supporting evidence," not "standalone proof."
4. Only then revisit `temporal_semantic` on real per-tweet event streams (it works on
   dense bursts — Xinjiang — but is starved at account granularity).

These are deferred to Phase 3 authorization. The automation-vs-manipulation and
legitimate-coordination-vs-manipulation boundary is tracked separately
(`TRUST_BOUNDARY_TRACKING.md`, Tier 3B).

---

## 6. Updated roadmap

| Item | Status |
|---|---|
| Phase 0 foundation (real timestamps) | ✅ merged |
| Phase 1 text-bearing validation + free wins | ✅ merged |
| **Phase 2 — IO → coordination engine + measurement** | ✅ **this report** |
| Coordination precision gate / re-weight `style_match` | ⏭ Phase 3 (recommended #1) |
| IO-native network detector (co-retweet/hashtag) | ⏭ Phase 3 (recommended #2) |
| Tier 3B — legitimate automation vs manipulation | 📌 tracked (not implemented) |

### Harness
`app/evaluation/io_coordination.py` (reuses the coordination benchmark machinery) ·
`tests/test_io_coordination.py`. Re-runnable on the real campaigns + controls.

> Phase 2 did its job: it proved the engine has real recall **and** surfaced that its
> aggregate score cannot yet tell a campaign from a newsroom. The next leverage point
> is precision, not more recall.
