# OMI_ENGINEERING_SPRINT_002 — Deterministic Foundation (report)

> **Engineering sprint, not a design doc.** Working, fully-tested deterministic
> infrastructure committed. Track A (the deterministic foundation) is the deliverable;
> Track B (live Qwen) stays externally blocked and is documented as activation-ready.

## A. GitHub commits

One commit on `claude/stoic-edison-2ueecx`. **Zero changes to existing files** — every
component is a new, additive, standalone module, so backward compatibility is preserved by
construction (the engine and the Sprint-001 analyst path are untouched).

## B. Implemented deterministic components (Track A — all 7 priorities)

| # | Component | Module | Notes |
|---|---|---|---|
| 1 | **Binder** | `app/evidence/binder.py` | Pure function of the engine payload → normalized bundle; assigns stable `ev:NNNN` ids; pseudonymizes refs; derives epistemics (contradictions / missing / unknowns) |
| 2 | **Canonical Evidence Bundle** | `app/evidence/bundle.py` | Normalized graph: flat `EvidenceItem` index + `Entity` + `Relationship`; `headline()` echo source; `citation_index`; `resolve()` (native `ev:` + legacy dotted paths) |
| 3 | **Version binding** | `app/evidence/bundle.py` | `bundle_schema_version` + engine/feature/binder versions on every bundle |
| 4 | **Constitutional Governor** | `app/governor/governor.py` | Deterministic S0–S11 pipeline; machine-checkable invariants; PERMIT/REJECT; never edits |
| 5 | **Audit pipeline** | `app/governor/audit.py` | Content-addressed `ValidationTrace` (`vt:…`) + append-only `AuditLog`; reproducible |
| 6 | **Content-addressed artifacts** | `app/evidence/bundle.py` | `canonical_json` + `digest`; `bundle_id` is a pure function of evidence (no wall-clock) |
| 7 | **Deterministic Floor hardening** | (verification) | Proven: the **real** Floor output passes the **real** Governor (PERMIT) — Floor↔Governor consistency on live data |

**Design guarantees met:** matches the approved architecture; **deterministic** (same
input → same `bundle_id` / `trace_id`); model-free (no GPU); graceful (Governor rejects to
the Floor, never repairs); backward-compatible (additive only); cleanly integrated
(imports only within the new layer; the Governor can already validate the existing
analyst's output via legacy-path resolution). No speculative features — exactly the
deterministic layer the specs define.

## C. Test results

`cd apps/api && python -m pytest tests/ -q` → **780 passed** (was 755; **+25**), 0
regressions. New suites:
- `tests/test_evidence_bundle.py` (11) — content-addressing determinism, projection
  correctness, pseudonymity, epistemics, native + legacy citation resolution.
- `tests/test_governor.py` (14) — PERMIT on a faithful ruling; **REJECT for each violation
  class** (fabrication, echo-override, gate-breach, confidence-inflation,
  insufficient≠inconclusive, suppressed counter-evidence, banned phrase,
  supplemental-as-suspicion, non-falsifiable, confirmed-without-anchor); trace
  reproducibility; append-only audit; **the real Floor output permitted by the real
  Governor**.

## D. Runtime activation status (Track B)

**Unchanged from Sprint 001 — still blocked on external resources** (no live HF Inference
Endpoint, no Render dashboard/GPU access from this environment). Nothing new was
verifiable; nothing was stalled. The repo remains **activation-ready**: Sprint 001 wired
the Render env config (`OMI_ANALYST_ENABLED` / `OMI_ANALYST_ENDPOINT_URL` / `HF_TOKEN`) and
the graceful Floor fallback; this sprint adds the deterministic foundation that the live
path will plug into — none of it requires the endpoint.

## E. Remaining blockers

1. **Live Qwen inference** — needs a deployed HF Inference Endpoint + the Render env
   applied (operator/GPU actions). The provider code path + fallback are verified; live
   inference is not.
2. **Foundation not yet wired into the live analyst path** — *intentional* this sprint
   (backward compatibility): the live `/analyst` route still uses the Sprint-001 lossy
   projection + partial validator. The new Binder/Bundle/Governor are built, tested, and
   importable, ready to be wired in additively next.

## F. Recommendation for Sprint 003

**Sprint 003 — Governor integration + Orchestrator control-plane skeleton (both GPU-free).**
1. Wire the **Governor as an additive validation gate** on the live `/analyst` path:
   build the Binder bundle alongside the existing assessment, run the Governor, record the
   `ValidationTrace` (best-effort, SAVEPOINT-isolated), and on REJECT fall back to the
   Floor — off by default, zero behavior change when off.
2. Stand up the **Reasoning Orchestrator control plane** (deterministic: the blackboard,
   `ReasoningContract` interfaces, the Budget Controller, with the Floor as the only
   "module") so the council can be added module-by-module later behind it.
Both are fully in our control and need no live endpoint; run the **HF endpoint + Render
activation** (E1) as a parallel operator task.

---

*Working software over documentation. No engine / scoring / OmiScore change; new modules
are additive and standalone; deterministic where specified; gates green at commit time
(780 backend tests). GitHub remains the source of truth; Hugging Face remains the source
of AI assets.*
