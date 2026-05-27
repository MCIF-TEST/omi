"""Monitoring + alerts (Phase 8).

Three pieces:

* ``anomalies.py`` — pure-function detectors over the existing DB.
* ``service.py`` — high-level read + write API for routes.
* ``scheduler.py`` — asyncio task that runs anomaly + watchlist passes.

The product is fully functional without the scheduler running. Set
``OMI_ENABLE_MONITORING=true`` in production to enable it.
"""

from app.monitoring.anomalies import (  # noqa: F401
    detect_high_tier_surge, detect_narrative_spikes,
)
from app.monitoring.scheduler import lifespan_monitoring  # noqa: F401
from app.monitoring.service import MonitoringService  # noqa: F401
