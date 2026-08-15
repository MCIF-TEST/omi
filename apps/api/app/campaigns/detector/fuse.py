"""Edges to findings: evidence in, calibrated probability out.

The rule this module implements is the product's rule, stated literally:

    An account joins an operation only when ITS OWN posterior probability of being coordinated
    with that group is at or above the threshold.

Per account, not per group. That distinction is the whole point. A group-level score lets a weakly
connected account ride in on its neighbours' evidence, which is exactly how a real person standing
next to an operation ends up named as part of it. Here every member has to earn its own place, and
the evidence that admitted it is attached to it.

---------------------------------------------------------------------------------------------------
WHAT THIS REPLACES, AND WHY THE OLD GUARDS ARE GONE
---------------------------------------------------------------------------------------------------

The previous version scored a community with a noisy-OR over family contributions and then bolted
on a gate: cap at 0.49 unless a discriminative family fired AND at least two families did. That gate
was right about the world and wrong about where it lived. With honest likelihood ratios the same
discipline falls out of the arithmetic (see ``probability.py``): no single family, at any strength,
can lift the prior past 0.95. So ``SUPPORTING_CEILING`` and ``EVIDENCE_EPS`` are deleted rather than
ported. ``tests/test_coordination_probability.py`` pins every refusal they used to enforce.

Three guards survive, because none of them is a probability claim:

* **Every edge must carry an artifact.** The deterministic form of "if you cannot quote it, you
  cannot claim it". An unquotable claim about a named person is not evidence at any confidence.
* **Minimum three members.** Two accounts agreeing is a coincidence with a good story.
* **Within-family max, across-family product.** Now load-bearing arithmetic rather than a
  heuristic: likelihood ratios multiply only when the evidence is conditionally independent, and
  the family map is that independence assumption written down.
"""

from __future__ import annotations

import hashlib
from collections import defaultdict

from app.campaigns.detector.probability import (
    DECISION_THRESHOLD,
    DEFAULT_PRIOR,
    LR_VERSION,
    explain,
    posterior,
)
from app.campaigns.detector.types import METHOD_FAMILY, Edge, Finding

#: Below this posterior a pair is not evidence of anything and is dropped before clustering. Well
#: under the decision threshold on purpose: a pair at 0.5 cannot convict, but three such pairs
#: pointing at one account are worth carrying into the growth step.
LINK_FLOOR = 0.50

#: Matches ``CampaignService._MIN_MEMBERS``.
MIN_MEMBERS = 3

#: Once a group has three members, a new account must clear the bar against at least this many of
#: them SEPARATELY. This is what stops a star.
#:
#: Per-member posterior alone is not enough here, and the reason is worth keeping: if one account
#: posted a script that four unrelated people each copied, every one of those four links to the hub
#: at high probability while sharing nothing with each other. Admitting them all would report five
#: accounts as "running together" on evidence that only ever said "each of these four echoed that
#: one". Requiring two independent links makes the claim mean what the sentence says. It also
#: replaces the old density ratio with something better matched to the per-member framing: a
#: threshold on the group's shape was a proxy for this, and this is the thing itself.
MIN_LINKS_INTO_GROUP = 2

LABEL_CORROBORATED = "corroborated"
LABEL_LEAD = "lead"


# ==================================================================================================
# Pairwise posteriors
# ==================================================================================================
def pair_evidence(edges: list[Edge]) -> dict[tuple[str, str], dict[str, float]]:
    """Per pair, the strongest log10 likelihood ratio each family contributed.

    Reduction to one value per family happens HERE and nowhere else, so the conditional-independence
    assumption has exactly one implementation. Edges with no artifact are dropped first: this is the
    single chokepoint every signal passes through, so an unquotable claim cannot reach a verdict by
    any route.
    """
    out: dict[tuple[str, str], dict[str, float]] = defaultdict(dict)
    for e in edges:
        if not (e.artifact or "").strip():
            continue
        family = METHOD_FAMILY.get(e.method)
        if family is None:
            continue
        contribution = e.log10_lr
        if contribution <= 0:
            continue
        if contribution > out[e.pair].get(family, 0.0):
            out[e.pair][family] = contribution
    return dict(out)


