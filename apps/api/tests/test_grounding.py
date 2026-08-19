"""The deterministic check on the analyst's per-account prose.

Every paragraph this system writes is a published claim about a named real person, and the product
owner posts them into comment sections. Until this existed the only control on that prose was the
protocol asking for it: the Governor's S9 lint never sees ``commenter_assessments[].assessment`` and
the comprehensive path runs ``adjudication="schema_only"``.

The load-bearing test in this file is the first one. A model that invents a quotation asserts that a
named person wrote words they never wrote, the reader cannot tell, and it is trivially checkable
against what the account actually posted.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.reasoning.grounding import (
    HARD,
    SOFT,
    WITHHELD_NOTICE,
    _sentence_shape,
    check_alias_in_prose,
    check_boilerplate,
    check_coherence,
    check_figures,
    check_phrasing,
    check_quotes,
    check_readability,
    verify_batch,
    verify_row,
)


def _account(**over) -> dict:
    base = {
        "handle": "realperson",
        "follower_count": 1200,
        "following_count": 300,
        "account_created_at": (datetime.now(timezone.utc) - timedelta(days=400)).isoformat(),
        "history_size": 42,
        "bio": "coffee, cats, and long walks",
        "recent_activity": [
            {"text": "Just got back from the farmers market, the tomatoes were unreal"},
            {"text": "Anyone else think the third act dragged? Still liked it though"},
            {"text": "Huge potential here, link in bio"},
        ],
    }
    base.update(over)
    return base


# --------------------------------------------------------------------------------------------- #
# Quotes: the check worth having if you only have one
# --------------------------------------------------------------------------------------------- #
def test_a_fabricated_quote_is_caught():
    """The model puts words in a named person's mouth. The reader cannot tell. We can."""
    v = check_quotes(
        'The account repeatedly writes "buy my crypto course now, DM me" across its history.',
        _account(),
    )
    assert [x.code for x in v] == ["quote_not_found"]
    assert v[0].severity == "hard"


def test_a_real_quote_passes():
    assert check_quotes(
        'It wrote "Huge potential here, link in bio", which is a promotional pattern.',
        _account(),
    ) == []


def test_a_quote_survives_punctuation_and_case_differences():
    """The model is allowed to normalise punctuation when quoting; that is not fabrication."""
    assert check_quotes(
        'Its own words: "just got back from the farmers market -- the tomatoes were unreal!"',
        _account(),
    ) == []


def test_a_truncated_quote_is_matched_on_its_head():
    """The protocol asks for SHORT quotes, so honest shortening must not read as invention."""
    assert check_quotes(
        'The account writes "Anyone else think the third act dragged..." in a reply.',
        _account(),
    ) == []


def test_a_short_rhetorical_quote_is_not_treated_as_an_excerpt():
    """Scare-quoting a concept is not a claim about what the account wrote."""
    assert check_quotes(
        'This is classic "engagement farming" behaviour rather than conversation.',
        _account(),
    ) == []


def test_quoting_an_account_with_no_collected_posts_is_a_hard_failure():
    """The most dangerous shape: nothing was gathered, so the quote came from somewhere else."""
    v = check_quotes('It wrote "follow me for more alpha signals every day".',
                     _account(recent_activity=[], bio=None))
    assert [x.code for x in v] == ["quote_without_evidence"]


def test_the_bio_counts_as_the_accounts_own_words():
    assert check_quotes('Its bio reads "coffee, cats, and long walks".', _account()) == []


# --------------------------------------------------------------------------------------------- #
# Figures: LLMs are unreliable at ratio and date arithmetic
# --------------------------------------------------------------------------------------------- #
def test_an_invented_follower_count_is_caught():
    v = check_figures("The account has 48,000 followers, which is out of step with its posting.",
                      _account())
    assert [x.code for x in v] == ["figure_mismatch"]
    assert "1200" in v[0].detail


def test_a_correct_follower_count_passes():
    assert check_figures("The account has 1,200 followers.", _account()) == []


