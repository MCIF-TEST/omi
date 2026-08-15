"""Tracking operations across investigations, time, platforms and account rotation.

The per-investigation detector answers "are these accounts running together on this post". This
package answers the larger question the product actually sells: **is this the same operation we
have seen before**, and it has to keep answering yes when the operation changes every account it
uses, moves to a different platform, or goes quiet for two months.

Four pieces:

* ``graph``       accumulates pairwise evidence across scans, so a pair seen twice on unrelated
                  posts is stronger than a pair seen once. This is the only part that makes the
                  probabilities sharper rather than merely making the database bigger.
* ``signature``   sketches an operation's BEHAVIOUR, never its account ids, so it survives
                  rotation.
* ``operations``  identity, matching order and lifecycle (dormant, resurfaced).
* ``seeds``       ingests publicly disclosed real-world operations as known signatures.

All of it is deterministic and offline: no model call, no network, no provider quota. Pinned at the
import graph by ``tests/test_campaign_detector_uses_no_model.py``.
"""

from app.campaigns.tracking.crossplatform import (
    PLATFORM_NEUTRAL_FAMILIES,
    global_key,
    split_key,
)
from app.campaigns.tracking.signature import (
    SIGNATURE_BANDS,
    SIGNATURE_MATCH_THRESHOLD,
    SIGNATURE_PERMUTATIONS,
    band_keys,
    build_signature,
    signature_similarity,
)

__all__ = [
    "PLATFORM_NEUTRAL_FAMILIES",
    "SIGNATURE_BANDS",
    "SIGNATURE_MATCH_THRESHOLD",
    "SIGNATURE_PERMUTATIONS",
    "band_keys",
    "build_signature",
    "global_key",
    "signature_similarity",
    "split_key",
]
