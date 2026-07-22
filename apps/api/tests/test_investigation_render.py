"""Steps 4-7 — normalize + budget the complete InvestigationPackage into model-facing evidence.

Proves the token-budgeting contract: MAXIMIZE INVESTIGATIVE INFORMATION PER TOKEN WITHOUT USING A
PRECOMPUTED CONCLUSION TO DECIDE THE INVESTIGATION.

* lossless normalization — reversible aliasing (evidence-neutral order), compact tabular rendering that
  preserves every detector value + disagreement, near-duplicate comment grouping (exemplar/count/refs/
  time-range/similarity), lossless relationship collapse;
* evidence-COVERAGE budgeting — per-domain soft budgets with surplus flow; selection by coverage signals
  (graph degree / bridges / cluster coverage / detector disagreement / duplicate-group size / recency),
  NEVER by suspicion; per-cluster coverage guaranteed; every omission disclosed; and — the load-bearing
  proof — a LOW-probability bridge account survives budget pressure that omits HIGH-probability
  non-bridge accounts.
"""
from __future__ import annotations

import json

from app.reasoning.evidence_repository import EvidenceRepository
from app.reasoning.investigation_composer import InvestigationComposer
from app.reasoning.investigation_render import (
    BudgetConfig,
    build_alias_legend,
    group_near_duplicate_comments,
    render_investigation_evidence,
)


def _snapshot(payload):
    return EvidenceRepository().snapshot(payload, ref="inv-1", platform="youtube")


def _package(payload):
    return InvestigationComposer().compose(_snapshot(payload))


def _small_payload() -> dict:
    return {
        "overall_probability": 0.72, "overall_tier": "elevated", "confidence": 0.55,
        "convergence_score": 0.3, "inputs_provided": ["video"], "video_id": "v1",
        "video": {
            "video_id": "v1", "coordination_score": 0.66, "coordination_tier": "elevated",
            "clusters": [{"method": "co_engagement", "members": ["a", "b", "c"], "score": 0.7,
                          "evidence": ["tight"]},
                         {"method": "style_match", "members": ["a", "b"], "score": 0.6}],
            "thread_scan": {"overall_probability": 0.5, "tier": "moderate"},
            "commenters": [
                {"external_id": "a", "handle": "@a", "overall_probability": 0.8, "tier": "high",
                 "confidence": 0.6, "from_cache": False, "matched_prior_neighbors": 2,
                 "follower_count": 12, "following_count": 900, "account_created_at": "2025-12-20T00:00:00Z",
                 "recent_activity": [{"text": "great video!!", "created_at": "2026-01-01T00:00:00Z"}],
                 "signals": [{"name": "temporal", "probability": 0.8, "confidence": 0.7,
                              "evidence": ["low variance"]},
                             {"name": "community", "probability": 0.18, "confidence": 0.5}],
                 "contributions": [{"name": "temporal", "impact": 0.4, "direction": "raises",
                                    "logit_delta": 0.9, "decorrelation_factor": 0.8,
                                    "evidence": "burst 3s"}]},
                {"external_id": "b", "handle": "@b", "overall_probability": 0.55, "tier": "elevated",
                 "confidence": 0.4, "from_cache": True,
                 "follower_count": 3400, "following_count": 210, "account_created_at": "2019-03-01T00:00:00Z",
                 "recent_activity": [{"text": "great video!!", "created_at": "2026-01-01T00:00:30Z"}],
                 "signals": [{"name": "temporal", "probability": 0.5}]},
            ]},
    }


# --------------------------------------------------------------------------- #
def test_aliasing_is_reversible_and_evidence_neutral():
    pkg = _package(_small_payload())
    legend = build_alias_legend(pkg)
    # aliases are A1..An in SORTED-ref order (evidence-neutral — NOT suspicion order)
    assert sorted(legend.account.values()) == ["A1", "A2"]
    assigned = [legend.account[r] for r in sorted(legend.account)]
    assert assigned == ["A1", "A2"], "aliases must be assigned in sorted-ref order, not by suspicion"
    # reversible: every alias resolves back to a real stable ref
    for real, alias in legend.account.items():
        assert legend.resolve(alias) == real
    man = legend.to_manifest()
    assert set(man) == {"accounts", "clusters", "narratives"}
    assert all(a.startswith("A") for a in man["accounts"])


