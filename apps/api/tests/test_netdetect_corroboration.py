"""Reading the accumulating graph back, and the measurement that shaped how.

THE ONE THAT MATTERS IS `test_total_history_does_not_separate_an_operation_from_a_newsroom`. The
obvious version of this feature adds accumulated history to a finding's confidence, and measured
against this package's own innocent controls it promotes the professional-beat control just as
hard as the planted operation. That test is a CHARACTERIZATION of a real property of the data, not
an aspiration, and it is what justifies `hard_pairs` existing as a separate number.
"""

from __future__ import annotations

import pytest

from app.campaigns.tracking.graph import record_pairs
from app.netdetect import corroboration as corrob
from app.netdetect import detect_from_commenters
from app.netdetect.persist import pair_evidence_from
from app.netdetect.types import HARD_FAMILIES, Candidate
from tests.netdetect_corpora import (
    fan_community,
    organic_population,
    planted_operation,
    professional_beat,
)

POST = "the_post_under_test"

#: The minimum that can express p<=0.05, which is what `detect` refuses below. These tests are
#: about what history says, not about the precision of the null, and each scan is expensive: at 40
#: shuffles this file ran 502 seconds against a suite that is already 19 minutes.
SHUFFLES = 20

#: Every group here is generated from a fixed seed and `detect` is deterministic by design, so the
#: same scan is recomputed many times across this file for no new information. Memoised on that
#: guarantee: if this cache ever changes a result, determinism has broken and
#: `test_the_answer_does_not_depend_on_the_interpreters_hash_seed` is the test that should say so.
_GROUPS = {
    "operation": lambda: planted_operation(8, discipline=0.0, seed=99),
    "newsroom": lambda: professional_beat(10, seed=21),
    "fandom": lambda: fan_community(12, seed=33),
}
_SCANS: dict[tuple[str, str, int], object] = {}


def members_of(kind):
    return sorted(r["external_id"] for r in _GROUPS[kind]())


def _scan(kind, context, *, seed=7):
    key = (kind, context, seed)
    if key not in _SCANS:
        rows = organic_population(60, seed=seed) + _GROUPS[kind]()
        _SCANS[key] = (rows, detect_from_commenters(
            rows, exclude_context={context}, shuffles=SHUFFLES))
    return _SCANS[key]


def _seed_history(session, kind, contexts, *, seed=7):
    """Simulate the group being scanned under several unrelated posts, as production would."""
    for i, context in enumerate(contexts):
        _rows, result = _scan(kind, context, seed=seed + i)
        for finding in result.findings:
            record_pairs(
                session, platform=finding.platform or "x", context_id=context,
                pair_evidence=pair_evidence_from(result.corpus, finding),
            )
    session.commit()


@pytest.fixture()
def session():
    """A session on the per-test in-memory database `conftest._clean_db_and_embedder` resets.

    Isolation matters more here than usual: several tests seed history for the SAME accounts under
    different contexts, so a database shared between them would let one test's seeding satisfy
    another test's "these accounts have not been seen before".
    """
    from app.storage.db import get_session, init_db

    init_db()
    with get_session() as s:
        yield s


# ==================================================================================================
# The measurement that decided the design
# ==================================================================================================
def test_total_history_does_not_separate_an_operation_from_a_newsroom(session):
    """The reason `log_lr` is context and `hard_pairs` is the discriminator.

    Seeded under three unrelated posts each, a planted operation and a newsroom covering one beat
    both SATURATE the history cap, and the newsroom carries MORE linked pairs than the operation.
    Reporters on a beat genuinely keep appearing under the same posts; that is what a beat is.

    So a confidence lift driven by total history would promote the exact control this package
    exists to refuse, and would do it with a number that reads like corroborating evidence. This
    test characterises that, so anybody tempted to add the lift sees the measurement first.
    """
    _seed_history(session, "operation",
                  ["op_1", "op_2", "op_3"])
    _seed_history(session, "newsroom",
                  ["beat_1", "beat_2", "beat_3"])

    operation = members_of("operation")
    newsroom = members_of("newsroom")

    op = corrob.for_members(session, operation, platform="x", exclude_context=POST)
    beat = corrob.for_members(session, newsroom, platform="x", exclude_context=POST)

    assert op.seen_before and beat.seen_before
    assert op.log_lr == beat.log_lr == corrob.MAX_HISTORY_LOG10, (
        "if these ever separate on the total, the design argument for hard_pairs is weaker and "
        "this test should be revisited rather than deleted"
    )
    assert beat.pairs_with_history >= op.pairs_with_history, (
        "the newsroom carried MORE linked pairs than the operation; that is the whole point"
    )


