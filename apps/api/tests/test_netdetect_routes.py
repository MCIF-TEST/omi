"""The netdetect admin surface: running, recording, and judging.

The distinction this suite is built around is the one in the route's docstring: **recording is not
publishing**. A run stores an internal finding so it can be dismissed later and so the accumulating
graph learns from it; it mints no share token and creates no `Campaign`. Storing a lead and making a
public claim about a named person are different acts, and the tests hold them apart.

The judgement routes are the other half. Every constant in `app/netdetect` is reasoned rather than
fitted, because no labelled corpus of coordinated accounts exists and none can be bought. An
operator saying "this is a newsroom" is the only signal a later calibration can be fitted against,
which is why the reason is required and why a judged row is never deleted.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from app.storage.db import get_session
from app.storage.models import Campaign, CoordinationEdge, Investigation, NetdetectFinding
from tests.netdetect_corpora import amplifier_ring, organic_population, planted_operation


def _client() -> TestClient:
    return TestClient(app)


def _seed(slug: str, rows: list[dict], *, target: str = "post-under-scan") -> int:
    with get_session() as session:
        inv = Investigation(
            user_id=1, slug=slug, label=f"label for {slug}",
            input_url="https://x.com/i/status/9", target_id=target,
            kind="comprehensive", platform="x",
            payload_json={"commenters": rows, "platform": "x"},
        )
        session.add(inv)
        session.flush()
        session.commit()
        return inv.id


def _catchable(seed: int = 5) -> list[dict]:
    """An operation the detector actually finds, planted in an organic background."""
    return organic_population(30, seed=seed) + planted_operation(8, seed=seed + 1, discipline=0.0)


# ==================================================================================================
# Running, and what a run leaves behind
# ==================================================================================================
def test_a_run_records_its_findings_and_accumulates_their_pairs():
    """The reason recording was worth building: the detector was read-only, so the tracking layer
    that survives account rotation learned only from the older, weaker cohort detector."""
    _seed("nd_record", _catchable(), target="ctx-record")
    body = _client().post("/v1/admin/netdetect/nd_record?shuffles=20").json()

    assert body["findings"], "the fixture stopped producing a finding; the test proves nothing"
    assert body["recorded"] == len(body["findings"])
    assert body["accumulated_pairs"] > 0

    with get_session() as session:
        stored = session.query(NetdetectFinding).all()
        assert stored, "the run reported recording and nothing reached the store"
        row = stored[0]
        assert row.status == "open"
        assert row.members_json and row.member_count == len(row.members_json)
        assert row.evidence_json, "a finding was stored with no readable evidence"
        assert row.corpus_size > 0 and row.null_shuffles == 20
        assert row.context_id == "ctx-record"


def test_the_run_states_what_the_member_list_does_not_claim():
    """Candidate generation is community detection, so a finding can name an account that borders
    the group without belonging to it. Measured at roughly 7% of named members. That belongs beside
    the numbers, not in a docstring, for the same reason `/narratives` states what it cannot see."""
    _seed("nd_note", _catchable(seed=53), target="ctx-note")
    body = _client().post("/v1/admin/netdetect/nd_note?shuffles=20").json()
    note = body["membership_note"].lower()
    assert "community detection" in note
    assert "check each name" in note
    # It names the members that do not carry the finding, and says plainly that this is a pointer
    # for review rather than a per-member confidence score. A number beside a person's name is read
    # as a judgement about them.
    assert "weakly_attached" in note
    assert "verdict" in note
    assert body["findings"] and "confidence" not in body["findings"][0]


def test_the_weak_member_flags_survive_into_the_store_and_the_queue():
    """The flag exists so a reviewer can challenge one name without dismissing the finding, which
    only works if it reaches the queue they read rather than dying with the run."""
    _seed("nd_weak", _catchable(seed=59), target="ctx-weak")
    client = _client()
    run = client.post("/v1/admin/netdetect/nd_weak?shuffles=20").json()
    assert run["findings"]
    first = run["findings"][0]
    # THREE states, and the flag is what keeps them apart: checked with weak members, checked with
    # none (every member carries the finding), and not checked at all. An empty list means opposite
    # things in the second and third.
    if first["attachment_checked"]:
        assert first["attachment_note"] is None
    else:
        assert first["attachment_note"], "not checked, and no reason given"
        assert first["weakly_attached"] == []
    # A flagged account is still a MEMBER. The flag reports, it never excludes.
    for flagged in first["weakly_attached"]:
        assert flagged in first["members"]

    stored = [f for f in client.get("/v1/admin/netdetect/findings/all").json()
              if f["context_id"] == "ctx-weak"][0]
    assert stored["weakly_attached"] == first["weakly_attached"]
    assert stored["attachment_note"] == first["attachment_note"]
    assert stored["attachment_checked"] == first["attachment_checked"]
    assert stored["member_count"] == len(first["members"]), (
        "the stored member count changed, so something dropped a flagged account"
    )


def test_the_membership_note_describes_the_flag_without_selling_it_as_a_score():
    """A number beside a person's name is read as a judgement about them. This one is a pointer for
    review, and the note has to say so, including that an empty list is not an all-clear."""
    _seed("nd_note2", _catchable(seed=61), target="ctx-note2")
    body = _client().post("/v1/admin/netdetect/nd_note2?shuffles=20").json()
    note = body["membership_note"].lower()
    assert "weakly_attached" in note
    assert "pointer for review" in note
    assert "remain" in note and "members" in note
    assert "not the same as every member belonging" in note


def test_a_run_publishes_nothing():
    """Persisting an internal finding is not publishing one. The rule that a claim about a person is
    a decision somebody took, never a side effect of a page load, is about PUBLICATION."""
    _seed("nd_quiet", _catchable(seed=11), target="ctx-quiet")
    with get_session() as session:
        before = session.query(Campaign).count()

    r = _client().post("/v1/admin/netdetect/nd_quiet?shuffles=20")
    assert r.status_code == 200

    with get_session() as session:
        assert session.query(Campaign).count() == before, "a run created a campaign"
        assert not session.query(Campaign).filter(Campaign.share_token.isnot(None)).count()


def test_recording_can_be_declined_without_changing_the_answer():
    """An operator tuning thresholds re-runs constantly, and does not want every draw in the queue.
    The finding itself must be identical either way."""
    _seed("nd_norecord", _catchable(seed=17), target="ctx-norecord")
    client = _client()
    dry = client.post("/v1/admin/netdetect/nd_norecord?shuffles=20&record=false").json()
    assert dry["recorded"] == 0
    assert dry["accumulated_pairs"] == 0

    with get_session() as session:
        assert session.query(NetdetectFinding).filter_by(context_id="ctx-norecord").count() == 0
        assert not [e for e in session.query(CoordinationEdge).all()
                    if "ctx-norecord" in (e.contexts_json or [])]

    wet = client.post("/v1/admin/netdetect/nd_norecord?shuffles=20").json()
    assert [f["members"] for f in wet["findings"]] == [f["members"] for f in dry["findings"]]


def test_re_running_the_same_post_does_not_stack_rows_or_compound_evidence():
    """An operator re-runs constantly while tuning, and a re-scan of one post is the same
    observation arriving twice."""
    _seed("nd_rerun", _catchable(seed=23), target="ctx-rerun")
    client = _client()
    first = client.post("/v1/admin/netdetect/nd_rerun?shuffles=20").json()
    assert first["findings"]

    with get_session() as session:
        rows_before = session.query(NetdetectFinding).filter_by(context_id="ctx-rerun").count()
        sums_before = sorted(
            e.log_lr_sum for e in session.query(CoordinationEdge).all()
            if "ctx-rerun" in (e.contexts_json or [])
        )

    client.post("/v1/admin/netdetect/nd_rerun?shuffles=20")

    with get_session() as session:
        assert session.query(NetdetectFinding).filter_by(context_id="ctx-rerun").count() == rows_before
        sums_after = sorted(
            e.log_lr_sum for e in session.query(CoordinationEdge).all()
            if "ctx-rerun" in (e.contexts_json or [])
        )
        assert sums_after == sums_before, "a re-run compounded its own evidence"


def test_a_run_that_finds_nothing_records_nothing_and_says_it_looked():
    """"We looked and refused" is a different, more trustworthy statement than "we found nothing",
    and an empty findings list must never be read as a clean result without checking `refused`."""
    _seed("nd_clean", organic_population(30, seed=3), target="ctx-clean")
    body = _client().post("/v1/admin/netdetect/nd_clean?shuffles=20").json()
    assert body["findings"] == []
    assert body["recorded"] == 0
    assert body["refused"] is None, "the control corpus was refused rather than tested"

    with get_session() as session:
        assert session.query(NetdetectFinding).filter_by(context_id="ctx-clean").count() == 0


def test_an_investigation_with_no_commenters_is_a_conflict_not_an_empty_result():
    _seed("nd_empty", [], target="ctx-empty")
    assert _client().post("/v1/admin/netdetect/nd_empty").status_code == 409


def test_an_unknown_slug_is_a_404():
    assert _client().post("/v1/admin/netdetect/nd_does_not_exist").status_code == 404


# ==================================================================================================
# The queue and the judgements
# ==================================================================================================
def _one_finding(slug: str, ctx: str) -> dict:
    _seed(slug, _catchable(seed=31), target=ctx)
    client = _client()
    run = client.post(f"/v1/admin/netdetect/{slug}?shuffles=20").json()
    assert run["recorded"], "no finding to judge"
    listing = client.get("/v1/admin/netdetect/findings/all").json()
    return [f for f in listing if f["context_id"] == ctx][0]


def test_the_queue_carries_the_denominator_a_reviewer_needs():
    """A rarity claim with no corpus count behind it asks to be trusted rather than read, and a
    finding among 30 accounts is a different statement from the same finding among 300."""
    finding = _one_finding("nd_queue", "ctx-queue")
    assert finding["corpus_size"] > 0
    assert finding["evidence"], "a queue entry with no evidence cannot be judged"
    assert finding["evidence"][0]["corpus_count"] > 0
    assert finding["evidence"][0]["sentence"]
    assert finding["status"] == "open"
    assert finding["confirmed"] is False


def test_a_dismissal_needs_a_reason():
    """A dismissal with no stated reason records that somebody was unconvinced and nothing about
    what convinced them, which cannot be fitted against later."""
    finding = _one_finding("nd_reason", "ctx-reason")
    client = _client()
    assert client.post(
        f"/v1/admin/netdetect/findings/{finding['id']}/dismiss", json={}
    ).status_code == 422
    # A reason of spaces is an absent reason wearing a length: `min_length` passes it and it strips
    # to nothing on the way into the column.
    assert client.post(
        f"/v1/admin/netdetect/findings/{finding['id']}/dismiss", json={"reason": "   "}
    ).status_code == 422
    assert client.post(
        f"/v1/admin/netdetect/findings/{finding['id']}/confirm", json={"reason": "\n\t"}
    ).status_code == 422


def test_dismissing_records_the_judgement_and_takes_it_out_of_the_open_queue():
    finding = _one_finding("nd_dismiss", "ctx-dismiss")
    client = _client()
    out = client.post(
        f"/v1/admin/netdetect/findings/{finding['id']}/dismiss",
        json={"reason": "reporters covering one beat, all of them named on their outlets"},
    ).json()
    assert out["status"] == "dismissed"
    assert out["dismissal_reason"].startswith("reporters covering one beat")

    open_ids = [f["id"] for f in client.get("/v1/admin/netdetect/findings/all").json()]
    assert finding["id"] not in open_ids
    all_ids = [f["id"] for f in client.get("/v1/admin/netdetect/findings/all?status=all").json()]
    assert finding["id"] in all_ids, "a judged row was removed rather than kept"


def test_confirming_is_a_separate_judgement_and_is_worth_more():
    """A reservoir holding only rejections can only ever teach the detector to be quieter, which is
    not the same as teaching it to be correct."""
    finding = _one_finding("nd_confirm", "ctx-confirm")
    client = _client()
    out = client.post(
        f"/v1/admin/netdetect/findings/{finding['id']}/confirm",
        json={"reason": "same script under four unrelated posts, checked by hand"},
    ).json()
    assert out["status"] == "confirmed"
    assert out["confirmed"] is True

    confirmed = client.get("/v1/admin/netdetect/findings/all?status=confirmed").json()
    assert finding["id"] in [f["id"] for f in confirmed]


def test_a_dismissed_finding_stays_dismissed_when_the_detector_runs_again():
    """THE LOAD-BEARING TEST FOR THE RESERVOIR. Somebody who has already said "this is a newsroom"
    must not be asked again on the next re-run; silently reopening the row would make every
    dismissal worthless as the training signal it is the only source of."""
    finding = _one_finding("nd_sticky", "ctx-sticky")
    client = _client()
    client.post(
        f"/v1/admin/netdetect/findings/{finding['id']}/dismiss",
        json={"reason": "a fan community, they reply to each other constantly"},
    )

    client.post("/v1/admin/netdetect/nd_sticky?shuffles=20")

    after = [f for f in client.get("/v1/admin/netdetect/findings/all?status=all").json()
             if f["id"] == finding["id"]][0]
    assert after["status"] == "dismissed"
    assert after["dismissal_reason"].startswith("a fan community")


def test_judging_something_that_does_not_exist_is_a_404():
    client = _client()
    assert client.post(
        "/v1/admin/netdetect/findings/99999999/dismiss", json={"reason": "x"}
    ).status_code == 404
    assert client.post(
        "/v1/admin/netdetect/findings/99999999/confirm", json={"reason": "x"}
    ).status_code == 404


def test_an_adjudication_flag_survives_into_the_queue():
    """A finding resting only on families a profession shares for free is real as a statistic and
    unresolved as a claim about people. It is neither suppressed nor published: it goes to a reader,
    and the queue has to carry the reason it needs one."""
    _seed("nd_adjudicate", organic_population(30, seed=41) + amplifier_ring(
        8, seed=42, targets=3, reposts=True), target="ctx-adjudicate")
    client = _client()
    run = client.post("/v1/admin/netdetect/nd_adjudicate?shuffles=20").json()
    if not run["findings"]:
        import pytest
        pytest.skip("this corpus produced no finding on this build")

    stored = [f for f in client.get("/v1/admin/netdetect/findings/all").json()
              if f["context_id"] == "ctx-adjudicate"]
    assert stored
    for f, c in zip(stored, run["findings"]):
        assert f["needs_adjudication"] == c["needs_adjudication"]


# ==================================================================================================
# The queue has an interface
#
# The routes above shipped before any UI existed, so the only way to read or judge a finding was
# curl. That is a bigger problem here than it looks: every threshold in `app/netdetect` is reasoned
# rather than fitted, and `findings/calibration` deliberately refuses to recommend anything until
# thirty findings have been judged with at least eight of each class. Nobody produces thirty
# judgements through curl, so the ground-truth path this queue exists to fill was inert.
#
# Source-level assertions against apps/web, in the same spirit as the dispute queue's: a page whose
# only protection is a hidden nav link is not protected, and TypeScript will not tell anyone if the
# server check is dropped.
# ==================================================================================================
from pathlib import Path  # noqa: E402 — kept beside the tests that use it

_WEB = Path(__file__).resolve().parents[3] / "apps" / "web"
_PAGE_DIR = _WEB / "app" / "(app)" / "netdetect"


def test_the_finding_queue_page_exists():
    assert (_PAGE_DIR / "page.tsx").exists(), "the netdetect finding API has no interface"


def test_the_finding_queue_is_gated_on_the_server():
    """A finding names real people as running an operation together, and the queue carries other
    customers' investigation ids. There is no owner to scope any of it to, which is why it is gated
    rather than filtered, exactly as `/campaigns` and `/narratives` are."""
    src = (_PAGE_DIR / "page.tsx").read_text()
    assert "is_admin" in src
    assert "notFound()" in src
    assert "force-dynamic" in src, "a cached render would serve one user's gate result to another"


def test_the_finding_queue_link_is_admin_only_in_both_navs():
    for nav in ("sidebar.tsx", "mobile-nav.tsx"):
        src = (_WEB / "components" / "layout" / nav).read_text()
        line = next((ln for ln in src.splitlines() if "'/netdetect'" in ln), None)
        assert line is not None, f"{nav} has no link to the finding queue"
        assert "adminOnly: true" in line, f"{nav} shows the finding queue to customers"


def test_the_page_never_lets_an_empty_weak_list_read_as_an_all_clear():
    """THREE STATES, and the middle one is easy to lose. An empty `weakly_attached` means "every
    member carries this finding" when `attachment_checked` is true and "we could not tell" when it
    is false, and those are opposite statements about the people named. The page has to branch on
    the flag rather than on the list being empty."""
    src = (_PAGE_DIR / "finding-queue.tsx").read_text()
    assert "attachment_checked" in src, "the page infers membership state from an empty list"
    assert "Membership was not tested" in src
    assert "Every member carries this finding" in src

    # FOUR STATES NOW, and the fourth only became reachable when the membership test was repaired.
    # It used to key on the median contribution and abstained on exactly the findings that are
    # mostly bystanders, so a majority flag could not occur; flagging went from 18 of 81 bystanders
    # to 81 of 81. "N highlighted members ... check those names first" is no prioritisation when N
    # is most of the list, and it frames a finding that is mostly bystanders as an operation with a
    # few weak members. Those are different claims about named real people.
    assert "which is most of it" in src, (
        "the page gives the same sentence whether 2 of 20 members were flagged or 17 of 25; the "
        "second is a finding whose composition is in doubt, not a few names to check first"
    )
    # AND IT MUST NOT RESTATE THE REVIEW BANNER. `detect` sets `needs_adjudication` on exactly this
    # condition and the card renders that reason a few lines above, so for a while the page said the
    # same thing twice in almost the same words: both carried the count AND both said "rather than
    # as an operation with weak members". That is the shape this repo already fixed once on the
    # analyst progress panel, where one fact had six vocabularies. The banner judges the FINDING;
    # this sentence sits under the member list and says how to read the LIST.
    assert "rather than the group as an operation with weak members" not in src, (
        "the membership sentence has gone back to restating the review banner's interpretation; "
        "cut it to what only its position can say"
    )

    # THE SAME TRAP ON THE ADJACENT BRANCH. The card prints "Membership was not tested: <note>"
    # from `attachment_note`, and `detect`'s size-abstention review reason opened with the same
    # clause when it was first written, so an over-cap finding said one fact twice. Guarded here
    # because the two strings live in different languages and neither file can see the other.
    import inspect

    from app.netdetect import detect as _detect_mod
    _detect_src = inspect.getsource(_detect_mod)
    assert "membership was not tested:" not in _detect_src, (
        "detect's review reason opens with the clause the card already prints under the member "
        "list; lead with the judgement instead so the card does not state one fact twice"
    )

    assert "weakly_attached.length * 2 > row.members.length" in src, (
        "the majority case is not computed from the two lists, so it cannot be distinguished"
    )


def test_a_judgement_cannot_be_recorded_without_a_reason():
    """The reason is the only thing a later calibration can be fitted against. The API rejects a
    blank one; the page must not offer a path that pretends otherwise."""
    src = (_PAGE_DIR / "finding-queue.tsx").read_text()
    assert "reason.trim()" in src
    assert "judgeNetdetectFinding" in src


def test_no_number_is_rendered_beside_a_member_name():
    """The obvious per-member number ranks some bystanders ABOVE genuine operation members, so it
    was measured and refused. A flagged member is highlighted as a pointer for review and carries
    nothing numeric beside their name, because a number there is read as a judgement about a person.

    Scoped to the members block rather than the whole file: the figures in the header readouts are
    about the FINDING and are meant to be there, and a blanket search would fail on an innocent
    comment while saying nothing useful about why.
    """
    # Member names now live in the MATRIX rows, with the chip row only as the fallback for
    # findings stored before the join existed. Both are checked; the rule did not move.
    matrix = (_PAGE_DIR / "evidence-matrix.tsx").read_text()
    row_block = matrix[matrix.index("matrix.rows.map("):matrix.index("{/* One row of prose")]

    chips = (_PAGE_DIR / "finding-queue.tsx").read_text()
    chip_block = chips[chips.index(">Members<"):chips.index("mt-1.5 text-2xs text-fg-mute")]

    for name, block in (("matrix rows", row_block), ("chip fallback", chip_block)):
        for numeric in (".toFixed(", "surprise", "posterior"):
            assert numeric not in block, (
                f"the {name} render {numeric!r}. A number beside a person's name reads as a "
                f"judgement about them, and the only per-member figure available does not "
                f"separate bystanders from real members."
            )

    # The column caption DOES carry figures, and must: they are about a FEATURE, not a person.
    assert ".toFixed(" in matrix


def test_the_sweep_panel_distinguishes_all_three_outcomes():
    """"Nothing catalogued", "weighed and matched nothing", and "placed" are different statements
    about named people, and two of them present as an empty list.

    Same distinction the API draws with `nothing_catalogued` and a finding draws with
    `attachment_checked`. A panel that branched on the list being empty would tell an operator that
    a section is clean when in fact no operation has ever been catalogued to compare it against.
    """
    src = (_PAGE_DIR / "formation-sweep.tsx").read_text()
    assert "nothing_catalogued" in src, "the sweep panel cannot tell 'nobody looked' from 'no match'"
    assert "not_a_clearance" in src, (
        "the panel drops the notice saying an unplaced account is not a clean bill of health, which "
        "is exactly the result most likely to be read as a verdict it is not"
    )
    assert "truncated" in src, "a capped sweep would render as a complete one that found nothing"


def test_the_sweep_panel_is_reached_from_the_gated_page():
    """It has to hang off `page.tsx`, whose server gate is the access control. A route of its own
    would need its own gate, and this repo's rule is that the nav flag is presentation only."""
    src = (_PAGE_DIR / "page.tsx").read_text()
    assert "FormationSweep" in src
    assert not (_PAGE_DIR / "sweep").exists(), "the sweep grew its own ungated route"