def test_rounding_is_allowed_but_a_different_number_is_not():
    assert check_figures("It has about 1,180 followers.", _account()) == []
    assert check_figures("It has about 900 followers.", _account()) != []


def test_a_wrong_ratio_is_caught():
    """0.25 is the real ratio (300 following / 1200 followers). A model describing an imbalance that
    is not there is exactly the failure _CHECKABLE_CLAIMS was written for."""
    v = check_figures("Its following-to-followers ratio of 14.0 is a strong imbalance.", _account())
    assert [x.code for x in v] == ["figure_mismatch"]


def test_a_wrong_age_is_caught():
    v = check_figures("Created only 9 days old at the time of the scan.", _account())
    assert [x.code for x in v] == ["figure_mismatch"]


def test_a_correct_age_in_years_passes():
    assert check_figures("The account is about 1.1 years old.", _account()) == []


def test_a_figure_with_no_ground_truth_is_left_alone():
    """Silence in the evidence is not a licence to accuse, and not a licence to flag either."""
    assert check_figures("It has 12,000 followers.",
                         _account(follower_count=None)) == []


# --------------------------------------------------------------------------------------------- #
# False positives: every one of these was withholding a TRUE paragraph in production
#
# A HARD violation deletes a paragraph a customer paid for and replaces it with a notice, so a
# checker bug here is not a missing feature, it is the product silently refusing its own correct
# work. Each case below is a sentence the protocol actively ASKS the model to write.
# --------------------------------------------------------------------------------------------- #
def test_a_subset_of_the_history_is_not_a_wrong_post_count():
    """The 75+ gate demands subset counts, so flagging them punished the required behaviour.

    "six posts inside one hour" is consistent with a 42-post history. Only a number ABOVE the
    history describes posts that do not exist, which is why the post comparison is one-directional.
    """
    acct = _account(history_size=42)
    assert check_figures("In one hour it published 6 posts with near-identical wording.", acct) == []
    assert check_figures("Three of its 42 posts repeat the same line.", acct) == []
    assert check_figures("It posted 12 replies in a single day.", acct) == []
    # ...but a count the history cannot support is still a fabrication.
    assert [v.code for v in check_figures("It has posted 900 times.", acct)] == ["figure_mismatch"]


def test_a_ratio_stated_the_other_way_up_is_still_a_true_figure():
    """Following-to-followers is what the protocol asks for; the inverse is the same fact inverted.

    Withholding a paragraph because the model named a true ratio in the other orientation is a
    checker bug, not a fabrication.
    """
    acct = _account(follower_count=1200, following_count=300)  # following/followers = 0.25
    assert check_figures("A following-to-followers ratio of 0.25 is unremarkable.", acct) == []
    assert check_figures("A followers-to-following ratio of 4.0 is unremarkable.", acct) == []
    assert check_figures("The ratio of 300:1200 is healthy.", acct) == []
    assert [v.code for v in check_figures("A ratio of 39 to 1.", acct)] == ["figure_mismatch"]


def test_counting_accounts_is_not_a_claim_about_who_it_follows():
    """A bare "N accounts" was compared against the following count and withheld true paragraphs."""
    acct = _account(following_count=300)
    assert check_figures("It is one of 4 accounts in this batch using that phrasing.", acct) == []
    assert check_figures("Two accounts posted the same sentence.", acct) == []
    # The contamination this check exists for names the verb, and is still caught.
    assert [v.code for v in check_figures(
        "It follows 1,281 accounts while only 505 follow back.", acct)] == ["figure_mismatch"]


