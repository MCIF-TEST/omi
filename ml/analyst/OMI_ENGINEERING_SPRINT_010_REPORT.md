# OMI_ENGINEERING_SPRINT_010 — Evidence Enrichment (report)

> **Engineering sprint.** Increased reasoning quality by increasing **evidence quality** — not
> the model, not the council. The Binder gains an **opt-in, additive** enrichment pass that
> projects richer structured facets from the *same* engine output (it computes nothing, runs no
> model, changes no score, and never invents). Every enriched item carries provenance + a
> traceability path back to its source. The Context Builder **auto-consumes** the new evidence
> with no prompt change, evidence-quality metrics are exposed through Shadow Mode + an
> engineering API, and replay stays correct (enrichment is off by default, so historical bundles
> are byte-identical and missing facets degrade gracefully). No new specialist; the Governor is
> untouched.

## A. GitHub commits

One commit on `claude/stoic-edison-2ueecx`. Two new evidence modules (`enrich.py`,
`quality.py`), plus additive edits: a one-line opt-in flag on the Binder, a generic
`derived_evidence` section in the Context Builder, an `enrich` passthrough on the Orchestrator /
shadow runner, a `compare_evidence_modes` benchmark, and one admin route. **Zero** changes to
the detection engine, scoring, OmiScore, the **Governor**, the Blackboard, the Contracts, or any
existing bundle field. With `enrich=False` (the default) the `bundle_id` is **byte-identical** to
before — so Sprint 002–009 paths, historical bundles, and replay are unaffected.

## B. Evidence enrichment implementation (`app/evidence/enrich.py`)

`enrich_bundle(bundle, payload, …)` projects, in a fixed deterministic order, the charter's
richer facets — **only** from data already present in the engine output:
- **feature_importance** (ranked contributions), **temporal_pattern**, **coordination_summary**
  (aggregate of the firing methods), **engagement_distribution** (commenter-tier histogram),
  **narrative_cluster** (when the payload carries narrative), **metadata_summary**,
  **detector_provenance**, **cross_link** evidence + **co_engaged** graph edges, and an
  **investigation_chronology**.
- **Never invents:** each step derives purely from existing fields and **degrades gracefully**
  when a source is absent (a thin payload simply yields fewer enriched items — no error, no
  fabrication). Every enriched `EvidenceItem` carries `provenance` + a `traceability_path` whose
  `ev:` references resolve against the bundle.

## C. Updated Binder (`app/evidence/binder.py`)

One additive parameter — `Binder().bind(payload, …, enrich=False)`. When `enrich=True`, the
enrichment pass runs after the core projection and **before** capabilities, so the bundle's
capability map reflects the new facets. Off by default; deterministic; the core projection is
unchanged.

## D. Evidence quality metrics (`app/evidence/quality.py`)

`evidence_quality(bundle)` — deterministic, model-free measurements that make enrichment
measurable (baseline scores lower, enriched higher):
- **evidence_completeness** (share of target kinds present), **facet_coverage**,
  **provenance_completeness**, **graph_density**, **timeline_completeness** (chronology
  coverage), **citation_integrity** (share of bundle-id references that resolve — **1.0** for
  enriched bundles). On the test fixture: completeness `0.25 → 1.0`, facet coverage
  `0.33 → 1.0`, graph density `1.0 → 1.67`, timeline `0.0 → 0.92`, integrity `1.0`. Exposed via
  `ShadowReport.evidence` and the admin route.

## E. Context Builder integration

The Context Builder **automatically consumes** enriched evidence with **no prompt change** and
no per-specialist modification:
- a generic **`derived_evidence`** section surfaces any non-base-kind item in a non-dedicated
  facet (feature_importance / temporal_pattern / detector_provenance / cross_link, and any
  *future* enriched kind), and `coordination_highlights` now also shows the coordination summary;
- the existing facet sections (narrative / metadata / graph) populate from enrichment.
On the fixture, structured-context completeness rises (`> baseline`) while citation retention
stays **1.0**. Any future AI specialist inherits the richer context for free.

## F. Test results

`cd apps/api && python -m pytest tests/ -q` → **913 passed** (was 898; **+15**), 0
regressions. `tests/test_evidence_enrichment.py` + `tests/test_evidence_shadow.py` cover:
- **Binder enrichment** + richer facets/kinds, **co_engaged** edges, **deterministic
  projection**, **provenance/traceability preservation**, **graceful degradation** on a thin
  payload, **backward compatibility** (enrich off → only atomic kinds, identical id);
- **evidence metrics** (quality rises; integrity + provenance 1.0; deterministic);
- **context integration** (derived_evidence empty baseline vs populated enriched; retention
  1.0), **Shadow Mode exposure** + **`compare_evidence_modes`** quality deltas;
- **regression safety** — **production read is unchanged by enrichment** (it adds evidence, not
  verdicts; both Governor-permitted);
- **replay compatibility** — enriched replay reproduces; a missing-facet payload replays.

## G. Engineering readiness

- **Evidence enrichment + metrics: ready and measurable today.** Richer, fully-traceable
  evidence is produced deterministically and its quality is quantified **without a model** — the
  improvement is real and inspectable now (the evidence route, the shadow `evidence` block).
- **Reasoning-quality signal: gated on live inference.** Whether richer evidence changes the
  *model's read* is null offline (the AI falls back to deterministic); `compare_evidence_modes`
  is proven with deterministic providers and yields real signal once the endpoint exists.
- **Constitution: intact.** Enrichment is evidence-over-opinion (projection, no inference),
  deterministic, fully traceable (integrity 1.0), replayable, Governor-compatible, and adds
  **zero fabricated evidence**. The production read is provably unchanged.

## H. Recommendation for Sprint 011

1. **Provision the endpoint and run the full quality sweep over the gold corpus.** Combine the
   three opt-in levers — `enrich` × `context_mode` × `prompt_version` × budget — via
   `compare_evidence_modes` / `compare_context_modes` / `ab_evaluate` over the Sprint-008 corpus
   (controls included), and promote each lever only where it **raises label agreement without
   raising control FPR**. This turns the now-complete measurement stack into the first
   evidence-based promotions (`OMI_ANALYST_ENRICH`, `…_CONTEXT_MODE`, `…_PROMPT_VERSION`).
2. **Widen the enrichment source surface.** Project the remaining engine stores the Binder does
   not yet read (e.g. `Account.fingerprint_json` k-NN memory neighbors, `CoordinationEdge`
   pairwise graph, `CampaignObservation` history) into the bundle — additively, deterministically
   — so `graph_density` and `timeline_completeness` climb further. Still no model change: more
   evidence, better reasoning.

---

*Long-term architecture over short-term sophistication. Reasoning improves by improving the
Evidence Bundle — projection, not inference. Enrichment is opt-in, deterministic, fully
traceable, replayable, and never invents; the production read is unchanged and the Governor is
untouched. No engine / scoring / OmiScore change. Gates green at commit time (913 backend
tests). GitHub remains the source of truth; Hugging Face remains the source of AI assets.*
