"""The section an operation is big enough to hide in.

`RARITY_CEILING` drops a feature held by more than a quarter of the corpus. That is sound while the
corpus is a fair background and false when it is a comment section, which is exactly what an
operation can flood: an operation of k accounts shares its hard-family tells across ALL k members,
so those tells sit at prevalence k/n and are discarded first, before any arithmetic.

The result is inverted from intuition and from what a customer would assume. The more of the section
an operation owns, the safer it is, and the run comes back looking exactly like a clean scan.

These tests pin the blind spot, pin the diagnostic that names it, and pin what the diagnostic must
refuse to say.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import netdetect_corpora as C  # noqa: E402

from app.netdetect import detect  # noqa: E402
from app.netdetect import candidates as cand  # noqa: E402
from app.netdetect import domination as dom  # noqa: E402
from app.netdetect.features import profile_from_commenter  # noqa: E402
from app.netdetect.significance import RARITY_CEILING, Corpus  # noqa: E402
from app.netdetect.types import HARD_FAMILIES  # noqa: E402

SHUFFLES = 24


def _corpus(rows: list[dict]) -> Corpus:
    return Corpus([profile_from_commenter(r) for r in rows])


def _assess(rows: list[dict]) -> dom.Domination:
    corpus = _corpus(rows)
    return dom.assess(corpus, list(cand.communities(corpus)))


# ==================================================================================================
# The blind spot itself
# ==================================================================================================
def test_an_operation_that_owns_a_quarter_of_the_section_erases_its_own_hard_evidence():
    """THE MECHANISM, measured rather than argued. Hold the operation at a fixed size and shrink the
    background: the hard-family features that survive as rare fall to zero, and they fall first,
    because per-account text varies between members and stays rare while a shared signup week does
    not."""
    surviving = {}
    for organic in (60, 25, 15):
        rows = C.organic_population(organic, seed=17) + C.planted_operation(8, seed=9)
        corpus = _corpus(rows)
        ops = {a for a in corpus.by_id if a.startswith("op")}
        surviving[round(len(ops) / corpus.size, 2)] = sum(
            1 for f, holders in corpus.feature_accounts.items()
            if f.family in HARD_FAMILIES
            and len(holders & ops) >= len(ops) // 2
            and corpus.is_rare(f)
        )
    shares = sorted(surviving)
    assert surviving[shares[0]] > 0, "the operation had no hard evidence even in a large background"
    assert surviving[shares[-1]] == 0, (
        "the ceiling no longer suppresses hard evidence at high share; if that is a real "
        "improvement, this blind spot is closed and the diagnostic below can go"
    )


def test_the_group_is_still_clustered_correctly_it_is_the_significance_test_that_loses_it():
    """Candidate generation is not the problem, which is why the diagnostic reads the communities.

    NOT the largest community: measured, at 32% share the biggest community is still an organic
    blob and the operation is a separate, essentially pure one. That is the claim the diagnostic
    rests on, so it is the claim pinned here.
    """
    rows = C.organic_population(25, seed=17) + C.planted_operation(12, seed=9)
    corpus = _corpus(rows)
    pure = [
        members for members in cand.communities(corpus)
        if len(members) >= 4
        and sum(1 for m in members if m.startswith("op")) >= len(members) - 1
    ]
    assert pure, "the operation was not clustered into any coherent community"
    assert max(len(m) for m in pure) >= 8, (
        "the operation was scattered across communities rather than found as a group"
    )


def test_a_dominated_section_currently_reports_nothing_at_all():
    """The failure this package calls the worst kind: a run that cannot report anything looks
    exactly like a clean corpus. Pinned so that if detection ever starts working here, whoever
    changes it is told that the diagnostic's reason for existing has moved."""
    rows = C.organic_population(25, seed=17) + C.planted_operation(12, seed=9)
    result = detect(_corpus(rows), shuffles=SHUFFLES)
    assert result.findings == []
    assert result.refused is None, "the run believes it looked and found nothing"


# ==================================================================================================
# The diagnostic
# ==================================================================================================
def test_it_fires_once_the_ceiling_has_eaten_the_operations_hard_evidence():
    small = _assess(C.organic_population(25, seed=17) + C.planted_operation(8, seed=9))
    big = _assess(C.organic_population(25, seed=17) + C.planted_operation(12, seed=9))
    assert not small.unresolvable, "fired on a section where the operation is found normally"
    assert big.unresolvable
    assert big.suppressed >= dom.MIN_SUPPRESSED_HARD
    assert set(big.families) <= set(HARD_FAMILIES)
    assert big.top_prevalence > RARITY_CEILING


