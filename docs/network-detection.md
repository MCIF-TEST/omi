# Coordinated network detection: architecture and algorithm

**Status: design. Nothing here is built yet.** Written 2026-08-20.

The ask: stop scoring accounts one at a time and start detecting *networks* — moderate, elevated and
high accounts pushing the same topic in the same window, with anomaly and spike detection on top.

---

## 1. What already exists, so we do not rebuild it

| Module | Does | State |
|---|---|---|
| `app/campaigns/detector/` | Cohort coordination over one investigation. 7 signals in 5 independent families, fused into a calibrated posterior against a stated prior (0.033). Real timestamps. | **Live**, both passes |
| `app/campaigns/tracking/` | `CoordinationEdge` accumulation across scans, discounted for context correlation. Operation signatures that survive account rotation. | **Live** |
| `app/detection/coordination/` | Six per-scan detectors feeding OmiScore. | **Live** |
| `app/narrative/` | Semantic clustering of comments into narratives, plus a coordination scoring layer with burst and entropy signals. | **Live but compromised** (§2) |
| `app/campaigns/verdict_coordination.py` | 1,148 lines. Clusters accounts from OMI scores + analyst verdicts alone, with score-band-conditional background subtraction and a permutation test. | **Written, never wired** |

The fusion framework is the important asset. `probability.py` already multiplies likelihood ratios
across *independent evidence families*, and `types.METHOD_FAMILY` is the independence assumption
written down. **A topic dimension should become a sixth family inside that framework, not a parallel
system.** Everything below is designed around that.

---

## 2. Three findings that block the ask as stated

### 2a. Production has no real embedder, so "same topic" currently means "same words"

`render.yaml` builds with `pip install -e .[youtube,postgres]`. The `[ml]` extra that carries
`sentence-transformers` is **not installed**. `get_embedder()` therefore falls back to
`HashingEmbedder`, whose own docstring says it "will NOT catch paraphrases."

So today's narrative clusters are lexical, not semantic. Two accounts pushing one narrative in
different words do not cluster, which is exactly the case a network detector exists to catch.

**Fix: an embedding API, not the local model.** Shipping `sentence-transformers` means torch, about
800 MB, on a Render starter instance. Measured against the alternative: a 100-account scan produces
~2,000 texts at ~50 tokens each, so ~100k tokens. At commodity embedding pricing (~$0.02/1M) that is
**$0.002 per scan**. The API is three orders of magnitude cheaper than the RAM.

### 2b. The narrative store records when we SCANNED, not when they POSTED

`NarrativeService.ingest_batch` writes `observed_at=now` for every row in the batch. Every temporal
signal computed over that column — `_temporal_burst`, `_timing_entropy_anomaly`, the propagation
timeline, `amplification_bursts` — is therefore measuring the scanner, not the accounts. Every
member of one scan is a perfect burst by construction.

This is a live defect in the existing narrative coordination layer, independent of this design.
`CommenterScanResult.thread_comments` and `FullVideoScanResult.thread_arrivals` already carry real
timestamps; the narrative ingest simply does not use them.

**Nothing in this design may key on `observed_at` until it holds the post time.**

### 2c. The verdict miner is written and unwired

`verdict_coordination.py` is the module that already answers "which of these accounts are running
together, from the analyst's own output". CLAUDE.md records why it was not adopted: every
measurement in it is *relative to the batch*, and the cohort detector's 70+ filter removes the batch.
That objection does not apply to a topic-window cohort, which is not score-filtered. It is the
natural home for the analyst-derived half of this system.

---

## 3. Architecture

Five layers. Each one is independently useful and independently testable.

```
  scan ──► L1 utterances ──► L2 topic assignment ──► L3 topic-window baseline
                                     │                        │
                                     ▼                        ▼
                            L4 narrative family ────► L5 spike + linkage
                              (pairwise LR)            (topic-level alert)
                                     │                        │
                                     └──► probability.py ◄─────┘
                                          (existing fusion)
```

### L1. The utterance

The unit of analysis, and it does not exist yet. One row per
`(account, parent_post, topic, posted_at)`.

Built from data already collected and currently discarded at this level: `thread_comments` carries
what an account said **on the scanned post** with a real timestamp, and `recent_activity` carries its
own timeline. Both are already in `payload_json`.

Storing utterances separately from `NarrativeMembership` is deliberate: memberships are per-comment
and unbounded; utterances are the deduplicated, timestamped, topic-tagged spine the rest of the
system queries.

### L2. Topic assignment

Embed each utterance, assign to a topic centroid (the existing `clustering.best_match` is the right
algorithm, it just needs real vectors). Two additions:

- **Topic from the analyst's quotes, not only raw text.** The protocol forces a verbatim quote into
  every claim about what an account wrote. Those quotes are pre-selected as the *characteristic*
  thing the account said, which is a cleaner topic signal than a comment corpus containing "great
  video".
- **Intent as a second axis.** `suspected_intent` is already produced per account. Topic ∧ intent is
  a stronger co-occurrence than topic alone.

### L3. The baseline

Per topic, per time bucket, maintain: utterance volume, distinct accounts, **tier mix** (share at
moderate or above), and **novelty** (share of accounts never previously seen on this topic).

Tier mix is the load-bearing statistic and the reason this design works. A genuinely viral topic
recruits a *representative* sample of accounts, so its tier mix stays near the corpus base rate. A
pushed topic recruits a *biased* sample. Volume alone cannot tell those apart; tier mix can.

### L4. The narrative evidence family

A new pairwise family, `FAMILY_NARRATIVE`, with one method: `narrative_cooccurrence`.

