"""AI-backed council specialists — real reasoning inside the constitutional architecture.

This is the proof Sprint 006 exists to deliver: a model can participate in the council
**without changing the surrounding system**. A :class:`RemoteAnalyst` is a drop-in for an
existing Reasoning Contract — it carries the *same* contract as the deterministic analyst it
shadows, so the Orchestrator, Blackboard, Contracts, and Governor are untouched. It delegates
reasoning to a model-agnostic :class:`ReasoningProvider`, then enforces the constitution in
code:

- consumes only the information its contract permits (here: behavioral evidence) + optional
  PriorContext (background, never proof);
- cites **bundle** evidence ids — and validates every citation resolves, so the model can
  **never fabricate evidence** (a fabricated ref triggers fallback, not a bad artifact);
- exposes uncertainty; never asserts a verdict or moves the engine number;
- on **any** failure (provider down, timeout, malformed output, fabricated citation) falls
  back to the deterministic analyst, so the council always receives valid findings.

The Governor downstream remains mandatory. The only thing that changes when a real endpoint
appears is configuration.
"""
from __future__ import annotations

import logging
from typing import Any, Callable

from app.reasoning.context import build_context, raw_context_text

from app.reasoning.contracts import Artifact, Finding, ReasoningContract
from app.reasoning.model_providers import ReasoningProvider, ReasoningRequest, ReasoningResponse
from app.reasoning.prompts import PromptRegistry, default_registry

from .blackboard import BlackboardView
from .modules import AnalystModule, BehaviorAnalyst, CounterEvidenceAnalyst

logger = logging.getLogger("omi.reasoning.ai")

PromptBuilder = Callable[[BlackboardView], ReasoningRequest]
ArtifactParser = Callable[[ReasoningResponse, BlackboardView], list[Artifact]]


class RemoteAnalyst:
    """A council module that delegates reasoning to a provider and falls back to a
    deterministic analyst on any failure. Carries the *same contract* as its fallback, so it
    is a true drop-in. Records ``last_diagnostics`` (ai | fallback + provider telemetry)."""

    def __init__(
        self, *, contract: ReasoningContract, provider: ReasoningProvider,
        prompt_builder: PromptBuilder, parser: ArtifactParser, fallback: AnalystModule,
    ) -> None:
        self.contract = contract
        self._provider = provider
        self._prompt = prompt_builder
        self._parser = parser
        self._fallback = fallback
        self.last_diagnostics: dict[str, Any] = {"mode": "uninitialized"}
        self.prompt_meta: dict[str, Any] = {}      # {analyst, version, hash} — set by the factory
        self.last_context: dict[str, Any] = {}     # structured-context metrics — set per run

    def run(self, view: BlackboardView) -> list[Artifact]:
        provider_name = getattr(self._provider, "name", "?")
        try:
            request = self._prompt(view)
            response = self._provider.complete(request)
            artifacts = self._parser(response, view)
            if not artifacts:
                raise ValueError("provider returned no usable artifacts")
            for art in artifacts:
                for ref in (art.evidence_refs or []):
                    if not view.resolve(ref):
                        raise ValueError(f"fabricated evidence_ref {ref!r}")
            self.last_diagnostics = {
                "mode": "ai", "provider": provider_name, "artifacts": len(artifacts),
                **(response.diagnostics or {}),
            }
            return artifacts
        except Exception as exc:  # noqa: BLE001 — graceful fallback to the deterministic analyst
            logger.warning("AI specialist %s fell back to deterministic: %s",
                           self.contract.module, exc)
            self.last_diagnostics = {
                "mode": "fallback", "provider": provider_name,
                "reason": type(exc).__name__, "detail": str(exc)[:160],
            }
            return self._fallback.run(view)


# --------------------------------------------------------------------------- #
# The first AI specialist: an AI-backed Behavior Analyst (Tier 1, Findings)
# --------------------------------------------------------------------------- #
def _behavior_prompt(
    view: BlackboardView, *, system: str, store: Any = None, now: Any = None,
) -> ReasoningRequest:
    """RAW context: contract-permitted behavioral evidence (non-supplemental contributions) +
    PriorContext as labeled background. The pre-Sprint-009 baseline, unchanged."""
    user = raw_context_text(view.bundle, store, now)
    return ReasoningRequest(system=system, user=user, response_format="json")


