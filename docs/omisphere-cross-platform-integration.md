# OmiSphere — Cross-Platform Intelligence Integration (Twitter/X)

> Author: Claude. Date: 2026-06-02. Branch: `claude/focused-turing-upy6c`.
> Mandate: integrate Twitter/X into the **existing** Omi intelligence engine —
> ONE engine, shared normalization + intelligence, platform-specific only at the
> data-source edge. This document is the pre-implementation analysis (the 8
> required deliverables). Implementation proceeds in the phased plan (§8),
> starting with the `Source`-protocol refactor (T0).

**Headline:** the Twitter integration that already shipped (PR #26) is **not** a
parallel intelligence system. `scan_twitter_account` normalizes to the shared
`Profile`/`Post` schemas and calls the **same** `scan_account_with_memory` →
`analyze_account` → `aggregate` → memory → persistence → OmiScore that YouTube
uses. Omi is already ~70% a cross-platform engine. The remaining work is **not new
intelligence** — it is (a) a refactor putting YouTube *and* Twitter behind one
`Source` protocol, then (b) extending the *investigation flow* (unified entry,
persistence, coordination batch) and *frontend* to Twitter.

---

## 1. Current YouTube ML Architecture
- **Rule engine (shipped default):** `analyze_account(profile, posts, extra_signals)`
  (`detection/engine.py:21`) runs 8 pure detectors — temporal, semantic, ai_writing,
  voice, engagement, narrative, profile, **community** (GAP-07 exculpatory anchor) —
  then `aggregate()` (`detection/scoring.py:94`): decorrelated log-odds + convergence
  bonus + single-axis HIGH cap + signed `contributions` (GAP-06) → `ScanResult`.
- **Learned scorer (dormant):** `ml/scorer.py` (off by default, no artifact). Tabular
  LightGBM/HistGB over `ml/features.py` (fingerprint + detector prob/conf + metadata),
  trained from a corpus built by running rows through `analyze_account`
  (`ml/public_import.py`). Optional DistilBERT text head.
- **OmiScore layer:** `intelligence/omiscore.py` composes `ScanResult` → dimensions
  (coordination / amplification / spam / ai_generation[contextual] / authenticity).
- **Memory:** `memory/fingerprint.py` + `memory/prior.py` (k-NN), injected as an `extra_signal`.
- **Coordination:** 5 cross-account detectors (`detection/coordination/*`) + `elevate.py`,
  injected as an `extra_signal` in the full-scan path.
- **Narrative:** cross-corpus clustering (`app/narrative/*`) + a per-account `analyze_narrative`.

## 2. Current Intelligence Pipeline (YouTube)
`POST /v1/scan/link` → `classify_url` (YouTube-only) → consume credits →
`orchestrator.scan_comprehensive` → `fetch_video_full` → per-commenter
`scan_account_with_memory` (= `analyze_account` + memory + persist Account/Scan/fingerprint
+ monitoring) → batch → 5 coordination detectors → `elevate` → cross-links → narrative
ingestion (background) → `ComprehensiveScanResult` → synchronous persist as Investigation →
OmiScore on demand → report/share/commentary → frontend workspace.

## 3. Shared Components — reuse directly (already platform-agnostic)
| Component | File | Evidence |
|---|---|---|
| `Profile` + `Post` normalization | `schemas.py:10-43` | `Platform` literal includes `"x"`; `Post` carries `reply_to_id`/`repost_of_id`/`parent_id`/like/reply/repost |
| `analyze_account` / `analyze_comments` + detectors + `aggregate` | `detection/engine.py`, `scoring.py` | Pure functions over `Profile`/`Post` |
| `compute_omiscore` + registry | `intelligence/omiscore.py`, `signals.py` | Consumes `ScanResult` |
| Memory (fingerprint + k-NN) | `memory/*` | Operates on posts |
| **`scan_account_with_memory`** | `orchestrator.py:57` | **Already `platform`-parameterized; Twitter already calls it** |
| **`scan_video_full`** | `orchestrator.py:203` | **Already injection-based** (`fetch_profile`/`fetch_history`/`platform`) |
| Storage (Account/Scan/CoordinationEdge/Narrative) | `storage/models.py` | Keyed by `(platform, external_id)` |
| 5 coordination detectors + `elevate` | `detection/coordination/*` | Operate on normalized batches |
| ML/dataset training | `ml/*` | Trains on engine outputs |

**Proof Twitter single-account scoring is already unified:** `scan_twitter_account` →
`fetch_user_profile`/`fetch_user_recent_tweets` (normalize to `Profile`/`Post`) →
`scan_account_with_memory(..., platform="x")`. No parallel scorer.

## 4. Components Requiring Adaptation (parameterize, don't fork)
| Component | File | Action |
|---|---|---|
| `scan_comprehensive` | `orchestrator.py:572` | Only YouTube-coupled function (imports youtube fns at `:585`, hardcodes `platform="youtube"` at `:625,694`). **Extract a `Source` protocol**; depend on it. (T0) |
| co-engagement | `orchestrator.py:837` | `load_engagement_sets(platform="youtube")` → take platform param (T0) |
| cache-record platform | `orchestrator.py:261` | `platform="youtube"` on a cached `Profile` → use the scan's `platform` (T0) |
| URL classification | `youtube.py:classify_url` vs `twitter.py:classify_twitter_url` | Unify into one `classify_link` dispatcher (T0); route `/scan/link` through it (T1) |
| Investigation persistence / `/scan/link` | `routes/scan.py` | Make platform-aware so a Twitter scan persists a `ComprehensiveScanResult` Investigation → report/share/commentary work for free (T1) |

## 5. Platform-Specific Components (keep isolated)
- **Data Source Layer:** `integrations/youtube.py`, `integrations/twitter.py` (+ `*_errors.py`)
  — fetch + normalize + classify + typed errors + quota/cost. The only per-platform code.
- **Platform-native fields:** retweets/quotes (`repost_count`/`reply_to_id`), YouTube channel
  metrics — already absorbed as optional fields on the shared `Post`.
- **Batch assembly differs:** YouTube batch = a video's commenters; Twitter batch = a tweet's
  repliers/quoters (or an account-interaction set). Each platform assembles the cross-account
  batch; the coordination intelligence over it is shared.

## 6. Dataset Reuse Opportunities (improve both platforms at once)
- The ML feature vector = **engine outputs over normalized `Profile`/`Post`**, so any labeled
  account dataset trains a model that scores **both** platforms. The Tier-2 dataset work
  (unlock the balanced fsm `.xlsx`, quarantine the random-label poison, `ai_vs_human_text_2026`
  benchmark) improves YouTube **and** Twitter simultaneously.
- **#1 cross-platform opportunity:** build the **real engagement/amplification detector on the
  shared `Post` engagement fields** (like/reply/repost) — both platforms populate them; fixes
  the Tier-2 "amplification is a relabel" finding for both, and Twitter gives true follower/following.
- **#1 shared gap:** no real coordination ground truth — a Twitter/X transparency IO archive
  (the `io_disclosure` adapter exists, labels `political_coord`/`high`) calibrates coordination
  for both platforms.

## 7. Unified Architecture Proposal
```
Data Source Layer   youtube.py | twitter.py | (reddit…)   ← ONLY platform-specific code
  Source protocol: classify · parse_content_id · resolve_account_id
                   · fetch_account_profile → Profile · fetch_account_posts → [Post]
                   · fetch_content_engagers → batch · quota/cost · typed errors
        ↓
Normalization Layer   Profile + Post (already multi-platform)
        ↓
Intelligence Layer (SHARED)  analyze_account · memory · coordination · narrative
                             · aggregate · compute_omiscore
        ↓
Evidence Layer (SHARED)  SignalResult.evidence · contributions · score_adjustments
                         · cross_links · OmiScore evidence
        ↓
Reporting Layer (platform-aware presentation, shared intelligence)
                 Investigation · report templates · frontend workspace
```
The orchestrator becomes platform-agnostic by depending on the **`Source` protocol** instead
of the `youtube` module. Everything below the Source layer is already shared.

## 8. Recommended Implementation Plan (architectural-consistency first)
- **T0 — `Source`-protocol refactor (no new platform behavior; YouTube tests stay green).**
  Introduce `Source`; refactor `scan_comprehensive` to fetch through it (YouTube = first
  Source impl, a thin delegating adapter); de-hardcode co-engagement + the cache-record
  platform; add a unified `classify_link`. *The keystone that guarantees ONE engine.*
- **T1 — Twitter as a first-class single-account investigation.** Route Twitter through the
  unified `/scan/link` so a Twitter scan persists a `ComprehensiveScanResult` Investigation →
  report/share/commentary/frontend work immediately (reuses the shared `scan_account_with_memory`).
- **T2 — Twitter coordination (the differentiator).** Implement Twitter `fetch_content_engagers`
  (a tweet's repliers/quoters or an account-set) → feed the **same** coordination/elevate/narrative.
- **T3 — Frontend.** Make the investigate workspace + report platform-aware (accept X URLs/handles,
  render tweet context). Mostly reuse — components are payload-driven.
- **Cross-cutting:** the shared engagement/amplification detector (§6) — improves both platforms.

**Principle:** every Twitter decision must strengthen the one shared engine, never fork it.
Prioritize architectural consistency over implementation speed.