def test_hard_family_history_is_what_separates_them(session):
    """The operator's OWN ACTS, gathered under other posts. `MIN_HARD_EVIDENCE` extended in time.

    A shared profession produces text, timing and infrastructure overlap for free. It does not
    produce a batch of accounts provisioned together (identity) or convergence on outside targets
    (network), which is why those two are the only ones this keys on.
    """
    _seed_history(session, "operation",
                  ["op_1", "op_2", "op_3"])
    _seed_history(session, "newsroom",
                  ["beat_1", "beat_2", "beat_3"])

    op = corrob.for_members(
        session, members_of("operation"),
        platform="x", exclude_context=POST,
    )
    beat = corrob.for_members(
        session, members_of("newsroom"),
        platform="x", exclude_context=POST,
    )

    assert op.hard_history, "the planted operation carried no prior evidence of the operator's acts"
    assert op.hard_pairs == op.pairs_with_history
    assert set(op.hard_families) <= set(HARD_FAMILIES)

    assert not beat.hard_history, "the newsroom control was credited with the operator's own acts"
    assert beat.hard_pairs == 0


def test_the_sentence_refuses_to_read_soft_history_as_corroboration(session):
    """A number a reader cannot interpret is worse than none, so the wording carries the caveat."""
    _seed_history(session, "newsroom",
                  ["beat_1", "beat_2", "beat_3"])
    beat = corrob.for_members(
        session, members_of("newsroom"),
        platform="x", exclude_context=POST,
    )
    sentence = beat.sentence()
    assert "context rather than corroboration" in sentence
    assert "operator's own acts" not in sentence.split("None of it")[0]


# ==================================================================================================
# The exclusion that makes it independent
# ==================================================================================================
def test_a_set_cannot_corroborate_itself_from_the_post_being_scanned(session):
    """Without this a formation corroborates itself the moment it is recorded, and every re-run
    strengthens the illusion. The exclusion is exact, on `contexts_json`, not approximate."""
    _seed_history(session, "operation", [POST])
    members = members_of("operation")

    same = corrob.for_members(session, members, platform="x", exclude_context=POST)
    assert not same.seen_before
    assert same.pairs_with_history == 0 and same.hard_pairs == 0
    assert same.log_lr == 0.0

    other = corrob.for_members(session, members, platform="x", exclude_context="a_different_post")
    assert other.seen_before, "excluding a different post should leave the history intact"


def test_only_the_share_from_other_posts_is_credited(session):
    """An edge seen under this post AND two others carries two thirds of its accumulated evidence
    into the answer, not all of it. Crediting the whole sum counts this post's own contribution
    a second time, which is the same double-count the exclusion above prevents wholesale."""
    _seed_history(session, "operation",
                  ["earlier_1", "earlier_2", POST])
    members = members_of("operation")

    including = corrob.for_members(session, members, platform="x", exclude_context="unrelated")
    excluding = corrob.for_members(session, members, platform="x", exclude_context=POST)

    assert POST not in excluding.contexts
    assert POST in including.contexts
    assert excluding.log_lr <= including.log_lr


# ==================================================================================================
# The controls
# ==================================================================================================
def test_strangers_report_no_history_and_say_so_plainly(session):
    members = sorted(r["external_id"] for r in organic_population(60, seed=7))[:8]
    out = corrob.for_members(session, members, platform="x", exclude_context=POST)
    assert out.checked and not out.seen_before and not out.hard_history
    assert out.log_lr == 0.0
    assert "not been seen together" in out.sentence()


def test_a_fan_community_accumulates_nothing(session):
    """It produces no findings at all, so there is nothing to accumulate. Recorded because a
    control that never enters the graph is a different, stronger result than one that enters and
    scores low."""
    _seed_history(session, "fandom", ["fan_1", "fan_2", "fan_3"])
    out = corrob.for_members(
        session, members_of("fandom"),
        platform="x", exclude_context=POST,
    )
    assert not out.seen_before


def test_an_edge_to_an_outsider_is_not_evidence_about_this_set(session):
    """The two `IN` clauses match each column independently, so a row pairing one member with an
    account outside the set comes back from the query. Both ends have to be inside it."""
    record_pairs(session, platform="x", context_id="elsewhere", pair_evidence={
        ("member_a", "an_outsider"): {"identity": 5.0},
    })
    session.commit()
    out = corrob.for_members(session, ["member_a", "member_b"], platform="x",
                             exclude_context=POST)
    assert out.pairs_with_history == 0, "an edge to an outsider was counted as evidence about the set"


def test_the_graph_is_keyed_on_platform(session):
    record_pairs(session, platform="youtube", context_id="elsewhere", pair_evidence={
        ("m1", "m2"): {"identity": 5.0},
    })
    session.commit()
    assert corrob.for_members(session, ["m1", "m2"], platform="youtube",
                              exclude_context=POST).seen_before
    assert not corrob.for_members(session, ["m1", "m2"], platform="x",
                                  exclude_context=POST).seen_before


