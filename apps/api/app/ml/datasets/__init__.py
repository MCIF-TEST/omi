"""Continuous dataset ingestion + training-corpus assembly.

This package is the glue between *files a human drops into the repo's
``datasets/`` folder* and the learned-detector track in :mod:`app.ml`.

The design goals, in priority order:

1. **Drop-in.** A new CSV placed in ``datasets/`` is auto-detected by an
   adapter (matched on its column signature, with a filename label hint as a
   fallback) and ingested with no code change. Genuinely novel schemas need
   only a small adapter registered in :mod:`app.ml.datasets.adapters`.

2. **Continuous / incremental.** Every ingested file is recorded in a
   content-hash ledger (:mod:`app.ml.datasets.ledger`). Re-running ingestion
   only processes files that are new or have changed, so the operator can keep
   adding datasets over time and re-run the same command cheaply.

3. **One feature space.** Account datasets are reduced to the platform-agnostic
   behavioral fields OMISPHERE already models and run through the *real*
   detector engine (via :mod:`app.ml.public_import`), so an imported row lands
   in the exact same feature space as a live YouTube scan — no train/serve
   skew. Text datasets feed the AI-writing track.

4. **A growing, brand-new corpus.** Imported dataset rows (``source =
   imported_dataset``) live alongside the labels OMISPHERE captures from its
   own scans + operator review + YouTube moderation actions. Exporting the
   union (:mod:`app.ml.export`) produces a single, continuously growing
   training corpus that is neither purely the public datasets nor purely our
   own capture — it is the new dataset the two form together.
"""

from __future__ import annotations

from app.ml.datasets.records import TextRecord
from app.ml.datasets.registry import (
    DatasetAdapter,
    detect_adapter,
    iter_adapters,
    register_adapter,
)

__all__ = [
    "TextRecord",
    "DatasetAdapter",
    "detect_adapter",
    "iter_adapters",
    "register_adapter",
]
