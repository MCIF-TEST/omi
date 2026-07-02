"""Every real investigation reaches the model — the scan→analyst auto-wire + exactly-once guard.

Before this wire, ``assess_payload`` (→ RemoteReasoningProvider → the HF endpoint) was reachable
ONLY through an explicit ``POST /v1/investigations/{slug}/analyst`` (the UI button). A normal scan
never triggered it, so a live endpoint received zero requests. These tests pin the fix:

* persisting a NEW investigation schedules a background analyst assessment (once),
* the schedule is a NO-OP when the analyst is disabled (backward compatible),
* concurrent triggers collapse to a single model call (in-flight guard),
* the transport names the served model in the request body (endpoint-log attribution).
"""
from __future__ import annotations

import json
import os
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.core.config import get_settings
from app.reasoning import analyst
from app.routes import scan as scan_mod
from app.storage.db import get_session, reset_db_for_tests
from app.storage.repository import AccountRepository
from tests.test_demo_scan import VID
from tests.test_investigation_hardening import _make_payload


@pytest.fixture(autouse=True)
def _fresh(monkeypatch):
    reset_db_for_tests("sqlite:///:memory:")
    get_settings.cache_clear()
    yield
    reset_db_for_tests("sqlite:///:memory:")
    get_settings.cache_clear()


# --------------------------------------------------------------------------- #
# maybe_autogenerate — the schedule decision
# --------------------------------------------------------------------------- #
def test_maybe_autogenerate_schedules_when_enabled(monkeypatch):
    monkeypatch.setenv("OMI_ANALYST_ENABLED", "true")
    get_settings.cache_clear()
    calls = []
    monkeypatch.setattr("app.core.background.submit",
                        lambda fn, *a, **k: (calls.append((fn, a)) or "future"))
    assert analyst.maybe_autogenerate("inv_x", 7) is True
    assert len(calls) == 1
    fn, args = calls[0]
    assert fn is analyst.generate_and_persist
    assert args == ("inv_x", 7, False)


def test_maybe_autogenerate_is_noop_when_disabled(monkeypatch):
    monkeypatch.setenv("OMI_ANALYST_ENABLED", "false")
    get_settings.cache_clear()
    calls = []
    monkeypatch.setattr("app.core.background.submit", lambda fn, *a, **k: calls.append(1))
    assert analyst.maybe_autogenerate("inv_x", 7) is False
    assert calls == []


def test_maybe_autogenerate_never_raises(monkeypatch):
    monkeypatch.setenv("OMI_ANALYST_ENABLED", "true")
    get_settings.cache_clear()

    def _boom(*a, **k):
        raise RuntimeError("pool exploded")

    monkeypatch.setattr("app.core.background.submit", _boom)
    assert analyst.maybe_autogenerate("inv_x", 7) is False  # swallowed, scan unaffected


# --------------------------------------------------------------------------- #
# Persistence path triggers the schedule exactly once (on create, not on merge)
# --------------------------------------------------------------------------- #
def test_persist_new_investigation_schedules_analyst(monkeypatch):
    seen = []
    monkeypatch.setattr(analyst, "maybe_autogenerate", lambda slug, uid: seen.append((slug, uid)))
    ok = scan_mod._persist_investigation(
        slug="inv_wire1", user_id=1, classification={"kind": "video", "video_id": VID},
        url=f"https://youtube.com/watch?v={VID}", payload=_make_payload(slug="inv_wire1"))
    assert ok is True
    assert seen == [("inv_wire1", 1)]                       # scheduled once, on create


def test_persist_continuation_batch_does_not_reschedule(monkeypatch):
    seen = []
    monkeypatch.setattr(analyst, "maybe_autogenerate", lambda slug, uid: seen.append((slug, uid)))
    scan_mod._persist_investigation(
        slug="inv_wire2", user_id=1, classification={"kind": "video", "video_id": VID},
        url=f"https://youtube.com/watch?v={VID}", payload=_make_payload(slug="inv_wire2"))
    # second batch merges into the existing row → must NOT schedule again (still one model call)
    scan_mod._persist_investigation(
        slug="inv_wire2", user_id=1, classification={"kind": "video", "video_id": VID},
        url=f"https://youtube.com/watch?v={VID}", payload=_make_payload(slug="inv_wire2", quota_used=9))
    assert seen == [("inv_wire2", 1)]


# --------------------------------------------------------------------------- #
# Exactly-once: the in-flight guard collapses a concurrent duplicate
# --------------------------------------------------------------------------- #
def test_generate_and_persist_skips_when_already_in_flight(monkeypatch):
    monkeypatch.setenv("OMI_ANALYST_ENABLED", "true")
    get_settings.cache_clear()
    called = []
    monkeypatch.setattr(analyst, "assess_payload", lambda *a, **k: called.append(1) or {})
    analyst._autogen_inflight.add("inv_busy")
    try:
        assert analyst.generate_and_persist("inv_busy", 1, False) is None
    finally:
        analyst._autogen_inflight.discard("inv_busy")
    assert called == []                                    # no second model call


# --------------------------------------------------------------------------- #
# The transport names the served model in the outbound request (log attribution)
# --------------------------------------------------------------------------- #
def test_qwen_transport_names_the_model_in_request_body(monkeypatch):
    monkeypatch.setenv("HF_TOKEN", "hf_fake")
    captured = {}

    class _R:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return json.dumps({"choices": [{"message": {"content": '{"ok": 1}'}}]}).encode()

    def _fake(req, timeout=None):
        captured["body"] = json.loads(req.data.decode())
        return _R()

    call = analyst._qwen_transport("http://ep/v1/chat/completions", timeout=5, max_retries=0,
                                   revision="r", api="messages",
                                   model="mistralai/Mistral-7B-Instruct-v0.3")
    with patch("app.reasoning.model_providers.remote.urllib.request.urlopen", _fake):
        out = call("SYS", "USER", SimpleNamespace(temperature=0.2, max_new_tokens=16))
    assert out is not None
    assert captured["body"]["model"] == "mistralai/Mistral-7B-Instruct-v0.3"
