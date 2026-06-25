# OMI_EVIDENCE_BUNDLE_SPEC_V1 — The Canonical Evidence Object for Omi's Reasoning Layer

> **Status: engineering specification only.** No implementation, no production change,
> no detector / scoring / OmiScore / model / dataset / deployment change. This defines
> the **canonical Evidence Bundle** — the single, normalized, read-only object that
> sits between the deterministic engine and the **approved** Omi Cognitive Engine
> (`OMI_COGNITIVE_ENGINE_V1.md`). It does **not** redesign that architecture; it makes
> its §5 "Batch Evidence Bundle" sketch complete and canonical.
>
> Authoritative upstream context (read for ground truth):
> `ml/analyst/OMI_COGNITIVE_ENGINE_V1.md` (the approved architecture this serves —
> esp. §5/§6/§7), `ml/analyst/OMI_ANALYST_SPEC_V1.md` Appendix A (the per-grain
> projection), `ml/features/OMI_FEATURE_SCHEMA_V1.md` (A1–A12 — the authoritative
> inventory of every signal the engine emits), `ml/analyst/analyst_response_schema.json`
> (the citation/`evidence_refs` contract), the existing projection
> `ml/analyst/omi_analyst/evidence_bundle.py`, and the live engine in
> `apps/api/app/{detection,intelligence,narrative,graph,memory,campaigns,content}/`.

---

## 0. The contract this object enforces

The Evidence Bundle is **the single source of truth for AI reasoning** and the only
thing any reasoning module is ever allowed to see. Three non-negotiable properties
define it:

1. **Normalized, not raw.** The bundle is a *normalized projection* of what the engine
   already computed. **A reasoning module NEVER receives raw platform data** (a raw
   YouTube comment payload, an X API blob, a Reddit listing). If a fact can be
   expressed as a normalized `EvidenceItem`, it is — and the raw form never reaches the
   LLM. The **Binder** (§A) is the single choke point that touches raw data; everything
   downstream of it sees only normalized, pseudonymous evidence.
2. **Evidence, never verdict.** The bundle stores observations, probabilities,
   confidence, and *contradictions / missing data / unknowns* — never a persisted
   "this IS a bot/campaign" boolean (`VISION.md`, Platform Guardian §2). Engine numbers
   are **echoed** verbatim; nothing in the bundle is a recomputation, and nothing the
   reasoning layer later says is written back into it as truth.
3. **Total traceability.** Every atomic piece of evidence has a **unique id, source,
   confidence, timestamp, originating detector, and a traceability path** back to the
   observation that produced it. Reasoning modules **cite evidence ids, never
   free-form text** — and the Governor (`OMI_COGNITIVE_ENGINE_V1.md` §7) rejects any
   claim whose citation does not resolve.

> One line: **the Evidence Bundle is a content-addressed, normalized, append-only
> *evidence graph* — a flat index of atomic, fully-traced evidence items, plus typed
> entities and relationships that reference them by id — that the LLM consumes by
> citation and never bypasses.**

---

## Table of contents (maps to the brief's deliverables A–J)

- **A. Complete Evidence Bundle architecture** → §A
- **B. Schema hierarchy** (+ the 19 required evidence sections) → §B
- **C. Object relationships** → §C
- **D. Data flow** → §D
- **E. Traceability strategy** → §E
- **F. Evidence citation system** → §F
- **G. Extensibility strategy** → §G
- **H. Performance considerations** → §H
- **I. Future compatibility** → §I
- **J. Recommendation for long-term scalability** → §J
- Appendices: atomic `EvidenceItem` schema · the 19-section catalog · batch design ·
  worked example · mapping to existing code · open questions.

---

## A. Complete Evidence Bundle architecture

### A.1 The shape: a normalized evidence graph (not a nested document)

The single most important architectural decision — the one that delivers *minimize
duplication + complete traceability + cite exact evidence + batch efficiency all at
once* — is that the bundle is structured like a **normalized store**, not a deeply
nested blob:

- **One flat `evidence` index** (`id → EvidenceItem`): every atomic fact lives **exactly
  once**, addressed by a stable id. An account's temporal finding is one item, whether
  it is "about" the account, a cluster, and a narrative.
- **Typed `entities`** (accounts, content, clusters, campaigns, narratives): each stored
  **once**, referencing evidence by id — never embedding copies of it.
- **Typed `relationships`** (the batch graph): membership, authorship, co-occurrence,
  reply, cross-link, identity-link — edges that reference entities/evidence by id.
- **Per-grain `views`**: a reasoning module receives an *ordered list of ids* (its lens
  per `OMI_COGNITIVE_ENGINE_V1.md` §4.3), not a copy of the data.

Contrast with the naïve design (nesting 10k comment blobs inside a narrative inside a
campaign): that duplicates the same account across cluster/narrative/graph, blows up
linearly with batch size, and makes citation ambiguous. The normalized graph stores
each fact once and lets any module reach it by id in O(1).

### A.2 The envelope (top level)

