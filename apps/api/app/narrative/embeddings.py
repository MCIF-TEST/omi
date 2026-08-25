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
    #: Which vector SPACE these embeddings live in, e.g. ``api:text-embedding-3-small:1536``.
    #:
    #: Two embedders are interchangeable only if this string matches. Dimensions alone are not
    #: enough: two different 1536-dimension models produce coordinates that mean nothing to each
    #: other, and a centroid built in one is not a centroid in the other. Clustering compares a new
    #: vector against stored centroids, and `cosine` returns 0.0 for a length mismatch, so mixing
    #: spaces does not raise anything: every utterance simply fails to match any existing topic and
    #: spawns a new one. The topic space silently forks in half and nothing anywhere reports it.
    space: str

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
    space: str = "hashing-v1:128"

    def __init__(self, dims: int = 128):
        self.dimensions = dims
        self.space = f"hashing-v1:{dims}"

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
    space: str = "st:all-MiniLM-L6-v2:384"

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

# ---------------------------------------------------------------------------
# Hosted embeddings over any OpenAI-compatible ``/v1/embeddings`` endpoint.
#
# Stdlib urllib, matching the analyst provider: no new dependency for a request this simple, and
# the same failure surface everyone here already knows.
#
# PROVIDER-AGNOSTIC ON PURPOSE. The endpoint, the model and the key are configuration, so choosing a
# vendor is a deployment decision rather than a code change, and the deployment that has not chosen
# one keeps working on the lexical fallback. Whichever vendor is chosen has to be named in the
# privacy policy's subprocessor list first: this sends other people's public posts off our servers,
# and those people are not our users and never agreed to anything.
# ---------------------------------------------------------------------------


class EmbeddingUnavailable(RuntimeError):
    """The hosted embedder could not answer. Raised rather than silently degraded, deliberately.

    A caller that catches this must skip the work, NOT substitute a different embedder. See
    ``Embedder.space``: vectors from two embedders are not comparable, and a batch quietly embedded
    in the fallback space matches no existing topic, spawns a duplicate of every topic it touches,
    and reports nothing. Skipping is recoverable, because the utterance store keeps the text and the
    assignment can be re-driven later. A forked topic space is not.
    """


class ApiEmbedder:
    """Hosted embeddings, batched, with no fallback of its own."""

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        api_key: str | None,
        dimensions: int | None = None,
        timeout: float = 30.0,
        batch_size: int = 96,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self._api_key = api_key
        self.timeout = timeout
        self.batch_size = max(1, batch_size)
        # Width is not known until the first response when the provider is not asked for a specific
        # one. `space` is finalised at the same moment, so a caller must read it AFTER embedding.
        self.dimensions = dimensions or 0
        self._requested_dimensions = dimensions
        self.space = self._space_for(self.dimensions)

    def _space_for(self, dims: int) -> str:
        return f"api:{self.model}:{dims}"

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        out: list[list[float]] = []
        for start in range(0, len(texts), self.batch_size):
            out.extend(self._embed_batch(texts[start:start + self.batch_size]))
        return out

    def embed_one(self, text: str) -> list[float]:
        return self.embed([text])[0]

    def _embed_batch(self, batch: list[str]) -> list[list[float]]:
        import json
        import urllib.error
        import urllib.request

        payload: dict = {"model": self.model, "input": batch}
        if self._requested_dimensions:
            payload["dimensions"] = self._requested_dimensions

        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(self.base_url, data=body, headers=self._headers())
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                parsed = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as he:  # pragma: no cover - exercised via tests with a stub
            # The status, never the body: a provider error body can echo the input back, and the
            # input here is other people's posts.
            raise EmbeddingUnavailable(f"embedding provider HTTP {he.code}") from he
        except Exception as exc:  # noqa: BLE001
            raise EmbeddingUnavailable(f"embedding provider unreachable: {type(exc).__name__}") from exc

        data = parsed.get("data")
        if not isinstance(data, list) or len(data) != len(batch):
            # A short reply would silently misalign every vector with the wrong text, which is worse
            # than no embedding at all: the topic assignment would be confidently wrong.
            raise EmbeddingUnavailable(
                f"embedding provider returned {len(data) if isinstance(data, list) else 'no'} "
                f"vectors for {len(batch)} inputs"
            )

        vectors: list[list[float]] = []
        for row in sorted(data, key=lambda r: r.get("index", 0) if isinstance(r, dict) else 0):
            vec = row.get("embedding") if isinstance(row, dict) else None
            if not isinstance(vec, list) or not vec:
                raise EmbeddingUnavailable("embedding provider returned an empty vector")
            vectors.append([float(v) for v in vec])

        width = len(vectors[0])
        if any(len(v) != width for v in vectors):
            raise EmbeddingUnavailable("embedding provider returned mixed widths")
        if self.dimensions and width != self.dimensions:
            raise EmbeddingUnavailable(
                f"embedding width changed from {self.dimensions} to {width}"
            )
        self.dimensions = width
        self.space = self._space_for(width)

        # Unit vectors, so `cosine` stays a dot product for every embedder in this module. Providers
        # differ on whether they normalise, and clustering must not depend on which one is behind it.
        return [_normalise(v) for v in vectors]


def _normalise(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in vec))
    if norm <= 0:
        return vec
    return [v / norm for v in vec]


_embedder: Embedder | None = None
_override: Embedder | None = None


def get_embedder() -> Embedder:
    """The embedder this deployment is configured for.

    Order is deliberate: the hosted API first when it is configured, because it is the only option
    that catches a paraphrase and paraphrase is the case cross-investigation topic detection exists
    to catch; then a local model if the package happens to be installed; then the lexical fallback,
    which always works and never pretends to be more than it is.

    The chosen embedder is cached for the process. Switching between them mid-run would mix vector
    spaces, which does not raise anything and instead forks the topic space in half (see
    ``Embedder.space``).
    """
    global _embedder
    if _override is not None:
        return _override
    if _embedder is not None:
        return _embedder

    hosted = _configured_api_embedder()
    if hosted is not None:
        _embedder = hosted
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


def _configured_api_embedder() -> "ApiEmbedder | None":
    """Build the hosted embedder, or return None when this deployment has not configured one.

    A URL and a model are required. **The vendor name is required too**, and that is not
    bureaucracy: the name is what the privacy policy has to disclose before other people's posts
    leave our servers, and a deployment that cannot say who is processing them should not be sending
    them. Refusing here makes that a configuration error rather than a disclosure gap nobody notices.
    """
    try:
        from app.core.config import get_settings
        settings = get_settings()
    except Exception:  # noqa: BLE001 - configuration must never break ingest
        return None

    base_url = (settings.narrative_embedding_base_url or "").strip()
    model = (settings.narrative_embedding_model or "").strip()
    provider = (settings.narrative_embedding_provider or "").strip()
    if not base_url or not model or not provider:
        return None

    return ApiEmbedder(
        base_url=base_url,
        model=model,
        api_key=(settings.narrative_embedding_api_key or "").strip() or None,
        dimensions=settings.narrative_embedding_dimensions,
        timeout=settings.narrative_embedding_timeout_seconds,
        batch_size=settings.narrative_embedding_batch_size,
    )


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
