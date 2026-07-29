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
    assert CONSTITUTION_VERSION == "v9"


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
    """Absence of evidence is not evidence. An account we barely looked at cannot be strongly
    accused, and the reason must say which evidence was never gathered."""
    assert "THIN EVIDENCE CAPS THE SCORE" in protocol
    assert "cannot exceed 49 on profile metadata alone" in protocol


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
    assert '"ref": "A3", "omi_score": 38, "suspicion_tier": "moderate"' in protocol


def test_the_worked_example_explains_its_own_cap(protocol):
    """The example models the required sentence: name what was not collected, and say that is why the
    score goes no higher."""
    assert "posting history was not collected" in protocol
    assert "behavioural evidence that was never gathered" in protocol


def test_the_high_scoring_example_still_shows_converging_evidence(protocol):
    """The discipline must not have flattened the example into uselessness. A2 at 82 has to remain a
    demonstration of several independent tells landing together."""
    assert '"ref": "A2", "omi_score": 82, "suspicion_tier": "high"' in protocol
    a2 = protocol.split('"ref": "A2"', 1)[1][:600]
    # follower shape + no history + repeated promotional text: three separate observations.
    assert "follows several thousand" in a2
    assert "no real posting history" in a2
    assert "near-identical promotional replies" in a2


# =========================================================================== #
# House rules still hold over the new text
# =========================================================================== #
def test_the_new_doctrine_introduced_no_dashes(protocol):
    """The punctuation rule covers the compiled protocol, because the model's prose renders directly
    on the site and would otherwise reintroduce em dashes on every scan."""
    body = BLOCKS_BY_ID["score_discipline"].body
    assert "—" not in body and "–" not in body
    assert "—" not in protocol and "–" not in protocol