def test_an_alias_inside_a_quotation_is_the_accounts_words_not_a_leaked_label():
    """`[AC]\\d{1,3}` matches plenty of things real people write, and they arrive inside quotes.

    An internal label only leaks in NARRATION, so narration is what is scanned. Three of five
    realistic paragraphs were being withheld over "C4" (the broadcaster), "C19" and "the A1".
    """
    assert check_alias_in_prose('It posted "Channel 4 and C4 news are the same thing" twice.') == []
    assert check_alias_in_prose('Wrote "I got my C19 booster today" in January.') == []
    assert check_alias_in_prose('It quoted "the A1 is closed again" about the motorway.') == []
    # A label in the model's own words is still HARD: the reader has never seen the legend.
    assert [v.severity for v in check_alias_in_prose("A17 is a 2009 account.")] == [HARD]


# --------------------------------------------------------------------------------------------- #
# Phrasing: the banned-phrase lint finally reaching per-account text
# --------------------------------------------------------------------------------------------- #
def test_an_identity_assertion_is_caught():
    v = check_phrasing("This is a bot and the evidence proves that beyond question.")
    assert v and all(x.severity == "hard" for x in v)


def test_behavioural_description_passes():
    assert check_phrasing(
        "The posting pattern is much more consistent with automation than with a person."
    ) == []


# --------------------------------------------------------------------------------------------- #
# Boilerplate, readability, coherence: quality, not suppression
# --------------------------------------------------------------------------------------------- #
def test_a_paragraph_reused_across_accounts_is_flagged():
    """Five accounts with one paragraph is one finding presented five times."""
    para = ("This account shows a pattern of short promotional replies with little personal "
            "content, a follower balance that leans heavily toward following, and a history that "
            "does not read like one person's life over time, so the score reflects that mixture.")
    out = check_boilerplate({"A1": para, "A2": para, "A3": "A genuinely different paragraph here."})
    assert out["A1"] and out["A2"]
    assert out["A3"] == []
    assert all(v.severity == "soft" for v in out["A1"])


def test_distinct_paragraphs_are_not_flagged():
    out = check_boilerplate({
        "A1": "Created eleven years ago with a deep and varied posting history about cycling.",
        "A2": "A brand new account that follows thousands and has posted four promotional lines.",
    })
    assert out["A1"] == [] and out["A2"] == []


def test_jargon_is_flagged_softly():
    v = check_readability("The n-gram entropy of this corpus is anomalous relative to the prior.")
    assert [x.code for x in v] == ["jargon"]
    assert v[0].severity == "soft"


def test_plain_english_passes_readability():
    assert check_readability(
        "This account is three weeks old. It follows 4,000 people and 12 follow it back. "
        "Everything it has posted is one line long."
    ) == []


def test_a_score_above_every_dimension_is_flagged():
    """Dossier Loop step 3c: when the number is high and the dimensions are not, the number is
    wrong. Nothing enforced it until now."""
    v = check_coherence({
        "omi_score": 88, "suspicion_tier": "high",
        "signals": [{"name": "temporal", "score": 20}, {"name": "voice", "score": 30}],
    })
    assert "score_not_explained" in [x.code for x in v]


def test_a_tier_that_disagrees_with_the_score_is_flagged():
    v = check_coherence({"omi_score": 80, "suspicion_tier": "low", "signals": []})
    assert "tier_mismatch" in [x.code for x in v]


def test_a_coherent_row_is_clean():
    assert check_coherence({
        "omi_score": 30, "suspicion_tier": "moderate",
        "signals": [{"name": n, "score": 30} for n in ("a", "b", "c", "d")],
    }) == []


# --------------------------------------------------------------------------------------------- #
# The batch pass
# --------------------------------------------------------------------------------------------- #
def test_a_hard_failure_withholds_the_paragraph_but_keeps_it_for_an_admin():
    rows = [{
        "ref": "A1", "omi_score": 70, "suspicion_tier": "elevated", "confidence": 90,
        "signals": [], "assessment": 'It wrote "send me 5 ETH and I will double it" repeatedly.',
    }]
    summary = verify_batch(rows, {"A1": _account()})

    assert summary["withheld"] == 1
    assert rows[0]["assessment"] == WITHHELD_NOTICE
    assert "send me 5 ETH" in rows[0]["assessment_unverified"], "the original must survive"
    assert rows[0]["grounding"]["ok"] is False
    assert rows[0]["grounding"]["hard"][0]["code"] == "quote_not_found"


