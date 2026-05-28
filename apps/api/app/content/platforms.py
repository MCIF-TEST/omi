"""Platform registry for content intelligence.

Adding a new platform (X, Reddit, TikTok, etc.) means:

  1. Implement an integration module under ``app/integrations/<name>.py``
     that exposes ``fetch_video_full(...)`` style functions and a metadata
     fetcher.
  2. Register a ``PlatformAdapter`` here so the universal content database
     can record batches, run incremental rescans, and surface entity metadata
     consistently across platforms.

Until a platform is registered, the content database still works for
read-only display (any platform string is accepted) — but rescans will
report "not yet supported" with a helpful message instead of a generic 501.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Any


@dataclass(frozen=True)
class PlatformAdapter:
    name: str
    display_name: str
    # Returns True iff "+ New batch" rescans are available for this platform.
    # YouTube has cursor-based pagination; some platforms don't.
    supports_continuation: bool
    # Optional human-readable note shown when rescans are disabled.
    rescan_note: str | None = None


REGISTRY: dict[str, PlatformAdapter] = {
    "youtube": PlatformAdapter(
        name="youtube",
        display_name="YouTube",
        supports_continuation=True,
    ),
    # Future:
    # "x":      PlatformAdapter("x", "X / Twitter", supports_continuation=True),
    # "reddit": PlatformAdapter("reddit", "Reddit",  supports_continuation=True),
}


def get_adapter(platform: str) -> PlatformAdapter | None:
    return REGISTRY.get(platform)


def supports_rescan(platform: str) -> bool:
    a = REGISTRY.get(platform)
    return bool(a and a.supports_continuation)


def display_name(platform: str) -> str:
    a = REGISTRY.get(platform)
    return a.display_name if a else platform
