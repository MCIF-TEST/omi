"""Persistence layer for Omi.

Keeps the growing behavioral fingerprint store, per-account scan history, and
video-scan aggregates that make OmniDetect self-improving across sessions.

The detection layer remains pure — it knows nothing about this module. The
engine orchestrator and route handlers are the only callers.
"""

from app.storage.db import get_session, init_db
from app.storage.models import Account, CommenterEngagement, Scan, VideoScan
from app.storage.repository import AccountRepository

__all__ = [
    "Account",
    "CommenterEngagement",
    "Scan",
    "VideoScan",
    "AccountRepository",
    "get_session",
    "init_db",
]
