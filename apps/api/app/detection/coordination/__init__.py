"""Cross-account coordination detectors.

These detectors operate on *batches* of accounts (e.g. every commenter on a
single video) and surface relationships that are invisible at the single-
account level — coordinated bursts, fingerprint-sibling bot families,
account-age cohorts dropped from the same farm, same-author sock puppets,
and "fellow-traveler" networks that show up on the same videos repeatedly.

Each detector returns a list of :class:`CoordinationCluster` records plus a
global score reflecting how coordinated the batch as a whole looks. The
orchestrator collects these and (a) elevates per-commenter scores when a
commenter sits inside a cluster, (b) builds a video-level coordination
verdict, (c) shows the operator which accounts hang together.

The detectors here remain I/O-free; the co-engagement detector takes a
pre-loaded ``{commenter_id: set[video_id]}`` dict from the caller, who
fetches it from the DB.
"""

from app.detection.coordination.cohort import detect_age_cohorts
from app.detection.coordination.co_engagement import detect_co_engagement
from app.detection.coordination.fingerprint_cluster import detect_fingerprint_clusters
from app.detection.coordination.style_match import detect_style_matches
from app.detection.coordination.temporal_semantic import detect_temporal_semantic_cliques

__all__ = [
    "detect_age_cohorts",
    "detect_co_engagement",
    "detect_fingerprint_clusters",
    "detect_style_matches",
    "detect_temporal_semantic_cliques",
]
