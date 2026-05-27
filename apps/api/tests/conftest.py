"""Global test fixtures — applies to every test in the suite."""

import pytest

from app.narrative.embeddings import set_embedder_for_tests
from app.storage.db import reset_db_for_tests


@pytest.fixture(autouse=True)
def _clean_db_and_embedder():
    """Reset the in-memory SQLite DB and clear the embedder override before
    each test so no test can contaminate another's state."""
    reset_db_for_tests("sqlite:///:memory:")
    yield
    set_embedder_for_tests(None)
    reset_db_for_tests("sqlite:///:memory:")