```jsonc
EvidenceBundle {
  "bundle_meta":     {...},   // identity, version, integrity, capabilities (§B.1)
  "investigation":   {...},   // case metadata — why this bundle exists (§B.2 / INCLUDE 1)
  "entities":        {...},   // the subjects: accounts/content/clusters/campaigns/narratives (§C)
  "evidence":        {...},   // THE FLAT INDEX: id -> EvidenceItem (§Appendix-1) — all 11 facets
  "relationships":   [...],   // THE BATCH GRAPH: typed edges (§C / INCLUDE 18)
  "confidence":      {...},   // bundle- & item-level confidence metrics (§B / INCLUDE 13)
  "epistemics":      {...},   // contradictions + missing_evidence + unknowns (INCLUDE 14/15/16)
  "identity":        {...},   // cross-platform pseudonymous identifiers (§C / INCLUDE 19)
  "views":           {...},   // per-grain/per-module reasoning views = ordered id lists (§H)
  "citation_index":  {...}    // id -> location, for O(1) citation resolution (§F)
}
```

Every atomic fact is an `EvidenceItem` in `evidence`, tagged with a **facet** — one of
the eleven the brief enumerates: `behavioral · language · narrative · coordination ·
graph · metadata · historical · risk · detector · ml · label`. "Facets" are an *index
over the flat store*, not separate stores (no duplication). The 19 required INCLUDE
sections all land in this envelope (§B catalog).

### A.3 The Binder — the single normalization choke point

The **Binder** (named in `OMI_COGNITIVE_ENGINE_V1.md` §3, Tier 0) is the only component
that reads raw engine/platform output and writes the bundle. It is **deterministic,
computes nothing new** (it *projects* what the engine already produced), and is where
every invariant is enforced exactly once:

- assigns stable ids; emits atomic `EvidenceItem`s with full provenance (§E);
- deduplicates entities by pseudonymous identity; emits relationships;
- **pseudonymizes** (hashes handles/PII at the boundary — nothing past the Binder sees
  raw identity);
- computes `confidence` rollups and the `epistemics` layer (contradictions / missing /
  unknowns);
- computes `bundle_meta.bundle_id` (content hash → cache key + integrity seal);
- **never** lets raw platform text/objects through except as bounded, quoted
  `sample_text` evidence items (themselves traced and cited).

Because the Binder is the sole producer, the bundle is immutable and read-only to all
consumers; "records evolve" happens by producing a **new** bundle revision (§E.4), never
by mutating one in place.

---

## B. Schema hierarchy

### B.1 `bundle_meta` — identity, versioning, integrity, capabilities

```jsonc
bundle_meta {
  "bundle_id":        "sha256(canonical(bundle_without_this_field))",  // content address + integrity
  "bundle_schema_version": 1,                 // append-only; bump on any schema change
  "grain": "comment_section|account|account_history|campaign|coordination_cluster|narrative|investigation",
  "created_at":       "ISO-8601",
  "engine_version":   "...",                  // the detector/scoring engine build
  "feature_schema_version": 1,                // == app/ml/features.FEATURE_SCHEMA_VERSION
  "platforms":        ["youtube"],            // platforms represented (multi for cross-platform batches)
  "capabilities": {                            // which facets/detectors actually ran (ties to missing_evidence)
    "behavioral": true, "language": true, "coordination": true, "narrative": true,
    "graph": true, "metadata": true, "historical": false, "risk": true,
    "detector": true, "ml": false, "label": false
  },
  "counts": { "entities": 152, "evidence": 1840, "relationships": 410, "sample_texts": 60 },
  "redaction": "pseudonymous-v1"               // declares the PII policy applied at the Binder
}
```

`bundle_id` is the cache key (`OMI_COGNITIVE_ENGINE_V1.md` §10) and the tamper seal:
identical evidence ⇒ identical id ⇒ never re-reasoned. `capabilities` makes "what we
*could* assess" explicit, so absence is data, not silence (feeds `epistemics.missing`).

### B.2 The 19 required sections — where each lives

The brief's INCLUDE list maps 1:1 into the envelope. Full per-section schemas are in
**Appendix 2**; here is the index and the real engine source of each (per
`OMI_FEATURE_SCHEMA_V1` A1–A12):

| # | INCLUDE section | Lives in | Engine source |
|---|---|---|---|
| 1 | **Investigation metadata** | `investigation` | `Investigation` row + scan request context |
| 2 | **Account evidence** | `entities.accounts[]` + facet `behavioral`/`metadata` | `AccountScanOut`, `Profile`, `Account` |
| 3 | **Behavioral evidence** | facet `behavioral` | A1 fingerprint (21d) + A2 detectors + A4 `contributions`/`score_breakdown` |
| 4 | **Language evidence** | facet `language` | `semantic`,`voice`,`ai_writing`[supplemental] + bounded `sample_text` items |
| 5 | **Narrative evidence** | facet `narrative` | A7 `CoordinationScores` (8 signals + derived) |
| 6 | **Coordination evidence** | facet `coordination` | A6 clusters/methods + `aggregate.py` gate state |
| 7 | **Graph evidence** | facet `graph` | A6 `CoordinationEdge` + `networkx` centrality/components |
| 8 | **Metadata evidence** | facet `metadata` | A3 account metadata (followers/age/verified/post-count) |
| 9 | **Historical intelligence** | facet `historical` | A4 `TrendInfo` + `Scan`/`HistoricalScan` trajectory |
| 10 | **Risk indicators** | facet `risk` | A10 OmiScore dimensions + `intent_label`/`suspected_intent` |
| 11 | **Detector outputs** | facet `detector` | A2 raw `SignalResult{probability,confidence,evidence,supplemental}` |
| 12 | **Behavioral ML outputs** | facet `ml` | dormant `app/ml/scorer.py` learned axis / behavioral NN (one item, not a detector/verdict) |
| 13 | **Confidence metrics** | `confidence` (+ per-item `confidence`) | A11 cross-cutting confidence |
| 14 | **Contradictory evidence** | `epistemics.contradictions[]` | derived from signed `contributions` (raises vs lowers) + cross-grain conflict |
| 15 | **Missing evidence** | `epistemics.missing_evidence[]` | `weak_signals[]`, abstained detectors, `capabilities=false` |
| 16 | **Unknowns** | `epistemics.unknowns[]` | named non-derivable limits (domain shift, absent controls) |
| 17 | **Evidence references** | every `EvidenceItem.id` + `citation_index` | §E/§F — the cross-cutting traceability spine |
| 18 | **Batch relationships** | `relationships[]` | A6 edges, membership, authorship, reply, cross-link |
| 19 | **Cross-platform identifiers** | `identity` | pseudonymous per-platform refs + linkage map |

