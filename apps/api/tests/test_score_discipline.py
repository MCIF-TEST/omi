"""The methodology that makes a high score expensive to reach.

Product decision (2026-07-29): the analyst was too willing to hand out elevated and high scores. The
fix is NOT a cap on the numbers, which would just move the error, but a stricter method: start from
the base rate, separate evidence that actually discriminates from traits that are ordinary among real
people, require converging independent indicators before a high band, test the innocent explanation,
and re-check the distribution before emitting.

These assertions pin the doctrine into the compiled protocol. It is easy to soften prose by accident
while editing nearby text, and the only symptom in production would be scores drifting back up, which
nobody would notice until a customer complained that real accounts were being called bots.
"""
from __future__ import annotations

import pytest

from app.reasoning.prompts.constitution import (
    CONSTITUTION,
    CONSTITUTION_VERSION,
    BLOCKS_BY_ID,
)
from app.reasoning.prompts.master_protocol import compile_master_analyst_protocol


@pytest.fixture(scope="module")
def protocol() -> str:
    return compile_master_analyst_protocol()["text"]


# =========================================================================== #
# The block exists, is in the constitution, and is versioned
# =========================================================================== #
def test_the_score_discipline_block_is_part_of_the_constitution():
    assert "score_discipline" in BLOCKS_BY_ID
    assert any(b.id == "score_discipline" for b in CONSTITUTION)


def test_the_constitution_version_records_the_change():
    """Adding doctrine is a material protocol change, so the version moves with it. A silent edit
    would make two deployments disagree about what the analyst was told while reporting the same
    version string in every trace."""
    assert CONSTITUTION_VERSION == "v10"


def test_the_block_reaches_the_compiled_protocol(protocol):
    assert "SCORE DISCIPLINE" in protocol


# =========================================================================== #
# The five ideas that do the work
# =========================================================================== #
def test_the_base_rate_is_stated(protocol):
    """Without a prior, every unusual-looking account reads as suspicious. The protocol has to say
    out loud that most commenters are real."""
    assert "BASE RATE" in protocol
    assert "large majority of accounts are real people" in protocol


def test_the_asymmetry_of_the_two_errors_is_stated(protocol):
    """A false accusation is the expensive error, and the model has to know which way to lean when
    the evidence is balanced."""
    assert "THE TWO ERRORS ARE NOT EQUAL" in protocol
    assert "the lower score is the correct answer" in protocol


@pytest.mark.parametrize("ambient", [
    "a low follower count", "a new account", "few posts", "no bio", "no verification",
    "emoji", "agreeing with the post", "consistent times of day",
])
def test_the_ambient_traits_are_named_individually(protocol, ambient):
    """Naming them one by one matters. A general instruction to "be careful" does not stop a model
    reading a 3-follower account as a bot; an explicit list does. Second-language writing is the one
    with the worst fairness consequences if it is treated as a tell."""
    assert ambient in protocol


def test_fluent_writing_is_explicitly_not_a_tell(protocol):
    """The trap that would systematically misjudge people who write well, and people writing in a
    second language, who often write more formally rather than less."""
    assert "many people write well" in protocol
    assert "second-language" in protocol
    assert "MORE formally, not less" in protocol


def test_ambient_traits_cannot_reach_the_high_bands(protocol):
    """However many ordinary traits are stacked up, they do not add to an accusation."""
    assert "may NEVER take an account above the moderate band" in protocol


def test_the_discriminative_evidence_is_defined_separately(protocol):
    """The counterpart to the ambient list: what genuinely is hard to explain innocently."""
    assert "WHAT IS ACTUALLY DISCRIMINATIVE" in protocol
    for tell in ("near-verbatim text reused across this account's OWN posts",
                 "a scheduler is a better explanation than a person",
                 "no topical continuity",
                 "follow-for-follow, link in bio, DM to earn"):
        assert tell in protocol


