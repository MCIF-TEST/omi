"""Render the COMPLETE InvestigationPackage into budgeted, normalized, model-facing evidence sections.

This is the normalization + budgeting seam between the complete :class:`InvestigationPackage` (the
lossless evidence) and the Prompt Builder (which turns sections into one request). It applies, in order:

1. **Lossless normalization** — account/cluster aliasing (reversible legend), compact *tabular* rendering
   (column headers declared once, positional rows — killing the repeated-JSON-key overhead that let the
   account domain consume half the prompt), near-duplicate comment grouping, and repeated-relationship
   collapse. Detector disagreement, provenance strings, signed contributions, graph bridges, and the
   sampling disclosure are all preserved.
2. **Evidence-coverage budgeting** — only if normalization still exceeds budget. Per-domain SOFT budgets
   with surplus flowing from small domains to large ones; selection by coverage signals (never
   suspicion); every omission disclosed in an ``evidence_coverage`` manifest.

The output is the seven model-facing sections (one per reasoning section Mistral produces), the reversible
alias legend (for the manifest + Governor citation resolution), and the coverage manifest. It renders the
complete package faithfully — it never decides the investigation.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .alias import AliasLegend, build_alias_legend
from .budget import BudgetConfig, select_accounts, select_comment_groups
from .dedup import collapse_relationships, group_near_duplicate_comments
from .tokens import estimate_json_tokens


@dataclass(frozen=True)
class RenderedEvidence:
    """The budgeted, normalized, model-facing projection of one complete InvestigationPackage."""

    sections: dict[str, Any]        # the seven domain evidence sections (normalized + budgeted)
    legend: dict[str, Any]          # the reversible alias legend (alias -> real ref), for the manifest
    coverage: dict[str, Any]        # the evidence_coverage manifest (per-domain observed/represented/…)
    tokens: int                     # estimated model-facing evidence tokens (this render)


# --------------------------------------------------------------------------- #
# Compact per-domain renderers (positional rows — column headers declared once)
# --------------------------------------------------------------------------- #
# AI-first (raw metadata only): the account row carries the objective, collected facts about the account —
# NO engine probability / tier / detector score. The model reasons its OWN per-account omi_score from these.
_ACCOUNT_COLUMNS = ["account", "follower_count", "following_count", "account_created_at",
                    "verified", "bio", "post_count", "recent_posts"]
_POST_COLUMNS = ["text", "created_at"]


def _account_row(a, alias: AliasLegend) -> list:
    """One compact, positional account row of RAW metadata: the alias, the objective profile counts, the
    account creation time (the model derives age itself), whether the platform verified it, its bio, how
    many posts the account has, and a raw sample of its own posts (text + time). No computed score — the
    AI judges the account from these facts.

    ``verified`` and ``bio`` are here because they are among the cheapest and most discriminating facts
    available: an account with no bio, no verification, a four-figure following count and a three-figure
    follower count reads very differently from one with a written bio and years of history — and none of
    that is recoverable from a probability."""
    return [
        alias.account_alias(a.author_ref),
        a.follower_count,
        a.following_count,
        a.account_created_at,
        getattr(a, "verified", None),
        getattr(a, "bio", None),
        a.post_count,
        [[p.text, p.created_at] for p in getattr(a, "recent_posts", ())],
    ]


def _render_accounts(package, alias, budget_tokens) -> tuple[dict, int, dict, tuple[str, ...]]:
    b = package.bundles
    by_ref = {a.author_ref: a for a in b.account.accounts}
    cost_of = lambda ref: estimate_json_tokens(_account_row(by_ref[ref], alias))  # noqa: E731
    sel = select_accounts(package, cost_of, budget_tokens)
    rows = [_account_row(by_ref[r], alias) for r in sel.represented]
    section = {
        "columns": _ACCOUNT_COLUMNS, "post_columns": _POST_COLUMNS,
        "note": ("RAW per-account metadata — objective facts only, no engine score. Derive account age "
                 "from account_created_at vs the post times; weigh follower/following ratio, history "
                 "depth, and the actual posts. YOU assign each account's omi_score."),
        "rows": rows,
        "memory_priors": [[p.type, p.label, p.confidence, p.influence_class, p.epistemic_status]
                          for p in b.account.memory_priors],
        "memory_prior_columns": ["type", "label", "confidence", "influence_class", "epistemic_status"],
        # omitted accounts are DISCLOSED (aliased) — the model knows they exist and can cite them
        "omitted_account_refs": [alias.account_alias(r) for r in sel.omitted],
        "coverage": sel.manifest,
    }
    return section, estimate_json_tokens(section), sel.manifest, sel.represented


def _render_comments(package, alias, budget_tokens) -> tuple[dict, int, dict]:
    b = package.bundles
    groups = group_near_duplicate_comments(b.comment.comments, alias)
    deduped = sum(g.count for g in groups if g.is_duplicate_group) - sum(
        1 for g in groups if g.is_duplicate_group)  # verbatim copies folded away
    cost_of = lambda i: estimate_json_tokens(  # noqa: E731
        [groups[i].exemplar, groups[i].count, list(groups[i].author_refs),
         groups[i].earliest, groups[i].latest, groups[i].similarity])
    sel = select_comment_groups(groups, cost_of, budget_tokens, deduplicated=deduped)
    kept = {int(i) for i in sel.represented}
    rows = [[g.exemplar, g.count, list(g.author_refs), g.earliest, g.latest, g.similarity,
             g.is_duplicate_group]
            for i, g in enumerate(groups) if i in kept]
    section = {
        "columns": ["exemplar", "count", "author_refs", "earliest", "latest", "similarity",
                    "is_duplicate_group"],
        # RAW comment structure only (exemplar text, how many copies, which accounts, time window).
        # No thread suspicion score — YOU judge whether a group is coordinated or benign.
        "comment_count": b.comment.comment_count,
        "near_duplicate_groups": rows,
        "omitted_group_count": len(sel.omitted),
        "coverage": sel.manifest,
    }
    return section, estimate_json_tokens(section), sel.manifest


def _render_commenter_history(package, alias, represented_refs) -> dict:
    """Track-record rows, restricted to the accounts represented in the account domain (bounded, and
    consistent with the account selection). Compact positional rows."""
    b = package.bundles
    keep = set(represented_refs)
    rows = [[alias.account_alias(c.author_ref), c.activity_sample_count, c.matched_prior_neighbors,
             c.from_cache]
            for c in b.commenter_history.commenters if c.author_ref in keep]
    return {
        "columns": ["account", "activity_sample_count", "matched_prior_neighbors", "from_cache"],
        "rows": rows, "count": len(rows),
    }


def _render_coordination(package, alias) -> dict:
    """Clusters (aliased) + collapsed relationships — the coordination backbone. Represented in full
    (clusters are few and structurally load-bearing); relationships collapsed losslessly."""
    b = package.bundles
    co = b.coordination
    # RAW co-occurrence structure only: how accounts are grouped by shared behavior (which accounts
    # engaged/tagged together, on what) + the raw factual justification. NO coordination score, NO
    # discriminative/single-axis flags — YOU judge whether the co-occurrence is hostile coordination or a
    # benign shared reaction (fan community, same event) and detect coordination from these raw groupings.
    clusters = [[alias.cluster_alias(cl.cluster_ref), cl.method,
                 [alias.account_alias(m) for m in cl.member_refs], cl.members_count, list(cl.evidence)]
                for cl in co.clusters]
    rels = collapse_relationships(co.graph_edges, alias)
    return {
        "note": ("RAW co-occurrence groupings (shared-behavior structure), not a coordination conclusion. "
                 "'method' is HOW the accounts co-occur (co_engagement / co_tag / …); 'members' are the "
                 "accounts; 'evidence' is the raw factual basis. You decide if it is coordination."),
        "cluster_columns": ["group", "method", "members", "members_count", "evidence"],
        "clusters": clusters,
        "relationship_columns": ["type", "from", "to", "count"],
        "relationships": [[r.type, r.from_ref, r.to_ref, r.count] for r in rels],
        "cluster_count": co.cluster_count,
    }


def _render_campaign(package, alias) -> dict:
    b = package.bundles
    return {
        "candidate_cluster_refs": [alias.cluster_alias(r) for r in b.campaign.candidate_cluster_refs],
        "count": b.campaign.count,
    }


def _render_narrative(package, alias) -> dict:
    b = package.bundles
    # RAW narrative structure only: how many messages in the cluster and how many distinct authors carried
    # it. No spread_ratio / inauthenticity score — more distinct authors is broader participation, not
    # itself proof of a synthetic narrative; YOU judge it.
    rows = [[alias.narrative_alias(n.narrative_ref), n.member_count, n.distinct_authors]
            for n in b.narrative.narratives]
    return {
        "columns": ["narrative", "member_count", "distinct_authors"],
        "rows": rows, "count": b.narrative.count,
    }


def _render_summary(package, alias) -> dict:
    """The investigation-level STRUCTURAL context (AI-first: NO echoed engine scores/probabilities/tiers,
    no signed drivers, no digest numbers — the model produces the overall omi_score itself). Kept: the
    factual scope (platform, what was scanned, how many accounts) and structural cross-links that tie
    entities across domains + background memory priors. Cross-link refs aliased."""
    sm = package.summary_bundle()
    acct = sm.accounts_digest
    return {
        "note": ("Scope + structure only. There is NO precomputed score here — YOU synthesize the overall "
                 "omi_score from the per-account raw metadata, comment structure, and co-occurrence."),
        "inputs_provided": list(sm.inputs_provided), "platform": sm.platform,
        "post_content_id": sm.post_content_id,
        "account_count": (acct.count if acct else 0),
        "cross_links": [[l.kind, list(l.evidence), [alias.account_alias(r) for r in l.related_refs]]
                        for l in sm.cross_links],
        "cross_link_columns": ["kind", "evidence", "related_refs"],
        "memory": [[p.type, p.label, p.influence_class, p.epistemic_status]
                   for p in sm.memory_priors],
    }


# --------------------------------------------------------------------------- #
# Top-level render — surplus-flowing budget across domains
# --------------------------------------------------------------------------- #
def render_investigation_evidence(
    package, *, config: BudgetConfig | None = None,
) -> RenderedEvidence:
    """Render the complete InvestigationPackage into budgeted, normalized, model-facing sections.

    Small structural domains render in full first; their unused soft budget flows into a surplus pool
    that the large domains (comments, then accounts) draw on — so a sparse narrative domain donates its
    budget to a dense account domain rather than either starving. Every domain's coverage is disclosed.
    """
    cfg = config or BudgetConfig()
    alias = build_alias_legend(package)

    # 1) full-render the small, structurally load-bearing domains; measure surplus
    summary = _render_summary(package, alias)
    coordination = _render_coordination(package, alias)
    campaign = _render_campaign(package, alias)
    narrative = _render_narrative(package, alias)

    pool = 0
    coverage_domains: dict[str, dict] = {}
    for name, sec in (("investigation_summary", summary), ("coordination_analysis", coordination),
                      ("campaign_analysis", campaign), ("narrative_analysis", narrative)):
        pool += cfg.domain_budget(name) - estimate_json_tokens(sec)

    # 2) budget the large domains, drawing on accumulated surplus (comments, then accounts)
    comment_budget = cfg.domain_budget("comment_analysis") + max(0, pool)
    comments, comments_used, comment_cov = _render_comments(package, alias, comment_budget)
    pool += cfg.domain_budget("comment_analysis") - comments_used

    account_budget = cfg.domain_budget("account_analysis") + max(0, pool)
    accounts, accounts_used, account_cov, represented_refs = _render_accounts(
        package, alias, account_budget)

    # 3) commenter history, bounded to the accounts represented in the account domain
    commenter_history = _render_commenter_history(package, alias, represented_refs)

    sections = {
        "investigation_summary": summary,
        "comment_analysis": comments,
        "commenter_history": commenter_history,
        "account_analysis": accounts,
        "narrative_analysis": narrative,
        "coordination_analysis": coordination,
        "campaign_analysis": campaign,
    }
    coverage_domains["account_analysis"] = account_cov
    coverage_domains["comment_analysis"] = comment_cov

    total_tokens = sum(estimate_json_tokens(s) for s in sections.values())
    sampling = getattr(package, "sampling", {}) or {}
    any_omission = (any(c.get("mode") == "large_investigation" for c in coverage_domains.values())
                    or bool(sampling.get("truncated_upstream")))
    coverage = {
        "mode": "large_investigation" if any_omission else "complete",
        "total_evidence_tokens_est": total_tokens,
        "budget": {"total_tokens": cfg.total_tokens, "domain_shares": cfg.domain_shares},
        "domains": coverage_domains,
        # upstream sampling DISCLOSURE — the Evidence layer caps very large investigations; when it did,
        # observed>carried is disclosed here so no truncation is silent.
        "sampling": sampling,
        "token_estimator": "deterministic BPE-approximation (no tokenizer library present); "
                           "figures are estimates",
        "note": ("complete evidence rendered — no omissions" if not any_omission else
                 "Large Investigation Mode: some domains exceeded budget; representation is by evidence "
                 "coverage (graph degree / bridges / cluster coverage / detector disagreement / "
                 "duplicate-group size / recency), never by suspicion. All omissions disclosed above; "
                 "omitted entities remain in the evidence index + alias legend and stay citable."),
    }
    return RenderedEvidence(sections=sections, legend=alias.to_manifest(), coverage=coverage,
                            tokens=total_tokens)


__all__ = ["RenderedEvidence", "render_investigation_evidence"]
