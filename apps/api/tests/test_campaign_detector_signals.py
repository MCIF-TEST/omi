"""Each signal, with the positive case it exists for and the confusable shape it must refuse.

The refusals are the important half. Every one corresponds to a documented confusable account shape
(the constitution's ``_CONFUSABLE_ACCOUNTS``) or to a false positive an earlier detector in this
repo already paid for. A signal that starts firing on its refusal case is wrong even if it also
catches more real campaigns, because the cost here is naming a real person as part of an operation.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.campaigns.detector import signals
from app.campaigns.detector.types import (
    ActivitySample,
    BatchBackground,
    Cohort,
    CohortAccount,
    ThreadComment,
)

T0 = datetime(2026, 3, 1, 12, 0, 0, tzinfo=timezone.utc)

SCRIPT = "the returns on this platform have been absolutely life changing for me honestly"


def account(
    i: int,
    *,
    handle: str | None = None,
    thread_text: str | None = None,
    thread_at: datetime | None = None,
    bio: str | None = None,
    created: datetime | None = None,
    posts: list[ActivitySample] | None = None,
) -> CohortAccount:
    return CohortAccount(
        external_id=f"u{i}",
        handle=handle or f"user{i}",
        score=80.0,
        score_source="engine",
        bio=bio,
        account_created_at=created,
        thread_comments=(
            [ThreadComment(text=thread_text, created_at=thread_at)] if thread_text else []
        ),
        activity=posts or [],
    )


def cohort(accounts, **bg) -> Cohort:
    bg.setdefault("scanned_total", max(len(accounts), 1))
    return Cohort(accounts=accounts, background=BatchBackground(**bg), platform="x")


# =============================================================================================
# verbatim_echo
# =============================================================================================
def test_verbatim_echo_fires_on_a_repeated_script():
    accs = [account(i, thread_text=SCRIPT) for i in range(3)]
    edges = signals.verbatim_echo(cohort(accs, thread_author_count=50))
    assert edges, "three accounts posting one 70-char string is the signal's whole purpose"
    assert all(e.artifact for e in edges), "every edge must carry the quotable material"


def test_verbatim_echo_refuses_short_reactions():
    """'first!' and 'great video' are posted by unrelated people under every video ever made."""
    for short in ("first!", "great video", "this is so true", "lmao"):
        accs = [account(i, thread_text=short) for i in range(4)]
        edges = signals.verbatim_echo(cohort(accs, thread_author_count=50))
        assert edges == [], f"{short!r} is not evidence of anything"


def test_verbatim_echo_refuses_a_copypasta_going_around():
    """A string a quarter of the thread's authors also posted is a meme, not a script handed out.

    The share is measured over the FULL thread, including authors never selected for scoring, which
    is exactly the background the 70+ filter does not remove.
    """
    from app.campaigns.detector import textsim

    meme = "i am not saying it was aliens but it was definitely aliens my friend"
    accs = [account(i, thread_text=meme) for i in range(4)]
    c = cohort(accs, thread_author_count=100, text_author_counts={textsim.normalize(meme): 40})
    assert signals.verbatim_echo(c) == []


def test_verbatim_echo_still_fires_when_only_the_cohort_posted_it():
    from app.campaigns.detector import textsim

    accs = [account(i, thread_text=SCRIPT) for i in range(4)]
    c = cohort(accs, thread_author_count=100, text_author_counts={textsim.normalize(SCRIPT): 4})
    assert signals.verbatim_echo(c)


def test_verbatim_echo_sees_through_invisible_character_padding():
    """Padding a copy-pasted script with zero-width characters is the cheapest evasion there is."""
    padded = SCRIPT.replace(" ", "​ ", 3)
    accs = [account(0, thread_text=SCRIPT), account(1, thread_text=padded)]
    assert signals.verbatim_echo(cohort(accs, thread_author_count=50))


# =============================================================================================
# bio_echo
# =============================================================================================
def test_bio_echo_fires_on_a_shared_bio():
    bio = "crypto enthusiast | early investor | financial freedom is a mindset not a salary"
    accs = [account(i, bio=bio) for i in range(3)]
    assert signals.bio_echo(cohort(accs))


def test_bio_echo_distinguishes_absent_from_empty():
    """``None`` means the platform never told us; ``""`` means the account has no bio.

    Collapsing them would link every account whose profile fetch happened to fail.
    """
    assert signals.bio_echo(cohort([account(i, bio=None) for i in range(4)])) == []
    assert signals.bio_echo(cohort([account(i, bio="") for i in range(4)])) == []


def test_bio_echo_refuses_universal_one_liners():
    for common in ("follow me", "link in bio", "living life", "god first"):
        accs = [account(i, bio=common) for i in range(4)]
        assert signals.bio_echo(cohort(accs)) == [], common


# =============================================================================================
# burst_lockstep -- the absolute-vs-relative thesis, in two tests
# =============================================================================================
def _thread(times: list[datetime]) -> dict:
    return {
        "thread_comment_times": times,
        "thread_arrival_total": len(times),
        "arrivals_complete": True,
        "thread_author_count": len(times),
    }


def test_burst_refuses_a_viral_post():
    """200 comments a minute. Four accounts sharing a minute there is not a coincidence worth
    reporting, it is Tuesday. Without the arrival-rate null this is the single worst
    false-positive generator in the detector."""
    viral = [T0 + timedelta(seconds=0.3 * k) for k in range(4000)]
    accs = [account(i, thread_text=f"unrelated words {i}", thread_at=T0 + timedelta(seconds=10 + i * 5))
            for i in range(4)]
    assert signals.burst_lockstep(cohort(accs, **_thread(viral))) == []


def test_burst_fires_on_a_quiet_post():
    """One comment an hour, then four accounts inside twenty seconds. Same four accounts, same
    window as the viral case; only the thread's own rate differs, and that is the entire point."""
    quiet = [T0 + timedelta(hours=k) for k in range(-12, 12)]
    burst = [T0 + timedelta(seconds=s) for s in (0, 6, 13, 19)]
    accs = [account(i, thread_text=f"unrelated words {i}", thread_at=burst[i]) for i in range(4)]
    edges = signals.burst_lockstep(cohort(accs, **_thread(quiet + burst)))
    assert edges
    stat = edges[0].statistic
    assert stat and stat[0] == "p_value" and stat[1] < 1e-4


