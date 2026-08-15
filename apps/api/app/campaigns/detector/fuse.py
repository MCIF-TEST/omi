"""Edges to findings: fuse, cluster, gate, score.

Three guards live here and each one exists because of a specific way a coordination detector
embarrasses itself:

1. **Family-max fusion, not method-max.** Two methods reading the same material are one kind of
   evidence seen twice. `verbatim_echo` + `bio_echo` both say "these accounts emitted the same
   string"; letting them stack would mean one copy-paste observation clears a gate designed to
   need independent confirmation.

2. **The density gate.** A path a-b-c-d is not an operation, it is what you get when one account
   happens to share one property with each of two others. Community detection alone will happily
   hand back that chain as a community.

3. **The corroboration guard, as AND not OR.** ``app/detection/coordination/aggregate.py`` gates on
   "a discriminative detector OR two detectors", and its docstring records what it was written to
   stop: a lone `style_match` scoring a group of unrelated professionals at 1.0. That gate was
   calibrated on a mixed batch, where a lone discriminative hit stands out against a background of
   ordinary accounts. Here the cohort is pre-selected for suspicion, so every member already looks
   bad and one lens is never enough. Hence AND.
"""

from __future__ import annotations

import hashlib
from collections import defaultdict

from app.campaigns.detector.types import (
    DISCRIMINATIVE_FAMILIES,
    FAMILY_RELIABILITY,
    METHOD_FAMILY,
    Edge,
    Finding,
)

#: Fused pair weight below which two accounts are not considered linked at all.
EDGE_FLOOR = 0.35
#: A family "fired" inside a community only above this contribution. Mirrors
#: ``aggregate.EVIDENCE_EPS`` in spirit: a rounding-error contribution is not a corroboration.
EVIDENCE_EPS = 0.10
#: Fraction of a community's members a family must touch before it counts as explaining that
#: community. A family linking 2 of 8 members explained a pair, not the group.
MIN_FAMILY_COVERAGE = 0.50
#: Fraction of all possible internal pairs that must carry an edge. This is the chain test.
MIN_DENSITY = 0.60
#: Matches ``CampaignService._MIN_MEMBERS``. Two accounts agreeing is a coincidence.
MIN_MEMBERS = 3
#: Top of MODERATE. Same value and same meaning as ``aggregate.SUPPORTING_CEILING``.
SUPPORTING_CEILING = 0.49
#: A finding at or above this, having passed the guard, is what gets called a campaign.
CAMPAIGN_SCORE = 0.60

LABEL_CORROBORATED = "corroborated"
LABEL_LEAD = "lead"


def fuse_pairs(edges: list[Edge]) -> dict[tuple[str, str], float]:
    """Fused 0..1 weight per account pair.

    Within a family the strongest edge wins; across families a noisy-OR combines them. Edges with
    an empty artifact are dropped before anything else: a claim nobody can check is not evidence,
    and this is the one chokepoint every signal passes through.
    """
    by_pair_family: dict[tuple[str, str], dict[str, float]] = defaultdict(dict)
    for e in edges:
        if not (e.artifact or "").strip():
            continue
        fam = METHOD_FAMILY.get(e.method)
        if fam is None:
            continue
        cur = by_pair_family[e.pair].get(fam, 0.0)
        if e.weight > cur:
            by_pair_family[e.pair][fam] = e.weight

    fused: dict[tuple[str, str], float] = {}
    for pair, fams in by_pair_family.items():
        not_or = 1.0
        for fam, w in fams.items():
            not_or *= (1.0 - FAMILY_RELIABILITY.get(fam, 0.5) * max(0.0, min(1.0, w)))
        fused[pair] = 1.0 - not_or
    return fused


def _communities(nodes: list[str], fused: dict[tuple[str, str], float]) -> list[list[str]]:
    """Partition the linked accounts.

    Louvain with a fixed seed and sorted insertion order, so the same input always gives the same
    partition. These findings name real people; a result that changes between two runs on one
    worker is not a result. If networkx is somehow unavailable the fallback is connected
    components, which is worse (it merges groups a bridge account touches) but never crashes a
    scan, and the density gate still throws out the chains it produces.
    """
    live = {p: w for p, w in fused.items() if w >= EDGE_FLOOR}
    if not live:
        return []
    try:
        import networkx as nx
        from networkx.algorithms.community import louvain_communities

        g = nx.Graph()
        g.add_nodes_from(sorted({n for p in live for n in p} & set(nodes)))
        for (a, b), w in sorted(live.items()):
            if a in g and b in g:
                g.add_edge(a, b, weight=w)
        parts = louvain_communities(g, weight="weight", resolution=1.0, seed=0)
        return [sorted(p) for p in parts]
    except Exception:  # noqa: BLE001 - clustering must never break a scan
        parent: dict[str, str] = {}

        def find(x: str) -> str:
            parent.setdefault(x, x)
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        for (a, b) in live:
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[ra] = rb
        groups: dict[str, list[str]] = defaultdict(list)
        for node in parent:
            groups[find(node)].append(node)
        return [sorted(v) for v in groups.values()]


