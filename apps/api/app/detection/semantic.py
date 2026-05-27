"""Semantic repetition detector.

Hypothesis: coordinated networks and AI-spam farms reuse a small pool of
messages (paraphrased or not). Honest accounts produce semantically diverse
content. We measure repetitiveness with two complementary signals:

1. Embedding-based cosine similarity (TF-IDF by default, sentence-transformers
   if installed — see ``_get_embeddings``).
2. Lexical n-gram overlap (cheap, catches copy-paste even when embeddings are
   unavailable or noisy).

Either signal alone is fallible; we report a blended probability.
"""

from __future__ import annotations

import math
import re
from collections import Counter

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from app.schemas import Post, SignalResult


MIN_POSTS_FOR_SEMANTIC = 5
_WORD_RE = re.compile(r"\w+", re.UNICODE)


def analyze_semantic(posts: list[Post]) -> SignalResult:
    texts = [p.text.strip() for p in posts if p.text and p.text.strip()]
    if len(texts) < MIN_POSTS_FOR_SEMANTIC:
        return SignalResult(
            name="semantic",
            probability=0.5,
            confidence=0.0,
            evidence=[
                f"Insufficient text data ({len(texts)} posts < {MIN_POSTS_FOR_SEMANTIC} needed)."
            ],
        )

    embed_prob, mean_sim, top_cluster_mass = _embedding_signal(texts)
    ngram_prob, ngram_jaccard = _ngram_signal(texts)

    # Weight embeddings higher when we have many samples.
    embed_weight = min(0.75, 0.4 + len(texts) / 200.0)
    blended = embed_weight * embed_prob + (1 - embed_weight) * ngram_prob

    sub = {
        "mean_pairwise_cosine": mean_sim,
        "top_cluster_mass": top_cluster_mass,
        "mean_ngram_jaccard": ngram_jaccard,
    }

    evidence: list[str] = []
    if mean_sim > 0.45:
        evidence.append(
            f"Posts are unusually similar to each other (mean cosine={mean_sim:.2f}); "
            "patterns consistent with template-driven or paraphrased output."
        )
    if top_cluster_mass > 0.40:
        evidence.append(
            f"{top_cluster_mass:.0%} of posts cluster into a single semantic group, "
            "suggesting narrow message-pool reuse."
        )
    if ngram_jaccard > 0.25:
        evidence.append(
            f"High lexical overlap across posts (mean 5-gram Jaccard={ngram_jaccard:.2f}); "
            "indicates direct text reuse, not just paraphrasing."
        )
    if not evidence:
        evidence.append("Post content shows healthy semantic diversity.")

    # Repetition becomes statistically meaningful well before 150 samples:
    # 30 posts already give 435 pairwise comparisons.
    confidence = min(1.0, len(texts) / 40.0)

    return SignalResult(
        name="semantic",
        probability=_clip01(blended),
        confidence=confidence,
        evidence=evidence,
        sub_signals=sub,
    )


# ---------------------------------------------------------------------------
# Embedding-based similarity
# ---------------------------------------------------------------------------


def _embedding_signal(texts: list[str]) -> tuple[float, float, float]:
    """Returns (probability, mean_pairwise_similarity, top_cluster_mass)."""
    vectors = _get_embeddings(texts)
    if vectors is None or vectors.shape[0] < 2:
        return 0.5, 0.0, 0.0

    sim = cosine_similarity(vectors)
    n = sim.shape[0]
    # Mean of upper triangle excluding diagonal.
    iu = np.triu_indices(n, k=1)
    pairwise = sim[iu]
    mean_sim = float(pairwise.mean()) if pairwise.size else 0.0

    # Simple greedy clustering at 0.55 similarity threshold (post-paraphrase floor).
    top_cluster_mass = _largest_cluster_fraction(sim, threshold=0.55)

    # Map to probability: mean_sim ∈ [0.1, 0.6] ↦ [0.2, 0.9] roughly.
    sim_prob = 1.0 / (1.0 + math.exp(-(mean_sim - 0.35) * 10))
    cluster_prob = top_cluster_mass  # already 0..1
    prob = 0.6 * sim_prob + 0.4 * cluster_prob
    return prob, mean_sim, top_cluster_mass


def _get_embeddings(texts: list[str]) -> np.ndarray | None:
    """Lazy embedding loader.

    Tries `sentence-transformers` if installed; otherwise falls back to TF-IDF.
    Returns an (n, d) float array or None on failure.
    """
    try:
        model = _load_st_model()
        if model is not None:
            return np.asarray(model.encode(texts, show_progress_bar=False))
    except Exception:
        # If a transformer was installed but fails (e.g. no internet to fetch
        # weights), silently fall back. We never let the API hot path die on
        # an optional dep.
        pass

    try:
        # max_df=1.0: don't filter "too common" terms — we *want* to detect
        # repetition. sublinear_tf dampens dominant tokens so a single repeated
        # word doesn't overwhelm everything else.
        vectorizer = TfidfVectorizer(
            lowercase=True,
            ngram_range=(1, 2),
            min_df=1,
            max_df=1.0,
            max_features=4096,
            sublinear_tf=True,
        )
        matrix = vectorizer.fit_transform(texts)
        return matrix.toarray().astype(np.float32)
    except ValueError:
        # Happens when every text is empty after tokenization.
        return None


_ST_MODEL = None


def _load_st_model():
    global _ST_MODEL
    if _ST_MODEL is not None:
        return _ST_MODEL
    try:
        from sentence_transformers import SentenceTransformer  # type: ignore
        from app.core.config import get_settings

        _ST_MODEL = SentenceTransformer(get_settings().embedding_model)
        return _ST_MODEL
    except Exception:
        return None


def _largest_cluster_fraction(sim: np.ndarray, threshold: float) -> float:
    """Greedy single-linkage clustering at the given cosine threshold.

    Returns the fraction of items in the largest cluster.
    """
    n = sim.shape[0]
    parent = list(range(n))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for i in range(n):
        for j in range(i + 1, n):
            if sim[i, j] >= threshold:
                union(i, j)

    sizes: Counter[int] = Counter(find(i) for i in range(n))
    largest = max(sizes.values()) if sizes else 0
    return largest / n


# ---------------------------------------------------------------------------
# N-gram fallback / supplement
# ---------------------------------------------------------------------------


def _ngram_signal(texts: list[str], n: int = 5) -> tuple[float, float]:
    """Mean Jaccard similarity over character-aware word n-grams."""
    shingles = [_shingles(t, n) for t in texts]
    shingles = [s for s in shingles if s]
    if len(shingles) < 2:
        return 0.5, 0.0

    pairs = 0
    total = 0.0
    for i in range(len(shingles)):
        for j in range(i + 1, len(shingles)):
            a, b = shingles[i], shingles[j]
            if not a or not b:
                continue
            inter = len(a & b)
            union = len(a | b)
            if union > 0:
                total += inter / union
                pairs += 1
    if pairs == 0:
        return 0.5, 0.0

    mean_j = total / pairs
    # Jaccard 0.25 is already alarming for organic posting.
    prob = 1.0 / (1.0 + math.exp(-(mean_j - 0.15) * 18))
    return prob, mean_j


def _shingles(text: str, n: int) -> set[tuple[str, ...]]:
    tokens = [t.lower() for t in _WORD_RE.findall(text)]
    if len(tokens) < n:
        return {tuple(tokens)} if tokens else set()
    return {tuple(tokens[i : i + n]) for i in range(len(tokens) - n + 1)}


def _clip01(x: float) -> float:
    return max(0.0, min(1.0, x))
