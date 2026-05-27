"""Narrative intelligence — Phase 3.

Tracks topic + framing fingerprints across the entire OMISPHERE corpus
(not just within a single scan). Lets us answer:

  * "Is this talking point spreading across uncorrelated accounts?"
  * "When did this narrative first appear, and where is it active?"
  * "Which accounts are amplifying it?"

The detector layer (``app/detection/semantic.py``) handles within-scan
repetition. The narrative layer handles across-scan, across-account,
across-time clustering.
"""

from app.narrative.embeddings import Embedder, get_embedder  # noqa: F401
from app.narrative.service import NarrativeService  # noqa: F401
