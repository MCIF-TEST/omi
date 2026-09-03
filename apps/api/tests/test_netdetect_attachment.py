"""Who in a finding is not carrying it, and when that question cannot be answered.

A netdetect finding names real people, and candidate generation is community detection, so a
finding can include an account that borders the group without belonging to it. That rate is
measured and pinned as a ceiling in `test_netdetect.py`; this suite covers the test that finally
identifies WHICH members those are.

THREE PROPERTIES CARRY THE MODULE, and two of them are about restraint:

* **It asks what a member ADDED, not how much it shares.** The sharing number was measured first and
  ranks some bystanders above genuine members (still pinned, in `test_netdetect.py`). Removing a
  genuine member drops the shared count across many rare features and the score falls; removing a
  bystander leaves that count alone while shrinking the group, so the score can rise.
* **The threshold is relative to the finding's own median.** Globally the two populations overlap:
  measured, the weakest genuine member scored -0.134 and the strongest bystander +0.116, so any
  fixed cut misclassifies one of them.
* **It abstains rather than guessing**, and it reports rather than excluding.
"""

from __future__ import annotations

import tests.netdetect_corpora as C
from app.netdetect import detect_from_commenters
from app.netdetect.attachment import (
    MAX_MEMBERS,
    MIN_CONTRIBUTION_GAP,
    MIN_MEDIAN_CONTRIBUTION,
    WEAK_FRACTION,
    assess,
    leave_one_out,
)

SHUFFLES = 20


#: Detection is the expensive part (seconds per corpus) and several tests below walk the same grid.
#: Cached per module so the grid is detected once rather than once per test, which took this file
#: from about three and a half minutes to under two.
#:
#: Safe only because the detector is deterministic, which is itself pinned
#: (`test_the_answer_does_not_depend_on_the_interpreters_hash_seed`). A cache in front of a
#: nondeterministic function would hide exactly the bug that test exists to catch.
_CACHE: dict[tuple[int, int], tuple] = {}


def _planted(organic: int, seed: int):
    """A grid corpus that ACTUALLY CONTAINS BYSTANDERS, which this whole file needs.

    `subject_noise=False` gives the sparse background this generator produced before mentions and
    hashtags existed. With the featureful background the measured contamination over this same grid
    is 0 of 96 named, so every test here would pass by having nothing to find, which is the failure
    mode `attachment.py` was written to avoid in the first place: a check that never looked reads
    exactly like a check that found nothing.

    The 0 of 96 is a property of the corpus and not an improvement in the detector: measured with
    the narrative feature disabled it is also 0 of 96. See `netdetect_corpora.organic_population`.
    """
    key = (organic, seed)
    if key not in _CACHE:
        rows = C.organic_population(
            organic, seed=seed, subject_noise=False, arrivals=False,
        ) + C.planted_operation(
            8, seed=seed + 1, discipline=0.0, subject_noise=False, arrivals=False)
        result = detect_from_commenters(rows, shuffles=SHUFFLES)
        hits = [c for c in result.findings if sum(1 for m in c.members if m.startswith("op")) >= 4]
        assert hits, f"the operation was not found at organic={organic} seed={seed}"
        _CACHE[key] = (result, hits[0])
    return _CACHE[key]


# ==================================================================================================
# It identifies the bystanders
# ==================================================================================================
def test_it_names_the_bystanders_a_finding_swept_in():
    """THE LOAD-BEARING TEST. This corpus puts three ordinary accounts into an eight-account
    operation, and until now nothing could say which three."""
    result, finding = _planted(60, 5)
    innocent = {m for m in finding.members if m.startswith("org")}
    assert len(innocent) == 3, "the corpus stopped being contaminated; the test proves nothing"

    attachment = assess(result.corpus, finding.members)
    assert attachment.answered, f"declined to answer: {attachment.abstained}"
    assert set(attachment.weak) == innocent