def test_the_bands_require_converging_independent_evidence(protocol):
    """The operational core. 50 or more needs two independent discriminative indicators; 75 or more
    needs several plus a reason the innocent explanation fails."""
    assert "CONVERGENCE, BY BAND" in protocol
    assert "TWO INDEPENDENT" in protocol
    # Independence has to be spelled out or one observation restated three times counts as three.
    assert "three restatements of one observation are ONE indicator" in protocol


def test_the_alternative_explanation_test_gates_the_elevated_band(protocol):
    """The single most effective debiasing device here: before accusing, say what the innocent
    reading is and point at the cell that rules it out."""
    assert "ALTERNATIVE-EXPLANATION TEST BEFORE ANY SCORE OF 50 OR MORE" in protocol
    assert "If no cell rules it out" in protocol


def test_thin_evidence_caps_the_score(protocol):
    """Absence of evidence is not evidence, and how much was collected is a fact about the SCAN.

    The old rule only covered a history "never collected", which left a hole the live export fell
    through in both directions: five sparse posts produced a 62 and eight produced a 78, while
    accounts with zero posts scattered from 3 to 34 because nothing said where they should land.
    The ceiling is now graduated and the zero-post case is pinned to a narrow band.
    """
    assert "HOW MUCH HISTORY YOU HAVE SETS A HARD CEILING" in protocol
    assert "ZERO POSTS COLLECTED" in protocol
    assert "score 10 to 20 and confidence 20 or less" in protocol
    assert "EXACTLY ONE POST" in protocol and "ceiling 39" in protocol
    assert "2 TO 14 POSTS" in protocol and "ceiling 49" in protocol
    assert "15 OR MORE POSTS" in protocol
    # Two accounts we learned nothing about must not come out 30 points apart.
    assert "must not come out 30 points apart" in protocol


def test_reposting_is_ambient_not_a_tell(protocol):
    """The single biggest calibration defect in the live data.

    Of ~90 accounts scored at 50 or above, roughly 75 rested on "the sampled posts are almost
    entirely reposts". The constitution already capped ambient traits at the moderate band but never
    named reposting as one, so the model was not disobeying: it had never been told.
    """
    assert "REPOSTING OR QUOTE-POSTING AS MOST OF WHAT THE ACCOUNT DOES" in protocol
    assert "A MOSTLY-REPOST TIMELINE IS NOT A FINDING" in protocol
    assert "Reposting is what the button is for" in protocol
    # The exact phrasings the live verdicts used to justify elevated scores, named and disowned.
    for phrase in ("amplifier than a personal timeline", "a message relay", "a broadcast feed"):
        assert phrase in protocol, f"the protocol must name and reject {phrase!r}"
    assert "may not on their own carry an account past 49" in protocol


def test_the_heavy_reposter_is_a_named_confusable_shape(protocol):
    """A generic instruction to be careful does not stop a model reading a retweeter as a farm.

    willowpete (2010, 435 followers / 213 following) and Trucker238 (2010, 607 / 616) were both
    scored 66 on repost share alone. Both are the ordinary shape this entry describes.
    """
    assert "THE HEAVY REPOSTER" in protocol
    assert "is a person with an opinion and a phone" in protocol


def test_nothing_reaches_the_top_band_without_a_mechanical_tell(protocol):
    """4ucmikey scored 86 naming zero mechanical tells: a 2011 account, 234 followers against 191
    following, elevated purely for reposting politics. The top band is now a gate, not a count."""
    assert "THE MECHANICAL GATE" in protocol
    assert "NOTHING REACHES 75 WITHOUT ONE" in protocol
    for tell in ("the same or near-identical text on two or more of this account's OWN posts",
                 "a posting rhythm a person does not produce",
                 "an explicit commercial or engagement pitch",
                 "a numbered or templated campaign sequence",
                 # v11 added two, both quotable and both from the research: a resold aged account
                 # shows as a break in its own continuity, and the one reliable AI tell is the
                 # generator's own boilerplate left in the text.
                 "a break in the account's own continuity",
                 "machine boilerplate in the account's own text"):
        assert tell in protocol, f"the gate must list {tell!r}"
    assert "can never BE the mechanical tell" in protocol


