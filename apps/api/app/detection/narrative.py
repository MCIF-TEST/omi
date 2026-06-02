"""Narrative injection / political-astroturf signal.

Hypothesis: coordinated influence operations (astroturf campaigns, hybrid
political ops) inject specific narrative phrases — "they don't want you to
know", "spread this everywhere", "mainstream media is lying" — into the post
histories of inauthentic amplifiers.

Unlike semantic.py (structural repetition *within* an account), this detector
reads *content theme*: whether posts contain language catalogued from public IO
disclosures (Twitter/X transparency reports, DFRLab, Stanford IO Observatory).
It catches varied-text astroturf where different phrases appear post-to-post
but the underlying operation fingerprint is the same.

This is the primary signal for hybrid operations where individual accounts post
human-quality but coordinated political content.
"""

from __future__ import annotations

import math
import re

from app.schemas import Post, SignalResult


# Phrases drawn from publicly documented influence operations.
# Conservative: each pattern is characteristic enough that incidental organic
# usage is rare when it appears across multiple posts of the same account.
_ASTROTURF_PATTERNS: list[re.Pattern] = [
    # Mainstream-media delegitimisation
    re.compile(
        r"mainstream\s+media.{0,35}(doesn.?t|won.?t|can.?t|refuse[sd]?|never)\s+want",
        re.I,
    ),
    # Media-suppression framing: "(mainstream|corporate) media (won't|will never|
    # refuse to) (cover|show|report|tell)" — the press is hiding the story.
    re.compile(
        r"(mainstream|corporate|legacy|state)\s+media\s+(will\s+)?"
        r"(won.?t|never|refuse[sd]?\s+to|wont)\s+(cover|show|report|tell|touch)",
        re.I,
    ),
    # Establishment fear-framing
    re.compile(
        r"(they|them|the\s+establishment|the\s+elites?).{0,35}"
        r"(don.?t\s+want|hiding|covering\s+up|terrified|afraid|scared|desperate|panicking)",
        re.I,
    ),
    # Amplification call-to-action
    re.compile(
        r"(spread\s+this|share\s+this|get\s+this\s+out).{0,30}"
        r"(everywhere|before\s+they\s+delete|before\s+it.?s\s+gone|to\s+everyone)",
        re.I,
    ),
    # Urgency amplification: "share/spread ... before it gets removed/banned/
    # taken down/deleted/disappears" — coordinated pre-emptive distribution.
    re.compile(
        r"(share|spread|repost|send)\b.{0,40}"
        r"before\s+(it|they|this)\s+(gets?\s+)?"
        r"(remov|delet|ban|taken\s+down|disappear|gone|shut)",
        re.I,
    ),
    # Imperative repetition: "share share share", "share this now/before"
    re.compile(r"\bshare\s+(this\s+)?(now|share\s+share)\b", re.I),
    # Consciousness-raising call
    re.compile(r"\bwake\s+up\b.{0,25}(people|everyone|america|world|sheeple)", re.I),
    # Deep-state conspiracy marker
    re.compile(r"\bdeep\s+state\b", re.I),
    # Media-corruption tropes
    re.compile(
        r"(the\s+)?(corrupt|fake|lying|controlled|propaganda)\s+(media|news|press|narrative)",
        re.I,
    ),
    # Hidden-truth framing
    re.compile(r"(the\s+)?(real|hidden|suppressed|buried)\s+(truth|facts?|story)", re.I),
    # DYOR (disinformation context)
    re.compile(r"\bdo\s+your\s+own\s+research\b", re.I),
    # Silencing/censorship claims
    re.compile(
        r"(tr(y|ying)\s+to\s+silence|want\s+to\s+silence|silence\s+us|"
        r"being\s+silenced|shadow.?ban(ned)?|"
        r"(shut|take)\s+(it|this|us|them|him|her)\s+down|"
        r"banned\s+from\s+(every\s+)?(mainstream\s+)?(platform|social))",
        re.I,
    ),
    # Narrative-collapse celebration
    re.compile(r"(their\s+)?(narrative|script|story)\s+(is\s+)?(falling\s+apart|crumbling|exposed|collapsing)", re.I),
    # Named globalist conspiracy markers
    re.compile(r"\b(globalist|nwo|new\s+world\s+order)\b", re.I),
]

_MIN_POSTS = 3


def analyze_narrative(posts: list[Post]) -> SignalResult:
    """Detect political/disinformation astroturf language patterns."""
    texts = [p.text.strip() for p in posts if p.text and p.text.strip()]
    if len(texts) < _MIN_POSTS:
        return SignalResult(
            name="narrative",
            probability=0.5,
            confidence=0.0,
            evidence=[
                f"Insufficient posts for narrative analysis "
                f"({len(texts)} < {_MIN_POSTS})."
            ],
        )

    # One match per post is enough to count it.
    flagged_posts: list[tuple[int, str]] = []
    for i, text in enumerate(texts):
        for pat in _ASTROTURF_PATTERNS:
            m = pat.search(text)
            if m:
                flagged_posts.append((i, m.group(0)[:60]))
                break

    posts_with_markers = len({idx for idx, _ in flagged_posts})
    total_posts = len(texts)

    if posts_with_markers == 0:
        return SignalResult(
            name="narrative",
            probability=0.5,
            confidence=0.0,
            evidence=["No coordinated-narrative language patterns detected."],
        )

    marker_rate = posts_with_markers / total_posts

    # Probability: logistic on the fraction of posts that contain markers.
    # Centred LOW (0.12) because these are *explicit* astroturf phrases catalogued
    # from IO disclosures — legitimate accounts essentially never use them, so a
    # marker rate of even 15-20% is already strong evidence of a narrative-
    # injection operation. The old 0.30 centre mapped a 30%-marker account (3 of
    # 10 posts of overt "share before they delete it / mainstream media is hiding
    # this" content) to a neutral 0.50, contributing nothing to the composite.
    # rate=0.10 → ~0.43, rate=0.20 → ~0.75, rate=0.30 → ~0.93, rate=0.50 → ~0.996.
    # Low absolute counts are reined in by the confidence term below, not here.
    prob = 1.0 / (1.0 + math.exp(-(marker_rate - 0.12) * 14))

    # Confidence: absolute count of marker posts (not just rate) matters here.
    # 2 markers on 3 posts is different from 2 on 30. Also require a non-trivial
    # corpus so a single-post account with one bad phrase doesn't look like an
    # operation.
    abs_conf = min(1.0, posts_with_markers / 4.0)
    corpus_conf = min(1.0, total_posts / 8.0)
    confidence = abs_conf * corpus_conf

    snippets = [snip for _, snip in flagged_posts[:3]]
    evidence = [
        f"{posts_with_markers} of {total_posts} posts ({marker_rate:.0%}) contain "
        f"coordinated-narrative language. "
        f"Sample: {'; '.join(repr(s) for s in snippets)}."
    ]

    return SignalResult(
        name="narrative",
        probability=_clip01(prob),
        confidence=confidence,
        evidence=evidence,
        sub_signals={
            "posts_with_markers": float(posts_with_markers),
            "marker_rate": marker_rate,
        },
    )


def _clip01(x: float) -> float:
    return max(0.0, min(1.0, x))
