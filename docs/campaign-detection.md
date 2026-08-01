# Coordinated-campaign detection from scores and verdicts

**Status:** designed and implemented (`apps/api/app/campaigns/verdict_coordination.py`), pinned by
`tests/test_verdict_coordination.py` (24 tests). Not yet wired to a route or a UI.

This is the algorithm the `/narratives` placeholder has been waiting for. The campaigns backend was
deliberately kept when the UI was removed (see CLAUDE.md, "The coordinated-events surface is removed
from the product, not from the code") precisely so this could land on top of it: `Campaign`,
`CampaignMember`, `CampaignObservation` and `CampaignService.record_clusters` already model recurring
campaigns, and this module produces the `CoordinationCluster` objects they consume.

Zero external calls at runtime. numpy, scipy, scikit-learn and networkx only, all already core
dependencies.

---

## 0. The problem, stated precisely

Input: a list of `(profile_id, omi_score ∈ [1,100], verdict: str)`. Nothing else. Output: groups that
are running together, a strength score per group, a label, and per-account evidence.

**The input is far richer than "some text".** The verdicts are written under the Master Analyst
Protocol, whose `_CHECKABLE_CLAIMS` block forces structure into every one of them:

> Compute, do not eyeball. State the following-to-followers ratio as a figure, the age in days or
> years, the post count as a number. [...] Quote, do not paraphrase. Any claim about what an account
> wrote carries a short verbatim quote. If you cannot quote it, you cannot claim it.

So each verdict is a small structured record of the account, embedded in prose, **plus the account's
own words in quotation marks**. That last part is the single most valuable signal in the system and
it exists only because the protocol demands it. Anything that weakens the quoting rule weakens this
detector, which is a dependency worth knowing before someone edits the constitution.

### The central trap

One model wrote every verdict in the batch. Therefore:

- Raw TF-IDF cosine between two verdicts mostly measures **the analyst's template**, not the
  accounts. It will happily report that two accounts are coordinated because both verdicts contain
  the word "ratio".
- Worse, the vocabulary is **conditioned on the score**. High-scoring verdicts share "converging",
  "elevated", "thin evidence" *by construction*. A naive method clusters every 80-scorer together
  and reports a campaign that is really just a score band, which is a restatement of the input
  dressed up as a discovery.

Every design decision below follows from one rule:

> **Agreement is evidence only in proportion to how improbable that agreement is under the batch's
> own background distribution, holding the omi score band fixed.**

### Coordination and botness are orthogonal

The system never multiplies coordination by mean omi score. A tight cluster of *low*-scoring accounts
is a real finding (a well-camouflaged network, or a genuine community), and collapsing the axes would
both hide it and let a pile of unrelated high scorers masquerade as an operation. The two numbers are
measured separately and combined only at the labelling step.

---

## 1. Feature extraction

Per profile, parsed with regex and pure Python. No model, no lookup.

| Feature | Source | Why it survives the trap |
|---|---|---|
| `quotes`, `quote_shingles` | text in quotation marks, char 5-shingles | the **account's** words, not the analyst's |
| `numerics` | `ratio`, `followers`, `following`, `posts`, `age_days` | protocol-forced figures; derived ratio when both sides present |
| `cohort` | ISO date or "March 2024" to a `YYYY-MM` bucket | account creation month |
| `handle_skeleton` | username to `a`/`A`/`9`/`_`, runs collapsed | `cryptoalex8837` to `a9` |
| `claim_types` | 15-entry lexicon to a set | *which kinds* of evidence were cited |
| `tokens` | lowercase words | input to the residual view only |
| `band` | `(score - 1) // 20` | the conditioning variable for every null |

On `handle_skeleton`, a caveat that is the constitution's rather than a stylistic one: **trailing
digits are auto-appended by platforms and are never a tell about an individual account.** What this
view claims is different and much narrower: an improbable number of accounts *in one section* sharing
one *uncommon* template. The individual-level claim stays forbidden, and the view weights by batch
rarity so a common template contributes nothing.

---

## 2. Six views, each rarity-weighted

Rather than concatenating features into one vector, the system builds six independent similarity
graphs. Three reasons: per-edge explainability ("linked by quote echo and cohort"), a natural fit
with the existing `CoordinationCluster(method=...)` shape, and it enables the corroboration gate.

| View | Algorithm | Rarity weighting |
|---|---|---|
| `quote_echo` | MinHash + LSH banding over char shingles, verified by Jaccard ≥ 0.62 | identity of text is inherently improbable |
| `numeric_cohort` | robust z (median/MAD, log1p first) then **DBSCAN** | blob rejected if > 40% of batch; cohort match weighted by `1 - p(cohort)` |
| `handle_morphology` | exact skeleton match | weight = surprisal `-log p / log 20`, skipped above 50% frequency |
| `verdict_residual` | TF-IDF, boilerplate stripped, **band-centred**, cosine ≥ 0.34 | the centring *is* the weighting |
| `rationale_shape` | Jaccard over claim-type sets, ≥ 3 shared | inverse-frequency sum over shared claims |
| `score_quantization` | identical scores in a dispersed batch | weighted by `1 - p(score)`; abstains if batch sd < 6 |

**Why DBSCAN and not k-means:** no cluster count needed, and it leaves ordinary accounts as *noise*
instead of forcing everyone into a group. Forcing is how you defame a bystander.

**Why median/MAD and not mean/sd:** a farm in the batch corrupts the mean. Robust statistics are not
optional when the anomaly you are measuring against is inside your sample.

**Why log1p first:** follower and post counts are heavy-tailed; a raw-scale distance is dominated
entirely by whichever account has the most followers.

### The residual view in detail

This is where the trap is defused, in two subtractions:

1. **Boilerplate**: drop any token with document frequency > 0.45. That is protocol scaffolding,
   present regardless of the account. This is a self-supervised stopword list derived from the corpus
   rather than a fixed one, which matters because the scaffolding changes when the constitution does.
2. **Band conditioning**: subtract the mean TF-IDF vector *of the profile's own score band*, then
   renormalise. Analogous to common-component removal in the word-embedding literature and to
   background-subtracted topic modelling. What survives is the part of the wording that the score
   does not already explain.

Step 2 is the load-bearing one. Without it this view reports "all the 80s look alike".

---

## 3. Fusion and community detection

**Fusion is noisy-OR, not a sum**, matching what `app/detection/coordination/aggregate.py` settled on
after the Tier-2B evaluation and for the same reason: coordination is disjunctive. Two accounts
linked by a quote echo *and* a cohort should be more strongly linked than by either alone, saturating
towards 1, with a third weak view unable to add as much as the first strong one did.

```
w(a,b) = 1 - Π over views (1 - weight_view × reliability_view)
```

**Community detection is consensus Louvain.** Louvain maximises modularity, which asks exactly the
right question: is this group denser than the configuration-model null expects? But it is stochastic
and resolution-dependent, and boundaries that move between runs are intolerable when the output is a
published claim about named people. So:

1. run Louvain at 3 resolutions × 5 seeds = 15 partitions,
2. accumulate a **co-association matrix** (how often each pair landed together),
3. keep pairs that co-occurred in ≥ 60% of runs,
4. take connected components of that stable graph,
5. **`k_core(k=2)`** to strip pendant nodes: an account attached by a single edge is a bridge or a
   coincidence, not a participant.

This converts Louvain's instability into a *measured* stability instead of a hidden one. Leiden would
be marginally better but needs `leidenalg`; Louvain ships in networkx.

---

## 4. Significance: the band-preserving permutation test

For each cluster, resample node sets matching its **per-band composition**, recompute mean pairwise
fused weight, and report an empirical p-value. This is the test that stops a score band being
reported as a campaign. Empirical rather than parametric because the weight distribution is nothing
like Gaussian.

### The small-sample trap this hit in development

A stratified permutation test **silently degenerates when a stratum is barely larger than the sample
drawn from it.** In the worked example the campaign occupied 3 of the 3 accounts in its score band,
so every "random" draw *was* the cluster, the null collapsed onto the observation, and a group with
100%-identical quoted text came back at **p = 0.502** and was gated down to `ambiguous`. The
arithmetic was correct. The test had no power and reported that as evidence of nothing unusual.

The fix is a tiered null with an explicit power check (`_null_space` counts distinct possible draws;
below 20 the tier is rejected):

| Tier | Control | Reported as |
|---|---|---|
| `band` | exact score-band composition | strongest |
| `band_adjacent` | each stratum widened to neighbours | "score confound only partly controlled" |
| `unstratified` | draw from the whole batch | "does NOT rule out these being merely the high scorers" |
| `none` | no usable null | `p_value = None` |

**`p_value is None` must never be treated as a high p-value.** It means the question was not asked.
The caller lowers *confidence*, not the score, and the corroboration gate carries the burden instead,
which is the right fallback: it asks for hard-to-fake evidence rather than for statistical power the
batch does not have.

---

## 5. Coordination scoring

Per cluster, measure: `density`, `cohesion` (mean fused weight), `view_multiplicity`,
`discriminative_views` (count), `size_prior` (saturating, `log1p(n-2)/log 25`), and the max strength
of each discriminative view.

Combine with the two-view scheme the engine already uses:

```
weighted_mean  = reliability-weighted mean of density, cohesion, multiplicity, size
corroboration  = 1 - Π over discriminative views (1 - strength × reliability)
score          = max(weighted_mean, corroboration)
```

then apply three gates:

- **Significance**: `p > 0.05` caps at 0.45; `p > 0.20` caps at 0.25. Skipped entirely when `p` is
  `None`.
- **Corroboration**: zero discriminative views caps at **0.49** (top of MODERATE), mirroring
  `SUPPORTING_CEILING` in `aggregate.py`. A cluster held together only by shared reasoning vocabulary
  can raise suspicion, never reach a strong verdict.
- **Untestable**: `p is None` *and* fewer than 2 discriminative views caps at 0.59.

---

## 6. Decision rules

Two axes, `C` = coordination, `B` = botness (**median**, not mean, of member scores, so one 95 among
four 20s does not read as a bot cluster).

| Label | Rule | What it means |
|---|---|---|
| `coordinated_bot_campaign` | C ≥ 0.60, B ≥ 0.55, p significant | the finding |
| `coordinated_authentic` | C ≥ 0.60, B < 0.35 | **real coordination among real people** |
| `coordinated_mixed` | C ≥ 0.60, 0.35 ≤ B < 0.55 | a real community with bots in it, or vice versa |
| `bot_swarm_uncoordinated` | B ≥ 0.70, C low or p high | lots of bots, no evidence they are together |
| `organic_cluster` | p > 0.20 and B < 0.45, or C < 0.35 and B < 0.35 | confident negative |
| `ambiguous` | everything else | genuine uncertainty |
| `insufficient_evidence` | n < 3 | |

Two orderings that matter:

- **`coordinated_authentic` exists because of the constitution's confusable shapes.** Fan
  communities, brands and news feeds genuinely do share vocabulary, join in cohorts and post
  repetitively. Detecting real coordination among real people is a *correct finding*; reporting it as
  a bot campaign is the mistake that defames someone.
- **A confident negative is `organic_cluster`, not `ambiguous`.** "Ambiguous" has to keep meaning
  "we could not tell". Reporting the most reassuring finding in the report as uncertainty wastes it.

**Lone wolves** are profiles with `omi_score ≥ 70` and degree 0 in the corroborated graph after
k-core: obviously bot-like, no evidence of partners.

---

## 7. Cross-investigation, cross-tenant linkage

The requirement is to recognise one operation across different accounts, different investigations and
different OmiSphere customers. Two mechanisms, and the second is the one that actually delivers it.

**(a) Member overlap.** Already implemented in `CampaignService._match_or_create`: Jaccard ≥ 0.30 or
≥ 3 shared accounts against existing `CampaignMember` rows. This links a campaign to itself when the
same accounts reappear.

**(b) Signature linkage.** An operation that rotates accounts between posts shares *no* members with
its own previous run, but it keeps its script, its handle factory and its creation cohort.
`campaign_signature()` builds a 32-permutation MinHash sketch over exactly those discriminative
features and bands it into 8 LSH keys, so matching is an indexed lookup rather than an O(n²) scan.

Measured on disjoint account sets running the same script:

```
same operation, zero shared accounts   -> signature similarity 1.000, 8/8 LSH bands collide
different operation                    -> signature similarity 0.031, 0/8 bands collide
```

**The sketch deliberately excludes profile ids**, so it reveals nothing about who was scanned. Pinned
by `test_a_signature_reveals_nothing_about_who_was_scanned`.

Proposed persistence (not yet built): a `campaign_signature_bands` table of `(band_index, band_key,
campaign_id)`, indexed on `(band_index, band_key)`. On each detection, look up candidates by band
collision, verify by sketch similarity ≥ 0.4, then merge or create.

### Tenancy: the precondition

`Campaign` has no `user_id`, so campaigns are already deployment-global. That is the right technical
answer for cross-customer linkage and it has a policy consequence that must be handled **before** this
ships:

> `GET /v1/campaigns` and `GET /v1/campaigns/{key}` are gated on `require_user` with no admin check
> and no owner filter, and `CampaignDetail.observations[].context_id` carries the post id of the scan
> that produced each observation. Any signed-in customer can therefore enumerate every campaign in the
> deployment and read **which posts other customers scanned**. This is live today; only the deleted
> UI hides it.

Required before wiring this up:

1. Strip `context_id` from any non-admin response, or drop it from the model. It is the only field
   that identifies someone else's investigation.
2. Decide whether the campaign library is admin-only or customer-visible. If customer-visible, it
   must expose aggregates and member handles only, never provenance.
3. Say so in the privacy policy. Cross-customer aggregation is defensible and arguably a product
   strength, but "we do not share your scan history" needs to remain true as written, and today the
   policy does not describe this.

---

## 8. Worked example

11 profiles: a 4-account crypto-promo operation, a 3-account film fan community, 3 ordinary people, a
business account, and one lone-wolf giveaway spammer. Real output from the implementation.

### Extraction (abridged)

```
  u1  band=3  skeleton='a9'      cohort=2024-03  numerics={ratio:21.5, posts:9, age_days:141}
      quotes=['Best signal group on TG, DM for entry, 400% last week']
  u2  band=4  skeleton='a9'      cohort=2024-03  numerics={ratio:19.8, posts:11, age_days:136}
  u3  band=3  skeleton='a9'      cohort=2024-03  numerics={ratio:24.0, posts:8,  age_days:134}
  u4  band=3  skeleton='a9'      cohort=2024-03  numerics={ratio:20.9, posts:10, age_days:139}
  u5  band=1  skeleton='AaAaAa'  cohort=2019-03  numerics={ratio:0.8, posts:3180, age_days:1972}
  u8  band=4  skeleton='Aa_Aa_Aa' cohort=2025-01 numerics={ratio:310.0, posts:220, age_days:12}
  u9  band=0  skeleton='a_a'     cohort=2011-08  numerics={ratio:1.4, posts:8900, age_days:4748}
```

### Result

```
note: 11 profiles, 5 views produced edges
note: graph: 8 fused pairs over 11 nodes

--- CLUSTER 1: COORDINATED_BOT_CAMPAIGN ---
  members      : ['u1', 'u2', 'u3', 'u4']
  coordination : 0.998   botness: 0.785   p=0.027   confidence: 1.0
  views        : quote_echo, numeric_cohort, handle_morphology, rationale_shape
  evidence     : 4 accounts, 100% of possible pairs linked, mean link strength 1.00
  evidence     : permutation test (strata: band_adjacent, 100 possible draws): p = 0.027.
                 score bands widened to neighbours: the exact-band null was degenerate
  evidence     : [quote_echo] quoted text 100% identical, e.g. "Best signal group on TG, DM for
                 entry, 400% last week"
  evidence     : [numeric_cohort] profile shape cluster (age ~138d, ~10 posts, ratio ~21.2),
                 both created 2024-03
  evidence     : [handle_morphology] handle template 'a9' shared by 4 of 11 (36% of the batch)
  evidence     : [rationale_shape] same evidence pattern: new_account, no_bio, promotional,
                 ratio_imbalance

lone wolves : ['u8']
unclustered : ['u5', 'u6', 'u7', 'u9', 'u10', 'u11']
```

Per-account evidence, e.g. for `u1`:

```
- [quote_echo] linked to u2: quoted text 100% identical, e.g. "Best signal group on TG..."
- [quote_echo] linked to u3: quoted text 100% identical
- [numeric_cohort] linked to u2: profile shape cluster (age ~138d, ~10 posts, ratio ~21.2),
  both created 2024-03
- parsed from verdict: age_days=141, posts=9, ratio=21.5
```

**Two intermediate results this walkthrough corrected**, both found by running it rather than by
inspection:

1. The campaign first came back `ambiguous` at p = 0.502, from the degenerate stratified null
   (§4).
2. The six ordinary accounts first came back as a 6-member `coordinated_authentic` cluster, because
   DBSCAN returned the batch's centre of mass ("old, many posts, balanced ratio") as its densest
   region. Fixed by `MAX_COHORT_SHARE`: a cohort larger than 40% of the batch *is* the batch. Fused
   edges dropped from 22 to 8 and the six were correctly left unclustered.

---

## 9. Limitations and failure modes

| Failure | Why | Mitigation |
|---|---|---|
| **A batch that is entirely one operation cannot be scored from within.** Measured: the same 4-account operation scores 0.590 / `bot_swarm_uncoordinated` alone, and 0.998 / `coordinated_bot_campaign` inside a normal section. | Everything is measured relative to the batch. With no background there is no contrast. | Signature linkage (§7) still matches it to a detection made elsewhere: measured similarity 1.000. Do **not** "fix" this by removing the null. |
| Sophisticated operations that vary their copy | `quote_echo` is the strongest view and defeated by paraphrase | `numeric_cohort` and `handle_morphology` survive; add semantic quote similarity (§10) |
| The analyst omits quotes or figures | every discriminative view degrades at once | the batch notes say so explicitly and every cluster is downgraded; do not weaken the protocol's quoting rule |
| Small batches (< ~20) | no null has power; DBSCAN unstable | `p_value = None` is reported honestly rather than faked |
| **Adversarial verdict poisoning** | an operator who knows the lexicon can write bios and posts that suppress `claim_types` overlap or force a common handle skeleton | only the supporting views are cheaply gamed; `quote_echo` requires actually varying the payload |
| Score-band confound | high scorers share vocabulary by construction | band-conditional centring plus band-stratified null; pinned by a dedicated test |
| Thresholds are reasoned, not fitted | no labelled corpus of verdict-only campaigns exists yet | see §10; treat every constant as provisional |
| A platform that auto-assigns handles | `handle_morphology` fires on everyone | frequency cutoff at 50% |

**The honest summary:** this reliably catches low-to-mid-effort operations that reuse copy,
provision accounts in batches, or mint handles from one template. It will not catch a well-run
operation using aged, purchased, individually-written accounts, and it should not be described as if
it does.

---

## 10. Optional enhancements, all pure-algorithm

1. **Semantic quote similarity** without a model: character-level TF-IDF + LSA (`TruncatedSVD`)
   catches paraphrase that shingling misses. scikit-learn only.
2. **Bipartite account-to-post projection** once multiple investigations exist: accounts co-occurring
   across *several unrelated posts* is far stronger evidence than co-occurrence in one. This needs
   only data already in `CampaignObservation`, and it is the highest-value addition on this list.
3. **Temporal recurrence weighting** on `Campaign.observation_count`: a signature seen in five scans
   over three months outranks one seen once.
4. **Bayesian score calibration**: model the batch's omi-score distribution as a two-component
   mixture (EM) and use component membership rather than a fixed 0.55 botness threshold.
5. **Spectral co-clustering** on the account-by-feature matrix as an independent check on Louvain;
   disagreement between the two is itself a useful instability signal.
6. **Benford / digit-frequency analysis** on extracted follower counts. Purchased followers are often
   provisioned in round lots.
7. **A labelled corpus.** The `ml/` pipeline and `datasets/` already exist for exactly this. Every
   threshold here is reasoned rather than fitted, and fitting them against known state-actor
   disclosure archives (which `featured_campaigns.json` already draws on) would be the single biggest
   accuracy improvement available.
8. **Minimum description length** as a principled alternative to the modularity resolution parameter:
   choose the partition that compresses the fused graph best.

---

## 11. Integration checklist

Not done. In order:

1. Close the `context_id` / campaign-enumeration leak (§7).
2. Decide the tenancy policy and update the privacy policy to match.
3. Add `campaign_signature_bands` and the LSH lookup to `CampaignService`.
4. Call `analyze()` after an investigation's analyst assessment completes, on
   `background.submit_slow`, and feed `to_coordination_clusters()` into
   `CampaignService.record_clusters`.
5. Gate on `coordination >= 0.60` **and** a discriminative view, so clean scans cannot manufacture
   campaigns.
6. Build the `/narratives` UI against the real thing.
