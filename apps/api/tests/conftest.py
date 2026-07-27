"""Global test fixtures — applies to every test in the suite."""

from concurrent.futures import Future

import pytest

from app.core import background
from app.core.rate_limit import reset_all_limiters_for_tests
from app.narrative.embeddings import set_embedder_for_tests
from app.storage.db import reset_db_for_tests


@pytest.fixture(autouse=True)
def _reset_rate_limiters():
    """Give every test the full request budget.

    Rate limits are in-process and cumulative, and `app.main` exposes a module-level
    `app = create_app()` that most test files import and share. The worst offender is
    GlobalRateLimitMiddleware's own limiter (120 requests / 60s, keyed on the client IP, which is the
    constant "testclient" under TestClient): it is an instance attribute on the shared middleware, so
    it counted every request the whole session made and then 429'd essentially everything after the
    120th. The damage did not look like throttling either — a fixture's signup would come back 429,
    the user row would never exist, and the test failed later with `NoResultFound`, which reads as a
    database or billing bug in a file that passes perfectly on its own.

    Reset before AND after: before so the test starts clean, after so an aborted test can't leave a
    spent budget behind.
    """
    reset_all_limiters_for_tests()
    yield
    reset_all_limiters_for_tests()


@pytest.fixture(autouse=True)
def _inline_content_recording(monkeypatch):
    """Run the DB-heavy per-scan background writes inline (synchronously) during tests.

    Production records them fire-and-forget on the background pool. The in-memory test DB is a
    SINGLE shared SQLite connection (``StaticPool``); a DB-heavy task running on a worker thread
    *concurrently* with the request/main thread corrupts that connection ("another row available" /
    StaleDataError, e.g. an UPDATE on ``narratives`` / ``coordination_edges`` matching 0 rows).
    We run each such writer inline — content-intelligence recording, **narrative ingestion**, and
    the **analyst auto-generation** (all of which open their own ``get_session()``) — while leaving
    every other background task (alert delivery, the async-scan job) its real async behavior, so the
    async-job "queued" contract and alert-delivery timing are unchanged. Production is untouched.
    """
    real_submit = background.submit

    def _submit(fn, *args, **kwargs):
        # Import lazily so the patch tracks the live function objects.
        from app.orchestrator import _ingest_narratives_async
        from app.reasoning.analyst import generate_and_persist
        from app.routes.scan import _record_content_intelligence_async

        if fn in (_record_content_intelligence_async, _ingest_narratives_async, generate_and_persist):
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
