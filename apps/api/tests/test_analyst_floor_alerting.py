"""A floored analyst assessment must be LOUD, because it is otherwise invisible by construction.

Every investigation was coming back with the customer-facing "the AI analysis isn't ready yet"
notice and nothing anywhere reported it. That is not an oversight in the alerting, it is a property
of the design: the deterministic Floor standing in for the model is a *successful* code path. Nothing
raises, so ``background._wrap``'s ``capture_exception`` never fires, and the only symptom is a
sentence on a page a human has to look at.

These tests pin the fix at the one place every result passes through, ``persist_assessment``.
"""
from __future__ import annotations

import logging

import pytest

from app.reasoning import analyst


class _Inv:
    """Minimal stand-in for the Investigation row: persist only touches slug + payload_json."""

    def __init__(self, slug: str = "inv-abc"):
        self.slug = slug
        self.payload_json: dict = {}


class _Session:
    """Session stub. persist_assessment only needs begin_nested() as a context manager and add()."""

    def __init__(self):
        self.added: list = []

    def begin_nested(self):
        class _Ctx:
            def __enter__(self_inner):
                return self_inner

            def __exit__(self_inner, *exc):
                return False
        return _Ctx()

    def add(self, obj):
        self.added.append(obj)


def _floored(reason: str = "no_model_call (endpoint unset/unreachable) -> deterministic floor") -> dict:
    return {
        "headline": "floor",
        "investigation_trace": {
            "model_backed": False, "fallback_reason": reason,
            "response_status": None, "served_model": None,
        },
    }


def _model_backed() -> dict:
    return {
        "headline": "real",
        "investigation_trace": {
            "model_backed": True, "fallback_reason": None,
            "response_status": 200, "served_model": "openai/gpt-5-mini",
        },
    }


@pytest.fixture
def sink(monkeypatch) -> list[BaseException]:
    """Capture what reaches the error tracker, not merely that a log line was written. The log line
    already existed in spirit and is exactly what was not enough."""
    captured: list[BaseException] = []
    monkeypatch.setattr(analyst, "capture_exception", captured.append)
    return captured


def test_a_floored_assessment_is_reported_to_the_error_tracker(sink):
    analyst.persist_assessment(_Session(), _Inv(), _floored(), "fallback_deterministic")
    assert len(sink) == 1
    assert isinstance(sink[0], analyst.AnalystFellBackToFloor)
    # The classified reason travels with it: "it floored" alone would not have shortened this outage.
    assert "no_model_call" in str(sink[0])
    assert "inv-abc" in str(sink[0])


def test_a_floored_assessment_logs_at_error_with_the_reason(sink, caplog):
    with caplog.at_level(logging.ERROR, logger=analyst.logger.name):
        analyst.persist_assessment(_Session(), _Inv(), _floored(), "fallback_deterministic")
    recs = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert recs, "a floored assessment must log at ERROR, not INFO"
    msg = recs[0].getMessage()
    assert "FLOORED" in msg and "no_model_call" in msg


def test_a_model_backed_assessment_reports_nothing(sink, caplog):
    """The inverse matters as much: an alert that fires on success is an alert people turn off."""
    with caplog.at_level(logging.ERROR, logger=analyst.logger.name):
        analyst.persist_assessment(_Session(), _Inv(), _model_backed(), "openrouter")
    assert sink == []
    assert [r for r in caplog.records if r.levelno >= logging.ERROR] == []


def test_the_governor_reject_reason_survives_into_the_alert(sink):
    """The four causes need different fixes, so the alert has to say which one happened."""
    analyst.persist_assessment(
        _Session(), _Inv("inv-gov"), _floored("governor_reject: ['policy_violation']"), "fallback")
    assert "governor_reject" in str(sink[0]) and "policy_violation" in str(sink[0])


def test_the_assessment_is_still_persisted_when_it_floored(sink):
    """Alerting must not change behaviour. The Floor is still cached, so the page still renders the
    real per-account scores rather than nothing at all."""
    inv, session = _Inv(), _Session()
    entry = analyst.persist_assessment(session, inv, _floored(), "fallback_deterministic")
    assert entry["provider"] == "fallback_deterministic"
    assert inv.payload_json[analyst.CACHE_KEY]["assessment"]["headline"] == "floor"


def test_a_broken_tracker_can_never_fail_the_scan(monkeypatch):
    """Monitoring that can break the thing it monitors is a downgrade. A raising sink is swallowed
    and the assessment still persists."""
    def _boom(_exc):
        raise RuntimeError("tracker down")

    monkeypatch.setattr(analyst, "capture_exception", _boom)
    inv, session = _Inv(), _Session()
    entry = analyst.persist_assessment(session, inv, _floored(), "fallback_deterministic")
    assert entry["assessment"]["headline"] == "floor"
    assert analyst.CACHE_KEY in inv.payload_json


def test_the_alert_uses_the_same_predicate_the_route_and_ui_use():
    """Three places decide "did the model write this": the route (entry_is_model_backed), the panel
    (isModelBacked) and now the alert. They must not drift, so the alert calls the shared one."""
    assert analyst.entry_is_model_backed({"assessment": _model_backed(), "provider": "openrouter"})
    assert not analyst.entry_is_model_backed(
        {"assessment": _floored(), "provider": "fallback_deterministic"})
