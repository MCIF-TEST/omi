"""First-boot content seeding.

Previous versions of this module inserted hand-crafted "UCshill_01 / SAVE20"
fixtures so a fresh dashboard wasn't empty. Those fixtures actively damaged
credibility — a real analyst sees obviously fake bots and closes the tab.

The current policy is: a fresh database stays empty. The UI handles the
empty state cleanly (see the /content and /dashboard pages). The first real
scan populates the database with real content.

The function is kept for backwards compatibility with ``main.py`` and for a
future hook (e.g. importing a sanitized labeled fixture set behind an
``OMI_LOAD_DEMO_FIXTURES=true`` flag). Today it's a deliberate no-op.
"""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)


def seed_example_content() -> None:
    """Intentional no-op. A fresh database stays empty until a real scan
    populates it. See module docstring for rationale."""
    log.debug("seed_example_content: skipped (intentional — no demo fixtures).")