def test_it_is_silent_on_a_newsroom_even_when_the_newsroom_owns_the_section():
    """THE CONTROL THAT MAKES THE STATISTIC HONEST, and the reason it is restricted to the hard
    families. Ten reporters filling 40% of a small section share text, timing and a publishing
    tool: much shared behaviour, none of it the operator's own acts, and nothing suppressed."""
    beat = _assess(C.organic_population(15, seed=3) + C.professional_beat(10, seed=21))
    assert beat.suppressed == 0, f"the newsroom scored {beat.suppressed}"
    assert not beat.unresolvable


def test_it_is_silent_on_ordinary_and_viral_sections():
    for label, rows in (
        ("organic 60", C.organic_population(60, seed=17)),
        ("organic 25", C.organic_population(25, seed=17)),
        ("viral", C.organic_population(60, seed=11, viral=True)),
    ):
        d = _assess(rows)
        assert not d.unresolvable, f"{label} was called unresolvable"


def test_a_dominant_fan_community_also_fires_and_that_is_the_honest_answer():
    """NOT A FALSE POSITIVE, and the test says so because the next reader will assume it is.

    Fans converging on one artist's posts is real network evidence. When they fill 44% of a small
    section, a null built from that section cannot price it, and cannot separate them from an
    operation either. The claim this module makes is "cannot resolve", which is true of both, so
    the fandom firing is the statistic working. What would be wrong is calling either an operation.
    """
    fans = _assess(C.organic_population(15, seed=5) + C.fan_community(12, seed=33))
    assert fans.unresolvable
    assert "network" in fans.families


def test_the_notice_never_claims_an_operation_and_names_the_tool_that_still_works():
    d = _assess(C.organic_population(25, seed=17) + C.planted_operation(12, seed=9))
    said = d.sentence().lower()
    assert said
    # It must not accuse. A null it cannot trust is not evidence of anything.
    for word in ("operation is", "coordinated", "bot", "detected"):
        assert word not in said, f"the notice claims {word!r} on evidence it could not price"
    assert "cannot tell them apart" in said
    assert "community" in said, "the innocent reading is not offered"
    assert "sweep" in said, "the tool that does not depend on this corpus is not named"


def test_the_check_is_explicit_and_a_zero_is_never_read_as_resolvable():
    """Same three-state rule as `attachment_checked` and `corroboration.checked`: not run and
    nothing found are different statements about the people in this section."""
    assert dom.Domination().checked is False
    assert dom.Domination().unresolvable is False
    assert "not checked" in dom.Domination().sentence()
    assert dom.Domination(suppressed=99, checked=False).unresolvable is False


def test_detect_carries_the_verdict_even_when_it_returns_early_with_no_findings():
    """The one case that most needs saying is the case where the run finds nothing, so the
    assessment has to happen before that early return."""
    rows = C.organic_population(25, seed=17) + C.planted_operation(12, seed=9)
    result = detect(_corpus(rows), shuffles=SHUFFLES)
    assert result.findings == []
    assert result.domination is not None
    assert result.domination.checked
    assert result.domination.unresolvable


# ==================================================================================================
# The route
# ==================================================================================================
def test_the_run_route_serves_the_third_state():
    """"Clean", "refused before looking" and "looked but cannot resolve" are three different
    statements about a comment section, and two of them present as an empty findings list."""
    import inspect

    from app.routes import netdetect as routes

    src = inspect.getsource(routes)
    assert "unresolvable" in src, "the route drops the verdict at the serialiser"
    fields = routes.RunOut.model_fields
    assert "unresolvable" in fields
    assert "refused" in fields, "the two states must stay separate fields"
    # None rather than an empty string, so a caller cannot read "" as a resolved section.
    assert fields["unresolvable"].default is None


# ==================================================================================================
# The record
#
# A dominated section produces NO findings, so nothing reaches the queue and the verdict dies with
# the request. That is the same failure `NetdetectFinding` was created to fix ("its findings
# evaporated when the page closed"), and worse here, because there is no finding whose absence an
# operator could notice.
# ==================================================================================================
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app as fastapi_app  # noqa: E402
from app.netdetect.persist import persist_section  # noqa: E402
from app.storage.db import get_session  # noqa: E402
from app.storage.models import NetdetectSection  # noqa: E402


def _wipe(session):
    session.query(NetdetectSection).delete()
    session.flush()


def _unresolvable() -> dom.Domination:
    return dom.assess(*_communities(
        C.organic_population(25, seed=17) + C.planted_operation(12, seed=9)))


def _communities(rows):
    corpus = _corpus(rows)
    return corpus, list(cand.communities(corpus))


