"""Tests for the content intelligence seeder."""

from __future__ import annotations

from app.content.seed import seed_example_content
from app.content.service import ContentIntelligenceService
from app.storage.db import get_session


def test_seed_populates_empty_db():
    seed_example_content()

    with get_session() as session:
        svc = ContentIntelligenceService(session)
        total, entities = svc.list_entities()

    assert total == 3
    titles = {e.title for e in entities}
    assert any("sourdough" in (t or "").lower() for t in titles)
    assert any("infrastructure" in (t or "").lower() for t in titles)


def test_seed_is_idempotent():
    seed_example_content()
    seed_example_content()  # second call must not duplicate rows

    with get_session() as session:
        svc = ContentIntelligenceService(session)
        total, _ = svc.list_entities()

    assert total == 3


def test_seed_sets_coordination_scores():
    seed_example_content()

    with get_session() as session:
        svc = ContentIntelligenceService(session)
        _, entities = svc.list_entities()

    scores = {e.latest_coordination_score for e in entities}
    # At least one entity should have an elevated coordination score
    assert any(s >= 0.3 for s in scores)
    # And at least one should be low-risk
    assert any(s < 0.1 for s in scores)


def test_seed_creates_comments():
    seed_example_content()

    with get_session() as session:
        svc = ContentIntelligenceService(session)
        _, entities = svc.list_entities()
        # Check comments exist for the YouTube entity
        yt = next((e for e in entities if e.platform == "youtube" and e.latest_coordination_score > 0.5), None)
        assert yt is not None
        total, comments = svc.get_comments(yt.id, limit=50)

    assert total > 0
    assert len(comments) > 0


def test_seed_skips_when_data_exists():
    """Seeder should exit without inserting if entities already exist."""
    seed_example_content()

    with get_session() as session:
        svc = ContentIntelligenceService(session)
        # Add a custom entity to simulate pre-existing data
        entity = svc.get_or_create_entity(
            platform="twitter",
            content_id="custom_existing_id",
            title="Custom existing post",
        )
        assert entity.id is not None

    # Run seeder again — should not wipe or re-insert the fixtures
    seed_example_content()

    with get_session() as session:
        svc = ContentIntelligenceService(session)
        total, _ = svc.list_entities()

    # The custom entity plus 3 seeded = 4, but since seed was called AFTER
    # data existed, only the manually-inserted entity is present
    # (the first seed_example_content() ran when the DB was empty, so the
    # custom entity is the 4th row; a second seed call is a no-op).
    assert total == 4
