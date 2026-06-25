"""The Orchestrator — the deterministic control plane (OMI_REASONING_ORCHESTRATION_V1 §A).

Binds the payload into a canonical Evidence Bundle, runs the council in tier order over a
phase-gated Blackboard, validates every artifact against its contract, adjudicates with the
Judge, then puts the Ruling through the **mandatory Governor**. On REJECT it ships the
deterministic **Floor** (FloorJudge), itself Governor-validated. Fully deterministic: the
same payload yields the same assessment and the same ValidationTrace.

The control plane never reasons; the modules do. Swapping a deterministic analyst for a
Qwen-backed one is a change of module list, not of orchestration.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from app.evidence import Binder
from app.governor import Governor
from app.governor.audit import ValidationTrace

from app.reasoning.contracts import Ruling, validate_artifact

from .blackboard import Blackboard
from .modules import AnalystModule, FloorJudge, Judge, default_council

logger = logging.getLogger("omi.reasoning.orchestrator")


class BudgetController:
    """Decides the cognitive budget for a bundle. Conservative by default: convene the
    council when invoked, but the seam exists to route low-stakes cases to the Floor only."""

    def decide(self, bundle: Any) -> str:  # "council" | "floor_only"
        return "council"


@dataclass
class CouncilResult:
    assessment: dict[str, Any]
    trace: ValidationTrace
    fallback: bool
    bundle_id: str
    rejected_codes: list[str] = field(default_factory=list)
    blackboard: Blackboard | None = None

    @property
    def permitted(self) -> bool:
        return self.trace.permitted


class Orchestrator:
    """Runs the Analyst Council deterministically, Governor-gated, Floor-backed."""

    def __init__(
        self,
        modules: list[AnalystModule] | None = None,
        *,
        judge: AnalystModule | None = None,
        floor: AnalystModule | None = None,
        governor: Governor | None = None,
        budget: BudgetController | None = None,
    ) -> None:
        self.modules = list(modules) if modules is not None else default_council()
        self.judge = judge or Judge()
        self.floor = floor or FloorJudge()
        self.governor = governor or Governor()
        self.budget = budget or BudgetController()

    def run(self, payload: dict, *, ref: str, platform: str = "youtube",
            grain: str = "comment_section") -> CouncilResult:
        bundle = Binder().bind(payload, grain=grain, subject_ref=ref, platform=platform)
        bb = Blackboard(bundle)

        if self.budget.decide(bundle) == "floor_only":
            ruling = self._ruling_from(self.floor, bb)
        else:
            # Phase execution: tier order; each artifact is contract-validated before posting
            # (an invalid artifact is dropped, never posted — the council degrades, never breaks).
            for module in sorted(self.modules, key=lambda m: m.contract.tier):
                view = bb.view_for(module.contract)
                for art in module.run(view):
                    ok, errors = validate_artifact(module.contract, art, bb)
                    if ok:
                        bb.post(art, module.contract.tier)
                    else:
                        logger.warning("dropping invalid %s artifact: %s", module.contract.module, errors[:3])
            ruling = self._ruling_from(self.judge, bb)

        # --- MANDATORY Governor gate ---------------------------------------- #
        trace = self.governor.validate(
            ruling.assessment, bundle, corroboration=ruling.assessment.get("corroboration"),
        )
        if trace.permitted:
            return CouncilResult(assessment=ruling.assessment, trace=trace, fallback=False,
                                 bundle_id=bundle.bundle_id(), blackboard=bb)

        # REJECT -> deterministic Floor (itself Governor-validated)
        logger.warning("council ruling REJECTED %s; falling back to Floor", trace.violation_codes)
        floor_ruling = self._ruling_from(self.floor, bb)
        ftrace = self.governor.validate(
            floor_ruling.assessment, bundle, corroboration=floor_ruling.assessment.get("corroboration"),
        )
        return CouncilResult(
            assessment=floor_ruling.assessment, trace=ftrace, fallback=True,
            bundle_id=bundle.bundle_id(), rejected_codes=trace.violation_codes, blackboard=bb,
        )

    @staticmethod
    def _ruling_from(module: AnalystModule, bb: Blackboard) -> Ruling:
        out = module.run(bb.view_for(module.contract))
        rulings = [a for a in out if isinstance(a, Ruling)]
        if not rulings:
            raise ValueError(f"{module.contract.module} did not produce a Ruling")
        return rulings[0]
