# Phase 4 — Member-Level Elevation: gate shipped, measured, published

> Closes Phase 3's residual risk #1. The member-level corroboration gate now
> ships in production (`app/detection/coordination/elevate.py`); this report
> publishes the **measured** member-level elevation numbers on the same real
> controls Phases 2–3 used — before vs after, with the residual decomposed and
> named. Per the execution directive: actual measured results only; the goal is
> trust, not passing a threshold.

**Reproduce:** `cd apps/api && python -m app.evaluation.member_elevation`
(reads the `validation`-governed corpora under `datasets/Datasets/`; the
measurement module is `app/evaluation/member_elevation.py`, CI-pinned by
`tests/test_member_elevation.py`).

---

## 1. What changed since Phase 3

Phase 3's gate capped the **batch verdict** (campaign-level: legit humans
1.00 → 0.49/gated) but per-member elevation still composed a coordination
signal from the member's own clusters at full strength — so a human inside a
`style_match`-only cluster could be elevated individually (the "member FPR
0.73" residual, §6.1 of the Phase 3 report).

The fix (shipped): `elevate.build_coordination_signal` now applies the SAME
corroboration rule as the aggregate — a lone supporting detector
(`style_match` / `temporal_semantic` / `age_cohort`) is capped at
`SUPPORTING_CEILING` (0.49) probability and 0.50 confidence; a discriminative
detector (`fingerprint_cluster` / `co_engagement` / `co_tag`) or ≥2 distinct
methods compose at full strength. Constants are imported from `aggregate.py`
so the two gates cannot drift.

## 2. Measurement design

Two arms over identical inputs, both pure measurement (no detection change):

* **gated** — the production path: `analyze_account` → detectors (+`co_tag`)
  → `coordination_membership` → `apply_coordination` → adjusted tier.
* **ungated** — the pre-fix signal composition reproduced in the evaluation
  module only (max cluster score; confidence 0.55 + 0.20/method, uncapped).

Headline metric — **induced elevation**: among accounts the standalone engine
scored *below* ELEVATED, the fraction lifted to ELEVATED+ by coordination.
On legitimate controls this is the member-level elevation FPR (the harm
Phase 3 §6.1 described); on IO operations it is coordination rescue.
`membership` (being inside ≥1 cluster) is reported separately — clustering is
*evidence* and is deliberately not suppressed; the question is whether it
*elevates*.

Controls: the same corpora as Phases 2–3 (all `validation` in
`datasets/manifest.toml`) — TwitterData_Joined verified legit humans (n=45)
and novelty bots (n=45); Russia GRU 2020-12; Iran 2020-09; China Xinjiang
CNHU (caps: 45 accounts/scenario, as Phase 3).

**Cross-validation of the harness** (numbers that must reproduce, and do):
human membership measured **0.733** — Phase 3 published 0.73; human standalone
ELEVATED+ measured **0.244** — Phase 1 published 24% (11/45). Same data, same
path, independent reimplementation.

## 3. Results (measured 2026-06-10)

| Scenario | n | membership | standalone ELEV+ | **induced (pre-fix)** | **induced (production gate)** |
|---|--:|--:|--:|--:|--:|
| **CONTROL — TwitterData legit humans** | 45 | 0.733 | 0.244 | **0.500** | **0.324** |
| CONTROL — TwitterData novelty bots | 45 | 0.089 | 0.422 | 0.000 | 0.000 |
| Russia GRU (2020-12) | 45 | 0.667 | 0.800 | 0.333 | 0.333 |
| Iran (2020-09) | 5 | 0.600 | 0.400 | 0.333 | 0.000 |
| China Xinjiang (CNHU) | 45 | 0.911 | 0.844 | 0.714 | 0.286 |

Total member ELEVATED+ rates (standalone + induced combined):
humans 0.622 → **0.489**; GRU 0.867 → 0.867; Xinjiang 0.956 → 0.889.

### Headline
**Member-level induced elevation FPR on legitimate humans: 0.500 → 0.324.**
The gate removed roughly a third of the coordination-induced harm — a real
improvement, **and short of the ≤0.15 working target**. Published as measured.

### What the gate fixed (decomposed)
Every gate-saved human (6/45) had a genuinely low standalone score
(0.15–0.33) that the pre-fix `style_match`-only signal (0.85/0.75) yanked to
ELEVATED — the catastrophic failure mode. **That failure mode is gone**: with
the gate, no LOW-range human is elevated by an uncorroborated cluster, and CI
pins it (`test_member_elevation.py`).

### The residual, named precisely
All 11 residual lifted humans are **`style_match`-only** members whose
standalone scores were already borderline (0.39–0.49, top of MODERATE). The
capped signal (≤0.49 prob, ≤0.50 conf) still contributes positive log-odds at
re-aggregation, nudging them to 0.51–0.61 — just over the ELEVATED boundary.
**None reach HIGH** (0/45 humans HIGH in either arm at member level). The gate
behaves exactly as specified; the residual is **additive-evidence semantics at
the tier boundary**, not a gate bypass. Two aggravating context notes:
(a) this control cohort is verified high-profile broadcast accounts — the
"coordination-shaped" Known-Mixed frontier by construction, with a 24%
standalone ELEVATED rate before any coordination input; (b) only `style_match`
clustered them (5 clusters; zero `co_tag`/`fingerprint`/`co_engagement`
clusters on humans — the discriminative lenses stayed silent, correctly).

### Recall cost (the honest trade)
* **GRU: zero cost** — induced rescue 0.333 in both arms (members corroborated
  by discriminative lenses; the gate is a no-op for them). Total ELEV+ 0.867.
* **Xinjiang: member-level rescue 0.714 → 0.286** — most members sat only in
  the big `age_cohort` cluster (supporting-only ⇒ capped). The campaign-level
  verdict is unaffected (0.999, 3 corroborating methods) and standalone already
  catches 0.844, so total member ELEV+ falls only 0.956 → 0.889.
* Iran: n=5 — too small to read (listed for completeness).
* Novelty bots: 0.000 induced in both arms — the engine still refuses to
  manufacture coordination on benign automation (membership 0.089).

## 4. Remaining risk + candidate next step (NOT implemented)

The residual (0.324) has one precise driver: **an uncorroborated, capped
signal may still tip a borderline account across the MODERATE→ELEVATED
boundary**. The candidate fix is a boundary rule at elevation — an
uncorroborated coordination signal may raise the score *within* MODERATE but
not across the ELEVATED boundary (cap the *adjusted result* at the ceiling,
not just the signal). Expected effect: humans induced 0.324 → 0.000 with zero
GRU cost (corroborated members unaffected); Xinjiang member-level induced lift
would stay at 0.286's gated level (cohort-only members already capped).
This is a **detection-logic change and is explicitly out of Phase-2/H1 scope**
("do not optimize or modify detection logic") — recorded here for
authorization, not done.

> **Update:** authorized and executed — see `PHASE5_REPORT.md`. Measured:
> humans induced elevation 0.324 → **0.000** with zero IO recall cost
> (GRU 0.867 → 0.867, Xinjiang 0.889 → 0.889).

Also carried forward from Phase 3: `co_tag` IDF hardening (still not biting on
controls — 0 human co_tag clusters); IRA-class sparse-op recall; Tier-3B
intent taxonomy.

## 5. Files

`app/evaluation/member_elevation.py` (measurement, gated + pre-fix arms,
standard-scenario CLI) · `tests/test_member_elevation.py` (5 CI tests pinning
the gate-saves-low-humans / discriminative-identical / no-cluster-untouched /
membership-vs-induced properties) · this report ·
`datasets/PHASE3_REPORT.md` §6 + `datasets/TRUST_BOUNDARY_TRACKING.md`
(residual updated to point here).

> Phase 4 met its objective: the member-level gate is in production and its
> real effect is now a published, reproducible number — induced elevation on
> legitimate humans halved-ish (0.500 → 0.324), the catastrophic low-human
> failure mode eliminated, GRU recall untouched — with the remaining boundary
> residual named, measured, and queued rather than hidden.
