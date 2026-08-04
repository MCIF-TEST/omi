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
    WITHHELD_NOTICE,
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
