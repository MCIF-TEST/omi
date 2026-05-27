"""OmniDetect — the Omi detection engine.

Every detector in this package is a pure function that takes normalized inputs
(`Profile`, list[`Post`]) and returns a `SignalResult`. No I/O, no LLM calls.
The orchestrator in ``engine.py`` calls each detector and hands the results
to ``scoring.aggregate`` for calibrated combination.
"""

from app.detection.engine import analyze_account, analyze_comments

__all__ = ["analyze_account", "analyze_comments"]
