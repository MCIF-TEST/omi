"""Promotion workflow tests (Sprint 011).

The deterministic state machine + append-only ledger: record → recommended → approved →
production, rejection, rollback, illegal-transition guards, required actor (human-controlled),
idempotent recording, history, and summary. The ledger never changes production config.
"""
from __future__ import annotations

import pytest

from app.reasoning.improvement import PromotionLedger, recommend


def _rec():
    b = {"config": {"prompt_version": "v1"}, "agreement_rate": 0.8, "control_fpr": 0.0}
    c = {"config": {"prompt_version": "v2"}, "agreement_rate": 0.9, "control_fpr": 0.0, "number_preserved_rate": 1.0}
    return recommend(b, c)[0]


def test_record_then_promote_to_production():
    led, rec = PromotionLedger(), _rec()
    led.record(rec)
    assert led.state(rec.id) == "recommended"
    led.transition(rec.id, "approved", actor="alice", note="corpus supports it")
    led.transition(rec.id, "production", actor="alice")
    assert led.state(rec.id) == "production"
    assert [h["to"] for h in led.history(rec.id)] == ["recommended", "approved", "production"]


def test_illegal_transitions_and_required_actor():
    led, rec = PromotionLedger(), _rec()
    led.record(rec)
    with pytest.raises(ValueError):
        led.transition(rec.id, "production", actor="a")     # cannot skip 'approved'
    with pytest.raises(ValueError):
        led.transition(rec.id, "approved", actor="")        # human actor required
    with pytest.raises(KeyError):
        led.transition("rec:does-not-exist", "approved", actor="a")


def test_reject_is_terminal():
    led, rec = PromotionLedger(), _rec()
    led.record(rec)
    led.reject(rec.id, actor="bob", note="insufficient evidence")
    assert led.state(rec.id) == "rejected"
    with pytest.raises(ValueError):
        led.transition(rec.id, "approved", actor="bob")     # terminal state


def test_rollback_path():
    led, rec = PromotionLedger(), _rec()
    led.record(rec)
    led.transition(rec.id, "approved", actor="a")
    led.transition(rec.id, "production", actor="a")
    led.transition(rec.id, "rolled_back", actor="a", note="regression detected")
    assert led.state(rec.id) == "rolled_back"


def test_record_is_idempotent_and_summary_and_filter():
    led, rec = PromotionLedger(), _rec()
    led.record(rec)
    led.record(rec)                                          # idempotent by content-addressed id
    assert led.summary() == {"total": 1, "by_state": {
        "candidate": 0, "recommended": 1, "approved": 0, "production": 0, "rejected": 0, "rolled_back": 0}}
    assert led.all(state="recommended") and not led.all(state="production")