def test_burst_abstains_when_the_arrival_stream_is_partial():
    """An investigation persisted before ``video.thread_arrivals`` existed has arrivals covering
    only the scanned accounts. A rate measured over that subset is lower than the real one, which
    makes ordinary co-timing look damning, so the signal says nothing at all."""
    burst = [T0 + timedelta(seconds=s) for s in (0, 6, 13, 19)]
    accs = [account(i, thread_text=f"words {i}", thread_at=burst[i]) for i in range(4)]
    bg = _thread(burst)
    bg["arrivals_complete"] = False
    assert signals.burst_lockstep(cohort(accs, **bg)) == []


def test_burst_refuses_a_thread_too_sparse_to_measure():
    accs = [account(i, thread_text=f"words {i}", thread_at=T0) for i in range(3)]
    assert signals.burst_lockstep(cohort(accs, **_thread([T0]))) == []


# =============================================================================================
# co_target
# =============================================================================================
def _posts(targets: list[str], client: str | None = None) -> list[ActivitySample]:
    return [ActivitySample(text=f"post about {t}", parent_id=t, source_client=client)
            for t in targets]


def test_co_target_fires_on_shared_unpopular_targets():
    accs = [account(i, posts=_posts(["p1", "p2", "p3", "p4"])) for i in range(2)]
    c = cohort(accs, target_counts={"p1": 2, "p2": 2, "p3": 2, "p4": 2}, scanned_total=100)
    assert signals.co_target(c)


def test_co_target_refuses_targets_the_whole_batch_engaged():
    """Everyone in a thread about a video has that video as a target. Sharing it says nothing."""
    accs = [account(i, posts=_posts(["popular1", "popular2", "popular3"])) for i in range(2)]
    c = cohort(accs, target_counts={"popular1": 60, "popular2": 55, "popular3": 70},
               scanned_total=100)
    assert signals.co_target(c) == []


def test_co_target_needs_more_than_two_shared_targets():
    accs = [account(i, posts=_posts(["p1", "p2"])) for i in range(2)]
    c = cohort(accs, target_counts={"p1": 2, "p2": 2}, scanned_total=100)
    assert signals.co_target(c) == []


# =============================================================================================
# client_signature
# =============================================================================================
def test_client_signature_fires_on_a_shared_third_party_tool():
    accs = [account(i, posts=_posts([f"p{j}" for j in range(6)], client="AutoPoster Pro"))
            for i in range(2)]
    c = cohort(accs, client_counts={"AutoPoster Pro": 2}, scanned_total=100)
    assert signals.client_signature(c)


def test_client_signature_refuses_every_ubiquitous_client():
    """Sharing 'Twitter for iPhone' is not evidence. This list is the whole reason the signal can
    be discriminative: what remains after it is a third-party tool."""
    for common in ("Twitter for iPhone", "Twitter for Android", "Twitter Web App", "TweetDeck"):
        accs = [account(i, posts=_posts([f"p{j}" for j in range(6)], client=common))
                for i in range(3)]
        c = cohort(accs, client_counts={common: 3}, scanned_total=100)
        assert signals.client_signature(c) == [], common


