"""Seed the content intelligence database with example scans on first boot.

These are realistic-looking but entirely fictional records that give new users
a populated dashboard from minute one instead of an empty screen. They are
inserted once when the DB is empty; if any ContentEntity rows already exist
the seeder exits immediately.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from app.content.service import ContentIntelligenceService
from app.storage.db import get_session

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Fixture data
# ---------------------------------------------------------------------------

_BASE = datetime(2026, 3, 1, 9, 0, 0, tzinfo=timezone.utc)


def _t(days: float = 0, hours: float = 0) -> datetime:
    return _BASE + timedelta(days=days, hours=hours)


_SEED_FIXTURES: list[dict] = [
    # ------------------------------------------------------------------
    # 1. High-risk YouTube video — astroturf pile-on
    # ------------------------------------------------------------------
    {
        "entity": {
            "platform": "youtube",
            "content_id": "dQw4w9WgXcQ",
            "kind": "video",
            "title": "This new product will CHANGE EVERYTHING (not clickbait)",
            "author_external_id": "UCexample_channel",
            "author_handle": "TechHypeTV",
            "canonical_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "thumbnail_url": "https://i.ytimg.com/vi/dQw4w9WgXcQ/hqdefault.jpg",
        },
        "batches": [
            {
                "fetched_at_offset": {"days": 0},
                "coordination_score": 0.21,
                "risk_tier": "low",
                "tier_distribution": {"low": 18, "moderate": 3, "elevated": 1, "high": 0},
                "comments": [
                    {"id": "yt_c001", "author": "UCreal_fan_1", "handle": "@realfan1",
                     "text": "Great video! Really informative.", "offset_h": 0},
                    {"id": "yt_c002", "author": "UCreal_fan_2", "handle": "@gadgetlover99",
                     "text": "Been waiting for this breakdown. Thanks!", "offset_h": 1},
                    {"id": "yt_c003", "author": "UCreal_fan_3", "handle": "@techskeptic",
                     "text": "I'm not convinced yet, will wait for reviews.", "offset_h": 2},
                    {"id": "yt_c004", "author": "UCreal_fan_4", "handle": "@earlyadopter77",
                     "text": "Already ordered mine. Can't wait!", "offset_h": 3},
                    {"id": "yt_c005", "author": "UCshill_01", "handle": "@bestdeals2026",
                     "text": "I bought this and it literally changed my life use my code SAVE20", "offset_h": 1},
                    {"id": "yt_c006", "author": "UCreal_fan_5", "handle": "@budgetbuild",
                     "text": "What's the price point on this thing?", "offset_h": 5},
                ],
            },
            {
                "fetched_at_offset": {"days": 5},
                "coordination_score": 0.61,
                "risk_tier": "elevated",
                "tier_distribution": {"low": 12, "moderate": 8, "elevated": 14, "high": 6},
                "comments": [
                    {"id": "yt_c007", "author": "UCshill_02", "handle": "@promoking88",
                     "text": "Amazing product already ordered three!! use code SAVE20", "offset_h": 0.5},
                    {"id": "yt_c008", "author": "UCshill_03", "handle": "@dailydeals_bot",
                     "text": "I was skeptical but WOW just WOW. Link in bio!!!", "offset_h": 0.6},
                    {"id": "yt_c009", "author": "UCshill_04", "handle": "@reviewkingdom",
                     "text": "5 stars! Best purchase 2026 hands down. SAVE20", "offset_h": 0.7},
                    {"id": "yt_c010", "author": "UCshill_05", "handle": "@techfinds_daily",
                     "text": "Game changer product!! I've told all my friends about this!", "offset_h": 0.8},
                    {"id": "yt_c011", "author": "UCshill_06", "handle": "@influencer_net1",
                     "text": "Just received mine today and WOW use SAVE20 for discount", "offset_h": 0.9},
                    {"id": "yt_c012", "author": "UCshill_07", "handle": "@viralproducts",
                     "text": "This actually works!! Ordered 2 for gifts. Promo code SAVE20", "offset_h": 1.1},
                    {"id": "yt_c013", "author": "UCshill_08", "handle": "@topdeals2026",
                     "text": "Can't believe I almost missed this! code SAVE20 still works", "offset_h": 1.2},
                    {"id": "yt_c014", "author": "UCreal_fan_6", "handle": "@skeptic_sam",
                     "text": "Why does literally every comment mention a promo code?", "offset_h": 6},
                    {"id": "yt_c015", "author": "UCreal_fan_7", "handle": "@consumer_watch",
                     "text": "These comments look super suspicious. Same posting pattern.", "offset_h": 8},
                ],
            },
        ],
    },

    # ------------------------------------------------------------------
    # 2. Moderate-risk post — coordinated political messaging
    # ------------------------------------------------------------------
    {
        "entity": {
            "platform": "twitter",
            "content_id": "1234567890123456789",
            "kind": "post",
            "title": "Senator announces new infrastructure vote tomorrow",
            "author_external_id": "twnews_example",
            "author_handle": "@BreakingPolitics",
            "canonical_url": None,
            "thumbnail_url": None,
        },
        "batches": [
            {
                "fetched_at_offset": {"days": 1},
                "coordination_score": 0.34,
                "risk_tier": "moderate",
                "tier_distribution": {"low": 20, "moderate": 12, "elevated": 4, "high": 0},
                "comments": [
                    {"id": "tw_c001", "author": "tw_usr_citizen1", "handle": "@concerned_citizen",
                     "text": "Finally some action on infrastructure!", "offset_h": 0},
                    {"id": "tw_c002", "author": "tw_usr_reporter1", "handle": "@local_reporter",
                     "text": "Full text of the bill is on congress.gov #infrastructure", "offset_h": 1},
                    {"id": "tw_c003", "author": "tw_coord_1", "handle": "@freedom_patriot_88",
                     "text": "This is a COMMUNIST takeover of private roads VOTE NO", "offset_h": 0.3},
                    {"id": "tw_c004", "author": "tw_coord_2", "handle": "@america_first_2026",
                     "text": "COMMUNIST takeover of private roads VOTE NO", "offset_h": 0.4},
                    {"id": "tw_c005", "author": "tw_coord_3", "handle": "@real_patriot_news",
                     "text": "Communist takeover of private roads VOTE NO!!!!", "offset_h": 0.5},
                    {"id": "tw_c006", "author": "tw_coord_4", "handle": "@liberty_bell_usa",
                     "text": "COMMUNIST TAKEOVER vote NO on this bill", "offset_h": 0.6},
                    {"id": "tw_c007", "author": "tw_usr_citizen2", "handle": "@suburbanvoter",
                     "text": "I support this. My town's roads are terrible.", "offset_h": 3},
                    {"id": "tw_c008", "author": "tw_usr_analyst1", "handle": "@policy_analyst",
                     "text": "The bill allocates 40% to rural broadband, not roads.", "offset_h": 4},
                    {"id": "tw_c009", "author": "tw_coord_5", "handle": "@constitution_defender",
                     "text": "Communist takeover, vote NO now!", "offset_h": 0.7},
                    {"id": "tw_c010", "author": "tw_coord_6", "handle": "@stoptheagenda2026",
                     "text": "Another communist grab, tell your rep VOTE NO", "offset_h": 0.8},
                ],
            },
        ],
    },

    # ------------------------------------------------------------------
    # 3. Low-risk content — organic discussion, no signals
    # ------------------------------------------------------------------
    {
        "entity": {
            "platform": "youtube",
            "content_id": "example_lowrisk_id",
            "kind": "video",
            "title": "How to make sourdough bread at home (beginner guide)",
            "author_external_id": "UCbaking_example",
            "author_handle": "@TheBakingChannel",
            "canonical_url": "https://www.youtube.com/watch?v=example_lowrisk_id",
            "thumbnail_url": None,
        },
        "batches": [
            {
                "fetched_at_offset": {"days": 2},
                "coordination_score": 0.04,
                "risk_tier": "low",
                "tier_distribution": {"low": 24, "moderate": 1, "elevated": 0, "high": 0},
                "comments": [
                    {"id": "bk_c001", "author": "UCbaker1", "handle": "@homebaker_jen",
                     "text": "Made this last weekend! Turned out amazing. My starter is 3 years old.", "offset_h": 0},
                    {"id": "bk_c002", "author": "UCbaker2", "handle": "@breadobsessed",
                     "text": "The scoring technique at 8:42 is SO helpful, never understood why my crust was flat.", "offset_h": 1},
                    {"id": "bk_c003", "author": "UCbaker3", "handle": "@gluten_free_greta",
                     "text": "Is there a GF version? My daughter has celiac.", "offset_h": 2},
                    {"id": "bk_c004", "author": "UCbaker4", "handle": "@kitch_experiments",
                     "text": "Failed 4 times before finding your channel. First successful loaf yesterday!!", "offset_h": 3},
                    {"id": "bk_c005", "author": "UCbaker5", "handle": "@weekend_chef",
                     "text": "What hydration ratio are you using here?", "offset_h": 4},
                    {"id": "bk_c006", "author": "UCbaker6", "handle": "@artisan_bread_fan",
                     "text": "The dutch oven method really makes a difference, worth the investment.", "offset_h": 5},
                ],
            },
        ],
    },
]


def seed_example_content() -> None:
    """Insert fixture content entities and batches if the table is empty.

    Safe to call repeatedly — exits immediately if any entity rows exist.
    """
    try:
        with get_session() as session:
            svc = ContentIntelligenceService(session)

            from sqlalchemy import select, func
            from app.storage.models import ContentEntity
            count = session.execute(select(func.count()).select_from(ContentEntity)).scalar_one()
            if count > 0:
                return

            log.info("Seeding example content intelligence data…")

            for fixture in _SEED_FIXTURES:
                ed = fixture["entity"]
                entity = svc.get_or_create_entity(
                    platform=ed["platform"],
                    content_id=ed["content_id"],
                    kind=ed.get("kind", "video"),
                    title=ed.get("title"),
                    author_external_id=ed.get("author_external_id"),
                    author_handle=ed.get("author_handle"),
                    canonical_url=ed.get("canonical_url"),
                    thumbnail_url=ed.get("thumbnail_url"),
                )

                for bdata in fixture["batches"]:
                    offset = bdata["fetched_at_offset"]
                    base_time = _BASE + timedelta(**offset)
                    entity.first_scanned_at = entity.first_scanned_at or base_time

                    raw_comments = [
                        {
                            "comment_id": c["id"],
                            "author_external_id": c["author"],
                            "text": c["text"],
                            "created_at": base_time + timedelta(hours=c.get("offset_h", 0)),
                        }
                        for c in bdata["comments"]
                    ]
                    handle_map = {c["author"]: c["handle"] for c in bdata["comments"] if "handle" in c}

                    batch = svc.record_batch(
                        entity=entity,
                        user_id=None,  # system-seeded, no user
                        comments=raw_comments,
                        handle_map=handle_map,
                        coordination_score=bdata["coordination_score"],
                        risk_tier=bdata["risk_tier"],
                        tier_distribution=bdata.get("tier_distribution", {}),
                    )
                    # Back-date the batch timestamp to match the fixture
                    batch.fetched_at = base_time
                    entity.first_scanned_at = min(entity.first_scanned_at or base_time, base_time)
                    entity.last_scanned_at = max(entity.last_scanned_at or base_time, base_time)

            log.info("Seed complete — %d fixture entities inserted.", len(_SEED_FIXTURES))

    except Exception:
        log.exception("Content seeder failed — non-fatal, continuing startup")