def pair_posteriors(
    edges: list[Edge],
    *,
    prior: float = DEFAULT_PRIOR,
    accumulated: dict[tuple[str, str], float] | None = None,
) -> dict[tuple[str, str], float]:
    """P(coordinated) for every pair with evidence.

    ``accumulated`` carries cross-scan history from the tracking layer: log10 evidence this same
    pair earned on OTHER posts, already discounted for context correlation. It is the mechanism that
    makes a pair seen twice on unrelated posts decisive when one sighting alone was not.
    """
    acc = accumulated or {}
    return {
        pair: posterior(fams, prior=prior, extra_log10=acc.get(pair, 0.0))
        for pair, fams in pair_evidence(edges).items()
    }


# ==================================================================================================
# Growth
# ==================================================================================================
def _member_evidence(
    candidate: str,
    members: set[str],
    evidence: dict[tuple[str, str], dict[str, float]],
) -> dict[str, float]:
    """One candidate's strongest evidence to a group, per family.

    Takes the max to ANY member rather than summing over members, and that is deliberate. Four
    accounts posting one script give a candidate four text edges, but they are four views of a
    single fact. Summing them would let group size manufacture confidence, so a big group would
    admit almost anyone, which is precisely the failure mode that makes coordination detectors
    embarrassing.
    """
    best: dict[str, float] = {}
    for member in members:
        pair = (candidate, member) if candidate <= member else (member, candidate)
        for family, value in evidence.get(pair, {}).items():
            if value > best.get(family, 0.0):
                best[family] = value
    return best


def grow(
    seed: tuple[str, str],
    evidence: dict[tuple[str, str], dict[str, float]],
    candidates: set[str],
    *,
    prior: float = DEFAULT_PRIOR,
    threshold: float = DECISION_THRESHOLD,
    accumulated: dict[tuple[str, str], float] | None = None,
) -> tuple[set[str], dict[str, float]]:
    """Grow a group from a seed pair, admitting only accounts that clear the bar themselves.

    Greedy and deterministic: at each step take the qualifying candidate with the highest posterior,
    ties broken on id. Returns the members and each member's own admitting posterior, which is what
    the UI shows so a reader can see WHY each specific person is on the list.
    """
    acc = accumulated or {}

    def link(cand: str, members: set[str]) -> float:
        fams = _member_evidence(cand, members, evidence)
        if not fams:
            return 0.0
        extra = max(
            (acc.get((cand, m) if cand <= m else (m, cand), 0.0) for m in members),
            default=0.0,
        )
        return posterior(fams, prior=prior, extra_log10=extra)

    def qualifying_links(cand: str, members: set[str]) -> int:
        """How many members this candidate independently clears the bar against."""
        n = 0
        for m in members:
            pair = (cand, m) if cand <= m else (m, cand)
            fams = evidence.get(pair)
            if not fams:
                continue
            if posterior(fams, prior=prior, extra_log10=acc.get(pair, 0.0)) >= threshold:
                n += 1
        return n

    members = {seed[0], seed[1]}
    seed_p = posterior(
        evidence.get(seed, {}), prior=prior, extra_log10=acc.get(seed, 0.0),
    )
    admitted = {seed[0]: seed_p, seed[1]: seed_p}

    while True:
        best_id, best_p = None, 0.0
        # Every admission after the seed pair needs MIN_LINKS_INTO_GROUP independent links. The
        # seed is two accounts with one link between them, which is all a pair can have; from the
        # third member on there is a group to join, and joining it means linking to more than one
        # of its members. Requiring this only from the fourth member let a three-account star
        # through, which is the smallest thing this rule exists to refuse.
        need = MIN_LINKS_INTO_GROUP if len(members) >= 2 else 1
        for cand in sorted(candidates - members):
            p = link(cand, members)
            if p < threshold or p <= best_p:
                continue
            if qualifying_links(cand, members) < need:
                continue
            best_id, best_p = cand, p
        if best_id is None:
            return members, admitted
        members.add(best_id)
        admitted[best_id] = best_p


def _finding_id(members: list[str]) -> str:
    """Stable across runs, so a re-run keeps the same identity for the same group."""
    return "cf_" + hashlib.blake2b(
        "|".join(sorted(members)).encode("utf-8"), digest_size=8,
    ).hexdigest()


