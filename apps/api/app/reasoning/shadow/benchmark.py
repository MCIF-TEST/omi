"""Prompt benchmarking over Shadow Mode (Sprint 008).

A/B evaluation between two versions of an analyst's prompt: run the shadow pipeline once per
variant (each pinning its prompt version) and compare the two AI-backed reads with the same
deterministic comparison engine used in Sprint 007. Every variant report carries the full
benchmark provenance (prompt / model / bundle / memory / governor revisions), so a result is
always attributable to an exact configuration. Deterministic given deterministic providers, so
A/B runs are replayable.
"""
from __future__ import annotations

from typing import Any

from app.reasoning.prompts import PromptExperiment, compare_prompts, default_registry

from .compare import compare
from .runner import run_shadow


def ab_evaluate(
    payload: dict, *, ref: str, experiment: PromptExperiment,
    provider_a: Any, provider_b: Any, platform: str = "youtube", grain: str = "comment_section",
    registry: Any = None, settings: Any | None = None, store: Any = None, now: Any = None,
) -> dict:
    """Run ``experiment``'s two prompt variants and compare them. ``provider_a`` / ``provider_b``
    drive each variant's AI analyst (inject mocks offline; the live provider when configured).
    Returns the prompt diff, the variant-vs-variant comparison, and both full reports."""
    registry = registry or default_registry()
    rep_a = run_shadow(
        payload, ref=ref, platform=platform, grain=grain, settings=settings, store=store, now=now,
        provider=provider_a, registry=registry, prompt_version=experiment.variant_a,
    )
    rep_b = run_shadow(
        payload, ref=ref, platform=platform, grain=grain, settings=settings, store=store, now=now,
        provider=provider_b, registry=registry, prompt_version=experiment.variant_b,
    )
    spec_a = registry.resolve(experiment.analyst, experiment.variant_a)
    spec_b = registry.resolve(experiment.analyst, experiment.variant_b)
    return {
        "experiment": {
            "analyst": experiment.analyst, "name": experiment.name,
            "variant_a": experiment.variant_a, "variant_b": experiment.variant_b,
        },
        "prompts": compare_prompts(spec_a, spec_b),
        "comparison": compare(rep_a.shadow, rep_b.shadow),   # variant A vs variant B (both AI-backed)
        "variant_a": rep_a.to_dict(),
        "variant_b": rep_b.to_dict(),
    }


def compare_context_modes(
    payload: dict, *, ref: str, provider_raw: Any, provider_structured: Any = None,
    budget: str = "standard", platform: str = "youtube", grain: str = "comment_section",
    registry: Any = None, settings: Any | None = None, store: Any = None, now: Any = None,
) -> dict:
    """Raw evidence context vs the structured Context Builder (Sprint 009): run the shadow
    pipeline once per context mode (same prompt, same model) and compare the two AI reads, plus
    surface the context-quality metrics of each. Determines whether *structuring* the context —
    not changing the model — improves the read. ``provider_structured`` defaults to
    ``provider_raw`` so a single deterministic provider drives a clean A/B."""
    provider_structured = provider_structured or provider_raw
    rep_raw = run_shadow(
        payload, ref=ref, platform=platform, grain=grain, settings=settings, store=store, now=now,
        provider=provider_raw, registry=registry, context_mode="raw",
    )
    rep_structured = run_shadow(
        payload, ref=ref, platform=platform, grain=grain, settings=settings, store=store, now=now,
        provider=provider_structured, registry=registry, context_mode="structured", context_budget=budget,
    )
    return {
        "comparison": compare(rep_raw.shadow, rep_structured.shadow),
        "raw_context": rep_raw.context,
        "structured_context": rep_structured.context,
        "raw": rep_raw.to_dict(),
        "structured": rep_structured.to_dict(),
    }
