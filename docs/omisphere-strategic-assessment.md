# OmiSphere — Strategic Assessment (Discovery → Analysis → Recommendations)

> Author: Claude (acting as founder / product strategist / architect / reliability &
> trust-&-safety researcher). Date: 2026-06-02. Branch: `claude/focused-turing-upy6c`.
> Method: full-repo discovery + four parallel evidence-gathering audits (backend
> reliability, detection engine, frontend/trust, datasets/ML/billing) + a live
> backend test run (**482 passed**, 85s). Every claim below is grounded in the
> code as it exists, not the marketing.

---

## Addendum — post-snapshot corrections (2026-06-02)

Two updates since this assessment's clone snapshot (`774ab1b`):

1. **Twitter/X ingestion shipped to `main`** (PR #26, via `twitterapi.io`). This
   partially addresses **Weakness #17** ("single-platform") and overtakes
   **Do-Not-Build #1** ("don't build other platforms yet") — X ingestion already
   landed. The core thesis is *unchanged and arguably reinforced*: a second
   platform — one that costs real money per call (Twitter is priced at
   ~$0.005/post → 10 credits/batch, vs YouTube's effectively-free 1) — has been
   added on top of an engine still validated only by synthetic fixtures. That
   makes real-data validation (**Improvement #4**) *more* urgent, not less.

2. **Tier-1 Foundation — completed on this branch.** The reliability,
   data-integrity, error-handling and recovery items in the priority hierarchy's
   Tier 1 are now closed:
   - **Investigation persistence** is synchronous + collision-safe: the slug
     `/scan/link` returns always resolves (no read-after-write 404, no
     empty-payload rows), and a client can't collide on another user's
     globally-unique slug and silently drop a save (Weakness #1).
   - **Honest billing**: a failed scan never costs a credit — `/scan/link`
     refunds on any failure (and `/comprehensive` on non-YouTube errors),
     preserving the `YouTubeAccessError` "no refund" policy (Weakness #3). A scan
     where *every* commenter errors is treated as a failure (refund + 502), not a
     uniformly-empty charged result.
   - **Data durability** (Weakness #7): the prod blueprint no longer provisions a
     `free` Postgres (deleted ~90 days after creation) — it uses a paid, backed-up
     tier. Boot now runs an idempotent **index gap-fill** so composite indexes
     added after a table already exists are created on long-lived production DBs
     (no silent full scans).
   - **Resource bounding** (part of Weakness #4/#15): `/scan/link` clamps
     `max_commenters` to the operator cap (closing a raw-dict bypass that could
     over-charge, 422, or fetch an unbounded batch) and parses bad input
     defensively; the YouTube client bounds every call with a socket timeout so a
     hung connection can't pin a worker.
   - **Recovery**: `background.shutdown` now honours its time budget instead of
     blocking a redeploy indefinitely on a hung best-effort task.
   - Covered by new regressions in `tests/test_investigation_hardening.py` and
     `tests/test_tier1_hardening.py`; full backend suite green.

   **Deliberately deferred (documented, not skipped):** releasing the DB session
   across YouTube I/O via an async job model for very large scans, and hoisting
   the per-commenter brute-force fingerprint-neighbor load (O(commenters ×
   accounts)). Both are larger, orchestrator-/detection-touching refactors whose
   worst case is already bounded by the new `max_commenters` clamp; per the
   operating directive ("prefer the simplest solution", "don't destabilize"),
   they belong in a dedicated, separately-tested effort and are the headline
   items for the scalability track once real-data validation (Tier 2 /
   Improvement #4) is underway.

---

## Executive Summary

OmiSphere is **much better built than a pre-PMF product has any right to be — and that is
both its strength and the source of its single biggest risk.** The engineering is
disciplined: 482 green tests, CI, harness-gated accuracy ratchets, production boot
guards, typed YouTube error handling with credit refunds, a clean
detection→intelligence→report architecture, and a genuinely above-average
transparency layer (per-detector evidence, "how this score was calibrated"
narration, weak-signal caveats, and a principled refusal to let AI-writing style
manufacture accusations).

The problem is that **almost none of the accuracy has been validated against reality.**
Every benchmark the product grades itself on (`seed_v1`, `coordination_v1`,
`rescue_v1`, `memory_v1`) is a hand-authored synthetic fixture whose inputs were
written to contain the exact tells the detectors look for. The celebrated "Brier
0.0588 / macro-F1 0.583" measures *internal consistency*, not correctness. For a
product whose entire promise is to be a **trust layer for the internet**, validating
trust against data you authored yourself is the existential gap.

Three things sit underneath that headline:

1. **Reliability has concrete, already-bitten failure modes** (Tier 1). Investigation
   persistence is best-effort and off-thread — the API returns a shareable slug
   *before* the row is guaranteed to exist, which is the most likely cause of the
   historically reported "scan finishes but shows no result." Users can also be
   **charged credits for scans that fail**. A failed/lost investigation is worse
   than no investigation.

2. **The newly-uploaded datasets are a trap, not an asset.** Half the dataset corpus
   (`bot_detection_data.csv`, 50k rows) is coin-flip noise; another file is poisoned
   with HTTP-error strings labeled "AI"; another is 99.8% one class. Ingesting them
   would degrade the model. Meanwhile the one kind of data that would actually move
   the needle — real, labeled coordinated-influence ground truth — is absent.

3. **The intended moat (accumulated intelligence) is currently self-confirming.** The
   `memory` detector scores an account by averaging the prior verdicts of its
   fingerprint-neighbors, and every scan adds a neighbor — so early mistakes compound
   into a confidently-wrong asset. An intelligence graph fed by unvalidated, circular
   signals is a liability, not a moat.

**The path to "I need this" (not "interesting") is narrow and clear:** make
investigations complete and durable (Tier 1), prove accuracy on *one* real labeled
corpus and show users honest uncertainty + alternative explanations (Tier 2), and
only then let the intelligence graph accumulate — with provenance and contamination
controls. Resist the pull to add platforms, detectors, ML, scale-out infra, or new
UI surfaces until the core YouTube thesis is reliable and *measured*.

---

## Product Overview

**What it is.** OmiSphere is a YouTube comment-section authenticity-intelligence tool.
Paste a video or channel URL → it fingerprints every commenter across eight detectors,
finds coordination clusters between accounts, synthesizes an overall verdict, and saves
the whole thing as a shareable, re-scannable **investigation**. "omi" (Online Media
Intelligence) is the embeddable detection engine; "OMISPHERE" is the investigative
product around it.

**What's actually live (verified):** YouTube video + channel scans; 8-detector
per-account scoring; 5 cross-account coordination detectors; a persistent coordination
graph (networkx over a `coordination_edges` table); cross-corpus narrative clustering;
saved investigations with slug URLs; public share reports (executive/evidence
templates, Markdown/JSON export); optional Claude-Haiku analyst commentary; watchlists +
background anomaly monitoring; Stripe billing with batch-based credit pricing; a
dormant learned-ML scorer track; a dataset-ingestion/training pipeline; an admin
benchmark/calibration scoreboard. **84 endpoints, ~24k LOC backend.**

**What's explicitly not there:** any non-YouTube ingestion (engine is platform-agnostic,
only the YouTube adapter ships), real-time push, team/multi-seat.

**Positioning (from the product copy):** "not a binary bot/not-bot classifier… every
result is a probability with an explicit evidence chain… we never accuse, we never claim
certainty." This is the right north star — and the product mostly lives up to it, with
specific gaps called out under *Transparency Assessment*.

---

## Architecture Overview

A clean monorepo with a deliberate, well-defended split:

| Layer | Stack | Notes |
|---|---|---|
| `apps/api` | FastAPI + Python + SQLAlchemy + networkx | The `omi` engine + HTTP service. Pure-Python detection (`app/detection/`), no I/O in detector code; `orchestrator.py` owns I/O. |
| `apps/web` | Next.js 14 + TypeScript + Tailwind | Server-component data fetching, minimal client state, `usePolling` for live surfaces. |
| `packages/shared` | TypeScript types | web⇄api contract. |
| Infra | Render blueprint + docker-compose | `render.yaml` provisions web + api + Postgres. |

**Engine flow (one scan):** `POST /v1/scan/link` → classify URL → consume credits →
`orchestrator.scan_comprehensive` → per-commenter (cache → YouTube profile+history →
detectors → fingerprint → persist) → thread scan → coordination clusters → cross-link
synthesis → `ComprehensiveScanResult` → saved investigation.

**Two scoring systems sit on top of each other (worth noting):** the rule engine emits a
4-tier verdict (LOW/MODERATE/ELEVATED/HIGH via decorrelated log-odds); the
`intelligence/` layer (**OmiScore**) re-composes the same signals into 0–100 named
dimensions (coordination, amplification, spam, ai_generation [contextual],
authenticity) with a 3-level risk band. The OmiScore envelope is the better-designed,
more explainable surface; the dual representation is a latent source of user confusion.

**Architecture strengths:** strict boundaries (no JS in api, no DB in web, third-party
APIs server-side only, LLMs never in the per-scan hot path, append-only fingerprint
schema); production boot refuses to start on SQLite / missing YouTube key / dev session
secret; a declarative signal registry so new detectors/dimensions are data, not code.

**Architecture risks (detail in Reliability):** scans are **synchronous** over up to
150 commenters' worth of blocking YouTube calls inside a single held DB session;
nearest-neighbor memory lookup is brute-force (loaded per commenter); the production
blueprint provisions a **free** Postgres tier for data the docs themselves call "the only
irreplaceable thing."

---

## Investigation Pipeline Overview

Stages, with the failure surface noted (file:line evidence in the Reliability section):

1. **Initiate** — `routes/scan.py:scan_link`; `classify_url` → video|channel|unknown.
2. **Charge** — `compute_scan_credits` → `consume_credits` (committed *before* the scan
   runs). 402 if short. No-op in local mode / for admins.
3. **Fetch + score** — `orchestrator.scan_video_full`: per-commenter loop
   (cache → `fetch_profile` → `fetch_history` → `scan_account_with_memory` → persist),
   each wrapped in `try/except` that demotes failures to a 0.5/LOW placeholder.
4. **Coordinate** — 5 cross-account detectors → clusters → `coordination/elevate.py`
   re-aggregates a what-if probability that *rescues* sparse in-cluster bots (without
   mutating the persisted per-account scan). Edges upserted best-effort.
5. **Synthesize** — overall tier + inferred intent + "why flagged" reasons +
   `score_adjustments` + `weak_signals`.
6. **Persist investigation** — **fire-and-forget** `background.submit(...)`; the HTTP
   response (with the slug) returns *before* this runs.
7. **Retrieve** — `GET /v1/investigations/{slug}`; continuation batches merge into the
   same row (commenters deduped by `external_id`).

The pipeline is well-factored and the coordination "rescue" path is genuinely the
product's best idea. The weak joints are all at the **edges**: charging before success,
persisting after responding, and holding a DB connection across minutes of network I/O.

---

## Dataset Audit

11 data files (~76k rows) are committed under `datasets/`. **Nothing has been ingested
yet** (no ledger, no `_generated/`). Quality, pulled live via pandas:

| File | Rows | Label | Verdict |
|---|---|---|---|
| `Fake…/bot_detection_data.csv` | 50,000 | `Bot Label` 50/50 | **NOISE — archive/delete.** Label has zero correlation to any feature (follower 4985 vs 4991; verified 50.1% vs 49.9%); tweets are Faker word-salad. 50% of the entire corpus. |
| `ai vs human/ai_human_detection_v1.csv` | 686 | `human_or_ai` | **POISON — archive.** "AI" class dominated by literal `Error: 400 Client Error … api.groq.com` strings. Teaches "contains 'Error'" = AI. |
| `Fake…/fake_social_media.csv` | 3,000 | `is_fake` | **Heuristics only.** 2993 fake / **7 real** (99.8% imbalance) — untrainable; useful only for feature distributions. |
| `Fake…/…global_2.0…with_missing.xlsx` | 3,000 | `is_fake` | **Best behavioral set (1941/1059) — but pipeline can't read `.xlsx` by design.** Needs CSV export to be usable. |
| `Fake…/real_users.csv` + `fake_users.csv` | 5,000 | filename | **Strongest real training source here** (labeled Twitter profiles) — but ~35% nulls; old MIB-style dump. |
| `Fake…/reddit_dead_internet_analysis_2026.csv` | 500 | `is_bot_flag` + type | **Validation/reference.** Small but has a bot-type taxonomy. |
| `ai vs human/ai_vs_human_text_2026.csv` | 2,000 | `label` | **Validation-only, dedupe first.** 51% duplicate texts; `generation_method` metadata perfectly predicts label (leakage if it ever reaches features). |
| `ai vs human/ai_vs_human_text.csv` | 1,000 | `label` | **Archive.** 100% templated stub text ("This is an example of text generated by ChatGPT…"). |
| `activity_botscore.csv` | 11,190 | `bot_score_english` (continuous) | **Reference-only.** No class label → no adapter matches → silently ignored. Synthetic-looking (all accounts ~8–12 yr old). |
| `article_discusses_claim` | ~793 | — | **Archive.** XZ-pickled DataFrame with no extension; fails to unpickle on current pandas; ingestion ignores it. Dead weight. |

**Applicability summary.** *Train (account track):* `real_users`+`fake_users`, and the
`.xlsx` once exported. *Heuristics/reference:* `fake_social_media`, `activity_botscore`,
`reddit_dead_internet`. *Validation-only:* `ai_vs_human_text_2026`. *Archive:*
`bot_detection_data`, `ai_human_detection_v1`, `ai_vs_human_text`, `article_discusses_claim`.

**The single biggest dataset issue:** `bot_detection_data.csv` is 50% of the corpus and
is pure noise; the ingestion registry's generic sniffer *will* claim it. The biggest
*absence:* there is **no real coordination ground truth** (the `io_disclosure` adapter
exists for Stanford-IO / X-transparency CSVs, but no such file is present), so the
product's core differentiator — coordination detection — has **zero** real validation
data.

**Recommended future dataset architecture:** a `datasets/` manifest with explicit
status per file (`train` / `heuristic` / `validation` / `reference` / `archive`),
provenance, and a quality gate (class-balance, label–feature mutual-information, dedupe,
null thresholds) that *refuses to ingest* anything failing the bar. Quarantine archives
out of the ingestion path. Treat real labeled IO archives as the top acquisition
priority.

---

## Reliability Assessment

Reliability is a Tier-1 product feature here, and it has the highest-leverage fixes in
the whole codebase. Imports are clean (87 routes register; the old `elevate` import bug
is resolved). The concrete failure surface:

1. **Investigation save is best-effort, off-thread, and races the response.**
   `scan_link` returns the slug at `routes/scan.py:928`, but persistence is
   `background.submit(...)` (`:920`) and `background.submit` swallows every exception
   (`core/background.py`). If payload serialization fails, the row is written with an
   **empty `{}` payload** (`:912-917`) — it *looks* saved but contains nothing. A fast
   client GET on the returned slug can **404** (read-after-write race). **This is the
   most likely root cause of "scan completes but no result shows."**
2. **`Investigation.slug` is globally unique but looked up per-user** (`models.py:386`
   vs `repository.py:135`). A client-supplied slug colliding across users → INSERT
   violates the constraint → 3 silent retries fail → **investigation never saved**.
3. **A whole scan's YouTube I/O runs inside one held DB session/transaction**
   (`scan.py:1024`), plus nested sessions within a request (`:280`→`:384`). On SQLite
   this starves concurrent writers (lock contention beyond the 30s busy-timeout).
4. **Scans are synchronous, sequential, un-timed, un-retried.** Every YouTube
   `.execute()` blocks with no timeout (`integrations/youtube.py`); a 100-commenter scan
   issues ~200 sequential calls. At 1k–10k commenters this exceeds any proxy idle
   timeout → the client never gets a response — a textbook "gets to the end and quits."
5. **Charged-for-failed-scan (billing).** Credits are consumed and committed *before*
   the scan; refunds only fire for `YouTubeClientError` on the `/comprehensive` path.
   Failures via `/scan/link` (which charged real cost, then calls inner with
   `_charge_credit=False` → refund computes 0) and **all** non-YouTube exceptions leave
   the charge in place. Charge and refund use independently-computed cost values that can
   diverge.
6. **Silent degradation that still bills.** A systemic detector bug yields a 200 where
   *every* commenter is a 0.5/LOW placeholder (`orchestrator.py:313-320`), fully charged.
7. **Scale cliffs.** Brute-force `all_with_fingerprints()` is loaded **per commenter**
   (`repository.py:40`) → O(commenters × accounts); coordination detectors are O(n²);
   the whole investigation payload is re-serialized as one JSON blob every batch.
8. **Data-durability.** `render.yaml` provisions **`plan: free`** Postgres (90-day
   expiry / tight limits) and single instances — for investigations/fingerprints the docs
   call irreplaceable. The incremental-column migration only *adds* columns and never
   creates model-declared indexes on pre-existing tables (silent full scans at scale);
   failed `ALTER`s are swallowed.
9. **`require_auth` defaults `False`** (correct for local mode; a prod-misconfig footgun,
   though the boot guard mitigates it) and `background.shutdown` ignores its
   `wait_seconds` budget and can block redeploys.

**Net:** the engine *computes* reliably (482 tests prove regression safety), but the
**persistence and billing edges are not yet trustworthy**, and the synchronous-scan
architecture will not survive large investigations. This is the right place to spend the
next sprint.

---

## Transparency Assessment

This is the product's genuine differentiator and it is **above-average for the category** —
but it falls short of its own promises in a few specific, fixable places.

**What's strong (keep, and market honestly):**
- Per-detector **evidence strings** with the actual measured values; a "why this was
  flagged" reasons list; **`score_adjustments`** that narrate every decorrelation
  discount, convergence bonus, and the single-axis HIGH cap in plain language ("How this
  score was calibrated"); **`weak_signals`** that surface data-quality caveats ("too few
  posts to establish a cadence").
- The **GAP-03 supplemental/contextual** architecture: AI-writing style is computed and
  shown but *structurally excluded* from suspicion — a principled, correct protection for
  ESL/formal/Grammarly-assisted writers, pinned by tests.
- Probabilistic framing in copy ("consistent with," never "is"; "not a definitive
  judgement") on signup and public reports.

**Where it breaks its own promise (the trust gaps):**
1. **Headline scores are point estimates with no uncertainty band.** A 74%@confidence-0.3
   and a 74%@confidence-0.9 render identically (`score-ring.tsx`, `probability-bar.tsx`).
   Confidence exists in the data but is not shown at the verdict level — directly at odds
   with "every result is a probability with an explicit evidence chain."
2. **No benign / alternative explanations are ever surfaced.** The competing innocent
   hypothesis ("this could be a scheduled brand account"; "low pronoun rate is normal for
   short informational comments") exists only in *source-code comments*, never in
   user-facing output. The founder directive's own investigation standard requires
   "evidence weakening the finding" and "alternative explanations" — today the engine
   only argues *for* suspicion.
3. **The headline label reads accusatory.** Commenter detail shows a bare "inauthentic"
   label even when probability < 1.0 (`commenter-detail.tsx:157`), contradicting "we
   never claim certainty."
4. **Claims not evidenced in-product.** "Self-improving fingerprint database" and "eight
   *independent* detectors" are asserted but never demonstrated (no accuracy-trend, no
   independence shown — and per the engine audit several detectors are explicitly
   *correlated*). The OmiScore panel silently renders nothing on a 404 rather than saying
   "not yet available."
5. **The deepest, least-visible gap: the accuracy numbers themselves.** The admin
   benchmark scoreboard reports Brier/F1 from synthetic fixtures as if they were
   real-world calibration. Honesty at the surface is undermined by self-grading
   underneath. `docs/youtube-credibility.md` already admits this in prose; the product UI
   does not.

**Verdict:** transparency is the wedge to "I trust this." Closing gaps 1–3 is low-effort
and would make OmiSphere best-in-class on explainability. Gap 5 is the existential one and
belongs to validation, below.

---

## Product-Market-Fit Assessment

**Assume no PMF (correct).** Evidence-based read of why:

**Why someone would use it / pay:** a journalist, brand-safety/T&S analyst, or researcher
investigating whether a video's engagement is organic gets something they genuinely
cannot easily get elsewhere — a per-commenter breakdown *plus cross-account coordination
clusters* with an evidence trail and a shareable report. When coordination is actually
present, the "I would have missed this" moment is real, and the rescue benchmark shows
the mechanism that produces it.

**Why they would not return / not pay:**
- **The value moment is rare and gated.** Most videos are organic; most scans correctly
  return "nothing." The empty state frames that as "the video is clean," which to a
  casual user reads as "this tool doesn't do anything." You only feel the magic on the
  subset of videos that *are* manipulated — and the product doesn't help users find those.
- **Single platform.** The people who care about coordinated influence overwhelmingly
  care about X/Twitter, Reddit, and TikTok. YouTube-comments-only is a narrow wedge; the
  "deep on one platform" framing is honest but limits the addressable buyer.
- **Unproven accuracy.** A paying T&S/journalism buyer will ask "what's your false
  positive rate on real data?" Today the only answer is a synthetic benchmark. That stalls
  the sale and, worse, a single visible false accusation destroys trust permanently.
- **Reliability tax.** A scan that completes-but-shows-nothing, or charges a credit for a
  failure, converts a curious first-time user into a churned one immediately.
- **Opaque economics.** Default scan = 2 credits (150-commenter = 3); "20 scans/month"
  is really ~6–10 real video scans for $9.99, and the 3-credit trial ≈ one full scan —
  thin runway to reach the value moment before the meter bites.

**The blunt PMF read:** the core insight (investigate *the comment section as a system*,
not one account) is differentiated and right. But the product is currently optimized to
*impress* (breadth: 84 endpoints, 9 phases, monitoring, narratives, graphs, ML) rather
than to *reliably deliver one indispensable outcome*. The move from "interesting" to "I
need this" is a depth-and-trust problem, not a feature-count problem.

---

## Intelligence Layer Assessment (the Moat)

The right instinct is already in the codebase: persist intelligence into reusable assets.
What exists — `accounts`, `scans`, `fingerprints` (memory), `coordination_edges` (the
cumulative graph), `narratives` + memberships, `account_labels` (ground truth),
`content_entities`/`comment_batches` — is a real skeleton of an **Authenticity
Intelligence Graph**, and that is the correct long-term moat.

**But the moat is currently fragile or self-defeating:**
1. **The `memory` detector is reflexively circular.** It scores an account by averaging
   the `last_score` of its fingerprint-neighbors, and every scan writes a new neighbor
   (`memory/prior.py`). "Self-improving" is, mechanically, also "self-confirming": an early
   false positive becomes a prior that manufactures the next one. The engine's own metrics
   code even warns about overfit/label-leakage influence — and nothing acts on it.
2. **It's cold-start empty and usage-gated.** Coordination correlations "stay at the
   curated prior until enough cross-account full scans exist" — i.e. the moat only
   compounds with usage volume that a pre-PMF product doesn't have. Chicken-and-egg.
3. **It's fed by unvalidated signals.** Accumulating intelligence from a detector stack
   that's never been checked against real labels builds a *confidently wrong* asset.
   Garbage accumulates too.
4. **Labels are mostly synthetic/empty.** `account_labels` is the bridge to real ground
   truth (via the LabelWidget + auto-captured YouTube suspensions), but it isn't populated.

**The opportunity (sequenced correctly):** the graph becomes a moat the moment it carries
**provenance, confirmation status (observed vs. confirmed-by-label/outcome), confidence,
and decay**, and reuses confirmed intelligence to *raise the floor* on future
investigations. But that must come **after** reliability and real validation — otherwise
you are pouring concrete around an unmeasured foundation.

---

## Top 20 Weaknesses (ranked: blended impact × urgency × trust × retention × revenue)

| # | Weakness | Tier | Primary harm |
|---|---|---|---|
| 1 | Investigation persistence is best-effort/off-thread; slug returned before row exists → lost/empty results, 404 race | 1 | Trust + retention (a failed investigation is worse than none) |
| 2 | Accuracy validated **only** against self-authored synthetic fixtures; no real ground truth | 2 | Existential credibility / revenue (can't sell unproven trust) |
| 3 | Users can be **charged credits for failed scans** (`/scan/link` + non-YouTube exceptions) | 1 | Revenue + trust (direct money harm) |
| 4 | Whole-scan YouTube I/O held inside one DB session; sync, un-timed, sequential fetches | 1 | Reliability at scale (large scans time out) |
| 5 | `memory` detector is circular/self-confirming → contaminates the moat | 2/3 | Quality + long-term defensibility |
| 6 | Newly-uploaded datasets are noise/poison/imbalanced; generic sniffer will ingest the 50k-row noise file | 2 | Quality (model poisoning) |
| 7 | Production blueprint provisions **free** Postgres + single instance for "irreplaceable" data | 1 | Data integrity |
| 8 | Headline scores are point estimates with **no uncertainty/confidence band** | 2 | Trust (violates the evidence-chain promise) |
| 9 | **No benign/alternative explanations** surfaced to users (only in code comments) | 2 | Trust + investigation quality (fails the directive's own standard) |
| 10 | No **real coordination ground truth** — the core differentiator is unvalidated | 2 | Credibility of the headline feature |
| 11 | Detector thresholds/weights are hand-tuned magic numbers; promised calibration never happened | 2 | Quality (won't transfer to real distributions) |
| 12 | Signals fire on benign behavior (scheduled brand accounts, informational/low-pronoun commenters, niche-community age cohorts, night-shift TZ) | 2 | Trust (false positives on real users) |
| 13 | Coordination confidence floor 0.55 → 3 generic "great video!" comments in 2 min = confidence 0.75 | 2 | Trust (overconfident on thin evidence) |
| 14 | Accusatory "inauthentic" headline label contradicts "we never claim certainty" | 2 | Trust |
| 15 | Quadratic scale paths (per-commenter neighbor load; O(n²) coordination; full-payload re-serialize per batch) | 1 | Reliability/cost at scale |
| 16 | Scope sprawl: 84 endpoints / 9 "done" phases / dormant ML for an unvalidated single-platform product | — | Focus (breadth over core-thesis validation) |
| 17 | Single-platform (YouTube comments) wedge limits the addressable buyer | 5 | PMF / revenue ceiling |
| 18 | Opaque/thin credit economics; "20 scans/mo" ≈ 6–10 real scans; 3-credit trial ≈ 1 scan | — | Retention/activation + revenue clarity |
| 19 | "Empty result = clean" conflates no-detection with authentic; most scans return nothing | 4 | Retention ("it does nothing") |
| 20 | ML training not reproducible (unpinned live-DB corpus, algorithm varies by installed libs); train/serve skew (`post_count=0`) | 3 | Quality/ops debt |

---

## Top 10 Highest-Leverage Improvements (ranked by expected ROI)

1. **Make investigations durable and complete (Tier 1).** Write the investigation row
   *synchronously with a real payload* before returning its slug; namespace the slug
   per-user; never hand the client a slug it can 404 on; add an audit/recovery path for
   the off-thread enrichment. *Low complexity, highest trust/retention ROI; fixes a
   known, already-experienced failure.*
2. **Fix charge-vs-refund (Tier 1).** Charge after success, or guarantee a refund on any
   failure, via one shared cost computation. *Low complexity; removes a direct
   trust-and-money wound.*
3. **De-risk the scan architecture (Tier 1).** Release the DB session across YouTube I/O;
   add per-call timeouts + bounded retries; clamp `max_commenters` server-side; route
   large scans through the existing async job model. *Medium; unlocks big-video scans
   without timeouts/lock-starvation.*
4. **Validate on ONE real labeled corpus (Tier 2).** Acquire a real coordinated-influence
   / bot ground-truth set (Stanford Internet Observatory, X transparency disclosures — the
   `io_disclosure` adapter already exists), build a real benchmark via `--from-db`, and
   report **real** precision/recall/false-positive rate. *Medium; converts "trust us" into
   a number — the single biggest unlock for sales and credibility.*
5. **Quarantine + curate datasets (Tier 2).** A `datasets/` manifest with status +
   provenance + an automatic quality gate (class balance, label–feature MI, dedupe, null
   thresholds) that refuses noise/poison. Archive `bot_detection_data` and the
   error-string set out of the ingest path. *Low; prevents moat poisoning.*
6. **Close the transparency gaps the product already promises (Tier 2).** Show a
   confidence/uncertainty band on headline scores; surface "alternative/benign
   explanations" and "evidence weakening this finding"; soften the accusatory label to
   "likely…". *Low–medium; makes OmiSphere best-in-class on the thing it's already best
   at.*
7. **Guarantee durable storage (Tier 1).** Move the prod blueprint off free Postgres,
   verify backups, and create the missing indexes. *Low; removes a data-loss landmine.*
8. **De-circularize memory (Tier 3 moat + quality).** Only *confirmed/labeled* outcomes
   feed the prior; separate "observed" from "confirmed"; add provenance + decay. *Medium;
   turns the moat from self-confirming into self-correcting.*
9. **Operationalize the "valuable investigation" standard (Tier 2).** Make every
   investigation explicitly answer the 9 questions (what/why/patterns/evidence-for/
   evidence-against/alternatives/confidence/takeaway/recommended-action). *Medium; this is
   what makes a report "I learned something" instead of "a score."*
10. **Redesign the first-run value moment (PMF).** Help users reach a real coordination
    finding fast (curated example investigations of known-manipulated videos; honest
    empty-state framing that distinguishes "clean," "too little data," and "quota
    limited"). *Medium; attacks the "interesting → churn" problem directly.*

---

## Top 5 Things That Should NOT Be Built Right Now

1. **New platform integrations (X / Reddit / TikTok).** Tempting and on the roadmap, but
   premature: validate and harden the YouTube thesis first. Adding platforms now multiplies
   an unvalidated, partly-unreliable engine across more surfaces.
2. **Activating the learned ML scorer on the current corpus.** It would train on
   synthetic + noise + poison data and ship a model worse than the rule engine. Keep it
   dormant until real labeled data exists and beats the rule baseline on a held-out *real*
   set.
3. **Scale-out infrastructure** (Redis/Dramatiq, pgvector, Cytoscape, server-side PDF,
   email/SMS). This is Phase-9.5 work for a load you don't have. The seams are already
   documented; leave them as seams.
4. **More detectors or more intelligence dimensions.** The bottleneck is validation and
   reliability, not detector count. Adding signals adds calibration surface you can't yet
   measure.
5. **New UI surfaces / tabs.** Deepen `investigate` and the report (uncertainty,
   alternatives, the 9-question contract) instead of widening the navigation.

---

## Recommended Development Priority Order

Strictly tier-ordered (never start a lower tier while a known higher-tier issue is open):

- **Phase A — Foundation (Tier 1, now):** investigation persistence + completeness;
  charge/refund correctness; scan architecture (session release, timeouts, clamps, async
  jobs); durable Postgres + indexes; audit logs + honest error states. *Exit criterion:
  no scan can complete-without-a-saved-result and no failure can charge a credit —
  demonstrated under load.*
- **Phase B — Core Value (Tier 2):** one real labeled benchmark with reported real-world
  precision/recall/FPR; dataset quarantine + quality gate; transparency upgrades
  (uncertainty band, alternative explanations, label softening); the 9-question
  investigation contract. *Exit criterion: a stranger's claim "your false-positive rate is
  unknown" is answerable with a number.*
- **Phase C — Intelligence Layer / Moat (Tier 3):** de-circularize memory; add
  provenance/confirmation/decay to the graph; reuse confirmed intelligence to raise the
  floor on new investigations.
- **Phase D — Retention (Tier 4):** monitoring/watchlist quality, saved-investigation
  polish, alert usefulness — *after* the value is proven, not before.
- **Phase E — Growth (Tier 5):** sharing/virality, additional platforms, multi-seat. Last.

---

## Immediate Next Action

**Fix investigation persistence (Tier 1) — the result-loss bug class.** Applying the
directive's decision framework:

- **Problem:** the API returns a shareable investigation slug *before* the row is
  guaranteed to exist, and persistence is a fire-and-forget background task that can write
  an empty payload or silently fail.
- **Impact:** the highest-trust, highest-retention failure possible — a completed
  investigation that vanishes or 404s. It has already been reported by a real user.
- **Root cause:** `scan_link` responds at `routes/scan.py:928` while persistence is
  `background.submit(...)` (`:920`); empty-payload fallback at `:912-917`; global-unique
  slug looked up per-user (`models.py:386` vs `repository.py:135`).
- **Proposed solution:** persist the investigation row synchronously with a real payload
  (server-generated, per-user-namespaced slug) before returning; offload only optional
  enrichment; add a recovery/repair path and a regression test that a returned slug always
  resolves.
- **Alternatives:** (a) keep async but block the response on the persisted row;
  (b) make the client tolerate eventual consistency — rejected as papering over the bug.
- **User/Trust/Retention/Revenue/Moat impact:** directly improves all of them; this is the
  precondition for everything else.
- **Complexity:** Low. **Priority Tier:** 1. **Recommendation:** Proceed — paired with the
  charge/refund fix in the same Tier-1 sprint.

> I have **not** started implementation. Per the operating directive ("request
> confirmation before proceeding"), I'm bringing this to you to authorize the direction
> before writing code.
