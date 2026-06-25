"""Unit tests for the deterministic Evidence Bundle + Binder (Sprint 002).

Verifies: content-addressing determinism, version binding, projection correctness,
pseudonymity, the epistemics layer, and citation resolution (native + legacy paths).
The engine is untouched — these test a standalone, additive foundation.
"""
from __future__ import annotations

from app.evidence import Binder, EvidenceBundle, canonical_json, digest


def _payload() -> dict:
    return {
        "overall_probability": 0.72,
        "overall_tier": "elevated",
        "confidence": 0.6,
        "summary": "Elevated suspicion across multiple signals.",
        "weak_signals": ["only 8 posts — temporal abstained"],
        "single_axis_capped": False,
        "contributions": [
            {"name": "temporal", "impact": 0.5, "logit_delta": 0.8, "direction": "raises"},
            {"name": "community", "impact": 0.2, "logit_delta": -0.3, "direction": "lowers"},
            {"name": "ai_writing", "impact": 0.1, "logit_delta": 0.0,
             "direction": "neutral", "supplemental": True},
        ],
        "coordination": {
            "clusters": [{"method": "co_engagement", "members": ["@a", "@b", "@c"], "score": 0.66}],
            "single_axis_capped": False,
        },
        "video": {"commenters": [{"handle": "@a", "tier": "high"}]},
    }


def _bind(p: dict | None = None) -> EvidenceBundle:
    return Binder().bind(p or _payload(), grain="comment_section",
                         subject_ref="inv_xyz", platform="youtube", engine_version="e1")


# --- content addressing / determinism --------------------------------------- #
def test_bundle_id_is_deterministic():
    a, b = _bind(), _bind()
    assert a.bundle_id() == b.bundle_id()
    assert a.bundle_id().startswith("b:")


def test_bundle_id_changes_with_evidence():
    base = _bind()
    altered = dict(_payload())
    altered["overall_probability"] = 0.99
    assert _bind(altered).bundle_id() != base.bundle_id()


def test_canonical_json_and_digest_stable():
    obj = {"b": 1, "a": [3, 2, 1]}
    assert canonical_json(obj) == '{"a":[3,2,1],"b":1}'
    assert digest(obj) == digest({"a": [3, 2, 1], "b": 1})  # key order irrelevant


# --- projection correctness ------------------------------------------------- #
def test_headline_is_the_echo_source():
    b = _bind()
    hl = b.headline()
    assert hl["overall_probability"] == 0.72 and hl["tier"] == "elevated"


def test_contributions_and_directions_projected():
    b = _bind()
    contribs = [it for it in b.evidence.values() if it.kind == "contribution"]
    assert {it.originating_detector for it in contribs} == {"temporal", "community", "ai_writing"}
    assert any(it.direction == "raises" for it in contribs)
    assert any(it.direction == "lowers" for it in contribs)
    # supplemental is preserved and flagged
    assert any(it.supplemental for it in contribs if it.originating_detector == "ai_writing")


def test_coordination_and_member_edges():
    b = _bind()
    methods = [it for it in b.evidence.values() if it.kind == "coordination_method"]
    assert methods and methods[0].discriminative is True  # co_engagement is discriminative
    member_edges = [r for r in b.relationships if r.type == "member_of"]
    assert len(member_edges) == 3  # @a @b @c


def test_pseudonymity_no_raw_handles():
    blob = canonical_json(_bind().to_dict())
    assert "@a" not in blob and "@b" not in blob and "inv_xyz" not in blob
    assert "sub_" in blob


# --- epistemics ------------------------------------------------------------- #
def test_epistemics_contradiction_and_missing():
    ep = _bind().epistemics
    assert ep["contradictions"] and ep["contradictions"][0]["kind"] == "raises_vs_lowers"
    assert ep["missing_evidence"] and ep["missing_evidence"][0]["why"] == "weak_signal"


def test_epistemics_unknown_on_gated_coordination():
    p = dict(_payload())
    p["coordination"] = {"clusters": [{"method": "style_match", "members": ["@x", "@y"]}]}
    ep = _bind(p).epistemics
    assert any(u["basis"] == "non_discriminative_coordination" for u in ep["unknowns"])


# --- citation resolution ---------------------------------------------------- #
def test_resolution_native_and_legacy():
    b = _bind()
    # native ev: id
    some_id = next(iter(b.evidence))
    assert b.resolve(some_id) is True
    assert b.resolve(some_id + "#/value/impact") is True
    # legacy dotted path used by the existing analyst
    assert b.resolve("contributions.temporal") is True
    assert b.resolve("signals.temporal") is True  # resolves by originating_detector
    # unresolvable
    assert b.resolve("ev:9999") is False
    assert b.resolve("contributions.nonexistent_detector") is False


def test_citation_index_covers_all_evidence():
    b = _bind()
    idx = b.citation_index()
    assert set(idx) == set(b.evidence)
    assert all("digest" in v for v in idx.values())
