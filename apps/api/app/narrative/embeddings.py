"""Embedding strategy with graceful fallback.

OMISPHERE works two ways:

* **With sentence-transformers installed** (`pip install -e .[ml]`):
  high-quality semantic embeddings via ``all-MiniLM-L6-v2`` (384 dims).
  Best clustering, smallest model that gives real semantics.

* **Without it**: TF-IDF embeddings — coarser, faster, no model download.
  Still useful: catches near-duplicates and templated content. Good
  enough for the narrative observatory to function in dev environments
  without the ML dependencies.

Tests inject a fake embedder via ``set_embedder_for_tests`` — no model
download in CI.
"""

from __future__ import annotations

import hashlib
import math
import re
from typing import Iterable, Protocol


class Embedder(Protocol):
    """Minimal embedder interface: text in, fixed-width vector out."""

    dimensions: int

    def embed(self, texts: list[str]) -> list[list[float]]: ...
    def embed_one(self, text: str) -> list[float]: ...


# ---------------------------------------------------------------------------
# Fast TF-IDF style fallback. Hashing trick → fixed-width vector.
# ---------------------------------------------------------------------------

_WORD_RE = re.compile(r"\w+", re.UNICODE)


class HashingEmbedder:
    """Hashing-vectorizer fallback. ~128 dims, normalized. No model needed.

    Catches lexical similarity and near-duplicates. Will NOT catch
    paraphrases (sentence-transformers does).
    """

    dimensions: int = 128

    def __init__(self, dims: int = 128):
        self.dimensions = dims

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self.embed_one(t) for t in texts]

    def embed_one(self, text: str) -> list[float]:
        vec = [0.0] * self.dimensions
        tokens = [t.lower() for t in _WORD_RE.findall(text or "")]
        if not tokens:
            return vec
        for tok in tokens:
            idx = (
                int.from_bytes(hashlib.blake2b(tok.encode(), digest_size=4).digest(), "big")
                % self.dimensions
            )
            vec[idx] += 1.0
        # add bigrams (light context)
        for i in range(len(tokens) - 1):
            bigram = tokens[i] + "_" + tokens[i + 1]
            idx = (
                int.from_bytes(hashlib.blake2b(bigram.encode(), digest_size=4).digest(), "big")
                % self.dimensions
            )
            vec[idx] += 0.5
        # L2 normalize
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]


# ---------------------------------------------------------------------------
# sentence-transformers — lazy import so the rest of the API runs without it.
# ---------------------------------------------------------------------------


class SentenceTransformerEmbedder:
    """Wraps sentence-transformers/all-MiniLM-L6-v2.

    Cached at process level; safe to construct multiple times.
    """

    _model = None

    dimensions: int = 384

    def _ensure_model(self):
        if SentenceTransformerEmbedder._model is None:
            from sentence_transformers import SentenceTransformer  # type: ignore
            SentenceTransformerEmbedder._model = SentenceTransformer(
                "sentence-transformers/all-MiniLM-L6-v2"
            )
        return SentenceTransformerEmbedder._model

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        model = self._ensure_model()
        # normalize_embeddings=True → unit vectors; cosine = dot product.
        vecs = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
        return [list(map(float, v)) for v in vecs]

    def embed_one(self, text: str) -> list[float]:
        return self.embed([text])[0]


# ---------------------------------------------------------------------------
# Singleton accessor — falls back to the hashing embedder when ML extras
# aren't installed. Tests can override via set_embedder_for_tests().
# ---------------------------------------------------------------------------

_embedder: Embedder | None = None
_override: Embedder | None = None


def get_embedder() -> Embedder:
    global _embedder
    if _override is not None:
        return _override
    if _embedder is not None:
        return _embedder
    try:
        # Probing without forcing a model download — sentence_transformers
        # import itself is what's expensive. If the package is missing we
        # immediately fall back.
        import sentence_transformers  # type: ignore  # noqa: F401
        _embedder = SentenceTransformerEmbedder()
    except ImportError:
        _embedder = HashingEmbedder()
    return _embedder


def set_embedder_for_tests(e: Embedder | None) -> None:
    """Inject a fake embedder for tests. Pass None to clear."""
    global _override
    _override = e


def cosine(a: list[float], b: list[float]) -> float:
    """Cosine similarity for unit vectors = dot product."""
    if len(a) != len(b):
        return 0.0
    return sum(x * y for x, y in zip(a, b))


_ = Iterable  # silence unused-import lints if any
