"""The structural guarantees of the fusion layer, on synthetic edges.

Every test here asserts a GUARANTEE, never the mechanism that currently delivers it. That
distinction earned itself: the previous version of this file asserted on `MIN_DENSITY` and
`SUPPORTING_CEILING`, and when the scoring moved to a calibrated posterior those constants stopped
existing even though every property they protected still held.
"""

from __future__ import annotations

from app.campaigns.detector import fuse
from app.campaigns.detector.probability import DECISION_THRESHOLD
from app.campaigns.detector.types import Edge

TRIO = ["a", "b", "c"]
QUAD = ["a", "b", "c", "d"]


def edge(a: str, b: str, method: str, measured_p: float | None = None) -> Edge:
    return Edge(
        a=a, b=b, method=method, weight=0.9,
        sentence=f"{a} and {b} via {method}", artifact="the quoted material",
        measured_p=measured_p,
    )


def clique(members: list[str], method: str, measured_p: float | None = None) -> list[Edge]:
    return [
        edge(members[i], members[j], method, measured_p)
        for i in range(len(members)) for j in range(i + 1, len(members))
    ]


def campaigns(findings) -> list:
    return [f for f in findings if f.label == fuse.LABEL_CORROBORATED]


# ==================================================================================================
# One kind of evidence is never enough, however strong
# ==================================================================================================
def test_a_single_family_never_convicts_however_strong():
    """The old code enforced this with an explicit gate and a 0.49 ceiling. It is now arithmetic:
    no single family can lift the prior past the bar. Same guarantee, no rule."""
    for method, p in [
        ("verbatim_echo", None),
        ("bio_echo", None),
        ("co_target", None),
        ("client_signature", None),
        ("handle_template", None),
        ("burst_lockstep", 1e-9),          # absurdly significant on purpose
        ("provisioning_window", 1e-9),
    ]:
        found = campaigns(fuse.build_findings(QUAD, clique(QUAD, method, p)))
        assert found == [], f"{method} alone produced a campaign"


def test_two_methods_in_one_family_do_not_corroborate_each_other():
    """`verbatim_echo` and `bio_echo` both say "these accounts emitted the same string". That is one
    observation seen twice, and multiplying it would be double-counting."""
    edges = clique(QUAD, "verbatim_echo") + clique(QUAD, "bio_echo")
    findings = fuse.build_findings(QUAD, edges)
    assert campaigns(findings) == []
    assert findings and findings[0].families_fired == ["text"]


def test_both_identity_methods_together_still_do_not_convict():
    """Handle shape and signup time are the two things a farm operator picks deliberately, so they
    are the cheapest pair to fake. One family, and a weak one."""
    edges = clique(QUAD, "handle_template") + clique(QUAD, "provisioning_window", 1e-6)
    assert campaigns(fuse.build_findings(QUAD, edges)) == []


# ==================================================================================================
# Two independent kinds of evidence are enough
# ==================================================================================================
def test_two_independent_families_convict():
    edges = clique(QUAD, "verbatim_echo") + clique(QUAD, "client_signature")
    found = campaigns(fuse.build_findings(QUAD, edges))
    assert len(found) == 1
    assert found[0].members == QUAD
    assert found[0].score >= DECISION_THRESHOLD


def test_the_group_score_is_its_weakest_member_not_its_strongest():
    """A group is only as defensible as the least defensible person named in it, and that person is
    the one harmed if this is wrong. `d` is linked by one family only."""
    edges = clique(TRIO, "verbatim_echo") + clique(TRIO, "client_signature")
    edges += [edge("d", m, "verbatim_echo") for m in TRIO]
    findings = fuse.build_findings(QUAD, edges)
    assert findings
    f = findings[0]
    assert "d" not in f.members, "one family should not have admitted d"
    assert f.score == min(f.member_posteriors.values())


# ==================================================================================================
# Shape: the claim has to mean what the sentence says
# ==================================================================================================
def test_a_star_is_not_a_group():
    """One account whose script four unrelated people each copied. Every spoke links to the hub at
    high probability and the spokes share nothing, so reporting all five as "running together"
    would say something the evidence never said."""
    members = ["hub", "s1", "s2", "s3", "s4"]
    edges = []
    for s in members[1:]:
        edges.append(edge("hub", s, "verbatim_echo"))
        edges.append(edge("hub", s, "client_signature"))
    assert campaigns(fuse.build_findings(members, edges)) == []


def test_a_chain_is_not_a_group():
    members = ["a", "b", "c", "d"]
    edges = []
    for x, y in (("a", "b"), ("b", "c"), ("c", "d")):
        edges.append(edge(x, y, "verbatim_echo"))
        edges.append(edge(x, y, "client_signature"))
    assert campaigns(fuse.build_findings(members, edges)) == []


