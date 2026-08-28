"""Recording netdetect's findings, and folding their pairs into the graph that accumulates.

Two claims are being kept apart here and the tests exist to hold them apart.

**The set was significant. A pair inside it was not.** netdetect's whole thesis is that a set-level
statistic is not recoverable by fusing pairwise ones, so decomposing a finding back into edges is
the one operation that could quietly undo the argument. Distributing the finding's score across its
pairs would put a number in the accumulating graph that no test produced, and it would look exactly
like measured pairwise significance. So a pair carries only the surprise of the features THAT PAIR
ACTUALLY SHARES.

**Recording is not publishing.** Nothing here mints a share token or writes a `Campaign` row. The
rule that a claim about a person is a decision somebody took, never a side effect of a page load, is
about publication and is untouched by storing an internal finding.
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.netdetect.persist import MAX_MEMBERS_FOR_PAIRS, members_key, pair_evidence_from, persist_finding
from app.netdetect.significance import Corpus
from app.netdetect.types import (
    FAMILY_IDENTITY,
    FAMILY_TEXT,
    AccountProfile,
    Candidate,
    Feature,
    FeatureEvidence,
)
from app.storage.db import get_session
from app.storage.models import CoordinationEdge, NetdetectFinding

T0 = datetime(2026, 4, 1, tzinfo=timezone.utc)


def _corpus(holdings: dict[str, list[Feature]]) -> Corpus:
    return Corpus([
        AccountProfile(external_id=ext, platform="x", features=set(feats))
        for ext, feats in holdings.items()
    ])


def _evidence(feature: Feature, *, shared_by: int, corpus_count: int, surprise: float):
    return FeatureEvidence(
        feature=feature, shared_by=shared_by, corpus_count=corpus_count,
        surprise=surprise, sentence=f"{shared_by} accounts share {feature.value}",
    )


# ==================================================================================================
# The decomposition: what a pair is recorded as having done
# ==================================================================================================
def test_a_pair_carries_only_what_it_actually_shares_not_the_findings_score():
    """THE LOAD-BEARING TEST. A high-scoring six-account finding, and one pair inside it that shares
    a single weak feature. The pair must come out weak.

    Distributing the set score would hand this pair a large number, and the graph would then carry
    an accumulated claim about two people that no measurement supports."""
    strong = Feature(FAMILY_IDENTITY, "creation_week", "2026-W02")
    weak = Feature(FAMILY_TEXT, "shingle", "a phrase two of them happened to use")

    corpus = _corpus({
        "a": [strong], "b": [strong], "c": [strong], "d": [strong],
        "e": [weak], "f": [weak],
    })
    candidate = Candidate(
        members=["a", "b", "c", "d", "e", "f"], platform="x",
        score=42.0,                                  # a big set-level number
        by_family={FAMILY_IDENTITY: 40.0, FAMILY_TEXT: 2.0},
        evidence=[
            _evidence(strong, shared_by=4, corpus_count=4, surprise=6.0),
            _evidence(weak, shared_by=2, corpus_count=2, surprise=0.8),
        ],
    )

    pairs = pair_evidence_from(corpus, candidate)

    ef = pairs[("e", "f")]
    assert sum(ef.values()) < 1.0, (
        "the weak pair inherited the finding's score; that is pairwise significance nobody measured"
    )
    assert FAMILY_IDENTITY not in ef, "a pair was credited with a feature neither member holds"


def test_a_feature_only_one_of_the_pair_holds_contributes_nothing_to_that_pair():
    shared = Feature(FAMILY_TEXT, "shingle", "the same eight words in the same order here")
    solo = Feature(FAMILY_IDENTITY, "handle_template", "L6_D3")

    corpus = _corpus({"a": [shared, solo], "b": [shared], "c": [shared]})
    candidate = Candidate(
        members=["a", "b", "c"], platform="x", score=5.0,
        by_family={FAMILY_TEXT: 5.0},
        evidence=[
            _evidence(shared, shared_by=3, corpus_count=3, surprise=3.0),
            _evidence(solo, shared_by=1, corpus_count=1, surprise=4.0),
        ],
    )

    pairs = pair_evidence_from(corpus, candidate)
    assert set(pairs) == {("a", "b"), ("a", "c"), ("b", "c")}
    for families in pairs.values():
        assert FAMILY_IDENTITY not in families, "a one-holder feature became pairwise evidence"


def test_one_feature_deposits_its_surprise_once_across_the_pairs_that_share_it():
    """A feature held by six of the group touches fifteen pairs. Giving each of them the full
    surprise would multiply one observation fifteen-fold, which is the same error the harmonic
    within-family discount exists to prevent at the set level."""
    f = Feature(FAMILY_TEXT, "shingle", "identical sentence across the whole ring right here")
    members = ["m0", "m1", "m2", "m3", "m4", "m5"]
    corpus = _corpus({m: [f] for m in members})
    candidate = Candidate(
        members=members, platform="x", score=4.0, by_family={FAMILY_TEXT: 4.0},
        evidence=[_evidence(f, shared_by=6, corpus_count=6, surprise=4.5)],
    )

    pairs = pair_evidence_from(corpus, candidate)
    assert len(pairs) == 15
    total = sum(sum(v.values()) for v in pairs.values())
    assert abs(total - 4.5) < 1e-9, f"one observation deposited {total} instead of 4.5"


def test_a_finding_too_large_to_decompose_writes_no_pairs():
    """Pairs grow quadratically. A finding this size is a subject rather than a formation, and is
    refused upstream anyway; writing tens of thousands of edges for one observation is not a
    fallback worth having."""
    f = Feature(FAMILY_TEXT, "shingle", "shared by everybody in a very large group indeed")
    members = [f"big{i:03d}" for i in range(MAX_MEMBERS_FOR_PAIRS + 1)]
    corpus = _corpus({m: [f] for m in members})
    candidate = Candidate(
        members=members, platform="x", score=9.0, by_family={FAMILY_TEXT: 9.0},
        evidence=[_evidence(f, shared_by=len(members), corpus_count=len(members), surprise=6.0)],
    )
    assert pair_evidence_from(corpus, candidate) == {}


def test_the_key_is_the_set_and_order_does_not_change_it():
    assert members_key(["c", "a", "b"]) == members_key(["b", "c", "a"]) == "a|b|c"


# ==================================================================================================
# The store
# ==================================================================================================
def _simple_finding():
    f = Feature(FAMILY_TEXT, "shingle", "the same opening line on three separate accounts")
    g = Feature(FAMILY_IDENTITY, "creation_week", "2026-W05")
    corpus = _corpus({"p1": [f, g], "p2": [f, g], "p3": [f]})
    candidate = Candidate(
        members=["p1", "p2", "p3"], platform="x", score=7.5,
        by_family={FAMILY_TEXT: 4.0, FAMILY_IDENTITY: 3.5},
        corrected_p=0.01,
        evidence=[
            _evidence(f, shared_by=3, corpus_count=3, surprise=4.0),
            _evidence(g, shared_by=2, corpus_count=2, surprise=3.5),
        ],
    )
    return corpus, candidate


def _persist(session, corpus, candidate, *, investigation_id=None, context_id="post-1", **kw):
    return persist_finding(
        session, candidate, corpus,
        investigation_id=investigation_id, context_id=context_id, platform="x",
        corpus_size=40, null_shuffles=32, null_threshold=6.0, **kw,
    )


def test_re_running_the_detector_updates_the_row_rather_than_stacking_duplicates():
    """An operator re-runs constantly while tuning. A second row per run would turn the queue into
    a log of every button press."""
    corpus, candidate = _simple_finding()
    with get_session() as session:
        _persist(session, corpus, candidate, investigation_id=4001)
        session.commit()
        candidate.score = 8.25
        _persist(session, corpus, candidate, investigation_id=4001)
        session.commit()

        rows = list(session.execute(
            NetdetectFinding.__table__.select().where(
                NetdetectFinding.investigation_id == 4001)
        ))
        assert len(rows) == 1
        stored = session.query(NetdetectFinding).filter_by(investigation_id=4001).one()
        assert stored.score == 8.25, "the refresh did not update the numbers"
        assert stored.member_count == 3
        assert stored.evidence_json and stored.evidence_json[0]["corpus_count"] == 3


def test_a_dismissed_finding_keeps_its_dismissal_when_the_numbers_are_refreshed():
    """THE DISMISSALS ARE THE ONLY GROUND TRUTH THIS DETECTOR WILL EVER ACCUMULATE, and silently
    reopening one on the next re-run would make them worthless: the operator would be asked the same
    question forever and no answer would survive to be fitted against."""
    corpus, candidate = _simple_finding()
    with get_session() as session:
        row = _persist(session, corpus, candidate, investigation_id=4002)
        session.commit()
        row.status = "dismissed"
        row.dismissal_reason = "these are all reporters on one beat"
        row.dismissed_at = T0
        session.commit()

        candidate.score = 11.0
        _persist(session, corpus, candidate, investigation_id=4002)
        session.commit()

        stored = session.query(NetdetectFinding).filter_by(investigation_id=4002).one()
        assert stored.status == "dismissed"
        assert stored.dismissal_reason == "these are all reporters on one beat"
        assert stored.score == 11.0, "the refresh should still carry the new evidence"


def test_the_same_member_set_under_two_investigations_is_two_findings():
    """Seeing the same accounts again under a different post is a SECOND observation, and collapsing
    it into the first would discard exactly the independent sighting the tracking layer is for."""
    corpus, candidate = _simple_finding()
    with get_session() as session:
        _persist(session, corpus, candidate, investigation_id=4003, context_id="post-a")
        _persist(session, corpus, candidate, investigation_id=4004, context_id="post-b")
        session.commit()
        key = members_key(candidate.members)
        assert session.query(NetdetectFinding).filter_by(members_key=key).count() == 2


# ==================================================================================================
# Accumulation into the graph
# ==================================================================================================
def _edges(session, members):
    return list(session.query(CoordinationEdge).filter(
        CoordinationEdge.account_a.in_(members)).all())


def test_recording_a_finding_folds_its_pairs_into_the_accumulating_graph():
    """The reason this was worth building: the tracking layer that survives account rotation was
    learning only from the older cohort detector while the better one ran read-only."""
    corpus, candidate = _simple_finding()
    with get_session() as session:
        _persist(session, corpus, candidate, investigation_id=4005, context_id="ctx-fold")
        session.commit()
        edges = _edges(session, ["p1", "p2", "p3"])
        assert edges, "nothing reached CoordinationEdge"
        assert all(e.log_lr_sum > 0 for e in edges)
        assert all("ctx-fold" in (e.contexts_json or []) for e in edges)


def test_re_scanning_one_post_does_not_compound_the_same_observation():
    """Otherwise anyone could strengthen a finding by pressing rescan."""
    corpus, candidate = _simple_finding()
    with get_session() as session:
        _persist(session, corpus, candidate, investigation_id=4006, context_id="ctx-once")
        session.commit()
        first = {(e.account_a, e.account_b): e.log_lr_sum for e in _edges(session, ["p1", "p2"])}

        _persist(session, corpus, candidate, investigation_id=4006, context_id="ctx-once")
        session.commit()
        second = {(e.account_a, e.account_b): e.log_lr_sum for e in _edges(session, ["p1", "p2"])}

        assert first == second, "a re-scan of one post compounded its own evidence"


def test_accumulation_can_be_switched_off_without_losing_the_finding():
    """The row is the operator's queue entry; the edges are a claim about pairs. A caller must be
    able to keep one without the other, which is also what makes the accumulation safe to make
    best-effort."""
    corpus, candidate = _simple_finding()
    with get_session() as session:
        _persist(session, corpus, candidate, investigation_id=4007,
                 context_id="ctx-no-accum", accumulate=False)
        session.commit()
        assert session.query(NetdetectFinding).filter_by(investigation_id=4007).count() == 1
        assert not [e for e in _edges(session, ["p1", "p2", "p3"])
                    if "ctx-no-accum" in (e.contexts_json or [])]


def test_recording_a_finding_publishes_nothing():
    """Persisting an internal finding is not the same act as publishing one. No share token, no
    `Campaign` row, nothing on a customer surface."""
    from app.storage.models import Campaign

    corpus, candidate = _simple_finding()
    with get_session() as session:
        before = session.query(Campaign).count()
        _persist(session, corpus, candidate, investigation_id=4008, context_id="ctx-quiet")
        session.commit()
        assert session.query(Campaign).count() == before