def test_no_genuine_member_is_ever_flagged_across_the_grid():
    """The mirror error, and the worse one. A wrongly flagged member is a real participant that a
    reader is invited to discount."""
    flagged_innocent = flagged_member = missed = 0
    for organic in (30, 40, 50, 60):
        for seed in (5, 11, 23):
            result, finding = _planted(organic, seed)
            innocent = {m for m in finding.members if m.startswith("org")}
            attachment = assess(result.corpus, finding.members)
            if not attachment.answered:
                # Abstaining is allowed; claiming a bystander that is not there is not.
                assert not attachment.weak
                continue
            weak = set(attachment.weak)
            flagged_innocent += len(weak & innocent)
            flagged_member += len(weak - innocent)
            missed += len(innocent - weak)

    assert flagged_member == 0, f"{flagged_member} genuine operation members were flagged"
    assert missed == 0, f"{missed} bystanders went unflagged"
    assert flagged_innocent >= 5, "the grid stopped exercising the contaminated case"


# ==================================================================================================
# The abstention, which is the honest half
# ==================================================================================================
def test_a_homogeneous_group_gets_no_verdict_rather_than_an_arbitrary_one():
    """When every member holds the same features, removing any one of them barely moves the score.
    There is no weak member to find, and a rule that went looking anyway would flag whichever
    account happened to round lowest."""
    seen = False
    for organic, seed in ((50, 5), (50, 23), (60, 23)):
        result, finding = _planted(organic, seed)
        assert not [m for m in finding.members if m.startswith("org")], "corpus changed"
        attachment = assess(result.corpus, finding.members)
        if attachment.answered:
            continue
        seen = True
        assert attachment.weak == []
        assert "equally" in attachment.abstained
        assert attachment.median < MIN_MEDIAN_CONTRIBUTION
    assert seen, "no homogeneous finding in the fixture; the abstention path went untested"


def test_it_abstains_on_a_contaminated_finding_whose_populations_do_not_separate():
    """Abstaining on a finding that HAS bystanders is correct when they are not distinguishable.

    The bimodality rule was measured on ring corpora built over organic seed 31, where it flags
    every bystander and no genuine member. On ring corpora whose background carries the ring's own
    seed the two populations overlap instead, and it names nobody. That looks like a miss and is the
    opposite of one.

    THE COUNTER-EXAMPLE IS WHAT MAKES THE POINT: here a bystander out-contributes genuine members of
    the ring, so any rule forced to produce a verdict would flag real operation members and clear the
    bystander. That is the failure the discarded MAX rule had, reached from the other direction. This
    asserts the overlap FIRST, so if a corpus change ever separates these populations the test says
    so instead of quietly passing on a premise that stopped being true.
    """
    ring = C.amplifier_ring(8, seed=61)
    ring_ids = {r["external_id"] for r in ring}
    rows = C.organic_population(40, seed=61) + ring
    result = detect_from_commenters(rows, shuffles=SHUFFLES)

    findings = [f for f in result.findings if len(set(f.members) & ring_ids) >= 4]
    assert findings, "the ring was not found, so this test has nothing to assess"

    checked = 0
    for finding in findings:
        members = set(finding.members)
        bystanders = members - ring_ids
        if not bystanders:
            continue
        attachment = assess(result.corpus, finding.members)
        contribution = attachment.contribution
        if not contribution:
            continue
        genuine = [v for m, v in contribution.items() if m in ring_ids]
        outside = [v for m, v in contribution.items() if m not in ring_ids]
        if not genuine or not outside:
            continue

        # THE PREMISE. If this ever fails the populations have separated and the abstention below is
        # no longer the right answer for this corpus.
        assert max(outside) > min(genuine), (
            "premise: on this corpus a bystander must out-contribute at least one genuine member, "
            "or there is a boundary to find and abstaining would be a miss rather than restraint"
        )

        checked += 1
        assert not attachment.answered, (
            "a verdict was reached on a finding whose populations overlap, so whoever it names was "
            "chosen by rounding rather than by evidence"
        )
        assert attachment.weak == [], "an abstention must name nobody"
        assert "equally" in (attachment.abstained or "")

    assert checked, "no contaminated finding was examined; the case went untested"


