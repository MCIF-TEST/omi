"""D1: investigation overall-confidence derivation for the list view.

The investigations list must surface confidence so a thin-data HIGH isn't
ranked above a well-supported ELEVATED. Confidence is derived from the saved
payload (it changes no score/tier/ranking). These pin the derivation.
"""

from __future__ import annotations

from app.storage.repository import overall_confidence_from_payload


def test_none_when_no_confidence_data():
    assert overall_confidence_from_payload(None) is None
    assert overall_confidence_from_payload({}) is None
    assert overall_confidence_from_payload({"video": {"commenters": []}}) is None


def test_mean_of_commenter_confidences():
    payload = {"video": {"commenters": [
        {"confidence": 0.2}, {"confidence": 0.4}, {"confidence": 0.6},
    ]}}
    assert overall_confidence_from_payload(payload) == 0.4


def test_low_confidence_payload_is_below_threshold():
    payload = {"video": {"commenters": [{"confidence": 0.1}, {"confidence": 0.2}]}}
    val = overall_confidence_from_payload(payload)
    assert val is not None and val < 0.4  # would render the "low conf" chip


def test_high_confidence_payload_is_at_or_above_threshold():
    payload = {"video": {"commenters": [{"confidence": 0.8}, {"confidence": 0.9}]}}
    val = overall_confidence_from_payload(payload)
    assert val is not None and val >= 0.4  # clean row, no chip


def test_weights_focus_commenters_and_coordination():
    # focus(1.0) + mean-commenters(1.0) + thread_scan(0.7), weighted mean.
    payload = {
        "focus_account": {"confidence": 1.0},
        "video": {
            "commenters": [{"confidence": 0.5}, {"confidence": 0.5}],
            "thread_scan": {"confidence": 0.0},
        },
    }
    # (1.0*1 + 0.5*1 + 0.0*0.7) / (1 + 1 + 0.7) = 1.5 / 2.7
    assert overall_confidence_from_payload(payload) == round(1.5 / 2.7, 4)


def test_ignores_non_numeric_confidence():
    payload = {"video": {"commenters": [{"confidence": None}, {"foo": 1}]}}
    assert overall_confidence_from_payload(payload) is None
