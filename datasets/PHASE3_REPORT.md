# Phase 3 Report — Coordination Precision Recovery

**Objective (authorized):** recover precision while preserving demonstrated recall.
Three priorities: a **corroboration gate**, the first **IO-native network detector**,
and **detector re-weighting**. Same eval framework and datasets as Phase 2; before/after
measured directly. **No recall regression on the strong campaigns.**

> **Result.** The Phase 2 precision crisis is fixed at the verdict level: legitimate
> humans drop **1.00 → 0.49** (gated to MODERATE), while IO campaigns stay maximal —
> now *corroborated* by a discriminative network signal rather than carried by a lone
> non-discriminative one. Score-level human FPR **100% → 0%**; recall preserved and, on
> two campaigns, improved.

---

## 1. Precision / Recall / FPR — before vs after

Same campaigns + controls as Phase 2, same harness. **Score** = the aggregate
coordination verdict (≥0.50 = flagged).

| Scenario | kind | Phase 2 score | **Phase 3 score** | gated | member recall | member FPR |
|---|---|---:|---:|:--:|---:|---:|
| Russia GRU | IO | 1.00 | **1.00** | — | 0.60 → **0.69** | — |
| Russia IRA (202012) | IO | 0.34 | 0.30 | — | 0.14 | — |
| Iran 092020 | IO | 1.00 | **1.00** | — | 0.20 | — |
| China Xinjiang | IO | 1.00 | **1.00** | — | 0.78 → **0.92** | — |
| **CONTROL — legit humans** | legit | **1.00** | **0.49** | **✓** | — | 0.73 (residual, see §6) |
| CONTROL — novelty bots | bots | 0.33 | 0.30 | — | — | 0.085 |

**Score-level precision/recall/FPR:**
- **FPR (the fix):** legitimate humans **1.00 → 0.49** — no longer a maximal (or even
  flagged) coordination verdict. Campaign-level human **FPR 100% → 0%**.
- **Recall (preserved):** GRU/Iran/Xinjiang stay 1.00; `co_tag` *raised* member recall
  on GRU (0.60→0.69) and Xinjiang (0.78→0.92). IRA stays weak (0.30) — small/diverse
  sample, a recall gap, not a precision one.
- **Separation restored:** Phase 2 IO and humans were indistinguishable (both 1.00).
  Phase 3 separates them — IO {1.00, 1.00, 1.00} vs humans **0.49**.

---

## 2. Corroboration Gate Analysis (Priority 1)

**Mechanism (`aggregate.py`).** A maximal verdict now requires **corroboration**:
either a **discriminative** detector fired (one that measured a real IO-vs-human gap),
or **≥2 independent detectors** agree. A lone *supporting* detector (e.g. `style_match`
on a set of professional writers) is capped at the MODERATE ceiling (0.49) — it can
raise suspicion but never produce a maximal coordination verdict.

- **Detector classes:** discriminative = `fingerprint_cluster`, `co_engagement`,
  `co_tag`; supporting = `style_match`, `temporal_semantic`, `age_cohort`.
- **Minimum corroboration:** 1 discriminative **or** 2 independent detectors with
  positive evidence (> 0.05).
- **Precision impact:** decisive — the only scenario gated is the legitimate-humans
  control (1.00 → 0.49). Every IO campaign fires a discriminative lens
  (`fingerprint` and/or `co_tag`) so none are gated.
- **Recall impact:** **zero** on the strong campaigns — they were never carried by a
  lone supporting detector; `fingerprint`/`co_tag` corroborate them.
- **Transparency:** the aggregate now reports `gated` and `ungated_score`, so a capped
  verdict is auditable.

Backward-compatible: all pre-existing `aggregate_coordination` tests pass unchanged
(they either fire a discriminative detector or were already sub-threshold).

---

## 3. Network Detector Analysis (Priority 2) — `co_tag`

The first IO-native network signal, modeled structurally on `co_engagement`
(pairwise Jaccard over a per-account set → Union-Find components). A "tag" is a
shared **target/topic**: a `#hashtag` or `@mention` (the latter also captures
`RT @account` amplification), lifted from the text Phase 0/1 already extract.

**Discrimination (real data):**

| | co_tag score | evidence | clusters |
|---|---:|---:|---:|
| Russia GRU | 1.00 | 1.00 | 4 |
| Iran 092020 | 1.00 | 1.00 | 1 |
| China Xinjiang | 1.00 | 0.99 | 2 |
| Russia IRA | 0.23 | 0.00 | 0 (sparse tags in sample) |
| **CONTROL humans** | **0.23** | **0.00** | **0** |
| CONTROL novelty-bots | 0.23 | 0.00 | 0 |

