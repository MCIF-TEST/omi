"""Omi Analyst — working implementation (OMI_ANALYST_IMPLEMENTATION_V1).

A runnable, schema-validated reasoning layer that *interprets* OmiSphere engine
evidence into four assessment types (account, campaign, narrative, investigation),
each carrying supporting evidence, contradicting evidence, a confidence explanation,
an uncertainty statement, and a recommended next investigation step.

It mirrors the existing ``app/reasoning/`` provider protocol (so it is drop-in as the
``OmiAnalystProvider``), loads its config from the registered HF model repo
``Andrewexiga/omi-analyst-v1``, is powered by ``Qwen/Qwen3-4B-Thinking-2507-FP8`` when
enabled, and ALWAYS works via a deterministic, schema-valid fallback (the spec's
always-on ``TemplateProvider`` analogue) so it runs and is testable with no GPU.

It does NOT train, fine-tune, or modify detectors / scoring / OmiScore — it consumes
their already-computed evidence.
"""
from __future__ import annotations

from .analyst import OmiAnalyst
from .config import AnalystConfig, load_analyst_config
from .providers import (
    AnalystResult,
    DeterministicAnalystProvider,
    QwenAnalystProvider,
    get_analyst_provider,
)
from .schema_validate import validate_analyst_response
from .store import AnalystOutputStore

__all__ = [
    "OmiAnalyst",
    "AnalystConfig",
    "load_analyst_config",
    "AnalystResult",
    "DeterministicAnalystProvider",
    "QwenAnalystProvider",
    "get_analyst_provider",
    "validate_analyst_response",
    "AnalystOutputStore",
]