def test_the_rhythm_tell_carries_a_method_and_not_just_a_name(protocol):
    """The bundle has always shipped a created_at per post and the protocol never said to read it,
    so 'scheduler-regular' was a vibe the model could assert without arithmetic. The tell now names
    what to compute and what a human pattern looks like, so it can be checked by a reader."""
    assert "WORK IT OUT from the" in protocol and "created_at" in protocol
    assert "no multi-hour quiet period" in protocol
    # The human inverse has to travel with it or the method just manufactures a new false positive.
    assert "posting at similar times each day is a routine" in protocol


def test_a_single_dimension_cannot_carry_a_high_score(protocol):
    """The per-account mirror of the engine's single-axis cap: one alarming axis is one observation."""
    assert "ONE DIMENSION CANNOT CARRY A HIGH SCORE" in protocol


def test_scores_do_not_spread_between_accounts(protocol):
    """A suspicious neighbour is not evidence. The worked example used to nudge one account up for
    resembling another, which is exactly the reasoning this forbids."""
    assert "NO CONTAGION BETWEEN ACCOUNTS" in protocol
    assert "A suspicious section never raises an individual's score" in protocol


def test_the_distribution_self_check_runs_before_emitting(protocol):
    """The backstop that catches a whole run drifting high, which is the failure mode a per-account
    rule cannot see."""
    assert "CHECK THE DISTRIBUTION BEFORE YOU EMIT" in protocol
    assert "more often a calibration failure than a captured section" in protocol
    # And it is wired into the method, not only asserted as doctrine.
    assert "DISTRIBUTION CHECK" in protocol


def test_ties_break_downward(protocol):
    assert "NEVER ROUND UP" in protocol
    assert "take the lower" in protocol


# =========================================================================== #
# The worked example has to model the doctrine, because it teaches harder than the rules
# =========================================================================== #
def test_the_worked_example_does_not_inflate_a_score_from_a_neighbour(protocol):
    """A3 used to sit at 55 "elevated" explicitly because its wording echoed another promotional
    account, which is the contagion the protocol forbids and a demonstration of the exact overclaim
    this change is meant to stop. It is now a capped moderate read on its own thin evidence."""
    assert "which nudges the score up" not in protocol
    assert "loosely echoes another promotional account" not in protocol
    assert "nudges the read up slightly" not in protocol
    # A3 now demonstrates the zero-post floor rather than a mid-band read on no evidence.
    assert '"ref": "A3", "omi_score": 14, "suspicion_tier": "low", "confidence": 12' in protocol


def test_the_worked_example_explains_its_own_cap(protocol):
    """A3 models the required sentence for an account with NO collected history: say plainly that
    nothing was observed, refuse to read anything into the gap, and name what would settle it."""
    assert "None of this account's posts were collected" in protocol
    assert "A missing history is a gap in what was gathered, not a mark against the account" in protocol


def test_the_worked_example_demonstrates_the_heavy_reposter(protocol):
    """Models copy examples over rules, so the shape that was being misjudged has to appear as a
    worked case scored low, not only as a prohibition in the constitution."""
    assert '"ref": "A4", "omi_score": 22, "suspicion_tier": "low"' in protocol
    assert "Forty-six of the fifty collected posts are reposts" in protocol
    assert "That is a heavy reposter, which is how a great many real people use the platform" in protocol
    # And it must show the reasoning that keeps it low, not merely assert the number. v11 makes that
    # reasoning arithmetic rather than an impression: the example states the gap range and the
    # nightly quiet period, which is what the model is being asked to do on every account.
    assert "nothing at all lands between 01:00 and 08:00 on any day" in protocol
    assert "which is a person who sleeps rather than a scheduler that does not" in protocol
    # The no-history case (A3) keeps its own hedge, in the zero-post wording.
    assert "a real person who joined last month looks like" in protocol