`co_tag` fires on **3/4 IO campaigns** with maximal evidence and is **silent on both
controls** — the discriminative network lens Phase 2 identified as the missing
capability. It also lifted member recall (Xinjiang 78%→92%, GRU 60%→69%). Underlying
separation measured directly: shared-tag pairs Iran 75% / Xinjiang 51% / GRU 21% vs
**humans 0%**.

---

## 4. Detector Weighting Analysis (Priority 3)

`style_match` is now **supporting evidence**: it keeps its reliability prior (so it
still contributes to the mean and to corroboration *when a discriminative detector
co-fires* — every real IO case), but the gate forbids it from producing a maximal
verdict **alone**. This implements "supporting unless corroborated" via the gate
rather than a blunt reliability cut, which is why recall is fully preserved.

| Detector | Class | Role after Phase 3 |
|---|---|---|
| `fingerprint_cluster` | discriminative | Primary discriminator (Phase 2) — unchanged |
| **`co_tag`** | discriminative | **New** — strongest network separation |
| `co_engagement` | discriminative | Unchanged (YouTube only) |
| `style_match` | **supporting** | High recall, gated from standalone maximal verdicts |
| `age_cohort` | supporting | Corroborating only |
| `temporal_semantic` | supporting | Corroborating only (floored on account history) |

---

## 5. Confidence behavior

Per-detector confidence is unchanged (rich on real text, 0 when sparse). The gate is a
score-level cap layered on top; it adds `gated`/`ungated_score` for audit and never
raises a score. Aggregation remains `max(weighted_mean, corroboration)` — then gated.

---

## 6. Remaining risks (→ Trust Boundary Tier 3B)

1. **Per-account elevation residual — ✅ CLOSED & MEASURED in Phase 4.** The
   corroboration rule now ships inside `elevate.build_coordination_signal`
   (lone supporting cluster ⇒ signal capped at 0.49/0.50), and the real-data
   member-level numbers are published in `PHASE4_REPORT.md`: induced elevation
   on the legit-human control 0.500 (pre-fix) → 0.324 (production), the
   low-standalone failure mode eliminated, GRU rescue cost zero. A precisely
   named boundary residual remains (capped signal can still tip 0.39–0.49
   borderline accounts just over ELEVATED; none reach HIGH) — see Phase 4 §4.
2. **`co_tag` generic-tag risk.** Ubiquitous hashtags/handles could link unrelated
   accounts; the human control shows 0 clusters so it isn't biting now, but **IDF
   down-weighting** of common tags is sensible hardening before broad deployment.
3. **≥2-supporting corroboration** is permitted; two weak lenses agreeing reaches a
   non-maximal-but-elevated verdict. Monitor for a legitimate cohort that trips two
   supporting detectors at once.
4. **IRA recall** (0.30) — small/diverse sample under-detected; a recall question for a
   future pass, not precision.

---

## 7. Updated roadmap

| Item | Status |
|---|---|
| Phase 0 / 1 / 2 | ✅ merged |
| **Phase 3 — corroboration gate + `co_tag` + re-weighting** | ✅ **this report** |
| Propagate gate into per-account elevation | ✅ shipped + measured — `PHASE4_REPORT.md` |
| `co_tag` IDF hardening | ⏭ future |
| Tier 3B — automation/coordination vs manipulation | 📌 updated, tracked |

### Files
`app/detection/coordination/co_tag.py` (new detector) · `aggregate.py` (gate +
`co_tag` prior) · `app/evaluation/io_coordination.py` (network + before/after) ·
`tests/test_co_tag.py`, `tests/test_coordination_aggregate.py` (gate tests) ·
`datasets/TRUST_BOUNDARY_TRACKING.md`.

## Recommendation for next action
~~Propagate the corroboration gate into per-account elevation (residual #1)~~ —
**done and measured; see `PHASE4_REPORT.md`** (humans induced elevation
0.500 → 0.324; low-standalone failure mode eliminated; GRU cost zero). The
remaining boundary residual + candidate fix are recorded in Phase 4 §4. Then
revisit IRA-style recall and `co_tag` IDF. The manipulation-intent layer
(Tier 3B) remains the longer-horizon precision frontier.

> Phase 3 met its objective: trustworthy detection. The aggregate coordination score
> can now tell a state campaign from a newsroom — IO 1.00, legitimate humans 0.49 —
> with recall preserved and a new discriminative signal carrying the verdict.
