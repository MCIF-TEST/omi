"""Deterministic Evidence layer (OMI_EVIDENCE_BUNDLE_SPEC_V1 / Sprint 002).

The canonical, normalized, content-addressed Evidence Bundle and the Binder that
projects existing engine outputs into it. Deterministic and model-free; imports
nothing from the detection engine and changes no existing behavior — a new, additive
foundation the Cognitive Engine will consume.
"""
from __future__ import annotations

from .bundle import (
    BUNDLE_SCHEMA_VERSION,
    DISCRIMINATIVE_METHODS,
    EvidenceBundle,
    EvidenceItem,
    Entity,
    Relationship,
    canonical_json,
    digest,
)
from .binder import Binder
from .enrich import enrich_bundle
from .quality import evidence_quality

__all__ = [
    "BUNDLE_SCHEMA_VERSION",
    "DISCRIMINATIVE_METHODS",
    "EvidenceBundle",
    "EvidenceItem",
    "Entity",
    "Relationship",
    "Binder",
    "enrich_bundle",
    "evidence_quality",
    "canonical_json",
    "digest",
]
