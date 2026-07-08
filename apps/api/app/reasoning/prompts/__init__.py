"""Intelligence Optimization Framework — prompt registry (Sprint 008).

Versioned, content-addressed prompts with config-driven selection, rollback, experiments, and
comparison. AI-backed analysts execute from a registered :class:`PromptSpec` rather than
embedded text, so reasoning quality can be improved through measurable, version-controlled
prompt evolution — without touching the architecture or any constitutional guarantee.
"""
from __future__ import annotations

from .constitution import (
    CONSTITUTION,
    CONSTITUTION_VERSION,
    ConstitutionBlock,
    constitution_hash,
    constitution_text,
)
from .registry import (
    PromptExperiment,
    PromptRegistry,
    compare_prompts,
    default_registry,
)
from .behavioral import (  # noqa: F401 — importing registers the behavioral framework overrides
    BEHAVIORAL_LIBRARY_VERSION,
    behavior_v2_prompt_spec,
    render_behavioral_handbook,
)
from .framework import (
    FRAMEWORK_VERSION,
    SpecialistProfile,
    framework_hash,
    framework_profiles,
    lift,
    new_specialist,
    validate_framework,
)
from .spec import PromptSpec
from .template import (
    PROMPT_TEMPLATE_VERSION,
    RESPONSE_CONTRACT,
    assembly_template,
    contract_hash,
    response_contract,
    template_hash,
)
from .specialists import (
    LIBRARY_VERSION,
    SPECIALISTS,
    SpecialistSpec,
    register_specialist_library,
    render,
    specialist_prompt_specs,
)

__all__ = [
    "PromptSpec", "PromptRegistry", "PromptExperiment",
    "compare_prompts", "default_registry",
    # Phase 3 — constitutional building blocks
    "CONSTITUTION", "CONSTITUTION_VERSION", "ConstitutionBlock",
    "constitution_hash", "constitution_text",
    # Phase 2 — specialist prompt library
    "LIBRARY_VERSION", "SPECIALISTS", "SpecialistSpec",
    "register_specialist_library", "render", "specialist_prompt_specs",
    # Phase A1 — the Specialist Intelligence Framework
    "FRAMEWORK_VERSION", "SpecialistProfile", "framework_profiles", "framework_hash",
    "lift", "new_specialist", "validate_framework",
    # Phase B1 — the Behavioral Intelligence Library (reference implementation)
    "BEHAVIORAL_LIBRARY_VERSION", "behavior_v2_prompt_spec", "render_behavioral_handbook",
    # Phase P1.1 — the Prompt Template + Response Contract assembly asset
    "PROMPT_TEMPLATE_VERSION", "RESPONSE_CONTRACT", "assembly_template", "response_contract",
    "template_hash", "contract_hash",
]