### L5. The spike detector

A topic-level alert, not a pairwise edge. Feeds `/narratives` (already the admin coordination queue)
and the existing `Alert` table.

---

## 4. Algorithm

### 4a. `narrative_cooccurrence` (pairwise, joins the fusion)

Accounts *a* and *b* co-occur when both produced an utterance on topic *T* inside window *W*
**on different parent posts**.

The different-parent rule is the whole signal. Two accounts commenting on the same post about that
post's topic is guaranteed and worth nothing; the same topic reached on *different* posts inside a
short window is the discriminative event. This mirrors `co_target` exactly, and the tracking layer's
existing "only a distinct post counts" rule.

Likelihood ratio, data-derived per observation exactly as `burst_lockstep` and
`provisioning_window` already are:

```
p_null = P(two independently-behaving accounts both touch T in W on different posts)
       = estimated from the empirical marginal rate of topic T over the trailing baseline,
         EXCLUDING window W
LR     = min(CAP, 1 / p_null)
```

Three guards, each inherited from a mistake the existing detector already paid for:

- **Never count the cluster in its own background.** `stats.local_rate`'s `exclude` argument exists
  because a burst that inflates the distribution it is tested against hides itself. Same here.
- **Cap the LR at ~2.0.** The null cannot see an external referral: a news event, a Discord link, a
  trending push makes real strangers converge on a topic, and that is precisely the deviation this
  measures. The cap is where the unmodelled confound is priced in.
- **Platform-neutral, so it may create cross-platform edges** (`PLATFORM_NEUTRAL_FAMILIES`). A
  narrative crossing platforms is one of the strongest available signals and text/network/timing are
  already admitted for exactly that reason.

### 4b. The spike test (topic-level)

For topic *T* and window *W*:

```
n  = distinct accounts with an utterance in (T, W)
k  = of those, how many scored MODERATE or above
p̂  = moderate+ rate across the whole scored corpus over a trailing 30 days,
     EXCLUDING W
significance = -log10 P(X >= k)  where X ~ Binomial(n, p̂)
```

Then two multipliers, both required before anything is reported:

- **Novelty** — the share of those *k* accounts never previously seen on *T*. An organically hot
  topic is discussed by the people who always discuss it; a pushed one recruits new mouths.
- **Linkage** — the density of existing `CoordinationEdge` posteriors *among those k accounts*,
  against the corpus-wide edge density.

**Linkage is the condition that makes this a network detector rather than a topic thermometer.**
Topic co-occurrence alone says "a lot of suspicious accounts are here," which is often true and
innocent (bots cluster on crypto because humans do). Topic co-occurrence *plus* mechanical linkage
says "these specific accounts are running together, and here is the topic they are running on."

### 4c. Refusals, stated up front

A topic-window is refused, not reported, when any of these hold:

| Refusal | Why |
|---|---|
| Fewer than 2 distinct parent posts | A single post is not a network, it is a comment section |
| Fewer than 2 distinct investigations | One customer scanning three posts on one topic manufactures the concentration |
| `n` below ~8 | The binomial tail is meaningless on tiny samples |
| Linkage at or below corpus baseline | Suspicious accounts sharing an interest is not an operation |
| Topic is a platform artifact | Auto-generated text ("I just earned a badge") clusters perfectly and means nothing |

---

## 5. What this cannot see, and the bias in it

**The corpus is not a sample of the platform.** We score the accounts customers chose to scan. So
`p̂` is "the moderate+ rate among accounts our customers look at," not a platform rate. That makes
the test valid for a *relative* claim — this topic is anomalous against our own corpus — and invalid
for any absolute statement about the platform. Reports must say so.

**It cannot see a slow network.** Every signal here is co-occurrence inside a window. An operation
that posts once a week each, on topic, from aged accounts, is invisible to this and to the existing
detector.

**Topic drift.** A centroid updated as a streaming mean will wander. A topic that starts as "election
integrity" and drifts into "voting machines" reports as one topic; splitting it needs periodic
re-clustering, which is deferred.

**The analyst's separation must hold.** The engine sends the analyst an evidence bundle and nothing
else — no engine scores, no tiers, no coordination findings. This design only ever consumes the
analyst's OUTPUT downstream, which is what the cohort detector's pass 2 already does. Nothing here
may feed back into what the model sees, or the anchoring the protocol forbids arrives by the back
door.

---

## 6. Build order

Each step ships something usable and nothing depends on a later step.

1. **Fix the timestamp.** `ingest_batch` writes the real post time. Unblocks every temporal signal in
   the narrative layer, which is currently measuring the scanner.
2. **Real embeddings** behind the existing `Embedder` protocol, via API. Provider-agnostic, falls
   back to `HashingEmbedder` when unconfigured so nothing breaks.
3. **The utterance table** and its backfill from stored `payload_json`. Read-only, no behaviour
   change, and it makes everything after it queryable.
4. **L3 baselines** as a scheduled rollup. Still no detection: just the counters, visible to admins.
   Watch them for a week before trusting a threshold.
5. **`narrative_cooccurrence`** as the sixth family. Small, testable, and it improves the existing
   detector on day one.
6. **The spike detector** and its alerts into `/narratives`.
7. **Wire `verdict_coordination`** against topic-window cohorts, which is the input it was written
   for and never got.

**Steps 4 and 6 are where calibration has to be earned rather than reasoned.** Every threshold in the
existing detector is reasoned rather than fitted, because no labelled corpus exists. The dismissals
on `campaign_detections` are the only ground truth that will ever accumulate, and this system should
record its own the same way.
