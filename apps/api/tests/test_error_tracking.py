"""Error tracking — the wiring, and the guarantees that make it safe to leave on.

Production had no error tracking. The only record of a failure was Render's log stream: ephemeral,
unsearchable at volume, no grouping, no alerting, no release correlation. Both 500-level bugs found
during the launch audit were completely silent in production, and the first signal would have been a
customer telling us.

Worse than the request path is the background pool. ``app.core.background`` absorbs every exception
by design, so a failed analyst run or scan job has NO user-visible signature at all: the work simply
never finishes. That is exactly how the ``NameError`` in the analyst's persist closure survived long
enough to mean no investigation over 25 accounts ever produced an assessment.

So this file pins two things:

1. The integration is actually reachable in production (the package is a real dependency, the DSN is
   declared in the blueprint, and the app factory initialises it).
2. It can never break the service it monitors. No DSN is a complete no-op; a missing package, a bad
   DSN, or a broken SDK degrades to a log line and the request still serves.
"""
from __future__ import annotations

import logging
from pathlib import Path

import pytest

from app.core import observability


REPO = Path(__file__).resolve().parents[3]
API = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    monkeypatch.delenv("SENTRY_DSN", raising=False)
    monkeypatch.delenv("OMI_SENTRY_DSN", raising=False)
    observability.reset_for_tests()
    yield
    observability.reset_for_tests()


# --- unconfigured is a complete no-op ---------------------------------------- #

def test_no_dsn_means_disabled():
    assert observability.error_tracking_dsn() == ""
    assert observability.error_tracking_enabled() is False


def test_init_without_a_dsn_does_nothing_and_reports_it():
    assert observability.init_error_tracking("production") is False


def test_capture_without_init_is_silent():
    """The whole codebase calls this unconditionally. It must never raise, ever."""
    observability.capture_exception(RuntimeError("boom"))  # no init, no DSN


def test_a_blank_dsn_is_treated_as_unset(monkeypatch):
    """An env var set to an empty string (or whitespace) is Render's shape for 'not filled in yet'."""
    monkeypatch.setenv("SENTRY_DSN", "   ")
    assert observability.error_tracking_enabled() is False
    assert observability.init_error_tracking("production") is False


def test_either_env_var_name_works(monkeypatch):
    monkeypatch.setenv("OMI_SENTRY_DSN", "https://k@example.invalid/1")
    assert observability.error_tracking_enabled() is True


# --- configured, and never fatal --------------------------------------------- #

def test_init_with_a_dsn_turns_it_on(monkeypatch):
    monkeypatch.setenv("SENTRY_DSN", "https://public@example.invalid/42")
    captured: dict = {}

    class _FakeSdk:
        @staticmethod
        def init(**kw):
            captured.update(kw)

    monkeypatch.setitem(__import__("sys").modules, "sentry_sdk", _FakeSdk)
    assert observability.init_error_tracking("production", release="1.2.3") is True
    assert captured["dsn"] == "https://public@example.invalid/42"
    assert captured["environment"] == "production"
    assert captured["release"] == "1.2.3"


def test_pii_and_request_bodies_are_never_sent(monkeypatch):
    """This service handles other people's social media data. An error tracker is not the place for
    it, and a scan payload attached to a crash report would be a data-protection incident of our own
    making."""
    monkeypatch.setenv("SENTRY_DSN", "https://public@example.invalid/42")
    captured: dict = {}

    class _FakeSdk:
        @staticmethod
        def init(**kw):
            captured.update(kw)

    monkeypatch.setitem(__import__("sys").modules, "sentry_sdk", _FakeSdk)
    observability.init_error_tracking("production")
    assert captured["send_default_pii"] is False
    assert captured["max_request_body_size"] == "never"


def test_tracing_is_off_unless_explicitly_asked_for(monkeypatch):
    """Tracing bills per transaction. Enabling error tracking must not silently enable a spend."""
    monkeypatch.setenv("SENTRY_DSN", "https://public@example.invalid/42")
    monkeypatch.delenv("SENTRY_TRACES_SAMPLE_RATE", raising=False)
    captured: dict = {}

    class _FakeSdk:
        @staticmethod
        def init(**kw):
            captured.update(kw)

    monkeypatch.setitem(__import__("sys").modules, "sentry_sdk", _FakeSdk)
    observability.init_error_tracking("production")
    assert captured["traces_sample_rate"] == 0.0


