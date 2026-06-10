"""First-boot content seeding.

Previous versions inserted hand-crafted "UCshill_01 / SAVE20" fixtures so a
fresh dashboard wasn't empty. Those fixtures actively damaged credibility — a
real analyst sees obviously fake bots and closes the tab. Those are gone for
good.

What we DO seed is the opposite of fake: a small set of **real** coordinated
campaigns from the platform's own state-actor disclosure archives (Russia GRU,
China Xinjiang), scored by the real engine (see ``featured.py``). A brand-new
user can immediately explore a genuine, disclosed influence operation — real
evidence, real confidence, real corroboration — instead of an empty page.
Idempotent and best-effort: a failure never breaks boot.
"""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)


def seed_example_content() -> None:
    """Seed the real featured campaigns for first-run value. Idempotent and
    best-effort — never raises into the boot path."""
    try:
        from app.content.featured import seed_featured_campaigns
        from app.storage.db import get_session

        with get_session() as session:
            n = seed_featured_campaigns(session)
        if n:
            log.info("seed_example_content: seeded %d featured campaign(s).", n)
        else:
            log.debug("seed_example_content: featured campaigns already present or no fixture.")
    except Exception as e:  # noqa: BLE001 — onboarding seed must never break boot
        log.warning("seed_example_content: skipped (%s).", e)

