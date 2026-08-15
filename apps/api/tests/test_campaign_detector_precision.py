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