def test_the_finding_survives_without_the_members_this_test_flags():
    """THE MEASUREMENT THAT SAYS THE FALSE NAMING IS AVOIDABLE, not a cost of detection.

    `attachment` reports and never drops, and the rule is stated in the module as a deliberate one.
    Its justification rested on an unmeasured worry: that removing flagged members would delete a
    real participant whenever the flag was wrong, and would change a finding's score and identity on
    a heuristic. This measures what a trim would actually do.

    On the pinned amplifier-ring grid the flagged set is EXACTLY the bystanders, and the finding
    survives without them by a wide margin. So the 52.9% false naming pinned in `test_netdetect.py`
    is not the price of catching the ring: the ring is catchable while naming nobody innocent.

    THE SCORE RISING IS EXPECTED ARITHMETIC, NOT INDEPENDENT EVIDENCE, and saying otherwise would
    overstate this. A subset that keeps the shared features has the same k over a smaller n, so the
    Poisson-binomial tail is smaller and the score is higher by construction. That is the same fact
    `leave_one_out` already measures. The load-bearing assertions are the two that are NOT
    arithmetic: the flag matches ground truth exactly, and the trimmed set still clears the null.

    NOTHING HERE CHANGES BEHAVIOUR. `attachment` still reports and never drops. This pins the
    evidence so the decision can be taken deliberately, and so the claim cannot quietly stop being
    true. See CLAUDE.md.
    """
    from app.netdetect.significance import score_candidate

    checked = 0
    for organic, seed in ((40, 63), (60, 61)):
        rows = C.organic_population(organic, seed=31) + C.amplifier_ring(8, seed=seed)
        result = detect_from_commenters(rows, shuffles=SHUFFLES)
        threshold = result.null_threshold
        for finding in result.findings:
            members = list(finding.members)
            ring = [m for m in members if not m.startswith("org")]
            bystanders = {m for m in members if m.startswith("org")}
            if len(ring) < 4 or not bystanders:
                continue
            attachment = assess(result.corpus, members)
            if not attachment.answered:
                continue

            flagged = set(attachment.weak)
            assert flagged == bystanders, (
                f"the flag no longer matches ground truth: flagged {len(flagged)}, bystanders "
                f"{len(bystanders)}. The trim argument below rests on this equality."
            )

            kept = [m for m in members if m not in flagged]
            assert len(kept) >= 3, "a trim would leave too few members to report at all"
            trimmed = score_candidate(result.corpus, kept, collect_evidence=True)

            checked += 1
            assert threshold is not None
            assert trimmed.score > threshold, (
                f"without its {len(flagged)} bystanders the finding scores {trimmed.score:.2f} "
                f"against a null threshold of {threshold:.2f}, so trimming would destroy it and "
                f"reporting-rather-than-dropping is load-bearing after all"
            )

    assert checked, "no contaminated ring finding was examined; this test asserted nothing"


def test_a_trim_would_take_nothing_from_the_community_controls():
    """The other half: a trim rule must not be able to hurt a real community.

    Measured, it cannot, and for a reason that is structural rather than lucky. A genuine community
    is everybody contributing alike, which is exactly the shape `assess` abstains on, so there is no
    flag to trim by. The newsroom control reaches this state and the fan community produces no
    finding at all.

    Asserted as "no GENUINE member is ever flagged" rather than "nothing is flagged", because the
    planted-operation fixtures do legitimately carry a bystander or two and flagging those is the
    module working.
    """
    cases = (
        (C.organic_population(60, seed=7) + C.professional_beat(10, seed=21), "press"),
        (C.organic_population(60, seed=7) + C.fan_community(12, seed=33), "fan"),
    )
    for rows, prefix in cases:
        result = detect_from_commenters(rows, shuffles=SHUFFLES)
        for finding in result.findings:
            members = list(finding.members)
            attachment = assess(result.corpus, members)
            if not attachment.answered:
                continue
            genuine_flagged = [m for m in attachment.weak if m.startswith(prefix)]
            assert not genuine_flagged, (
                f"{len(genuine_flagged)} genuine {prefix} members were flagged as not carrying "
                f"the finding, so a trim rule would delete real participants from a community"
            )