def test_a_withheld_paragraph_drags_confidence_down():
    """An unsupported paragraph is a reason to trust the rest of the row less."""
    rows = [{"ref": "A1", "omi_score": 70, "confidence": 95, "signals": [],
             "assessment": 'It wrote "buy my course now" every single day.'}]
    verify_batch(rows, {"A1": _account()})
    assert rows[0]["confidence"] <= 40


def test_a_clean_paragraph_is_untouched():
    good = ('This account is over a year old with 1,200 followers and 42 posts. It wrote '
            '"Anyone else think the third act dragged?", which reads like ordinary conversation. '
            'The innocent explanation fits and nothing here points the other way.')
    rows = [{"ref": "A1", "omi_score": 15, "suspicion_tier": "low", "confidence": 80,
             "signals": [], "assessment": good}]
    summary = verify_batch(rows, {"A1": _account()})

    assert summary["withheld"] == 0
    assert rows[0]["assessment"] == good
    assert "assessment_unverified" not in rows[0]
    assert rows[0]["grounding"]["ok"] is True


def test_soft_flags_never_suppress():
    """Boilerplate and jargon are quality signals, not grounds to refuse a finding."""
    para = ("The heuristic entropy of this account is anomalous and the corpus shows a vector of "
            "behaviour consistent with automation across its posting history over time here.")
    rows = [{"ref": "A1", "omi_score": 40, "confidence": 70, "signals": [], "assessment": para},
            {"ref": "A2", "omi_score": 41, "confidence": 70, "signals": [], "assessment": para}]
    summary = verify_batch(rows, {"A1": _account(), "A2": _account()})

    assert summary["withheld"] == 0
    assert rows[0]["assessment"] == para
    assert summary["soft_flags"] > 0


def test_one_bad_account_does_not_affect_its_neighbours():
    """Each account degrades alone, the same property the signal coercion already guarantees."""
    rows = [
        {"ref": "A1", "omi_score": 70, "confidence": 90, "signals": [],
         "assessment": 'It wrote "totally invented sentence right here" many times.'},
        {"ref": "A2", "omi_score": 10, "confidence": 90, "signals": [],
         "assessment": 'It wrote "Huge potential here, link in bio" once, which is mild.'},
    ]
    summary = verify_batch(rows, {"A1": _account(), "A2": _account()})
    assert summary["withheld"] == 1
    assert rows[1]["assessment"].startswith("It wrote")
    assert rows[1]["confidence"] == 90


def test_the_summary_reports_the_withheld_rate():
    """An operator has to be able to see the model drifting without reading every paragraph."""
    rows = [
        {"ref": f"A{i}", "omi_score": 50, "confidence": 60, "signals": [],
         "assessment": f'It wrote "fabricated line number {i} goes here" often.'}
        for i in range(4)
    ]
    summary = verify_batch(rows, {f"A{i}": _account() for i in range(4)})
    assert summary["accounts"] == 4
    assert summary["withheld"] == 4
    assert summary["withheld_rate"] == 1.0
    assert "quote_not_found" in summary["codes"]


def test_an_account_with_no_matching_evidence_still_gets_a_report():
    """A row whose alias did not resolve has no corpus. Quotes then cannot be supported, and the
    verification must say so rather than silently pass."""
    rows = [{"ref": "A9", "omi_score": 60, "confidence": 50, "signals": [],
             "assessment": 'It wrote "some quoted sentence of reasonable length here".'}]
    verify_batch(rows, {})
    assert rows[0]["grounding"]["ok"] is False


def test_verify_row_counts_what_it_checked():
    rep = verify_row(
        {"ref": "A1", "omi_score": 20, "signals": [],
         "assessment": 'It wrote "Huge potential here, link in bio" once.'},
        _account(),
    )
    assert rep.checked["quotes"] == 1
    assert rep.checked["posts_available"] == 3