def build_findings(
    nodes: list[str],
    edges: list[Edge],
    *,
    prior: float = DEFAULT_PRIOR,
    threshold: float = DECISION_THRESHOLD,
    accumulated: dict[tuple[str, str], float] | None = None,
) -> list[Finding]:
    """Every group whose members each clear the bar.

    Groups are grown from qualifying seed pairs, strongest first, and an account is never placed in
    two groups: the first (strongest) group that admits it keeps it, so findings come out
    member-disjoint. That matters downstream because ``CampaignService.merge_clusters`` unions any
    two clusters sharing one account, and overlapping findings would fuse into a fake mega-campaign.
    """
    evidence = pair_evidence(edges)
    if not evidence:
        return []

    posts = {
        pair: posterior(fams, prior=prior, extra_log10=(accumulated or {}).get(pair, 0.0))
        for pair, fams in evidence.items()
    }
    live = {p: v for p, v in posts.items() if v >= LINK_FLOOR}
    node_set = set(nodes)

    findings: list[Finding] = []
    claimed: set[str] = set()

    for seed in sorted(live, key=lambda p: (-live[p], p)):
        if live[seed] < threshold:
            break
        if seed[0] in claimed or seed[1] in claimed:
            continue
        members, admitted = grow(
            seed, evidence, node_set - claimed,
            prior=prior, threshold=threshold, accumulated=accumulated,
        )
        if len(members) < MIN_MEMBERS:
            continue
        claimed |= members
        findings.append(_finding(members, admitted, evidence, edges, prior))

    # Anything left that linked above the floor but never cleared the bar is reported as a lead:
    # visible to an operator, never written as a campaign, never published.
    leads = {n for p, v in live.items() if v < threshold for n in p} - claimed
    if len(leads) >= MIN_MEMBERS:
        near = {n: max(
            (v for p, v in live.items() if n in p), default=0.0,
        ) for n in leads}
        findings.append(_finding(leads, near, evidence, edges, prior, forced_label=LABEL_LEAD))

    findings.sort(key=lambda f: (-f.score, f.finding_id))
    return findings


def _finding(
    members: set[str],
    admitted: dict[str, float],
    evidence: dict[tuple[str, str], dict[str, float]],
    edges: list[Edge],
    prior: float,
    *,
    forced_label: str | None = None,
) -> Finding:
    ordered = sorted(members)
    internal = [
        e for e in edges
        if e.a in members and e.b in members and (e.artifact or "").strip()
    ]
    families = sorted({
        fam
        for pair, fams in evidence.items()
        if pair[0] in members and pair[1] in members
        for fam in fams
    })
    possible = max(1, len(ordered) * (len(ordered) - 1) // 2)
    linked = sum(
        1 for pair in evidence
        if pair[0] in members and pair[1] in members
    )

    # The group's headline number is its WEAKEST member's admitting posterior, not its strongest and
    # not its mean. A group is only as defensible as the least defensible person named in it, and
    # that person is the one who will be harmed if this is wrong.
    weakest = min((admitted.get(m, 0.0) for m in ordered), default=0.0)

    label = forced_label or (
        LABEL_CORROBORATED
        if weakest >= DECISION_THRESHOLD and len(ordered) >= MIN_MEMBERS
        else LABEL_LEAD
    )

    notes: list[str] = []
    if label == LABEL_LEAD:
        notes.append(
            f"Weakest member links at {weakest:.0%}, below the {DECISION_THRESHOLD:.0%} bar."
            if weakest else "No member cleared the bar."
        )
    if len(ordered) < MIN_MEMBERS:
        notes.append("Two accounts agreeing is a coincidence, not an operation.")

    strongest_pair = max(
        ((p, f) for p, f in evidence.items() if p[0] in members and p[1] in members),
        key=lambda kv: sum(kv[1].values()), default=None,
    )

    return Finding(
        finding_id=_finding_id(ordered),
        members=ordered,
        score=round(weakest, 4),
        label=label,
        capped=False,
        density=round(linked / possible, 4),
        families_fired=families,
        families_silent=sorted(set(METHOD_FAMILY.values()) - set(families)),
        methods=sorted({e.method for e in internal}),
        edges=sorted(internal, key=lambda e: (-e.log10_lr, e.method, e.a, e.b)),
        notes=notes,
        member_posteriors={m: round(admitted.get(m, 0.0), 4) for m in ordered},
        prior=prior,
        lr_version=LR_VERSION,
        derivation=explain(strongest_pair[1], prior=prior) if strongest_pair else "",
    )


def lone_high_scorers(nodes: list[str], edges: list[Edge]) -> list[str]:
    """Cohort accounts with no link to anyone above the floor.

    Reported separately and never as a campaign. For most of them this is the expected outcome: an
    account the per-account engine found suspicious, with no partner visible. Suspicious alone is
    not the same as acting together, and collapsing the two is how a detector turns a list of
    individuals into an imaginary conspiracy.
    """
    linked = {n for p, v in pair_posteriors(edges).items() if v >= LINK_FLOOR for n in p}
    return sorted(set(nodes) - linked)