def _family_contributions(
    members: list[str], edges: list[Edge],
) -> tuple[dict[str, float], dict[str, float]]:
    """Per family: its coverage-weighted contribution, and the share of members it touched.

    The contribution divides by *all possible* internal pairs rather than by the pairs the family
    happened to link, so a family that links three pairs out of twenty-eight contributes like it
    linked three, not like it was unanimous.
    """
    member_set = set(members)
    n = len(members)
    possible = max(1, n * (n - 1) // 2)

    best: dict[str, dict[tuple[str, str], float]] = defaultdict(dict)
    touched: dict[str, set[str]] = defaultdict(set)
    for e in edges:
        if e.a not in member_set or e.b not in member_set:
            continue
        if not (e.artifact or "").strip():
            continue
        fam = METHOD_FAMILY.get(e.method)
        if fam is None:
            continue
        if e.weight > best[fam].get(e.pair, 0.0):
            best[fam][e.pair] = e.weight
        touched[fam].update((e.a, e.b))

    contributions: dict[str, float] = {}
    coverage: dict[str, float] = {}
    for fam, pairs in best.items():
        rel = FAMILY_RELIABILITY.get(fam, 0.5)
        contributions[fam] = rel * (sum(pairs.values()) / possible)
        coverage[fam] = len(touched[fam]) / n if n else 0.0
    return contributions, coverage


def _finding_id(members: list[str]) -> str:
    """Stable across runs, so the admin API can address a finding and a re-run keeps the same
    identity for the same group."""
    joined = "|".join(sorted(members))
    return "cf_" + hashlib.blake2b(joined.encode("utf-8"), digest_size=8).hexdigest()


def build_findings(nodes: list[str], edges: list[Edge]) -> list[Finding]:
    """Everything from raw edges to scored, gated, labelled findings."""
    fused = fuse_pairs(edges)
    findings: list[Finding] = []

    for members in _communities(sorted(set(nodes)), fused):
        if len(members) < 2:
            continue
        member_set = set(members)
        internal = [
            e for e in edges
            if e.a in member_set and e.b in member_set and (e.artifact or "").strip()
        ]
        live_pairs = {
            p for p, w in fused.items()
            if w >= EDGE_FLOOR and p[0] in member_set and p[1] in member_set
        }
        n = len(members)
        possible = max(1, n * (n - 1) // 2)
        density = len(live_pairs) / possible

        contributions, coverage = _family_contributions(members, internal)
        fired = sorted(
            fam for fam, c in contributions.items()
            if c > EVIDENCE_EPS and coverage.get(fam, 0.0) >= MIN_FAMILY_COVERAGE
        )
        silent = sorted(set(FAMILY_RELIABILITY) - set(fired))

        not_or = 1.0
        for fam in fired:
            not_or *= (1.0 - min(0.999, contributions[fam]))
        score = 1.0 - not_or

        has_discriminative = any(f in DISCRIMINATIVE_FAMILIES for f in fired)
        corroborated = has_discriminative and len(fired) >= 2

        capped = False
        notes: list[str] = []
        if not corroborated and score > SUPPORTING_CEILING:
            score = SUPPORTING_CEILING
            capped = True
        if not corroborated:
            if not fired:
                notes.append("No family of evidence covered enough of this group to count.")
            elif not has_discriminative:
                notes.append(
                    "Only supporting evidence fired (" + ", ".join(fired) + "). "
                    "A campaign needs at least one discriminative family."
                )
            else:
                notes.append(
                    "Only one family of evidence fired (" + ", ".join(fired) + "). "
                    "A campaign needs a second, independent kind."
                )
        if density < MIN_DENSITY:
            notes.append(
                f"Members are linked in a chain rather than a group "
                f"({len(live_pairs)} of {possible} possible pairs)."
            )
        if n < MIN_MEMBERS:
            notes.append("Two accounts agreeing is a coincidence, not an operation.")

        passes_structure = n >= MIN_MEMBERS and density >= MIN_DENSITY
        label = (
            LABEL_CORROBORATED
            if (corroborated and passes_structure and score >= CAMPAIGN_SCORE)
            else LABEL_LEAD
        )

        findings.append(Finding(
            finding_id=_finding_id(members),
            members=members,
            score=round(score, 4),
            label=label,
            capped=capped,
            density=round(density, 4),
            families_fired=fired,
            families_silent=silent,
            methods=sorted({e.method for e in internal}),
            edges=sorted(internal, key=lambda e: (-e.weight, e.method, e.a, e.b)),
            notes=notes,
        ))

    findings.sort(key=lambda f: (-f.score, f.finding_id))
    return findings


def lone_high_scorers(nodes: list[str], edges: list[Edge]) -> list[str]:
    """Cohort accounts with no surviving link to anyone.

    Reported separately and never as a campaign. These are accounts the per-account engine already
    found suspicious and this detector found no partner for, which is the expected outcome for most
    of them: a bought account with no visible network is still just one account.
    """
    fused = fuse_pairs(edges)
    linked = {n for p, w in fused.items() if w >= EDGE_FLOOR for n in p}
    return sorted(set(nodes) - linked)
