# OMI_INTELLIGENCE_MEMORY_SYSTEM_V1 — Omi's Permanent Institutional Intelligence

> **Status: canonical engineering specification only.** No implementation, no
> production change, no detector / scoring / OmiScore / model / dataset / deployment
> change. This designs Omi's **Intelligence Memory System** — the *second* major input
> to the **approved, frozen** Cognitive Engine, alongside the Evidence Bundle. It does
> **not** redesign either frozen document; it adds the institutional-memory layer they
> already foreshadow ("Analyst Memory … cited as *context not proof*",
> `OMI_COGNITIVE_ENGINE_V1.md` §11; the Evidence Bundle's `controls` + `identity`
> sections "from V2+ memory", `OMI_EVIDENCE_BUNDLE_SPEC_V1.md` §B/§C).
>
> **This is NOT conversational memory and NOT LLM context memory.** It is Omi's
> permanent, falsifiable, evidence-backed institutional intelligence — a knowledge
> graph that accumulates across investigations **without retraining the model**.
>
> Frozen upstream contracts (do not redesign): `OMI_COGNITIVE_ENGINE_V1.md`,
> `OMI_EVIDENCE_BUNDLE_SPEC_V1.md`. Ground-truth context:
> `ml/features/OMI_FEATURE_SCHEMA_V1.md` (A5 memory/k-NN, A6 coordination, A7
> narrative, A8 campaign, A12 labels), and the live stores in
> `apps/api/app/memory/` (`fingerprint.py`, `prior.py`), `app/storage/models.py`
> (`Campaign`, `CampaignObservation`, `CoordinationEdge`, `Narrative`, `AccountLabel`).

---

## 0. The three hard lines that govern everything

The danger of any memory system on this platform is the platform's oldest enemy: the
**self-reinforcing loop** — investigation N concludes "X is coordinated" → that
conclusion is stored → investigation N+1 reads it as evidence → "confirms" it →
forever. That is the exact failure `VISION.md`, the Platform Guardian (§2), and the
Cognitive Engine's "no self-reinforcing loop" doctrine (§11, V5's named danger) all
forbid. So three hard lines define this system and are enforced in every section:

1. **Memory stores EVIDENCE and OBSERVED PATTERNS — never VERDICTS.** A knowledge
   object is never "Campaign X *is* a manipulation network." It is "a recurring
   co-engagement + fingerprint-sharing pattern observed across N independent
   investigations, with M supporting and K *contradicting*, confidence 0.6, decaying."
   This is the engine's "measurements that future observations can move, **not a
   verdict**" rule (literally the existing `Campaign` model's docstring) raised to the
   institutional grain.