def test_client_signature_abstains_without_client_data():
    """YouTube has no equivalent field. The signal says nothing rather than inventing one."""
    accs = [account(i, posts=_posts([f"p{j}" for j in range(6)], client=None)) for i in range(3)]
    assert signals.client_signature(cohort(accs)) == []


def test_client_signature_needs_the_client_to_dominate_both_accounts():
    a = account(0, posts=_posts(["p1"], client="AutoPoster Pro") + _posts(
        [f"q{j}" for j in range(9)], client="Twitter for iPhone"))
    b = account(1, posts=_posts([f"p{j}" for j in range(6)], client="AutoPoster Pro"))
    c = cohort([a, b], client_counts={"AutoPoster Pro": 2}, scanned_total=100)
    assert signals.client_signature(c) == []


# =============================================================================================
# provisioning_window
# =============================================================================================
def test_provisioning_fires_on_a_tight_window_against_a_wide_batch():
    made = [T0 - timedelta(days=400) + timedelta(seconds=s) for s in (0, 90, 200)]
    accs = [account(i, created=made[i]) for i in range(3)]
    batch = [T0 - timedelta(days=d, hours=3, minutes=17) for d in range(0, 4000, 12)]
    c = cohort(accs, batch_created_at=batch + made, scanned_total=len(batch) + 3)
    assert signals.provisioning_window(c)


def test_provisioning_refuses_date_only_timestamps():
    """Some providers return a bare date. A date-only cohort is exactly the `age_cohort` false
    positive this product already paid for once: with no sub-day resolution, "same day" is a
    property of the data format, not of the accounts."""
    day = datetime(2024, 5, 1, 0, 0, 0, tzinfo=timezone.utc)
    accs = [account(i, created=day) for i in range(5)]
    assert signals.provisioning_window(cohort(accs, batch_created_at=[day] * 5)) == []


def test_provisioning_refuses_a_platform_signup_wave():
    """If half the batch was created that week, the window mass is huge and no k is significant.
    Platform growth is not uniform and a theoretical prior would fire on every migration wave."""
    made = [T0 - timedelta(days=400) + timedelta(hours=h, minutes=7) for h in range(3)]
    accs = [account(i, created=made[i]) for i in range(3)]
    wave = [T0 - timedelta(days=400) + timedelta(minutes=13 * k) for k in range(200)]
    c = cohort(accs, batch_created_at=wave + made, scanned_total=203)
    assert signals.provisioning_window(c) == []


# =============================================================================================
# handle_template
# =============================================================================================
def test_handle_skeleton_shape():
    assert signals.handle_skeleton("john_smith8412") == "L4_L5####"
    assert signals.handle_skeleton("crypto_mike_2024") == "L6_L4_####"
    # Separators are kept, and that is what distinguishes a template from a name with digits
    # appended by the platform.
    assert signals.handle_skeleton("johnsmith") == "L9"


def test_handle_template_refuses_the_auto_append_shape():
    """The constitution is explicit that digits appended to a handle are generated by the platform
    on a signup collision and are NEVER a tell. Forget this and the signal fires on half of X."""
    accs = [account(i, handle=h) for i, h in enumerate(
        ["john1234", "mary5678", "pete9012", "anna3456"])]
    counts: dict[str, int] = {}
    for a in accs:
        sk = signals.handle_skeleton(a.handle)
        counts[sk] = counts.get(sk, 0) + 1
    assert signals.handle_template(cohort(accs, handle_skeleton_counts=counts)) == []


def test_handle_template_fires_on_a_multi_segment_template():
    accs = [account(i, handle=h) for i, h in enumerate(
        ["free_crypto_8841", "fast_profit_2213", "easy_money_9910"])]
    counts = {signals.handle_skeleton("free_crypto_8841"): 3}
    edges = signals.handle_template(cohort(accs, handle_skeleton_counts=counts, scanned_total=100))
    assert edges


def test_handle_template_refuses_a_shape_most_of_the_batch_shares():
    accs = [account(i, handle=h) for i, h in enumerate(
        ["free_crypto_8841", "fast_profit_2213", "easy_money_9910"])]
    sk = signals.handle_skeleton("free_crypto_8841")
    c = cohort(accs, handle_skeleton_counts={sk: 40}, scanned_total=100)
    assert signals.handle_template(c) == []


# =============================================================================================
# Every signal, on empty input
# =============================================================================================
def test_every_signal_survives_an_empty_cohort():
    empty = cohort([])
    for signal in signals.SIGNALS:
        assert signal(empty) == [], signal.__name__


def test_every_signal_survives_accounts_with_no_evidence_at_all():
    accs = [account(i) for i in range(4)]
    c = cohort(accs)
    for signal in signals.SIGNALS:
        assert signal(c) == [], signal.__name__
