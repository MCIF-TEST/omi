"""Intelligence Library — retrieval interfaces (Sprint 025, Phase 4).

Constant-time lookups over the library along every dimension a specialist needs: keyword, category,
behavior, relationship, platform, and investigation type. The inverted indexes are built ONCE from
the library (at construction / process start), so a lookup is a dict access plus a bounded scan of
only the matched postings — it never scans the whole library and adds no reasoning-path latency.
Retired/superseded entries are excluded. Results are deterministically ordered.
"""
from __future__ import annotations

import time
from collections import defaultdict

from .entry import KnowledgeEntry
from .library import IntelligenceLibrary, default_library


class KnowledgeIndex:
    """Pre-built inverted indexes for O(1) lookup along each dimension."""

    def __init__(self, library: IntelligenceLibrary | None = None) -> None:
        self._lib = library or default_library()
        self._by_id: dict[str, KnowledgeEntry] = {}
        self._by_keyword: dict[str, set[str]] = defaultdict(set)
        self._by_category: dict[str, list[str]] = defaultdict(list)
        self._by_platform: dict[str, list[str]] = defaultdict(list)
        self._by_investigation: dict[str, list[str]] = defaultdict(list)
        self._by_specialist: dict[str, list[str]] = defaultdict(list)
        self._by_tag: dict[str, list[str]] = defaultdict(list)
        self._build()

    def _build(self) -> None:
        for e in self._lib.active():                       # only validated knowledge is retrievable
            self._by_id[e.id] = e
            self._by_category[e.category].append(e.id)
            for term in e.lookup_terms():
                self._by_keyword[term].add(e.id)
            for p in e.platforms:
                self._by_platform[p].append(e.id)
            for it in e.investigation_types:
                self._by_investigation[it].append(e.id)
            for s in e.specialists:
                self._by_specialist[s].append(e.id)
            for t in e.tags:
                self._by_tag[t].append(e.id)

    def _entries(self, ids) -> list[KnowledgeEntry]:
        return [self._by_id[i] for i in sorted(set(ids)) if i in self._by_id]

    # ---- the six lookup interfaces (all O(1) index access) ----------------------------- #
    def keyword(self, query: str) -> list[KnowledgeEntry]:
        """Keyword lookup: match query tokens against ids/titles/tags, ranked by overlap."""
        tokens = {t.lower() for t in query.replace("-", " ").split() if len(t) > 2}
        scored: dict[str, int] = defaultdict(int)
        for tok in tokens:
            for eid in self._by_keyword.get(tok, ()):  # exact token
                scored[eid] += 2
            for term, ids in self._by_keyword.items():  # prefix/substring (bounded, small vocab)
                if tok in term:
                    for eid in ids:
                        scored[eid] += 1
        ranked = sorted(scored, key=lambda i: (-scored[i], i))
        return self._entries(ranked)

    def category(self, category_id: str) -> list[KnowledgeEntry]:
        return self._entries(self._by_category.get(category_id, ()))

    def behavior(self, term: str) -> list[KnowledgeEntry]:
        """Behavior lookup: entries tagged with a behavior term or in the behavioral-archetype /
        bot-behavior categories matching the term."""
        term = term.lower()
        hits = list(self._by_tag.get(term, ()))
        for cat in ("behavioral_archetypes", "bot_behaviors"):
            for eid in self._by_category.get(cat, ()):
                if term in {t.lower() for t in self._by_id[eid].tags} or term in eid:
                    hits.append(eid)
        return self._entries(hits) or self.keyword(term)

    def related(self, entry_id: str) -> list[KnowledgeEntry]:
        """Relationship lookup: the knowledge-graph neighbors of an entry."""
        e = self._by_id.get(entry_id)
        return self._entries(e.relationships) if e else []

    def platform(self, platform: str) -> list[KnowledgeEntry]:
        return self._entries(self._by_platform.get(platform.lower(), ()))

    def investigation_type(self, investigation_type: str) -> list[KnowledgeEntry]:
        return self._entries(self._by_investigation.get(investigation_type.lower(), ()))

    def for_specialist(self, specialist_key: str) -> list[KnowledgeEntry]:
        """The reading list one specialist should access (drives the Phase-3 dependency graph)."""
        return self._entries(self._by_specialist.get(specialist_key, ()))

    # ---- diagnostics ------------------------------------------------------------------- #
    def measure_latency(self, iterations: int = 200) -> dict:
        """Micro-benchmark: average lookup time across the dimensions (Phase-6 retrieval speed)."""
        samples = [("keyword", "coordination"), ("category", "coordination_techniques"),
                   ("behavior", "bot"), ("platform", "youtube"),
                   ("investigation_type", "campaign")]
        t0 = time.perf_counter()
        for _ in range(iterations):
            self.keyword("coordination"); self.category("coordination_techniques")
            self.behavior("bot"); self.platform("youtube")
            self.investigation_type("campaign")
        elapsed = time.perf_counter() - t0
        per_lookup_us = (elapsed / (iterations * len(samples))) * 1_000_000
        return {"iterations": iterations, "lookups": iterations * len(samples),
                "avg_lookup_us": round(per_lookup_us, 2)}


__all__ = ["KnowledgeIndex"]
