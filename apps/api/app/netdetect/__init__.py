"""Coordinated-network detection.

Finds SETS of accounts that share improbably many rare behaviours, and proves the set would not
appear by chance in a corpus of this shape. See ``docs/network-detection.md`` for why this replaces
pairwise scoring, and ``shuffle.py`` for the correction that makes a reported finding mean anything.
"""

from app.netdetect.detect import DetectionResult, detect, detect_from_commenters
from app.netdetect.significance import Corpus, score_candidate
from app.netdetect.types import AccountProfile, Candidate, Feature

__all__ = [
    "AccountProfile",
    "Candidate",
    "Corpus",
    "DetectionResult",
    "Feature",
    "detect",
    "detect_from_commenters",
    "score_candidate",
]
