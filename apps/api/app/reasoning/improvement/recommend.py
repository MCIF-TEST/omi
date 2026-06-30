"""The recommendation engine (Sprint 011) — deterministic, evidence-backed.

Compares two evaluation *snapshots* (a baseline config and a candidate config, each a dict of
metrics produced by the existing measurement stack) and emits ``Recommendation``s. Each detector
fires only when a metric crosses a deterministic threshold, and **every recommendation carries
the supporting metrics** — the engine never recommends a change without evidence. It only
*recommends*: nothing here changes production. Recommendation ids are content-addressed, so the
same inputs always yield the same recommendation (reproducible).
"""
from __future__ import annotations

from dataclasses import dataclass

from app.evidence.bundle import digest

_SEVERITY_RANK = {"critical": 0, "regression": 1, "improvement": 2, "info": 3}


@dataclass(frozen=True)
class Thresholds:
    """Deterministic decision thresholds. Conservative: any control-FPR or fabricated-citation
    increase is a regression (the precision + constitutional frontiers)."""

    min_agreement_gain: float = 0.02
    max_control_fpr_increase: float = 0.0
    max_latency_ratio: float = 1.5
    min_citation_retention: float = 0.99
    max_citation_failure_increase: float = 0.0
    max_governor_floor_increase: float = 0.05


DEFAULT_THRESHOLDS = Thresholds()


@dataclass(frozen=True)
class Recommendation:
    """One evidence-backed engineering recommendation. ``action`` ∈ promote | rollback | hold |
    investigate; ``state`` starts at ``recommended`` (the engine recommends — humans approve)."""

    kind: str
    lever: str
    action: str
    severity: str                  # critical | regression | improvement | info
    baseline: dict
    candidate: dict
    metrics: dict
    rationale: str
    state: str = "recommended"

    @property
    def id(self) -> str:
        return digest({
            "kind": self.kind, "lever": self.lever, "action": self.action,
            "baseline": self.baseline, "candidate": self.candidate, "metrics": self.metrics,
        }, prefix="rec:")

    def to_dict(self) -> dict:
        return {
            "id": self.id, "kind": self.kind, "lever": self.lever, "action": self.action,
            "severity": self.severity, "state": self.state, "baseline": self.baseline,
            "candidate": self.candidate, "metrics": self.metrics, "rationale": self.rationale,
        }


def _m(snap: dict, key: str, default: float = 0.0) -> float:
    v = snap.get(key)
    return float(v) if isinstance(v, (int, float)) else default


def _delta(c: float, b: float) -> float:
    return round(c - b, 4)


def _lever(baseline: dict, candidate: dict) -> str | None:
    bc, cc = baseline.get("config", {}) or {}, candidate.get("config", {}) or {}
    diffs = sorted(k for k in set(bc) | set(cc) if bc.get(k) != cc.get(k))
    return diffs[0] if diffs else None


def _rec(kind, lever, action, severity, b, c, metrics, rationale) -> Recommendation:
    return Recommendation(
        kind=kind, lever=lever, action=action, severity=severity,
        baseline=b.get("config", {}), candidate=c.get("config", {}),
        metrics=metrics, rationale=rationale,
    )


# --------------------------------------------------------------------------- #
# Cross-cutting detectors (regressions only; always checked)
# --------------------------------------------------------------------------- #
def _detect_control_fpr(b, c, t) -> list[Recommendation]:
    cb, cc = _m(b, "control_fpr"), _m(c, "control_fpr")
    if cc > cb + t.max_control_fpr_increase:
        return [_rec("control_fpr_increase", _lever(b, c) or "config", "rollback", "critical", b, c,
                     {"baseline_control_fpr": cb, "candidate_control_fpr": cc, "delta": _delta(cc, cb)},
                     f"Control false-positive rate rose {cb} -> {cc}. Legitimate-coordination controls "
                     "must not be flagged — do not promote; roll back if live.")]
    return []


def _detect_calibration(b, c, t) -> list[Recommendation]:
    np_c = _m(c, "number_preserved_rate", 1.0)
    if np_c < 1.0:
        return [_rec("calibration_drift", "number_preserved", "rollback", "critical", b, c,
                     {"candidate_number_preserved_rate": np_c},
                     f"number_preserved_rate {np_c} < 1.0: the AI moved the engine number on some cases "
                     "— a constitutional breach. Roll back.")]
    return []


