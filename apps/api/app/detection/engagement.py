"""Engagement / content-style detector.

Single-account detector that catches the spam, promo, and engagement-farm
patterns that the per-account behavioral detectors miss. It models spam as a
set of **independent, individually-sufficient axes** — an account is promotional
if it does *any one* of these blatantly:

* **Link spam** — fraction of posts containing a URL. Affiliate / promo accounts
  approach 100%; organic users rarely link.
* **Emoji density / bursts** — total emoji per word, plus 🚀🚀🚀 / 🔥🔥🔥-style
  repeated-emoji bursts indicating promotional copy-paste.
* **Engagement bait** — phrases optimised to extract algorithmic engagement,
  e.g. "drop a like", "subscribe for more", "smash that like", "follow me",
  "comment 'YES' below", "DM me".
* **Self-promotion / traffic redirection** — driving viewers to the author's own
  property: "link in bio", "on my channel", "my free course", "check out my".
* **Financial shilling** — cashtags ($MOON) plus pump language ("100x", "get in
  before", "to the moon", "insiders are accumulating").

Because spam is **disjunctive** (one blatant axis is enough), the axes are
combined with a noisy-OR rather than a weighted average — a 100%-link affiliate
account is not "30% suspicious" just because it doesn't also spam emoji. And
because blatant spam is *self-evident*, confidence is **strength-aware**: a
consistent, unambiguous pattern across even a handful of posts is a confident
call, not a low-confidence one gated purely on volume.

Catches obvious-promo accounts that score clean on temporal / semantic
detectors because their behavior at the API level *is* legitimate posting —
they're just spamming people.
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
# Link shorteners and affiliate/marketplace domains. A link to one of these is
# itself promotional evidence; a link to a news site or public document is not.
# This is what keeps journalists, researchers, and ordinary people who cite
# sources from being scored as link spammers.
_SHORTENER_RE = re.compile(
    r"\b(?:"
    r"bit\.ly|tinyurl|t\.co|goo\.gl|ow\.ly|buff\.ly|rebrand\.ly|cutt\.ly|shorturl"
    r"|lnkd\.in|linktr\.ee|linktree|geni\.us|shp\.ee|s\.click"
    r"|amzn\.to|amzn\.com|aliexpress|temu\.|shareasale|clickbank|gumroad"
    r")\b",
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

# Curated literal bait phrases (fast substring pass). Regexes below catch the
# productive/parametrised variants (e.g. "comment 'READY' below") that a fixed
# list can't enumerate.
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

# Parametrised engagement-bait / call-to-action patterns. These catch the
# follow-bait and DM-bait phrasings ("follow me if", "comment 'HOOK' below",
# "subscribe for daily tips", "I'll DM you") that the fixed list misses.
_BAIT_RE = re.compile(
    r"\b(?:"
    r"follow\s+(?:me|us|for|if|back)"
    r"|subscribe\s+(?:for|to|now|if|and)"
    r"|(?:smash|hit|drop|leave|tap)\s+(?:that\s+|the\s+|a\s+)?(?:like|sub(?:scribe)?|bell|follow)"
    r"|comment\s+['\"]?\w+['\"]?\s+(?:below|and|to|for|if)"
    r"|comment\s+(?:below|down below)"
    r"|(?:i'?ll|i\s+will)\s+(?:dm|message|send)\s+you"
    r"|dm\s+me"
    r"|like\s+and\s+subscribe"
    r"|don'?t\s+forget\s+to\s+(?:like|subscribe|follow)"
    r")\b",
    re.IGNORECASE,
)

# Self-promotion / traffic redirection: pointing viewers at the author's own
# channel, bio, store, course, or DMs. This is the unifying tell of "promo"
# and "follow-bait" accounts that don't necessarily spam links or emoji.
#
# Deliberately tight on the "my <noun>" branch: it matches only a closed set of
# *promotable property* nouns (channel, course, store, …). It must NOT fire on a
# journalist's "my sources" or "my follow-up piece", which is why there is no
# greedy "I … my" pattern here.
_SELF_PROMO_RE = re.compile(
    r"\b(?:"
    r"link\s+in\s+(?:my\s+)?(?:bio|description|desc|profile)"
    r"|(?:on|in|check|visit|from|via|to)\s+my\s+(?:channel|bio|profile|page|store|shop|course|guide|content|link|merch|discord|patreon|website|blog|podcast)"
    r"|my\s+(?:free\s+)?(?:channel|course|program|guide|ebook|store|shop|page|newsletter|masterclass|spreadsheet|setup|merch|discord|patreon|coaching|mentorship)"
    r"|check\s+(?:it|me|my|us)\s+out"
    r"|worth\s+checking\s+out"
    r"|use\s+(?:my\s+|the\s+)?(?:code|promo)"
    r"|(?:promo|discount|coupon|referral)\s+code"
    r"|affiliate"
    r")\b",
    re.IGNORECASE,
)

# Financial shilling: cashtags plus pump/FOMO language. Kept deliberately narrow
# so genuine crypto/markets *discussion* does not trip it. A bare multiplier like
# "10x" is NOT sufficient on its own (legitimate investors say "buying for 10x"):
# a post counts as shill only when a cashtag ($MOON) OR an unambiguous pump phrase
# is present.
_CASHTAG_RE = re.compile(r"\$[A-Z]{2,6}\b")
_SHILL_RE = re.compile(
    r"\b(?:"
    r"to\s+the\s+moon|going\s+to\s+(?:the\s+)?moon|moonshot|next\s+(?:gem|moon|100x|bitcoin)"
    r"|get\s+in\s+(?:early|now|before|on\s+this)"
    r"|insiders?\s+(?:are\s+)?(?:accumulating|buying)"
    r"|(?:huge|massive|guaranteed)\s+(?:gains|pump|returns)"
    r"|pump\s+(?:and\s+dump|it|this)|ape\s+in|aping\s+in"
    r"|not\s+financial\s+advice|nfa\b"
    r"|\d{2,4}\s*x\s+(?:gains|return|potential|incoming|soon|easy)"  # "100x gains"
    r")\b",
    re.IGNORECASE,
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

    n = len(texts)
    emoji_total = len(_EMOJI_RE.findall(corpus))
    emoji_per_post = emoji_total / n
    emoji_density = emoji_total / max(1, word_count)

    # Per-post booleans → rates. A "rate" is the fraction of posts exhibiting a
    # behavior, which is what makes the signal robust to post count.
    url_posts = 0
    burst_posts = 0
    bait_posts = 0
    promo_posts = 0
    shill_posts = 0
    for t in texts:
        low = t.lower()
        has_bait = any(p in low for p in _ENGAGEMENT_BAIT_PHRASES) or bool(_BAIT_RE.search(t))
        has_promo = bool(_SELF_PROMO_RE.search(t))
        if has_bait:
            bait_posts += 1
        if has_promo:
            promo_posts += 1
        if _REPEATED_EMOJI_RE.search(t):
            burst_posts += 1
        if _CASHTAG_RE.search(t) or _SHILL_RE.search(t):
            shill_posts += 1
        # A link counts toward the *spam-link* axis only when it is itself
        # promotional: a known shortener / affiliate domain, or any URL posted
        # alongside promo / bait framing in the same comment. A bare link to a
        # news site or public document (journalists, researchers, citing a
        # source) is NOT spam and must not move the score.
        if _URL_RE.search(t) and (
            _SHORTENER_RE.search(t) or has_bait or has_promo
        ):
            url_posts += 1

    url_rate = url_posts / n
    burst_rate = burst_posts / n
    bait_rate = bait_posts / n
    promo_rate = promo_posts / n
    shill_rate = shill_posts / n

    # Map each raw rate to an independent per-axis probability. Each is ~0 below
    # its organic-baseline threshold and rises sharply past it, so a clean
    # account (which sits below every threshold) contributes 0 on every axis.
    emoji_prob = _clip01((emoji_density - 0.06) * 3.0)   # > 6% emoji-per-word
    url_prob = _clip01((url_rate - 0.12) * 1.8)          # > 12% of posts linked
    burst_prob = _clip01((burst_rate - 0.10) * 3.0)      # > 10% emoji bursts
    bait_prob = _clip01((bait_rate - 0.12) * 2.2)        # > 12% of posts bait
    promo_prob = _clip01((promo_rate - 0.15) * 2.2)      # > 15% self-promo
    shill_prob = _clip01((shill_rate - 0.15) * 2.2)      # > 15% shill

    axis_probs = {
        "link": url_prob,
        "emoji": emoji_prob,
        "burst": burst_prob,
        "bait": bait_prob,
        "self_promo": promo_prob,
        "shill": shill_prob,
    }

    # Group correlated axes before combining. Link spam, engagement bait, and
    # self-promotion are typically the *same* promotional behavior expressed
    # three ways (an affiliate post links + "limited time!" + "link in bio");
    # emoji density and emoji bursts are the same emoji-spam behavior. Counting
    # each as independent would over-credit one account's single MO — the same
    # double-counting GAP-02 fixed in the main scorer. So we take the max WITHIN
    # each correlated group, then combine ACROSS the genuinely-independent groups
    # disjunctively (noisy-OR). Result: one promotional behavior reads ELEVATED;
    # it takes a second independent spam axis (e.g. promo + emoji-bombing) to
    # reach HIGH.
    # Cap each group's standalone contribution at the ELEVATED ceiling: one
    # promotional behavior — however intense — is "elevated", not "high". HIGH is
    # reserved for accounts that combine two independent spam axes (e.g. a promo
    # CTA *and* emoji-bombing), which the noisy-OR then escalates past 0.75.
    _GROUP_CEIL = 0.72
    promo_group = min(_GROUP_CEIL, max(url_prob, bait_prob, promo_prob))
    emoji_group = min(_GROUP_CEIL, max(emoji_prob, burst_prob))
    shill_group = min(_GROUP_CEIL, shill_prob)
    blended = _noisy_or((promo_group, emoji_group, shill_group))

    sub = {
        "emoji_per_post": emoji_per_post,
        "emoji_density": emoji_density,
        "url_inclusion_rate": url_rate,
        "emoji_burst_rate": burst_rate,
        "engagement_bait_rate": bait_rate,
        "self_promo_rate": promo_rate,
        "shill_rate": shill_rate,
        "promo_group": promo_group,
        "emoji_group": emoji_group,
    }

    evidence = _build_evidence(
        axis_probs,
        emoji_density=emoji_density,
        url_rate=url_rate,
        burst_rate=burst_rate,
        bait_rate=bait_rate,
        promo_rate=promo_rate,
        shill_rate=shill_rate,
    )

    # Strength-aware confidence. Volume still matters, but a *consistent,
    # unambiguous* pattern is a confident call even at a handful of posts:
    # 8/8 posts carrying affiliate links is not a low-confidence reading. We
    # only let strength raise confidence when a real spam signal is present, so
    # clean accounts keep modest (volume-based) confidence and don't over-assert
    # authenticity.
    volume_conf = min(1.0, n / 25.0)
    confidence = volume_conf
    if blended >= 0.5:
        # peak_rate = how consistently the worst behavior recurs across posts.
        peak_rate = max(url_rate, burst_rate, bait_rate, promo_rate, shill_rate)
        strength_conf = _clip01(0.45 + 0.55 * peak_rate)
        confidence = max(confidence, strength_conf)

    return SignalResult(
        name="engagement",
        probability=_clip01(blended),
        confidence=confidence,
        evidence=evidence,
        sub_signals=sub,
    )


def _noisy_or(probs) -> float:
    """Combine independent per-axis probabilities disjunctively.

    ``1 - ∏(1 - p_i)``: the probability that *at least one* axis is genuinely
    firing. A single axis at 1.0 yields ~1.0; all-zero yields 0.0.
    """
    product = 1.0
    for p in probs:
        product *= (1.0 - _clip01(p))
    return 1.0 - product


def _build_evidence(axis_probs: dict[str, float], **rates: float) -> list[str]:
    evidence: list[str] = []
    if axis_probs["emoji"] > 0.55:
        evidence.append(
            f"Emoji density of {rates['emoji_density']*100:.1f}% per word is "
            "unusually high; patterns consistent with promotional or spam-style "
            "accounts."
        )
    if axis_probs["link"] > 0.55:
        evidence.append(
            f"{rates['url_rate']*100:.0f}% of posts contain links — far above the "
            "organic baseline (most users rarely include URLs in comments)."
        )
    if axis_probs["burst"] > 0.55:
        evidence.append(
            f"Frequent emoji bursts (🚀🚀🚀 / 🔥🔥🔥-style) appearing in "
            f"{rates['burst_rate']*100:.0f}% of posts."
        )
    if axis_probs["bait"] > 0.55:
        evidence.append(
            f"Engagement-bait phrases (\"subscribe for more\", \"drop a like\", "
            f"\"follow me\", etc.) in {rates['bait_rate']*100:.0f}% of posts — "
            "algorithmic engagement-optimization patterns."
        )
    if axis_probs["self_promo"] > 0.55:
        evidence.append(
            f"Self-promotion / traffic redirection (\"link in bio\", \"on my "
            f"channel\", \"my course\") in {rates['promo_rate']*100:.0f}% of posts."
        )
    if axis_probs["shill"] > 0.55:
        evidence.append(
            f"Financial-shill patterns (cashtags + pump language like \"100x\", "
            f"\"get in before\") in {rates['shill_rate']*100:.0f}% of posts."
        )
    if not evidence:
        evidence.append("Content style does not exhibit notable spam/promo tells.")
    return evidence


def _clip01(x: float) -> float:
    return max(0.0, min(1.0, float(x)))
