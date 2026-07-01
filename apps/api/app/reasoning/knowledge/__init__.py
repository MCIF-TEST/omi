"""Institutional Intelligence Library (Sprint 025).

A structured layer of curated investigative EXPERTISE the AI specialists reason from — distinct
from Institutional Memory (observations) and the Prompt Registry (instructions). Content-addressed,
versioned, category-organized, graph-linked, and retrievable in constant time. GitHub is canonical;
the library is published alongside the prompts to Hugging Face (drift-guarded). Additive and inert:
it changes nothing about the Governor, OmiScore, memory, the council, or deployment.
"""
from __future__ import annotations

from .benchmark import benchmark
from .categories import CATEGORIES, CATEGORIES_BY_ID, KnowledgeCategory, taxonomy_hash
from .entry import KnowledgeEntry, Revision
from .library import IntelligenceLibrary, default_library
from .retrieval import KnowledgeIndex
from .specialists import (
    dependency_graph,
    duplicate_entries,
    orphan_entries,
    specialist_dependencies,
    unmapped_specialists,
)

__all__ = [
    "KnowledgeEntry", "Revision",
    "KnowledgeCategory", "CATEGORIES", "CATEGORIES_BY_ID", "taxonomy_hash",
    "IntelligenceLibrary", "default_library",
    "KnowledgeIndex",
    "specialist_dependencies", "dependency_graph", "unmapped_specialists",
    "orphan_entries", "duplicate_entries",
    "benchmark",
]
