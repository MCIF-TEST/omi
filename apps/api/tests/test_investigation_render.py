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
    """AI-first: the account row is RAW metadata — profile counts, creation time, post count, the
    account's own raw posts, and descriptive statistics over its own post timestamps. NO engine
    probability / tier / detector score reaches the model.

    The timing columns are the one place that distinction needs stating, because they are computed.
    Computed is not the same as judged: they are arithmetic over timestamps already in the bundle,
    carrying no threshold and no opinion, in exactly the way `account_created_at` is a fact the model
    turns into an age. They exist because the protocol asked the model to do that arithmetic itself,
    three times over, and across four live investigations it never once did, while every rhythm claim
    it wrote without a figure ran exculpatory.
    """
    rv = render_investigation_evidence(_package(_small_payload()))
    acct = rv.sections["account_analysis"]
    cols = acct["columns"]
    assert cols == ["account", "follower_count", "following_count", "account_created_at",
                    "verified", "bio", "post_count",
                    "post_gap_median_min", "post_gap_stdev_min", "longest_daily_quiet_min",
                    "distinct_post_hours", "recent_posts"]
    # The engine's own judgement still reaches nothing. This is the guard that matters.
    for banned in ("signals", "contributions", "overall_probability", "tier", "confidence", "omiscore"):
        assert banned not in cols
    row = next(r for r in acct["rows"] if r[0] == "A1")
    assert row[cols.index("follower_count")] == 12
    assert row[cols.index("following_count")] == 900
    # account_created_at — the model derives age itself
    assert row[cols.index("account_created_at")] == "2025-12-20T00:00:00Z"
    # the account's own raw post (text + time)
    assert row[cols.index("recent_posts")][0] == ["great video!!", "2026-01-01T00:00:00Z"]
    # the row carries NO numeric suspicion score
    dump = json.dumps(row)
    assert "0.8" not in dump and "high" not in dump


def test_bio_and_verified_reach_the_model_and_empty_is_not_unknown():
    """An empty bio is a fact about the account and a common bought-account tell; a missing one means
    the platform never told us. Collapsing them would report "unknown" about something we know."""
    from app.reasoning.context.investigation import _account_evidence

    blank = _account_evidence({"handle": "@x", "bio": "", "verified": False}, "x")
    assert blank.bio == "" and blank.verified is False

    unknown = _account_evidence({"handle": "@y"}, "x")
    assert unknown.bio is None and unknown.verified is None


def test_a_full_history_is_not_truncated_to_a_handful_of_posts():
    """The per-account sample ceiling is a safety limit, not the budget. The coverage budgeter (with
    its disclosed omission manifest) decides what renders; a cut above it is silent and undisclosed."""
    from app.reasoning.context.investigation import _account_evidence

    ev = _account_evidence({
        "handle": "@z", "history_size": 40,
        "recent_activity": [{"text": f"post {i}", "created_at": "2026-01-01T00:00:00Z"}
                            for i in range(40)],
    }, "x")
    assert len(ev.recent_posts) == 40, "an account's pulled history must survive to the evidence layer"
    assert ev.post_count == 40


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


# ==================================================================================================
# Measured post timing
# ==================================================================================================
# The mechanical gate's rhythm tell (item b) was unreachable for four live investigations. The
# protocol told the model to work the gaps out of the created_at column three separate times, in the
# strongest wording in the document, and across roughly 400 accounts it produced eleven rhythm claims
# and NOT ONE figure, while `signal_temporal` never exceeded about 35. Every unmeasured claim ran
# exculpatory ("human-like quiet periods"), so an impression nobody computed was holding scores down.
#
# Computing 49 gaps for each of 25 accounts is arithmetic, and arithmetic is what the Evidence
# Compiler is for. These are descriptive statistics with no threshold and no verdict attached.
from datetime import datetime, timedelta, timezone  # noqa: E402

from app.reasoning.context.investigation import _account_evidence  # noqa: E402


def _account_posting_every(minutes_between, n, handle="a"):
    t = datetime(2026, 8, 1, tzinfo=timezone.utc)
    acts = []
    for gap in (minutes_between if isinstance(minutes_between, list) else [minutes_between] * n):
        acts.append({"text": "x", "created_at": t.isoformat().replace("+00:00", "Z")})
        t += timedelta(minutes=gap)
    return _account_evidence({"handle": handle, "recent_activity": acts,
                              "history_size": len(acts)}, "x")


def test_a_scheduler_and_a_person_come_out_different():
    """The whole point. A spread near zero is a machine; a spread in the hundreds is a person."""
    bot = _account_posting_every(62, 20)
    human = _account_posting_every(
        [13, 240, 7, 1100, 45, 9, 600, 22, 180, 31, 900, 5, 77, 410, 18, 66, 240, 12, 333], 0)
    assert bot.post_gap_stdev_min == 0.0
    assert human.post_gap_stdev_min > 100
    # People sleep, so a real timeline has a long daily quiet stretch and covers fewer clock hours.
    assert human.longest_daily_quiet_min > bot.longest_daily_quiet_min
    assert human.distinct_post_hours < bot.distinct_post_hours


def test_too_few_timestamps_yields_nulls_rather_than_a_confident_figure():
    """The protocol's own floor: fewer than about ten gaps cannot show a rhythm. Reporting a median
    computed from four posts would manufacture exactly the unearned confidence this replaces."""
    thin = _account_posting_every(30, 4)
    assert thin.timing_sample_size == 4
    assert thin.post_gap_median_min is None
    assert thin.distinct_post_hours is None


def test_an_account_with_no_posts_is_all_nulls():
    a = _account_evidence({"handle": "a", "recent_activity": []}, "x")
    assert a.timing_sample_size == 0
    assert a.post_gap_stdev_min is None


def test_unparseable_timestamps_are_skipped_not_guessed_at():
    acts = [{"text": "x", "created_at": "not-a-date"} for _ in range(12)]
    a = _account_evidence({"handle": "a", "recent_activity": acts}, "x")
    assert a.timing_sample_size == 0 and a.post_gap_median_min is None
