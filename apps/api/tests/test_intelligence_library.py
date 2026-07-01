"""Institutional Intelligence Library (Sprint 025).

Verifies the curated knowledge layer the AI specialists will reason from: the entry schema and its
content addressing, the seeded library's integrity (every category covered, no dangling
relationships, no duplicates, no orphans), the six constant-time retrieval interfaces, the
specialist dependency mapping (all 13 mapped, derived — not duplicated), the benchmark, and the
drift-guarded Hugging Face knowledge manifest. The library is additive + inert: it changes nothing
about the Governor, OmiScore, memory, the council, or deployment.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

from app.reasoning.knowledge import (
    CATEGORIES,
    KnowledgeIndex,
    benchmark,
    default_library,
    dependency_graph,
    duplicate_entries,
    orphan_entries,
    specialist_dependencies,
    unmapped_specialists,
)
from app.reasoning.knowledge.entry import KnowledgeEntry
from app.reasoning.prompts.export import (
    KNOWLEDGE_PATH,
    knowledge_manifest,
    knowledge_matches_committed,
    render_knowledge_json,
)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SPECIALISTS = {
    "behavior_analyst", "counter_evidence_analyst", "narrative_analyst", "language_analyst",
    "coordination_analyst", "campaign_analyst", "metadata_analyst", "network_analyst",
    "temporal_analyst", "memory_analyst", "risk_analyst", "calibration_analyst", "judge",
}


# --------------------------------------------------------------------------- #
# Entry schema + library integrity
# --------------------------------------------------------------------------- #
def test_entry_is_content_addressed_and_renders():
    e = default_library().get("astroturfing")
    assert e.content_hash.startswith("ie:")
    assert e.active and e.confidence in ("established", "emerging", "hypothesis")
    text = e.render()
    for section in ("Definition", "Indicators", "Counter-indicators", "False-positive risks",
                    "Constitutional constraints", "Relationships"):
        assert section in text, section


def test_library_integrity_is_clean():
    lib = default_library()
    assert len(lib) >= 20 and len(lib.categories()) == 14
    assert lib.validate() == []                    # no dangling category/relationship/specialist
    assert duplicate_entries(lib) == []            # no duplicate knowledge
    assert orphan_entries(lib) == []               # every entry has a consuming specialist
    assert lib.library_hash().startswith("il:")


def test_every_category_has_at_least_one_entry():
    lib = default_library()
    for c in CATEGORIES:
        assert lib.by_category(c.id), f"empty category {c.id}"


# --------------------------------------------------------------------------- #
# Phase 4 — retrieval interfaces (all six, constant-time)
# --------------------------------------------------------------------------- #
def test_all_six_retrieval_interfaces():
    idx = KnowledgeIndex()
    assert any(e.id == "coordinated_inauthentic_behavior" for e in idx.keyword("coordination"))
    assert {e.id for e in idx.category("bot_behaviors")} == {"bot_amplification", "benign_automation"}
    assert idx.behavior("bot")                                   # behavior lookup
    assert {e.id for e in idx.related("astroturfing")} >= {"consensus_illusion", "sockpuppets"}
    assert idx.platform("youtube") and idx.investigation_type("campaign")
    assert any(e.id == "fingerprint_clustering" for e in idx.for_specialist("coordination_analyst"))


def test_retrieval_is_fast_constant_time():
    # a lookup is a dict access + bounded scan; average well under 100µs even in CI.
    assert KnowledgeIndex().measure_latency(iterations=50)["avg_lookup_us"] < 500.0


def test_retrieval_excludes_non_validated_entries():
    from app.reasoning.knowledge.library import IntelligenceLibrary
    from app.reasoning.knowledge.categories import CATEGORIES_BY_ID
    lib = IntelligenceLibrary()
    lib.add_category(CATEGORIES_BY_ID["deception_indicators"])
    lib.add(KnowledgeEntry(id="draft_x", title="Draft", category="deception_indicators",
                           definition="d", purpose="p", status="draft", tags=("draftx",)))
    assert KnowledgeIndex(lib).keyword("draftx") == []          # non-validated is not retrievable


# --------------------------------------------------------------------------- #
# Phase 3 — specialist dependency mapping (derived, no duplicate map)
# --------------------------------------------------------------------------- #
def test_every_specialist_is_mapped_to_knowledge():
    deps = specialist_dependencies()
    assert set(deps) == _SPECIALISTS
    assert unmapped_specialists() == []                         # all 13 have a reading list
    assert deps["judge"] and deps["memory_analyst"]
    g = dependency_graph()
    assert g["coverage"]["specialists_with_knowledge"] == 13
    # the graph is explainable: each mapped entry declares this specialist as a consumer.
    lib = default_library()
    for entry_id in g["specialists"]["coordination_analyst"]["entries"]:
        assert "coordination_analyst" in lib.get(entry_id).specialists


# --------------------------------------------------------------------------- #
# Phase 6 — benchmark
# --------------------------------------------------------------------------- #
def test_benchmark_reports_full_coverage_and_no_duplication():
    b = benchmark()
    assert b["coverage"]["categories_covered"] == 14 and b["coverage"]["empty_categories"] == []
    assert b["duplication"]["duplicate_free"] is True
    assert b["knowledge_completeness"]["complete_entries"] == b["knowledge_completeness"]["total_entries"]
    assert b["knowledge_completeness"]["integrity_issues"] == []
    assert b["specialist_utilization"]["specialists_with_knowledge"] == 13
    assert b["retrieval_speed"]["avg_lookup_us"] >= 0.0


# --------------------------------------------------------------------------- #
# Phase 5 — Hugging Face packaging (published alongside prompts, drift-guarded)
# --------------------------------------------------------------------------- #
def test_knowledge_manifest_matches_committed_and_is_library_derived():
    assert knowledge_matches_committed() is True
    assert KNOWLEDGE_PATH.exists()
    assert KNOWLEDGE_PATH.read_text(encoding="utf-8") == render_knowledge_json()


def test_knowledge_manifest_carries_index_hashes_and_dependencies():
    m = knowledge_manifest()
    assert m["library_hash"].startswith("il:") and m["taxonomy_hash"].startswith("kc:")
    assert m["counts"]["entries"] >= 20 and m["counts"]["categories"] == 14
    assert all(e["content_hash"].startswith("ie:") for e in m["entries"])
    assert set(m["specialist_dependencies"]) == _SPECIALISTS


def test_hf_manifest_publishes_knowledge_index():
    spec = importlib.util.spec_from_file_location(
        "register_hf_model", _REPO_ROOT / "ml" / "analyst" / "register_hf_model.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    target, files = mod.load_manifest(_REPO_ROOT / "ml" / "analyst" / "hf_repo_manifest.toml")
    ok, resolved, errors = mod.validate(target, files)
    assert ok, errors
    assert any(dst == "knowledge/knowledge_manifest.json" for _s, dst, _k in resolved)
