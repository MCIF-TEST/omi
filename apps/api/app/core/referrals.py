"""Referral system primitives.

Owns the rules:
  * Each user gets a unique 8-char URL-safe ``referral_code`` at signup.
  * When ``referred_user`` signs up with a referrer's code AND is NOT
    flagged as a same-IP fraud signup, the referrer is granted +3 credits.
  * When the referred user later starts a paid subscription, the referrer
    is granted +5 more credits (idempotent via
    ``referral_subscription_bonus_paid``).
"""

from __future__ import annotations

import logging
import secrets

from sqlalchemy.orm import Session

from app.storage.models import User


logger = logging.getLogger("omi.referrals")


SIGNUP_BONUS_CREDITS = 3
SUBSCRIPTION_BONUS_CREDITS = 5


def generate_unique_code(session: Session) -> str:
    """Return a URL-safe code that is not yet present in the users table.

    Tries 5 times before giving up; collision probability at 8 chars of
    ``token_urlsafe`` is astronomically low so this is purely defensive.
    """
    for _ in range(5):
        code = secrets.token_urlsafe(6)[:8]
        existing = session.query(User).filter(User.referral_code == code).first()
        if existing is None:
            return code
    raise RuntimeError("Could not generate a unique referral code after 5 attempts.")


def resolve_referrer(session: Session, code: str | None) -> User | None:
    """Look up the user who owns ``code``, returning None for unknown/empty."""
    if not code:
        return None
    code = code.strip()
    if not code:
        return None
    return session.query(User).filter(User.referral_code == code).first()


def grant_signup_bonus(session: Session, referrer: User) -> None:
    """Award the +3 signup bonus to ``referrer``.

    Caller is responsible for deciding whether the referee qualifies
    (e.g. not an IP-suppressed signup). This function just does the math.
    """
    referrer.credits_remaining = (referrer.credits_remaining or 0) + SIGNUP_BONUS_CREDITS
    referrer.referral_credits_earned = (referrer.referral_credits_earned or 0) + SIGNUP_BONUS_CREDITS
    logger.info(
        "Referral signup bonus: +%d credits to user_id=%d",
        SIGNUP_BONUS_CREDITS, referrer.id,
    )


def grant_subscription_bonus_if_due(session: Session, referred_user: User) -> bool:
    """Award the +5 subscription bonus to the referrer of ``referred_user``
    iff it hasn't already been paid for this referral.

    Returns True when a bonus was actually granted (for logging/tests).
    """
    if not referred_user.referred_by_user_id:
        return False
    if referred_user.referral_subscription_bonus_paid:
        return False

    referrer = session.get(User, referred_user.referred_by_user_id)
    if referrer is None:
        # Referrer account was deleted — flag the bonus paid so we don't
        # keep retrying on every webhook redelivery.
        referred_user.referral_subscription_bonus_paid = 1
        return False

    referrer.credits_remaining = (referrer.credits_remaining or 0) + SUBSCRIPTION_BONUS_CREDITS
    referrer.referral_credits_earned = (referrer.referral_credits_earned or 0) + SUBSCRIPTION_BONUS_CREDITS
    referred_user.referral_subscription_bonus_paid = 1
    logger.info(
        "Referral subscription bonus: +%d credits to user_id=%d (referred user_id=%d converted)",
        SUBSCRIPTION_BONUS_CREDITS, referrer.id, referred_user.id,
    )
    return True