def test_the_high_scoring_example_shows_three_independent_observations_in_its_prose(protocol):
    """The discipline must not have flattened the example into uselessness. A2 at 82 remains a
    demonstration of several independent tells landing together, and it says so, so the model learns
    to justify the band rather than just assert it."""
    assert '"ref": "A2", "omi_score": 82, "suspicion_tier": "high"' in protocol
    a2 = protocol.split('"ref": "A2"', 1)[1][:2600]
    assert "the identical sentence" in a2                  # semantic
    assert "390 to 1" in a2                                # profile, computed
    assert "created 9 days before this post" in a2         # maturity
    # v11: A2 now also demonstrates the one AI tell that is real, quoted rather than inferred from
    # style, because the example is what the model copies.
    assert "As an AI language model, I cannot" in a2
    assert "two different kinds of evidence" in a2
    assert "which is why this sits high rather than moderate" in a2


# =========================================================================== #
# Checkable claims (v10). These exist because per-account prose gets published,
# about named real accounts, where a wrong claim is both a harm and a liability.
# =========================================================================== #
def test_the_checkable_claims_block_is_part_of_the_constitution():
    assert "checkable_claims" in BLOCKS_BY_ID
    assert any(b.id == "checkable_claims" for b in CONSTITUTION)


def test_figures_must_be_computed_and_stated_not_eyeballed(protocol):
    """LLMs are unreliable at ratio and date arithmetic and will happily describe "a huge following
    imbalance" that is not there. Forcing the computed number both improves the reasoning and makes
    the claim auditable by whoever reads it."""
    assert "COMPUTE, DO NOT EYEBALL" in protocol
    assert "following-to-followers ratio" in protocol
    assert "a comparison you have not actually computed is not evidence" in protocol


def test_text_claims_require_a_verbatim_quote(protocol):
    """A quote can be checked by anyone; a paraphrase is an opinion. This is the single strongest
    thing a published claim can carry."""
    assert "QUOTE, DO NOT PARAPHRASE" in protocol
    assert "If you cannot quote it, you cannot claim it" in protocol


def test_the_hedge_must_be_in_the_sentence_not_only_the_number(protocol):
    """The failure this prevents: a confident-sounding sentence carrying a low confidence score gets
    quoted without the score, and then it is simply an overclaim in someone's feed.

    It now also pins WHERE the hedge goes. Live output ended roughly 60% of verdicts on a trailing
    apology ("collecting more posts would increase confidence"), which is the hedge in the wrong
    place: the last line is the one a reader remembers, and closing on the analysis being
    insufficient tells someone who just paid that they got nothing."""
    assert "THE HEDGE GOES IN THE WORDS" in protocol
    assert "INSIDE the sentence" in protocol
    assert "Do not save it for the end" in protocol


def test_every_serious_claim_names_what_would_overturn_it(protocol):
    assert "SAY WHAT WOULD OVERTURN IT" in protocol
    assert "separates an analytical finding" in protocol


def test_identity_and_intent_are_never_assertable(protocol):
    """The line between a finding and an accusation. The evidence can narrow whether behaviour is
    automated; it can never establish who owns an account or that anyone was paid."""
    assert "NEVER ASSERT IDENTITY OR INTENT" in protocol
    # The rule names the forbidden forms verbatim so the model can pattern-match against them.
    for forbidden in ("This account IS a bot", "this is a paid troll", "they were hired to"):
        assert forbidden in protocol
    # And gives the correct replacements, which is what makes the rule actionable.
    assert "behaves in a way consistent with" in protocol
    assert "difficult to explain as ordinary use" in protocol


