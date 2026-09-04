"""The load-bearing suite: what the detector must NOT call a campaign.

These findings name real people, and the reports this product produces get posted publicly. A false
positive here is not a missing feature, it is an accusation against someone who did nothing. So the
controls come first and the true positive is one test at the end.

Every control is a shape the constitution names as legitimately resembling the tells
(``_CONFUSABLE_ACCOUNTS``): a fan community, a news feed, second-language writers, professionals
covering one beat. Each one is built to score 70+ across the board, because that is the state the
cohort filter guarantees: every account here already looks bad to the per-account engine, and the
question is only whether they are acting *together*.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.campaigns.detector import fuse, run
from app.campaigns.detector.types import (
    ActivitySample,
    BatchBackground,
    Cohort,
    CohortAccount,
    ThreadComment,
)

T0 = datetime(2026, 3, 1, 12, 0, 0, tzinfo=timezone.utc)


#: Shuffles for the one test here that also runs netdetect, kept low because this suite is fast
#: and the contrast it draws does not depend on the precision of the null.
SHUFFLES_FOR_NETDETECT = 24


def build(
    specs: list[dict],
    *,
    thread_times: list[datetime] | None = None,
    arrivals_complete: bool = True,
    **bg,
) -> Cohort:
    """A cohort from compact per-account specs, with a realistic full-thread background."""
    accounts = []
    created_all: list[datetime] = []
    for i, s in enumerate(specs):
        created = s.get("created")
        if created:
            created_all.append(created)
        accounts.append(CohortAccount(
            external_id=f"u{i}",
            handle=s.get("handle", f"user{i}"),
            score=s.get("score", 80.0),
            score_source="engine",
            bio=s.get("bio"),
            account_created_at=created,
            thread_comments=[ThreadComment(text=s["text"], created_at=s.get("at"))]
            if s.get("text") else [],
            activity=[
                ActivitySample(
                    text=s.get("post_text", s.get("text", "")),
                    created_at=(s.get("at") or T0) - timedelta(days=d),
                    parent_id=(s.get("targets") or [f"own{i}_{d}"])[
                        d % len(s.get("targets") or [1])
                    ] if s.get("targets") else f"own{i}_{d}",
                    source_client=s.get("client"),
                )
                for d in range(s.get("post_count", 6))
            ],
        ))
    bg.setdefault("scanned_total", max(len(specs) * 8, 40))
    bg.setdefault("thread_author_count", bg["scanned_total"])
    bg.setdefault("batch_created_at", created_all)
    if thread_times is not None:
        bg["thread_comment_times"] = thread_times
        bg["thread_arrival_total"] = len(thread_times)
    bg.setdefault("arrivals_complete", arrivals_complete)
    return Cohort(accounts=accounts, background=BatchBackground(**bg), platform="x")


def campaigns(cohort: Cohort) -> list:
    r = run.detect(cohort)
    return [f for f in r.findings if f.label == fuse.LABEL_CORROBORATED]


# =============================================================================================
# Controls. None of these may produce a campaign.
# =============================================================================================
JOURNALISTS = [
    "the filing itself is public, i have linked the docket number in the thread below",
    "worth noting the committee declined to comment when we put this to them yesterday",
    "correction on my earlier post, the figure is 4.2bn not 4.2m, apologies for that",
    "i spoke to two people in the room and their accounts differ on one material point",
    "this is the third time this quarter the same subsidiary has appeared in a filing",
    "adding context, the regulation being cited was amended in 2019 and again in 2023",
    "my colleague has the full documents, i am only reporting what has been verified",
    "we are still trying to confirm the timeline before publishing anything further",
]


def test_professionals_covering_one_beat_are_not_a_campaign():
    """Eight reporters on the same story: same topic, same hours, same platform, overlapping
    sources, all scoring 70+ because the per-account engine found them all suspicious.

    This is the exact shape that made an earlier detector in this repo score unrelated
    professionals at 1.0 (see ``detection/coordination/aggregate.py``). It is the reason the
    corroboration guard here is AND rather than OR.
    """
    specs = [
        {"text": JOURNALISTS[i], "at": T0 + timedelta(minutes=13 * i),
         "handle": f"reporter_{name}", "client": "Twitter for iPhone",
         "created": T0 - timedelta(days=3000 + i * 211, hours=i, minutes=i * 7),
         "targets": ["bigstory", "bigstory2"]}
        for i, name in enumerate(
            ["hall", "obrien", "nakamura", "silva", "ahmed", "kowalski", "dubois", "park"])
    ]
    thread = [T0 + timedelta(minutes=2 * k) for k in range(300)]
    c = build(specs, thread_times=thread,
              target_counts={"bigstory": 60, "bigstory2": 55}, scanned_total=100)
    assert campaigns(c) == []


def test_a_fan_community_is_not_a_campaign():
    """Fans genuinely share vocabulary, join in cohorts around a launch, and post repetitively.
    Recognising one is a correct finding, not a failure to find something."""
    lines = [
        "album of the year and it is not even close, track seven has not left my head",
        "been waiting six years for this tour and i finally have tickets for the march date",
        "the bridge on that second single is the best thing released this decade honestly",
        "queued outside for four hours and it was completely worth every single minute",
        "my sister got me into them in 2019 and now we are both completely obsessed",
        "the vinyl pressing sounds so much warmer than the streaming version does",
    ]
    specs = [
        {"text": lines[i], "at": T0 + timedelta(minutes=17 * i), "handle": f"fan_{i}_official",
         "client": "Twitter for Android", "created": T0 - timedelta(days=900 + i * 40, minutes=i)}
        for i in range(6)
    ]
    thread = [T0 + timedelta(minutes=3 * k) for k in range(200)]
    assert campaigns(build(specs, thread_times=thread)) == []


def test_second_language_writers_are_not_a_campaign():
    """The largest documented false-positive class in adjacent tooling. Shared non-native phrasing
    is a property of the writers, not evidence they know each other."""
    lines = [
        "i am thinking this video is very good and explain the situation very clear for us",
        "thanks you for making this, in my country we do not have this information at all",
        "this is very important topic and i am agree with most of what is said here today",
        "please can you make more video like this one, is very helpful for understand it",
        "i am watching from far away and this help me very much to know what is happening",
    ]
    specs = [
        {"text": lines[i], "at": T0 + timedelta(minutes=23 * i), "handle": f"user_{i}_2019",
         "created": T0 - timedelta(days=1200 + i * 90, hours=i * 3)}
        for i in range(5)
    ]
    thread = [T0 + timedelta(minutes=5 * k) for k in range(150)]
    assert campaigns(build(specs, thread_times=thread)) == []


def test_a_busy_thread_where_everyone_arrives_together_is_not_a_campaign():
    """A viral post. Everybody comments in the same few minutes because that is what viral means."""
    specs = [
        {"text": f"completely different opinion number {i} written in my own words entirely here",
         "at": T0 + timedelta(seconds=8 * i), "handle": f"person{i}"}
        for i in range(10)
    ]
    viral = [T0 + timedelta(seconds=0.4 * k) for k in range(3000)]
    assert campaigns(build(specs, thread_times=viral, scanned_total=800)) == []


def test_accounts_that_share_only_a_handle_shape_are_not_a_campaign():
    """Supporting evidence alone can never make a campaign, however many accounts share it."""
    specs = [
        {"text": f"my own thoughts here number {i}, nothing like what anyone else has written",
         "at": T0 + timedelta(hours=i), "handle": h}
        for i, h in enumerate(
            ["free_stuff_1122", "cool_things_3344", "best_deals_5566", "top_picks_7788"])
    ]
    thread = [T0 + timedelta(minutes=9 * k) for k in range(120)]
    found = campaigns(build(specs, thread_times=thread))
    assert found == []


def test_unrelated_high_scorers_come_back_as_lone_wolves_not_a_group():
    """Suspicious alone is not the same as acting together, and the report has to keep them
    separate or the product is just restating its own input as a discovery."""
    lines = [
        "sold my car to buy in at the top and i have regretted it every day since then",
        "whoever is running the marketing for this deserves whatever they are being paid",
        "my uncle keeps forwarding me these and i genuinely cannot make him stop doing it",
        "nothing about the tokenomics makes sense once you actually read the whitepaper",
        "been in this space since 2016 and the pattern is always exactly the same one",
    ]
    specs = [
        {"text": lines[i], "at": T0 + timedelta(hours=2 * i), "handle": f"solo{i}"}
        for i in range(5)
    ]
    thread = [T0 + timedelta(minutes=11 * k) for k in range(150)]
    r = run.detect(build(specs, thread_times=thread))
    assert [f for f in r.findings if f.label == fuse.LABEL_CORROBORATED] == []
    assert len(r.lone_high_scorers) == 5


# =============================================================================================
# The true positive. One test, and it has to pass for any of the above to mean anything.
# =============================================================================================
def test_a_real_operation_is_caught():
    """Same script, same third-party scheduler, arriving together on a quiet thread. Three
    independent families, and it must clear the gate."""
    script = "this project is the most undervalued opportunity in the space right now, do not sleep"
    burst = [T0 + timedelta(seconds=s) for s in (0, 7, 15, 22)]
    specs = [
        {"text": script, "at": burst[i], "handle": f"gains_daily_{i}",
         "client": "AutoPoster Pro", "post_count": 8,
         "created": T0 - timedelta(days=30, seconds=60 * i)}
        for i in range(4)
    ]
    quiet = [T0 + timedelta(hours=k) for k in range(-10, 10)]
    c = build(specs, thread_times=quiet + burst,
              client_counts={"AutoPoster Pro": 4}, scanned_total=60)
    found = campaigns(c)
    assert len(found) == 1
    f = found[0]
    assert sorted(f.members) == ["u0", "u1", "u2", "u3"]
    assert len(f.families_fired) >= 2
    assert "text" in f.families_fired
    assert not f.capped
    assert f.evidence, "a finding with no readable evidence is not reviewable"
    assert all(e.artifact for e in f.edges), "every edge must quote what the accounts produced"


def test_a_batch_that_is_entirely_one_operation_is_still_caught():
    """No innocent background inside the cohort at all.

    The previous algorithm in this repo could not score this case: measured, the same four-account
    operation came out at 0.590 alone and 0.998 embedded in a normal section, because everything it
    measured was relative to the batch. This detector's evidence is absolute, so the two cases
    should agree.
    """
    script = "the presale closes in six hours and the allocation is nearly gone already friends"
    burst = [T0 + timedelta(seconds=s) for s in (0, 5, 11, 18, 24)]
    specs = [
        {"text": script, "at": burst[i], "handle": f"alpha_calls_{i}",
         "client": "MassTweet", "post_count": 8}
        for i in range(5)
    ]
    quiet = [T0 + timedelta(hours=k) for k in range(-8, 8)]
    c = build(specs, thread_times=quiet + burst,
              client_counts={"MassTweet": 5}, scanned_total=5, thread_author_count=5)
    assert len(campaigns(c)) == 1


def test_an_operation_sharing_a_cohort_with_ordinary_high_scorers_names_only_the_operation():
    """THE MIXED CASE, which is the realistic one and was untested.

    Every other test in this file is either all-innocent (the controls) or all-operation. The cohort
    is whatever scored 70 or above, so in practice an operation shares it with ordinary accounts
    that merely look suspicious one at a time: old, chatty, high-volume, unremarkable.

    THIS IS THE QUESTION THAT FOUND THE BIGGEST DEFECT IN THE OTHER DETECTOR. `app/netdetect` takes
    Louvain communities wholesale and has no per-account admission test, and its amplifier-ring
    findings name 52.9% innocent accounts. This detector gates membership per account: one joins
    only when its OWN posterior link to the group clears the bar. Measured with 0, 2, 4 and 8
    ordinary high scorers added to a four-account operation, it names 4 of 4 operatives and 0
    innocents every time.

    So false naming is not intrinsic to detecting sets. It is what happens without an admission
    gate, and this codebase already contains a working one.
    """
    script = "this project is the most undervalued opportunity in the space right now, do not sleep"
    chatter = [
        "honestly not sure what to make of this one but the chart looks interesting today",
        "been following since the start and the team has delivered every single time so far",
        "people keep saying it is over and yet here we are again another green candle",
        "i sold too early last cycle and i am not making that mistake twice this time",
        "the fundamentals have not changed at all regardless of what the price is doing",
        "watching this closely, might add more if it dips under the previous support level",
        "everyone in my timeline is talking about this today which is usually a bad sign",
        "no financial advice obviously but this looks like accumulation to me right now",
    ]
    burst = [T0 + timedelta(seconds=s) for s in (0, 7, 15, 22)]

    for innocents in (2, 4, 8):
        specs = [
            {"text": script, "at": burst[i], "handle": f"gains_daily_{i}",
             "client": "AutoPoster Pro", "post_count": 8,
             "created": T0 - timedelta(days=30, seconds=60 * i)}
            for i in range(4)
        ]
        # Ordinary people who merely SCORE high: their own words, their own clients, arriving
        # minutes apart rather than seconds, and years older than the operation's accounts.
        for j in range(innocents):
            specs.append({
                "text": chatter[j % len(chatter)],
                "at": T0 + timedelta(minutes=7 * (j + 1)),
                "handle": f"realperson{j}",
                "client": f"Client{j}",
                "post_count": 40,
                "created": T0 - timedelta(days=900 + 40 * j),
            })

        quiet = [T0 + timedelta(hours=k) for k in range(-10, 10)]
        cohort = build(specs, thread_times=quiet + burst,
                       client_counts={"AutoPoster Pro": 4}, scanned_total=60)
        found = campaigns(cohort)

        assert len(found) == 1, (
            f"with {innocents} ordinary high scorers the detector reported {len(found)} campaigns; "
            f"the operation is still one group and the innocents are not a second"
        )
        named = sorted(found[0].members)
        assert named == ["u0", "u1", "u2", "u3"], (
            f"with {innocents} ordinary high scorers the campaign named {named}. Anything beyond "
            f"u0-u3 is an innocent account reported as part of an operation."
        )


def test_the_seventy_cut_is_blind_to_a_disciplined_operation_and_the_cost_is_a_cliff():
    """MEASURES A CLAIM CLAUDE.md MAKES AND NOTHING CHECKED: that the 70+ cohort filter is "blind by
    construction" to the operation most worth catching.

    It matters because of WHICH detector is wired where. The cohort detector runs automatically on
    every scan. `app/netdetect` never reads a score at all, and is admin-only and manual.

    Same accounts, same behaviour, varying only the OMI score they were given:

        op score 95 / 85 / 75  ->  cohort holds all 8, the automatic detector can see them
        op score 65 / 45 / 30  ->  cohort holds ZERO accounts

    So the claim is right and the cost is a cliff rather than a slope: one point under the cut and
    the operation disappears from the automatic path entirely. The cohort comes back EMPTY rather
    than merely incomplete, because ordinary accounts do not clear 70 either, so both passes produce
    nothing and nothing records that anything was skipped.

    THIS IS NOT AN ARGUMENT FOR RUNNING NETDETECT AUTOMATICALLY, and the two open decisions are why.
    netdetect costs nothing to run (no provider call, no model call, no credit) so the obvious move
    is to wire it into the scan path. It also names 52.9% innocent accounts on the amplifier ring,
    and running it automatically would mean naming those people automatically, without an operator
    ever choosing to look. The membership trim gates the wiring: fix who gets named first.
    """
    from app.campaigns.detector.cohort import SCORE_THRESHOLD, from_scan_rows

    import tests.netdetect_corpora as NC
    from app.netdetect import detect_from_commenters

    ring = NC.amplifier_ring(8, seed=63)
    op_ids = {r["external_id"] for r in ring}
    rows = NC.organic_population(60, seed=31) + ring

    def cohort_for(op_score: float):
        scan_rows = [
            {
                "external_id": r["external_id"],
                "handle": r.get("handle") or r["external_id"],
                "overall_probability": (op_score if r["external_id"] in op_ids else 22) / 100.0,
            }
            for r in rows
        ]
        return from_scan_rows(scan_rows, [], platform="x")

    above = cohort_for(SCORE_THRESHOLD + 5)
    assert sum(1 for a in above.accounts if a.external_id in op_ids) == len(op_ids), (
        "premise: above the cut the whole operation must reach the cohort"
    )

    below = cohort_for(SCORE_THRESHOLD - 5)
    assert not [a for a in below.accounts if a.external_id in op_ids], (
        "the operation reached the cohort while scoring under the threshold, so the filter is not "
        "what this test believes it is"
    )
    assert not below.accounts, (
        "the cohort came back non-empty, so the 'nothing at all is produced' half of this is no "
        "longer true and the note above needs revisiting"
    )

    # And the score-blind detector is unaffected, which is the whole reason it exists.
    result = detect_from_commenters(rows, shuffles=SHUFFLES_FOR_NETDETECT)
    assert any(len(set(f.members) & op_ids) >= 4 for f in result.findings), (
        "netdetect failed to find the operation, so this corpus no longer demonstrates the contrast"
    )


def test_two_operations_in_one_cohort_are_two_campaigns_and_never_one():
    """THE DETECTOR THAT RUNS ON EVERY SCAN, asked the question the fixtures never asked.

    Every scenario in this file carries at most ONE operation, so nothing had checked what happens
    when two unrelated ones land in the same 70+ cohort. That is ordinary on a contested topic, and
    the merge risk here is concrete rather than theoretical: `CampaignService.merge_clusters` unions
    any two clusters sharing a single account, which is exactly why findings are required to come
    out member-disjoint and why `record_clusters` is called once per finding.

    A merge would publish one campaign naming all eight accounts, on evidence that only ever said
    each four were running together separately. Unlike the netdetect equivalent this reaches a
    customer surface by default, because this pass fires automatically when the scan is saved.

    Measured, it separates every time, including when the two operations genuinely share features:

        shared: nothing                    2 campaigns, 4+4, 0 mixed
        shared: publishing client          2 campaigns, 4+4, 0 mixed
        shared: amplification targets      2 campaigns, 4+4, 0 mixed
        shared: client AND targets         2 campaigns, 4+4, 0 mixed

    The two scripts, handle factories, provisioning windows and arrival bursts differ, which is what
    an unrelated second operation looks like. Sharing a commodity tool is the case an operator could
    most cheaply engineer.
    """
    script_a = "this project is the most undervalued opportunity in the space right now, do not sleep"
    script_b = "the clinic closure leaves this whole district without any urgent care whatsoever today"
    burst_a = [T0 + timedelta(seconds=s) for s in (0, 7, 15, 22)]
    burst_b = [T0 + timedelta(hours=5, seconds=s) for s in (0, 6, 13, 20)]
    first = {f"u{i}" for i in range(4)}
    second = {f"u{i}" for i in range(4, 8)}

    for label, shared_client, shared_targets in (
        ("nothing", False, False),
        ("the publishing client", True, False),
        ("the amplification targets", False, True),
        ("the client and the targets", True, True),
    ):
        specs = [
            {"text": script_a, "at": burst_a[i], "handle": f"gains_daily_{i}",
             "client": "AutoPoster Pro", "post_count": 8,
             "created": T0 - timedelta(days=30, seconds=60 * i),
             "targets": ["campaign_post_0", "campaign_post_1"]}
            for i in range(4)
        ] + [
            {"text": script_b, "at": burst_b[i], "handle": f"care_voice_{i}",
             "client": "AutoPoster Pro" if shared_client else "BulkPoster Studio",
             "post_count": 8,
             "created": T0 - timedelta(days=300, seconds=60 * i),
             "targets": (["campaign_post_0", "campaign_post_1"] if shared_targets
                         else ["health_thread_0", "health_thread_1"])}
            for i in range(4)
        ]
        counts = ({"AutoPoster Pro": 8} if shared_client
                  else {"AutoPoster Pro": 4, "BulkPoster Studio": 4})
        quiet = [T0 + timedelta(hours=k) for k in range(-10, 12)]
        cohort = build(specs, thread_times=quiet + burst_a + burst_b,
                       client_counts=counts, scanned_total=60)

        found = campaigns(cohort)
        assert len(found) == 2, (
            f"sharing {label}: expected two campaigns, got {len(found)} "
            f"with sizes {sorted(len(f.members) for f in found)}"
        )
        for finding in found:
            members = set(finding.members)
            assert not (members & first and members & second), (
                f"sharing {label}: one campaign mixes both operations, naming "
                f"{len(members)} accounts as a single group"
            )
            assert len(members) == 4, (
                f"sharing {label}: a campaign carries {len(members)} members rather than its "
                f"operation's four"
            )