# --------------------------------------------------------------------------------------------- #
# The gate
# --------------------------------------------------------------------------------------------- #
def test_the_working_notes_are_admin_only():
    """A customer shown the refused paragraph beside the notice explaining it was refused would
    just read the refused paragraph."""
    from app.reasoning.analyst import (
        ADMIN_ONLY_ACCOUNT_FIELDS,
        NEVER_PUBLIC_ACCOUNT_FIELDS,
        assessment_for_viewer,
    )

    assert NEVER_PUBLIC_ACCOUNT_FIELDS == {"grounding", "assessment_unverified"}
    # Kept OUT of the reversible feature gate: emptying that set to ship the eight-signal
    # breakdown must not also release the paragraphs verification refused.
    assert not (NEVER_PUBLIC_ACCOUNT_FIELDS & ADMIN_ONLY_ACCOUNT_FIELDS)

    served = assessment_for_viewer({"commenter_assessments": [{
        "ref": "A1", "omi_score": 70, "assessment": WITHHELD_NOTICE,
        "assessment_unverified": "the refused text", "grounding": {"ok": False},
    }]}, is_admin=False)
    row = served["commenter_assessments"][0]
    assert "assessment_unverified" not in row and "grounding" not in row
    assert row["assessment"] == WITHHELD_NOTICE


# --------------------------------------------------------------------------------------------- #
# Aliases in the investigation-level prose
#
# Live on omisphere.online: "style-match clusters (C4, C6, C1, C5, C3, C7)" and "few or no collected
# posts (A24, A20, A19)". `check_alias_in_prose` is HARD but only guards the per-account paragraphs;
# this text goes through the Governor's S9 lint, which has no alias rule.
# --------------------------------------------------------------------------------------------- #
def test_account_aliases_become_real_handles():
    """Resolving beats refusing: a handle is strictly more useful than the label the model wrote."""
    from app.reasoning.grounding import resolve_aliases_in_prose
    out = resolve_aliases_in_prose(
        "Several accounts had few or no collected posts (A24, A20, A19) so those are weak reads.",
        {"A24": "realguy", "A20": "@second", "A19": "third"})
    assert out == ("Several accounts had few or no collected posts (@realguy, @second, @third) "
                   "so those are weak reads.")


def test_cluster_labels_are_removed_because_they_have_no_public_name():
    """And the parenthetical goes with them: "()" left behind reads as a defect."""
    from app.reasoning.grounding import resolve_aliases_in_prose
    out = resolve_aliases_in_prose(
        "A small number belong to style-match clusters (C4, C6, C1, C5, C3, C7) suggesting "
        "single-author fingerprints.", {})
    assert "C4" not in out and "(" not in out
    assert out == ("A small number belong to style-match clusters suggesting single-author "
                   "fingerprints.")


def test_prose_without_aliases_is_untouched():
    from app.reasoning.grounding import resolve_aliases_in_prose
    text = "Most accounts look like ordinary partisan amplifiers or heavy reposters."
    assert resolve_aliases_in_prose(text, {"A1": "someone"}) == text


def test_an_unresolvable_account_alias_is_removed_rather_than_printed():
    """An unresolved label tells the reader nothing and looks like a bug."""
    from app.reasoning.grounding import resolve_aliases_in_prose
    out = resolve_aliases_in_prose("The pattern centres on A77 and A78.", {})
    assert "A77" not in out and "A78" not in out


