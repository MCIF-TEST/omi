"""The Prompt Registry (Sprint 008) — versioning, selection, rollback, comparison.

The registry is the single source of truth for AI-analyst prompts. It records, per analyst,
every versioned :class:`PromptSpec` and which version is *active*. Selection is
configuration-driven: an analyst executes the active version unless a caller (or settings)
pins a specific one, so promoting, A/B-testing, or **rolling back** a prompt is a config/version
change — never a code edit. The default registry seeds the shipped prompts; ``compare_prompts``
and ``PromptExperiment`` support controlled prompt evolution.
"""
from __future__ import annotations

from dataclasses import dataclass

from .spec import PromptSpec

# --------------------------------------------------------------------------- #
# Shipped behavior-analyst prompts. v1 is the exact prompt the AI specialist has
# used since Sprint 006 (now versioned, not embedded); v2 is a refined variant
# available for A/B evaluation. Both honor the same constitutional constraints.
# --------------------------------------------------------------------------- #
_BEHAVIOR_V1 = (
    "You are OMI BEHAVIOR ANALYST, a Tier-1 specialist inside a constitutional reasoning "
    "council. You receive behavioral evidence items (each with a stable id) and optional "
    "prior context. For each informative behavioral signal, emit a short, probabilistic "
    "finding. RULES: cite ONLY the provided evidence ids — never invent an id; prior context "
    "is background, NOT proof, and must never be cited as evidence; never assert a verdict or "
    "a probability number; expose uncertainty honestly. Output ONE JSON object: "
    '{"findings":[{"signal":"...","claim":"...","direction":"raises|lowers|neutral",'
    '"evidence_refs":["ev:...."]}],"uncertainty":["..."]}. Output only the JSON object.'
)

_BEHAVIOR_V2 = (
    "You are OMI BEHAVIOR ANALYST, a Tier-1 specialist inside a constitutional reasoning "
    "council. You are given behavioral evidence items (each with a stable id) and optional "
    "prior context. Emit one finding per informative signal, ordered strongest first, and "
    "weigh exculpatory (lowering) evidence as carefully as incriminating (raising) evidence. "
    "RULES: cite ONLY the provided evidence ids — never invent an id; prior context is "
    "background, NOT proof, and must never be cited as evidence; never assert a verdict or a "
    "probability number; state uncertainty explicitly when the signal is thin. Output ONE JSON "
    'object: {"findings":[{"signal":"...","claim":"...","direction":"raises|lowers|neutral",'
    '"evidence_refs":["ev:...."]}],"uncertainty":["..."]}. Output only the JSON object.'
)

_BEHAVIOR_CONSTRAINTS = (
    "cite only provided bundle evidence ids; never fabricate",
    "prior context is background, never proof, never cited",
    "never assert a verdict or move the engine number",
    "supplemental signals carry zero suspicion weight",
    "expose uncertainty honestly",
)
_BEHAVIOR_OBJECTIVES = (
    "interpret behavioral signals into cited, probabilistic findings",
    "surface both raising and lowering evidence",
)


class PromptRegistry:
    """A versioned store of prompts with a config-driven active selection per analyst."""

    def __init__(self) -> None:
        self._specs: dict[tuple[str, str], PromptSpec] = {}
        self._active: dict[str, str] = {}

    def register(self, spec: PromptSpec, *, activate: bool = False) -> PromptSpec:
        """Add a versioned prompt. The first registered version for an analyst becomes active;
        pass ``activate=True`` to make a later version active on registration."""
        self._specs[(spec.analyst, spec.prompt_version)] = spec
        if activate or spec.analyst not in self._active:
            self._active[spec.analyst] = spec.prompt_version
        return spec

    def get(self, analyst: str, version: str) -> PromptSpec:
        return self._specs[(analyst, version)]

    def resolve(self, analyst: str, version: str | None = None) -> PromptSpec:
        """The spec to execute: an explicit ``version`` if given, else the active one."""
        return self._specs[(analyst, version or self.active_version(analyst))]

    def active_version(self, analyst: str) -> str:
        if analyst not in self._active:
            raise KeyError(f"no prompts registered for analyst {analyst!r}")
        return self._active[analyst]

    def set_active(self, analyst: str, version: str) -> None:
        """Config-driven selection. Setting it to a prior version is a **rollback**."""
        if (analyst, version) not in self._specs:
            raise KeyError(f"unknown prompt {analyst!r} {version!r}")
        self._active[analyst] = version

    def rollback(self, analyst: str, version: str) -> None:
        self.set_active(analyst, version)

    def versions(self, analyst: str) -> list[str]:
        return sorted(v for (a, v) in self._specs if a == analyst)

    def analysts(self) -> list[str]:
        return sorted({a for (a, _) in self._specs})

    def records(self, analyst: str | None = None) -> list[dict]:
        """Serializable registry listing (for the observability APIs), with an ``active`` flag."""
        out: list[dict] = []
        for (a, v), spec in sorted(self._specs.items()):
            if analyst is not None and a != analyst:
                continue
            rec = spec.to_record()
            rec["active"] = (self._active.get(a) == v)
            out.append(rec)
        return out


@dataclass(frozen=True)
class PromptExperiment:
    """An A/B configuration between two registered versions of one analyst's prompt."""

    analyst: str
    variant_a: str
    variant_b: str
    name: str = ""


def compare_prompts(a: PromptSpec, b: PromptSpec) -> dict:
    """A deterministic metadata diff between two prompt versions (for review + benchmarking)."""
    return {
        "analyst": {"a": a.analyst, "b": b.analyst},
        "version": {"a": a.prompt_version, "b": b.prompt_version},
        "hash": {"a": a.prompt_hash, "b": b.prompt_hash, "identical": a.prompt_hash == b.prompt_hash},
        "template_changed": a.template != b.template,
        "constraints": {
            "a_only": sorted(set(a.constraints) - set(b.constraints)),
            "b_only": sorted(set(b.constraints) - set(a.constraints)),
        },
        "objectives": {
            "a_only": sorted(set(a.reasoning_objectives) - set(b.reasoning_objectives)),
            "b_only": sorted(set(b.reasoning_objectives) - set(a.reasoning_objectives)),
        },
        "expected_output_contract": {
            "a": a.expected_output_contract, "b": b.expected_output_contract,
            "match": a.expected_output_contract == b.expected_output_contract,
        },
    }


def default_registry() -> PromptRegistry:
    """A freshly-seeded registry with the shipped prompts. Deterministic and side-effect-free —
    the active version is the conservative default (behavior ``v1``); config selects otherwise."""
    reg = PromptRegistry()
    reg.register(PromptSpec(
        analyst="behavior_analyst", prompt_version="v1", template=_BEHAVIOR_V1,
        created_at="2026-06-26", author="omi-engineering",
        model_compatibility=("Qwen/Qwen3-4B-Thinking-2507-FP8", "qwen-family"),
        reasoning_objectives=_BEHAVIOR_OBJECTIVES, constraints=_BEHAVIOR_CONSTRAINTS,
        expected_output_contract="finding",
    ), activate=True)
    reg.register(PromptSpec(
        analyst="behavior_analyst", prompt_version="v2", template=_BEHAVIOR_V2,
        created_at="2026-06-26", author="omi-engineering",
        model_compatibility=("Qwen/Qwen3-4B-Thinking-2507-FP8", "qwen-family"),
        reasoning_objectives=_BEHAVIOR_OBJECTIVES + ("rank findings strongest-first",),
        constraints=_BEHAVIOR_CONSTRAINTS, expected_output_contract="finding",
    ))
    return reg
