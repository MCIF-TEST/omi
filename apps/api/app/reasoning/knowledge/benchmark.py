"""Intelligence Library — benchmark (Sprint 025, Phase 6).

Measures the library on the axes the charter names: coverage, retrieval speed, duplication,
knowledge completeness, and specialist utilization. Pure + deterministic (except the timing
micro-benchmark); grounds the Phase-7 reports in real numbers rather than assertion.
"""
from __future__ import annotations

from .categories import CATEGORIES
from .entry import KnowledgeEntry
from .library import IntelligenceLibrary, _SPECIALIST_KEYS, default_library
from .retrieval import KnowledgeIndex
from .specialists import duplicate_entries, specialist_dependencies, unmapped_specialists

# The metadata fields an entry must populate to count as "complete".
_REQUIRED = ("definition", "purpose", "indicators", "counter_indicators", "evidence_requirements",
             "limitations", "false_positive_risks", "constitutional_constraints", "relationships")


def _complete(e: KnowledgeEntry) -> bool:
    return all(getattr(e, f) for f in _REQUIRED)


def benchmark(lib: IntelligenceLibrary | None = None) -> dict:
    lib = lib or default_library()
    entries = lib.active()
    cats_present = {e.category for e in entries}
    per_cat = {c.id: len(lib.by_category(c.id)) for c in CATEGORIES}
    deps = specialist_dependencies(lib)
    idx = KnowledgeIndex(lib)

    return {
        "coverage": {
            "entries": len(entries),
            "categories_total": len(CATEGORIES),
            "categories_covered": len(cats_present),
            "empty_categories": sorted(c.id for c in CATEGORIES if per_cat[c.id] == 0),
            "entries_per_category": per_cat,
        },
        "retrieval_speed": idx.measure_latency(),
        "duplication": {
            "duplicate_hash_groups": duplicate_entries(lib),
            "duplicate_free": not duplicate_entries(lib),
        },
        "knowledge_completeness": {
            "complete_entries": sum(1 for e in entries if _complete(e)),
            "total_entries": len(entries),
            "avg_sections_present": round(sum(e.sections_present() for e in entries) / max(1, len(entries)), 2),
            "integrity_issues": lib.validate(),
        },
        "specialist_utilization": {
            "specialists_total": len(_SPECIALIST_KEYS),
            "specialists_with_knowledge": sum(1 for v in deps.values() if v),
            "unmapped_specialists": unmapped_specialists(lib),
            "entries_per_specialist": {k: len(v) for k, v in deps.items()},
        },
        "library_hash": lib.library_hash(),
    }


__all__ = ["benchmark"]
