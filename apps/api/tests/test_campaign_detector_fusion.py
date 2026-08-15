"""The three structural guards in ``fuse.py``, tested directly on synthetic edges.

Testing these at the edge level rather than through a fixture is deliberate: a fixture proves the
guard fires for one arrangement of text, while these prove it fires for the *shape*, which is what
the guard is actually about.
"""

from __future__ import annotations

from app.campaigns.detector import fuse
from app.campaigns.detector.types import Edge


def edge(a: str, b: str, method: str, weight: float = 0.9) -> Edge:
    return Edge(a=a, b=b, method=method, weight=weight,
                sentence=f"{a} and {b} via {method}", artifact="the quoted material")


def clique(members: list[str], method: str, weight: float = 0.9) -> list[Edge]:
    return [
        edge(members[i], members[j], method, weight)
        for i in range(len(members)) for j in range(i + 1, len(members))
    ]


TRIO = ["a", "b", "c"]


# =============================================================================================
# Guard 1: family-max, not method-max
# =============================================================================================
def test_two_methods_in_one_family_do_not_corroborate_each_other():
    """`verbatim_echo` and `bio_echo` both say "these accounts emitted the same string". That is
    one kind of evidence seen twice. Counting method names would let a pure copy-paste observation
    clear a gate designed to require an independent second opinion."""
    edges = clique(TRIO, "verbatim_echo") + clique(TRIO, "bio_echo")
    findings = fuse.build_findings(TRIO, edges)
    assert len(findings) == 1
    f = findings[0]
    assert f.families_fired == ["text"]
    assert f.capped is True
    assert f.score <= fuse.SUPPORTING_CEILING
    assert f.label == fuse.LABEL_LEAD


def test_two_families_do_corroborate():
    edges = clique(TRIO, "verbatim_echo") + clique(TRIO, "client_signature")
    f = fuse.build_findings(TRIO, edges)[0]
    assert sorted(f.families_fired) == ["infrastructure", "text"]
    assert f.capped is False
    assert f.label == fuse.LABEL_CORROBORATED


# =============================================================================================
# Guard 2: AND, not OR
# =============================================================================================
def test_a_lone_discriminative_family_is_still_capped():
    """The engine's own gate is "discriminative OR two detectors". This one is AND, because the
    cohort here is pre-selected for suspicion: every member already looks bad, so a single lens
    agreeing is much weaker evidence than the same lens standing out against a mixed batch."""
    f = fuse.build_findings(TRIO, clique(TRIO, "verbatim_echo", 1.0))[0]
    assert f.capped is True
    assert f.score == fuse.SUPPORTING_CEILING


def test_two_supporting_methods_cannot_reach_a_campaign_either():
    """Both IDENTITY methods, which is one family, so this fails the family rule too.

    Stated as its own test because it is the arrangement an attacker controls most cheaply: handle
    shapes and signup times are the two things a farm operator picks deliberately.
    """
    edges = clique(TRIO, "provisioning_window") + clique(TRIO, "handle_template")
    f = fuse.build_findings(TRIO, edges)[0]
    assert f.families_fired == ["identity"]
    assert f.score <= fuse.SUPPORTING_CEILING
    assert f.label == fuse.LABEL_LEAD


def test_a_supporting_family_plus_a_discriminative_one_clears_the_gate():
    edges = clique(TRIO, "handle_template", 0.5) + clique(TRIO, "verbatim_echo", 0.95)
    f = fuse.build_findings(TRIO, edges)[0]
    assert sorted(f.families_fired) == ["identity", "text"]
    assert f.capped is False


# =============================================================================================
# Guard 3: density
# =============================================================================================
def test_a_chain_is_never_a_campaign():
    """a-b-c-d with no other links is what you get when one account happens to share one property
    with each of two others. The guarantee is that no campaign comes out of it; whether that
    happens because the partition splits the chain or because the density gate rejects it is an
    implementation detail, and asserting on which one fired would make this test brittle."""
    members = ["a", "b", "c", "d"]
    edges = [
        edge("a", "b", "verbatim_echo"), edge("b", "c", "verbatim_echo"),
        edge("c", "d", "verbatim_echo"),
        edge("a", "b", "client_signature"), edge("b", "c", "client_signature"),
        edge("c", "d", "client_signature"),
    ]
    findings = fuse.build_findings(members, edges)
    assert all(f.label == fuse.LABEL_LEAD for f in findings)
    assert not any(len(f.members) == 4 and f.label == fuse.LABEL_CORROBORATED for f in findings)