### B.3 The atomic unit — `EvidenceItem` (full schema in Appendix 1)

Everything in the eleven facets is the same shape, an `EvidenceItem`, carrying the six
**EVIDENCE REFERENCES** fields the brief requires (`id`, `source`, `confidence`,
`timestamp`, `originating_detector`, `traceability_path`) plus the doctrine fields
(`direction`, `supplemental`, `discriminative`, `subject_refs`, `provenance`). This
single type is what makes the bundle uniformly traceable and citable. See Appendix 1.

---

## C. Object relationships

Three record types and the edges between them — a small, closed relational model.

### C.1 Entities (the subjects)

```jsonc
Entity {
  "id": "acct:001 | content:001 | cluster:001 | campaign:001 | narrative:001 | commenter:001",
  "kind": "account|content|cluster|campaign|narrative|commenter",
  "ref":  "pseudonymous hash (never raw handle/PII)",
  "grain_role": "subject|member|context",      // is this the thing under investigation, a member, or context?
  "headline": { "probability": .., "tier": "..", "confidence": .. },  // ECHOED engine numbers (never recomputed)
  "evidence_refs": ["ev:0042", "ev:0043"],     // ids of EvidenceItems about this entity (index into the flat store)
  "platform": "youtube|twitter|reddit|unknown",
  "platform_ext": { ... }                      // platform-specific escape hatch (forward-compat, §G)
}
```

Entities **reference** evidence by id; they never embed it. The same account appearing
in a cluster, a narrative, and the graph is **one** `acct:001` record.

### C.2 Evidence → Entity (aboutness)

`EvidenceItem.subject_refs: [entity_id...]` — which entities a piece of evidence is
about. A coordination-cluster finding's `subject_refs` are the member accounts; a
sample-text item's `subject_refs` is the one author. This is the inverse of
`Entity.evidence_refs` (the Binder maintains both for O(1) traversal either way).

### C.3 Relationships (the batch graph)

```jsonc
Relationship {
  "id": "rel:0007",
  "type": "member_of | authored | replied_to | co_engaged | co_tagged | shares_fingerprint
           | cross_link | identity_link | amplified",
  "from": "<entity_id or evidence_id>",
  "to":   "<entity_id or evidence_id>",
  "weight": 0.0,                               // strength, ECHOED from the engine (e.g. CoordinationEdge.mean_cluster_score)
  "evidence_refs": ["ev:0310"],                // the EvidenceItem(s) that substantiate this edge
  "grain_boundary": false                      // true ⇒ this edge crosses grains (account<->message); never silent
}
```

Relationships are how **grains stay separate but linkable** (Platform Guardian §1; the
Cognitive Engine's "combine only via `cross_links`"). Account-coordination (pair/cluster
grain) and narrative (message grain) are **never merged** — they are joined by an
explicit `cross_link` relationship with `grain_boundary: true`, so any cross-grain
inference is visible and cited, never implicit.

### C.4 The relationship type catalog (grounded in real edges)

| `type` | from → to | Engine source |
|---|---|---|
| `member_of` | account → cluster/campaign/narrative | `CampaignMember`, `NarrativeMembership`, cluster membership |
| `authored` | account → content/comment | scan ingestion |
| `replied_to` | comment → comment | reply-pod detector (`reply_pods.py`) |
| `co_engaged` | account ↔ account | `co_engagement` detector |
| `co_tagged` | account ↔ account | `co_tag` detector |
| `shares_fingerprint` | account ↔ account | `fingerprint_cluster` / memory k-NN |
| `cross_link` | cluster ↔ narrative ↔ campaign | `CrossLink` / `convergence_score` |
| `identity_link` | account ↔ account (cross-platform) | identity resolution (§C.5 / future) |
| `amplified` | account → narrative/content | narrative spread signals |

### C.5 Identity (cross-platform identifiers)

```jsonc
identity {
  "entities": {
    "acct:001": {
      "platform_ids": [ { "platform": "youtube", "ref": "hash(yt:UC...)", "id_type": "channel" },
                        { "platform": "twitter", "ref": "hash(x:12345)",  "id_type": "user" } ],
      "linkage": [ { "to": "acct:007", "basis": "shares_fingerprint", "confidence": 0.72,
                     "evidence_refs": ["ev:0610"], "note": "similarity, NOT confirmed identity" } ]
    }
  },
  "resolution_policy": "pseudonymous-v1"        // never de-anonymize; linkage is similarity, not proof
}
```

