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
    key = (organic, seed)
    if key not in _CACHE:
        rows = C.organic_population(organic, seed=seed) + C.planted_operation(
            8, seed=seed + 1, discipline=0.0)
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


def test_a_real_community_is_not_given_a_weakest_member():
    """The professional-beat control. A newsroom on one beat IS everybody contributing alike, so
    singling one reporter out would be inventing a distinction the evidence does not carry."""
    rows = C.organic_population(40, seed=9) + C.professional_beat(10, seed=21)
    result = detect_from_commenters(rows, shuffles=SHUFFLES)
    if not result.findings:
        import pytest
        pytest.skip("the beat control produced no finding on this build")
    for finding in result.findings:
        attachment = assess(result.corpus, finding.members)
        assert not attachment.answered, (
            f"a member of a genuine community was singled out: {attachment.weak}"
        )
        assert attachment.weak == []


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