def test_a_hub_is_not_a_group():
    """One account linked to four others that are linked to nothing else. A partition keeps a star
    together, so this is the shape the density gate exists for: 4 of 10 possible pairs carry an
    edge, and a group where most members have never met is not an operation."""
    members = ["hub", "s1", "s2", "s3", "s4"]
    edges = []
    for s in members[1:]:
        edges.append(edge("hub", s, "verbatim_echo"))
        edges.append(edge("hub", s, "client_signature"))
    findings = fuse.build_findings(members, edges)
    assert findings
    f = max(findings, key=lambda x: len(x.members))
    assert len(f.members) == 5
    assert f.density < fuse.MIN_DENSITY
    assert f.label == fuse.LABEL_LEAD
    assert any("chain" in n for n in f.notes)


def test_a_pair_is_never_a_campaign():
    edges = [edge("a", "b", "verbatim_echo"), edge("a", "b", "client_signature")]
    findings = fuse.build_findings(["a", "b"], edges)
    assert all(f.label == fuse.LABEL_LEAD for f in findings)


# =============================================================================================
# The artifact requirement
# =============================================================================================
def test_an_edge_without_an_artifact_is_discarded():
    """The deterministic form of "if you cannot quote it, you cannot claim it". An unquotable
    claim about a named person is not evidence, so it never reaches a finding at all."""
    ghosts = [
        Edge(a=a, b=b, method="verbatim_echo", weight=1.0, sentence="trust me", artifact="")
        for a in TRIO for b in TRIO if a < b
    ]
    assert fuse.fuse_pairs(ghosts) == {}
    assert fuse.build_findings(TRIO, ghosts) == []


# =============================================================================================
# Determinism
# =============================================================================================
def test_the_same_input_always_gives_the_same_answer():
    """These are published claims about named accounts. A verdict that changes between two runs on
    one machine is not a verdict. Clustering is seeded and every iteration is over sorted keys."""
    members = [f"acct{i}" for i in range(9)]
    edges = (
        clique(members[:5], "verbatim_echo", 0.9)
        + clique(members[:5], "client_signature", 0.85)
        + clique(members[5:], "co_target", 0.8)
        + clique(members[5:], "burst_lockstep", 0.8)
    )
    baseline = fuse.build_findings(members, edges)
    for _ in range(5):
        again = fuse.build_findings(list(reversed(members)), list(reversed(edges)))
        assert [f.finding_id for f in again] == [f.finding_id for f in baseline]
        assert [f.score for f in again] == [f.score for f in baseline]
        assert [f.members for f in again] == [f.members for f in baseline]


def test_disjoint_groups_stay_disjoint():
    """Two operations under one post must not be merged into one. ``CampaignService.merge_clusters``
    unions any two clusters sharing an account, so the detector hands it member-disjoint
    communities and calls it once per finding."""
    left, right = ["a", "b", "c"], ["x", "y", "z"]
    edges = (
        clique(left, "verbatim_echo") + clique(left, "client_signature")
        + clique(right, "co_target") + clique(right, "burst_lockstep")
    )
    findings = fuse.build_findings(left + right, edges)
    assert len(findings) == 2
    got = sorted(tuple(f.members) for f in findings)
    assert got == [("a", "b", "c"), ("x", "y", "z")]


def test_lone_high_scorers_are_the_unlinked_ones():
    edges = clique(TRIO, "verbatim_echo") + clique(TRIO, "client_signature")
    nodes = TRIO + ["alone1", "alone2"]
    assert fuse.lone_high_scorers(nodes, edges) == ["alone1", "alone2"]
