# OmiSphere Product Intelligence Audit — Ground Truth

**Method:** repository-wide trace of backend (`apps/api`) + frontend (`apps/web`) by
two exhaustive read-only mapping passes, then data-flow verification. This answers
the gate question *before* any large build. **No production code was committed for
this audit.** (Disclosure: a campaign-persistence prototype was built+tested
concurrently and is held **uncommitted** pending the decision below.)

---

## 0. The definitive relationship (the question asked)

Traced data flow — **these are six *separate* stores, not one system:**

```
            ┌─────────────────────── ONE SCAN (scan_video_full) ───────────────────────┐
            │                                                                            │
 per-commenter scan_account_with_memory          cross-account: 5 coordination detectors │
   │                                               │ (temporal_semantic, fingerprint,     │
   ├─► Account.fingerprint_json  ◄── MEMORY (k-NN) │  cohort, style_match, co_engagement) │
   ├─► Scan.signals_json (detectors, intent,       │      │                               │
   │     confidence, weak_signals, adjustments)    │      ▼                               │
   └─► CommenterEngagement edges                   │   coordination CLUSTERS (objects)    │
                                                    │      │                               │
   background ─► NarrativeService.ingest_batch      │      ├─► CoordinationEdge (pairwise) │
        │  embeds comment TEXT → clusters           │      ├─► VideoScan.coordination_score│
        └─► Narrative + NarrativeMembership          │      └─► the CLUSTER OBJECT … DISCARDED
                                                    └────────────────────────────────────┘
   whole scan ─► Investigation.payload_json (immutable per-user snapshot)
```

| Concept | What it actually is | Persisted as | Grain |
|---|---|---|---|
| **Memory** | per-account behavioral fingerprint + k-NN prior | `Account.fingerprint_json` | account |
| **Coordination clusters** | the 5 detectors' "these N accounts act together" | **only** `CoordinationEdge` (pairs) + scalar `VideoScan.coordination_score` — **cluster object discarded** | account-group (ephemeral) |
| **Narratives** | semantic clusters of **messages** (comment text) | `Narrative` + `NarrativeMembership` | message |
| **Cross-scan intelligence** | three *disconnected* cumulative stores (fingerprints, `CoordinationEdge` graph, narratives) | — | mixed |
| **Investigation history** | immutable full-scan snapshots, per user | `Investigation.payload_json` | scan |