def test_the_limits_of_the_evidence_are_stated_explicitly(protocol):
    """Guards the most tempting overreach: implying knowledge of ownership, payment, networks, DMs,
    or other platforms, none of which are in the bundle."""
    assert "NO CLAIM ABOUT WHAT YOU CANNOT SEE" in protocol
    assert "whether money changed hands" in protocol


# =========================================================================== #
# Confusable accounts (v10): the biggest single source of false positives
# =========================================================================== #
def test_the_confusable_accounts_block_is_part_of_the_constitution():
    assert "confusable_accounts" in BLOCKS_BY_ID
    assert any(b.id == "confusable_accounts" for b in CONSTITUTION)


@pytest.mark.parametrize("archetype", [
    "A BUSINESS OR BRAND ACCOUNT",
    "A FAN, HOBBY, OR SUPPORTER ACCOUNT",
    "A NEWS, SPORTS, OR AGGREGATOR ACCOUNT",
    "A REAL PERSON WHO IS NEW",
    "A DORMANT ACCOUNT THAT CAME BACK",
    "A PRIVATE PERSON WITH A TINY FOOTPRINT",
    "SOMEONE WRITING IN A SECOND LANGUAGE",
])
def test_each_legitimate_shape_that_resembles_a_bot_is_named(protocol, archetype):
    """Generic instructions to be careful do not stop a model reading a small fan account as a farm.
    An explicit list of the shapes that get misread does."""
    assert archetype in protocol


def test_recognising_a_legitimate_shape_is_framed_as_a_finding(protocol):
    """Otherwise the model treats "nothing found" as a failure and reaches for a score."""
    assert "not a failure to find something" in protocol


def test_handle_digits_and_non_latin_names_are_not_tells(protocol):
    """Platforms append digits automatically when a name is taken, and script or naming convention
    says nothing about authenticity. Treating either as evidence would make the product
    systematically wrong about whole populations."""
    assert "digits in a handle" in protocol
    assert "non-Latin script" in protocol
    assert "accuracy failure before it is a fairness one" in protocol
    # v11 promoted this from a clause in a list to its own confusable shape, carrying the measured
    # rate, because it is the largest documented false-positive class in adjacent tooling.
    assert "SOMEONE WRITING IN A SECOND LANGUAGE" in protocol
    assert "about 61% of the time" in protocol


def test_stance_and_topic_are_never_evidence(protocol):
    """Especially important given results get posted into political comment sections."""
    assert "AN ACCOUNT WHOSE OPINION IS UNPOPULAR" in protocol
    assert "Stance, politics" in protocol


def test_the_loop_checks_score_against_its_own_signals(protocol):
    """A model will write 85 above eight mild dimensions. The number and the breakdown have to agree,
    and when they do not it is the number that is wrong."""
    assert "CHECK YOUR OWN COHERENCE" in protocol
    assert "the number is wrong, not the dimensions" in protocol


# =========================================================================== #
# The worked example must now demonstrate all of it
# =========================================================================== #
def test_every_account_in_the_example_carries_all_eight_signals():
    """The example used to show eight dimensions for one account and none for the other two, while
    the schema declared them required on every account. Models copy examples over schemas, so that
    contradiction was an invitation to skip the block."""
    import json

    from app.reasoning.prompts import comprehensive_investigation_template as T

    raw = T._OUTPUT_EXAMPLE
    obj = json.loads(raw[raw.find("{"):])
    rows = obj["commenter_assessments"]
    # Four now: a genuine account, a promotional shell, an account with no collected history, and a
    # heavy reposter. The last two exist because both were being scored wrongly in production.
    assert len(rows) == 4
    for row in rows:
        assert len(row["signals"]) == 8, f"{row['ref']} does not show all eight"
        assert isinstance(row["confidence"], int)