def test_bystanders_do_not_separate_on_anything_generation_can_see():
    """CLOSES the other option for reducing the false naming, so nobody builds it twice.

    CLAUDE.md offered two routes: the `RARITY_CEILING` decision, or tightening candidate generation
    so bystanders are never proposed. The second is the more attractive of the two, because an
    exclusion at generation time is a MISS rather than a false accusation, which is the safer error
    for a product that names real people.

    It is not available. The generator sees the pair-weight graph and nothing else, and on that
    graph the two populations do not separate: the strongest bystander carries far MORE internal
    weight than the weakest genuine member, in every configuration measured.

    That is structural rather than unlucky. A bystander is swept in precisely BECAUSE it shares many
    rare features with the group, so shared weight is the very quantity that makes it look like a
    member. What separates the two is whether removing an account makes the set more or less
    surprising, which is a property of the set statistic and does not exist yet at generation time.

    So this asserts the OVERLAP, deliberately. If it ever fails, a weight-based refinement in
    `candidates.py` has become viable and is worth building; until then it is measured dead.
    """
    from app.netdetect.candidates import pair_weights

    checked = 0
    for organic, seed in ((40, 63), (60, 61)):
        rows = C.organic_population(organic, seed=31) + C.amplifier_ring(8, seed=seed)
        result = detect_from_commenters(rows, shuffles=SHUFFLES)
        weights = pair_weights(result.corpus)
        for finding in result.findings:
            members = list(finding.members)
            ring = [m for m in members if not m.startswith("org")]
            bystanders = [m for m in members if m.startswith("org")]
            if len(ring) < 4 or not bystanders:
                continue

            inside = set(members)
            strength = {m: 0.0 for m in members}
            for (a, b), w in weights.items():
                if a in inside and b in inside:
                    strength[a] += w
                    strength[b] += w

            checked += 1
            assert max(strength[m] for m in bystanders) > min(strength[m] for m in ring), (
                "the populations now SEPARATE on internal edge weight, so a refinement in "
                "candidates.py could exclude bystanders before they are ever named. That is the "
                "better fix and it is worth building; see the note in candidates.py."
            )

    assert checked, "no contaminated ring finding was examined; this test asserted nothing"


def test_a_real_community_is_not_given_a_weakest_member():
    """The professional-beat control. A newsroom on one beat IS everybody contributing alike, so
    singling one reporter out would be inventing a distinction the evidence does not carry."""
    rows = C.organic_population(
        40, seed=9, subject_noise=False, arrivals=False,
    ) + C.professional_beat(10, seed=21)
    result = detect_from_commenters(rows, shuffles=SHUFFLES)
    if not result.findings:
        import pytest
        pytest.skip("the beat control produced no finding on this build")
    for finding in result.findings:
        attachment = assess(result.corpus, finding.members)
        # THE INVARIANT IS THAT NOBODY IS SINGLED OUT, not which route gets there. Two outcomes
        # satisfy it and both are correct answers about a newsroom: abstain because the group is
        # too homogeneous to have a weakest member, or answer that every member carries the
        # finding. The wrong outcome is a name.
        #
        # It used to abstain, and the pinned reason was a measured median contribution of 0.04 to
        # 0.18 against `MIN_MEDIAN_CONTRIBUTION` of 0.5. Once reporters on a beat share the beat's
        # hashtag and the officials they name, removing one costs more and the median measures
        # 0.5217, just over the floor, so it answers instead. The relative threshold still refuses
        # to pick anybody, which is the property that protects the people named.
        assert attachment.weak == [], (
            f"a member of a genuine community was singled out: {attachment.weak}"
        )


def test_a_finding_too_small_to_have_a_typical_member_abstains():
    result, finding = _planted(60, 5)
    attachment = assess(result.corpus, finding.members[:2])
    assert not attachment.answered
    assert attachment.weak == []


# ==================================================================================================
# The arithmetic, and what it must not become
# ==================================================================================================
def test_removing_a_genuine_member_costs_the_finding_and_removing_a_bystander_does_not():
    """The sign is the signal, and it comes out of the arithmetic rather than a threshold. Removing
    a real member drops the shared count across many rare features so the tail widens; removing a
    bystander leaves that count alone while shrinking the group, so the tail narrows."""
    result, finding = _planted(60, 5)
    deltas = leave_one_out(result.corpus, finding.members)

    members = [v for m, v in deltas.items() if m.startswith("op")]
    bystanders = [v for m, v in deltas.items() if m.startswith("org")]
    assert min(members) > 0, "removing a genuine member did not cost the finding anything"
    assert max(bystanders) <= 0, "a bystander carried positive weight on this corpus"


