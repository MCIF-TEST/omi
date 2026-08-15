"""Deterministic coordinated-campaign detection over an investigation's high-scoring cohort.

No model call, no network, no provider quota. Everything here is arithmetic over evidence the scan
already collected, which is what lets a finding be checked by anyone who reads it.

The entry points:

* ``run.detect_for_scan(...)``          pass 1, inside the scan, on the engine probability
* ``run.detect_for_investigation(...)`` pass 2, after the analyst, on the OMI score
* ``run.maybe_refine(slug, user_id)``   schedules pass 2 on the background pool

Both passes share ``run.detect``, so they cannot produce competing verdicts: the later one replaces
the earlier one's stored result rather than sitting beside it.

See ``docs/campaign-detection.md`` for the design, and the module docstrings in ``stats.py`` and
``fuse.py`` for the two things a future change is most likely to break.
"""

from app.campaigns.detector.types import (
    COHORT_DISCRIMINATIVE,
    COHORT_METHODS,
    THRESHOLDS_VERSION,
)

__all__ = [
    "COHORT_DISCRIMINATIVE",
    "COHORT_METHODS",
    "THRESHOLDS_VERSION",
]
