"""Context Builder tests (Sprint 009).

Covers deterministic, versioned context generation; evidence + citation preservation (no
synthesized statement loses traceability); budget selection + compression correctness; and the
quality metrics — all model-independent and operating only on the Evidence Bundle + Memory.
"""
from __future__ import annotations

from datetime import datetime, timezone

from app.evidence import Binder
from app.memory.graph import MemoryStore
from app.reasoning.context import BUDGETS, build_context, raw_context_text

NOW = datetime(2026, 6, 25, tzinfo=timezone.utc)


def _payload() -> dict:
    return {
        "overall_probability": 0.72, "overall_tier": "elevated", "confidence": 0.6,
        "weak_signals": ["only 8 posts — temporal abstained"], "single_axis_capped": False,
        "contributions": [
            {"name": "temporal", "impact": 0.5, "direction": "raises"},        # ev:0002
            {"name": "community", "impact": 0.2, "direction": "lowers"},       # ev:0003
            {"name": "ai_writing", "impact": 0.1, "direction": "neutral", "supplemental": True},  # ev:0004
        ],
        "video": {"clusters": [{"method": "co_engagement", "members": ["@a", "@b", "@c"]}]},  # ev:0005
    }


def _bundle():
    return Binder().bind(_payload(), grain="comment_section", subject_ref="inv1", platform="youtube")


def _store_with_control() -> MemoryStore:
    s = MemoryStore()
    s.ingest(candidate={"type": "LegitimateCoordinationControl", "signature": ["co_engagement"],
                        "label": "regional newsroom", "is_control": True},
             investigation="h1", stance="supports", evidence_refs=["d"], independence_key="a", at=NOW.isoformat())
    return s


def _all_statements(ctx):
    return [st for s in ctx.sections for st in s.statements]


# --- determinism + versioning ----------------------------------------------- #
def test_build_context_is_deterministic():
    a, b = build_context(_bundle(), budget="standard"), build_context(_bundle(), budget="standard")
    assert a.context_hash == b.context_hash and a.to_dict() == b.to_dict()
    assert a.context_version == "ctx-v1" and a.context_hash.startswith("ctx:")


def test_context_hash_changes_with_budget():
    assert build_context(_bundle(), budget="compact").context_hash != build_context(_bundle(), budget="comprehensive").context_hash


def test_unknown_budget_falls_back_to_standard():
    assert build_context(_bundle(), budget="bogus").to_dict() == build_context(_bundle(), budget="standard").to_dict()


# --- evidence + citation preservation --------------------------------------- #
def test_every_statement_retains_a_reference():
    ctx = build_context(_bundle(), store=_store_with_control(), budget="comprehensive")
    assert all(st.evidence_refs for st in _all_statements(ctx))     # no statement loses traceability
    assert ctx.metrics["citation_retention"] == 1.0


def test_behavioral_evidence_is_preserved_and_supplemental_excluded():
    ctx = build_context(_bundle(), budget="standard")
    beh = next(s for s in ctx.sections if s.name == "behavioral_summary")
    refs = {r for st in beh.statements for r in st.evidence_refs}
    assert "ev:0002" in refs and "ev:0003" in refs                 # temporal + community preserved
    assert "ev:0004" not in refs                                   # supplemental ai_writing excluded


def test_evidence_coverage_by_budget():
    # standard/comprehensive cover all informative evidence; compact (capped, fewer sections) does not.
    assert build_context(_bundle(), budget="standard").metrics["evidence_coverage"] == 1.0
    assert build_context(_bundle(), budget="comprehensive").metrics["evidence_coverage"] == 1.0
    assert build_context(_bundle(), budget="compact").metrics["evidence_coverage"] == round(2 / 3, 4)


def test_prior_context_populates_from_memory_with_attribution():
    ctx = build_context(_bundle(), store=_store_with_control(), budget="standard")
    prior = next(s for s in ctx.sections if s.name == "prior_context")
    assert prior.statements
    refs = {r for st in prior.statements for r in st.evidence_refs}
    assert any(r.startswith("ko:") for r in refs)                  # memory provenance retained
    assert any(r.startswith("ev:") for r in refs)                  # + resolvable bundle evidence


# --- budgets + compression -------------------------------------------------- #
def test_budget_selection_is_nested_and_capped():
    compact = build_context(_bundle(), budget="compact")
    standard = build_context(_bundle(), budget="standard")
    comprehensive = build_context(_bundle(), budget="comprehensive")
    cs = {s.name for s in compact.sections}
    ss = {s.name for s in standard.sections}
    assert cs < ss < {s.name for s in comprehensive.sections}      # strictly nested section sets
    assert all(len(s.statements) <= BUDGETS["compact"]["per_section"] for s in compact.sections)


def test_compression_correctness():
    compact = build_context(_bundle(), budget="compact").metrics
    comprehensive = build_context(_bundle(), budget="comprehensive").metrics
    assert compact["context_tokens"] < comprehensive["context_tokens"]   # compact is smaller
    assert 0.0 < compact["token_utilization"] <= 1.5
    assert compact["compression_ratio"] == round(compact["context_tokens"] / compact["raw_tokens"], 4)


def test_completeness_reflects_populated_sections():
    # without memory or narrative/metadata facets, comprehensive has empty sections -> < 1.0.
    full = build_context(_bundle(), store=_store_with_control(), budget="comprehensive")
    assert 0.0 < full.metrics["context_completeness"] <= 1.0


# --- raw baseline unchanged (regression safety) ----------------------------- #
def test_raw_context_text_is_unchanged():
    raw = raw_context_text(_bundle(), _store_with_control(), NOW)
    assert "BEHAVIORAL EVIDENCE" in raw and "never proof" in raw   # the pre-Sprint-009 baseline
    assert "ev:0002" in raw and "regional newsroom" in raw         # behavioral ids + prior context present
