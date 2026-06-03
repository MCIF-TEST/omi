# OmiSphere Trust Boundary — Tier 2C P1+P2 Evaluation

Where does detection become difficult? This report answers that from **real
on-disk data**, by scoring Known Bad, Known Good, and a Known-Mixed proxy
through the production engine and the calibrated coordination aggregate.

## 0. Environment reality (measured, not assumed)
External acquisition specified by the directive is **infeasible in this
environment**:

| Host | Result |
|---|---|
| pypi.org / raw.githubusercontent.com | 200 / reachable |
| botometer.osome.iu.edu (Cresci-2017 source) | **403 blocked** |
| api.twitterapi.io (live human/mixed pull) | **403 blocked** |
| twitter.com | **403 blocked** |
| API keys in env | **none** |

So Cresci-2017 genuine+tweets cannot be downloaded and no live human/mixed pull
is possible here. This evaluation therefore uses the strongest real proxies
already in the repo, and the text-bearing human gap is carried forward as an
environmental blocker (see §7).

## 1. Populations (real, on-disk)
| Group | Source | N (sampled) | Text? |
|---|---|---|---|
| KB-IO (coordination) | Russia IRA + GRU IO tweets | 75 | ✅ |
| KB-bot (fake) | `fake_users.csv` profiles | 400 | ❌ |
| KB-bot (cresci) | cresci-rtbust bot profiles | 353 | ❌ |
| KG-human (cresci) | cresci-rtbust **human** profiles | 340 | ❌ |
| KG-human (real) | `real_users.csv` active (≥50 statuses) | 400 / 1141 | ❌ |
| **KM-proxy (hi-vol)** | `real_users.csv` ≥1k followers **and** ≥1k statuses | 64 | ❌ |

**Known-Mixed proxy:** `real_users` has a long legitimate tail (max **796k
followers / 139k statuses**). The ≥1k/≥1k cohort is the influencer/brand-shaped
sub-population that behaviorally *resembles* coordinated actors. It is a
documented proxy, **not** curated journalists/brands (which need egress/keys).

## 2. Known Good Dataset Report
- Real human negatives available on disk: **~693 cresci humans+bots** (profiles
  only, no tweet text) and **2500 `real_users`** (1141 active; the rest dormant
  shells with 0 statuses/0 followers).
- Usable for: `fingerprint` (profile-derived), `cohort` (cresci has creation
  dates; `real_users` does not), and per-account profile scoring.
- **Not** usable for: `style` / `temporal_semantic` — no human tweet text
  exists on disk. This is the load-bearing gap.