**Key facts:**
- **Narratives ≠ Coordination clusters.** Narratives = *what is being said* (message themes); coordination clusters / `CoordinationEdge` = *who is acting together* (account network). They are produced by different pipelines and never joined.
- **Cross-scan learning today = ONLY the fingerprint memory loop** (`Account.fingerprint_json` → next scan's k-NN neighbors). `CoordinationEdge` accumulates a graph but nothing reads it back into scoring. Narratives accumulate but aren't tied to account clusters.
- **The coordinated-account-group object is the one thing computed every scan and thrown away** — only its pairwise shadow (`CoordinationEdge`) and a scalar survive.

---

## 1. Backend Capability Inventory

| Capability | Backend source | Persistence |
|---|---|---|
| Per-account detector scan | `detection/engine.analyze_account` | `Scan.signals_json`, `Account.last_*` |
| Behavioral fingerprint + memory k-NN | `memory/fingerprint`, `memory/prior` | `Account.fingerprint_json` |
| 5 coordination detectors + gate | `detection/coordination/*`, `aggregate` | clusters → `CoordinationEdge`, `VideoScan.coordination_score` |
| Co-tag network detector (Phase 3) | `coordination/co_tag` | (eval only; not yet in `scan_video_full`) |
| Narrative clustering | `narrative/service`, `narrative/coordination` | `Narrative`, `NarrativeMembership` |
| OmiScore dimensions | `intelligence/omiscore`, `signals` | computed from `Scan.signals_json` |
| Content intelligence (per-content trend) | `content/service` | `ContentEntity`, `CommentBatch`, `ContentComment` |
| Coordination graph | `graph/store` | `CoordinationEdge`, `UserGraph*` |
| Investigations (saved scans) | `routes/investigations` | `Investigation.payload_json` |
| Monitoring / watchlists / alerts | `monitoring/*` | `Watchlist`, `Alert` |
| Ground-truth labels | `routes/labels` | `AccountLabel` |
| Engine benchmarks (admin) | `evaluation/*` | computed on demand |

---

## 2. Repository Reality Audit (per item)

Legend: Y / N / ◑ partial.

| Capability | Exists | Persisted | Queryable | UI shown | UI *effective* | Investigator | Admin |
|---|:--:|:--:|:--:|:--:|:--:|:--:|:--:|
| coordination clusters | Y | ◑ (pairs only) | ◑ (`/graph`) | Y (per-scan rings) | ◑ (in-scan only) | Y | N |
| narratives | Y | Y | Y (`/narratives`) | Y | ◑ (mislabeled value) | Y | ◑ |
| **campaign records** | **N** | N | N | N | N | N | N |
| **campaign relationships** | **N** | N | N | N | N | N | N |
| investigation history | Y | Y | Y | Y (`/investigations`) | ◑ (no cross-inv.) | Y | N |
| detector contributions | Y | Y (`signals_json`) | Y (payload) | ◑ (evidence only) | ◑ | ◑ | ◑ (benchmarks) |
| confidence metrics | Y | Y | Y | ◑ (signal detail) | N (hidden in hero) | ◑ | N |
| uncertainty / **weak signals** | Y | Y (payload) | Y | **N** | N | N | N |
| **score adjustments** (reasons) | Y | Y (payload) | Y | **N** | N | N | N |
| **matched prior neighbors** | Y | N (response-only) | N | **N** | N | N | N |
| intent classification | Y | Y | Y | ◑ (high-susp only) | ◑ | ◑ | N |
| propagation analysis | Y | ◑ (recomputed) | Y | Y (narrative detail) | Y | Y | ◑ |
| network evidence (`CoordinationEdge`) | Y | Y | Y (`/graph`) | Y | ◑ (manual graphs) | Y | N |
| memory signals | Y | Y (fingerprint) | Y | ◑ (signal only) | N | N | N |
| historical intelligence (account) | Y | Y | Y (`/accounts/{}/history`) | Y | ◑ | Y | N |

---

## 3. Intelligence Visibility Matrix

| Capability | Backend source | Persistence | Current UI | **Missing UI** | Recommended surface | Priority |
|---|---|---|---|---|---|---|
| Coordination **cluster object** | 5 detectors | **discarded** | per-scan rings | a durable, revisitable cluster | **Campaign record + Library** | **P0** |
| Coordination-adjusted prob / evidence | `orchestrator:547` | **discarded** | partial | the per-account coord verdict | persist on `Scan`; show in detail | P1 |
| Weak signals (uncertainty) | engine | payload | **none** | "low-confidence / not enough data" | result hero "uncertainty" block | **P0 (trust)** |
| Score adjustments (reasons) | engine | payload | **none** | why the score moved | result detail | P1 |
| Detector contributions (signed) | `aggregate`/scoring | `signals_json` | evidence bullets | for/against with weights | result "why" panel | **P0 (trust)** |
| Confidence | engine | `Scan.confidence` | signal detail | not in verdict hero | hero confidence band | **P0 (trust)** |
| Matched prior neighbors (memory) | `orchestrator:179` | **discarded** | none | "seen near N known accounts" | result + account page | P1 |
| Intent label | engine | `signals_json` | high-susp only | the headline "what kind" | result hero | P1 |
| `CoordinationEdge` graph | `graph/store` | Y | `/graph` (manual) | auto "this account's coordination" | account page + campaign | P2 |
| Cross-investigation correlation | — | none | none | "account in N investigations" | account + admin | P2 |
| Ecosystem/admin intelligence | aggregate over stores | none | none | recurring accounts/tags/campaigns | **Admin Intelligence** | P2 |
| Scan progress (real) | job status | — | **fake timer** | true stage from backend | progress component | **P0 (trust)** |

---

## 4. Campaign Intelligence Assessment — explicit answer

**Does Omi already possess the *foundation* of a Campaign Intelligence Library?
YES — the foundation, NO — the asset.**

- **What exists (foundation):** the account graph (`CoordinationEdge`, cumulative,
  with methods/observation_count/score), message themes (`Narrative`), per-content
  coordination trend (`ContentEntity`), the fingerprint memory loop, and full
  per-scan evidence (`Scan.signals_json`). Every *ingredient* of a campaign is
  already persisted **except the campaign itself**.
- **What is missing (the asset):** a first-class **Campaign** object that unifies an
  account-cluster + its methods + coordination score + hashtags/mentions + narrative
  theme + **recurrence** into one durable, queryable, **evolving** record. The
  per-scan cluster — the natural campaign seed — is computed and discarded; only its
  pairwise shadow survives. There is also no campaign↔campaign relationship and no
  cross-investigation correlation.
- **What should be renamed:** **do NOT rename Narratives → Campaigns.** Narratives is
  *message-cluster* intelligence; a campaign is an *account-cluster*. Renaming would
  mislabel it. Instead: group the coordination surfaces under one **"Coordination"**
  nav section — **Campaigns** (new, account-clusters), **Narratives** (themes), **Graph**
  (network). That is the grounded, non-blind restructure.
- **What should be restructured/surfaced:** materialize clusters as Campaigns;
  surface the discarded trust intelligence (weak signals, confidence, contributions,
  coordination evidence); fix fake scan progress.

**Campaign Library recommendation:** build the thin **Campaign** layer (model +
capture-on-detection + query API + a `/campaigns` page) that sits *on top of* the
existing `CoordinationEdge`/`Narrative` foundation — store **evidence/observations,
not verdicts**; each detection appends an observation and recomputes aggregates so
interpretation stays revisable. This is ~1 model-group + 1 service + 1 route + 1 page,
not a new engine. *(This is exactly the held prototype.)*

---

## 5. Memory Assessment

Implemented and real: `Account.fingerprint_json` + k-NN prior is the **only** cross-scan
learning loop, and it works within and across scans. Gated for anchoring (Trust
Boundary: profile-only fingerprints non-discriminative; Phase 0–1 made them
text-discriminative but the gate decision is still held). **Discarded memory
intelligence:** `matched_prior_neighbors` is computed and thrown away — surfacing it
("this account resembles N previously-flagged accounts") is free and high-trust.
`CoordinationEdge` is a *latent* memory the scorer never reads back — a future
campaign-recurrence signal.

---

## 6. Founder Testing Readiness Assessment

A founder can today: run a scan, see a verdict + tier + coordination rings + narratives
+ a manual graph + saved investigations + account history. **A founder canNOT, without
reading code:** see *why* a verdict (signed contributions/confidence/weak signals);
trust the progress bar (it's a fake timer); revisit a *campaign* (none persist);
discover that an account recurs across investigations; or — as admin — see what the
ecosystem is learning. **Readiness: usable for single scans; NOT ready for
"intelligence compounds over time" testing** until campaigns persist and the trust
panels are surfaced.

### Immediate UX trust issues (confirmed, all real)
1. **Fake scan progress** — `loading-overlay.tsx` advances 6 hardcoded stages on a ~3.5s timer, decoupled from the backend job. **Fix: drive stages from real `/scan/link/status` state.**
2. **Hidden confidence** — in schema, shown only in signal detail, absent from the verdict hero.
3. **Hidden evidence-for/against** — `DetectorContribution.direction` exists; not surfaced as a clear for/against split.
4. **Hidden detector contributions / weights** — computed, not shown as "why."
5. **Hidden coordination evidence + weak signals + score-adjustment reasons** — all in the payload, none rendered.

---

## 7. Top 20 Highest-Leverage Product Surface Improvements

| # | Improvement | Type | Effort | Priority |
|---|---|---|---|---|
| 1 | **Persist coordination clusters as Campaign records** | build | M | P0 |
| 2 | **Campaign Library page** (`/campaigns`) + API | build/surface | M | P0 |
| 3 | **Real scan progress** (backend-driven stages) | surface/fix | S | P0 |
| 4 | **"Why this verdict" panel**: signed contributions + confidence + weak signals | surface | S–M | P0 |
| 5 | Surface **evidence-for / evidence-against** split in result hero | surface | S | P0 |
| 6 | Persist + show **coordination-adjusted per-account verdict + evidence** | build | S | P1 |
| 7 | Surface **matched prior neighbors** ("resembles N flagged accounts") | surface | S | P1 |
| 8 | Surface **intent label** in the result hero (not just high-susp) | surface | S | P1 |
| 9 | **Group nav into "Coordination"** (Campaigns / Narratives / Graph) | rename/restructure | S | P1 |
| 10 | **Campaign recurrence** (member-overlap linking across scans) | build | M | P1 |
| 11 | Campaign detail: members, observations, hashtags, mentions, evidence | surface | S | P1 |
| 12 | **Account → campaigns/edges** ("appeared in N campaigns") | surface | M | P2 |
| 13 | **Cross-investigation correlation** (shared accounts/tags) | build | M | P2 |
| 14 | **Admin Intelligence dashboard** (recurring accounts/tags/campaigns) | build | M | P2 |
| 15 | Wire `co_tag` into `scan_video_full` (Phase 3 detector into production) | build | S | P1 |
| 16 | Show **uncertainty** explicitly ("not enough data" states) | surface | S | P1 |
| 17 | Persist thread-level + comments scans (today discarded) | build | S | P2 |
| 18 | **Weekly coordination report** from accumulated campaigns | build | M | P3 |
| 19 | **Publication/approval workflow** (human-reviewed notices) | build | L | P3 (defer) |
| 20 | Campaign confidence trend (evolves with observations) | build | S | P2 |

---

## 8. Recommendations

**1. Build (now, high-ROI, low-risk):** the **Campaign layer** (#1, #2, #10, #11) —
it's the single missing first-class object and unblocks library/memory/admin/reporting.
Prototype is built+tested, held for your go.
**2. Surface (no new systems, pure exposure of existing data):** the trust panels
(#3–#8, #16) and real scan progress — *highest trust ROI*, mostly frontend.
**3. Rename/restructure:** group nav under **Coordination** (Campaigns / Narratives /
Graph); **do not** rename Narratives → Campaigns (different grain).
**4. Remove/deprecate:** the **fake progress timer** (replace with real state); nothing
else — no capability should be deleted, only surfaced.
**5. Defer:** admin ecosystem dashboard (#14), cross-investigation graph (#13), weekly
reports (#18), and the public **publication/approval** layer (#19) — design first,
build after the Campaign layer + trust surfacing land and you've founder-tested them.

> The foundation is here and rich. The gap is not intelligence — it's **a first-class
> Campaign object + exposing the evidence the engine already computes.** Build one
> object; surface what exists.
