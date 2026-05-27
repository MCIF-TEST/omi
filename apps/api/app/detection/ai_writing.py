"""AI-writing fingerprint detector.

We do *not* try to label individual sentences as AI vs human. We estimate a
corpus-level probability that the content has been heavily AI-assisted by
combining several stylistic tells:

- **Burstiness** — sentence-length variance / mean. AI text is famously
  low-burstiness.
- **Hedging / template phrase frequency** — common GPT-era boilerplate.
- **Em-dash and Oxford-comma rate** — empirically elevated in AI output.
- **Sentence-start template repetition** — fraction of sentences sharing
  their opening bigram.

All evidence is phrased "consistent with AI assistance". Never "AI-generated".
"""

from __future__ import annotations

import math
import re
from collections import Counter

from app.schemas import Post, SignalResult


_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z\"'(])")
_WORD_RE = re.compile(r"\w+", re.UNICODE)

# Conservative list — every entry has to be genuinely overrepresented in AI
# output relative to typical social-media writing. Expand cautiously; false
# positives here are expensive because they bias the corpus-level score.
_AI_HEDGES = (
    # Classic GPT-era boilerplate
    "it's worth noting",
    "it is worth noting",
    "it's important to note",
    "it is important to",
    "in conclusion",
    "in summary",
    "moreover",
    "furthermore",
    "additionally",
    "delve into",
    "tapestry of",
    "navigating the",
    "in the realm of",
    "in today's fast-paced",
    "shed light on",
    "underscores the",
    "underscore the",
    "at its core",
    "a multifaceted",
    "ever-evolving",
    "let's explore",
    "let's dive into",
    # 2024-2025 era LLM tells
    "stands as a testament",
    "speaks volumes",
    "in essence",
    "at the heart of",
    "embark on a journey",
    "in stark contrast",
    "this raises important questions",
    "what's particularly fascinating",
    "intricate",
    "intricacies of",
    "i appreciate you sharing",
    "thanks for breaking this down",
    "great breakdown",
    "this is such a thoughtful",
    "a nuanced take",
    "it's truly remarkable",
    "captures the essence",
    "from this perspective",
    "fundamentally important",
    "cannot be overstated",
    "paramount importance",
    "speaks to the broader",
)

MIN_WORDS_FOR_AI_WRITING = 120


def analyze_ai_writing(posts: list[Post]) -> SignalResult:
    corpus = " ".join(p.text for p in posts if p.text).strip()
    word_count = len(_WORD_RE.findall(corpus))

    if word_count < MIN_WORDS_FOR_AI_WRITING:
        return SignalResult(
            name="ai_writing",
            probability=0.5,
            confidence=0.0,
            evidence=[
                f"Insufficient text for stylometric analysis ({word_count} words "
                f"< {MIN_WORDS_FOR_AI_WRITING} needed)."
            ],
        )

    sentences = _split_sentences(corpus)
    sentences = [s.strip() for s in sentences if len(_WORD_RE.findall(s)) >= 3]
    if len(sentences) < 6:
        return SignalResult(
            name="ai_writing",
            probability=0.5,
            confidence=0.0,
            evidence=["Not enough complete sentences for stylometric analysis."],
        )

    burst_prob, burstiness = _burstiness_signal(sentences)
    hedge_prob, hedge_rate = _hedging_signal(corpus, len(sentences))
    em_dash_prob, em_dash_rate = _em_dash_signal(corpus, len(sentences))
    template_prob, template_rate = _template_start_signal(sentences)

    sub = {
        "burstiness": burstiness,
        "hedge_phrase_rate": hedge_rate,
        "em_dash_rate": em_dash_rate,
        "sentence_start_repetition": template_rate,
    }

    blended = (
        0.30 * burst_prob
        + 0.30 * hedge_prob
        + 0.15 * em_dash_prob
        + 0.25 * template_prob
    )

    evidence: list[str] = []
    if burst_prob > 0.6:
        evidence.append(
            f"Sentence-length variation is unusually low (burstiness={burstiness:.2f}); "
            "patterns consistent with AI-assisted writing."
        )
    if hedge_prob > 0.6:
        evidence.append(
            f"Elevated frequency of hedging / boilerplate phrases "
            f"({hedge_rate:.2f} per sentence) — common in LLM output."
        )
    if em_dash_prob > 0.6:
        evidence.append(
            f"Em-dash usage is unusually frequent ({em_dash_rate:.2f}/sentence)."
        )
    if template_prob > 0.6:
        evidence.append(
            f"{template_rate:.0%} of sentences share their opening bigram with another, "
            "indicating structural repetition."
        )
    if not evidence:
        evidence.append("Writing style does not exhibit prominent AI tells.")

    # Stylometric tells are usually visible by ~500 words.
    confidence = min(1.0, word_count / 600.0)

    return SignalResult(
        name="ai_writing",
        probability=_clip01(blended),
        confidence=confidence,
        evidence=evidence,
        sub_signals=sub,
    )


# ---------------------------------------------------------------------------
# Sub-signals
# ---------------------------------------------------------------------------


def _burstiness_signal(sentences: list[str]) -> tuple[float, float]:
    lengths = [len(_WORD_RE.findall(s)) for s in sentences]
    if not lengths:
        return 0.5, 0.0
    mean = sum(lengths) / len(lengths)
    if mean == 0:
        return 0.5, 0.0
    var = sum((l - mean) ** 2 for l in lengths) / len(lengths)
    burstiness = math.sqrt(var) / mean
    # Burstiness 0.2 → very AI-like; 0.6 → human-like; 1.0+ → very human.
    prob = 1.0 / (1.0 + math.exp((burstiness - 0.45) * 10))
    return prob, burstiness


def _hedging_signal(corpus: str, sentence_count: int) -> tuple[float, float]:
    lower = corpus.lower()
    hits = sum(lower.count(phrase) for phrase in _AI_HEDGES)
    rate = hits / max(1, sentence_count)
    # rate of 0.10/sentence ≈ noticeable; 0.25 ≈ heavy.
    prob = 1.0 / (1.0 + math.exp(-(rate - 0.08) * 20))
    return prob, rate


def _em_dash_signal(corpus: str, sentence_count: int) -> tuple[float, float]:
    # Em-dash (U+2014) is the giveaway; en-dash (U+2013) is too common for
    # numeric ranges to count cleanly.
    count = corpus.count("—")
    rate = count / max(1, sentence_count)
    prob = 1.0 / (1.0 + math.exp(-(rate - 0.2) * 8))
    return prob, rate


def _template_start_signal(sentences: list[str]) -> tuple[float, float]:
    starts: list[tuple[str, str]] = []
    for s in sentences:
        tokens = _WORD_RE.findall(s.lower())
        if len(tokens) >= 2:
            starts.append((tokens[0], tokens[1]))
    if not starts:
        return 0.5, 0.0
    counts = Counter(starts)
    duplicate_starts = sum(c for c in counts.values() if c > 1)
    rate = duplicate_starts / len(starts)
    # rate 0.20 ≈ noticeable; 0.45 ≈ obvious template.
    prob = 1.0 / (1.0 + math.exp(-(rate - 0.18) * 12))
    return prob, rate


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------


def _split_sentences(text: str) -> list[str]:
    if not text:
        return []
    # First normalize all newlines to single spaces — social media text often
    # uses newlines mid-thought.
    cleaned = re.sub(r"\s+", " ", text).strip()
    parts = _SENTENCE_SPLIT.split(cleaned)
    # Catch trailing sentences without final punctuation.
    return [p for p in parts if p]


def _clip01(x: float) -> float:
    return max(0.0, min(1.0, x))