# ==================================================================================================
# What it must never do
# ==================================================================================================
def test_zero_history_and_no_lookup_are_different_answers(session):
    """Same distinction as `attachment_checked` and as `score: null` against `0`. A zero with
    `checked` false means nobody looked, which is not a statement about the people named."""
    looked = corrob.for_members(session, ["p", "q"], platform="x", exclude_context=POST)
    assert looked.checked and looked.log_lr == 0.0

    unchecked = corrob.Corroboration(unavailable="the lookup could not run")
    assert not unchecked.checked
    assert not unchecked.seen_before and not unchecked.hard_history
    assert unchecked.log_lr == 0.0
    assert "No history was read" in unchecked.sentence()


def test_an_oversized_member_list_refuses_rather_than_running_the_query(session):
    members = [f"acct_{i}" for i in range(200)]
    out = corrob.for_members(session, members, platform="x", exclude_context=POST)
    assert not out.checked
    assert "current corpus alone" in out.unavailable


def test_history_never_touches_a_candidates_score(session):
    """It is measured outside this corpus and was never subjected to the shuffled search correction
    that makes the families' sum honest. Folding it in would slip evidence past the very thing that
    makes the score defensible."""
    _seed_history(session, "operation",
                  ["op_1", "op_2", "op_3"])
    _rows, result = _scan("operation", POST)
    assert result.findings

    before = [(c.score, dict(c.by_family), c.corrected_p) for c in result.findings]
    corrob.annotate(session, result.findings, exclude_context=POST)
    after = [(c.score, dict(c.by_family), c.corrected_p) for c in result.findings]

    assert before == after, "corroboration moved a score, a family total or a corrected p-value"
    assert result.findings[0].corroboration is not None


def test_history_never_clears_an_adjudication_flag(session):
    """`needs_adjudication` means a person has to look. Resolving it from accumulated numbers would
    be a threshold quietly overruling a human review step, which `calibration.py` refuses by the
    same argument."""
    _seed_history(session, "newsroom",
                  ["beat_1", "beat_2", "beat_3"])
    _rows, result = _scan("newsroom", POST, seed=11)
    flagged = [c for c in result.findings if c.needs_adjudication]
    if not flagged:
        pytest.skip("this corpus produced no finding needing adjudication")

    reasons = [c.needs_adjudication for c in flagged]
    corrob.annotate(session, result.findings, exclude_context=POST)
    assert [c.needs_adjudication for c in flagged] == reasons


def test_annotate_uses_each_candidates_own_platform(session):
    """The graph is keyed on platform, so a hardcoded one would silently return nothing for a
    candidate found on another."""
    record_pairs(session, platform="youtube", context_id="elsewhere", pair_evidence={
        ("yt_a", "yt_b"): {"identity": 5.0},
    })
    session.commit()

    candidate = Candidate(members=["yt_a", "yt_b"], platform="youtube", score=1.0)
    corrob.annotate(session, [candidate], platform="x", exclude_context=POST)
    assert candidate.corroboration.seen_before, "the fallback platform overrode the candidate's own"


def test_annotate_survives_a_broken_lookup_without_failing_the_run(session):
    """Context on a finding is never a reason to fail the detection that produced it."""
    class Exploding:
        def execute(self, *_a, **_k):
            raise RuntimeError("the database went away")

    candidate = Candidate(members=["a", "b"], platform="x", score=1.0)
    assert corrob.annotate(Exploding(), [candidate], exclude_context=POST) == 1
    assert candidate.corroboration is not None
    assert not candidate.corroboration.checked


# ==================================================================================================
# The migration path
# ==================================================================================================
def test_the_snapshot_column_reaches_a_database_that_already_had_the_table():
    """`create_all` LEAVES EXISTING TABLES ALONE and the boot upgrade pass works from an explicit
    list, so a column added to the model alone never reaches a database that already created the
    table. Built as a real database rather than asserted against the registry, because a typo in
    the list passes inspection and fails at runtime."""
    import os
    import sqlite3
    import tempfile

    from app.core.config import get_settings
    import app.storage.db as db

    path = os.path.join(tempfile.mkdtemp(), "pre_corroboration.db")
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
    con.execute("INSERT INTO netdetect_findings (id, members_key, status) VALUES (1, 'a|b', 'open')")
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
        assert "corroboration_json" in columns
        stored = con.execute(
            "SELECT corroboration_json FROM netdetect_findings WHERE id = 1"
        ).fetchone()[0]
        assert stored is None, (
            "a finding from before the lookup existed must read as 'not checked', never as "
            "'these accounts have never been seen together'"
        )
        con.close()
    finally:
        if previous_url is None:
            os.environ.pop("OMI_DATABASE_URL", None)
        else:
            os.environ["OMI_DATABASE_URL"] = previous_url
        get_settings.cache_clear()
        db._engine, db._SessionLocal = previous_engine, previous_session