def test_the_threshold_must_stay_relative_because_the_populations_overlap_globally():
    """Measured across the grid: the weakest genuine member scored -0.134 and the strongest
    bystander +0.116. A fixed global cut misclassifies one of them whichever value it takes, which
    is why the rule compares a member against the median of its OWN finding."""
    weakest_member = None
    strongest_bystander = None
    for organic in (30, 40, 50, 60):
        for seed in (5, 11, 23):
            result, finding = _planted(organic, seed)
            deltas = leave_one_out(result.corpus, finding.members)
            for m, v in deltas.items():
                if m.startswith("org"):
                    strongest_bystander = v if strongest_bystander is None else max(strongest_bystander, v)
                else:
                    weakest_member = v if weakest_member is None else min(weakest_member, v)

    assert weakest_member is not None and strongest_bystander is not None
    assert weakest_member < strongest_bystander, (
        "the two populations now separate globally. That would make a fixed threshold viable and "
        "this rule simpler; verify across more corpora before changing it."
    )


def test_the_flag_reports_and_never_removes_a_member():
    """Dropping a flagged account would change the finding's membership, its score and its stored
    identity on the strength of a heuristic, and would silently delete a real participant whenever
    the heuristic got it the other way round."""
    result, finding = _planted(60, 5)
    assert finding.weakly_attached, "the fixture stopped flagging anyone"
    for flagged in finding.weakly_attached:
        assert flagged in finding.members, "a flagged account was removed from the finding"
    assert len(finding.members) == 11
    assert finding.size == 11


def test_an_empty_flag_list_is_never_ambiguous():
    """THERE ARE THREE STATES AND THE MIDDLE ONE IS EASY TO LOSE.

    Checked with weak members; checked with none, meaning every member carries the finding; and not
    checked at all. The second and third both present an empty list and are opposite statements
    about the people named, so `attachment_checked` is explicit rather than inferred from the note.
    Same distinction as `score: null` against `0` on the analyst's signals.
    """
    seen_checked = seen_abstained = False
    for organic, seed in ((60, 5), (50, 5), (60, 11), (50, 23)):
        _, finding = _planted(organic, seed)
        if finding.attachment_checked:
            seen_checked = True
            assert finding.attachment_note is None
        else:
            seen_abstained = True
            assert finding.attachment_note, "not checked, and no reason given"
            assert finding.weakly_attached == []
    assert seen_checked and seen_abstained, "the fixture stopped covering both states"


def test_the_constants_are_the_measured_ones():
    """Pinned so a later tweak is a deliberate act with a measurement behind it."""
    assert WEAK_FRACTION == 0.25
    assert MIN_MEDIAN_CONTRIBUTION == 0.5
    # Cost is steep in the member count: measured on a 220-account corpus at 0.21s for 20 members,
    # 2.8s for 40 and 15.4s for 60. This runs inside a request that has already spent tens of
    # seconds detecting, so the cap is where the answer stops being worth the wait.
    assert MAX_MEMBERS == 40


def test_an_oversized_finding_abstains_rather_than_making_the_operator_wait():
    """And it says which of the two empty-list meanings applies, so nobody reads the silence as
    'every member belongs'."""
    result, finding = _planted(60, 5)
    oversized = sorted(result.corpus.by_id)[:MAX_MEMBERS + 5]
    attachment = assess(result.corpus, oversized)
    assert not attachment.answered
    assert attachment.weak == []
    assert str(MAX_MEMBERS) in attachment.abstained


