"""OmiAnalyst orchestrator — the working entry point (OMI_ANALYST_IMPLEMENTATION_V1).

Wires the pieces: project evidence -> choose provider (Qwen gated / deterministic) ->
generate -> validate against ``analyst_response_schema.json`` -> store for future
training data -> return. Exposes the four required assessment types:

    assess_account(...)          -> A. Account Assessment
    assess_campaign(...)         -> B. Campaign Assessment
    assess_narrative(...)        -> C. Narrative Assessment
    summarize_investigation(...) -> D. Investigation Summary (rolls the others up)

Every returned response carries supporting evidence (``evidence_for``), contradicting
evidence (``evidence_against``), a confidence explanation (``confidence_band`` +
``confidence_rationale``), an uncertainty statement (``uncertainty``), and a
recommended next investigation step (``what_would_change_this``).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .config import AnalystConfig, load_analyst_config
from .evidence_bundle import (
    project_account_bundle,
    project_campaign_bundle,
    project_investigation_bundle,
    project_narrative_bundle,
)
from .providers import DeterministicAnalystProvider, get_analyst_provider
from .schema_validate import validate_analyst_response
from .store import AnalystOutputStore


@dataclass
class AssessmentOutcome:
    response: dict[str, Any]
    provider: str
    valid: bool
    errors: list[str] = field(default_factory=list)
    bundle: dict[str, Any] = field(default_factory=dict)

    def component_ref(self) -> dict[str, Any]:
        """Compact descriptor used to roll this assessment into an Investigation Summary."""
        r = self.response
        subj = r.get("subject", {})
        return {
            "grain": subj.get("grain"),
            "ref": subj.get("ref"),
            "verdict": r.get("verdict"),
            "suspicion_tier": r.get("suspicion_tier"),
            "suspicion_probability": r.get("suspicion_probability"),
            "headline": r.get("headline"),
        }


class OmiAnalyst:
    def __init__(
        self,
        config: AnalystConfig | None = None,
        provider: Any | None = None,
        store: AnalystOutputStore | None = None,
        *,
        validate: bool = True,
        record: bool = True,
    ) -> None:
        self.config = config or load_analyst_config()
        self.provider = provider or get_analyst_provider(self.config)
        self.store = store if store is not None else AnalystOutputStore()
        self.validate = validate
        self.record = record

    # -- core ----------------------------------------------------------------
    def assess(self, bundle: dict[str, Any]) -> AssessmentOutcome:
        result = self.provider.generate(bundle, self.config)
        errors = validate_analyst_response(result.response) if self.validate else []

        # If a non-deterministic provider produced an invalid object, degrade to the
        # always-valid deterministic provider rather than shipping a bad verdict.
        if errors and not isinstance(self.provider, DeterministicAnalystProvider):
            result = DeterministicAnalystProvider().generate(bundle, self.config)
            errors = validate_analyst_response(result.response) if self.validate else []

        if self.record and self.store is not None:
            self.store.record(
                response=result.response, provider=result.provider,
                bundle=bundle, valid=(not errors), validation_errors=errors,
            )
        return AssessmentOutcome(
            response=result.response, provider=result.provider,
            valid=(not errors), errors=errors, bundle=bundle,
        )

    # -- the four assessment types ------------------------------------------
    def assess_account(self, *, ref: str, platform: str, scan: dict,
                       memory: dict | None = None, trend: dict | None = None) -> AssessmentOutcome:
        bundle = project_account_bundle(ref=ref, platform=platform, scan=scan,
                                        memory=memory, trend=trend)
        return self.assess(bundle)

    def assess_campaign(self, *, ref: str, platform: str, campaign: dict) -> AssessmentOutcome:
        bundle = project_campaign_bundle(ref=ref, platform=platform, campaign=campaign)
        return self.assess(bundle)

    def assess_narrative(self, *, ref: str, platform: str, narrative: dict) -> AssessmentOutcome:
        bundle = project_narrative_bundle(ref=ref, platform=platform, narrative=narrative)
        return self.assess(bundle)

    def summarize_investigation(
        self, *, ref: str, platform: str, scan: dict | None = None,
        components: list[AssessmentOutcome] | None = None,
        cross_links: list[Any] | None = None,
    ) -> AssessmentOutcome:
        comp_refs = [c.component_ref() for c in (components or [])]
        bundle = project_investigation_bundle(
            ref=ref, platform=platform, scan=scan, components=comp_refs, cross_links=cross_links,
        )
        return self.assess(bundle)