Cross-platform identity is **similarity, never confirmed identity** (memory-k-NN
doctrine, A5). The bundle records *candidate* links with evidence + confidence, so a
reasoning module can reason about "this YouTube account behaves like that X account"
without ever asserting they are the same person, and without seeing any raw handle.

---

## D. Data flow

```
RAW PLATFORM DATA           YouTube / X / Reddit  (app/integrations/source.py adapters)
   │                        ── the ONLY layer that sees raw data ──
   ▼
NORMALIZED PLATFORM RECORDS Source protocol → platform-agnostic records
   ▼
DETERMINISTIC ENGINE        detection/* · coordination/* · narrative/* · graph/* · memory/* · intelligence/*
   │                        (Tier 0; computes probabilities, clusters, scores, fingerprints — UNCHANGED)
   ▼
┌───────────────────────────────────────────────────────────────────────────┐
│ THE BINDER (deterministic; the choke point)                                 │
│  • pseudonymize at the boundary (hash handles/PII)                          │
│  • emit atomic EvidenceItems  (id, source, confidence, timestamp,           │
│    originating_detector, traceability_path)  — projection, never recompute  │
│  • dedup entities; emit relationships (the batch graph)                     │
│  • echo engine numbers; compute confidence rollups                          │
│  • compute epistemics: contradictions / missing_evidence / unknowns         │
│  • seal: bundle_id = content hash                                           │
└───────────────────────────────┬───────────────────────────────────────────┘
                                 ▼
EVIDENCE BUNDLE (immutable · read-only · content-addressed · pseudonymous · no raw data)
                                 ▼
COGNITIVE ENGINE                 modules receive lens-filtered VIEWS (id lists) and
                                 CITE evidence ids → Governor resolves every citation
                                 (OMI_COGNITIVE_ENGINE_V1.md §4/§6/§7)
                                 ▼
ASSESSMENT (cached on the record, keyed by bundle_id; async; off the hot path)
```

The flow has exactly one place that touches raw data (the adapters/Binder) and exactly
one object the LLM sees (the bundle). That is what makes "the LLM must never receive raw
platform data" *structurally* true, not a guideline.

---

## E. Traceability strategy

### E.1 Every item carries its lineage
Each `EvidenceItem` has a `traceability_path` — an ordered chain from observation to
normalized fact:

```jsonc
"traceability_path": [
  { "stage": "source",       "ref": "scan:8842", "platform": "youtube", "at": "ISO-8601" },
  { "stage": "detector",     "ref": "temporal",  "version": "engine@1.x" },
  { "stage": "normalization","ref": "binder@1",  "transform": "SignalResult->EvidenceItem" }
]
```

A human or audit can walk the path back from any cited id to the exact scan + detector +
normalization step that produced it — and re-run the detector if needed. Paths reference
**hashed** ids + `scan_id`, never PII.

### E.2 The six required reference fields (brief: EVIDENCE REFERENCES)
Every item provides, as first-class fields: **`id`** (unique), **`source`** (store/facet
origin), **`confidence`** (0–1), **`timestamp`**, **`originating_detector`**, and the
**`traceability_path`** above. These are mandatory — the Binder rejects an item missing
any of them (a traceless fact cannot enter the single source of truth).

### E.3 Versioned and tamper-evident
Each item records `engine_version` + `feature_schema_version` + `detector_version` in
`provenance`; the envelope's `bundle_id` is a content hash over the whole normalized
bundle. A stale or altered bundle is detectable (id mismatch), and a consumer can refuse
a bundle whose `bundle_schema_version` it does not support.

### E.4 Records evolve by revision, never mutation
New evidence ⇒ the Binder produces a **new bundle** (new `bundle_id`) that may carry a
`supersedes: <prior_bundle_id>` pointer. Nothing is edited in place; the audit trail is
the chain of immutable bundle revisions (mirrors HF revisions / investigation
snapshots). This is the bundle-level expression of the platform's "no self-reinforcing
loop" doctrine — a prior conclusion is never fed back in as a new fact.

---

## F. Evidence citation system

### F.1 Identifier grammar
- **Entity ids:** `<kind>:<seq>` — `acct:001`, `content:001`, `cluster:001`,
  `campaign:001`, `narrative:001`, `commenter:001`.
- **Evidence ids:** `ev:<NNNN>` — flat, opaque, monotonic within a bundle. (Facet/scope
  are *fields* on the item, not encoded in the id, to keep the index normalized.)
- **Relationship ids:** `rel:<NNNN>`.
- **Content digest:** each item also carries `digest = sha256(canonical(value))` so
  identical evidence is detectable across bundles (global dedup, §H/§I).

### F.2 A citation
A reasoning module cites an **id**, optionally with a JSON-Pointer fragment into the
item's value for sub-field precision:

```
ev:0042                         → the whole evidence item
ev:0042#/value/interval_cov     → a specific normalized field within it
ev:0058#/value/samples/2        → the 3rd quoted sample text in a language item
```

This supersedes the V1 dotted-path convention in `analyst_response_schema.json`
(`signals.temporal`, `contributions.temporal`): those become resolvable ids. The schema's
`evidence_refs: [string]` arrays now carry `ev:NNNN[#pointer]` tokens.