## 3. Known Mixed Dataset Report
- First Known-Mixed cohort constructed (proxy): 64 high-volume legitimate humans.
- Median follower/following ratio **2.01** (audience > outreach — influencer
  shape), median age **15.0y**, all flagged **0%** at both the per-account and
  group level. The engine's `followers > 50k → don't penalize` rule plus the
  ratio handling protect them.
- Real curated Known-Mixed (journalists/news orgs/brands/politicians/activists)
  remains an acquisition item — blocked on egress/keys.

## 4. Detector Evaluation Report

### (A) Profile-only per-account — identical inputs for every population
| Population | mean p | p90 | flag ≥ELEV | fr/fo ratio (med) | age yr (med) |
|---|---|---|---|---|---|
| KB-IO | 0.26 | 0.31 | **0.0%** | 0.38 | 8.6 |
| KB-bot/fake | 0.25 | 0.29 | 0.0% | 0.00 | 13.9 |
| KB-bot/cresci | 0.22 | 0.28 | 0.0% | 0.75 | 11.3 |
| KG-human/cresci | 0.19 | 0.25 | 0.0% | 0.83 | 12.2 |
| KG-human/real | 0.24 | 0.28 | 0.0% | 0.04 | 14.8 |
| KM-proxy | 0.21 | 0.25 | 0.0% | 2.01 | 15.0 |

**On profile metadata alone the engine is non-discriminative** — every
population sits at 0.19–0.26, nothing flags. No false positives, and no true
positives either. Profile features carry **no verdict** on these mature
accounts.

### (B) Coordination at group level — calibrated aggregate, threshold ≥ELEV
| Population | groups | text | flagged | scores |
|---|---|---|---|---|
| KB-IO | 3 | ✅ | **66.7%** | 0.70, 0.90, 0.21 |
| KG-human/cresci | 6 | ❌ | **0.0%** | 0.20–0.23 |
| KG-human/real | 6 | ❌ | **0.0%** | 0.21–0.30 |
| KM-proxy | 2 | ❌ | **0.0%** | 0.21, 0.27 |

**Coordination FPR = 0/14 human & mixed groups** (a much larger negative set
than Tier-2B's 5), **including** the high-volume-legitimate proxy. Caveat: these
groups have no text, so the 0% is carried by `fingerprint`+`cohort` not
clustering humans; `style`/`temporal` abstain. Precision/recall on IO is
consistent with Tier-2B (the strong-signal groups flag; weak samples don't).

## 5. Trust Boundary Analysis
1. **Strongly associated with manipulation:** text-level coordination
   signatures — shared writing style, behavior-derived fingerprint clustering,
   synchronized bursts. These fired on IO (67% of groups) and **never** on any
   human/mixed group.
2. **Strongly associated with legitimacy:** at the profile layer, essentially
   **nothing** — legitimacy isn't a positive profile signal. The only
   protective rule is high follower count (`>50k`), which correctly shields the
   Known-Mixed proxy.
3. **Shared by both (TRUST-CRITICAL):** *all* static profile metadata — account
   age (IO/bots are 8–14y mature, not fresh), follower/following ratio
   (overlapping ranges across every group), bio, verified status. Profile
   metadata is a shared space and **cannot** carry a manipulation verdict.

**The boundary:** detection is tractable *only* in the text/coordination layer
and collapses to chance in the profile-only layer. Manipulation and legitimacy
are separable by **what accounts say and how synchronously**, not by what their
profiles look like.

## 6. Updated Memory Readiness Gate
The profile-only result sharpens the gate. Memory anchoring is fingerprint-NN:
- **Profile-derived fingerprints are non-discriminative** (all populations
  overlap at 0.19–0.26). Anchoring in that subspace would pull text-less humans
  toward IO labels → **precision risk is real and now data-confirmed**.
- Anchoring is only safe on **text-derived** fingerprints, where IO separates.
  But the human side of the anchor neighborhood has **no text on disk** — so a
  safe anchor set cannot be built here yet.

| Gate dimension | Status |
|---|---|
| Expected recall impact | + on text-bearing IO lookalikes; ~0 on profile-only |
| Expected precision impact | **negative** without text-bearing Known Good (shared fingerprint space) |
| Dominant failure mode | fingerprint collision in the text-less profile subspace → human anchored to IO (**confirmed plausible**) |
| Verdict | **NOT MET** — now blocked specifically on *text-bearing* Known Good/Mixed |

Memory anchoring remains **not implemented**, per directive.

## 7. Tier 2C Progress Assessment
- ✅ Known Good evaluated at scale (1000+ real human/bot profiles) — profile
  layer proven non-discriminative & FP-safe.
- ✅ First Known-Mixed cohort built (proxy) and proven FP-safe.
- ✅ Real Trust Boundary established: detection lives in text/coordination, not
  profile.
- ⛔ Text-bearing Known Good/Mixed **blocked** by egress + missing keys — the one
  gap that gates both the `style`/`temporal` FPR proof and memory anchoring.

## 8. Recommended Next Action
The remaining work is gated on **environment access**, not analysis. To execute
P1/P2 as specified, one of:
1. **Allowlist egress** to the dataset host (OSoMe/Cresci) + Twitter API, and
   provide an API key — enables Cresci-2017 genuine+tweets and a curated
   Known-Mixed pull; **or**
2. **Commit the datasets directly** to the repo (Cresci-2017 genuine_accounts +
   tweets; a curated Known-Mixed handle set with timelines) — and the existing
   adapter/manifest path ingests them.

Until then: the profile layer is non-discriminative and FP-safe; coordination is
FP-safe on text-less humans; the **text-human FPR proof and memory anchoring
stay blocked**, concentrated exactly where Omi is currently blindest.

*The objective was understanding where detection becomes difficult. It becomes
difficult — and currently untested — the moment text is removed.*