def _detect_latency(b, c, t) -> list[Recommendation]:
    lb, lc = _m(b, "avg_latency_ms"), _m(c, "avg_latency_ms")
    if lb > 0 and lc > lb * t.max_latency_ratio:
        return [_rec("latency_regression", _lever(b, c) or "config", "hold", "regression", b, c,
                     {"baseline_latency_ms": lb, "candidate_latency_ms": lc, "ratio": round(lc / lb, 3)},
                     f"Average latency rose {lb}ms -> {lc}ms ({round(lc / lb, 2)}x). Hold pending review.")]
    return []


def _detect_citation(b, c, t) -> list[Recommendation]:
    cr = _m(c, "citation_retention", 1.0)
    if cr < t.min_citation_retention:
        return [_rec("citation_regression", _lever(b, c) or "config", "hold", "regression", b, c,
                     {"candidate_citation_retention": cr, "min": t.min_citation_retention},
                     f"Citation retention {cr} < {t.min_citation_retention}: some context statements "
                     "lost traceability. Hold.")]
    return []


def _detect_hallucination(b, c, t) -> list[Recommendation]:
    fb, fc = _m(b, "citation_failure_rate"), _m(c, "citation_failure_rate")
    if fc > fb + t.max_citation_failure_increase:
        return [_rec("hallucination_increase", _lever(b, c) or "config", "rollback", "regression", b, c,
                     {"baseline_citation_failure_rate": fb, "candidate_citation_failure_rate": fc,
                      "delta": _delta(fc, fb)},
                     f"Fabricated-citation (fallback) rate rose {fb} -> {fc}: the model cited evidence "
                     "that did not resolve more often. Do not promote.")]
    return []


def _detect_governor(b, c, t) -> list[Recommendation]:
    pb, pc = _m(b, "governor_permit_rate", 1.0), _m(c, "governor_permit_rate", 1.0)
    fb, fc = _m(b, "governor_floor_rate"), _m(c, "governor_floor_rate")
    if pc < pb - 1e-9 or fc > fb + t.max_governor_floor_increase:
        return [_rec("governor_violation_increase", _lever(b, c) or "config", "rollback", "regression", b, c,
                     {"baseline_permit_rate": pb, "candidate_permit_rate": pc,
                      "baseline_floor_rate": fb, "candidate_floor_rate": fc},
                     f"Governor outcomes worsened (permit {pb} -> {pc}, floor-fallback {fb} -> {fc}). "
                     "Do not promote.")]
    return []


# --------------------------------------------------------------------------- #
# Lever detector (improvement OR regression for the differing config key)
# --------------------------------------------------------------------------- #
_LEVER_KINDS = {
    "prompt_version": ("prompt_improvement", "prompt_regression"),
    "context_mode": ("context_improvement", "context_regression"),
    "enrich": ("evidence_improvement", "evidence_regression"),
}


def _detect_lever(lever, b, c, t) -> list[Recommendation]:
    ab, ac = _m(b, "agreement_rate"), _m(c, "agreement_rate")
    fpr_b, fpr_c = _m(b, "control_fpr"), _m(c, "control_fpr")
    gain = _delta(ac, ab)
    imp, reg = _LEVER_KINDS.get(lever, ("improvement", "regression"))
    metrics = {"baseline_agreement": ab, "candidate_agreement": ac, "agreement_gain": gain,
               "baseline_control_fpr": fpr_b, "candidate_control_fpr": fpr_c}
    if gain >= t.min_agreement_gain and fpr_c <= fpr_b:
        return [_rec(imp, lever, "promote", "improvement", b, c, metrics,
                     f"{lever} candidate raises label agreement {ab} -> {ac} (+{gain}) without raising "
                     f"control FPR ({fpr_b} -> {fpr_c}). Recommend promote (human approval required).")]
    if gain <= -t.min_agreement_gain:
        return [_rec(reg, lever, "rollback", "regression", b, c, metrics,
                     f"{lever} candidate lowers label agreement {ab} -> {ac} ({gain}). Recommend rollback "
                     "/ do not promote.")]
    return []


_DETECTORS = (_detect_control_fpr, _detect_calibration, _detect_latency, _detect_citation,
              _detect_hallucination, _detect_governor)


def recommend(baseline: dict, candidate: dict, *, thresholds: Thresholds = DEFAULT_THRESHOLDS) -> list[Recommendation]:
    """Compare ``candidate`` to ``baseline`` and return evidence-backed recommendations,
    deterministically ordered (most severe first). Empty when there is no actionable difference."""
    recs: list[Recommendation] = []
    for detect in _DETECTORS:
        recs.extend(detect(baseline, candidate, thresholds))
    lever = _lever(baseline, candidate)
    if lever:
        recs.extend(_detect_lever(lever, baseline, candidate, thresholds))
    return sorted(recs, key=lambda r: (_SEVERITY_RANK.get(r.severity, 9), r.id))
