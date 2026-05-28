"""Tests for the content intelligence seeder.

Policy: the seeder is a deliberate no-op. A fresh DB stays empty until a
real scan populates it. These tests lock that contract in so a future
contributor can't quietly re-introduce fake "UCshill" fixtures without
flipping a feature flag.
"""

from __future__ import annotations

from app.content.seed import seed_example_content
from app.content.service import ContentIntelligenceService
from app.storage.db import get_session


def test_seed_does_not_populate_empty_db():
    """A fresh database stays empty after seeding."""
    seed_example_content()

    with get_session() as session:
        svc = ContentIntelligenceService(session)
        total, entities = svc.list_entities()

    assert total == 0
    assert entities == []


def test_seed_is_safe_to_call_repeatedly():
    """Idempotent in the sense that nothing changes — empty stays empty."""
    seed_example_content()
    seed_example_content()
    seed_example_content()

    with get_session() as session:
        svc = ContentIntelligenceService(session)
        total, _ = svc.list_entities()

    assert total == 0


def test_seed_leaves_existing_data_alone():
    """If real scan data is already present, the seeder must not touch it."""
    with get_session() as session:
        svc = ContentIntelligenceService(session)
        svc.get_or_create_entity(
            platform="youtube",
            content_id="real_user_scan_id",
            title="A real video the user scanned",
        )

    seed_example_content()

    with get_session() as session:
        svc = ContentIntelligenceService(session)
        total, entities = svc.list_entities()

    assert total == 1
    assert entities[0].title == "A real video the user scanned"