def test_the_example_high_score_is_coherent_with_its_own_dimensions():
    """A2 at 82 has to be explainable by its breakdown, which is what the loop's coherence step now
    demands of the model."""
    import json

    from app.reasoning.prompts import comprehensive_investigation_template as T

    raw = T._OUTPUT_EXAMPLE
    a2 = next(r for r in json.loads(raw[raw.find("{"):])["commenter_assessments"]
              if r["ref"] == "A2")
    elevated = [s["name"] for s in a2["signals"]
                if isinstance(s["score"], int) and s["score"] >= 50]
    assert a2["omi_score"] >= 75
    assert len(elevated) >= 3, "a high score with fewer than three elevated dimensions teaches the "\
                               "exact incoherence the loop is supposed to catch"
    # And it still shows an honest null, so a high score does not imply everything was measurable.
    assert any(s["score"] is None for s in a2["signals"])


def test_the_example_thin_account_is_null_heavy_with_low_confidence():
    """A3 is the teaching case for the null semantics: history never collected means most dimensions
    are unscorable, and confidence has to fall accordingly rather than staying high."""
    import json

    from app.reasoning.prompts import comprehensive_investigation_template as T

    raw = T._OUTPUT_EXAMPLE
    a3 = next(r for r in json.loads(raw[raw.find("{"):])["commenter_assessments"]
              if r["ref"] == "A3")
    nulls = [s["name"] for s in a3["signals"] if s["score"] is None]
    assert len(nulls) >= 4, "the thin-evidence example must show nulls, not invented numbers"
    assert a3["confidence"] <= 40, "null-heavy signals must come with low confidence"
    assert a3["omi_score"] < 50


def test_the_example_leads_with_computed_figures_and_a_quote():
    """The example has to model the two things that make a claim checkable, or the rules asking for
    them are competing with a demonstration that ignores them."""
    import json

    from app.reasoning.prompts import comprehensive_investigation_template as T

    raw = T._OUTPUT_EXAMPLE
    rows = {r["ref"]: r for r in json.loads(raw[raw.find("{"):])["commenter_assessments"]}
    a2, a3, a4 = (rows["A2"]["assessment"], rows["A3"]["assessment"], rows["A4"]["assessment"])
    assert '"Huge potential here, link in bio"' in a2      # verbatim quote
    assert "390 to 1" in a2                                # computed ratio
    assert "4 to 1" in a3                                  # computed ratio
    assert "would overturn it" in a2                        # falsifiability
    # A3 hedges in the words: it says outright that nothing was observed rather than implying a read.
    assert "there is nothing here about how it actually behaves" in a3
    # A4 leads with a count and states the age as a figure, not as the adjective "old".
    assert "Forty-six of the fifty collected posts" in a4
    assert "about 14 years old" in a4 and "612 followers against 588 following" in a4


def test_no_worked_example_narrates_its_own_scoring_or_names_an_alias():
    """The contract used to ASK for the counterfactual ("why not ten points higher or lower"), which
    is why "I settled on 72 rather than 57" appeared in roughly 90% of live verdicts. It also used to
    permit "a short alias in parentheses", which is why every verdict opened with one. Both are gone,
    and the example must not reintroduce either by demonstration."""
    import json
    import re

    from app.reasoning.prompts import comprehensive_investigation_template as T

    raw = T._OUTPUT_EXAMPLE
    for row in json.loads(raw[raw.find("{"):])["commenter_assessments"]:
        text = row["assessment"]
        assert not re.search(r"\b[AC]\d{1,3}\b", text), f"{row['ref']} names an alias in its prose"
        for tic in ("I settled on", "rather than one", "more like a ", "more like an "):
            assert tic not in text, f"{row['ref']} demonstrates the banned formula {tic!r}"


# =========================================================================== #
# House rules still hold over the new text
# =========================================================================== #
@pytest.mark.parametrize("block_id", ["score_discipline", "confusable_accounts", "checkable_claims"])
def test_the_new_doctrine_introduced_no_dashes(protocol, block_id):
    """The punctuation rule covers the compiled protocol, because the model's prose renders directly
    on the site and would otherwise reintroduce em dashes on every scan."""
    body = BLOCKS_BY_ID[block_id].body
    assert "—" not in body and "–" not in body
    assert "—" not in protocol and "–" not in protocol


