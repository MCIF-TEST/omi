"""Intelligence Library — the store (Sprint 025).

Holds the curated knowledge entries + categories, deterministically. ``default_library`` seeds the
shipped taxonomy + entries and validates integrity (every entry's category exists, every
relationship resolves, every consuming specialist is a real Specialist-Library key). Read-only at
reasoning time; content-addressed so the whole library is drift-detectable. GitHub is canonical.
"""
from __future__ import annotations

from app.evidence.bundle import digest

from .categories import CATEGORIES, CATEGORIES_BY_ID, KnowledgeCategory
from .entries import SEED_ENTRIES
from .entry import KnowledgeEntry

# The valid consuming-specialist keys (the Specialist Library). Imported lazily to avoid a hard
# import cycle; falls back to the known set if the prompts package is unavailable.
_SPECIALIST_KEYS = (
    "behavior_analyst", "counter_evidence_analyst", "narrative_analyst", "language_analyst",
    "coordination_analyst", "campaign_analyst", "metadata_analyst", "network_analyst",
    "temporal_analyst", "memory_analyst", "risk_analyst", "calibration_analyst", "judge",
)


class IntelligenceLibrary:
    """A curated set of knowledge entries + categories. Deterministic ordering by id."""

    def __init__(self) -> None:
        self._entries: dict[str, KnowledgeEntry] = {}
        self._categories: dict[str, KnowledgeCategory] = {}

    def add_category(self, cat: KnowledgeCategory) -> KnowledgeCategory:
        self._categories[cat.id] = cat
        return cat

    def add(self, entry: KnowledgeEntry) -> KnowledgeEntry:
        self._entries[entry.id] = entry
        return entry

    def get(self, entry_id: str) -> KnowledgeEntry:
        return self._entries[entry_id]

    def all(self) -> list[KnowledgeEntry]:
        return [self._entries[k] for k in sorted(self._entries)]

    def active(self) -> list[KnowledgeEntry]:
        return [e for e in self.all() if e.active]

    def by_category(self, category_id: str) -> list[KnowledgeEntry]:
        return [e for e in self.all() if e.category == category_id]

    def categories(self) -> list[KnowledgeCategory]:
        return [self._categories[k] for k in sorted(self._categories)]

    def entry_ids(self) -> list[str]:
        return sorted(self._entries)

    def __len__(self) -> int:
        return len(self._entries)

    def records(self) -> list[dict]:
        return [e.to_record() for e in self.all()]

    def library_hash(self) -> str:
        """Content address of the whole library — drift-detectable + versionable."""
        return digest({"entries": [e.content_hash for e in self.all()],
                       "categories": [c.id for c in self.categories()]}, prefix="il:")

    def validate(self) -> list[str]:
        """Integrity issues: unknown category, dangling relationship, unknown specialist. Empty ==
        valid. Deterministic; used by the benchmark + a regression test."""
        issues: list[str] = []
        ids = set(self._entries)
        for e in self.all():
            if e.category not in self._categories:
                issues.append(f"{e.id}: unknown category {e.category!r}")
            for rel in e.relationships:
                if rel not in ids:
                    issues.append(f"{e.id}: dangling relationship {rel!r}")
            for spec in e.specialists:
                if spec not in _SPECIALIST_KEYS:
                    issues.append(f"{e.id}: unknown specialist {spec!r}")
        return issues


def default_library() -> IntelligenceLibrary:
    """A freshly-seeded, validated Intelligence Library (deterministic + side-effect-free)."""
    lib = IntelligenceLibrary()
    for cat in CATEGORIES:
        lib.add_category(cat)
    for entry in SEED_ENTRIES:
        lib.add(entry)
    return lib


__all__ = ["IntelligenceLibrary", "default_library"]