def test_account_rows_carry_raw_metadata_not_computed_scores():
    """AI-first: the account row is RAW metadata — profile counts, creation time, post count, and the
    account's own raw posts. NO engine probability / tier / detector score reaches the model."""
    rv = render_investigation_evidence(_package(_small_payload()))
    acct = rv.sections["account_analysis"]
    assert acct["columns"] == ["account", "follower_count", "following_count", "account_created_at",
                               "post_count", "recent_posts"]
    # no computed columns anywhere in the account section
    for banned in ("signals", "contributions", "overall_probability", "tier", "confidence", "omiscore"):
        assert banned not in acct["columns"]
    row = next(r for r in acct["rows"] if r[0] == "A1")
    assert row[1] == 12 and row[2] == 900                    # follower / following (raw)
    assert row[3] == "2025-12-20T00:00:00Z"                  # account_created_at (model derives age)
    assert row[5][0] == ["great video!!", "2026-01-01T00:00:00Z"]   # the account's own raw post (text+time)
    # the row carries NO numeric suspicion score
    dump = json.dumps(row)
    assert "0.8" not in dump and "high" not in dump


def test_near_duplicate_grouping_is_lossless():
    pkg = _package(_small_payload())
    legend = build_alias_legend(pkg)
    groups = group_near_duplicate_comments(pkg.bundles.comment.comments, legend)
    assert len(groups) == 1                    # the two identical "great video!!" collapse to one group
    g = groups[0]
    assert g.count == 2 and g.is_duplicate_group
    assert set(g.author_refs) == {"A1", "A2"}  # every member ref preserved (aliased)
    assert g.earliest == "2026-01-01T00:00:00Z" and g.latest == "2026-01-01T00:00:30Z"  # time-range
    assert g.similarity == 1.0                 # measured intra-group similarity preserved


def test_small_investigation_is_complete_no_omissions():
    rv = render_investigation_evidence(_package(_small_payload()))
    assert rv.coverage["mode"] == "complete"
    assert rv.sections["account_analysis"]["coverage"]["omitted"] == 0
    assert rv.sections["account_analysis"]["omitted_account_refs"] == []
    assert rv.tokens > 0


def test_no_conclusion_leaks_into_rendered_sections():
    """Rendering carries no verdict / heuristic band — only measured evidence, aliases, and disclosure."""
    p = _small_payload()
    p["video"]["commenters"][0].update({"intent_label": "astroturf", "risk_level": "high",
                                        "reasons": ["bursty"]})
    dump = json.dumps(render_investigation_evidence(_package(p)).sections)
    for forbidden in ("intent_label", "risk_level", "astroturf", "verdict", "bursty", "reasons"):
        assert forbidden not in dump


