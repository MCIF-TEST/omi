"""Profile authenticity detector.

Looks at the static-ish attributes of an account: handle, age, follower
ratios, bio. These are weaker signals than behavioral ones, but they're cheap
and they catch the most obviously-fake long tail.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from datetime import datetime, timezone

from app.schemas import Profile, SignalResult


_HANDLE_NUMBER_TAIL = re.compile(r"\d{4,}$")
_WORD_RE = re.compile(r"\w+")


def analyze_profile(profile: Profile, post_count: int | None = None) -> SignalResult:
    sub: dict[str, float] = {}
    evidence: list[str] = []
    contributions: list[float] = []

    # ---- Handle entropy / numeric tail ----
    handle_prob, handle_entropy = _handle_signal(profile.handle)
    sub["handle_entropy"] = handle_entropy
    contributions.append(handle_prob)
    if handle_prob > 0.6:
        evidence.append(
            f"Handle '@{profile.handle}' looks algorithmically generated "
            f"(entropy={handle_entropy:.2f}, suspicious numeric suffix or random characters)."
        )

    # ---- Account age vs activity ----
    age_prob, posts_per_day = _age_vs_activity_signal(profile.created_at, post_count)
    sub["posts_per_day"] = posts_per_day
    if age_prob is not None:
        contributions.append(age_prob)
        if age_prob > 0.6:
            evidence.append(
                f"Posting rate of {posts_per_day:.1f}/day is high for an account this young."
            )

    # ---- Follower/following ratio ----
    ratio_prob, ratio = _follower_ratio_signal(profile.follower_count, profile.following_count)
    sub["follower_following_ratio"] = ratio
    if ratio_prob is not None:
        contributions.append(ratio_prob)
        if ratio_prob > 0.6:
            evidence.append(
                f"Follower / following ratio of {ratio:.2f} is an outlier "
                "(very high or very low for a typical account)."
            )

    # ---- Bio quality ----
    bio_prob, bio_score = _bio_quality_signal(profile.bio)
    sub["bio_quality"] = bio_score
    if bio_prob is not None:
        contributions.append(bio_prob)
        if bio_prob > 0.6:
            evidence.append(
                "Bio is empty, generic, or contains low-information / suspicious link patterns."
            )

    if not contributions:
        return SignalResult(
            name="profile",
            probability=0.5,
            confidence=0.0,
            evidence=["Insufficient profile metadata to evaluate authenticity."],
        )

    prob = sum(contributions) / len(contributions)
    # Verified accounts get a small dampener — not a hall pass, but a prior shift.
    if profile.verified:
        prob *= 0.7
        evidence.append("Account is marked verified by the platform.")

    if not evidence:
        evidence.append("Profile metadata does not show notable authenticity concerns.")

    # Confidence proportional to how many sub-signals we could compute.
    confidence = min(1.0, len(contributions) / 4.0)

    return SignalResult(
        name="profile",
        probability=_clip01(prob),
        confidence=confidence,
        evidence=evidence,
        sub_signals=sub,
    )


# ---------------------------------------------------------------------------
# Sub-signals
# ---------------------------------------------------------------------------


def _handle_signal(handle: str) -> tuple[float, float]:
    handle = handle.lstrip("@")
    if not handle:
        return 0.5, 0.0

    entropy = _shannon_entropy(handle.lower())
    base_prob = 0.0

    # High-entropy short string with a long digit suffix is the classic
    # auto-generated handle pattern.
    if _HANDLE_NUMBER_TAIL.search(handle):
        base_prob += 0.45
    if entropy > 3.5:
        base_prob += 0.35
    elif entropy > 3.2:
        base_prob += 0.2

    # All-lowercase-no-vowel pattern (jkrtmqx) — random-string giveaway.
    letters = [c for c in handle.lower() if c.isalpha()]
    if letters:
        vowel_ratio = sum(1 for c in letters if c in "aeiou") / len(letters)
        if vowel_ratio < 0.15:
            base_prob += 0.2

    return min(1.0, base_prob), entropy


def _age_vs_activity_signal(
    created_at: datetime | None, post_count: int | None
) -> tuple[float | None, float]:
    if created_at is None or post_count is None:
        return None, 0.0
    created = created_at if created_at.tzinfo else created_at.replace(tzinfo=timezone.utc)
    age_days = max(1.0, (datetime.now(timezone.utc) - created).total_seconds() / 86400.0)
    per_day = post_count / age_days

    # < 5/day = normal; > 30/day on a new account is the warning zone.
    # Combine rate with age: same rate from a 5-year-old account is far less alarming.
    if age_days > 365:
        # Mature accounts: only extreme rates count.
        prob = 1.0 / (1.0 + math.exp(-(per_day - 80) / 20))
    elif age_days > 90:
        prob = 1.0 / (1.0 + math.exp(-(per_day - 40) / 10))
    else:
        # < 3 months old.
        prob = 1.0 / (1.0 + math.exp(-(per_day - 15) / 6))

    return prob, per_day


def _follower_ratio_signal(
    followers: int | None, following: int | None
) -> tuple[float | None, float]:
    if followers is None or following is None:
        return None, 0.0
    if following == 0 and followers == 0:
        # Brand-new ghost account.
        return 0.55, 0.0
    ratio = followers / max(1, following)

    # Sweet spot for organic users is roughly 0.3 .. 5.0.
    # Far outside that range is mildly suspicious unless followers > ~50k (influencer territory).
    if followers > 50_000:
        # Famous accounts naturally skew. Don't penalize.
        return 0.3, ratio

    log_ratio = math.log10(max(1e-3, ratio))
    # log_ratio 0 → 0.3; log_ratio ±2 → ~0.75
    prob = 0.3 + 0.45 * min(1.0, abs(log_ratio) / 2.0)
    return prob, ratio


def _bio_quality_signal(bio: str | None) -> tuple[float | None, float]:
    if bio is None:
        return 0.55, 0.0  # missing bio is mildly suspicious
    stripped = bio.strip()
    if not stripped:
        return 0.55, 0.0

    words = _WORD_RE.findall(stripped)
    if len(words) < 3:
        return 0.55, float(len(words))

    # Suspicious markers: lots of crypto/airdrop emoji, shortlinks, mass hashtags.
    crypto_markers = sum(1 for w in words if w.lower() in {"airdrop", "nft", "crypto", "presale"})
    link_count = stripped.lower().count("bit.ly") + stripped.lower().count("t.me/")
    hashtag_count = stripped.count("#")

    bad = crypto_markers * 1.5 + link_count * 2 + max(0, hashtag_count - 3) * 0.5
    # Map bad-score to probability.
    prob = 1.0 / (1.0 + math.exp(-(bad - 2) / 1.5))
    return max(0.25, prob), float(len(words))


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------


def _shannon_entropy(s: str) -> float:
    if not s:
        return 0.0
    counts = Counter(s)
    total = len(s)
    return -sum((c / total) * math.log2(c / total) for c in counts.values())


def _clip01(x: float) -> float:
    return max(0.0, min(1.0, x))