def test_the_formation_catalogue_has_an_interface():
    """The sweep can place an account in a formation, and nothing could show you the formations.

    A catalogue nobody can read is a catalogue nobody curates, and these rows are what every future
    sweep is measured against.
    """
    src = (_PAGE_DIR / "formation-catalogue.tsx").read_text()
    assert "listFormations" in src
    assert "phase" in src, "phase is the column to read: dormant and resurgent live only here"
    assert "concealed" in src, (
        "the catalogue drops the posture, which is the inverted reading the whole formation layer "
        "exists to surface"
    )
    page = (_PAGE_DIR / "page.tsx").read_text()
    assert "FormationCatalogue" in page, "the catalogue is not reachable from the gated page"


def test_an_empty_catalogue_says_it_is_empty_rather_than_rendering_nothing():
    """An empty table and a table that has not loaded look identical, and one of them is a claim."""
    src = (_PAGE_DIR / "formation-catalogue.tsx").read_text()
    assert "No operation has been catalogued yet" in src


def test_the_judging_order_is_labelled_as_information_and_not_as_strength():
    """The ranking is the one thing on this page whose obvious reading is wrong.

    It orders open findings by how many thresholds their verdict would move, which is close to the
    OPPOSITE of how likely each group is to be an operation: a finding reported at every candidate
    setting flips nothing and teaches nothing, and that is the most obviously coordinated group in
    the queue. An operator reading a "#1" beside an account set as a strength rank would work the
    borderline cases believing them to be the most damning.

    The caveat exists on the API response and nobody reads an API response. It has to be in the one
    place the ordering is visible, so this asserts on the page rather than on the endpoint.
    """
    src = (_PAGE_DIR / "finding-queue.tsx").read_text()
    assert "next_to_judge" in src or "netdetectCalibration" in src, "the ranking is not fetched"
    assert "not a strength order" in src
    assert "moves {next.flips_constants} threshold" in src, (
        "the marker renders a bare rank, which reads as a strength ordering"
    )
    assert "still_needed" in src or "stillNeeded" in src, (
        "the shortfall to the fitting floor is not shown where the judging happens"
    )