def _store(session, domination, context="post-1"):
    return persist_section(
        session, domination, investigation_id=None, context_id=context,
        platform="x", corpus_size=37,
    )


def test_an_unresolvable_section_is_written_down():
    d = _unresolvable()
    assert d.unresolvable
    with get_session() as session:
        _wipe(session)
        row = _store(session, d)
        session.commit()
        assert row is not None
        assert row.suppressed == d.suppressed
        assert row.group_size == d.group_size
        assert row.families_json == d.families
        assert row.sentence == d.sentence()
        assert row.status == "open"


def test_a_resolvable_section_withdraws_an_earlier_warning():
    """THE HALF THAT IS EASY TO FORGET. A section stops being unresolvable as soon as enough
    ordinary accounts comment under the post. A warning left standing after that is a claim about a
    comment section that is no longer true, sitting in a queue an operator is meant to trust."""
    with get_session() as session:
        _wipe(session)
        _store(session, _unresolvable())
        session.commit()
        assert session.query(NetdetectSection).count() == 1

        # The same post, re-run, now resolvable.
        assert _store(session, dom.Domination(checked=True)) is None
        session.commit()
        assert session.query(NetdetectSection).count() == 0


def test_a_reviewed_section_is_never_withdrawn_by_a_re_run():
    """Somebody's verdict is the only ground truth this system accumulates. Deleting it on a re-run
    would make reviewing worthless, the same rule a dismissed finding follows."""
    with get_session() as session:
        _wipe(session)
        row = _store(session, _unresolvable())
        row.status = "reviewed"
        row.review_note = "checked by hand: a fan community, not an operation"
        session.commit()

        assert _store(session, dom.Domination(checked=True)) is None
        session.commit()
        kept = session.query(NetdetectSection).one()
        assert kept.status == "reviewed"
        assert "fan community" in kept.review_note


def test_re_running_updates_the_row_rather_than_stacking_duplicates():
    with get_session() as session:
        _wipe(session)
        _store(session, _unresolvable())
        session.commit()
        _store(session, _unresolvable())
        session.commit()
        assert session.query(NetdetectSection).count() == 1


def test_the_route_serves_the_queue_with_the_note_that_it_is_not_a_queue_of_operations():
    with get_session() as session:
        _wipe(session)
        _store(session, _unresolvable())
        session.commit()

    body = TestClient(fastapi_app).get("/v1/admin/netdetect/sections").json()
    assert body["sections"], "the record was written and never served"
    said = body["note"].lower()
    assert "not sections where an operation was found" in said
    assert "community" in said, "the innocent reading is not offered"
    assert "sweep" in said

    row = body["sections"][0]
    assert row["suppressed"] >= dom.MIN_SUPPRESSED_HARD
    assert row["sentence"]
    # No account is ever named: the group failed the significance test.
    assert "members" not in row
    assert not any(isinstance(v, list) and any(str(x).startswith("op") for x in v)
                   for v in row.values())


def test_reviewing_needs_a_reason_that_is_not_blank():
    with get_session() as session:
        _wipe(session)
        row = _store(session, _unresolvable())
        session.commit()
        section_id = row.id

    client = TestClient(fastapi_app)
    assert client.post(f"/v1/admin/netdetect/sections/{section_id}/reviewed",
                       json={"note": "   "}).status_code == 422
    ok = client.post(f"/v1/admin/netdetect/sections/{section_id}/reviewed",
                     json={"note": "a fan community, checked by hand"})
    assert ok.status_code == 200
    assert ok.json()["status"] == "reviewed"
    assert client.get("/v1/admin/netdetect/sections?status=open").json()["sections"] == []


def test_the_page_warns_about_what_the_queue_could_not_cover():
    """A finding queue can only show what the detector NAMED. A dominated section produces no
    findings, so an empty queue and a clean queue look identical unless something says otherwise.
    Source-level, because TypeScript will not notice if the panel is dropped."""
    web = Path(__file__).resolve().parents[3] / "apps" / "web" / "app" / "(app)" / "netdetect"
    page = (web / "page.tsx").read_text()
    assert "UnresolvedSections" in page, "the page renders no warning about unresolved sections"

    panel = (web / "unresolved-sections.tsx").read_text()
    # It must never name accounts: the group failed the significance test.
    assert "members" not in panel, "the panel reaches for a member list that must not exist"
    # A verdict needs a reason, the same rule the finding queue follows.
    assert "note.trim()" in panel
    # And it must not take the page down with it.
    assert "setRows([])" in panel, "a failed load does not degrade to an empty panel"
