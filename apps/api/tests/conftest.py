"""Global test fixtures — applies to every test in the suite."""

from concurrent.futures import Future

import pytest

from app.core import background
from app.narrative.embeddings import set_embedder_for_tests
from app.storage.db import reset_db_for_tests


@pytest.fixture(autouse=True)
def _inline_content_recording(monkeypatch):
    """Run the content-intelligence write inline (synchronously) during tests.

    Production records it fire-and-forget on the background pool. The in-memory
    test DB is a SINGLE shared SQLite connection (``StaticPool``); a DB-heavy
    task running on a worker thread *concurrently* with the request/main thread
    corrupts that connection ("another row available" / StaleDataError). Of the
    per-scan background tasks only content recording is heavy enough to trip
    this, so we run JUST that one inline — every other background task keeps its
    real async behavior, so the async-job "queued" contract and alert-delivery
    timing are unchanged. Production is untouched.
    """
    real_submit = background.submit

    def _submit(fn, *args, **kwargs):
        # Import lazily so the patch tracks the live function object.
        from app.routes.scan import _record_content_intelligence_async

        if fn is _record_content_intelligence_async:
            fut: Future = Future()
            try:
                fut.set_result(fn(*args, **kwargs))
            except Exception as exc:  # mirror real submit: never raise to caller
                fut.set_exception(exc)
            return fut
        return real_submit(fn, *args, **kwargs)

    monkeypatch.setattr(background, "submit", _submit)
    yield


@pytest.fixture(autouse=True)
def _clean_db_and_embedder():
    """Reset the in-memory SQLite DB and clear the embedder override before
    each test so no test can contaminate another's state.

    Crucially: drains any in-flight background tasks BEFORE resetting the
    DB. Phase 10 schedules content-intelligence recording in the background
    after every /v1/scan/youtube/full request; without this drain those
    tasks would race the DB teardown and surface as flaky StaleDataErrors.
    """
    reset_db_for_tests("sqlite:///:memory:")
    yield
    # Drain background work first so it can't touch the DB after we tear it down.
    try:
        background.shutdown(wait_seconds=10.0)
    except Exception:
        pass
    set_embedder_for_tests(None)
    reset_db_for_tests("sqlite:///:memory:")
