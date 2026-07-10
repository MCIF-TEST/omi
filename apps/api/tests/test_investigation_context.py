"""Phase P1.0 — the Investigation Context Builder (evidence assembly only).

Proves the builder is the ONE typed evidence-assembly layer and that it obeys every P1.0 rule:
assembles typed sections from the payload, REUSES existing collectors (the Evidence Bundle Binder,
``compute_omiscore``, memory ``retrieve``) instead of re-extracting, pseudonymizes identifiers (no
raw PII), is deterministic + content-addressed, constructs NO prompt and invokes NO model, and
degrades gracefully (empty payload / honest gaps) without raising.
"""
from __future__ import annotations

import json

import pytest

from app.evidence.binder import Binder
from app.reasoning.context import (
    INVESTIGATION_CONTEXT_VERSION,
    SECTION_ORDER,
    InvestigationContext,
    build_investigation_context,
)
from app.reasoning.context.investigation import build_investigation_context as _direct


def _payload() -> dict:
    """A realistic ``Investigation.payload_json`` (ComprehensiveScanResult shape)."""
    return {
        "overall_probability": 0.72, "overall_tier": "elevated", "confidence": 0.55,
        "convergence_score": 0.3, "summary": "Elevated suspicion.", "quota_used": 12,
        "inputs_provided": ["video"], "video_id": "vid_123",
        "contributions": [
            {"name": "temporal", "impact": 0.4, "direction": "raises", "headline": "bursty"},
            {"name": "community", "impact": 0.1, "direction": "lowers", "headline": "real footprint"},
        ],
        "weak_signals": ["few posts"],
        "cross_links": [{
            "kind": "fellow_traveler", "severity": "elevated", "summary": "co-appeared",
            "evidence": ["5 shared videos"], "related_entities": ["chanA", "chanB"],
        }],
        "video": {
            "video_id": "vid_123", "coordination_score": 0.66, "coordination_tier": "elevated",
            "commenter_count": 2, "fresh_count": 2, "cached_count": 0, "quota_used": 12,
            "tier_distribution": {"high": 1, "elevated": 1}, "high_suspicion_handles": ["@a"],
            "thread_scan": {"overall_probability": 0.5, "tier": "moderate"},
            "clusters": [
                {"method": "co_engagement", "members": ["chanA", "chanB", "chanC"], "score": 0.7,
                 "evidence": ["tight co-engagement"], "metadata": {"density": 0.8}},
                {"method": "style_match", "members": ["chanA", "chanB"], "score": 0.3, "evidence": []},
            ],
            "commenters": [
                {"platform": "youtube", "external_id": "chanA", "handle": "@a",
                 "overall_probability": 0.8, "coordination_adjusted_probability": 0.85, "tier": "high",
                 "confidence": 0.6, "from_cache": False, "matched_prior_neighbors": 2,
                 "intent_label": "astroturf", "reasons": ["bursty posting"], "weak_signals": [],
                 "coordination_evidence": ["in co_engagement ring"], "score_adjustments": ["convergence bonus"],
                 "recent_activity": [{"text": "great video!!", "created_at": "2026-01-01T00:00:00Z",
                                      "parent_id": "vid_9"}],
                 "signals": [
                     {"name": "temporal", "probability": 0.8, "confidence": 0.7,
                      "evidence": ["low variance"], "sub_signals": {}},
                     {"name": "engagement", "probability": 0.6, "confidence": 0.5},
                 ],
                 "contributions": [{"name": "temporal", "impact": 0.4, "direction": "raises",
                                    "headline": "bursty"}]},
                {"platform": "youtube", "external_id": "chanB", "handle": "@b",
                 "overall_probability": 0.55, "tier": "elevated", "confidence": 0.4, "from_cache": True,
                 "matched_prior_neighbors": 0, "reasons": [],
                 "signals": [{"name": "temporal", "probability": 0.5, "confidence": 0.4, "sub_signals": {}}],
                 "contributions": []},
            ],
        },
        "focus_account": {"external_id": "focusX", "handle": "@focus", "overall_probability": 0.6,
                          "tier": "elevated", "confidence": 0.5, "intent_label": "coordinator",
                          "reasons": ["runs the ring"], "history_size": 40},
    }


def _build(payload=None, **kw):
    kw.setdefault("ref", "inv-slug-1")
    kw.setdefault("platform", "youtube")
    kw.setdefault("slug", "inv-slug-1")
    kw.setdefault("kind", "video")
    return build_investigation_context(payload if payload is not None else _payload(), **kw)


def test_returns_one_typed_object_with_all_sections():
    ctx = _build()
    assert isinstance(ctx, InvestigationContext)
    assert ctx.context_version == INVESTIGATION_CONTEXT_VERSION
    d = ctx.to_dict()
    # Every canonical section is present as a typed dict — the shape is stable for the Prompt Builder.
    for name in SECTION_ORDER:
        assert name in d, f"missing section {name}"
        assert isinstance(d[name], dict) and "present" in d[name]
    # The canonical tree the contract named.
    for name in ("investigation", "post", "author", "comments", "accounts", "coordination",
                 "narratives", "campaigns", "graph", "behavioral", "omiscore", "memory", "metadata"):
        assert name in d


