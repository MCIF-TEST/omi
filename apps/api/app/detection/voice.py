"""First-person voice / pronoun rate detector.

Single-account stylometric signal that complements the existing
``ai_writing`` detector. Real humans use first-person pronouns
("I", "me", "my", "we", "our") at roughly 5-15% of their words. Two
failure modes signal something off:

* **< 1%** — impersonal, broadcast-style text. Common in AI-generated
  comments and in pure amplification bots that exist to push talking
  points, not converse.
* **> 25%** — overcompensating. Some prompt-engineered bots aimed at
  faking authenticity overshoot ("I really felt this. I have to say. I
  agree so much. I think it's...").

We score the *distance* from the typical human band, not the raw rate.
"""

from __future__ import annotations

import re

from app.schemas import Post, SignalResult


_WORD_RE = re.compile(r"\w+", re.UNICODE)
_FIRST_PERSON = {"i", "me", "my", "mine", "myself", "we", "us", "our", "ours"}

MIN_WORDS_FOR_VOICE = 80


def analyze_voice(posts: list[Post]) -> SignalResult:
    texts = [p.text for p in posts if p.text]
    corpus = " ".join(texts).strip()
    words = [w.lower() for w in _WORD_RE.findall(corpus)]
    if len(words) < MIN_WORDS_FOR_VOICE:
        return SignalResult(
            name="voice",
            probability=0.5,
            confidence=0.0,
            evidence=[
                f"Insufficient text for voice analysis ({len(words)} words "
                f"< {MIN_WORDS_FOR_VOICE} needed)."
            ],
        )

    fp_count = sum(1 for w in words if w in _FIRST_PERSON)
    rate = fp_count / len(words)
    avg_post_words = len(words) / max(1, len(texts))

    # Distance from a generous healthy band. Casual social-media writing
    # routinely drops the implied "I" ("finally got around to fixing the
    # faucet"), so we only really flag the extremes.
    if rate < 0.005:
        dist = 1.0  # 0% — almost certainly impersonal broadcast
    elif rate < 0.02:
        dist = 0.45 * (0.02 - rate) / 0.015
    elif rate > 0.30:
        dist = min(1.0, (rate - 0.30) / 0.15)
    else:
        dist = 0.0

    prob = 0.35 + 0.45 * dist  # max ~0.80; never on its own a verdict

    # Confidence collapses on short posts: humans routinely drop the
    # implied "I" in tweet-length text ("finally got around to fixing the
    # faucet"), so a low pronoun rate is uninformative there. Voice
    # detection is mostly useful for paragraph-length content (YouTube
    # comments, Reddit posts, blog comments).
    if avg_post_words < 12:
        length_factor = 0.0
    elif avg_post_words < 25:
        length_factor = (avg_post_words - 12) / 13
    else:
        length_factor = 1.0
    confidence = min(1.0, len(words) / 800.0) * length_factor

    evidence: list[str] = []
    if rate < 0.005:
        evidence.append(
            f"First-person pronouns appear in only {rate*100:.1f}% of words — "
            "writing reads as impersonal / broadcast-style."
        )
    elif rate > 0.30:
        evidence.append(
            f"First-person pronouns make up {rate*100:.1f}% of words — "
            "unusually self-referential."
        )
    else:
        evidence.append(
            f"First-person pronoun rate of {rate*100:.1f}% sits within the "
            f"typical human range."
        )

    return SignalResult(
        name="voice",
        probability=_clip01(prob),
        confidence=confidence,
        evidence=evidence,
        sub_signals={"first_person_rate": rate},
    )


def _clip01(x: float) -> float:
    return max(0.0, min(1.0, x))