def test_a_pair_is_never_a_campaign():
    edges = [edge("a", "b", "verbatim_echo"), edge("a", "b", "client_signature")]
    assert campaigns(fuse.build_findings(["a", "b"], edges)) == []


def test_disjoint_groups_stay_disjoint():
    """Two operations under one post must not be merged. ``CampaignService.merge_clusters`` unions
    any two clusters sharing an account, so findings must come out member-disjoint."""
    left, right = ["a", "b", "c"], ["x", "y", "z"]
    edges = (
        clique(left, "verbatim_echo") + clique(left, "client_signature")
        + clique(right, "co_target") + clique(right, "burst_lockstep", 1e-5)
    )
    found = campaigns(fuse.build_findings(left + right, edges))
    assert sorted(tuple(f.members) for f in found) == [("a", "b", "c"), ("x", "y", "z")]


def test_no_account_appears_in_two_findings():
    left, right = ["a", "b", "c"], ["c", "y", "z"]      # 'c' is in both
    edges = (
        clique(left, "verbatim_echo") + clique(left, "client_signature")
        + clique(right, "co_target") + clique(right, "burst_lockstep", 1e-5)
    )
    findings = fuse.build_findings(sorted(set(left + right)), edges)
    seen: set[str] = set()
    for f in findings:
        assert not (seen & set(f.members)), "an account was reported in two groups"
        seen |= set(f.members)


# ==================================================================================================
# Evidentiary floors
# ==================================================================================================
def test_an_edge_without_an_artifact_is_discarded():
    """The deterministic form of "if you cannot quote it, you cannot claim it". An unquotable claim
    about a named person is not evidence at any confidence."""
    ghosts = [
        Edge(a=a, b=b, method="verbatim_echo", weight=1.0, sentence="trust me", artifact="")
        for a in QUAD for b in QUAD if a < b
    ]
    ghosts += [
        Edge(a=a, b=b, method="client_signature", weight=1.0, sentence="trust me", artifact="")
        for a in QUAD for b in QUAD if a < b
    ]
    assert fuse.pair_evidence(ghosts) == {}
    assert fuse.build_findings(QUAD, ghosts) == []


def test_every_member_carries_its_own_admitting_posterior():
    """Shown per account in the UI so a reviewer can challenge one name without dismissing the
    whole finding."""
    edges = clique(QUAD, "verbatim_echo") + clique(QUAD, "client_signature")
    f = campaigns(fuse.build_findings(QUAD, edges))[0]
    assert set(f.member_posteriors) == set(f.members)
    assert all(v >= DECISION_THRESHOLD for v in f.member_posteriors.values())
    assert f.derivation and "posterior" in f.derivation


# ==================================================================================================
# Cross-scan accumulation
# ==================================================================================================
def test_a_second_independent_sighting_can_carry_a_single_family_over_the_bar():
    """One family on one post is not enough. The same pair showing the same evidence on a DIFFERENT
    post is a new observation, and two of them are decisive. This is the whole return on tracking
    operations across investigations rather than per scan."""
    edges = clique(QUAD, "verbatim_echo")
    assert campaigns(fuse.build_findings(QUAD, edges)) == []

    from app.campaigns.detector.probability import log10_lr
    carried = log10_lr("verbatim_echo") * 0.5
    accumulated = {
        (QUAD[i], QUAD[j]): carried
        for i in range(len(QUAD)) for j in range(i + 1, len(QUAD))
    }
    found = campaigns(fuse.build_findings(QUAD, edges, accumulated=accumulated))
    assert len(found) == 1 and found[0].score >= DECISION_THRESHOLD


# ==================================================================================================
# Determinism
# ==================================================================================================
def test_the_same_input_always_gives_the_same_answer():
    """These are published claims about named accounts. A verdict that changes between two runs on
    one machine is not a verdict."""
    members = [f"acct{i}" for i in range(9)]
    edges = (
        clique(members[:5], "verbatim_echo") + clique(members[:5], "client_signature")
        + clique(members[5:], "co_target") + clique(members[5:], "burst_lockstep", 1e-5)
    )
    baseline = fuse.build_findings(members, edges)
    for _ in range(5):
        again = fuse.build_findings(list(reversed(members)), list(reversed(edges)))
        assert [f.finding_id for f in again] == [f.finding_id for f in baseline]
        assert [f.members for f in again] == [f.members for f in baseline]
        assert [f.score for f in again] == [f.score for f in baseline]


def test_lone_high_scorers_are_the_unlinked_ones():
    edges = clique(TRIO, "verbatim_echo") + clique(TRIO, "client_signature")
    nodes = TRIO + ["alone1", "alone2"]
    assert fuse.lone_high_scorers(nodes, edges) == ["alone1", "alone2"]
