"""Intelligence Library — specialist dependency mapping (Sprint 025, Phase 3).

Which Library entries each specialist should reason from. The mapping is DERIVED from each entry's
own ``specialists`` field (the single source of truth), so there is no separate, duplicable map to
drift. Produces the per-specialist reading list, the dependency graph (specialist -> entries ->
categories), and the gap/duplication checks the charter requires ("no duplicate knowledge").
"""
from __future__ import annotations

from .library import IntelligenceLibrary, _SPECIALIST_KEYS, default_library


def specialist_dependencies(lib: IntelligenceLibrary | None = None) -> dict[str, list[str]]:
    """``{specialist_key: [entry_ids]}`` — each specialist's reading list, deterministic order."""
    lib = lib or default_library()
    deps: dict[str, list[str]] = {k: [] for k in _SPECIALIST_KEYS}
    for e in lib.active():
        for spec in e.specialists:
            if spec in deps:
                deps[spec].append(e.id)
    return {k: sorted(v) for k, v in deps.items()}


def dependency_graph(lib: IntelligenceLibrary | None = None) -> dict:
    """The full Phase-3 graph: per specialist, the entries it reads and the categories they span,
    plus coverage counts. Explainable — every edge traces to an entry's declared consumers."""
    lib = lib or default_library()
    deps = specialist_dependencies(lib)
    by_id = {e.id: e for e in lib.active()}
    nodes = {}
    for spec, entry_ids in deps.items():
        cats = sorted({by_id[i].category for i in entry_ids})
        nodes[spec] = {"entries": entry_ids, "entry_count": len(entry_ids), "categories": cats}
    return {
        "specialists": nodes,
        "coverage": {
            "specialists_total": len(_SPECIALIST_KEYS),
            "specialists_with_knowledge": sum(1 for v in deps.values() if v),
            "unmapped_specialists": unmapped_specialists(lib),
        },
    }


def unmapped_specialists(lib: IntelligenceLibrary | None = None) -> list[str]:
    """Specialist keys with zero knowledge entries — a coverage gap for the Missing-Knowledge report."""
    deps = specialist_dependencies(lib)
    return sorted(k for k, v in deps.items() if not v)


def orphan_entries(lib: IntelligenceLibrary | None = None) -> list[str]:
    """Entries no specialist consumes — dead knowledge to prune or wire up."""
    lib = lib or default_library()
    return sorted(e.id for e in lib.active() if not e.specialists)


def duplicate_entries(lib: IntelligenceLibrary | None = None) -> list[list[str]]:
    """Groups of entries sharing an identical content hash — true duplicate knowledge (should be
    empty). Enforces the charter's 'no duplicate knowledge'."""
    lib = lib or default_library()
    by_hash: dict[str, list[str]] = {}
    for e in lib.all():
        by_hash.setdefault(e.content_hash, []).append(e.id)
    return [sorted(ids) for ids in by_hash.values() if len(ids) > 1]


__all__ = [
    "specialist_dependencies", "dependency_graph", "unmapped_specialists",
    "orphan_entries", "duplicate_entries",
]