### F.3 Resolution and enforcement
- The bundle ships a `citation_index` (`id → {facet, location, digest}`) for O(1)
  resolution.
- **Cite-or-be-dropped:** the Governor resolves every `evidence_ref` in every reasoning
  artifact against `citation_index`; an unresolvable ref is a fabrication (F1) →
  the claim is suppressed and, if load-bearing, the whole output is rejected to the
  Deterministic Floor (`OMI_COGNITIVE_ENGINE_V1.md` §7).
- **Quotes are citations.** Sample texts are `EvidenceItem`s (`facet: language`,
  `kind: sample_text`); a module quotes by citing the item id, never by pasting free
  text — so every quotation is itself traced and dedup-safe.
- **Echo fields are citations too.** `suspicion_probability`/`tier` in an assessment must
  cite the `headline` evidence id they were copied from, making echo-not-recompute (F8)
  machine-checkable.

---

## G. Extensibility strategy

1. **Append-only, versioned — never reorder/remove** (the discipline that keeps
   `build_feature_vector` train/serve-safe, `OMI_FEATURE_SCHEMA_V1` §E). New evidence ⇒
   append; bump `bundle_schema_version`; every artifact records the version it was built
   under.
2. **`kind`-typed items over an open registry.** A new detector emits a new
   `EvidenceItem.kind` + `originating_detector`; the envelope is unchanged. A consumer
   that does not understand a `kind` **ignores it** (forward-compatible) rather than
   breaking.