def test_the_banned_phrases_cover_certainty_identity_and_intent():
    """These three are the ways a finding turns into an accusation. The list is also documented as
    NOT reaching per-account prose on the live path, which is why the protocol has to hold the line."""
    from app.governor.governor import BANNED_PHRASES

    for phrase in ("is a bot", "confirmed bot", "proves that", "was hired", "is operated by",
                   "real identity", "undoubtedly"):
        assert phrase in BANNED_PHRASES


# =========================================================================== #
# The protocol must not contradict itself
#
# Two documents disagreeing about the same instruction is worse than either one alone: the model
# picks, and it tends to pick the cheaper option. These are regression tests for contradictions that
# were live in the compiled protocol and were the most likely cause of thin per-account verdicts.
# =========================================================================== #
def _protocol() -> str:
    from app.reasoning.prompts.master_protocol import compile_master_analyst_protocol

    return compile_master_analyst_protocol()["text"]


def test_the_protocol_asks_for_one_assessment_length_everywhere():
    """The base prompt and the Dossier Loop both said "1-3 sentence" while the output contract said
    "4-7 sentences" and the schema sets minLength 200. Told "1-3" twice and "4-7" once, a model
    writes short, and three sentences cannot carry a figure, a quote, both explanations and a limit.
    """
    text = _protocol()
    assert "1-3 sentence" not in text, "the short-reason instruction is back and contradicts the schema"
    assert "4 to 7 full sentences" in text
    assert "4-7 sentences" in text


def test_the_stated_length_can_actually_satisfy_the_schema_floor():
    """A floor of 200 characters is roughly four sentences. An instruction that cannot satisfy the
    schema it is paired with is a bug in the pairing, not a style preference."""
    from app.reasoning.prompts.comprehensive_investigation_template import (
        _COMMENTER_ASSESSMENT_ITEM_SCHEMA,
    )

    assert _COMMENTER_ASSESSMENT_ITEM_SCHEMA["properties"]["assessment"]["minLength"] >= 200


def test_the_dossier_loop_does_not_advertise_a_stale_step_count():
    """The base prompt called it a "four-step worksheet" after the constitution had grown the loop
    with a coherence check and a distribution check. A model told there are four steps stops at four.
    """
    text = _protocol()
    assert "four-step worksheet" not in text
    assert "the constitution governs" in text, "the precedence between the two must be stated"


def test_there_is_a_final_pass_over_the_finished_json():
    """The last thing read before generation. Counts the accounts, re-checks quotes and figures
    against the rows, and asks for plain English, which are the failures that actually occur."""
    text = _protocol()
    i = text.index("FINAL PASS OVER THE JSON")
    # The checklist grew when the history ceiling and the alias/own-row items were added, so the
    # window is sized to the block rather than to a number that happened to fit the old one.
    block = text[i:text.index('Do NOT produce Omi-owned', i)]
    for item in ("COUNT", "QUOTES", "FIGURES", "SPREAD", "LENGTH", "PLAIN"):
        assert item in block, f"the final pass lost its {item} item"
    assert "machine-checked" in block


def test_the_final_pass_does_not_restate_the_distribution_check():
    """Two blocks giving calibration instructions would compete. The final pass points at the
    constitution's version rather than issuing a second one."""
    text = _protocol()
    i = text.index("FINAL PASS OVER THE JSON")
    block = text[i:text.index("Do NOT produce Omi-owned", i)]
    assert "The distribution check above governs" in block


