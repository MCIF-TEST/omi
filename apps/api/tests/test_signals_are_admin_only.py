"""The eight-signal breakdown is admin-only while the feature is unfinished.

Product decision (2026-07-29): a customer looking at an analysis sees each account's OMI score, its
tier and the written read. The per-dimension scoring behind that score is not shown to them yet.

The load-bearing design choice is that this is filtered **on serve, never on persist**. The signals
stay in ``payload_json``, so the day the breakdown ships every investigation already generated has
one and no model output anyone paid for is discarded. Test 3 below is the one that matters: it proves
serving to a customer does not destroy the admin's copy.
"""
from __future__ import annotations

import copy

import pytest

from app.reasoning.analyst import ADMIN_ONLY_ACCOUNT_FIELDS, assessment_for_viewer
from app.reasoning.prompts.comprehensive_investigation_template import (
    COMPREHENSIVE_SIGNAL_NAMES,
)


def _signals() -> list[dict]:
    return [
        {"name": n, "score": 30, "reason": "an ordinary reading with nothing unusual about it"}
        for n in COMPREHENSIVE_SIGNAL_NAMES
    ]


def _assessment() -> dict:
    return {
        "verdict": "mixed", "omi_score": 61, "suspicion_tier": "elevated",
        "headline": "Mixed section.", "assessment": "Some accounts read as bought.",
        "commenter_assessments": [
            {"ref": "A1", "handle": "@a", "external_id": "a", "omi_score": 82,
             "suspicion_tier": "high", "confidence": 88, "signals": _signals(),
             "assessment": "Posts on a mechanically regular cadence.", "citations": ["A1"],
             "resolved": True, "follower_count": 12, "engine_probability": 0.8},
            {"ref": "A2", "handle": "@b", "external_id": "b", "omi_score": 14,
             "suspicion_tier": "low", "confidence": 71, "signals": _signals(),
             "assessment": "Reads like a real person.", "citations": ["A2"],
             "resolved": True},
        ],
    }


# =========================================================================== #
# What each audience sees
# =========================================================================== #
def test_a_customer_sees_the_omi_score_but_not_the_breakdown():
    served = assessment_for_viewer(_assessment(), is_admin=False)

    for row in served["commenter_assessments"]:
        assert "signals" not in row
        assert "confidence" not in row
        # Everything the customer IS meant to see survives untouched.
        assert isinstance(row["omi_score"], int)
        assert row["suspicion_tier"] in ("low", "moderate", "elevated", "high")
        assert row["assessment"]
        assert row["handle"]
        assert row["citations"]
        assert row["resolved"] is True
    # The investigation-level read is unaffected: only the per-account block is gated.
    assert served["omi_score"] == 61
    assert served["headline"] == "Mixed section."


def test_an_admin_sees_every_dimension():
    served = assessment_for_viewer(_assessment(), is_admin=True)

    for row in served["commenter_assessments"]:
        assert [s["name"] for s in row["signals"]] == list(COMPREHENSIVE_SIGNAL_NAMES)
        assert isinstance(row["confidence"], int)


# =========================================================================== #
# The one that matters
# =========================================================================== #
def test_serving_to_a_customer_does_not_destroy_the_stored_signals():
    """Filter on serve, never on persist.

    ``assessment_for_viewer`` is handed the live ``payload_json`` object. Filtering it in place would
    strip the signals from the row SQLAlchemy may flush back, so a single customer page view would
    permanently delete model output for that investigation, for admins too, and irreversibly for all
    history the day the feature ships.
    """
    stored = _assessment()
    before = copy.deepcopy(stored)

    customer_view = assessment_for_viewer(stored, is_admin=False)
    assert all("signals" not in r for r in customer_view["commenter_assessments"])

    assert stored == before, "serving mutated the stored assessment"
    # And an admin reading the same object afterwards still gets everything.
    admin_view = assessment_for_viewer(stored, is_admin=True)
    assert all(len(r["signals"]) == 8 for r in admin_view["commenter_assessments"])


def test_the_row_dicts_themselves_are_copies_not_aliases():
    """Not just the list: each row must be a new dict, or the comprehension would be filtering the
    very dicts still referenced by the stored payload."""
    stored = _assessment()
    served = assessment_for_viewer(stored, is_admin=False)

    for stored_row, served_row in zip(stored["commenter_assessments"],
                                      served["commenter_assessments"]):
        assert stored_row is not served_row
    assert stored["commenter_assessments"] is not served["commenter_assessments"]


# =========================================================================== #
# Edges
# =========================================================================== #
@pytest.mark.parametrize("value", [None, "not-a-dict", 42, []])
def test_non_dict_input_passes_through_untouched(value):
    """Never raises on the way to a response. A malformed assessment is a rendering problem, not a
    500 on an investigation the customer already paid for."""
    assert assessment_for_viewer(value, is_admin=False) is value


def test_an_assessment_with_no_per_account_rows_is_returned_as_is():
    for rows in ([], None, "nope"):
        a = {"omi_score": 10, "commenter_assessments": rows}
        assert assessment_for_viewer(a, is_admin=False) == a


def test_a_row_that_is_not_a_dict_survives_rather_than_crashing():
    a = {"commenter_assessments": [{"ref": "A1", "signals": _signals()}, "junk", None]}
    served = assessment_for_viewer(a, is_admin=False)

    assert "signals" not in served["commenter_assessments"][0]
    assert served["commenter_assessments"][1] == "junk"
    assert served["commenter_assessments"][2] is None


def test_no_route_serves_a_cached_assessment_without_the_viewer_filter():
    """The gate is only as good as its call sites, and there are four in one function.

    A fifth return path added later (an export, a share view, a report) would serve the breakdown to
    every customer, and nothing would fail: the extra fields simply appear in the JSON. So assert on
    the source instead. Every place a route reaches into a cached entry for its assessment must hand
    it to ``assessment_for_viewer`` on the way out.
    """
    import re
    from pathlib import Path

    routes = Path(__file__).resolve().parents[1] / "app" / "routes"
    offenders: list[str] = []
    for path in sorted(routes.glob("*.py")):
        lines = path.read_text(encoding="utf-8").splitlines()
        for i, line in enumerate(lines):
            if not re.search(r"""\[["']assessment["']\]""", line):
                continue
            # The call wraps across lines, so look at a small window rather than this line alone.
            window = "".join(lines[max(0, i - 2):i + 2])
            if "assessment_for_viewer" not in window:
                offenders.append(f"{path.name}:{i + 1}: {line.strip()}")

    assert not offenders, (
        "these lines read a cached assessment without filtering it for the viewer:\n  "
        + "\n  ".join(offenders)
    )


def test_the_gate_is_one_named_set_so_shipping_the_feature_is_a_one_line_change():
    """The whole gate is this set. Emptying it ships the breakdown to everyone, which is the intended
    way to turn the feature on, so it must stay the single source of truth."""
    assert ADMIN_ONLY_ACCOUNT_FIELDS == frozenset({"signals", "confidence"})

    a = _assessment()
    served = assessment_for_viewer(a, is_admin=False)
    dropped = set(a["commenter_assessments"][0]) - set(served["commenter_assessments"][0])
    assert dropped == set(ADMIN_ONLY_ACCOUNT_FIELDS)
