"""Gold evaluation corpus (Sprint 008) — curated, human-reviewed investigations.

Infrastructure for measuring reasoning quality against a fixed, labeled set: each
``GoldCase`` carries an investigation payload plus a human benchmark label (expected read,
and whether it is a **legitimate-coordination control** — the precision frontier). The corpus
is for **evaluation, not training** (it never feeds a model); it supports replay, regression
testing, and prompt comparison by running the Shadow Mode pipeline over every case
deterministically and scoring against the labels.

Key metrics: agreement with the human label, and — for controls — the **false-positive rate**
(a legitimate, on-message group must not be read as hostile coordination). Promotion of any AI
prompt or specialist should be gated on these numbers, never on capability alone.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.reasoning.shadow import run_shadow

# Reads that constitute flagging a subject as hostile coordination (a false positive on a control).
_HOSTILE_LABELS = frozenset({"suspicious", "coordinated", "manipulation_network"})
_HOSTILE_VERDICTS = frozenset({"likely_inauthentic"})


@dataclass
class GoldCase:
    """One human-reviewed benchmark investigation. ``label`` holds the reviewed expectation:
    ``expected_verdict`` / ``expected_coordination_label`` / ``is_control``."""

    id: str
    payload: dict
    label: dict = field(default_factory=dict)
    ref: str = ""
    platform: str = "youtube"
    grain: str = "comment_section"
    reviewer: str = ""
    notes: str = ""


class GoldCorpus:
    """A curated set of ``GoldCase``s. Deterministic ordering by id for replayable evaluation."""

    def __init__(self) -> None:
        self._cases: dict[str, GoldCase] = {}

    def add(self, case: GoldCase) -> GoldCase:
        self._cases[case.id] = case
        return case

    def get(self, case_id: str) -> GoldCase:
        return self._cases[case_id]

    def all(self) -> list[GoldCase]:
        return [self._cases[k] for k in sorted(self._cases)]

    def controls(self) -> list[GoldCase]:
        return [c for c in self.all() if c.label.get("is_control")]

    def __len__(self) -> int:
        return len(self._cases)


def _label_agreement(assessment: dict, label: dict) -> dict:
    out: dict[str, bool] = {}
    if "expected_verdict" in label:
        out["verdict_match"] = assessment.get("verdict") == label["expected_verdict"]
    if "expected_coordination_label" in label:
        out["coordination_match"] = assessment.get("coordination_label") == label["expected_coordination_label"]
    return out


def _is_false_positive(assessment: dict) -> bool:
    """A legitimate (control) subject read as hostile coordination — verdict or coordination label."""
    return (
        assessment.get("coordination_label") in _HOSTILE_LABELS
        or assessment.get("verdict") in _HOSTILE_VERDICTS
    )


def _rate(num: int, den: int) -> float | None:
    return round(num / den, 4) if den else None


def evaluate_corpus(
    corpus: GoldCorpus, *, registry: Any = None, prompt_version: str | None = None,
    provider: Any = None, settings: Any | None = None, store: Any = None, now: Any = None,
    context_mode: Any = None, context_budget: Any = None, enrich: bool = False,
) -> dict:
    """Run the shadow pipeline over every case and score against the human labels. Deterministic
    given a deterministic provider — so re-running it is a regression test, and running it under
    a different ``prompt_version`` / ``context_mode`` / ``enrich`` is a lever comparison. Returns
    per-case results, the full shadow reports, and a summary (label agreement, control FPR for
    both paths, number-preserved rate)."""
    cases = corpus.all()
    results: list[dict] = []
    reports: list[dict] = []
    for case in cases:
        rep = run_shadow(
            case.payload, ref=case.ref or case.id, platform=case.platform, grain=case.grain,
            settings=settings, store=store, now=now, provider=provider,
            registry=registry, prompt_version=prompt_version,
            context_mode=context_mode, context_budget=context_budget, enrich=enrich,
        )
        reports.append(rep.to_dict())
        prod_a = rep.production["assessment"]
        shadow_a = rep.shadow["assessment"]
        is_control = bool(case.label.get("is_control"))
        results.append({
            "id": case.id,
            "is_control": is_control,
            "production_label_agreement": _label_agreement(prod_a, case.label),
            "shadow_label_agreement": _label_agreement(shadow_a, case.label),
            "production_false_positive": is_control and _is_false_positive(prod_a),
            "shadow_false_positive": is_control and _is_false_positive(shadow_a),
            "comparison": rep.comparison,
            "versioning": rep.versioning,
        })

    controls = [r for r in results if r["is_control"]]
    summary = {
        "n": len(results),
        "controls": len(controls),
        "production_control_fpr": _rate(sum(1 for r in controls if r["production_false_positive"]), len(controls)),
        "shadow_control_fpr": _rate(sum(1 for r in controls if r["shadow_false_positive"]), len(controls)),
        "agreement_rate": _rate(sum(1 for r in results if r["comparison"]["overall_agreement"]), len(results)),
        "number_preserved_rate": _rate(sum(1 for r in results if r["comparison"]["number_preserved"]), len(results)),
        "prompt_version": prompt_version or (registry.active_version("behavior_analyst") if registry else None),
    }
    return {"summary": summary, "cases": results, "reports": reports}