# ==================================================================================================
# Cross-account contamination, the half that was reaching the page
# ==================================================================================================
# Found 2026-08-19 in a live export. `jamesthatcher_` is a 2023 account with 322 followers and 349
# following, and the product published this about them:
#
#   "A long-running account (2009) with 337 followers and 2,263 following and fifty sampled posts"
#
# Every one of those figures belongs to `unique59`, four rows away in the same batch. Two holes let
# it through, and both are about the FORM the model writes a figure in rather than about the check
# being absent:
#
#   * `_FOLLOWING_RE` matched only the verb-first order ("follows 2,263"). The number-first order
#     ("2,263 following") is what the model actually writes, on most rows, and was unchecked.
#   * No creation-date check existed in any form the model writes. "N years old" was checked;
#     "(created 2023-07-04)", "A 2009 account" and "account (2009)" were not, and those are the
#     forms the protocol's own opening-sentence rule produces.
#
# Every case in the CLEAN half below is a sentence the protocol asks for. That is the standard for
# adding to this file: a HARD rule that fires on prose the constitution demands is the rule being
# wrong, not the model.
_CONTAMINATED = {
    "handle": "jamesthatcher_", "follower_count": 322, "following_count": 349,
    "account_created_at": "2023-07-04T00:28:48Z", "history_size": 50, "recent_activity": [],
}


def _codes(text, account=_CONTAMINATED):
    return [v.code for v in check_figures(text, account)]


def test_the_live_contamination_is_caught_on_both_figures():
    served = ("A long-running account (2009) with 337 followers and 2,263 following and fifty "
              "sampled posts of opinion and retweets.")
    details = [v.detail for v in check_figures(served, _CONTAMINATED)]
    assert any("following" in d for d in details), f"following count not checked: {details}"
    assert any("2009" in d for d in details), f"creation year not checked: {details}"
    assert all(v.severity == HARD for v in check_figures(served, _CONTAMINATED))


class TestAFollowingCountIsCheckedInBothWordOrders:
    def test_number_first_is_checked(self):
        assert _codes("2,263 following") == ["figure_mismatch"]

    def test_verb_first_is_still_checked(self):
        assert _codes("follows 2,263 accounts") == ["figure_mismatch"]

    def test_the_true_number_passes_in_both_orders(self):
        assert _codes("322 followers and 349 following") == []
        assert _codes("follows 349 accounts while 322 follow back") == []

    def test_a_follower_count_is_not_read_as_a_following_count(self):
        """The trailing guard on the verb form. Without it `follows?` matches inside "followers"
        and every clean paragraph in this file failed."""
        assert _codes("322 followers") == []


class TestTheCreationDateIsChecked:
    def test_a_wrong_iso_date_is_caught(self):
        assert _codes("This account (created 2009-05-11) posts daily.") == ["figure_mismatch"]

    def test_the_right_iso_date_passes(self):
        assert _codes("This account (created 2023-07-04) posts daily.") == []

    def test_a_wrong_bare_year_is_caught(self):
        assert _codes("A 2009 account with a long history.") == ["figure_mismatch"]
        assert _codes("A long-running account (2009) with a personal voice.") == ["figure_mismatch"]

    def test_the_right_bare_year_passes(self):
        """A bare year is held only to the year. "A 2023 account" is a true statement about anything
        created in 2023, and demanding the day would withhold prose the protocol never forbade."""
        assert _codes("A 2023 account with a long history.") == []

    def test_one_wrong_date_is_reported_once(self):
        """A full date already reported must not also be reported as a bare year: one wrong date is
        one error, and a doubled violation reads to an operator as two separate faults."""
        assert len(_codes("This account (created 2009-05-11) is old.")) == 1

    def test_a_year_that_is_not_about_the_account_is_left_alone(self):
        """Years appear constantly in quoted posts and in topics. Only a year adjacent to a creation
        word or to the word "account" is a claim about the profile."""
        for ordinary in ("the 2020 election was contested",
                         "posts about the 2016 primaries",
                         'wrote "I have said this since 2011"',
                         "commentary on the 1776 project"):
            assert _codes(ordinary) == [], ordinary

    def test_an_account_with_no_creation_date_is_not_guessed_at(self):
        blank = {**_CONTAMINATED, "account_created_at": None}
        assert _codes("A 2009 account.", blank) == []


