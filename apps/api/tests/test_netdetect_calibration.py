"""Reading the reservoir back, and refusing to fit anything until there is enough of it.

Every constant in `app/netdetect` is reasoned rather than fitted, because no labelled corpus of
coordinated accounts exists. The judgements an operator records are the only ground truth this
detector will ever accumulate, and this suite covers what is done with them.

TWO PROPERTIES CARRY THE WHOLE MODULE, and both are about restraint rather than arithmetic:

* **It reports and it never moves anything.** A threshold that retunes itself on operator clicks can
  be steered by whoever clicks, and this one decides whether named real people are reported as
  running an operation together.
* **It refuses to recommend while the reservoir is thin.** Four constants fitted against a dozen
  labels memorises the last dozen posts somebody happened to look at.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from app.netdetect import calibration as cal
from app.netdetect.detect import MIN_HARD_EVIDENCE
from app.netdetect.types import FAMILY_IDENTITY, FAMILY_NETWORK, FAMILY_TEXT, FAMILY_TIMING
from app.storage.db import get_session
from app.storage.models import NetdetectFinding


def _finding(session, *, status: str, by_family: dict, corrected_p=0.01, n=4, tag="cal"):
    row = NetdetectFinding(
        investigation_id=None,
        members_key=f"{tag}|{status}|{len(session.new)}|{by_family}",
        members_json=[f"{tag}{i}" for i in range(n)],
        member_count=n,
        platform="x",
        score=sum(by_family.values()),
        corrected_p=corrected_p,
        by_family_json=by_family,
        evidence_json=[],
        corpus_size=60,
        null_shuffles=32,
        null_threshold=6.0,
        status=status,
        dismissal_reason="because" if status != "open" else None,
    )
    session.add(row)
    session.flush()
    return row


def _wipe(session):
    session.query(NetdetectFinding).delete()
    session.flush()


# ==================================================================================================
# The refusal to fit
# ==================================================================================================
def test_a_thin_reservoir_reports_the_sweep_and_recommends_nothing():
    """Watching the reservoir fill is useful, so the sweeps still come back; an empty response would
    read as a broken endpoint rather than as an honest 'not yet'."""
    with get_session() as session:
        _wipe(session)
        for _ in range(4):
            _finding(session, status="dismissed", by_family={FAMILY_TEXT: 8.0}, tag="thin")
        session.commit()
        report = cal.build_report(session)

    assert report.sufficient is False
    assert report.recommendations == []
    assert str(cal.MIN_JUDGEMENTS) in report.insufficient_reason
    assert report.sweeps, "the sweep was withheld along with the recommendation"
    assert all(s.recommendation is None for s in report.sweeps)


def test_one_sided_evidence_is_refused_even_when_there_is_plenty_of_it():
    """A reservoir of one class can only ever teach the detector to be quieter, or louder, and
    neither is the same as teaching it to be right."""
    with get_session() as session:
        _wipe(session)
        for i in range(40):
            _finding(session, status="dismissed", by_family={FAMILY_TEXT: 8.0}, tag=f"one{i}")
        session.commit()
        report = cal.build_report(session)

    assert report.dismissed == 40 and report.confirmed == 0
    assert report.sufficient is False
    assert str(cal.MIN_PER_CLASS) in report.insufficient_reason
    assert report.recommendations == []


# ==================================================================================================
# What it recommends once there is enough
# ==================================================================================================
def _separable(session):
    """Confirmed findings with real hard-family evidence, dismissed ones with none.

    This is the professional-beat shape: statistically real, innocent, and separable only by whether
    the operator's own acts (provisioning, converging on outside targets) are in the evidence.
    """
    _wipe(session)
    for i in range(12):
        _finding(session, status="confirmed", tag=f"c{i}",
                 by_family={FAMILY_IDENTITY: 6.0, FAMILY_TEXT: 4.0})
    for i in range(24):
        # Enough hard evidence to clear the CURRENT bar and not the next one up, which is the only
        # shape a sweep can act on: a class already refused today leaves nothing to recommend.
        _finding(session, status="dismissed", tag=f"d{i}",
                 by_family={FAMILY_IDENTITY: 3.2, FAMILY_TEXT: 7.0, FAMILY_TIMING: 5.0})
    session.flush()


def test_it_names_the_constant_the_file_and_the_arithmetic():
    """A recommendation a person has to act on by hand is useless without the place to act."""
    with get_session() as session:
        _separable(session)
        session.commit()
        report = cal.build_report(session)

    assert report.sufficient is True
    assert report.recommendations, "separable evidence produced no recommendation at all"
    hard = [s for s in report.sweeps if s.constant == "MIN_HARD_EVIDENCE"][0]
    assert hard.recommendation is not None
    assert "app/netdetect/detect.py" in hard.recommendation
    assert hard.proposed is not None and hard.proposed > MIN_HARD_EVIDENCE
    assert hard.stricter_direction == "raise"


def test_a_recommendation_never_trades_away_a_confirmed_finding():
    """THE ASYMMETRY IS THE WHOLE RULE. A false positive is a claim that named real people are
    running an operation, which somebody then has to spend attention deciding is a newsroom. So the
    search is only over settings that keep every confirmed finding."""
    with get_session() as session:
        _separable(session)
        session.commit()
        report = cal.build_report(session)
        judged = cal.load_judged(session)

    confirmed_total = sum(1 for j in judged if j.confirmed)
    for sweep in report.sweeps:
        if sweep.proposed is None:
            continue
        row = [r for r in sweep.rows if r.value == sweep.proposed][0]
        assert row.confirmed_kept == confirmed_total, (
            f"{sweep.constant} was recommended at {sweep.proposed}, which drops "
            f"{confirmed_total - row.confirmed_kept} confirmed findings"
        )


def test_a_move_inside_the_noise_is_not_recommended():
    """A setting that reclassifies one or two findings is inside the noise of who happened to be
    reviewing that week, and churning a threshold for it costs more than it buys."""
    with get_session() as session:
        _wipe(session)
        for i in range(20):
            _finding(session, status="confirmed", tag=f"cc{i}",
                     by_family={FAMILY_IDENTITY: 6.0, FAMILY_TEXT: 4.0})
        for i in range(20):
            # Same shape as the confirmed ones: nothing separates them, so nothing should move.
            _finding(session, status="dismissed", tag=f"dd{i}",
                     by_family={FAMILY_IDENTITY: 6.0, FAMILY_TEXT: 4.0})
        session.commit()
        report = cal.build_report(session)

    assert report.sufficient is True
    assert report.recommendations == [], (
        "a threshold was recommended on evidence that does not separate the two classes"
    )


def test_the_family_split_says_which_evidence_argued_for_an_operation():
    with get_session() as session:
        _separable(session)
        session.commit()
        report = cal.build_report(session)

    by_name = {f.family: f for f in report.families}
    assert by_name[FAMILY_IDENTITY].separation > 0, "identity did not separate the confirmed set"
    assert by_name[FAMILY_TIMING].separation < 0, "timing did not separate the dismissed set"
    assert by_name[FAMILY_IDENTITY].hard is True
    assert by_name[FAMILY_TIMING].hard is False


def test_an_uncorrected_finding_is_never_counted_as_significant():
    """`corrected_p` NULL means "not compared against the shuffled search", and reading it as
    significant would silently restore the very search bias the null exists to remove."""
    with get_session() as session:
        _wipe(session)
        _finding(session, status="confirmed", corrected_p=None, tag="nop",
                 by_family={FAMILY_IDENTITY: 6.0, FAMILY_TEXT: 4.0})
        session.commit()
        report = cal.build_report(session)

    alpha_sweep = [s for s in report.sweeps if s.constant.startswith("alpha")][0]
    assert all(r.confirmed_kept == 0 for r in alpha_sweep.rows)


# ==================================================================================================
# It changes nothing
# ==================================================================================================
def test_building_the_report_moves_no_threshold_and_writes_no_row():
    """No constant in this package is read from the database, and none may become so. A gate that
    retunes itself on operator clicks can be steered by whoever clicks."""
    import importlib

    # `from app.netdetect import detect` gives the FUNCTION, which the package re-exports. The
    # module is what holds the constants.
    detect = importlib.import_module("app.netdetect.detect")
    sig = importlib.import_module("app.netdetect.significance")

    before = (detect.MIN_HARD_EVIDENCE, detect.MIN_FAMILIES,
              sig.MAX_SINGLE_FAMILY_SHARE, sig.MIN_FAMILY_CONTRIBUTION)
    with get_session() as session:
        _separable(session)
        session.commit()
        count = session.query(NetdetectFinding).count()
        statuses = sorted((r.id, r.status) for r in session.query(NetdetectFinding).all())

        cal.build_report(session)
        session.commit()

        assert session.query(NetdetectFinding).count() == count
        assert sorted((r.id, r.status) for r in session.query(NetdetectFinding).all()) == statuses

    assert (detect.MIN_HARD_EVIDENCE, detect.MIN_FAMILIES,
            sig.MAX_SINGLE_FAMILY_SHARE, sig.MIN_FAMILY_CONTRIBUTION) == before


def test_the_source_never_reads_a_threshold_out_of_the_database():
    """A source-level guard, in the spirit of the signal gate's. The property is that the constants
    are imported from the modules that define them and only ever compared against, and TypeScript's
    equivalent of that check does not exist here either."""
    import pathlib

    src = pathlib.Path(cal.__file__).read_text()
    for forbidden in ("session.add", "session.merge", "session.delete", "update(", "commit("):
        assert forbidden not in src, f"the calibration report performs a write: {forbidden}"


# ==================================================================================================
# The route
# ==================================================================================================
def test_the_route_carries_the_caveats_with_the_numbers():
    """A precision figure computed over whatever an operator chose to open is not the deployment's
    precision, and a number served without that sentence beside it will be quoted as if it were."""
    with get_session() as session:
        _separable(session)
        session.commit()

    body = TestClient(app).get("/v1/admin/netdetect/findings/calibration").json()
    assert body["sufficient"] is True
    assert body["caveats"], "the numbers were served with no caveats"
    joined = " ".join(body["caveats"]).lower()
    assert "not a sample" in joined or "not a sample of anything" in joined
    assert "labels the finding" in joined
    assert body["sweeps"][0]["where"].endswith(".py")
    assert body["sweeps"][0]["rows"]


def test_the_route_is_reachable_beside_the_findings_list_and_not_shadowed_by_a_slug():
    """`/{slug}` is POST and these are GET, so the declaration order is safe today. A GET added at
    `/{slug}` later would shadow both silently."""
    client = TestClient(app)
    assert client.get("/v1/admin/netdetect/findings/calibration").status_code == 200
    assert client.get("/v1/admin/netdetect/findings/all").status_code == 200


# ==================================================================================================
# Which finding to judge next
#
# The reservoir needs thirty judgements with eight of each class, and it fills one operator click at
# a time. Nothing in this system produces those judgements automatically and nothing ever will, so
# the only lever available is making the thirty count: a finding classified the same way at every
# candidate setting cannot change a fit whichever verdict it gets, and judging it is a click spent.
#
# THE ORDER IS INFORMATION, NOT SUSPICION, and the two are close to opposite. That is what the
# second test here is for, and it is the one worth breaking the build over.
# ==================================================================================================
def _unambiguous(session, tag="obvious"):
    """Enormous, hard-family, tightly corrected, spread across four families.

    Reported at every candidate setting of every constant, so a verdict on it teaches nothing. Also
    by far the highest-scoring finding in each of these fixtures, which is the point.
    """
    return _finding(
        session, status="open", tag=tag, corrected_p=0.0001,
        by_family={FAMILY_IDENTITY: 20.0, FAMILY_NETWORK: 20.0,
                   FAMILY_TEXT: 20.0, FAMILY_TIMING: 20.0},
    )


def _borderline(session, tag="border"):
    """Sits on all four boundaries: hard evidence at the bar, two families, a top-family share and a
    corrected p that each fall inside their sweep range."""
    return _finding(
        session, status="open", tag=tag, corrected_p=0.02,
        by_family={FAMILY_IDENTITY: 3.0, FAMILY_TEXT: 3.0},
    )


def test_the_ranking_leads_with_the_finding_that_would_move_the_most_constants():
    with get_session() as session:
        _wipe(session)
        _unambiguous(session)
        middling = _finding(session, status="open", tag="mid", corrected_p=0.0001,
                            by_family={FAMILY_IDENTITY: 20.0, FAMILY_TEXT: 20.0})
        border = _borderline(session)
        session.commit()
        border_id, middling_id = border.id, middling.id

    with get_session() as session:
        report = cal.build_report(session)

    named = [n.finding_id for n in report.next_to_judge]
    assert named[0] == border_id, "the finding sitting on four boundaries was not offered first"
    assert middling_id in named
    ranked = {n.finding_id: n for n in report.next_to_judge}
    assert ranked[border_id].flips_constants > ranked[middling_id].flips_constants
    assert ranked[border_id].nearest_constant
    assert "candidate settings" in ranked[border_id].why


def test_a_finding_reported_at_every_setting_is_never_offered_however_coordinated_it_looks():
    """THE ANTI-SUSPICION GUARD. The unambiguous finding has the highest score in the fixture by a
    factor of ten, and it is the one thing here that must NOT be named: it is reported whatever the
    thresholds are set to, so a label on it cannot move a fit.

    An operator who read this list as strongest-first would work the borderline cases believing them
    to be the most damning, which is exactly backwards, so the caveat travels with the numbers."""
    with get_session() as session:
        _wipe(session)
        obvious = _unambiguous(session)
        _borderline(session)
        session.commit()
        obvious_id, obvious_score = obvious.id, obvious.score

    with get_session() as session:
        report = cal.build_report(session)

    named = [n.finding_id for n in report.next_to_judge]
    assert named, "nothing was offered at all"
    assert obvious_id not in named, "the highest-scoring finding was offered as informative"
    assert obvious_score > 60.0, "the fixture stopped being the obviously-coordinated one"

    joined = " ".join(report.caveats).lower()
    assert "not a suspicion ranking" in joined
    assert "backwards" in joined


def test_a_judged_finding_is_never_offered_for_judging_again():
    """Somebody who has already ruled on a finding must not be asked twice; the list exists to spend
    the next click well, and re-offering a settled one spends it on nothing."""
    with get_session() as session:
        _wipe(session)
        settled = _finding(session, status="dismissed", tag="done", corrected_p=0.02,
                           by_family={FAMILY_IDENTITY: 3.0, FAMILY_TEXT: 3.0})
        _borderline(session)
        session.commit()
        settled_id = settled.id

    with get_session() as session:
        report = cal.build_report(session)

    assert settled_id not in [n.finding_id for n in report.next_to_judge]


def test_the_list_is_capped_because_a_queue_nobody_can_finish_is_a_queue_nobody_starts():
    with get_session() as session:
        _wipe(session)
        for i in range(cal.MAX_NEXT_TO_JUDGE + 6):
            _borderline(session, tag=f"many{i}")
        session.commit()

    with get_session() as session:
        report = cal.build_report(session)

    assert len(report.next_to_judge) == cal.MAX_NEXT_TO_JUDGE


def test_the_shortfall_is_stated_as_work_and_goes_quiet_once_the_reservoir_is_deep():
    """`insufficient_reason` explains the refusal; this says how far off it is. An operator deciding
    whether to spend an afternoon judging findings needs the number, not the argument."""
    with get_session() as session:
        _wipe(session)
        _finding(session, status="confirmed", tag="lonely",
                 by_family={FAMILY_IDENTITY: 6.0, FAMILY_TEXT: 4.0})
        session.commit()

    with get_session() as session:
        thin = cal.build_report(session)
    assert "29 more judgements" in thin.still_needed
    assert "7 more confirmed" in thin.still_needed
    assert "8 more dismissed" in thin.still_needed

    with get_session() as session:
        _separable(session)
        session.commit()

    with get_session() as session:
        full = cal.build_report(session)
    assert full.sufficient is True
    assert full.still_needed == "", "the shortfall kept being reported after it was closed"


def test_the_route_serves_the_ranking_and_the_shortfall():
    with get_session() as session:
        _wipe(session)
        _borderline(session)
        session.commit()

    body = TestClient(app).get("/v1/admin/netdetect/findings/calibration").json()
    assert body["next_to_judge"], "the ranking was computed and not served"
    first = body["next_to_judge"][0]
    assert first["flips_constants"] >= 1
    assert first["nearest_constant"]
    assert first["why"]
    assert body["still_needed"]
    assert "not a suspicion ranking" in " ".join(body["caveats"]).lower()