# --------------------------------------------------------------------------- #
# Large Investigation Mode — the load-bearing coverage-not-suspicion proof
# --------------------------------------------------------------------------- #
def _large_payload() -> dict:
    """40 accounts. TWO are LOW-probability BRIDGES (each in two clusters). The rest are HIGH-probability
    but each sits in only ONE cluster. Coverage-based selection under a tight budget must keep the
    low-probability bridges and may omit high-probability non-bridges — the opposite of suspicion
    ranking."""
    commenters = []
    # two low-probability bridge accounts
    commenters.append({"external_id": "bridge1", "handle": "@bridge1", "overall_probability": 0.05,
                       "tier": "low", "signals": [{"name": "temporal", "probability": 0.05}]})
    commenters.append({"external_id": "bridge2", "handle": "@bridge2", "overall_probability": 0.06,
                       "tier": "low", "signals": [{"name": "temporal", "probability": 0.06}]})
    # 38 high-probability, single-cluster accounts with long RAW post text (to burn the account budget)
    for i in range(38):
        commenters.append({
            "external_id": f"hi{i}", "handle": f"@high_probability_account_{i}",
            "overall_probability": 0.97, "tier": "high", "follower_count": 4, "following_count": 5000,
            "recent_activity": [
                {"text": "a very long raw post that this account actually wrote " * 4,
                 "created_at": "2026-01-01T00:00:00Z"},
                {"text": "another long raw post from the same account to burn budget " * 4,
                 "created_at": "2026-01-01T00:00:05Z"}],
            "signals": [{"name": "temporal", "probability": 0.97, "confidence": 0.9,
                         "evidence": ["a very long detector justification line " * 3]},
                        {"name": "fingerprint", "probability": 0.96, "confidence": 0.9,
                         "evidence": ["another long provenance justification string " * 3]}],
            "contributions": [{"name": "temporal", "impact": 0.5, "direction": "raises",
                               "evidence": "long contribution provenance string " * 3}],
        })
    # cluster A: bridge1 + bridge2 + first 18 high accounts;  cluster B: bridge1 + bridge2 + next 20
    clusterA = ["bridge1", "bridge2"] + [f"hi{i}" for i in range(18)]
    clusterB = ["bridge1", "bridge2"] + [f"hi{i}" for i in range(18, 38)]
    return {
        "overall_probability": 0.9, "overall_tier": "high", "inputs_provided": ["video"],
        "video_id": "v1",
        "video": {"video_id": "v1", "coordination_score": 0.8, "coordination_tier": "high",
                  "clusters": [{"method": "co_engagement", "members": clusterA, "score": 0.8},
                               {"method": "fingerprint_cluster", "members": clusterB, "score": 0.9}],
                  "commenters": commenters},
    }


def test_large_investigation_selects_by_coverage_not_suspicion():
    pkg = _package(_large_payload())
    # a tight account budget forces selection
    cfg = BudgetConfig(total_tokens=2600)
    rv = render_investigation_evidence(pkg, config=cfg)
    acct = rv.sections["account_analysis"]
    cov = acct["coverage"]
    assert cov["mode"] == "large_investigation" and cov["omitted"] > 0, "budget must bind here"

    legend = build_alias_legend(pkg)
    represented = {r[0] for r in acct["rows"]}
    bridge_aliases = {legend.account_alias(pkg_ref) for pkg_ref in legend.account
                      if legend.account[pkg_ref] and _is_bridge_ref(pkg, pkg_ref)}
    # THE PROOF: every low-probability bridge is represented, even though 0.05 << 0.97
    assert bridge_aliases and bridge_aliases <= represented, \
        "low-probability bridge accounts must survive budgeting (coverage, not suspicion)"
    # AND at least one high-probability non-bridge was omitted (suspicion did NOT drive selection)
    assert cov["omitted"] >= 1
    # selection signals are the allowed coverage signals — never a suspicion score
    for banned in ("probability", "tier", "intent", "risk", "suspicion"):
        assert not any(banned in s for s in cov["selection_signals"])


def test_per_cluster_coverage_guarantee_every_cluster_represented():
    pkg = _package(_large_payload())
    rv = render_investigation_evidence(pkg, config=BudgetConfig(total_tokens=2600))
    represented = {r[0] for r in rv.sections["account_analysis"]["rows"]}
    legend = build_alias_legend(pkg)
    # every cluster keeps at least one represented member — no cluster is rendered empty
    for cl in pkg.bundles.coordination.clusters:
        member_aliases = {legend.account_alias(m) for m in cl.member_refs}
        assert member_aliases & represented, f"cluster {cl.method} lost all representation"


def test_omitted_entities_stay_citable_in_index_and_legend():
    pkg = _package(_large_payload())
    rv = render_investigation_evidence(pkg, config=BudgetConfig(total_tokens=2600))
    acct = rv.sections["account_analysis"]
    # omitted accounts are DISCLOSED and remain in the alias legend + evidence index (still citable)
    assert acct["omitted_account_refs"], "omissions must be disclosed"
    legend_aliases = set(rv.legend["accounts"])
    for alias in acct["omitted_account_refs"]:
        assert alias in legend_aliases


def _is_bridge_ref(pkg, ref) -> bool:
    from app.reasoning.investigation_render.budget import compute_account_coverage
    cov = compute_account_coverage(pkg)
    return ref in cov and cov[ref].is_bridge
