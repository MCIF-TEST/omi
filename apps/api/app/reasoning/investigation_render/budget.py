"""Evidence-coverage budgeting — Large Investigation Mode.

When even the losslessly-normalized evidence exceeds the model-facing token budget, some items cannot be
rendered in full. The selection objective is **evidence COVERAGE, not suspicion ranking**: the goal is
to represent the full *structure* of the investigation (every cluster, every bridge, the detector
disagreements, the largest duplicate patterns) — never "show the most suspicious accounts and hide the
rest". A low-probability account may be the bridge that ties two clusters together; suppressing it by
tier/probability/intent/risk would let a heuristic conclusion decide what the model may see. That is
forbidden.

Every signal used here is an ALLOWED coverage signal: graph degree, cross-cluster (bridge) membership,
cluster-membership count, detector disagreement (signal-probability spread), near-duplicate group size,
and recency. None is a suspicion score. Selection is deterministic, and every omission is DISCLOSED in a
coverage manifest (observed / represented / deduplicated / omitted, plus the signals used) — nothing is
hard-truncated silently, and omitted entities remain in the evidence index + alias legend, so they stay
citable.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from app.reasoning.investigation_composer import InvestigationPackage

# The allowed coverage signals — recorded in every coverage manifest so the selection is auditable.
COVERAGE_SIGNALS = (
    "graph_degree", "cross_cluster_bridge", "cluster_membership_count",
    "detector_disagreement", "cluster_coverage_guarantee", "near_duplicate_group_size", "recency",
)


@dataclass(frozen=True)
class BudgetConfig:
    """Soft, evidence-neutral token budget for the model-facing evidence. Per-domain shares are SOFT:
    unused budget flows to later domains; a domain may exceed its share to honor a coverage guarantee.
    The ceiling sits well under the model window minus the system prompt."""

    total_tokens: int = 12000
    min_domain_tokens: int = 200
    domain_shares: dict[str, float] = field(default_factory=lambda: {
        "account_analysis": 0.30, "comment_analysis": 0.20, "coordination_analysis": 0.20,
        "commenter_history": 0.10, "narrative_analysis": 0.08, "campaign_analysis": 0.04,
        "investigation_summary": 0.08,
    })

    def domain_budget(self, domain: str) -> int:
        return max(self.min_domain_tokens, int(self.total_tokens * self.domain_shares.get(domain, 0.0)))


@dataclass(frozen=True)
class AccountCoverage:
    """The allowed coverage signals for one account (NO suspicion signal). ``priority`` orders
    representation when the budget binds — structurally important nodes first."""

    ref: str
    graph_degree: int = 0
    cluster_membership: int = 0
    is_bridge: bool = False               # participates in >= 2 clusters
    detector_disagreement: float = 0.0    # spread of the account's signal probabilities
    max_dup_group: int = 0                # largest near-duplicate comment group the account is in
    recency: str = ""                     # most-recent activity timestamp (ISO), "" if none

    @property
    def priority(self) -> tuple:
        """Deterministic coverage-priority key (descending importance). Bridges and high-degree nodes
        rank first — this is structural centrality, NOT suspicion. Ties break by ref for determinism."""
        return (self.is_bridge, self.cluster_membership, self.graph_degree,
                round(self.detector_disagreement, 6), self.max_dup_group, self.recency)


@dataclass(frozen=True)
class Selection:
    """The result of budgeting one domain: which refs/items are represented, which are omitted, and the
    disclosed coverage manifest."""

    represented: tuple[str, ...]
    omitted: tuple[str, ...]
    manifest: dict


def compute_account_coverage(package: "InvestigationPackage") -> dict[str, AccountCoverage]:
    """Derive each account's ALLOWED coverage signals from the complete package — graph degree,
    cluster membership / bridge status, detector disagreement, largest duplicate-group participation,
    recency. No probability / tier / intent / risk is read.

    ``graph_degree`` is connectivity over the coordination graph: the number of DISTINCT accounts an
    account is directly connected to — its co-members across shared clusters, plus any joined
    account-account graph edge. (Co-membership is used because it joins reliably to the account
    records; it is a distinct signal from ``cluster_membership``, which counts clusters, not peers.)"""
    b = package.bundles
    known = {a.author_ref for a in b.account.accounts}
    neighbors: dict[str, set[str]] = defaultdict(set)
    membership: dict[str, set[str]] = defaultdict(set)
    for cl in b.coordination.clusters:
        members = [m for m in cl.member_refs if m in known]
        for m in members:
            membership[m].add(cl.cluster_ref)
            neighbors[m].update(x for x in members if x != m)
    # fold in any account-account graph edge whose BOTH endpoints are known accounts (joined edges)
    for e in b.coordination.graph_edges:
        if e.from_ref in known and e.to_ref in known and e.from_ref != e.to_ref:
            neighbors[e.from_ref].add(e.to_ref)
            neighbors[e.to_ref].add(e.from_ref)
    degree = {r: len(ns) for r, ns in neighbors.items()}
    # largest duplicate comment group each author participates in
    sig_counts: Counter[str] = Counter()
    author_sig: dict[str, list[str]] = defaultdict(list)
    from .dedup import _signature
    for c in b.comment.comments:
        s = _signature(c.text)
        sig_counts[s] += 1
        author_sig[c.author_ref].append(s)
    recency: dict[str, str] = {}
    for c in b.comment.comments:
        if c.created_at and c.created_at > recency.get(c.author_ref, ""):
            recency[c.author_ref] = c.created_at

    out: dict[str, AccountCoverage] = {}
    for a in b.account.accounts:
        ref = a.author_ref
        probs = [s.probability for s in a.signals]
        spread = (max(probs) - min(probs)) if len(probs) >= 2 else 0.0
        max_dup = max((sig_counts[s] for s in author_sig.get(ref, [])), default=0)
        out[ref] = AccountCoverage(
            ref=ref, graph_degree=degree.get(ref, 0), cluster_membership=len(membership.get(ref, ())),
            is_bridge=len(membership.get(ref, ())) >= 2, detector_disagreement=spread,
            max_dup_group=max_dup, recency=recency.get(ref, ""),
        )
    return out


def select_accounts(
    package: "InvestigationPackage", cost_of: Callable[[str], int], budget_tokens: int,
) -> Selection:
    """Select the accounts to represent within ``budget_tokens`` by COVERAGE. Greedy by coverage
    priority, then a hard per-cluster coverage guarantee (every cluster keeps >= 1 represented member,
    chosen by degree), then disclosure of every omission. Never orders by suspicion."""
    b = package.bundles
    coverage = compute_account_coverage(package)
    refs = [a.author_ref for a in b.account.accounts]
    observed = len(refs)
    # 1) greedy representation in coverage-priority order (bridges/degree/disagreement first)
    ordered = sorted(refs, key=lambda r: (coverage[r].priority, r), reverse=True)
    represented: list[str] = []
    used = 0
    for r in ordered:
        c = cost_of(r)
        if used + c <= budget_tokens or not represented:  # always keep at least one
            represented.append(r)
            used += c
        # else: defer — may still be force-added by the cluster-coverage guarantee below
    kept = set(represented)
    # 2) per-cluster coverage guarantee — no cluster may be entirely unrepresented
    forced: list[str] = []
    for cl in b.coordination.clusters:
        members = [m for m in cl.member_refs if m in coverage]
        if members and not (kept & set(members)):
            pick = max(members, key=lambda r: (coverage[r].graph_degree, r))
            kept.add(pick)
            forced.append(pick)
    represented = [r for r in ordered if r in kept]
    omitted = tuple(r for r in ordered if r not in kept)
    mode = "large_investigation" if omitted else "complete"
    manifest = {
        "domain": "account_analysis", "observed": observed, "represented": len(represented),
        "deduplicated": 0, "omitted": len(omitted), "mode": mode,
        "selection_signals": list(COVERAGE_SIGNALS),
        "cluster_coverage_forced": len(forced),
        "note": ("all accounts represented" if not omitted else
                 f"{len(omitted)} account(s) omitted from full rendering by evidence-coverage budgeting "
                 f"(never by suspicion); every omitted account remains in the evidence index + alias "
                 f"legend and stays citable. Per-cluster coverage guaranteed."),
    }
    return Selection(represented=tuple(represented), omitted=omitted, manifest=manifest)


def select_comment_groups(
    groups, cost_of: Callable[[int], int], budget_tokens: int, *, deduplicated: int = 0,
) -> Selection:
    """Select near-duplicate comment GROUPS to represent within budget. Groups are pre-ordered by size
    (a larger identical-text group is a stronger coordination signal — coverage, not suspicion); keep
    them greedily, always keeping at least one, and disclose omitted groups. ``groups`` are indexed by
    position; ``cost_of(i)`` estimates the i-th group's rendered cost."""
    represented: list[int] = []
    used = 0
    for i, _g in enumerate(groups):
        c = cost_of(i)
        if used + c <= budget_tokens or not represented:
            represented.append(i)
            used += c
    omitted = tuple(str(i) for i in range(len(groups)) if i not in set(represented))
    mode = "large_investigation" if omitted else "complete"
    manifest = {
        "domain": "comment_analysis", "observed": sum(g.count for g in groups),
        "represented_groups": len(represented), "total_groups": len(groups),
        "deduplicated": deduplicated, "omitted_groups": len(omitted), "mode": mode,
        "selection_signals": ["near_duplicate_group_size", "coverage_of_distinct_patterns"],
        "note": ("all comment groups represented" if not omitted else
                 f"{len(omitted)} smaller near-duplicate group(s) omitted from full rendering by "
                 f"coverage budgeting; each omitted group's members remain in the evidence index."),
    }
    return Selection(represented=tuple(str(i) for i in represented), omitted=omitted, manifest=manifest)


__all__ = [
    "COVERAGE_SIGNALS", "BudgetConfig", "AccountCoverage", "Selection",
    "compute_account_coverage", "select_accounts", "select_comment_groups",
]
