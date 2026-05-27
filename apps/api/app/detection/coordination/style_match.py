"""Linguistic-style fingerprint matching ("same writer" detector).

Two random humans writing on the same topic produce different stylometric
fingerprints. Two sock-puppet accounts run by the same operator (or the
same LLM with the same system prompt) produce nearly-identical ones.

We extract a small per-commenter style vector from their recent comment
history:

* sentence-length burstiness
* hedge-phrase rate
* em-dash rate per sentence
* first-person pronoun rate
* type-token ratio
* mean sentence length (normalized)
* punctuation density

Pairs with style-distance below a tight threshold are flagged. Connected
components of flagged pairs become coordination clusters.

This detector is intentionally strict: stylometry is noisy and false
positives are expensive (they imply "the same human wrote these"). We err
toward fewer, higher-confidence matches.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

from app.detection.coordination._types import (
    CoordinationCluster,
    CoordinationFinding,
    _UnionFind,
)


_WORD_RE = re.compile(r"\w+", re.UNICODE)
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z\"'(])")
_FIRST_PERSON = {"i", "me", "my", "mine", "myself", "we", "us", "our", "ours"}
_HEDGES = (
    "it's worth noting", "moreover", "furthermore", "additionally",
    "in conclusion", "delve into", "tapestry of",
)


@dataclass
class StyleEntry:
    external_id: str
    handle: str
    texts: list[str]


def _style_vector(texts: list[str]) -> list[float] | None:
    corpus = " ".join(t for t in texts if t).strip()
    words = [w.lower() for w in _WORD_RE.findall(corpus)]
    if len(words) < 40:
        return None  # too little text to fingerprint a style
    cleaned = re.sub(r"\s+", " ", corpus)
    sentences = [s for s in _SENTENCE_SPLIT.split(cleaned)
                 if len(_WORD_RE.findall(s)) >= 3]
    if len(sentences) < 3:
        return None

    lengths = [len(_WORD_RE.findall(s)) for s in sentences]
    mean_len = sum(lengths) / len(lengths)
    var = sum((l - mean_len) ** 2 for l in lengths) / len(lengths)
    burstiness = math.sqrt(var) / mean_len if mean_len else 0.0

    lower = corpus.lower()
    hedge_hits = sum(lower.count(p) for p in _HEDGES)
    hedge_rate = hedge_hits / max(1, len(sentences))
    em_dash_rate = corpus.count("—") / max(1, len(sentences))
    first_person_rate = sum(1 for w in words if w in _FIRST_PERSON) / len(words)
    type_token = len(set(words)) / len(words)
    norm_mean_len = min(1.0, mean_len / 30.0)
    punct_density = sum(1 for c in corpus if c in ".,;:!?—–-") / max(1, len(corpus))

    # Each component is roughly 0..1 so euclidean is sane.
    return [
        min(1.0, burstiness / 1.2),
        min(1.0, hedge_rate / 0.5),
        min(1.0, em_dash_rate / 1.0),
        min(1.0, first_person_rate / 0.3),
        type_token,
        norm_mean_len,
        min(1.0, punct_density * 10),
    ]


def _euclid(a: list[float], b: list[float]) -> float:
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def detect_style_matches(
    entries: list[StyleEntry],
    *,
    distance_threshold: float = 0.10,
    min_cluster_size: int = 2,
) -> CoordinationFinding:
    vectors: list[tuple[StyleEntry, list[float]]] = []
    for e in entries:
        v = _style_vector(e.texts)
        if v is not None:
            vectors.append((e, v))

    if len(vectors) < 2:
        return CoordinationFinding(
            method="style_match",
            overall_score=0.5,
            confidence=0.0,
            clusters=[],
            evidence=[
                f"Only {len(vectors)} commenter(s) had enough text to fingerprint a writing style."
            ],
        )

    uf = _UnionFind(range(len(vectors)))
    pair_distances: list[float] = []
    for i in range(len(vectors)):
        for j in range(i + 1, len(vectors)):
            d = _euclid(vectors[i][1], vectors[j][1])
            pair_distances.append(d)
            if d <= distance_threshold:
                uf.union(i, j)

    clusters: list[CoordinationCluster] = []
    for _, idxs in uf.components().items():
        if len(idxs) < min_cluster_size:
            continue
        members = [vectors[i][0].external_id for i in idxs]
        # Mean intra-cluster distance.
        intra = []
        for a in range(len(idxs)):
            for b in range(a + 1, len(idxs)):
                intra.append(_euclid(vectors[idxs[a]][1], vectors[idxs[b]][1]))
        mean_d = sum(intra) / len(intra) if intra else 0.0
        score = min(1.0, 0.65 + 0.3 * (1.0 - mean_d / distance_threshold))
        clusters.append(
            CoordinationCluster(
                method="style_match",
                members=sorted(members),
                score=score,
                evidence=[
                    f"{len(idxs)} accounts share an implausibly similar writing-style "
                    f"fingerprint (mean style-distance {mean_d:.3f}); patterns "
                    f"consistent with a single author behind multiple accounts."
                ],
                metadata={
                    "size": float(len(idxs)),
                    "mean_style_distance": mean_d,
                },
            )
        )

    flagged = {m for c in clusters for m in c.members}
    share = len(flagged) / len(vectors) if vectors else 0.0
    overall = 1.0 / (1.0 + math.exp(-(share - 0.10) * 12))
    confidence = min(1.0, len(vectors) / 20.0)
    evidence = (
        [
            f"Found {len(clusters)} style-similar group(s) covering "
            f"{len(flagged)} account(s)."
        ]
        if clusters
        else ["No implausibly similar writing styles detected across commenters."]
    )

    return CoordinationFinding(
        method="style_match",
        overall_score=float(overall),
        confidence=confidence,
        clusters=clusters,
        evidence=evidence,
    )