# ==================================================================================================
# The migration path
# ==================================================================================================
def test_the_new_columns_reach_a_database_that_already_had_the_table():
    """`create_all` LEAVES EXISTING TABLES ALONE, and the boot upgrade pass works from an explicit
    list rather than from the models. A column added to `NetdetectFinding` without a matching entry
    in `_INCREMENTAL_COLUMNS` therefore never appears on a database that already created the table,
    and every insert fails against it. This repo has paid for that shape before.

    The default matters as much as the column: a row written before the membership test existed was
    never checked, and reading its empty `weak_members_json` as "every member belongs" would turn
    "we did not look" into a clean bill of health for named people.
    """
    import os
    import sqlite3
    import tempfile

    from app.core.config import get_settings
    import app.storage.db as db

    directory = tempfile.mkdtemp()
    path = os.path.join(directory, "pre_attachment.db")
    con = sqlite3.connect(path)
    con.execute(
        """CREATE TABLE netdetect_findings (
             id INTEGER PRIMARY KEY, investigation_id INTEGER, context_id VARCHAR(128),
             platform VARCHAR(32), members_key VARCHAR(2048), members_json JSON,
             member_count INTEGER, score FLOAT, corrected_p FLOAT, by_family_json JSON,
             needs_adjudication TEXT, evidence_json JSON, corpus_size INTEGER,
             null_shuffles INTEGER, null_threshold FLOAT, status VARCHAR(16),
             dismissed_at TIMESTAMP, dismissed_by INTEGER, dismissal_reason TEXT,
             confirmed_at TIMESTAMP, created_at TIMESTAMP, updated_at TIMESTAMP)"""
    )
    con.execute("INSERT INTO netdetect_findings (id, members_key, status) VALUES (1, 'a|b|c', 'open')")
    con.commit()
    con.close()

    previous_url = os.environ.get("OMI_DATABASE_URL")
    previous_engine, previous_session = db._engine, db._SessionLocal
    try:
        os.environ["OMI_DATABASE_URL"] = f"sqlite:///{path}"
        get_settings.cache_clear()
        db._engine = None
        db._SessionLocal = None
        db.init_db()

        con = sqlite3.connect(path)
        columns = {r[1] for r in con.execute("PRAGMA table_info(netdetect_findings)")}
        assert {"weak_members_json", "attachment_note", "attachment_checked"} <= columns

        checked = con.execute(
            "SELECT attachment_checked FROM netdetect_findings WHERE id = 1"
        ).fetchone()[0]
        assert int(checked) == 0, "a row from before the test existed reads as already checked"
        con.close()
    finally:
        if previous_url is None:
            os.environ.pop("OMI_DATABASE_URL", None)
        else:
            os.environ["OMI_DATABASE_URL"] = previous_url
        get_settings.cache_clear()
        db._engine, db._SessionLocal = previous_engine, previous_session


# ==================================================================================================
# The abstention used to switch itself off exactly when it was needed
# ==================================================================================================
def test_a_finding_more_than_half_bystanders_still_gets_a_verdict():
    """THE BUG THIS FILE'S RULE WAS REWRITTEN FOR, and it is a converse error rather than a
    mis-set threshold.

    The old rule abstained when the MEDIAN contribution was low. Its stated reasoning was sound: a
    homogeneous group gives every member a delta near zero. The code relied on the converse, which
    is false. A finding that is more than half bystanders ALSO has a near-zero median, because the
    median then falls INSIDE the bystander cluster instead of between the clusters. So the guard
    against naming innocent people went quiet as contamination got worse.

    Measured on the amplifier-ring grid before the change, it abstained on every finding where
    bystanders reached half or more (9 of 17, 15 of 23, 17 of 25) while the two populations were
    cleanly separated in each: no genuine member below +1.19, no bystander above +0.52. Flagging
    across the grid was 18 of 81. After keying on the widest step instead it is every bystander in
    each of the eight configurations measured, with no genuine member flagged.

    This pins the shape rather than the exact counts: a finding whose bystanders OUTNUMBER its
    genuine members must still get an answer, and that answer must not name a genuine member.
    """
    rows = C.organic_population(60, seed=31) + C.amplifier_ring(8, seed=61)
    ring = {r["external_id"] for r in rows if not str(r["external_id"]).startswith("org")}
    result = detect_from_commenters(rows, shuffles=SHUFFLES)
    hits = [c for c in result.findings if len(set(c.members) & ring) >= 4]
    assert hits, "the ring was not found; fixture changed"

    finding = hits[0]
    bystanders = {m for m in finding.members if m not in ring}
    genuine = {m for m in finding.members if m in ring}
    assert len(bystanders) > len(genuine), (
        f"this fixture no longer has a bystander MAJORITY ({len(bystanders)} of "
        f"{len(finding.members)}), which is the condition the old median rule could not survive. "
        f"Find another corpus that does, or this test has stopped testing anything."
    )

    attachment = assess(result.corpus, finding.members)
    assert attachment.answered, (
        f"abstained on a finding that is {len(bystanders)} bystanders to {len(genuine)} members. "
        f"That is the regression: the abstention must not fire because the median sank into the "
        f"bystander cluster. Reported gap {attachment.gap} against {MIN_CONTRIBUTION_GAP}."
    )
    assert not (set(attachment.weak) & genuine), (
        f"genuine operation members were flagged as weakly attached: "
        f"{sorted(set(attachment.weak) & genuine)}"
    )
    assert set(attachment.weak) == bystanders, (
        f"flagged {len(attachment.weak)} of {len(bystanders)} bystanders; the boundary is supposed "
        f"to land on the empty band between the two populations"
    )