def test_ruling3_heuristic_interpretations_are_not_projected_as_evidence():
    """Ruling 3 (frozen architecture): intent_label / suspected_intent / reasons are heuristic
    INTERPRETATIONS, not observations. Even though the payload carries them (the engine still
    measures), the Repository's evidence projection must NOT expose them — on any account or the
    focus author. Observations (weak_signals / coordination_evidence / signals) remain."""
    ctx = _build()  # the payload has intent_label/reasons on chanA and the focus author
    for acct in ctx.accounts.accounts:
        d = acct.to_dict()
        assert "intent_label" not in d and "suspected_intent" not in d and "reasons" not in d
        assert "signals" in d and "weak_signals" in d          # observations preserved
    author = ctx.author.to_dict()
    assert "intent_label" not in author and "suspected_intent" not in author and "reasons" not in author


def test_projects_accounts_coordination_campaigns_crosslinks():
    d = _build().to_dict()
    assert d["accounts"]["count"] == 2
    assert d["coordination"]["cluster_count"] == 2
    assert d["coordination"]["coordination_score"] == pytest.approx(0.66)
    # Campaign candidates = corroboration-gated clusters (score >= 0.5): only the co_engagement one.
    assert d["campaigns"]["count"] == 1
    assert d["campaigns"]["candidates"][0]["method"] == "co_engagement"
    assert "co_engagement" in d["coordination"]["discriminative_methods"]
    assert d["cross_platform"]["count"] == 1
    # Timing / engagement surfaced from the named detector signals (evidence, not recomputation).
    assert d["timing"]["accounts_with_temporal_signal"] == 2
    assert d["engagement"]["co_engagement_clusters"] == 1


def test_reuses_the_evidence_bundle_binder_not_a_parallel_extractor():
    """Graph + behavioral come from the canonical Binder — proven by the bundle_id matching a
    bundle built directly. This is REUSE (same content address), not duplicate extraction."""
    ctx = _build()
    bundle = Binder().bind(_payload(), grain="comment_section", subject_ref="inv-slug-1",
                           platform="youtube", enrich=True)
    assert ctx.metadata.bundle_id == bundle.bundle_id()
    assert ctx.graph.present and ctx.graph.relationship_count == len(bundle.relationships)
    assert ctx.behavioral.present and len(ctx.behavioral.items) > 0


def test_omiscore_reuses_compute_omiscore_over_payload_signals():
    """OmiScore is populated for real by reusing the deterministic ``compute_omiscore`` collector
    over the per-account signals already in the payload — no new detection, no session/store."""
    d = _build().to_dict()
    assert d["omiscore"]["present"] and d["omiscore"]["count"] == 2
    s0 = d["omiscore"]["scores"][0]
    assert 0.0 <= s0["omi_score"] <= 100.0
    assert s0["risk_level"] in ("low", "medium", "high")
    assert s0["ref"].startswith("sub_")


def test_pseudonymizes_identifiers_no_raw_pii():
    """No raw handle / external id appears anywhere in the assembled object — identifiers are
    pseudonymized with the same ``sub_`` scheme the Evidence Bundle uses."""
    dump = json.dumps(_build().to_dict())
    for raw in ("@a", "@b", "@focus", "chanA", "chanB", "chanC", "focusX"):
        assert raw not in dump, f"raw identifier {raw!r} leaked into the context"
    d = json.loads(dump)
    assert d["accounts"]["accounts"][0]["ref"].startswith("sub_")
    assert d["author"]["ref"].startswith("sub_")
    # Comment BODIES are carried verbatim (the evidence the future stage needs); identifiers aren't.
    assert any("great video" in s["text"] for s in d["comments"]["samples"])


def test_author_from_focus_account_else_absent():
    assert _build().author.present is True
    p = _payload()
    p.pop("focus_account")
    ctx = _build(p)
    assert ctx.author.present is False
    assert ctx.author.ref is None


def test_deterministic_and_content_addressed():
    a = _build().context_id
    b = _build().context_id
    assert a == b and a.startswith("ictx:")
    # A change in the evidence changes the id.
    p = _payload()
    p["overall_probability"] = 0.11
    assert _build(p).context_id != a


def test_honest_gaps_are_typed_but_absent():
    """Narratives, OmiScore-from-store, and previous investigations have no ready per-investigation
    collector yet — they are emitted empty-but-typed (P1.2 completeness), never fabricated."""
    ctx = _build()
    assert ctx.narratives.present is False and ctx.narratives.count == 0
    assert ctx.previous_investigations.present is False


def test_constructs_no_prompt_and_no_model_surface():
    """This layer ONLY assembles evidence: it exposes no prompt-rendering and no model surface."""
    ctx = _build()
    assert not hasattr(ctx, "to_prompt_text")
    assert not hasattr(ctx, "render")
    # No section value is a rendered prompt string; the object is pure structured data.
    d = ctx.to_dict()
    assert isinstance(d, dict) and set(SECTION_ORDER).issubset(d.keys())


def test_empty_and_malformed_payloads_are_safe():
    for bad in ({}, {"video": None}, {"video": {"commenters": "nope"}}, {"contributions": 5}):
        ctx = _direct(bad, ref="x", platform="unknown")
        assert isinstance(ctx, InvestigationContext)
        d = ctx.to_dict()
        assert all(name in d for name in SECTION_ORDER)
        # Investigation + metadata are always present; evidence sections degrade to empty, not error.
        assert d["metadata"]["present"] is True


def test_memory_section_is_typed_and_safe_with_default_store():
    """The Memory section reuses the production ``retrieve`` collector; with memory persistence off
    it yields an empty-but-typed section rather than raising."""
    ctx = _build()
    d = ctx.to_dict()
    # Sections use immutable tuples (deterministic); they JSON-serialize as arrays.
    assert "priors" in d["memory"] and isinstance(d["memory"]["priors"], (list, tuple))
    assert d["memory"]["count"] == len(d["memory"]["priors"])
    assert isinstance(json.loads(json.dumps(d))["memory"]["priors"], list)