# ==================================================================================================
# FINISHED VERDICT (v12): the analysis was right and the writing sold it short
#
# Derived from ~250 real scored rows across three live investigations. Nothing in this section moves
# a score or softens the score discipline above; every rule is about how a finished verdict READS.
# The failures it fixes were all present in that export:
#   * clean accounts written as four negations in a row, so a correct result read as "nothing found"
#   * ~60% of verdicts closing on "collecting more posts would increase confidence"
#   * ~16% of accounts with NO posts collected, described as fitting a benign explanation
#   * `evidence_against: None reported` on a section of 100 ordinary people
#   * every paragraph opening "This account (created X) has N followers and follows M"
# ==================================================================================================
def test_a_clean_account_must_be_written_as_a_finding(protocol):
    """A correct low score is a result, and it was being written as an absence. Four negated clauses
    in a row read as though nothing was examined, which is what made a working product feel empty."""
    assert "A CLEAN ACCOUNT IS A FINDING" in protocol
    assert "Say what the account IS" in protocol


def test_a_verdict_may_not_close_by_asking_for_more_data(protocol):
    """The last line is the one a reader remembers. Ending on the analysis being insufficient tells
    someone who just paid for it that they received nothing."""
    assert "NEVER CLOSE ON A REQUEST FOR MORE DATA" in protocol
    assert "Collecting more posts would increase confidence" in protocol      # named and banned
    assert "Close on what you found" in protocol


def test_an_unexamined_account_may_never_be_described_as_looking_fine(protocol):
    """The one rule here that is about honesty rather than tone, and the most important of the set.

    Roughly one account in six comes back with no posts collected at all. Those were being scored
    low, tiered `low`, and described as 'consistent with a real user' - a clean bill of health for
    an account nobody looked at. The score discipline cannot catch this because the score is
    correct; only the prose is false."""
    assert "WHEN NOTHING WAS COLLECTED, SAY IT ONCE AND STOP" in protocol
    assert "NOTHING WAS EXAMINED" in protocol
    assert "not a clean" in protocol and "bill of health" in protocol
    # And it must not be padded out to resemble an analysis.
    assert "Do not pad it out" in protocol


def test_the_verdict_does_not_editorialise_about_the_method(protocol):
    """The product states its own scope on the report, the markdown export, the CSV footer and
    /accuracy. A fifth copy inside the verdict only tells a paying reader the answer does not count.
    This sentence was INSTRUCTED by the old base prompt, so it appeared on every single scan."""
    assert "DO NOT EDITORIALISE ABOUT THE METHOD" in protocol
    assert "the human analyst sets the final verdict" in protocol             # named and banned
    assert "Your subject" in protocol and "is the account" in protocol


def test_exculpatory_evidence_must_actually_be_written_down(protocol):
    """`evidence_against: None reported` on a scan of 100 ordinary accounts. Multi-year histories,
    balanced ratios and overnight quiet periods are collected exculpatory evidence, and on a clean
    section they are the substance of the report rather than an empty panel."""
    assert "EXCULPATORY EVIDENCE IS EVIDENCE" in protocol
    assert "almost always a failure to write down what you saw" in protocol
    # The output contract must agree, since that is where the escape hatch was.
    assert "FILL evidence_against" in protocol


def test_the_batch_may_not_be_written_from_one_skeleton(protocol):
    """Twenty paragraphs on one template read as a mail merge, and a reader who spots it stops
    believing any of the accounts were read individually."""
    assert "NO TWO ACCOUNTS IN A BATCH OPEN THE SAME WAY" in protocol


def test_the_reader_facing_rules_do_not_touch_the_score(protocol):
    """The guard on this whole section. It exists to make correct results read well, never to make
    weak evidence read strongly, and the discipline it sits next to is unchanged."""
    assert "None of it moves a score" in protocol
    assert "none of it licenses a claim the evidence does not carry" in protocol
    # The bands and the mechanical gate are still exactly where they were.
    assert "START FROM THE BASE RATE" in protocol
    assert "AMBIENT TRAITS ARE NOT TELLS" in protocol
    assert "THE TWO ERRORS ARE NOT EQUAL" in protocol
