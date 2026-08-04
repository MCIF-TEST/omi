"""Calibration regression tests, built from four live investigation exports (2026-08-04).

The v10 recalibration was driven by roughly 250 real scored rows. Of the ~90 accounts the model put
at 50 or above, about 75 rested on "posts mostly reposts" and nothing else, which is a description of
how somebody uses the platform rather than evidence about who they are. Those verdicts get posted
publicly, about named people, so the false-positive class is the expensive one.

**What this file can and cannot prove.** The suite never calls the model, so nothing here asserts a
future score. It asserts the two halves that ARE deterministic:

  * the code-level fixes (tier derivation in the join, the alias check, the figure check) against the
    prose the live model actually wrote, and
  * that the compiled protocol carries each rule the recalibration depends on, so a later edit that
    quietly drops one fails here rather than on a customer's report.

`tests/fixtures/analyst_calibration_rows.json` carries the accounts themselves and is the checklist
for the live re-scan, which is the only real proof.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.reasoning.analyst import _join_commenter_assessments, _tier_for_score
from app.reasoning.grounding import (
    HARD, SOFT, check_alias_in_prose, check_figures, check_style, verify_row,
)
from app.reasoning.prompts.master_protocol import compile_master_analyst_protocol

FIXTURE = Path(__file__).parent / "fixtures" / "analyst_calibration_rows.json"
ROWS = json.loads(FIXTURE.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def protocol() -> str:
    return compile_master_analyst_protocol()["text"]


class _Legend:
    """Minimal legend stand-in: the join only needs alias -> author_ref both ways."""

    def __init__(self, mapping: dict[str, str]):
        self._m = mapping

    def to_manifest(self) -> dict:
        return {"accounts": dict(self._m)}

    def resolve(self, alias):
        return self._m.get(alias)


def _joined(items: list[dict]) -> list[dict]:
    legend = _Legend({it["ref"]: f"author:{it['ref']}" for it in items})
    return _join_commenter_assessments({"commenter_assessments": items}, legend, {"commenters": []})


# --------------------------------------------------------------------------- #
# The tier is derived from the score, at every band edge
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("score,tier", [
    (0, "low"), (24, "low"), (25, "moderate"), (49, "moderate"),
    (50, "elevated"), (74, "elevated"), (75, "high"), (100, "high"),
])
def test_the_served_tier_is_derived_from_the_score_at_every_band_edge(score, tier):
    """One live export served score 28 as 'low' on two accounts and 'moderate' on two others.

    The badge a customer reads was not a function of the number printed beside it. Deriving it in the
    join makes the score the single source of truth, and the edges are where an off-by-one would hide.
    """
    row, = _joined([{"ref": "A1", "omi_score": score, "suspicion_tier": "low", "assessment": "x"}])
    assert row["omi_score"] == score
    assert row["suspicion_tier"] == tier == _tier_for_score(score)


def test_a_model_tier_that_disagrees_with_its_own_score_never_reaches_the_reader():
    """Exactly the live defect, replayed from the fixture: same score, two different badges."""
    cases = ROWS["tier_passthrough"]["cases"]
    items = [{"ref": f"A{i}", "omi_score": c["live_score"],
              "suspicion_tier": c["model_tier"], "assessment": "x"}
             for i, c in enumerate(cases, start=1)]
    served = _joined(items)
    for row, case in zip(served, cases):
        assert row["suspicion_tier"] == case["correct_tier"], case["handle"]
    # every one of these scored 28 or 29, so after derivation they agree with each other.
    assert len({r["suspicion_tier"] for r in served}) == 1


def test_a_missing_score_leaves_the_model_tier_alone():
    """Nothing to derive from. Inventing 'low' here would assert a finding the model did not make."""
    row, = _joined([{"ref": "A1", "omi_score": None, "suspicion_tier": "elevated", "assessment": "x"}])
    assert row["omi_score"] is None and row["suspicion_tier"] == "elevated"


# --------------------------------------------------------------------------- #
# Cross-account contamination: the worst class, caught deterministically
# --------------------------------------------------------------------------- #
def test_a_follower_figure_carried_from_a_neighbouring_row_is_a_hard_violation():
    """`swanson18982373` (505/600) was published as following "1,281 people while only 505 follow
    back". The 1,281 belongs to `X_is_Arbitrary`, elsewhere in the same batch.

    A HARD violation withholds the paragraph, which is the right outcome: the alternative is
    publishing another person's numbers under this person's handle.
    """
    case = next(c for c in ROWS["cross_account_contamination"]["cases"]
                if c["handle"] == "swanson18982373")
    account = {"follower_count": case["real_follower_count"],
               "following_count": case["real_following_count"],
               "recent_activity": []}
    violations = check_figures(case["live_prose"], account)
    assert [v.severity for v in violations] == [HARD]
    assert "1281" in violations[0].detail.replace(",", "")


def test_the_same_prose_is_clean_once_the_figures_come_from_the_right_row():
    case = next(c for c in ROWS["cross_account_contamination"]["cases"]
                if c["handle"] == "swanson18982373")
    account = {"follower_count": case["real_follower_count"],
               "following_count": case["real_following_count"],
               "recent_activity": []}
    assert check_figures("It has 505 followers and follows 600 accounts.", account) == []


# --------------------------------------------------------------------------- #
# Aliases and the scoring formula
# --------------------------------------------------------------------------- #
def test_an_internal_alias_in_the_prose_is_hard_and_the_rewritten_sentence_is_clean():
    """Essentially every live verdict opened "A17 is a 2009 account". The reader has never seen that
    label, and after the batches merge it does not even identify the same account."""
    case = next(c for c in ROWS["prose_defects"]["cases"] if c["defect"] == "alias_in_prose")
    violations = check_alias_in_prose(case["live_prose"])
    assert [v.severity for v in violations] == [HARD]
    assert "A17" in violations[0].detail and "A23" in violations[0].detail
    assert check_alias_in_prose(
        "This account is about 15 years old and 46 of its 50 collected posts are reposts.") == []


def test_the_score_counterfactual_and_the_label_swap_are_flagged_but_never_suppress():
    """SOFT on purpose. The paragraph can be entirely true and still be written this way, and
    withholding a correct assessment over a stylistic tic is worse than printing it."""
    for case in [c for c in ROWS["prose_defects"]["cases"] if c["defect"] == "style_formula"]:
        violations = check_style(case["live_prose"])
        assert violations and all(v.severity == SOFT for v in violations), case["live_prose"]


def test_a_style_tic_alone_does_not_withhold_the_paragraph():
    """The whole point of the SOFT/HARD split: verify_row stays ok when only the style check fires."""
    account = {"follower_count": 234, "following_count": 191, "recent_activity": []}
    row = {"ref": "A1", "omi_score": 30, "assessment": (
        "This account has 234 followers and follows 191 accounts, a balanced ratio. "
        "The timeline reads more like an amplifier than a personal account.")}
    report = verify_row(row, account)
    assert report.ok is True
    assert {v.code for v in report.violations} == {"style_formula"}


# --------------------------------------------------------------------------- #
# The protocol carries the rules the recalibration depends on
# --------------------------------------------------------------------------- #
def test_the_protocol_names_reposting_and_volume_as_ambient(protocol):
    """The rule the ~75 false positives needed. The constitution always said ambient traits cap an
    account below 50; it just never listed the traits that were actually driving the scores."""
    lowered = protocol.lower()
    assert "reposting or quote-posting as most of what the account does" in lowered
    assert "a mostly-repost timeline is not a finding" in lowered
    for trait in ("a timeline about one topic or one cause", "a high volume of posts",
                  "sharing links and clips rather than writing originals"):
        assert trait in lowered, trait


def test_the_protocol_states_the_mechanical_gate_with_all_five_tells(protocol):
    assert "NOTHING REACHES 75 WITHOUT ONE" in protocol
    for clause in ("same or near-identical text on two or more of this account's OWN posts",
                   "a scheduler explains them better than a person",
                   "commercial or engagement pitch in the account's own words",
                   "numbered or templated campaign sequence",
                   "profile's own claims contradicting its own metadata"):
        assert clause in protocol, clause
    # the load-bearing exclusion: the traits above may sit beside a tell, never substitute for one.
    assert "can never BE the mechanical tell" in protocol


def test_the_protocol_states_the_history_ceiling_at_every_step(protocol):
    """PedroJaniec scored 3 and Jamison598294 scored 34 on identical evidence: none at all."""
    for clause in ("ZERO POSTS COLLECTED", "EXACTLY ONE POST", "2 TO 14 POSTS", "15 OR MORE POSTS"):
        assert clause in protocol, clause
    assert "must not come out 30 points apart" in protocol


def test_every_must_stay_high_account_has_a_gate_clause_the_protocol_actually_contains(protocol):
    """These are the correct high scores in the same data. A recalibration that also silenced them
    would have traded one failure for another, so each one's justifying clause is checked to still
    exist in the shipped text."""
    accounts = ROWS["must_stay_high"]["accounts"]
    assert len(accounts) >= 5
    for a in accounts:
        assert a["mechanical_tell"], a["handle"]
        head = a["gate_clause"].split("(")[-1].split(")")[-1].strip()
        assert head[:40] in protocol, (a["handle"], head)


def test_no_must_come_down_account_had_a_mechanical_tell(protocol):
    """The fixture's own claim, kept honest: if a future session adds an account to this group while
    naming a tell for it, the group no longer means what the tests say it means."""
    group = ROWS["must_come_down"]
    assert group["expected_ceiling"] == 49
    for a in group["accounts"]:
        assert a["mechanical_tell"] is None, a["handle"]
        assert a["live_score"] > group["expected_ceiling"], a["handle"]


def test_the_protocol_forbids_the_alias_and_the_score_counterfactual_in_prose(protocol):
    """Both defects were INSTRUCTED. The output contract asked for the counterfactual and three
    separate places permitted an alias in the prose; all four sites are gone."""
    assert "alias in parentheses" not in protocol
    assert "rather than one 10 points higher or lower" not in protocol
    assert "DO NOT NARRATE YOUR OWN SCORING" in protocol


def test_the_distribution_check_is_a_quarter_everywhere_it_is_stated(protocol):
    """It is stated in two documents. They said a third and a quarter respectively for one commit,
    which is exactly the silent drift this repo keeps paying for."""
    assert "a third" not in protocol.lower()
    assert protocol.count("50 or above") >= 2
    assert "QUARTER" in protocol
