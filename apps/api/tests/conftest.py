"""Global test fixtures — applies to every test in the suite."""

import pytest

from app.core import background
from app.narrative.embeddings import set_embedder_for_tests
from app.storage.db import reset_db_for_tests


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