3. **Platform-agnostic core; platforms live only in adapters.** Adding Reddit / a new X
   surface is a **Source adapter** that emits the *same* normalized `EvidenceItem`s
   (ARCHITECTURE: "the only platform-specific seam is the Source protocol; the detection
   stack is platform-agnostic"). The bundle schema does not change per platform; a
   `platform` tag + `entity.platform_ext` escape hatch absorb platform specifics.
4. **Facets are an open index, not a closed enum at the envelope level.** New facet ⇒
   new tag value + a `capabilities` entry; existing consumers keep working.
5. **Capability-driven.** `bundle_meta.capabilities` declares what ran, so modules adapt
   to what is present and the absent is recorded (no silent gaps).
6. **The ML facet is pre-wired but optional.** The behavioral ML / NN learned axis enters
   as a single `facet: ml` item (a *learned axis*, never a detector or verdict, per
   `OMI_NEURAL_NETWORK_V1`); when the scorer is dormant the facet is simply absent
   (`capabilities.ml = false`) and that absence is in `missing_evidence`.

### G.1 What is forbidden to change (stability guarantees)
The atomic `EvidenceItem` reference fields (§E.2), the id grammar (§F.1), the
"evidence-not-verdict" rule, and the pseudonymity guarantee are **frozen**. Everything
else grows by addition. Consumers may rely on these never changing within a major
`bundle_schema_version`.

---

## H. Performance considerations

1. **Normalization kills the blow-up.** Storing each fact once (flat index + id
   references) means a batch with heavy overlap (one account across many
   clusters/narratives) does **not** duplicate that account's evidence N times — the
   decisive win for large discussions.
2. **Content-addressed caching.** `bundle_id` is the cache key; identical evidence is
   never re-reasoned, and the assessment is cached on the record keyed by it
   (`OMI_COGNITIVE_ENGINE_V1.md` §10).
3. **Summary-plus-drill-down (paged facets).** The bundle always carries section-level
   aggregates (tier distribution, cluster scores, narrative signals); per-item detail is
   reachable by id and **pageable**, so map-reduce over a 10k-comment section
   (`OMI_COGNITIVE_ENGINE_V1.md` §10.4) reads aggregates + a stratified sample, not the
   whole index.
4. **Views are id lists, not copies.** A module's lens is an ordered list of ids; the
   prompt serializes only the cited items, not the whole bundle — essential for staying
   inside LLM context limits over big batches.
5. **Representative sampling, bounded and stratified.** `sample_text` items are capped
   and **stratified by tier/cluster/author** (the existing projection already caps to
   5–6; this formalizes *which* to keep), so a module always sees a faithful, bounded
   slice rather than a truncation.
6. **Streaming assembly.** The Binder emits facets incrementally as detectors finish; a
   consumer can begin on `behavioral` while `graph` is still being assembled.
7. **Cheap integrity.** Per-item `digest` + envelope `bundle_id` are hashes computed once
   at bind time; resolution and dedup are O(1) lookups, not re-derivation.

---

## I. Future compatibility

| Future change | Cost | Why it's absorbed |
|---|---|---|
| **New platform** (Reddit, TikTok, new X surface) | adapter only | platform-agnostic core; same `EvidenceItem`s; `platform` tag + `platform_ext` |
| **New detector** | append a `kind` | open `kind` registry; unknown kinds ignored |
| **Behavioral ML / NN goes live** | one `facet: ml` item | pre-wired optional facet; learned axis, not a detector/verdict |
| **New reasoning module** | new `view` (id list) | views are derived; bundle unchanged |
| **Fine-tuned Analyst V3+** | none | the bundle is the **stable training input**; targets stay engine-independent (`future_finetuning_strategy.md`) |
| **Cross-platform identity store** | grow `identity` | linkage is similarity + evidence, append-only; never de-anonymizes |
| **Schema v2** | bump + append | append-only guarantee; consumers pin `bundle_schema_version` |
| **New grain** (e.g. `subreddit_history`) | add a grain value + a view | grain is a tag; relationships already generalize |

The bundle is deliberately the **slow-moving contract** in a fast-moving system:
platforms, detectors, models, and reasoning modules all evolve around it without forcing
a schema break — the same role `build_feature_vector` plays for the behavioral model.

---

## J. Recommendation for long-term scalability

**Make the Evidence Bundle a normalized, content-addressed, append-only evidence graph,
produced by a single Binder choke point, and treat it as the one frozen contract the
entire Cognitive Engine is built on.** Concretely, over the 5-year horizon:

1. **Persist bundles as immutable, content-addressed artifacts** (like investigation
   snapshots / HF revisions), keyed by `bundle_id`, with `supersedes` chains. This makes
   every assessment **replayable** for evaluation, training, and audit — and turns the
   bundle into the natural unit for the analyst-eval set and the V3 gold dataset
   (`OMI_COGNITIVE_ENGINE_V1.md` §11). *A stored bundle is a reusable training/eval
   example for free.*
2. **Keep the bundle the only surface the Cognitive Engine sees.** One contract to
   govern means one place to enforce no-raw-data, no-PII, citation-resolvability, and
   evidence-not-verdict. Every safety property becomes a property of *one object*.
3. **Version like the Feature Schema: append-only, never reorder, record the version in
   every artifact, refuse on mismatch.** This is the discipline that has already kept
   Omi's train/serve contract honest; apply it verbatim here.
4. **Normalize ruthlessly; let relationships carry all cross-grain joins.** Duplication
   is the enemy of both batch performance and traceability; the flat index + typed
   relationships solve both, and keep account/message/campaign grains separate-but-linked
   (Platform Guardian §1).
5. **Pseudonymize at the Binder, once.** Identity resolution grows as *evidence-backed
   similarity links*, never as de-anonymization — so the bundle can scale to
   cross-platform reasoning without ever becoming a surveillance object (`VISION.md`:
   not an accusation engine).

> In one line: **the Evidence Bundle wins long-term not by holding more data, but by
> holding each fact exactly once, fully traced, behind one normalization choke point —
> a frozen, versioned, content-addressed contract that every platform, detector, model,
> and reasoning module can evolve around without breaking.**

---

## Appendix 1 — The atomic `EvidenceItem` schema

```jsonc
EvidenceItem {
  // ---- identity & required reference fields (brief: EVIDENCE REFERENCES) ----
  "id":            "ev:0042",                  // unique within the bundle
  "digest":        "sha256(canonical(value))", // global content address (cross-bundle dedup)
  "facet":         "behavioral|language|narrative|coordination|graph|metadata|historical|risk|detector|ml|label",
  "kind":          "detector_signal|contribution|score_breakdown|fingerprint|coordination_cluster|
                    coordination_method|narrative_signal|graph_metric|graph_edge|metadata_fact|
                    trend|risk_dimension|intent|ml_axis|sample_text|label|control",
  "source":        "detection.temporal | coordination.aggregate | narrative.coordination | graph.service |
                    memory.knn | intelligence.omiscore | ml.scorer | labels.investigation",
  "originating_detector": "temporal",          // the specific detector/method/model
  "confidence":    0.0,                         // 0–1, engine-provided (data sufficiency)
  "timestamp":     "ISO-8601",                  // when observed/computed
  "traceability_path": [ {stage, ref, version, at}, ... ],   // §E.1
  "provenance":    { "platform": "youtube", "scan_id": "hash", "engine_version": "...",
                     "feature_schema_version": 1, "redaction": "pseudonymous-v1" },

  // ---- aboutness & doctrine flags ----
  "subject_refs":  ["acct:001"],               // which entities this is about
  "direction":     "raises|lowers|neutral",    // signed attribution where applicable (DetectorContribution.direction)
  "supplemental":  false,                       // true ⇒ context only, ZERO suspicion weight (e.g. ai_writing) — E7/F6
  "discriminative": null,                       // for coordination methods: true=fingerprint/co_engagement/co_tag

  // ---- the normalized payload (typed by `kind`) ----
  "value":         { ... },                     // e.g. {probability, impact, logit_delta, decorrelation_factor}
  "label":         "human-readable name",       // e.g. "posting cadence" (intelligence._DETECTOR_LABELS)
  "note":          "plain-language, probabilistic, behavior-not-persons"
}
```

**Rules:** an item missing any required reference field is rejected by the Binder; a
`supplemental` item may never appear with positive suspicion weight; an item's `value`
**echoes** the engine and is never recomputed; raw text appears only in
`kind: sample_text` items, bounded and quoted.

## Appendix 2 — The 19-section catalog (schemas, grounded in A1–A12)

Condensed; each is a set of `EvidenceItem`s in the named facet unless noted.

1. **Investigation metadata** (`investigation`): `{ id, slug(hash), created_at,
   requested_by(hash), input_kind, platform(s), scope(grain), engine_version,
   bundle_id, status }`. Case context only — never a verdict.
2. **Account evidence** (`entities.accounts[]`): the `Entity` (§C.1) + its
   `behavioral`/`metadata`/`language` evidence ids. Echoed headline; no recompute.
3. **Behavioral** (`facet:behavioral`): A1 fingerprint (21 named dims, normalized
   [0,1]), A2 detector `(probability,confidence)` pairs, A4 `contributions`
   (`impact, logit_delta, direction, decorrelation_factor, supplemental`) + the
   `score_breakdown` item (prior→posterior logits, `single_axis_capped`,
   `convergence_bonus_logit`).
4. **Language** (`facet:language`): `semantic`/`voice` signals, `ai_writing`
   (**supplemental**), and bounded stratified `sample_text` items (quoted, traced).
5. **Narrative** (`facet:narrative`): A7 `CoordinationScores` — the 8 weighted signals
   + `coordination_score, cluster_confidence, narrative_corroboration,
   manipulation_probability, coordination_label, risk_tier` + `member_count,
   distinct_authors, spread_ratio`. Message grain.
6. **Coordination** (`facet:coordination`): per-method `DetectorContribution`
   (`method, score, confidence, reliability, evidence`), `CoordinationCluster`
   (`method, members, score, evidence`), and the **gate state**
   (`discriminative_methods, single_axis_capped/gated, convergence`). Pair/cluster grain.
7. **Graph** (`facet:graph`): `CoordinationEdge` (`observation_count, methods,
   mean_cluster_score, last_shared_parent`) as `graph_edge` items + component/centrality
   `graph_metric` items.
8. **Metadata** (`facet:metadata`): A3 `meta_log_followers/following/account_age_days,
   meta_verified, meta_log_post_count`, platform, creation cohort.
9. **Historical intelligence** (`facet:historical`): A4 `TrendInfo{direction, summary,
   scan_count}` + per-scan trajectory. **Trajectory is context, never fed back as a new
   suspicion fact** (no self-reinforcing loop).
10. **Risk indicators** (`facet:risk`): A10 OmiScore dimensions
    (`coordination_probability, amplification_probability, spam_probability,
    ai_generation_probability, authenticity_score, risk_level`) + `intent_label`.
    Reported as **indicators with evidence**, not as a second verdict.
11. **Detector outputs** (`facet:detector`): the raw A2 `SignalResult` set
    (`probability, confidence, evidence[], sub_signals{}, supplemental`) — the unblended
    detector block.
12. **Behavioral ML outputs** (`facet:ml`): one `ml_axis` item when the learned
    scorer/NN is live (`model_id, revision, score, confidence, blend_weight`), explicitly
    a **learned axis, not a detector or verdict**; absent + recorded in `missing` when
    dormant.
13. **Confidence metrics** (`confidence` + per-item): bundle-level
    `{ data_sufficiency, corroboration_count, conflict_magnitude, domain_shift_flag,
    capabilities_coverage }` + each item's own `confidence`. Separate from suspicion.
14. **Contradictory evidence** (`epistemics.contradictions[]`):
    `{ id, between: [ev_id, ev_id], kind: raises_vs_lowers|cross_grain|method_conflict,
    note }` — the engine's signed `raises`/`lowers` and any cross-grain tension made
    **explicit pairs**, never silently netted (supports the Red Team, §G of the
    Cognitive Engine).
15. **Missing evidence** (`epistemics.missing_evidence[]`):
    `{ what, why: abstained_detector|thin_data|capability_off, expected_facet,
    weak_signal_ref }` — from `weak_signals[]`, abstained detectors (absent ⇒
    `(0.5,0.0)`), and `capabilities=false`. What the engine *couldn't* establish.
16. **Unknowns** (`epistemics.unknowns[]`): `{ statement, basis }` — named limits not
    derivable from this bundle at all (domain shift, no legitimate-coordination control
    available, identity unconfirmable). The honesty floor.
17. **Evidence references**: the `id`/`digest`/`citation_index` spine (§F) — every item
    addressable, every claim citable.
18. **Batch relationships** (`relationships[]`): §C.3 typed edges — the graph that makes
    batch reasoning relational.
19. **Cross-platform identifiers** (`identity`): §C.5 — pseudonymous per-platform refs +
    evidence-backed similarity links (never confirmed identity).

## Appendix 3 — Batch organization (entire discussions, histories, campaigns, clusters)

The bundle is **batch-native**; the `grain` tag selects how entities/relationships are
populated, but the envelope is identical across batch types:

| Batch type | `grain` | subject entity | members | key relationships | representative sampling |
|---|---|---|---|---|---|
| **YouTube discussion / comment section** | `comment_section` | `content:001` (video) | commenter accounts | `authored`, `replied_to`, `co_engaged`, `member_of` (pods) | stratify samples by tier + reply-pod |
| **Reddit discussion** | `comment_section` | `content:001` (thread) | commenter accounts | `replied_to` (tree), `co_engaged` | stratify by subtree + tier |
| **X conversation** | `comment_section` | `content:001` (root post) | repliers/quoters | `replied_to`, `co_tagged`, `amplified` | stratify by branch + tier |
| **Account history** | `account_history` | `acct:001` | the account's scans | `authored` over time; `historical` trend | sample posts across the time span |
| **Investigation** | `investigation` | the case | accounts + clusters + narratives | `cross_link` across components | per-component headline + drill-down |
| **Campaign** | `campaign` | `campaign:001` | member accounts | `member_of`, `shares_fingerprint`, `co_engaged` | sample members by centrality + authenticity |
| **Coordination cluster** | `coordination_cluster` | `cluster:001` | member accounts | `member_of`, the firing methods | sample by method contribution |

For very large batches, the **summary-plus-drill-down** rule (§H.3) applies: section
aggregates are always present in full; per-entity/per-item detail is pageable by id so a
map-reduce reasoning pass (`OMI_COGNITIVE_ENGINE_V1.md` §10.4) reads aggregates + a
bounded stratified sample, never the whole index.

## Appendix 4 — Worked example (abridged, a 3-account co-engagement cluster)

```jsonc
{
  "bundle_meta": { "bundle_id": "b1f3…", "grain": "coordination_cluster",
                   "platforms": ["youtube"], "capabilities": { "coordination": true, "ml": false } },
  "investigation": { "slug": "inv_77c1", "scope": "coordination_cluster", "platform": "youtube" },
  "entities": {
    "cluster:001": { "kind": "cluster", "grain_role": "subject",
                     "headline": { "probability": 0.66, "confidence": 0.55 },
                     "evidence_refs": ["ev:0300","ev:0301"] },
    "acct:001": { "kind": "account", "grain_role": "member", "ref": "h:9f3a",
                  "headline": { "probability": 0.71, "tier": "elevated" }, "evidence_refs": ["ev:0104"] }
    // acct:002, acct:003 …
  },
  "evidence": {
    "ev:0300": { "facet": "coordination", "kind": "coordination_method", "source": "coordination.aggregate",
                 "originating_detector": "co_engagement", "discriminative": true, "confidence": 0.58,
                 "subject_refs": ["cluster:001"], "value": { "score": 0.66, "members": 3 },
                 "traceability_path": [ {"stage":"detector","ref":"co_engagement"} ] },
    "ev:0104": { "facet": "behavioral", "kind": "contribution", "source": "detection.temporal",
                 "originating_detector": "temporal", "direction": "raises", "confidence": 0.5,
                 "subject_refs": ["acct:001"], "value": { "impact": 0.61, "logit_delta": 0.8 } }
  },
  "relationships": [
    { "id": "rel:001", "type": "member_of", "from": "acct:001", "to": "cluster:001", "evidence_refs": ["ev:0300"] },
    { "id": "rel:002", "type": "co_engaged", "from": "acct:001", "to": "acct:002", "weight": 0.66,
      "evidence_refs": ["ev:0300"] }
  ],
  "confidence": { "data_sufficiency": 0.55, "corroboration_count": 1, "conflict_magnitude": 0.1 },
  "epistemics": {
    "contradictions": [],
    "missing_evidence": [ { "what": "member account histories", "why": "thin_data", "expected_facet": "historical" } ],
    "unknowns": [ { "statement": "No legitimate-coordination control available to rule out a benign on-message group.",
                    "basis": "absent_control" } ]
  },
  "identity": { "resolution_policy": "pseudonymous-v1" }
}
```

A reasoning module then cites `ev:0300` for the co-engagement claim and is *required* to
address `epistemics.unknowns[0]` (the benign-coordination control) before it may
recommend `coordinated` — and it can't, because `corroboration_count == 1` and only one
discriminative method fired (the gate, carried as evidence).

## Appendix 5 — Mapping to existing code (continuity, not rewrite)

| This spec | Existing today | Relationship |
|---|---|---|
| `EvidenceBundle` envelope | `OMI_COGNITIVE_ENGINE_V1.md` §5 sketch | **canonicalizes** it |
| per-grain `project_*` | `ml/analyst/omi_analyst/evidence_bundle.py` | the V1 single-grain projection → **generalized** to the normalized graph; keep as the bootstrap producer |
| `EvidenceItem` facets | `OMI_FEATURE_SCHEMA_V1` A1–A12 | A1–A12 are the **source inventory**; each becomes typed items |
| citation `evidence_refs` | `analyst_response_schema.json` `evidenceItem.evidence_refs` | dotted paths → resolvable `ev:NNNN` ids |
| the Binder | (new, deterministic) | the one new component; **computes nothing**, projects + seals |
| no-raw-data / no-PII | `app/integrations/source.py` + pseudonymity rules | enforced **once**, at the Binder boundary |

## Appendix 6 — Open specification questions (none blocks this spec)
1. **Id stability across revisions** — are `ev:NNNN` stable when a bundle is
   re-bound with new evidence, or only `digest` is? (Recommend: `digest` is the durable
   cross-revision identity; `ev:NNNN` is per-bundle.)
2. **Sample-text sampling policy** — exact stratification weights for huge sections
   (tier × cluster × author) and the per-bundle cap.
3. **Persistence format** — JSON for the contract; consider a columnar/SQLite sidecar for
   very large batches (drill-down paging) — implementation detail, out of spec scope.
4. **`platform_ext` governance** — what may live in the escape hatch without leaking raw
   data or PII (must stay normalized + pseudonymous).
5. **Confidence rollup formula** — the exact bundle-level `data_sufficiency` aggregation
   (recommend: a weakest-link / min over present facets, not a mean — honesty-first).

---

*Engineering specification only. No production code, scoring, detector, model, dataset,
or deployment was changed by this document. The Evidence Bundle is a read-only,
normalized, content-addressed projection of evidence the engine already computed; it
adds no detection capability and asserts no verdict.*
