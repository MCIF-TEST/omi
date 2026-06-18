"""Account/commenter-history readability: parent-content titles from storage.

Recent-activity samples reference the parent content (e.g. a YouTube video) by
raw id. _attach_content_titles annotates them with the human-readable title
when that content is already in the ContentEntity store — readability only, no
external fetch, no scoring/detection change.
"""

from __future__ import annotations

from app.routes.scan import _attach_content_titles
from app.storage.db import get_session, reset_db_for_tests
from app.storage.models import ContentEntity


def _seed_content(platform: str, content_id: str, title: str | None) -> None:
    with get_session() as s:
        s.add(ContentEntity(platform=platform, content_id=content_id, kind="video", title=title))


def test_attaches_title_when_content_on_file():
    reset_db_for_tests()
    _seed_content("youtube", "vid_known", "How the GRU network operated")
    samples = [
        {"text": "a", "parent_id": "vid_known"},
        {"text": "b", "parent_id": "vid_unknown"},   # not in store
        {"text": "c", "parent_id": None},             # no parent
    ]
    _attach_content_titles("youtube", samples)
    assert samples[0]["parent_title"] == "How the GRU network operated"
    assert "parent_title" not in samples[1]   # unknown parent → unchanged (keeps id/link)
    assert "parent_title" not in samples[2]


def test_platform_scoped_lookup():
    reset_db_for_tests()
    _seed_content("youtube", "shared_id", "YT title")
    samples = [{"text": "a", "parent_id": "shared_id"}]
    _attach_content_titles("x", samples)          # wrong platform → no match
    assert "parent_title" not in samples[0]


def test_empty_or_titleless_is_safe():
    reset_db_for_tests()
    _seed_content("youtube", "vid_notitle", None)  # content on file but no title
    samples = [{"text": "a", "parent_id": "vid_notitle"}]
    _attach_content_titles("youtube", samples)
    assert "parent_title" not in samples[0]
    # No samples / no parents → no error.
    _attach_content_titles("youtube", [])