def test_the_ranking_can_never_hide_the_queue():
    """A convenience over the work must not be able to take the work down with it. If the
    calibration call fails the ranking is dropped and every finding still renders, unmarked."""
    src = (_PAGE_DIR / "finding-queue.tsx").read_text()
    assert "setRanking(null)" in src, "a failed ranking fetch does not degrade to an unranked queue"
    assert "(ordered ?? rows)" in src


def test_only_the_open_queue_is_reordered():
    """Confirmed and dismissed are a record, not a work queue. Reordering a record by how much each
    row would teach is meaningless, and it would move rows under somebody rereading their own past
    judgements."""
    src = (_PAGE_DIR / "finding-queue.tsx").read_text()
    assert "filter === 'open' && ranks.size > 0" in src


def _code_only(src: str) -> str:
    """Source with comments stripped.

    A guard that scans raw source fails on the comment explaining the guard, which teaches whoever
    hits it that the rule is noise. Both guards below are about what the CODE does.
    """
    import re

    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    return "\n".join(re.sub(r"//.*$", "", line) for line in src.splitlines())


def test_the_finding_card_draws_the_join_and_not_two_flat_lists():
    """A finding is a members-by-features incidence structure. The card had been rendering two
    disconnected projections of it, a row of member chips and a list of evidence sentences, so the
    reviewer's actual question about a group of named real people, "are these the same people
    throughout or two sub-groups joined at a seam", could only be taken on faith."""
    src = (_PAGE_DIR / "finding-queue.tsx").read_text()
    assert "EvidenceMatrix" in src, "the card renders no matrix"
    matrix = (_PAGE_DIR / "evidence-matrix.tsx").read_text()

    # ONE member list, not two. The matrix's row labels ARE the member list when the join was
    # recorded; the chip row is only the fallback for findings stored before it existed.
    assert "hasHolderData" in src

    # The three-state rule. An empty grid would say these accounts share nothing, which cannot be
    # true of a finding that exists at all.
    assert "was not recorded" in matrix

    # An absent hard family is STATED. Measured, the professional-beat control is a solid block
    # with zero identity and zero network features: the solidity is the alarming part and the
    # absence is the answer, so it cannot be left undrawn.
    assert "hardPresence" in matrix
    assert "none" in matrix


