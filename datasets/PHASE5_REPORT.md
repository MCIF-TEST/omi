# Phase 5 — Boundary Hold: the member-level residual, closed and measured

> Executes the candidate fix recorded in `PHASE4_REPORT.md` §4. The
> corroboration principle now completes at the verdict boundary:
> **uncorroborated coordination evidence may raise a member's score within its
> tier band, but may not cross a tier boundary upward.** Implemented in the
> production elevation path, measured on the same real controls as Phases 2–4,
> published exactly as observed.

**Reproduce:** `cd apps/api && python -m app.evaluation.member_elevation`
(same harness, datasets, and caps as Phase 4; the production "gated" arm now
includes the boundary hold automatically).

---

## 1. What was implemented

`app/detection/coordination/elevate.py::apply_coordination`: after the normal
re-aggregation, if the member's clusters are **uncorroborated** (no
discriminative method, <2 distinct methods) and the adjusted verdict crossed a
tier boundary upward, the result is clamped at the base band's ceiling —
**0.49** (top of MODERATE, the shared `SUPPORTING_CEILING` constant) when the
standalone tier was below ELEVATED, **0.74** (the same ELEVATED ceiling the
single-axis HIGH cap uses) when the standalone tier was ELEVATED — with an
explicit `score_adjustments` narration and a corrected summary. Never silent;
corroborated members are untouched.

**Approach selection (trustworthiness over FPR-minimization).** Alternatives
considered and rejected: a tier-only hold (probability left above the
boundary) breaks the system-wide probability↔tier mapping; dropping the
uncorroborated signal hides computed evidence; tightening the signal cap
punishes legitimate within-band movement. The chosen clamp mirrors the
codebase's existing cap idiom (`scoring.py` single-axis HIGH cap: clamp at the
tier ceiling + plain-language adjustment), keeps the evidence visible, and
narrates exactly why the verdict was held.

## 2. Results (measured 2026-06-10, n=45 per scenario except Iran n=5)

Member-level **induced elevation** (accounts below ELEVATED standalone that
coordination lifts to ELEVATED+):

| Scenario | pre-fix (Phase 3 era) | Phase 4 (signal gate) | **Phase 5 (boundary hold)** |
|---|--:|--:|--:|
| **CONTROL — legit humans** | 0.500 | 0.324 | **0.000** |
| CONTROL — novelty bots | 0.000 | 0.000 | 0.000 |
| Russia GRU (2020-12) | 0.333 | 0.333 | **0.333** (cost: zero) |
| Iran (2020-09, n=5) | 0.333 | 0.000 | 0.000 |
| China Xinjiang (CNHU) | 0.714 | 0.286 | **0.286** (cost: zero) |

Total member ELEVATED+ (standalone + induced):

| Scenario | standalone | ungated (pre-fix) | Phase 4 | **Phase 5** |
|---|--:|--:|--:|--:|
| Legit humans | 0.244 | 0.622 | 0.489 | **0.244** |
| Russia GRU | 0.800 | 0.867 | 0.867 | **0.867** |
| China Xinjiang | 0.844 | 0.956 | 0.889 | **0.889** |

### Headline
**Member-level induced elevation FPR on legitimate humans: 0.000.** Elevated
rate on the human control is now exactly the standalone engine's own rate
(0.244) — coordination evidence adds zero false elevation. Membership stays
0.733 (clustering remains visible evidence; it just doesn't elevate without
corroboration).

### Recall cost of the hold: zero, everywhere measured
GRU 0.867 → 0.867 and Xinjiang 0.889 → 0.889 (totals unchanged to the third
decimal). The Phase-4 decomposition predicted this: every residual *human*
lift was an uncorroborated boundary-crosser (style-only, borderline base),
while every surviving *IO* lift was corroborated (discriminative methods) —
the hold, by construction, touches only the former. The measurement confirms
the prediction exactly.

### Cross-checks
Harness continuity holds (membership 0.733, standalone 0.244 — identical to
Phase 4 and consistent with Phases 1–3). CI pins the mechanism:
borderline-MODERATE + style-only held at 0.49/MODERATE with narration;
within-band raises untouched; no uncorroborated path to HIGH from an ELEVATED
base; corroborated members cross boundaries freely
(`tests/test_coordination_elevate.py`, `tests/test_member_elevation.py`).

## 3. Remaining residual risks

1. **Standalone engine FPR on broadcast humans (0.244)** — the floor the
   coordination layer now never adds to. This is a *single-account* precision
   issue (Phase 1's known 24% on verified high-profile accounts), outside the
   coordination trust boundary; tracked, not hidden.
2. **Accepted adversarial trade (inherited, now consistent):** an operation
   coordinating *only* through supporting signals (style/cohort/burst) tops
   out at member-MODERATE and batch-0.49 — the same trade Phase 3 accepted at
   the batch level, now applied uniformly, always narrated, with campaign
   records still capturing the cluster as visible evidence.
3. Carried forward, unchanged: `co_tag` IDF hardening (still not biting on
   controls), IRA-class sparse-operation recall, Tier-3B manipulation-intent
   taxonomy, `expected_tier` taxonomy for benign automation.

## 4. Recommendation: is the trust boundary closed?

**Yes — the coordination trust boundary (Tier 3B's precision arm) is closed.**
Every layer now holds, measured on real data: batch verdict (Phase 3: humans
1.00 → 0.49 gated, FPR 0%), member elevation (Phase 4 gate + Phase 5 hold:
induced elevation on humans 0.500 → 0.324 → **0.000**, zero IO recall cost),
with the corroboration rule expressed identically at signal, member, and batch
levels from shared constants, and every cap narrated in the output. What
remains (standalone broadcast-human FPR; manipulation-intent) belongs to other
boundaries and is tracked in `TRUST_BOUNDARY_TRACKING.md`.

## 5. Files

`app/detection/coordination/elevate.py` (boundary hold in
`apply_coordination`) · `tests/test_coordination_elevate.py` (+4 boundary
tests) · `tests/test_member_elevation.py` (+1 borderline-population test) ·
this report · `PHASE4_REPORT.md` §4 + `TRUST_BOUNDARY_TRACKING.md` updated to
the closed state.

> Phase 5 met its objective with the cleanest possible result: the number is
> 0.000, the cost is zero, and the mechanism is the same corroboration
> principle the platform already trusted — now applied wherever a verdict can
> cross a boundary.
