"""Community-anchor signal (GAP-07 false-positive reduction).

Every other detector answers "does this account *behave* synthetically?". This
one answers the orthogonal question "is this account *embedded in a real
community*?" — and it can only ever pull a verdict **down**.

Rationale: synthetic / coordinated / spam accounts are empirically young and
thinly-connected. They get caught and culled, and an audience of real followers
cannot be conjured on demand. So a large, established follower base — sustained
over years without the account being banned — is strong Bayesian evidence
*against* inauthenticity. An established brand account, a long-running automated
news/weather feed, or an AI-assisted human writer with a real audience will trip
the behavioral detectors (impersonal voice, regular cadence, templated phrasing)
exactly the way a bot does; community anchoring is what keeps those legitimate
accounts from being over-flagged.

Design constraints that keep this honest (it must not whitewash real threats):

* **Downward only.** The signal's probability is always at or below the prior,
  so in the log-odds aggregator it can subtract suspicion but never add it.
* **Age-gated.** Anchoring requires genuine *maturity*, not just a follower
  count — bought followers on a months-old account don't qualify. The age ramp
  starts at 1 year and saturates at 4. This deliberately protects younger
  high-follower accounts (which are exactly where bought-audience operations
  live) from being dampened.
* **Bounded.** Confidence is capped so the dampener can pull roughly one tier,
  not collapse a HIGH straight to LOW. Anchoring is meaningful evidence, not an
  override — a sufficiently blatant multi-axis bot still outweighs it.
* **Silent when weak.** Below a minimum anchor it returns zero confidence and
  contributes nothing, so ordinary accounts are unaffected.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone

from app.schemas import Profile, SignalResult


# Follower count where anchoring begins (below this, an account is not yet a
# "community") and where it saturates (a genuinely large audience).
_FOLLOWERS_LO = 300
_FOLLOWERS_HI = 50_000

# Account age (days) where maturity anchoring begins (1 year) and saturates
# (4 years). Starting at a year is deliberate: it keeps the dampener away from
# the young high-follower accounts where bought-audience operations concentrate.
_AGE_LO_DAYS = 365
_AGE_HI_DAYS = 1460

# Minimum combined anchor before the detector fires at all. Below it the signal
# is silent (zero confidence).
_MIN_ANCHOR = 0.30

# Confidence envelope. Capped well below 1.0 so the dampener is bounded — it can
# pull about one tier, never a full HIGH→LOW collapse.
_CONF_BASE = 0.30
_CONF_SPAN = 0.40  # max confidence = 0.70 at full anchor

# Verification is a strong independent anchor: platforms gate it behind identity
# or notability checks that synthetic accounts rarely clear.
_VERIFIED_ANCHOR_FLOOR = 0.60


def analyze_community(profile: Profile, post_count: int | None = None) -> SignalResult:
    """Estimate how strongly an account is anchored in a real community.

    Returns a *downward-only* SignalResult: probability ≤ prior, with confidence
    proportional to anchor strength. Silent (confidence 0) for accounts that are
    not clearly established.
    """
    followers = profile.follower_count
    following = profile.following_count
    verified = bool(profile.verified)

    age_days = _age_days(profile.created_at)

    # Need *some* basis: either a follower count or verification. Verified-only
    # (counts hidden) still anchors via the floor below.
    if followers is None and not verified:
        return _neutral("No follower/verification data to assess community anchoring.")

    follower_anchor = _log_ramp(followers or 0, _FOLLOWERS_LO, _FOLLOWERS_HI)
    age_anchor = _linear_ramp(age_days, _AGE_LO_DAYS, _AGE_HI_DAYS) if age_days is not None else 0.0

    # Both maturity AND audience are required — multiply, don't average. A huge
    # but brand-new account (bought followers) and an old but audience-less ghost
    # account both score ~0.
    anchor = follower_anchor * age_anchor

    # Mass-follow penalty: the classic bot/farm shape is "follows thousands, is
    # followed by few". When we can see the ratio and it's lopsided that way,
    # discount the anchor — a real community is reciprocal-ish.
    ratio_note = ""
    if following and followers is not None and following > 0:
        ratio = followers / following
        if ratio < 0.1:
            anchor *= 0.4
            ratio_note = f" (follows {following:,} but only {followers:,} follow back — discounted)"
        elif ratio < 0.5:
            anchor *= 0.75

    # Verification is its own anchor floor, independent of raw counts.
    if verified:
        anchor = max(anchor, _VERIFIED_ANCHOR_FLOOR)

    if anchor < _MIN_ANCHOR:
        return _neutral(
            "Account is not clearly community-anchored "
            f"(followers={_fmt(followers)}, age={_fmt_age(age_days)})."
        )

    strength = (anchor - _MIN_ANCHOR) / (1.0 - _MIN_ANCHOR)
    probability = 0.10 - 0.06 * strength          # 0.10 → 0.04, always ≤ prior
    confidence = _CONF_BASE + _CONF_SPAN * strength  # 0.30 → 0.70

    bits: list[str] = []
    if verified:
        bits.append("platform-verified")
    if followers is not None:
        bits.append(f"{followers:,} followers")
    if age_days is not None:
        bits.append(f"~{age_days // 365}y old" if age_days >= 365 else f"{age_days}d old")
    evidence = (
        "Account is embedded in an established community ("
        + ", ".join(bits)
        + ")"
        + ratio_note
        + " — real audiences are hard to fabricate, which lowers the likelihood "
        "of synthetic/coordinated operation. (Reduces suspicion; never raises it.)"
    )

    return SignalResult(
        name="community",
        probability=probability,
        confidence=confidence,
        evidence=[evidence],
        sub_signals={
            "anchor": round(anchor, 3),
            "follower_anchor": round(follower_anchor, 3),
            "age_anchor": round(age_anchor, 3),
        },
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _neutral(reason: str) -> SignalResult:
    return SignalResult(name="community", probability=0.5, confidence=0.0, evidence=[reason])


def _age_days(created_at: datetime | None) -> int | None:
    if created_at is None:
        return None
    created = created_at if created_at.tzinfo else created_at.replace(tzinfo=timezone.utc)
    return max(0, (datetime.now(timezone.utc) - created).days)


def _log_ramp(value: float, lo: float, hi: float) -> float:
    """0 at/below ``lo``, 1 at/above ``hi``, log-scaled in between."""
    if value <= lo:
        return 0.0
    if value >= hi:
        return 1.0
    return math.log10(value / lo) / math.log10(hi / lo)


def _linear_ramp(value: float, lo: float, hi: float) -> float:
    if value <= lo:
        return 0.0
    if value >= hi:
        return 1.0
    return (value - lo) / (hi - lo)


def _fmt(n: int | None) -> str:
    return "unknown" if n is None else f"{n:,}"


def _fmt_age(days: int | None) -> str:
    if days is None:
        return "unknown"
    if days >= 365:
        return f"~{days // 365}y"
    return f"{days}d"