def test_the_matrix_uses_no_opacity_modifier_on_a_design_token():
    """MEASURED, NOT STYLE. The palette declares its colours as bare `var(--x)`, so Tailwind emits
    no `/n` variant for them: `bg-accent/70` lands in the class list and never in the stylesheet.
    The first version of this grid rendered every cell transparent because of it.

    Scoped to this file rather than the app, because there are ~200 such uses elsewhere and fixing
    those is a palette change that would restyle every page. See CLAUDE.md.
    """
    import re

    src = _code_only((_PAGE_DIR / "evidence-matrix.tsx").read_text())
    bad = re.findall(
        r"\b(?:bg|border|text|ring|fill|stroke)-"
        r"(?:accent|accent-2|fg|fg-dim|fg-mute|border-1|border-2|border-hot|tier-[a-z]+)/\d+",
        src,
    )
    assert not bad, f"opacity modifiers that will not be generated: {sorted(set(bad))}"


def test_rule_rack_is_a_hairline_and_is_never_used_as_a_container():
    """`.rule-rack` is `height: 1px`. Used as a wrapper it collapses the box and spills its content
    over whatever follows: measured at 1px tall with the text overlapping the next element. Two
    shipped components were doing it, so this is a regression guard rather than a style rule."""
    import re

    for name in ("finding-queue.tsx", "evidence-matrix.tsx", "formation-sweep.tsx"):
        src = _code_only((_PAGE_DIR / name).read_text())
        for line in src.splitlines():
            if "rule-rack" not in line:
                continue
            assert re.search(r"<hr\b", line), (
                f"{name} uses rule-rack on something other than an <hr>: {line.strip()[:100]}"
            )