# ==================================================================================================
# The opening and closing sentences are counted separately from the paragraph
# ==================================================================================================
# Whole-paragraph Jaccard never fired on the live runs, and could not: twenty-five verdicts shared
# one opening skeleton and one closing sentence while their middles differed enough to stay far
# under the threshold.
#
# v12 banned "collecting more posts would increase confidence" as a closer. The model complied and
# built a replacement, which then closed the majority of every run: "the one observation that would
# most change this read is finding identical templated text repeated across its own posts." Banning
# a sentence teaches substitution. Counting SHAPES measures the thing that is actually wrong.
#
# SOFT throughout. A repeated opener is a writing failure, not a false claim, and withholding a true
# paragraph over a stylistic tic is the trade this file has already paid for four times.
def _batch_with_shared_skeleton(n=5):
    mids = ["It posts about football and local news most days.",
            "Its timeline is mostly reposts of political commentary with a few originals.",
            "The account writes long threads about marine biology and shares photographs.",
            "Replies dominate, mostly short reactions to sports results and weather.",
            "It shares recipes, family photographs and occasional book recommendations."]
    return {
        f"A{i + 1}": (
            f"This account (created 20{11 + i}-04-0{1 + i % 9}) has {100 * i + 7} followers and "
            f"follows {90 * i + 3}. {mids[i % len(mids)]} The one observation that would most "
            "change this read is finding identical templated text repeated across its own posts."
        )
        for i in range(n)
    }


def test_a_shared_opening_skeleton_is_reported():
    out = check_boilerplate(_batch_with_shared_skeleton())
    assert all(any(v.code == "repeated_opening" for v in vs) for vs in out.values())


def test_a_shared_closing_sentence_is_reported():
    out = check_boilerplate(_batch_with_shared_skeleton())
    assert all(any(v.code == "repeated_closing" for v in vs) for vs in out.values())


def test_the_repetition_report_is_soft_and_never_withholds():
    """A repeated opener is a writing failure, not a false claim about a person."""
    out = check_boilerplate(_batch_with_shared_skeleton())
    assert all(v.severity == SOFT for vs in out.values() for v in vs)


def test_the_shape_ignores_the_numbers_that_differ():
    """Two sentences are one template when they differ only in the figures filled into them, and no
    word-level comparison catches that because nearly every word already matches."""
    a = "This account (created 2019-04-02) has 400 followers and follows 900."
    b = "This account (created 2023-11-18) has 51 followers and follows 2,204."
    assert _sentence_shape(a) == _sentence_shape(b)


def test_genuinely_varied_verdicts_are_left_alone():
    varied = {
        "A1": ("Fourteen years of continuous posting, 3,512 followers against 4,696 following, and "
               "no posts between 02:00 and 09:00 on any day in the sample."),
        "A2": ("The timeline opens in 2019 and runs unbroken to last week, mostly reposts of county "
               "cricket results. Nothing in it is written twice."),
        "A3": ('Wrote "the ferry was late again and I have opinions" on 4 March, one of nine posts '
               "that read as one continuing complaint about the same commute."),
        "A4": ("A ratio of 51 followers to 2,204 following is the only thing here that stands out, "
               "and following widely is how many people build a feed."),
        "A5": ("Its posts are photographs of allotments, captioned in Welsh, spread across six "
               "growing seasons."),
    }
    assert all(vs == [] for vs in check_boilerplate(varied).values())


def test_a_couple_of_accounts_sharing_a_shape_is_not_a_template():
    """Some convergence is natural when every account is described from the same fields. The rule
    is aimed at the runs where it was nearly all of them, not at two."""
    batch = _batch_with_shared_skeleton(2)
    batch["A3"] = "Its posts are photographs of allotments, captioned in Welsh, over six seasons."
    batch["A4"] = "The timeline opens in 2019 and runs unbroken, mostly county cricket results."
    batch["A5"] = "Wrote \"the ferry was late again\" on 4 March, one of nine such complaints."
    assert all(not any(v.code.startswith("repeated_") for v in vs)
               for vs in check_boilerplate(batch).values())