def _parse_findings(response: ReasoningResponse, view: BlackboardView, *, module: str) -> list[Artifact]:
    """Map the model's structured output into Finding artifacts. Defensive: clamps direction,
    keeps only string evidence_refs, drops findings citing supplemental evidence (which may
    never raise suspicion). Citation *resolution* is enforced by RemoteAnalyst."""
    obj = response.structured or {}
    supplemental_ids = {it.id for it in view.bundle.evidence.values() if it.supplemental}
    out: list[Artifact] = []
    for f in (obj.get("findings") or []):
        if not isinstance(f, dict):
            continue
        direction = f.get("direction", "neutral")
        if direction not in ("raises", "lowers", "neutral"):
            direction = "neutral"
        refs = [r for r in (f.get("evidence_refs") or []) if isinstance(r, str)]
        if direction == "raises" and any(r in supplemental_ids for r in refs):
            continue  # supplemental signals are context, never suspicion
        out.append(Finding(
            module=module, signal=str(f.get("signal", "?")), claim=str(f.get("claim", "")),
            direction=direction, evidence_refs=refs,
        ))
    return out


def ai_behavior_analyst(
    provider: ReasoningProvider, *, store: Any = None, now: Any = None,
    fallback: AnalystModule | None = None, registry: PromptRegistry | None = None,
    prompt_version: str | None = None, settings: Any | None = None,
    context_mode: str | None = None, context_budget: str | None = None,
) -> RemoteAnalyst:
    """The first AI-backed specialist: a drop-in for the Behavior Analyst contract that reasons
    via ``provider`` from a **versioned prompt** (registry-resolved, never embedded) and falls
    back to the deterministic ``BehaviorAnalyst`` on any failure. Prompt selection and context
    mode are config-driven (explicit arg → settings → default). ``context_mode`` is ``"raw"``
    (baseline) or ``"structured"`` (the Sprint-009 Context Builder, captured into
    ``last_context`` for Shadow Mode). ``store`` (optional) supplies PriorContext."""
    registry = registry or default_registry()
    if prompt_version is None and settings is not None:
        prompt_version = getattr(settings, "analyst_prompt_version", None)
    if context_mode is None:
        context_mode = getattr(settings, "analyst_context_mode", None) if settings is not None else None
        context_mode = context_mode or "raw"
    if context_budget is None:
        context_budget = (getattr(settings, "analyst_context_budget", None) if settings is not None else None) or "standard"

    spec = registry.resolve("behavior_analyst", prompt_version)
    fb = fallback or BehaviorAnalyst()
    module = fb.contract.module
    analyst = RemoteAnalyst(
        contract=fb.contract, provider=provider,
        prompt_builder=lambda v: _behavior_prompt(v, system=spec.template, store=store, now=now),
        parser=lambda resp, v: _parse_findings(resp, v, module=module),
        fallback=fb,
    )
    if context_mode == "structured":
        def _structured(view: BlackboardView) -> ReasoningRequest:
            ctx = build_context(
                view.bundle, store=store, now=now, budget=context_budget, inputs=fb.contract.inputs,
            )
            analyst.last_context = {
                "mode": "structured", "version": ctx.context_version, "budget": ctx.budget,
                "hash": ctx.context_hash, "metrics": ctx.metrics,
            }
            return ReasoningRequest(system=spec.template, user=ctx.to_prompt_text(), response_format="json")
        analyst._prompt = _structured
    else:
        analyst.last_context = {"mode": "raw"}

    analyst.prompt_meta = {
        "analyst": "behavior_analyst", "version": spec.prompt_version, "hash": spec.prompt_hash,
        "context_mode": context_mode, "context_budget": context_budget,
    }
    return analyst


# --------------------------------------------------------------------------- #
# Config-driven council assembly (activation = configuration, not architecture)
# --------------------------------------------------------------------------- #
def build_council(settings: Any | None = None, *, store: Any = None, now: Any = None) -> list[AnalystModule]:
    """Assemble the council from configuration. When the analyst is enabled AND an endpoint is
    configured, the Behavior Analyst is AI-backed (Qwen via the remote provider); otherwise the
    council is fully deterministic. When ``store`` is given, the Memory Analyst is included.
    The Orchestrator, Governor, and Floor are identical either way."""
    if settings is None:
        from app.core.config import get_settings
        settings = get_settings()
    from app.reasoning.model_providers import build_remote_provider

    provider = build_remote_provider(settings) if getattr(settings, "analyst_enabled", False) else None
    behavior: AnalystModule = (
        ai_behavior_analyst(provider, store=store, now=now, settings=settings)
        if provider is not None else BehaviorAnalyst()
    )
    council: list[AnalystModule] = [behavior]
    if store is not None:
        from .modules import MemoryAnalyst
        council.append(MemoryAnalyst(store, now=now))
    council.append(CounterEvidenceAnalyst())
    return council
