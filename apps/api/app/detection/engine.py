"""OmniDetect orchestrator.

Glue layer between the route handlers and the individual detectors. Keeps the
detectors decoupled from each other and from FastAPI.
"""

from __future__ import annotations

from app.detection.ai_writing import analyze_ai_writing
from app.detection.engagement import analyze_engagement
from app.detection.narrative import analyze_narrative
from app.detection.profile import analyze_profile
from app.detection.scoring import aggregate
from app.detection.semantic import analyze_semantic
from app.detection.temporal import analyze_temporal
from app.detection.voice import analyze_voice
from app.schemas import Post, Profile, ScanResult, SignalResult


def analyze_account(
    profile: Profile,
    posts: list[Post],
    *,
    extra_signals: list[SignalResult] | None = None,
) -> ScanResult:
    """Run every account-level detector and return an aggregated scan result.

    ``extra_signals`` lets the orchestrator inject signals that depend on I/O
    (e.g. the memory-derived prior from the persistent fingerprint store, or
    the coordination signal from a full video scan). Detectors themselves
    remain pure.
    """
    signals: list[SignalResult] = [
        analyze_temporal(posts),
        analyze_semantic(posts),
        analyze_ai_writing(posts),
        analyze_voice(posts),
        analyze_engagement(posts),
        analyze_narrative(posts),
        analyze_profile(profile, post_count=len(posts) or None),
    ]
    if extra_signals:
        signals.extend(extra_signals)
    result = aggregate(signals)
    result.subject = profile.handle
    return result


def analyze_comments(
    comments: list[Post],
    *,
    extra_signals: list[SignalResult] | None = None,
) -> ScanResult:
    """Run content-level detectors on a batch of comments.

    Profile and temporal-per-author detectors don't apply here (the comments
    typically come from many different authors). We focus on semantic
    repetition and AI-writing patterns across the batch.
    """
    signals: list[SignalResult] = [
        analyze_semantic(comments),
        analyze_ai_writing(comments),
    ]
    if extra_signals:
        signals.extend(extra_signals)
    result = aggregate(signals)
    return result