def test_an_sdk_that_blows_up_on_init_does_not_take_the_app_down(monkeypatch, caplog):
    monkeypatch.setenv("SENTRY_DSN", "not-a-valid-dsn")

    class _FakeSdk:
        @staticmethod
        def init(**kw):
            raise ValueError("Unsupported scheme")

    monkeypatch.setitem(__import__("sys").modules, "sentry_sdk", _FakeSdk)
    with caplog.at_level(logging.WARNING):
        assert observability.init_error_tracking("production") is False
    assert "continuing without it" in caplog.text


def test_a_missing_package_names_the_fix(monkeypatch, caplog):
    """The failure mode this replaces: a DSN set in the dashboard that silently does nothing."""
    monkeypatch.setenv("SENTRY_DSN", "https://public@example.invalid/42")
    import builtins

    real_import = builtins.__import__

    def _no_sentry(name, *a, **kw):
        if name == "sentry_sdk":
            raise ImportError("No module named 'sentry_sdk'")
        return real_import(name, *a, **kw)

    monkeypatch.setattr(builtins, "__import__", _no_sentry)
    with caplog.at_level(logging.WARNING):
        assert observability.init_error_tracking("production") is False
    assert "sentry-sdk" in caplog.text


def test_init_is_idempotent(monkeypatch):
    """Called from the app factory and available to worker entry points; a second call must not
    re-initialise the client."""
    monkeypatch.setenv("SENTRY_DSN", "https://public@example.invalid/42")
    calls: list[dict] = []

    class _FakeSdk:
        @staticmethod
        def init(**kw):
            calls.append(kw)

    monkeypatch.setitem(__import__("sys").modules, "sentry_sdk", _FakeSdk)
    assert observability.init_error_tracking("production") is True
    assert observability.init_error_tracking("production") is True
    assert len(calls) == 1


def test_capture_swallows_an_sdk_failure(monkeypatch):
    monkeypatch.setenv("SENTRY_DSN", "https://public@example.invalid/42")

    class _FakeSdk:
        @staticmethod
        def init(**kw):
            pass

        @staticmethod
        def capture_exception(exc):
            raise RuntimeError("transport is down")

    monkeypatch.setitem(__import__("sys").modules, "sentry_sdk", _FakeSdk)
    observability.init_error_tracking("production")
    observability.capture_exception(ValueError("the real bug"))  # must not raise


# --- the background pool is the blind spot this exists for -------------------- #

def test_a_failing_background_task_is_reported(monkeypatch):
    """``background._wrap`` absorbs everything, so without this the failure has no signature at all.

    Note the assertion is on the exception OBJECT reaching the sink, not on a log line: the log line
    already existed and is exactly what was not enough.
    """
    from app.core import background

    seen: list[BaseException] = []
    monkeypatch.setattr(background, "capture_exception", seen.append)

    def _explodes():
        raise ZeroDivisionError("analyst persist closure")

    background._wrap(_explodes, (), {})
    assert len(seen) == 1
    assert isinstance(seen[0], ZeroDivisionError)
    assert "analyst persist closure" in str(seen[0])


def test_a_succeeding_background_task_reports_nothing(monkeypatch):
    from app.core import background

    seen: list[BaseException] = []
    monkeypatch.setattr(background, "capture_exception", seen.append)
    background._wrap(lambda: None, (), {})
    assert seen == []


def test_background_capture_is_a_module_level_name():
    """See CLAUDE.md, "A bug class worth knowing". This module runs other people's closures; a
    function-level import of the sink would not be visible from inside one, and the resulting
    NameError would be absorbed by the very handler that was supposed to report it."""
    import app.core.background as bg

    assert callable(getattr(bg, "capture_exception", None))


# --- reachable in production, not just in this test file ---------------------- #

def test_the_sdk_is_a_real_api_dependency():
    """Not an extra. The build command installs `.[youtube,postgres]`, so anything outside those
    extras and the core list is simply absent in production, and setting SENTRY_DSN would then do
    nothing but log a warning nobody is watching for."""
    text = (API / "pyproject.toml").read_text()
    core = text.split("[project.optional-dependencies]")[0]
    assert "sentry-sdk" in core


def test_the_dsn_is_declared_on_the_api_service():
    """An undeclared env var is one a blueprint sync will not surface in the dashboard, so nobody
    finds it when they go looking for how to turn error tracking on."""
    blueprint = (REPO / "render.yaml").read_text()
    api_block = blueprint.split("name: omisphere-web")[0]
    assert "SENTRY_DSN" in api_block


def test_the_app_factory_initialises_tracking():
    """Before init_db, so a boot-time failure is itself reported."""
    main_src = (API / "app" / "main.py").read_text()
    assert "init_error_tracking(" in main_src
    assert main_src.index("init_error_tracking(") < main_src.index("init_db()")