def test_a_finding_too_large_to_test_goes_to_a_reader_rather_than_publishing_unchecked():
    """THE SAME BUG AS THE MEDIAN RULE, REACHED BY THE SIZE ROUTE, and measured rather than feared.

    `assess` abstains above `MAX_MEMBERS`, and contamination is what GROWS a finding, so the largest
    findings are the most contaminated ones and were the only ones nobody looked at. Measured on the
    amplifier ring as the background grows, bystanders of members:

        20 -> 12    25 -> 17    33 -> 25    38 -> 30    40 -> 32     all tested, all sent to review
        49 -> 41    44 -> 36                             OVER CAP, untested, and PUBLISHED

    So at exactly the point contamination is worst (84%), crossing the cap flipped a finding from
    "a human is asked" to "nothing asks anybody". A 168-account comment section is ordinary for this
    product, so this is production-reachable and not a fixture artefact.

    THE FIX ADDS REVIEW AND CHANGES NO MEMBERSHIP. Nobody is dropped, no score moves. That is what
    keeps it separate from the two open decisions, which change who is NAMED.
    """
    ring = C.amplifier_ring(8, seed=62)
    ring_ids = {r["external_id"] for r in ring}
    rows = C.organic_population(160, seed=31) + ring
    result = detect_from_commenters(rows, shuffles=SHUFFLES)

    checked = 0
    for finding in result.findings:
        members = set(finding.members)
        if len(members & ring_ids) < 4:
            continue
        if len(members) <= MAX_MEMBERS:
            continue
        checked += 1
        assert not finding.attachment_checked, "premise: this finding must be over the cap"
        assert finding.needs_adjudication, (
            f"a {len(members)}-member finding was published with its membership untested and "
            f"nothing asking a human; that is the guard switching off where it is needed most"
        )
        assert "not tested" in finding.needs_adjudication

    assert checked, (
        "no finding exceeded MAX_MEMBERS on this corpus, so the size route went untested. If the "
        "corpora changed, find one that does rather than deleting this."
    )


def test_the_ordinary_abstention_does_not_drag_a_clean_group_into_review():
    """The other half, and the reason only the SIZE abstention is acted on.

    "Every member contributes about equally" is a real answer about a real group: it is what a
    homogeneous operation and a genuine community both look like. Acting on it would send everything
    to a reader, and a review queue that flags everything is the same as no review queue.
    """
    rows = (
        C.organic_population(40, seed=9, subject_noise=False, arrivals=False)
        + C.planted_operation(8, discipline=0.0, seed=23, subject_noise=False, arrivals=False)
    )
    result = detect_from_commenters(rows, shuffles=SHUFFLES)

    seen = 0
    for finding in result.findings:
        attachment = assess(result.corpus, finding.members)
        if attachment.answered or attachment.unchecked_for_size:
            continue
        seen += 1
        assert "equally" in (attachment.abstained or "")
        assert not attachment.unchecked_for_size, (
            "a gap abstention was marked as a capability limit, which would send every clean "
            "homogeneous group to a reader"
        )
    if not seen:
        import pytest
        pytest.skip("no gap-abstaining finding on this build")
