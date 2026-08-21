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
