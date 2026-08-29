"""The coordinated-network detector.

READ THE FALSIFICATION TEST FIRST. Everything else in this file is a claim about what the detector
finds; ``test_a_shuffled_corpus_yields_nothing`` is the claim that it finds nothing when there is
nothing there, and if that one fails every other pass in this file is meaningless.

The controls come before the recall tests on purpose. This product publishes claims about named real
people, so a detector that catches every operation and also accuses a newsroom is worse than one
that catches half of them and stays quiet.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import netdetect_corpora as C  # noqa: E402

from app.netdetect import Corpus, detect, detect_from_commenters, score_candidate  # noqa: E402
from app.netdetect.candidates import communities  # noqa: E402
from app.netdetect.features import (  # noqa: E402
    handle_skeleton,
    profile_from_commenter,
    timing_features,
)
from app.netdetect.shuffle import shuffle_corpus  # noqa: E402
from app.netdetect.significance import _poisson_binomial_tail, internal_reply_ratio  # noqa: E402

#: Enough shuffles to express p<=0.05 (the floor is 1/(K+1)), small enough to keep the suite quick.
SHUFFLES = 24


def _corpus(rows: list[dict]) -> Corpus:
    return Corpus([profile_from_commenter(r) for r in rows])


def _members_from(candidate, prefix: str) -> int:
    return sum(1 for m in candidate.members if m.startswith(prefix))


# =============================================================================================== #
# 1. Falsification. If this fails, nothing else in this file means anything.
# =============================================================================================== #
def test_a_shuffled_corpus_yields_nothing():
    """Run the WHOLE pipeline on data with the association destroyed and the structure kept.

    A degree-preserving shuffle leaves every account as prolific as it was and every feature as
    popular as it was, and removes only WHICH account holds WHICH feature. That association is
    exactly what coordination is, so a detector that still reports findings here is reporting its
    own search, not the data.
    """
    real = _corpus(C.organic_population(50) + C.planted_operation(8, discipline=0.0))
    scrambled = shuffle_corpus(real, seed=4242)

    result = detect(scrambled, shuffles=SHUFFLES)

    assert result.findings == [], (
        "the detector found structure in shuffled data, which means the pipeline manufactures "
        f"findings: {[(c.size, round(c.score, 1)) for c in result.findings]}"
    )


def test_the_answer_does_not_depend_on_the_interpreters_hash_seed():
    """The same corpus must give the same findings in every process. It did not.

    `AccountProfile.features` is a set of dataclasses whose fields are strings, so it iterates in an
    order that depends on `hash(str)`, which Python randomises per process. `shuffle_corpus` built
    its edge list by walking that set and then indexed into the list with a seeded RNG, so one seed
    produced a DIFFERENT shuffle in every process. Every shuffle in the null is built that way, so
    the correction threshold became a function of the interpreter rather than of the data.

    Measured before the fix, one corpus and one seed across three hash seeds: thresholds of 8.505,
    8.02 and 0.0. A threshold of 0.0 accepts every candidate, which removes the search correction
    this module exists for, and it is why the falsification test above failed about one run in five
    and was read as flakiness.

    Run as subprocesses because PYTHONHASHSEED is fixed at interpreter start and cannot be changed
    from inside a running one. That makes this the slowest test in the file and the only one that
    can see the bug at all.
    """
    import json
    import subprocess
    import sys as _sys

    program = (
        "import sys; sys.path.insert(0, %r)\n"
        "import netdetect_corpora as C\n"
        "from app.netdetect import Corpus, detect\n"
        "from app.netdetect.features import profile_from_commenter\n"
        "from app.netdetect.shuffle import shuffle_corpus\n"
        "rows = C.organic_population(50) + C.planted_operation(8, discipline=0.0)\n"
        "c = Corpus([profile_from_commenter(r) for r in rows])\n"
        "r = detect(shuffle_corpus(c, seed=4242), shuffles=24)\n"
        "import json; print(json.dumps({'n': len(r.findings), 't': round(r.null_threshold or 0, 6)}))\n"
    ) % str(Path(__file__).resolve().parent)

    seen = []
    for hash_seed in ("1", "3", "7"):
        out = subprocess.run(
            [_sys.executable, "-c", program],
            capture_output=True, text=True, check=True,
            env={"PYTHONHASHSEED": hash_seed, "PATH": "/usr/bin:/bin", "HOME": "/tmp"},
        )
        seen.append(json.loads(out.stdout.strip().splitlines()[-1]))

    assert seen[0] == seen[1] == seen[2], (
        f"the detector's answer moved with the interpreter's hash seed: {seen}"
    )
    # And the correction is actually doing something, so this cannot pass by everything being zero.
    assert seen[0]["t"] > 0.0


def test_the_shuffle_preserves_both_degree_sequences_exactly():
    """The null is only valid if the shuffle changes nothing except the wiring.

    A shuffle that let degrees drift would destroy the very structure the null exists to hold fixed,
    and everything real would then look significant against it.
    """
    before = _corpus(C.organic_population(30))
    after = shuffle_corpus(before, seed=7)

    assert sorted(before.account_degree.values()) == sorted(after.account_degree.values())
    b = sorted(len(v) for v in before.feature_accounts.values())
    a = sorted(len(v) for v in after.feature_accounts.values())
    assert b == a
    assert before.total_edges == after.total_edges


def test_too_few_shuffles_refuses_instead_of_silently_finding_nothing():
    """The bug this pins was live during development and is the worst kind.

    With K shuffles the smallest reportable p-value is 1/(K+1). Asked for p<=0.05 with K=8, the
    detector could never report anything whatever the data held, and the output was indistinguishable
    from a clean corpus. A detector that cannot possibly fire must say so.
    """
    corpus = _corpus(C.organic_population(40) + C.planted_operation(8))
    result = detect(corpus, shuffles=8, quantile=0.95)

    assert result.refused is not None
    assert not result.looked
    assert "1/(K+1)" in result.refused or "cannot express" in result.refused


# =============================================================================================== #
# 2. Controls. Real populations that a naive detector calls a bot network.
# =============================================================================================== #
def test_an_ordinary_population_produces_no_findings():
    result = detect_from_commenters(C.organic_population(60), shuffles=SHUFFLES)
    assert result.looked
    assert result.findings == []


def test_a_fan_community_is_not_reported():
    """Fans share vocabulary, share targets and joined when the thing launched.

    They are also, decisively, TALKING TO EACH OTHER. Mutual conversation is the signature of a
    community and the opposite of a broadcast formation, and a detector that counts in-group replies
    as coordination evidence inverts the signal on exactly the population most at risk of being
    wrongly accused.
    """
    rows = C.organic_population(60) + C.fan_community(12)
    result = detect_from_commenters(rows, shuffles=SHUFFLES)

    published = [c for c in result.findings
                 if _members_from(c, "fan") >= 3 and not c.needs_adjudication]
    assert published == [], "a fan community was published as a coordinated network"


def test_a_professional_beat_is_never_published_without_review():
    """Ten reporters on one story share a topic, a working day and a newsroom tool.

    That is statistically rare and completely innocent, and no threshold can tell it from an
    operation. So the detector must not publish it. It may flag it for a reader, which is the only
    thing that can actually make the call.
    """
    rows = C.organic_population(60) + C.professional_beat(10)
    result = detect_from_commenters(rows, shuffles=SHUFFLES)

    for c in result.findings:
        if _members_from(c, "press") >= 3:
            assert c.needs_adjudication, (
                "a newsroom was published as a coordinated network without review"
            )
            assert c.hard_evidence < 3.0


def test_the_scanned_post_is_never_evidence():
    """Every commenter engaged the scanned post by construction.

    Counting it would hand a perfect feature to every account in the investigation and report the
    whole comment section as one enormous operation.
    """
    shared = "the_scanned_post"
    rows = C.organic_population(40)
    for r in rows:
        for a in r["recent_activity"]:
            a["parent_id"] = shared

    with_exclusion = detect_from_commenters(rows, exclude_context={shared}, shuffles=SHUFFLES)
    profiles = [profile_from_commenter(r, exclude_context={shared}) for r in rows]
    assert not any(
        f.kind == "target_post" and f.value == shared
        for p in profiles for f in p.features
    )
    assert with_exclusion.findings == []


# =============================================================================================== #
# 3. Recall, and the honest limit of it
# =============================================================================================== #
def test_a_sloppy_operation_is_caught_and_is_publishable():
    rows = C.organic_population(60) + C.planted_operation(8, discipline=0.0)
    result = detect_from_commenters(rows, shuffles=SHUFFLES)

    hits = [c for c in result.findings if _members_from(c, "op") >= 6]
    assert hits, f"planted operation missed; found {[(c.size, c.score) for c in result.findings]}"

    hit = hits[0]
    assert hit.needs_adjudication is None, "a clear operation should not need review"
    # The two families a profession or a fandom does not produce: how the accounts were MADE, and
    # what OUTSIDE targets they converge on.
    assert hit.by_family.get("identity", 0) > 0
    assert hit.by_family.get("network", 0) > 0
    assert hit.corrected_p is not None and hit.corrected_p <= 0.05


def test_the_finding_carries_checkable_evidence():
    """A published claim about named people needs a line a reviewer can verify.

    The same standard the analyst's prose is held to: if you cannot quote it, you cannot claim it.
    """
    rows = C.organic_population(60) + C.planted_operation(8, discipline=0.0)
    result = detect_from_commenters(rows, shuffles=SHUFFLES)
    hit = next(c for c in result.findings if _members_from(c, "op") >= 6)

    assert hit.evidence
    for e in hit.evidence[:5]:
        assert e.sentence and e.corpus_count > 0
        assert e.shared_by >= 2
        # The denominator is in the sentence, so the rarity claim can be checked rather than trusted.
        assert str(e.corpus_count) in e.sentence


@pytest.mark.parametrize("discipline,expected", [(0.0, True), (0.25, True), (1.0, False)])
def test_the_dilution_curve_is_the_honest_product_claim(discipline, expected):
    """How well-run an operation can be before this goes blind.

    A disciplined operation (aged accounts, individually written posts, ordinary clients, human
    handles) shares no rare features, and no amount of statistics recovers a signal that was never
    emitted. That is a limit to state in the product, not a bug to tune away.
    """
    rows = C.organic_population(60) + C.planted_operation(8, discipline=discipline, seed=5)
    result = detect_from_commenters(rows, shuffles=SHUFFLES)
    found = any(_members_from(c, "op") >= 4 for c in result.findings)
    assert found is expected


# =============================================================================================== #
# 4. Properties that must not drift
# =============================================================================================== #
def test_the_same_input_always_gives_the_same_answer():
    """These are published claims about named accounts. A verdict that changes between runs is not
    a verdict."""
    rows = C.organic_population(50) + C.planted_operation(8, discipline=0.0)
    a = detect_from_commenters(rows, shuffles=SHUFFLES)
    b = detect_from_commenters(rows, shuffles=SHUFFLES)

    assert [(c.members, round(c.score, 6)) for c in a.findings] == \
           [(c.members, round(c.score, 6)) for c in b.findings]


def test_the_score_never_reads_an_accounts_own_suspicion_score():
    """Coordination and botness are orthogonal axes.

    A dense, improbable cluster of LOW-scoring accounts is the most valuable thing this system can
    find: the competent operation the old 70+ filter was blind to by construction. Multiplying the
    two would hide it, and would also let a pile of unrelated high scorers masquerade as one thing.
    """
    rows = C.organic_population(50) + C.planted_operation(8, discipline=0.0)

    for r in rows:
        r["omi_score"], r["tier"] = 5.0, "low"
    low = detect_from_commenters(rows, shuffles=SHUFFLES)
    for r in rows:
        r["omi_score"], r["tier"] = 95.0, "high"
    high = detect_from_commenters(rows, shuffles=SHUFFLES)

    assert [c.members for c in low.findings] == [c.members for c in high.findings]
    assert [round(c.score, 6) for c in low.findings] == [round(c.score, 6) for c in high.findings]


def test_a_tiny_corpus_refuses_rather_than_guessing():
    """Below a real corpus the shuffle has too few edges to rewire, so the maxima collapse and
    everything looks significant. Refusing is the honest answer."""
    result = detect_from_commenters(C.organic_population(10), shuffles=SHUFFLES)
    assert result.refused is not None
    assert not result.looked


# =============================================================================================== #
# 5. Components
# =============================================================================================== #
class TestPoissonBinomial:
    def test_matches_the_binomial_when_every_probability_is_equal(self):
        from math import comb

        p, n, k = 0.3, 8, 5
        expect = sum(comb(n, j) * p ** j * (1 - p) ** (n - j) for j in range(k, n + 1))
        assert _poisson_binomial_tail([p] * n, k) == pytest.approx(expect, rel=1e-9)

    def test_edges(self):
        assert _poisson_binomial_tail([0.5, 0.5], 0) == 1.0
        assert _poisson_binomial_tail([0.5, 0.5], 3) == 0.0
        assert _poisson_binomial_tail([1.0, 1.0], 2) == pytest.approx(1.0)


class TestHandleSkeleton:
    def test_a_real_template_is_recognised(self):
        assert handle_skeleton("crypto_mike_8821") == handle_skeleton("crypto_dave_4417")

    def test_a_single_word_handle_is_not_a_template(self):
        """Letter runs cap at 9, so three unrelated one-word handles would all reduce to the same
        skeleton and be reported as sharing a convention they do not share."""
        for h in ("marchingfern", "quietwaterbird", "brightpennylane"):
            assert handle_skeleton(h) is None

    def test_the_platforms_own_auto_append_is_not_a_template(self):
        """A word followed by digits is what a platform hands you when your name is taken. It is a
        fact about the platform, not about the operator."""
        assert handle_skeleton("jsmith8821") is None
        assert handle_skeleton("dave1234") is None


class TestTimingFeatures:
    def test_too_little_history_produces_no_rhythm_claim(self):
        from datetime import datetime, timedelta, timezone

        base = datetime(2026, 1, 1, tzinfo=timezone.utc)
        assert timing_features([base, base + timedelta(hours=1)]) == set()

    def test_a_scheduler_and_a_human_do_not_share_an_hour_profile(self):
        from datetime import datetime, timedelta, timezone

        base = datetime(2026, 1, 1, 3, tzinfo=timezone.utc)
        bot = [base + timedelta(minutes=62 * i) for i in range(40)]
        human = [base.replace(hour=9) + timedelta(days=i // 3, minutes=97 * i) for i in range(40)]

        bot_hours = {f.value for f in timing_features(bot) if f.kind == "active_hours"}
        human_hours = {f.value for f in timing_features(human) if f.kind == "active_hours"}
        assert bot_hours and human_hours and bot_hours != human_hours


class TestInternalReplyRatio:
    def test_a_conversation_scores_high_and_a_broadcast_scores_low(self):
        chatty = _corpus(C.fan_community(12))
        ratio = internal_reply_ratio(chatty, [a.external_id for a in chatty.accounts])
        assert ratio > 0.5

        broadcast = _corpus(C.planted_operation(8, discipline=0.0))
        assert internal_reply_ratio(
            broadcast, [a.external_id for a in broadcast.accounts]) == 0.0


class TestCandidates:
    def test_communities_are_member_disjoint(self):
        corpus = _corpus(C.organic_population(50) + C.planted_operation(8))
        seen: set[str] = set()
        for group in communities(corpus):
            assert not (seen & set(group)), "overlapping candidates inflate the search space"
            seen |= set(group)

    def test_a_group_needs_at_least_three_accounts(self):
        corpus = _corpus(C.organic_population(40))
        assert all(len(g) >= 3 for g in communities(corpus))


class TestScoring:
    def test_a_group_of_one_scores_nothing(self):
        corpus = _corpus(C.organic_population(30))
        assert score_candidate(corpus, [corpus.accounts[0].external_id]).score == 0.0

    def test_within_family_evidence_is_discounted_not_summed(self):
        """Fifty shingles from one copy-pasted post is one observation seen fifty times.

        Harmonic weighting keeps the score monotone (more evidence never hurts) while refusing to
        let a single copy-paste accumulate unbounded certainty.
        """
        from app.netdetect.significance import _harmonic_sum

        assert _harmonic_sum([6.0] * 10) < 10 * 6.0
        assert _harmonic_sum([6.0] * 10) > _harmonic_sum([6.0] * 3)
        assert _harmonic_sum([6.0]) == pytest.approx(6.0)


# =============================================================================================== #
# Reposts as network evidence.
#
# `repost_of_id` has always been collected and has always been read by the cohort detector; this
# reader took parents and replies only, so an operation whose members amplify the same outside post
# left NO network evidence. That is the family weighted 1.00 and one of the two whose innocent
# sharing is implausible, so losing it is the difference between a publishable finding and one that
# has to go to a human.
# =============================================================================================== #


def test_two_accounts_amplifying_the_same_outside_post_share_network_evidence():
    from app.netdetect.features import network_features

    a = network_features([], [], exclude=set(), reposts=["outside_1", "outside_2"])
    b = network_features([], [], exclude=set(), reposts=["outside_1"])
    shared = a & b
    assert shared, "amplifying the same post is engagement and has to register as such"
    assert all(f.family == "network" for f in shared)


def test_a_repost_is_kept_distinct_from_a_reply_to_the_same_post():
    # Two accounts that both REPOSTED X and two that both REPLIED under X are different claims, and
    # the evidence sentence a reader sees has to be able to say which.
    from app.netdetect.features import network_features

    reposted = network_features([], [], exclude=set(), reposts=["X"])
    replied = network_features([], ["X"], exclude=set())
    assert reposted != replied
    assert {f.kind for f in reposted} == {"repost_of"}
    assert {f.kind for f in replied} == {"reply_to"}


def test_reposting_the_scanned_post_is_excluded_like_every_other_engagement():
    # Every commenter engaged the scanned post by construction. Counting a repost of it would hand
    # a perfect feature to the whole comment section, which is the single most important exclusion
    # in that file.
    from app.netdetect.features import network_features

    assert network_features([], [], exclude={"the_post"}, reposts=["the_post"]) == set()


def test_a_pure_repost_ring_is_still_refused_for_want_of_a_second_family():
    """Reposts are evidence, not a licence. One family is never enough, and that must not change.

    Amplification alone is one kind of observation seen many times, and `MIN_FAMILIES` exists
    precisely to refuse that. Pinned so a future change cannot make the network family a shortcut
    past convergence.
    """
    from app.netdetect.detect import MIN_FAMILIES

    assert MIN_FAMILIES >= 2
    rows = C.organic_population(50) + C.amplifier_ring(8)
    for i, row in enumerate(rows):
        # Strip the shared tool, AND give every account text nobody else could share, leaving
        # amplification as the only thing the ring has in common.
        #
        # THE SECOND HALF WAS MISSING AND THE TEST WAS PASSING ON LUCK. `_sentence` draws from a
        # pool of eight topics, so unrelated accounts genuinely share five-word shingles at a
        # measured rate of about 14 in 58, and the ring shared them with the organic background
        # like everybody else. Louvain then attached organic accounts to the ring, their shingles
        # supplied a second family, and the candidate cleared `MIN_FAMILIES` without any coherent
        # group having two kinds of evidence.
        #
        # Measured against the tree before this test was fixed, over six organic backgrounds: the
        # ring was admitted in FIVE. This test passed because the default background happened to
        # be the sixth. It was asserting a property the detector does not have.
        row["recent_activity"] = [
            {**p, "source_client": None, "text": f"account {i} note {j} about nothing in particular"}
            for j, p in enumerate(row["recent_activity"])
        ]
        row["bio"] = f"bio belonging only to account {i}"
    result = detect(_corpus(rows), shuffles=SHUFFLES)
    assert not [c for c in result.findings if _members_from(c, "amp") >= 4]


def test_an_amplifier_ring_is_now_reachable_where_it_previously_left_no_evidence():
    """A shared tool plus shared amplification: two families, one of them hard.

    Without the reposts this group shares only a publishing client, which is one soft family and
    cannot be reported. The amplification is what turns it into a finding.
    """
    rows = C.organic_population(50) + C.amplifier_ring(8)
    result = detect(_corpus(rows), shuffles=SHUFFLES)

    assert result.looked, result.refused
    caught = [c for c in result.findings if _members_from(c, "amp") >= 4]
    assert caught, "shared amplification plus a shared tool should be reachable"
    # And the network family is carrying part of it rather than the tool doing all the work.
    assert any(c.by_family.get("network", 0) > 0 for c in caught)


def test_without_the_amplification_the_same_group_can_only_go_to_a_human():
    """The counterfactual, and it is more interesting than "it disappears".

    Same accounts, same text, same timing, same publishing client, with only the amplification not
    recorded. The group is still reachable, because a shared tool is a real statistical observation,
    but it rests on NO hard family, so it comes back carrying `needs_adjudication` and contaminated
    with organic accounts that happen to share the pattern.

    That is the whole value of reading reposts: it is the difference between a finding a reader has
    to arbitrate and one the evidence settles.
    """
    rows = C.organic_population(50) + C.amplifier_ring(8, reposts=False)
    without = detect(_corpus(rows), shuffles=SHUFFLES)

    blind = [c for c in without.findings if _members_from(c, "amp") >= 4]
    for candidate in blind:
        assert candidate.needs_adjudication, (
            "with no hard family this cannot be published on the evidence alone"
        )

    withheld = detect(_corpus(C.organic_population(50) + C.amplifier_ring(8)), shuffles=SHUFFLES)
    caught = [c for c in withheld.findings if _members_from(c, "amp") >= 4]
    assert caught
    assert any(c.needs_adjudication is None for c in caught), (
        "amplification is a hard family, so it should settle what the shared tool could not"
    )


# =============================================================================================== #
# The narrative family, which was declared and empty.
#
# `FAMILY_NARRATIVE` has been in the weight map at 0.45 since the module was written, with a note
# saying "once real embeddings land". Nothing ever produced it, so netdetect had five live families
# rather than six and the paraphrase axis was missing entirely.
# =============================================================================================== #


def test_topic_ids_produce_narrative_evidence():
    from app.netdetect.features import topic_features

    feats = topic_features([11, 12], exclude=set())
    assert {f.family for f in feats} == {"narrative"}
    assert sorted(f.value for f in feats) == ["11", "12"]


def test_the_topic_the_cohort_was_assembled_on_is_excluded():
    """Whatever you selected the group BY cannot also be evidence about the group.

    Every member spoke on the cohort's topic by construction. Counting it would hand a perfect
    feature to the whole cohort and report a topic's entire population as one operation, which is
    the same trap as the scanned post in `network_features`.
    """
    from app.netdetect.features import topic_features

    assert topic_features([7], exclude={"7"}) == set()
    assert {f.value for f in topic_features([7, 9], exclude={"7"})} == {"9"}


def test_the_per_scan_path_stays_silent_rather_than_faking_a_topic():
    """A single investigation has no topic assignment, so the family produces nothing there.

    Deliberate: the honest alternative to "no topic evidence" is no topic evidence, not a lexical
    proxy, which the text family already covers and which would double-count the same observation
    under two family weights.
    """
    row = {
        "external_id": "a1", "platform": "x", "handle": "a1",
        "recent_activity": [{"text": "a post about something", "created_at": "2026-01-01T00:00:00Z"}],
        "thread_comments": [],
    }
    profile = profile_from_commenter(row)
    assert not [f for f in profile.features if f.family == "narrative"]


def test_narrative_evidence_cannot_carry_a_finding_on_its_own():
    """Soft by design: a shared topic is the most innocently shared thing there is.

    It can add to convergence and must never be the whole case, which is what the weight and the
    two-family rule together guarantee.
    """
    from app.netdetect.types import FAMILY_WEIGHT, HARD_FAMILIES

    assert FAMILY_WEIGHT["narrative"] < FAMILY_WEIGHT["network"]
    assert FAMILY_WEIGHT["narrative"] < FAMILY_WEIGHT["identity"]
    assert "narrative" not in HARD_FAMILIES


# =============================================================================================== #
# 6. Contamination: who ELSE ends up named
# =============================================================================================== #
#
# The recall tests above ask whether the planted operation was found. They pass at `>= 4 of 8`, and
# no test anywhere asked the other question: WHO ELSE is in the finding. That matters more here than
# recall does, because a finding names real people. An innocent account swept into one is the exact
# harm this package's refusals, family weights and adjudication flag all exist to avoid, and it was
# going unmeasured.
#
# It became worth pinning when findings started being RECORDED. A swept-in account used to evaporate
# when the page closed; it now lands in an operator's queue as a member of an operation and its
# pairs are folded into the accumulating graph. The consequence changed even though the numbers did
# not (measured identical against the pre-persistence tree).
#
# MEASURED 2026-08-28 across the full grid below: recall 8/8 on every one of the twelve
# configurations, and 7 innocent accounts across 103 named members, so about 6.8%. Seven of the
# twelve findings are clean and the worst single one is 3 innocents among 11 members.
#
# THE GRID IS SYSTEMATIC, every background size against every seed, and it has to stay that way. An
# earlier draft trimmed it to six configurations and the trim happened to keep most of the
# contaminated ones, which reported 12.7% and would have baselined every future change against a
# number produced by the selection rather than by the detector.
#
# THIS IS A CEILING, NOT A TARGET. It is here so that a change which makes contamination worse
# cannot land silently behind a recall test that still passes.

CONTAMINATION_GRID = [(organic, seed) for organic in (30, 40, 50, 60) for seed in (5, 11, 23)]

#: Share of all named members, across the grid, that may be innocent. Measured 6.8%; the headroom
#: is for seed noise, not for regression.
MAX_CONTAMINATION_RATE = 0.10

#: No single finding may be more than this much bystander. A finding that is half innocent is not a
#: slightly noisy finding, it is a different claim about different people.
MAX_PER_FINDING_SHARE = 0.40


def test_a_finding_is_mostly_the_operation_and_the_rate_is_pinned():
    """Recall was measured and purity was not. Both are claims about named real people."""
    named = innocent = 0
    per_finding: list[tuple[int, int]] = []

    for organic, seed in CONTAMINATION_GRID:
        rows = C.organic_population(organic, seed=seed) + C.planted_operation(
            8, seed=seed + 1, discipline=0.0)
        result = detect_from_commenters(rows, shuffles=SHUFFLES)
        hits = [c for c in result.findings if _members_from(c, "op") >= 4]
        assert hits, f"the operation was not found at organic={organic} seed={seed}"

        for c in hits:
            org = sum(1 for m in c.members if m.startswith("org"))
            named += len(c.members)
            innocent += org
            per_finding.append((org, len(c.members)))

            assert _members_from(c, "op") == 8, (
                f"recall dropped at organic={organic} seed={seed}: "
                f"{_members_from(c, 'op')} of 8"
            )

    worst = max(org / total for org, total in per_finding)
    assert worst <= MAX_PER_FINDING_SHARE, (
        f"one finding is {worst:.0%} bystanders; at that point it is a claim about different people"
    )

    rate = innocent / named
    assert rate <= MAX_CONTAMINATION_RATE, (
        f"{innocent} innocent accounts among {named} named ({rate:.1%}), above the pinned "
        f"{MAX_CONTAMINATION_RATE:.0%}. A recall test cannot see this, which is why it is here."
    )


def test_attachment_weight_is_still_not_publishable_as_a_per_member_confidence():
    """A GUARD AGAINST A TEMPTING AND WRONG FEATURE, AND A RECORD OF WHY IT IS STILL WRONG.

    `pair_evidence_from` knows how much of a group's shared evidence each member participates in, so
    it is very tempting to publish that as a per-member confidence and let a reviewer challenge one
    name. The cohort detector does exactly that with its admitting posterior, and it is right to.

    THE MEASUREMENT MOVED, AND THIS TEST NO LONGER ASSERTS WHAT IT USED TO. It previously asserted
    that the naive statistic ranks at least one bystander ABOVE a genuine member, which was true on
    the corpus it used. After mentions and hashtags were added, genuine members share more evidence
    with each other, and across every contaminated corpus that could be built here (organic seed 5
    with operation seed 99, and organic seed 4 with operation seed 11) the naive statistic separated
    cleanly: every bystander below every member.

    THAT IS NOT ENOUGH TO SHIP IT, and the reason is arithmetic rather than caution. Two corpora
    holding two bystanders each is not a basis for putting a number beside a named real person,
    which is what publishing this would do. `attachment.py` exists because a DIFFERENT statistic,
    leave-one-out set surprise, was measured over a systematic grid at 7 of 7 bystanders flagged
    and 0 of 96 genuine members, and even that ships as a FLAG rather than a number.

    So this test now guards the thing that matters and can be asserted: no per-member number
    reaches any response. What would make the feature buildable is a systematic grid like
    `attachment.py`'s, not a green test on two corpora.
    """
    import inspect

    from app.netdetect import persist
    from app.routes import netdetect as netdetect_routes

    # The statistic that DOES work ships as a flag. A response carrying a float per member would be
    # read as a judgement about a person, which is the whole objection.
    source = inspect.getsource(netdetect_routes)
    assert "weakly_attached" in source
    for forbidden in ("attachment_score", "member_confidence", "attachment_weight"):
        assert forbidden not in source, (
            f"{forbidden} reached a response. The working statistic is deliberately published as a "
            f"flag and the naive one is not published at all; see this test and "
            f"app/netdetect/attachment.py."
        )

    # And nothing in the package turns `pair_evidence_from` into a per-member ranking for a reader.
    assert not [n for n in dir(persist) if "confidence" in n or n.startswith("member_")], (
        "persist grew a per-member confidence helper"
    )


# ==================================================================================================
# Mentions and hashtags: the narrative family on the per-scan path
# ==================================================================================================
def test_a_mention_is_narrative_and_never_hard_evidence():
    """THE MEASUREMENT THAT DECIDED WHICH FAMILY A MENTION BELONGS TO.

    Mentions were first written into `network_features` beside `reply_to` / `target_post` /
    `repost_of`, on the reasoning that converging on an outside target is the operator's own act.
    `network` is weighted 1.00 and sits in `HARD_FAMILIES`, so a shared @ became enough to clear
    `MIN_HARD_EVIDENCE`.

    Measured immediately, the professional-beat control went from flagged-for-adjudication to
    PUBLISHABLE: hard evidence 7.50 against a floor of 3.0, on ten reporters all naming
    `@stadiumauthority`. That is an accusation about real journalists, and no threshold would have
    caught it because the finding was statistically real.

    A repost is a structural act the platform recorded. A mention is a name inside a sentence, and
    naming somebody is about SUBJECT. So it is narrative, weighted 0.45 and deliberately not hard.
    """
    from app.netdetect.features import subject_features
    from app.netdetect.types import FAMILY_NARRATIVE, HARD_FAMILIES

    feats = subject_features(["angry at @stadiumboss about #stopthestadium"], exclude=set())
    kinds = {f.kind for f in feats}
    assert kinds == {"mentions", "hashtag"}
    assert all(f.family == FAMILY_NARRATIVE for f in feats)
    assert FAMILY_NARRATIVE not in HARD_FAMILIES, (
        "narrative became a hard family, which would make a shared @ or tag enough to publish a "
        "finding about a newsroom covering one beat"
    )


def test_the_newsroom_control_is_still_flagged_for_review_when_it_names_the_same_officials():
    """The control that decides whether mention and tag features can ship at all.

    Reporters on one beat converge on the same officials and the same hashtag, innocently. The
    finding is statistically real and must reach a person rather than a customer.
    """
    rows = C.organic_population(60, seed=7) + C.professional_beat(10, seed=21)
    result = detect_from_commenters(rows, shuffles=SHUFFLES)
    for finding in result.findings:
        if sum(1 for m in finding.members if m.startswith("press")) < 4:
            continue
        assert finding.needs_adjudication, (
            "the newsroom control became publishable without review; a shared mention or tag is "
            "being counted as the operator's own act"
        )


def test_a_mention_of_another_member_is_not_convergence_on_an_outside_target():
    """A mention names a HANDLE, not an external id, so the member set does not exclude it.

    Adding "mentions" to the in-group tuple in `score_candidate` would silently exclude nothing,
    and a group that @s each other by handle would read as convergence on an outside target: the
    exact inversion the in-group rule exists to prevent, on a real community.
    """
    import inspect

    from app.netdetect import significance

    source = inspect.getsource(significance.score_candidate)
    assert "inside_handles" in source, "the by-handle exclusion for mentions is gone"
    assert 'f.kind == "mentions" and f.value in inside_handles' in source


def test_an_email_address_is_not_a_mention_and_a_bare_number_is_not_a_tag():
    from app.netdetect.features import hashtags_in, mentions_in

    assert mentions_in(["write to foo@bar.com about it"]) == set()
    assert mentions_in(["hey @alice and @Bob_2"]) == {"alice", "bob_2"}
    assert hashtags_in(["#1 #2026 costs"]) == set(), "a digits-only tag is a number, not a subject"
    assert hashtags_in(["#budget2026 #StopIt"]) == {"budget2026", "stopit"}


def test_the_narrative_family_is_no_longer_empty_on_an_ordinary_scan():
    """`topic_features` needs assignments only the cross-investigation pass produces, so before
    mentions and tags an ordinary scan ran with five families while `MIN_FAMILIES` counts them."""
    from app.netdetect.features import profile_from_commenter
    from app.netdetect.types import FAMILY_NARRATIVE

    rows = C.planted_operation(8, discipline=0.0, seed=99)
    profiles = [profile_from_commenter(r) for r in rows]
    assert any(f.family == FAMILY_NARRATIVE for p in profiles for f in p.features), (
        "the narrative family is empty on the per-scan path again"
    )


# ==================================================================================================
# Co-arrival under the scanned post
# ==================================================================================================
def test_co_arrival_strengthens_a_push_that_lands_together():
    """`thread_comments` timestamps were POOLED into the account's own rhythm and never compared
    between accounts, so nothing here could say "these eight arrived inside the same three minutes".

    That is a different claim from `timing_features`' rhythm: two accounts posting at 14:03 on
    unrelated days is nothing; two accounts arriving at 14:03 under the SAME post is the evidence.
    """
    rows = C.organic_population(60, seed=7) + C.planted_operation(8, seed=99, discipline=0.0)
    result = detect_from_commenters(rows, shuffles=SHUFFLES)
    hit = next(c for c in result.findings if _members_from(c, "op") >= 4)

    arrivals = [e for e in hit.evidence if e.feature.kind == "arrival"]
    assert arrivals, "the co-arrival feature contributed nothing to a push that landed together"
    assert any(e.shared_by >= 4 for e in arrivals)
    assert all(e.feature.family == "timing" for e in arrivals)


def test_a_viral_post_produces_nothing():
    """THE FAILURE MODE CO-ARRIVAL IS BUILT AROUND, and it took two attempts to get right.

    On a post drawing sixty comments in four minutes, ANY small group shares a window. Measured
    naively this is the worst false-positive generator available.

    The first design leaned on rarity alone: a window is a feature, and features held by most of
    the corpus are dropped before scoring. That fixed the dense middle of a burst and NOT its
    sparse tails, which still produced windows holding three or four accounts. Measured: a viral
    background went from 0 findings to 1.

    The second design scaled the windows to the post's own median gap. That fixed the tails and
    created a subtler failure, because constant occupancy cuts both ways: if a window holds about
    four accounts on any post, "shared a window" is equally unsurprising everywhere and rarity can
    no longer tell a push from a slice of a burst. Worse, the candidate generator groups accounts BY
    the window and the scorer then scores them ON it. Measured: one viral background in eight
    produced a fourteen-account finding carrying `timing: 11.13`, entirely arrival-driven.

    What works is the ratio: an arrival emits nothing unless its neighbourhood is denser than the
    thread's own average by `ARRIVAL_BURST_RATIO`. Measured 0 false positives across eight
    backgrounds, with recall 8 of 8 on the sloppy operation.
    """
    rows = C.organic_population(60, seed=7, viral=True)
    result = detect_from_commenters(rows, shuffles=SHUFFLES)
    assert result.findings == [], (
        "a viral post reported a finding; co-arrival is firing on density rather than coordination"
    )


def test_strangers_forced_into_one_window_are_never_published():
    """The most adversarial co-arrival available: eight unrelated accounts forced inside a
    twenty-second window on an already-busy post, tighter than the planted operation's own push.

    THE STANDARD HERE IS "NEVER PUBLISHED", NOT "NEVER FOUND", and that is the same standard the
    professional-beat control is held to rather than a softer one invented for this feature. A group
    of strangers who genuinely did arrive together is a real statistical fact; what makes it not an
    operation is that they share none of the operator's own acts, so `MIN_HARD_EVIDENCE` sends it to
    a person instead of to a customer.

    Measured across eight backgrounds: 0 publishable, 1 flagged for review. Forcing the burst also
    perturbs the density estimate the burst test uses, which is why the one finding that appears is
    not even mostly the forced accounts (2 of 8).
    """
    import random

    published = []
    for seed in (7, 3, 4, 5, 6, 8):
        rows = C.organic_population(60, seed=seed, viral=True)
        rng = random.Random(4242)
        for row in rows[:8]:
            row["thread_comments"] = C._thread(rng, spread_seconds=20, centre_offset=100)

        result = detect_from_commenters(rows, shuffles=SHUFFLES)
        published += [f for f in result.findings if not f.needs_adjudication]

    assert published == [], (
        "a burst of strangers became publishable without review; co-arrival is being treated as "
        "the operator's own act rather than as the soft timing evidence it is"
    )


def test_a_fandom_arriving_on_a_drop_is_not_a_finding():
    """A fandom watching for a drop arrives inside minutes for entirely innocent reasons, and no
    threshold elsewhere would catch it because the co-arrival is real."""
    rows = C.organic_population(60, seed=7) + C.fan_community(12, seed=33)
    result = detect_from_commenters(rows, shuffles=SHUFFLES)
    assert not [c for c in result.findings if _members_from(c, "fan") >= 4]


def test_co_arrival_goes_quiet_rather_than_loud_when_it_cannot_discriminate():
    """An operation arriving INSIDE a viral burst is still found, and NOT by co-arrival.

    This is the property that makes the feature safe: where every account shares the windows the
    arrival evidence is not rare, so it drops out entirely and the finding rests on the operation's
    other families. A feature that fired here would be reporting the post's popularity.
    """
    import random

    rng = random.Random(4242)
    operation = C.planted_operation(8, seed=99, discipline=0.0)
    for row in operation:
        row["thread_comments"] = C._thread(rng, spread_seconds=180, centre_offset=30)

    rows = C.organic_population(60, seed=7, viral=True) + operation
    result = detect_from_commenters(rows, shuffles=SHUFFLES)
    hit = next((c for c in result.findings if _members_from(c, "op") >= 4), None)
    assert hit is not None, "the operation became invisible on a busy post"
    assert not [e for e in hit.evidence if e.feature.kind == "arrival"], (
        "co-arrival contributed on a post where every account shares the windows"
    )


def test_the_half_offset_grid_catches_a_burst_across_a_bucket_boundary():
    """Fixed buckets lose a burst that straddles an edge, and which side it falls on is an accident
    of where the epoch happens to sit rather than a fact about the accounts."""
    from datetime import datetime, timedelta, timezone

    from app.netdetect.features import arrival_features

    # A thread that clusters around noon and then trickles, so the burst test admits these.
    noon = datetime(2026, 3, 1, 12, 0, 0, tzinfo=timezone.utc)
    everyone = ([noon + timedelta(seconds=x) for x in (-4, -2, -1, 0, 1, 2, 4)]
                + [noon + timedelta(hours=h) for h in range(1, 12)])
    scales = (60, 300)

    before = arrival_features([noon - timedelta(seconds=2)],
                              scales=scales, all_arrivals=everyone)
    after = arrival_features([noon + timedelta(seconds=3)],
                             scales=scales, all_arrivals=everyone)
    assert before, "the burst test rejected an arrival in the middle of a burst"
    assert before & after, "five seconds apart across a boundary shared no window at all"

    far = arrival_features([noon + timedelta(hours=6)], scales=scales, all_arrivals=everyone)
    assert not (before & far), "six hours apart shared a window"


def test_co_arrival_is_not_emitted_when_too_few_accounts_carry_arrivals():
    """THE DEGENERATE CASE. If five accounts have thread comments and three share a minute, the
    window reads as rare against the whole corpus while the only background that could judge it is
    those five arrivals. That is measuring nothing and reporting a finding."""
    from app.netdetect.features import MIN_ACCOUNTS_FOR_CO_ARRIVAL, profile_from_commenter

    rows = C.organic_population(60, seed=7)
    for row in rows[MIN_ACCOUNTS_FOR_CO_ARRIVAL - 1:]:
        row["thread_comments"] = []

    result = detect_from_commenters(rows, shuffles=SHUFFLES)
    assert result.corpus is not None
    assert not [
        f for p in result.corpus.by_id.values() for f in p.features if f.kind == "arrival"
    ], "co-arrival was emitted with too small an arrival population to judge it against"

    # And the per-account builder defaults to OFF, so a caller that forgets cannot turn it on by
    # accident on a corpus that cannot support it.
    assert not [f for f in profile_from_commenter(rows[0]).features if f.kind == "arrival"]


def test_co_arrival_reads_the_thread_and_never_the_accounts_own_timeline():
    """Co-timing is only evidence when both accounts were commenting on the same thing, which is
    the reason `thread_comments` is stored apart from `recent_activity` in the first place."""
    from app.netdetect.features import profile_from_commenter

    row = C.organic_population(1, seed=3)[0]
    row["thread_comments"] = []
    built = profile_from_commenter(row, arrival_windows=(60, 300), all_arrivals=[])
    assert not [f for f in built.features if f.kind == "arrival"], (
        "arrival features were produced from the account's own timeline with no thread comments"
    )


def test_co_arrival_shares_the_timing_family_so_it_cannot_inflate_the_family_count():
    """A scheduler produces both a machine rhythm and a tight arrival. Those are one kind of
    evidence seen twice, and `MIN_FAMILIES` counts families."""
    from datetime import datetime, timedelta, timezone

    from app.netdetect.features import arrival_features
    from app.netdetect.types import ALL_FAMILIES, FAMILY_TIMING

    noon = datetime(2026, 3, 1, 12, 0, 0, tzinfo=timezone.utc)
    everyone = ([noon + timedelta(seconds=x) for x in (-2, -1, 0, 1, 2)]
                + [noon + timedelta(hours=h) for h in range(1, 10)])
    feats = arrival_features([noon], scales=(60,), all_arrivals=everyone)
    assert feats
    assert {f.family for f in feats} == {FAMILY_TIMING}
    assert "arrival" not in ALL_FAMILIES, "co-arrival became a family of its own"


# =============================================================================================== #
# The sub-group hole in MIN_FAMILIES, measured rather than assumed
#
# `MIN_FAMILIES` is checked on the WHOLE candidate, and a candidate is a Louvain community rather
# than a chosen set. On paper that lets two DISJOINT sub-groups supply one family each and clear a
# gate meant to require two independent kinds of evidence ABOUT THE SAME PEOPLE. It has stood as
# the most interesting known weakness in the refusals, and a shared-core refusal built against it
# in an earlier session was measured to be a complete no-op and removed with no explanation of why.
#
# These build the shape deliberately and say why it does not arrive. The point is not that the
# corpus below is clean: it is that the two mechanisms named in the tests are what keep it clean,
# so a change to either has somewhere to fail.
# =============================================================================================== #
_CULVERT = "the drainage culvert on maple street has been open since february"


def _one_family_group(prefix: str, n: int, seed: int, *, text: bool = False, ident: bool = False):
    """Accounts sharing exactly ONE thing: a repeated line, or a signup week plus a handle template.

    Everything else is drawn per account, so a group built with `text=True` has no identity evidence
    at all and vice versa. That is what makes the two sub-groups disjoint in family support.
    """
    import random
    from datetime import timedelta

    rng = random.Random(seed)
    signup = C.BASE - timedelta(days=210)
    out = []
    for i in range(n):
        t = C.BASE - timedelta(days=rng.randint(1, 20))
        posts = []
        for j in range(16):
            t = t + timedelta(minutes=rng.randint(30, 500))
            posts.append(C._post(_CULVERT if (text and j % 3 == 0) else C._sentence(rng), t))
        out.append(C._account(
            f"{prefix}{i:03d}", posts=posts,
            created=(signup + timedelta(hours=i * 4)) if ident
            else C.BASE - timedelta(days=rng.randint(400, 2500)),
            handle=(f"riverwatch_{2200 + i * 7}" if ident
                    else f"{rng.choice(['mel', 'sam', 'ivy'])}{rng.randint(1000, 9999)}"),
        ))
    return out


def _family_support(corpus, candidate) -> dict[str, set[str]]:
    """family -> the members actually holding a feature that counted toward it."""
    members = set(candidate.members)
    out: dict[str, set[str]] = {}
    for ev in candidate.evidence:
        holders = corpus.feature_accounts.get(ev.feature, set())
        out.setdefault(ev.feature.family, set()).update(members & holders)
    return out


def test_two_sub_groups_with_nothing_in_common_are_never_merged_into_one_candidate():
    """THE FIRST MECHANISM, and the one that makes the hole hard to reach at all.

    Candidate generation builds its graph from SHARED rare features, so two groups with nothing in
    common have no edge between them and Louvain has nothing to merge them on. The pathological
    candidate is not refused later; it is never proposed.

    Measured: eight text-only accounts and eight identity-only accounts in one 76-account corpus
    land in different communities, the identity group is split across them so its family never
    reaches `MIN_FAMILY_CONTRIBUTION`, and the run reports nothing.
    """
    from app.netdetect.significance import MIN_FAMILY_CONTRIBUTION

    rows = (C.organic_population(60, seed=17)
            + _one_family_group("tx", 8, 301, text=True)
            + _one_family_group("id", 8, 401, ident=True))
    corpus = _corpus(rows)

    for members in communities(corpus):
        if not any(m.startswith(("tx", "id")) for m in members):
            continue
        c = score_candidate(corpus, members)
        carried = [f for f, v in c.by_family.items() if v >= MIN_FAMILY_CONTRIBUTION]
        support = _family_support(corpus, c)
        for fam in carried:
            for other in carried:
                if fam == other:
                    continue
                assert support.get(fam, set()) & support.get(other, set()), (
                    f"{fam} and {other} both carried this candidate and no member holds both; "
                    f"the sub-group hole in MIN_FAMILIES is reachable and must now be closed"
                )

    assert detect(corpus, shuffles=SHUFFLES).findings == []


def test_bridging_the_two_sub_groups_gives_the_candidate_a_real_shared_core():
    """THE SECOND MECHANISM. Merging them requires accounts that share with both, and those accounts
    ARE the shared core the gate is asking for, so the merged candidate is not the pathological
    case: some members genuinely hold evidence in both families.

    The set statistic also prices the dilution. A feature held by k of n members is measured against
    n, so the smaller sub-group's family is discounted for sitting inside a larger candidate:
    measured here at identity 2.33 against text 19.59, barely over the floor. `MIN_HARD_EVIDENCE`
    then flags the finding for adjudication rather than publishing it, which is the correct outcome
    for a group whose only hard evidence is three accounts' signup week.
    """
    from app.netdetect.significance import MIN_FAMILY_CONTRIBUTION

    rows = (C.organic_population(60, seed=17)
            + _one_family_group("tx", 8, 301, text=True)
            + _one_family_group("id", 8, 401, ident=True)
            + _one_family_group("hb", 3, 501, text=True, ident=True))
    corpus = _corpus(rows)
    result = detect(corpus, shuffles=SHUFFLES)

    merged = [c for c in result.findings if _members_from(c, "tx") and _members_from(c, "id")]
    assert merged, "the bridged corpus stopped producing the merged candidate this test is about"
    for c in merged:
        support = _family_support(corpus, c)
        carried = [f for f, v in c.by_family.items() if v >= MIN_FAMILY_CONTRIBUTION]
        assert len(carried) >= 2
        core = set.intersection(*(support.get(f, set()) for f in carried))
        assert core, "the merged candidate has no member holding evidence in every carried family"
        assert any(m.startswith("hb") for m in core), (
            "the bridging accounts, which are the reason these two groups were merged at all, "
            "are not among the members holding evidence in every carried family"
        )
        # The core is WIDER than the three bridges, and that is the topic pool rather than a bug:
        # `_sentence` draws from eight topics, so unrelated accounts genuinely share five-word
        # shingles at a measured rate (the same effect the repost-ring test above pays for). The
        # identity-only accounts therefore pick up incidental text support. Asserting the core is
        # EXACTLY the bridges would be asserting a property of the fixture's vocabulary.
        assert c.needs_adjudication, (
            "a group whose only hard evidence is three accounts' signup week was published"
        )
