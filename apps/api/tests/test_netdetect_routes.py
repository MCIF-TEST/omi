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
