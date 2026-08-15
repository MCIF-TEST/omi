"""Persistence: the payload block, the index row, the Campaign bridge, and the two passes.

Asserts against what was actually WRITTEN (rows in the database, keys in ``payload_json``) rather
than against a return value, because the return value is the thing that was already known to be
right. This is the same lesson ``coerce_comprehensive_model_output`` paid for: tests covering the
two ends of a pipeline pass happily while the middle silently drops everything.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.campaigns.detector import persist
from app.campaigns.detector import run as detector
from app.routes.scan import _merge_payloads
from app.storage.db import get_session
from app.storage.models import Campaign, CampaignDetection, CampaignMember, Investigation

T0 = datetime(2026, 3, 1, 12, 0, 0, tzinfo=timezone.utc)
SCRIPT = "this project is the most undervalued opportunity in the space right now, do not sleep"


def _commenter(i: int, prob: float, *, text: str, at: datetime, client: str | None):
    return {
        "external_id": f"u{i}",
        "handle": f"gains_daily_{i}",
        "overall_probability": prob,
        "tier": "high",
        "bio": None,
        "thread_comments": [{"text": text, "created_at": at.isoformat()}],
        "recent_activity": [
            {"text": text, "created_at": (at - timedelta(days=d)).isoformat(),
             "parent_id": f"p{d}", "source_client": client}
            for d in range(8)
        ],
    }


def coordinated_payload() -> dict:
    """Four accounts running one script through one scheduler, on a quiet thread."""
    burst = [T0 + timedelta(seconds=s) for s in (0, 7, 15, 22)]
    rows = [_commenter(i, 0.88, text=SCRIPT, at=burst[i], client="AutoPoster Pro")
            for i in range(4)]
    rows += [
        _commenter(i, 0.15, text=f"unrelated human comment number {i} about the actual video",
                   at=T0 + timedelta(hours=i), client="Twitter for iPhone")
        for i in range(4, 20)
    ]
    arrivals = [int((T0 + timedelta(hours=k)).timestamp()) for k in range(-10, 10)]
    arrivals += [int(b.timestamp()) for b in burst]
    return {
        "video": {
            "commenters": rows,
            "thread_arrivals": sorted(arrivals),
            "thread_arrival_total": len(arrivals),
        },
        "platform": "x",
    }


def make_investigation(session, slug: str, payload: dict) -> Investigation:
    inv = Investigation(
        user_id=1, slug=slug, label=f"label for {slug}",
        input_url="https://x.com/i/status/1", target_id="tweet123",
        kind="comprehensive", payload_json=payload, platform="x",
    )
    session.add(inv)
    session.flush()
    return inv


# =============================================================================================
# Pass 1
# =============================================================================================
def test_pass_one_writes_the_block_the_row_and_the_campaign():
    with get_session() as s:
        make_investigation(s, "inv_p1", coordinated_payload())

    run = detector.detect_for_investigation("inv_p1", 1, "engine")
    assert run is not None
    assert run.score_source == "engine"
    assert run.cohort_size == 4, "only the accounts at 70+ are cohort members"
    assert run.scanned_total == 20, "the background stays the whole batch"

    with get_session() as s:
        inv = s.execute(select(Investigation).where(Investigation.slug == "inv_p1")).scalar_one()
        block = inv.payload_json.get(persist.PAYLOAD_KEY)
        assert block is not None
        assert block["passes"] == 1
        assert block["findings"], "the coordinated four must be found"

        row = s.execute(
            select(CampaignDetection).where(CampaignDetection.investigation_slug == "inv_p1")
        ).scalar_one()
        assert row.cohort_size == 4
        assert row.campaign_count == 1
        assert row.status == "open"

        camps = s.execute(select(Campaign)).scalars().all()
        assert len(camps) == 1
        assert camps[0].member_count == 4
        members = s.execute(select(CampaignMember)).scalars().all()
        assert sorted(m.account_external_id for m in members) == ["u0", "u1", "u2", "u3"]


def test_a_clean_scan_writes_no_campaign():
    """The negative is the real test. A detector that cannot stay quiet is not usable."""
    lines = [
        "honestly the second half lost me completely, the argument does not hold up at all",
        "been following for six years and this is easily the best thing posted here",
        "my brother works in that industry and says the numbers quoted are way off",
        "great breakdown but you skipped where the funding actually came from",
        "watched twice and i still cannot decide whether i agree with the conclusion",
    ]
    rows = [
        _commenter(i, 0.85, text=lines[i], at=T0 + timedelta(hours=i, minutes=i * 7),
                   client="Twitter for iPhone")
        for i in range(5)
    ]
    payload = {
        "video": {
            "commenters": rows,
            "thread_arrivals": sorted(int((T0 + timedelta(hours=k)).timestamp())
                                      for k in range(24)),
            "thread_arrival_total": 24,
        },
        "platform": "x",
    }
    with get_session() as s:
        make_investigation(s, "inv_clean", payload)
        before = len(s.execute(select(Campaign)).scalars().all())

    run = detector.detect_for_investigation("inv_clean", 1, "engine")
    assert run is not None
    assert [f for f in run.findings if f.label == "corroborated"] == []

    with get_session() as s:
        row = s.execute(
            select(CampaignDetection).where(CampaignDetection.investigation_slug == "inv_clean")
        ).scalar_one()
        assert row.campaign_count == 0
        # The row that matters: a clean scan must add nothing to the durable, deployment-global
        # campaign record. Counted rather than compared to zero because these tests share a
        # database with the ones above.
        after = len(s.execute(select(Campaign)).scalars().all())
        assert after == before


# =============================================================================================
# Pass 2
# =============================================================================================
def test_pass_two_replaces_pass_one_rather_than_sitting_beside_it():
    """One stored result, never two. If both passes could publish, a reader would have to work out
    which of two verdicts about the same accounts was current."""
    with get_session() as s:
        make_investigation(s, "inv_p2", coordinated_payload())

    detector.detect_for_investigation("inv_p2", 1, "engine")

    with get_session() as s:
        inv = s.execute(select(Investigation).where(Investigation.slug == "inv_p2")).scalar_one()
        p = dict(inv.payload_json)
        p["analyst_assessment_v1"] = {
            "assessment": {
                "commenter_assessments": [
                    {"external_id": f"u{i}", "omi_score": 88 if i < 4 else 12, "assessment": "x"}
                    for i in range(20)
                ],
            },
            "provider": "test", "generated_at": "now",
        }
        inv.payload_json = p
        s.flush()

    run2 = detector.detect_for_investigation("inv_p2", 1, "analyst")
    assert run2 is not None
    assert run2.score_source == "analyst"
    assert run2.passes == 2

    with get_session() as s:
        inv = s.execute(select(Investigation).where(Investigation.slug == "inv_p2")).scalar_one()
        keys = [k for k in inv.payload_json if k.startswith("campaign_detection")]
        assert keys == [persist.PAYLOAD_KEY], "exactly one detection block, ever"
        assert inv.payload_json[persist.PAYLOAD_KEY]["passes"] == 2

        rows = s.execute(
            select(CampaignDetection).where(CampaignDetection.investigation_slug == "inv_p2")
        ).scalars().all()
        assert len(rows) == 1, "the index row is updated in place, not appended to"
        assert rows[0].passes == 2
        assert rows[0].score_source == "analyst"


def test_pass_two_no_ops_without_an_assessment():
    """Re-running on engine scores would reproduce pass 1 while overwriting its timestamp, which
    would make the queue look like it had done work it had not."""
    with get_session() as s:
        make_investigation(s, "inv_noassess", coordinated_payload())
    detector.detect_for_investigation("inv_noassess", 1, "engine")
    assert detector.detect_for_investigation("inv_noassess", 1, "analyst") is None


def test_pass_two_does_not_mint_a_second_campaign_for_the_same_group():
    with get_session() as s:
        make_investigation(s, "inv_once", coordinated_payload())
    detector.detect_for_investigation("inv_once", 1, "engine")

    with get_session() as s:
        before = len(s.execute(select(Campaign)).scalars().all())
        inv = s.execute(select(Investigation).where(Investigation.slug == "inv_once")).scalar_one()
        p = dict(inv.payload_json)
        p["analyst_assessment_v1"] = {
            "assessment": {"commenter_assessments": [
                {"external_id": f"u{i}", "omi_score": 88 if i < 4 else 12, "assessment": "x"}
                for i in range(20)]},
            "provider": "test", "generated_at": "now",
        }
        inv.payload_json = p
        s.flush()

    detector.detect_for_investigation("inv_once", 1, "analyst")

    with get_session() as s:
        after = s.execute(select(Campaign)).scalars().all()
        assert len(after) == before, "the same accounts must merge into the existing campaign"
        assert after[-1].observation_count >= 2


# =============================================================================================
# The continuation-batch defect this feature would otherwise have hit
# =============================================================================================
def test_a_continuation_batch_does_not_delete_the_analyst_assessment():
    """``_merge_payloads`` started from ``dict(new)``, so any top-level key present only in the
    stored payload was dropped. A fresh scan result never carries ``analyst_assessment_v1``, so a
    second batch was silently deleting the written analysis the customer had already paid for.

    Pre-existing defect, not introduced here, but the detection block lives in the same place and
    would have been destroyed the same way.
    """
    existing = {
        "video": {"commenters": [{"external_id": "a"}]},
        "analyst_assessment_v1": {"assessment": {"headline": "keep me"}},
        persist.PAYLOAD_KEY: {"passes": 1, "findings": []},
        "overall_tier": "low",
    }
    new = {"video": {"commenters": [{"external_id": "b"}]}, "overall_tier": "high"}
    merged = _merge_payloads(existing, new)

    assert merged["analyst_assessment_v1"]["assessment"]["headline"] == "keep me"
    assert persist.PAYLOAD_KEY in merged
    assert merged["overall_tier"] == "high", "the new batch still wins for keys it does carry"
    assert len(merged["video"]["commenters"]) == 2, "commenters still append"


# =============================================================================================
# Serialisation round trip
# =============================================================================================
def test_the_stored_block_round_trips_through_json():
    import json

    with get_session() as s:
        make_investigation(s, "inv_json", coordinated_payload())
    run = detector.detect_for_investigation("inv_json", 1, "engine")
    block = persist.to_dict(run)
    assert json.loads(json.dumps(block)) == block, "payload_json is a JSON column"


def test_inherited_timing_edges_carry_only_timing():
    with get_session() as s:
        make_investigation(s, "inv_inherit", coordinated_payload())
    run = detector.detect_for_investigation("inv_inherit", 1, "engine")
    inherited = persist.inherited_timing_edges(persist.to_dict(run))
    assert inherited, "the coordinated fixture bursts, so there is timing evidence to carry"
    assert {e.method for e in inherited} == {"burst_lockstep"}