2. **Only evidence-backed investigations may WRITE. The LLM never writes.** The write
   sources are exactly two: the deterministic, content-addressed **Evidence Bundle**
   (frozen) and **human/platform ground-truth anchors** (`Investigation.verdict`,
   `AccountLabel`, platform disclosures). **A Cognitive-Engine assessment — an LLM
   interpretation — is NEVER a write source.** Knowledge is never created from LLM
   opinion (the brief's absolute rule). The model *reads* memory; it never *feeds*
   memory.
3. **Memory enters reasoning as CITED CONTEXT — never as PROOF.** Retrieved knowledge
   is a *prior/similarity*, clearly labeled, that may **frame** a hypothesis,
   **exculpate**, or **lower confidence** — but may **never** change the engine's
   echoed `suspicion_probability`/`tier`, and **never by itself** satisfy the
   corroboration gate. Historical intelligence *influences but never overrides* current
   evidence (§E).

> One line: **the Intelligence Memory is the institution's falsifiable notebook —
> written only from evidence and human anchors, read only as cited context, decaying
> and contradiction-tracked so it can never harden into self-fulfilling prophecy.**

### 0.1 This is a unification, not an invention (continuity with the live engine)
Omi already keeps primitive institutional memory, and already in the right doctrine.
This spec **canonicalizes and unifies** what exists:

| Existing store | What it already does | Becomes |
|---|---|---|
| `Account.fingerprint_json` + k-NN (`memory/prior.py`) | "every scan grows the reference set future scans compare against"; similarity-not-identity; confidence saturates | `LinguisticFingerprint` / `BehavioralArchetype` knowledge + the retrieval index |
| `CoordinationEdge` | cumulative cross-scan pairs (`observation_count`, running mean, first/last observed) | `CoordinationFingerprint` + graph edges |
| `Campaign` / `CampaignMember` | "measurements future observations can move, **not a verdict**"; `observation_count` recurrence | `Campaign` knowledge node |
| `CampaignObservation` | "raw evidence retained so aggregates can be **recomputed and history never overwritten**" | the per-object **observation ledger** (§D) |
| `Narrative` | running-centroid message cluster, incremental update | `NarrativeTemplate` knowledge |
| `AccountLabel` | provenance-weighted human truth; "disagreement is itself a signal" | the human-anchor **write source** + review signal |

The doctrine (measurements-not-verdicts, recompute-don't-overwrite, observation
provenance, contradiction-as-signal, similarity-not-identity) is **already practiced**;
this spec elevates it from six scattered stores into one falsifiable graph that becomes
the Cognitive Engine's second input.

---

## Table of contents (maps to the brief's deliverables A–J)

- **A. Complete Intelligence Memory architecture** → §A
- **B. Knowledge Graph architecture** (taxonomy) → §B
- **C. Knowledge object schemas** → §C
- **D. Learning lifecycle** → §D
- **E. Cognitive Engine integration** → §E
- **F. Governance and validation** → §F
- **G. Scalability strategy** → §G
- **H. Future training compatibility** → §H
- **I. Long-term roadmap** → §I
- **J. Recommendation (highest-ceiling, 10-year)** → §J
- Appendices: full `KnowledgeObject` schema · edge catalog · write-path state machine ·
  retrieval contract · mapping to existing stores · worked example · open questions.

---

## A. Complete Intelligence Memory architecture

### A.1 Where it sits — the second input

```
                          ┌──────────────────────────────────────────────┐
  CURRENT EVIDENCE  ───►   │                                              │
  (Evidence Bundle,       │           COGNITIVE ENGINE                    │ ───► assessment
   frozen, per-case)      │        (frozen — Analyst Council)             │      (cached; async)
                          │                                              │
  INSTITUTIONAL  ─────►   │   reasons over BOTH inputs, cites BOTH        │
  INTELLIGENCE            └──────────────────────────────────────────────┘
  (PriorContext,                         ▲                 │
   retrieved per-case)                   │ read (cited)    │ write (evidence + human anchors ONLY)
                          ┌──────────────┴─────────────────▼──────────────┐
                          │     INTELLIGENCE MEMORY SYSTEM (this spec)     │
                          │  Knowledge Graph · Observation Ledgers ·       │
                          │  Retrieval · Decay/Contradiction Governance    │
                          └────────────────────────────────────────────────┘
```

The Cognitive Engine consumes **two** inputs and cites both: the per-case **Evidence
Bundle** (current evidence) and a per-case **PriorContext** (institutional
intelligence, retrieved deterministically). The memory both **feeds** new bundles'
already-specced `controls`/`identity` sections and **supplies** the richer PriorContext
channel — so nothing in the frozen docs changes; this layer plugs into seams they
already defined.

### A.2 The five components

1. **Knowledge Graph** — the canonical store of institutional knowledge objects (nodes)
   and their relationships (edges). §B/§C.
2. **Observation Ledgers** — per-object append-only logs of the *evidence events* that
   formed it (the generalization of `CampaignObservation`: "history never
   overwritten"). Aggregates are always *recomputed* from the ledger, never mutated in
   place. §D.
3. **The Intake (write path)** — the deterministic, evidence-gated process that turns a
   *settled* investigation (Evidence Bundle + human anchor) into create/update/merge/
   retire operations. **The only writer. Never the LLM.** §D.
4. **Retrieval (read path)** — a deterministic query that, given the current Evidence
   Bundle, returns a bounded, ranked, cited **PriorContext**. The LLM never queries
   memory freely (preserves the Evidence Bundle's "no fetch/no tools" property). §E.
5. **Governance** — confidence decay, contradiction handling, human review, evidence
   thresholds, falsifiability/retirement, precision-frontier FPR gate. §F.

### A.3 The defining invariant
**Every knowledge object is, itself, an Evidence Bundle citizen.** Its confidence is
reconstructable from its Observation Ledger (which cites `EvidenceItem` *digests* from
the frozen bundles) exactly the way an OmiScore is reconstructable from `score_breakdown`.
No knowledge object carries a confidence that cannot be traced back to specific evidence
in specific investigations. There is no "black-box institutional belief."

---

## B. Knowledge Graph architecture

A typed property graph. I keep the brief's catalog but **organize it by epistemic
role** (cleaner and more defensible than a flat list), in five families.

### B.1 Node families

**Family 1 — Actors & Entities (the "who")**
- `Account` — a persistent pseudonymous account identity seen across investigations
  (generalizes the existing `Account` memory).
- `Organization` — an attributed real entity (state media, PR firm). Attribution is
  always evidence-graded and human-gated.
- `ThreatActor` — a hypothesized/attributed actor behind operations. Highest evidence
  bar; never reaches "confirmed", only "attributed-with-evidence".
- `Community` — an organic/semi-organic group. **Many are legitimate** — this family is
  also where benign groups live (precision frontier).

**Family 2 — Operations & Structures (the "what was done")**
- `Campaign` — a materialized coordinated operation (generalizes the `Campaign` store).
- `CoordinationCluster` — a recurring coordinated structure.
- `Event` — a real-world event investigations cluster around (election, launch, crisis).

**Family 3 — Patterns & Signatures (the "how" — the reusable intelligence)**
- `BehavioralArchetype` — a recurring behavior pattern ("burst-then-dormant amplifier").
- `ManipulationTechnique` — a named tactic ("reply-pod brigading", "hashtag hijacking").
- `NarrativeTemplate` — a recurring framing/message pattern (generalizes `Narrative`).
- `LinguisticFingerprint` — a recurring stylometric signature (generalizes the 21-d
  fingerprint centroid + k-NN).
- `CoordinationFingerprint` — a recurring coordination method-signature (generalizes
  `CoordinationEdge` method sets).
- `GraphFingerprint` — a recurring network topology (hub-and-spoke, dense pod, bridge).
- `PlatformBehavior` — platform-specific norms/patterns (so a YouTube norm isn't read as
  an X anomaly).

**Family 4 — Topics & External Context (the "about what")**
- `Topic` — a subject/claim domain (Omi is **not** a truth machine — topics are
  context, never a label of truth/falsity).
- `Event` (shared with F2 as context anchor).
- `ExternalIntelligenceReference` — a pointer to external OSINT/disclosure (state-actor
  archives, research reports) used as a corroboration anchor.

**Family 5 — Provenance & Controls (the epistemic backbone)**
- `HistoricalInvestigation` — the immutable provenance anchor; every object traces to a
  set of these (each referencing a content-addressed Evidence Bundle).
- `LegitimateCoordinationControl` — **known-benign** patterns (newsrooms, fandoms,
  official on-message networks). A *first-class node type* so memory actively
  **prevents false positives** — the Phase-3 precision frontier made institutional.

### B.2 The improvement over the brief's list
Three deliberate additions: (1) **`LegitimateCoordinationControl` as a first-class
family** — memory's job is as much to exonerate as to flag; (2) the **epistemic-role
grouping** so the graph's structure encodes *how much each kind of node may influence
reasoning* (Family 3 patterns are reusable lenses; Family 1/2 actors/ops are
case-specific and lower-leverage); (3) **`PlatformBehavior`** as an explicit node so
cross-platform reasoning has a place to hold platform norms rather than mislabeling
them.

### B.3 Edge catalog (knowledge relationships)
| Edge | from → to | Meaning |
|---|---|---|
| `exhibits` | Account → Archetype/LinguisticFingerprint | account shows a pattern |
| `member_of` | Account → Campaign/Community | participation |
| `employs` | Campaign/ThreatActor → ManipulationTechnique | tactic use |
| `instance_of` | Campaign → CoordinationFingerprint; Narrative → NarrativeTemplate | a concrete case of a reusable pattern |
| `attributed_to` | Campaign → ThreatActor/Organization | **evidence-graded, human-gated**, usually low-confidence |
| `targets` | Campaign → Topic/Event/Community | what an operation acted on |
| `similar_to` | object ↔ object | shared signature (vector-retrieved) |
| `contradicts` | object ↔ object | one's evidence undercuts the other (falsifiability) |
| `bounded_by` | suspicious pattern → LegitimateCoordinationControl | "looks like X but matches benign control Y" |
| `observed_in` | any object → HistoricalInvestigation | **the provenance edges** |
| `corroborated_by` | object → ExternalIntelligenceReference | external anchor |
| `supersedes` | object → object | versioning/merge |

`contradicts` and `bounded_by` are first-class — the graph is built to hold
*disagreement* and *exculpation*, not just accumulation.

---

## C. Knowledge object schemas

### C.1 The base `KnowledgeObject` (every node)
Includes every field the brief requires plus the doctrine fields that keep it
falsifiable. Full schema in **Appendix 1**; the spine:

```jsonc
KnowledgeObject {
  // --- identity ---
  "id":            "ko:lingfp:000123",          // stable, type-prefixed
  "type":          "LinguisticFingerprint",     // §B taxonomy
  "family":        "patterns_signatures",
  "label":         "human-readable, behavior-not-persons",

  // --- the two epistemic axes (kept distinct) ---
  "confidence":    0.62,                          // how strongly evidence supports it NOW (raised by independent
                                                  // corroboration, lowered by contradiction + decay)
  "stability_score": 0.71,                        // how CONSISTENT its characterization has been across observations
                                                  // (low variance = stable; high churn = unstable). Different axis.
  "epistemic_status": "observed",                 // hypothesized → observed → corroborated → attributed
                                                  //  (+ retired/superseded). NEVER "confirmed truth".

  // --- evidence tally (falsifiability core) ---
  "evidence_count":            34,                // distinct EvidenceItems across investigations (deduped)
  "supporting_investigations": ["hist:8a..", ...],// HistoricalInvestigation ids that support it
  "contradicting_investigations": ["hist:c1.."], // ids whose evidence CONTRADICTS it (first-class, never dropped)
  "evidence_refs":             ["evd:digest..", ...], // EvidenceItem DIGESTS from frozen bundles (full traceability)

  // --- time & uncertainty evolution ---
  "first_observed":  "ISO-8601",
  "last_observed":   "ISO-8601",
  "last_updated":    "ISO-8601",
  "confidence_decay": { "half_life_days": 180, "last_decayed_at": "ISO-8601" },

  // --- lifecycle / revisability ---
  "provenance":         { "created_by": "intake@m2", "write_sources": ["evidence_bundle","human_anchor"],
                          "never": "llm_opinion" },
  "retirement_criteria":{ "confidence_floor": 0.15, "max_contradiction_ratio": 0.4,
                          "stale_after_days": 540, "human_retire": true },
  "superseded_by":  null,                         // ko id if merged/replaced
  "version_history":[ { "rev": 1, "at": "..", "change": "created", "by": "intake@m2", "bundle": "b:.." } ],

  // --- doctrine flags ---
  "is_control":     false,                         // true for LegitimateCoordinationControl — NEVER raises suspicion
  "influence_class":"context",                     // context | exculpatory | (never "discriminative")
  "platform_scope": ["youtube","twitter"],         // cross-platform observation
  "human_review":   { "status": "none|pending|approved|rejected", "anchor": "rev_hash", "at": ".." },

  // --- type-specific payload ---
  "attributes":     { ... }                        // §C.2 per-type
}
```

Two design points worth flagging:
- **`confidence` and `stability_score` are different axes** (the brief lists both). An
  object can be high-confidence/low-stability (we keep seeing *something* but its shape
  shifts → don't over-lean) or high-stability/decaying-confidence (very consistent but
  not seen recently → uncertain again). The Cognitive Engine weighs *both* (§E).
- **`influence_class` is capped at `context`/`exculpatory`** — a knowledge object can
  **never** be `discriminative`. Discriminative evidence only ever comes from the
  *current* Evidence Bundle. This field is the schema-level enforcement of hard line #3.

### C.2 Representative type specializations (`attributes`)
- **`LinguisticFingerprint`**: `{ centroid: float[21], variance: float[21],
  fingerprint_schema_version, exemplar_refs[], distance_radius }` — generalizes
  `extract_fingerprint`; the centroid + radius drive vector retrieval.
- **`BehavioralArchetype`**: `{ signature: {detector → typical (prob,conf) band},
  temporal_profile, defining_contributions[] }`.
- **`CoordinationFingerprint`**: `{ method_set: ["co_engagement","fingerprint_cluster"],
  discriminative: bool, typical_member_count, gate_profile }` — generalizes
  `CoordinationEdge.methods_json`.
- **`ManipulationTechnique`**: `{ definition, observable_signatures[],
  distinguishing_from_benign }` — the last field is mandatory (precision discipline).
- **`Campaign`**: `{ coordination_score_observed, max_coordination_score, member_count,
  methods, hashtags, recurrence: observation_count }` — mirrors the `Campaign` store.
- **`LegitimateCoordinationControl`**: `{ control_kind: "newsroom|fandom|official|
  benign_automation", defining_pattern, why_benign, exemplar_refs[] }` —
  `is_control: true`, `influence_class: exculpatory`.
- **`ThreatActor`**: `{ attribution_basis[], attributed_campaigns[], confidence_attrib,
  external_refs[] }` — `epistemic_status` may reach `attributed` only via human review.

### C.3 The Observation Ledger (per object)
```jsonc
ObservationLedgerEntry {
  "id": "obs:..", "object_id": "ko:..", "at": "ISO-8601",
  "investigation": "hist:..",              // the settled investigation (→ a content-addressed bundle)
  "stance": "supports | contradicts",      // both are recorded
  "evidence_refs": ["evd:digest.."],       // exact EvidenceItem digests cited
  "human_anchor": { "kind": "analyst_verdict|platform_disclosure|account_label|none",
                    "value": "...", "confidence": "high|medium" },
  "independence_key": "grouped(account|campaign|operation|time-window)",  // anti-double-count (§D/§F)
  "memory_influence": "none|framed|primed"  // was THIS investigation itself influenced by memory? (§D.4)
}
```
Aggregates (`confidence`, `stability_score`, counts) are **always recomputed from the
ledger** — never incremented in place — so history is never overwritten (the
`CampaignObservation` discipline, generalized).

---

## D. Learning lifecycle

The write path is a deterministic state machine driven **only** by settled
investigations (Evidence Bundle + optional human anchor). LLM assessments are excluded.

### D.1 When new knowledge is CREATED
A candidate pattern is extracted *deterministically* from a settled bundle (e.g., a
fingerprint centroid, a coordination method-set, a narrative template). It becomes a new
`KnowledgeObject` only when **both**:
- it does **not** match an existing object within the similarity threshold (else →
  update), **and**
- it clears the **creation evidence threshold**: either (a) observed across **≥ K
  independent** investigations (grouped by account/campaign/operation — never K re-scans
  of the same accounts), or (b) anchored by a **human/platform** ground truth.

New objects start `epistemic_status: hypothesized`, low `confidence`, `is_control` set
only for human-confirmed benign patterns.

### D.2 When existing knowledge is UPDATED
A new settled investigation whose evidence matches an object appends an
**ObservationLedgerEntry** (stance `supports` or `contradicts`), then **recomputes**
aggregates from the full ledger:
- independent `supports` raise `confidence` with **diminishing returns** (saturating —
  the existing memory signal already saturates coverage at k/2; same principle);
- `contradicts` lower `confidence` and dent `stability_score`;
- `last_observed` advances (which *resets the decay clock*, §D.6).
Updates never feed the object's *prior conclusion* back as new evidence — only the new
investigation's independent evidence counts.

### D.3 When knowledge is MERGED
Two objects shown to be the same pattern (high `similar_to` + corroborating evidence of
sameness, not mere convenience) merge into one: ledgers concatenate, aggregates
recompute, the absorbed object is marked `superseded_by` and retained for audit. Merge
requires *evidence of sameness*; the LLM may *suggest* a merge during reasoning but
**cannot execute one** (suggestion ≠ write).

### D.4 The anti-self-reinforcement machinery (the heart of D)
Four interlocking safeguards make the loop non-reinforcing:
1. **LLM-opinion exclusion.** Write sources are only `evidence_bundle` + `human_anchor`.
   A Cognitive-Engine assessment is never written. (Hard line #2.)
2. **No double-counting.** Each object's confidence counts an investigation **once**,
   deduped by `independence_key` (grouped by account/campaign/operation/time-window) and
   by `EvidenceItem.digest`. Re-scanning the same accounts cannot inflate confidence —
   the same grouped-split discipline the fine-tuning doc mandates.
3. **Memory-influence quarantine.** If the current investigation's reasoning was
   materially **primed** by memory (the retrieved PriorContext shaped the hypothesis),
   its ledger entry is flagged `memory_influence: primed` and contributes **zero or
   heavily-discounted** weight back to the objects it was primed with. *Memory cannot
   confirm itself.* This is the precise closure of the loop hole.
4. **Independent-corroboration requirement.** `epistemic_status` may advance to
   `corroborated` only via **independent** investigations (different
   accounts/campaign/time/analyst) — the corroboration gate, at the institutional grain.

### D.5 When knowledge is RETIRED (falsifiability)
Soft-retire (mark `retired`, keep for audit — never hard-delete) when any
`retirement_criteria` fires: `confidence` below floor for too long; contradiction ratio
above threshold; staleness beyond `stale_after_days`; human retirement; or superseded.
**Every object must be retireable by contradicting evidence** — an object that cannot be
falsified is a defect (§F).

### D.6 How uncertainty evolves over time
`confidence(t)` is governed by three opposing forces, all reconstructable from the
ledger (conceptual, not code):
- **corroboration ↑** — each independent support raises it, saturating;
- **contradiction ↓** — each contradiction lowers it and reduces stability;
- **decay ↓** — without re-observation, confidence erodes on a **half-life**
  (`confidence_decay.half_life_days`), so unrefreshed knowledge drifts back toward
  `hypothesized`/uncertain.
The result: patterns re-seen across many independent investigations become **stable and
confident**; one-off or stale patterns **decay to uncertainty**; contradicted patterns
**lose status and retire**. Memory that isn't continuously re-earned fades — the
structural guarantee against ossification.

---

## E. Cognitive Engine integration

Memory plugs into the **frozen** Cognitive Engine via seams it already defined — no
redesign.

### E.1 How the Cognitive Engine queries (deterministic retrieval)
A deterministic **Retrieval** step (not the LLM) runs at bind time, using the *current
Evidence Bundle* as the query key:
- **vector search** over `LinguisticFingerprint`/`NarrativeTemplate` centroids (the
  k-NN that `memory/prior.py` already does, generalized to all signature types);
- **graph lookup** over entities (does this account/campaign already exist in memory?);
- returns a **bounded, ranked `PriorContext`** — top-K relevant knowledge objects, each
  carrying its `confidence`, `stability_score`, `epistemic_status`, contradiction tally,
  `is_control`/`influence_class`, and `evidence_refs`.

The LLM **never** queries memory freely — preserving the Evidence Bundle's "no fetch, no
tools" property (`OMI_COGNITIVE_ENGINE_V1.md` §7). The PriorContext is itself a set of
**cited** items (each with a `ko:`/`evd:` id), so the **Governor** resolves every memory
citation exactly as it resolves bundle citations (cite-or-be-dropped).

### E.2 What specialists receive (lens-respecting)
PriorContext is filtered to each Tier-1 specialist's **lens**, obeying the frozen §4.3
information-hiding matrix:
- Language Analyst ← matching `LinguisticFingerprint`/`NarrativeTemplate` priors;
- Coordination Analyst ← `CoordinationFingerprint`/`ManipulationTechnique` priors;
- Graph Analyst ← `GraphFingerprint` priors; Behavior ← `BehavioralArchetype`; etc.
Each prior is labeled **"prior / similarity — context, not current evidence, not
proof."**

### E.3 What remains hidden
- **No verdict to anchor to.** A specialist sees "this fingerprint resembles archetype
  A (a recurring burst-amplifier pattern in N prior investigations, stability 0.6)" —
  **never** "archetype A is a bot network." Only `epistemic_status` + tallies, never a
  conclusion. (Preserves the §4.3 blindness that keeps specialist convergence real.)
- **Suspicion magnitude stays hidden from Risk & Calibration**, as in the frozen matrix.
- **The asymmetry (precision-frontier safeguard):** `LegitimateCoordinationControl` and
  `bounded_by` priors are surfaced *prominently* to the Hypothesis Generator and Red
  Team (they **help exculpate**); incriminating priors (`ThreatActor`, suspicious
  `Campaign`) are surfaced *more conservatively* and only as context. **Memory is freer
  to exonerate than to incriminate.**

### E.4 How history influences but never overrides current evidence (the hard rules)
1. **Memory NEVER changes the echoed `suspicion_probability`/`tier`.** Priors are not
   detectors; echo-never-recompute (frozen F8) is untouched.
2. **Memory NEVER alone satisfies the corroboration gate.** `coordinated`/
   `manipulation_network` still requires **discriminative methods in the *current*
   bundle**. "This matches a known campaign" is suggestive context, not a discriminative
   method.
3. **Memory moves only CONFIDENCE — and mostly downward.** Per the frozen §9, council
   confidence signals act as **clamps**. A strong, independent, *human-anchored* prior
   match may modestly *support* confidence, but never above the engine band and never
   converting an ungated read into a gated one.
4. **The exculpatory asymmetry is encoded:** a control match can pull a read toward
   `mixed`/lower confidence; an incriminating prior cannot push it past the gate.
5. **Every used prior is CITED**, so the Governor can audit that memory influenced
   reasoning *only within these bounds* — and the resulting investigation is flagged
   `memory_influence: primed` so it can't write back into the priors it used (§D.4).

> The crux: **memory is a lens and a guardrail, not a gun.** It helps Omi ask sharper
> questions and avoid false positives; it never manufactures suspicion the current
> evidence doesn't already support.

---

## F. Governance and validation

1. **Confidence decay** (§D.6) — half-life erosion; re-observation re-earns confidence.
   Prevents stale conclusions from ossifying.
2. **Contradiction handling** — `contradicting_investigations` are first-class; a high
   contradiction ratio lowers confidence/stability and triggers **split** (the object
   was two patterns) or **retire**. Contradiction is never silently netted away
   (mirrors the Evidence Bundle's epistemics layer + the Red Team).
3. **Human review gates** — high-impact transitions require a human anchor before they
   take effect: any `attributed_to` a `ThreatActor`/`Organization`, any object reaching
   `corroborated` that would materially shift reasoning at scale, and any
   `LegitimateCoordinationControl` (a wrong control suppresses real detections, so
   controls are human-confirmed). Analyst **accept/edit/reject** on memory-surfaced
   priors is recorded — as *human feedback*, never LLM self-write.
4. **Evidence thresholds** — creation/promotion require ≥ K independent investigations or
   a human/platform anchor (§D.1); below threshold, knowledge stays `hypothesized` and
   low-leverage.
5. **Falsifiability invariant** — every object must be in-principle retireable by
   contradicting evidence; a non-falsifiable object is a defect and is flagged in audit.
6. **Precision-frontier FPR gate** — the hard gate from `future_finetuning_strategy.md`,
   applied to *memory changes*: any change that increases false-positive flagging of
   legitimate coordination on the controls set **fails** governance and is rolled back.
7. **Provenance audit** — an object's confidence must be reconstructable from its ledger
   (no black-box belief); the audit recomputes and compares.
8. **Governance of inputs** — only `train`/`validation`-governed bundles (per
   `datasets/manifest.toml`) write; quarantine/poison never writes. Pseudonymity is
   preserved end-to-end (the Binder's hashed refs); attribution is to *evidence-graded
   attributed entities*, never doxxing (`VISION.md`: not an accusation engine).

---

## G. Scalability strategy (millions of investigations)

1. **Tiered storage by access pattern:** a **graph DB** for nodes/edges (hot); a
   **vector index** for signature retrieval (warm, `LinguisticFingerprint`/
   `NarrativeTemplate` centroids); an **immutable, content-addressed object store** for
   Observation Ledgers + `HistoricalInvestigation` bundles + `version_history` (cold,
   append-only). Each is independently scalable.
2. **Bounded retrieval cost.** Per-investigation reasoning reads only **top-K** priors,
   so cost is ~constant regardless of total memory size — the system scales in *content*
   without scaling per-case *latency*.
3. **Dedup + grouped identity at write** (§D.4) keeps evidence_count honest and storage
   sub-linear in raw scans (heavy re-scan overlap collapses).
4. **Lazy decay.** Confidence decays **on read** + periodic batch sweeps — never a
   continuous global recompute.
5. **Sharding** by platform and object family; provenance partitioned so one hot
   campaign/event doesn't bloat a shard.
6. **Content-addressing** (ledgers cite `EvidenceItem.digest`; bundles are
   content-addressed) gives free cross-investigation dedup and replay.
7. **Read/write separation** — Retrieval (read, hot, latency-bound) is fully decoupled
   from Intake (write, batch, throughput-bound), so they scale on different axes.

---

## H. Future training compatibility

The key strategic distinction — and the reason this system is *non-parametric*:

> **Keep fast-changing, falsifiable intelligence in the memory graph; bake only
> slow-changing reasoning *skill* into weights (LoRA / fine-tune).** Never bake
> yesterday's (possibly wrong) institutional conclusions into the model's parameters —
> parameters can't be falsified, decayed, or retired, and would ossify the exact
> self-reinforcement this whole design forbids.

Concretely, against the brief's list:
- **LoRA adapters / fine-tuning** — memory is the *complement* to LoRA, not a substitute:
  LoRA encodes durable reasoning skill (how to weigh evidence, honor the gate, surface
  counter-evidence); memory holds the volatile facts (which fingerprints/campaigns/
  controls exist right now). They upgrade on **different clocks**. Memory also *feeds*
  training: `(Evidence Bundle + PriorContext → human-anchored outcome)` becomes a
  governed V3/V4 dataset — but only with engine-independent, human-anchored targets,
  grouped splits, and **LLM-opinion excluded** (the same anti-leakage discipline).
- **Cross-platform intelligence** — `platform_scope` on every object; the 21-d
  fingerprint is platform-agnostic by design; `PlatformBehavior` nodes isolate
  platform norms; `identity` links are cross-platform *similarity*, never confirmed
  identity.
- **Distributed storage / graph DBs / vector search / semantic retrieval** — the §G
  backend is designed for exactly these; Retrieval is a vector + graph query from day
  one.
- **Future reasoning models** — the `PriorContext` interface is model-agnostic; a future
  Omi reasoning model consumes the identical retrieval output. The memory outlives any
  single model generation.

---

## I. Long-term roadmap (M1 → M5)

Mirrors and stays consistent with the Cognitive Engine's V1→V5 (§11) and the Evidence
Bundle's relationship to existing stores.

| Stage | What it is | Training? | Prerequisite | Now? |
|---|---|---|---|---|
| **M1** | **Read-only unification** — project the existing fingerprint k-NN + `CoordinationEdge` + `Campaign`/`CampaignObservation` + `Narrative` + `AccountLabel` into the canonical `KnowledgeObject`/ledger schema; deterministic Retrieval → PriorContext as **context only**; no new write loop | none | this spec + the frozen Evidence Bundle | **Yes** (mostly projection — like the Bundle's relation to existing stores) |
| **M2** | **Evidence-gated write path + falsifiability** — Intake creates/updates/merges/retires under thresholds + dedup + decay + contradiction tracking; seed `LegitimateCoordinationControl`s; memory-influence quarantine live | none | M1 + a human-anchor stream (analyst verdicts / disclosures) | **Yes (gated on human anchors)** |
| **M3** | **Graph-DB + vector backend at scale** — move from SQL stores to graph DB + vector index; millions-scale bounded retrieval; sharding/decay sweeps | none | M2 + infra | **No — infra** |
| **M4** | **Memory as a governed training source** — emit `(bundle + PriorContext → human outcome)` for V3 LoRA / V4 fine-tune, engine-independent + grouped + LLM-excluded | SFT/DPO (downstream) | M3 + gold human-anchored outcomes | **No — blocked on gold data** |
| **M5** | **Continuous institutional learning** — closed governed loop (human-review, decay, contradiction-driven retirement) with the precision-frontier FPR as a hard gate every cycle; HF-style immutable revisions as the audit trail | periodic | M4 + steady analyst feedback | **No — the destination** |

**Honest blocker (consistent with the whole repo):** the binding constraint is the same
everywhere — **human-anchored outcomes at scale** (analyst verdicts, platform
disclosures, confirmed legitimate-coordination controls), which are ~0 committed today.
Memory makes the *most* of those once they exist, but cannot manufacture them. And
because self-reinforcement is the central risk, the write path is deliberately
**conservative**: a sparse, trustworthy, falsifiable memory beats a dense, confident,
self-confirming one.

---

## J. Recommendation — the highest-ceiling architecture for the next decade

**Build the Intelligence Memory as a falsifiable, evidence-anchored, *non-parametric*
institutional knowledge graph that:**
1. **stores measurements and patterns, never verdicts** (the live `Campaign` model's
   doctrine, universalized);
2. **is written only by evidence-backed investigations + human anchors — never by the
   LLM** — and never double-counts, with a **memory-influence quarantine** so it cannot
   confirm itself;
3. **enters the Cognitive Engine only as cited `PriorContext`** that can frame,
   exculpate, and *lower* confidence, but **never** changes the engine's number or
   satisfies the gate — *influences but never overrides current evidence*;
4. **decays, tracks contradiction, and retires**, so every belief is falsifiable and
   nothing ossifies; with an **exculpatory asymmetry** (freer to exonerate than to
   flag) that makes precision the default;
5. **stays out of the weights** — the decade's key architectural bet:

> **Separate fast-changing falsifiable *intelligence* (the memory graph) from
> slow-changing reasoning *skill* (LoRA / fine-tune).** This is what gives the highest
> ceiling: Omi accumulates institutional intelligence indefinitely **without
> retraining** (the brief's core objective) and **without the model ossifying
> yesterday's possibly-wrong conclusions.** Memory is the institution's falsifiable,
> auditable *notebook*; the model is its trained *analyst*. You upgrade them on
> different clocks — and you never let the notebook write itself.

This is the architecture that compounds value over ten years while remaining
trustworthy: it makes Omi *smarter every investigation* (a richer, better-calibrated
prior) **and** *safer every investigation* (more known legitimate-coordination controls,
more falsified bad patterns) — without ever crossing the lines that protect "evidence,
not verdict."

---

## Appendix 1 — `KnowledgeObject` full schema
(See §C.1 for the annotated spine.) Required fields: `id, type, family, label,
confidence, stability_score, epistemic_status, evidence_count,
supporting_investigations[], contradicting_investigations[], evidence_refs[],
first_observed, last_observed, last_updated, confidence_decay{}, provenance{},
retirement_criteria{}, superseded_by, version_history[], is_control, influence_class,
platform_scope[], human_review{}, attributes{}`. Invariants: `influence_class ∈
{context, exculpatory}` (never `discriminative`); `epistemic_status` never reaches a
"confirmed truth" value; every field in `attributes` is evidence-derived; all refs are
pseudonymous.

## Appendix 2 — Write-path state machine
```
settled investigation (Evidence Bundle [+ human anchor])
  → extract candidate patterns (DETERMINISTIC; no LLM)
  → for each candidate:
       match existing object? ── no ──► threshold met (≥K independent | human anchor)? ── yes ─► CREATE (hypothesized)
              │ yes                                                        │ no ─► hold (sub-threshold)
              ▼
       append ObservationLedgerEntry (supports|contradicts, independence_key, memory_influence)
       recompute aggregates from ledger (confidence, stability, counts)   [never mutate in place]
       independent corroboration? ─► maybe promote epistemic_status
       contradiction ratio high?  ─► split | flag for review
       retirement_criteria met?   ─► soft-retire (keep for audit)
  → governance pass (FPR gate on controls; provenance audit; human-review queue)
```

## Appendix 3 — Retrieval (read-path) contract
`retrieve(current_bundle) → PriorContext{ items: RankedPrior[], budget: K }` where each
`RankedPrior = { ko_id, type, label, confidence, stability_score, epistemic_status,
contradiction_ratio, is_control, influence_class, evidence_refs[], match_basis }`.
Deterministic (vector + graph); bounded to K; lens-filtered per consumer (§E.2); every
item citable + Governor-resolvable; sets `memory_influence` on the resulting
investigation for write-back quarantine (§D.4).

## Appendix 4 — Mapping to existing stores (continuity)
| This spec | Existing today | Relationship |
|---|---|---|
| `LinguisticFingerprint` + Retrieval | `memory/fingerprint.py` + `prior.py` k-NN | **generalizes** the one existing learning loop |
| `CoordinationFingerprint` + graph edges | `CoordinationEdge` | cumulative pairs → recurring signatures |
| `Campaign` node | `Campaign` ("measurements, not a verdict") | doctrine already correct; lift to the graph |
| Observation Ledger | `CampaignObservation` ("history never overwritten") | the generalized append-only ledger |
| `NarrativeTemplate` | `Narrative` (running centroid) | message-pattern memory |
| human-anchor write source | `AccountLabel` / `Investigation.verdict` | the only non-bundle writer |
| `HistoricalInvestigation` | `Investigation.payload_json` snapshots | the immutable provenance anchor (→ a content-addressed bundle) |

## Appendix 5 — Worked example (abridged)
A new YouTube scan's fingerprint vector-matches `ko:lingfp:000123` ("burst-amplifier",
confidence 0.62, stability 0.71, `contradicting_investigations: 2`, `is_control:false`,
`influence_class:context`). Retrieval also surfaces `ko:control:0007` ("regional-newsroom
on-message pattern", `is_control:true`, `influence_class:exculpatory`). PriorContext to
the council: the Language/Behavior specialists see the archetype *as similarity context*
(no verdict); the Red Team sees the newsroom **control** prominently and must address it.
The Judge may **lower** confidence (a credible benign control fits) and cite both
priors — but the echoed `suspicion_probability`/`tier` are **unchanged**, and because no
discriminative method fired in the *current* bundle, the gate still caps the label at
`suspicious`. The investigation is flagged `memory_influence: primed`, so it contributes
**zero** weight back to `ko:lingfp:000123` (no self-confirmation). If a human later
anchors a verdict, *that* settles an independent ledger entry.

## Appendix 6 — Open questions (none blocks this spec)
1. **Creation threshold K** and the exact `independence_key` grouping (recommend start
   conservative: K≥3 independent or one high-confidence human anchor).
2. **Decay half-lives per object type** (fingerprints stable/long; event-bound campaigns
   short).
3. **Memory-influence discount** — zero vs heavy discount for `primed` write-backs
   (recommend zero until measured).
4. **Control seeding** — initial `LegitimateCoordinationControl` set (newsrooms, major
   fandoms, official accounts) and its human-confirmation bar.
5. **Graph-DB vs relational at M1** — recommend staying on the existing relational
   stores for M1 (projection only) and moving to a graph DB at M3 when scale demands.

---

*Canonical engineering specification only. No production code, scoring, detector,
model, dataset, or deployment was changed by this document. The Intelligence Memory
stores evidence and observed patterns — never verdicts — is written only by
evidence-backed investigations and human anchors (never LLM opinion), and enters
reasoning only as cited, falsifiable context that influences but never overrides current
evidence.*
