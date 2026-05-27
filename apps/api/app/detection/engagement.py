"""Engagement / content-style detector.

Single-account detector that catches the spam, promo, and engagement-farm
patterns that the per-account behavioral detectors miss. Looks at:

* **Emoji density** — total emoji count divided by word count. Above 5%
  is unusual for organic comments; promo accounts ramp into the double
  digits.
* **URL inclusion rate** — fraction of posts containing a link.
  Spam/affiliate accounts approach 100%; organic users rarely link.
* **Repeated emoji bursts** — 🚀🚀🚀 / 🔥🔥🔥 patterns indicating
  promotional copy-paste.
* **Engagement bait** — phrases optimized to extract algorithmic
  engagement signals from viewers, e.g. "drop a like", "subscribe for
  more", "let me know in the comments", "link in bio".

Catches obvious-promo accounts that score clean on temporal / semantic
detectors because their behavior at the API level *is* legitimate
posting — they're just spamming people.
"""

from __future__ import annotations

import re

from app.schemas import Post, SignalResult


# Broad emoji block. Catches the most common social-media emoji ranges
# without going overboard on rare characters.
_EMOJI_RE = re.compile(
    "["
    "\U0001F300-\U0001F6FF"  # symbols + transport + map symbols
    "\U0001F900-\U0001FAFF"  # supplemental + extended symbols
    "\U0001F1E6-\U0001F1FF"  # regional indicator (flags)
    "☀-➿"          # misc symbols + dingbats
    "]"
)
_URL_RE = re.compile(
    r"https?://\S+"
    r"|www\.\S+"
    r"|\b\S+\.(?:com|net|org|io|gg|me|tv|ly|to|app|xyz|store|link)\b/?\S*",
    re.IGNORECASE,
)
_REPEATED_EMOJI_RE = re.compile(
    r"(["
    "\U0001F300-\U0001F6FF"
    "\U0001F900-\U0001FAFF"
    "☀-➿"
    r"])\1{2,}"
)
_WORD_RE = re.compile(r"\w+", re.UNICODE)

_ENGAGEMENT_BAIT_PHRASES = (
    "subscribe for more", "drop a like", "smash that like",
    "smash the like", "smash subscribe", "smash that subscribe",
    "leave a like", "hit subscribe", "hit the subscribe",
    "ring the bell", "ring that bell", "click the bell",
    "comment below if", "let me know in the comments",
    "let us know in the comments", "watch till the end",
    "watch until the end", "share this video", "share if you",
    "like if you agree", "like if you ", "follow for more",
    "follow me for", "tag a friend", "tag your friend",
    "link in bio", "link in description", "link in the description",
    "check my bio", "check my profile", "dm me for",
    "use my code", "promo code", "discount code", "affiliate link",
    "free shipping", "limited time", "click here", "click the link",
    "join now", "sign up now", "register now",
)

MIN_POSTS_FOR_ENGAGEMENT = 5
MIN_WORDS_FOR_ENGAGEMENT = 40


def analyze_engagement(posts: list[Post]) -> SignalResult:
    texts = [p.text for p in posts if p.text and p.text.strip()]
    if len(texts) < MIN_POSTS_FOR_ENGAGEMENT:
        return SignalResult(
            name="engagement",
            probability=0.5,
            confidence=0.0,
            evidence=[
                f"Insufficient post data ({len(texts)} < {MIN_POSTS_FOR_ENGAGEMENT})."
            ],
        )

    corpus = " ".join(texts)
    word_count = len(_WORD_RE.findall(corpus))
    if word_count < MIN_WORDS_FOR_ENGAGEMENT:
        return SignalResult(
            name="engagement",
            probability=0.5,
            confidence=0.0,
            evidence=[f"Posts too short ({word_count} words)."],
        )

    emoji_total = len(_EMOJI_RE.findall(corpus))
    emoji_per_post = emoji_total / len(texts)
    emoji_density = emoji_total / max(1, word_count)

    url_posts = sum(1 for t in texts if _URL_RE.search(t))
    url_rate = url_posts / len(texts)

    burst_posts = sum(1 for t in texts if _REPEATED_EMOJI_RE.search(t))
    burst_rate = burst_posts / len(texts)

    lower = corpus.lower()
    bait_hits = sum(lower.count(p) for p in _ENGAGEMENT_BAIT_PHRASES)
    bait_rate = bait_hits / len(texts)

    # Map raw rates to per-signal probabilities. Each one is gentle below
    # the suspicion threshold and rises sharply past it.
    emoji_prob = _clip01((emoji_density - 0.05) * 3.0)      # > 5% per word elevated
    url_prob = _clip01((url_rate - 0.10) * 2.5)              # > 10% of posts have URLs
    burst_prob = _clip01((burst_rate - 0.08) * 4.0)          # > 8% have emoji bursts
    bait_prob = _clip01((bait_rate - 0.10) * 3.0)            # > 0.10 phrases per post

    blended = (
        0.30 * emoji_prob
        + 0.30 * url_prob
        + 0.15 * burst_prob
        + 0.25 * bait_prob
    )

    sub = {
        "emoji_per_post": emoji_per_post,
        "emoji_density": emoji_density,
        "url_inclusion_rate": url_rate,
        "emoji_burst_rate": burst_rate,
        "engagement_bait_rate": bait_rate,
    }

    evidence: list[str] = []
    if emoji_prob > 0.55:
        evidence.append(
            f"Emoji density of {emoji_density*100:.1f}% per word is unusually "
            "high; patterns consistent with promotional or spam-style accounts."
        )
    if url_prob > 0.55:
        evidence.append(
            f"{url_rate*100:.0f}% of posts contain links — far above the "
            "organic baseline (most users rarely include URLs in comments)."
        )
    if burst_prob > 0.55:
        evidence.append(
            f"Frequent emoji bursts (🚀🚀🚀 / 🔥🔥🔥-style) appearing in "
            f"{burst_rate*100:.0f}% of posts."
        )
    if bait_prob > 0.55:
        evidence.append(
            f"Engagement-bait phrases (\"subscribe for more\", \"drop a like\", "
            f"etc.) at {bait_rate:.2f} per post — algorithmic engagement "
            "optimization patterns."
        )
    if not evidence:
        evidence.append("Content style does not exhibit notable spam/promo tells.")

    confidence = min(1.0, len(texts) / 30.0)

    return SignalResult(
        name="engagement",
        probability=_clip01(blended),
        confidence=confidence,
        evidence=evidence,
        sub_signals=sub,
    )


def _clip01(x: float) -> float:
    return max(0.0, min(1.0, float(x)))
