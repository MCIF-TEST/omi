"""Authentication, session cookies, and the credit-gating dependency.

Session model: signed-cookie sessions via ``itsdangerous``. The cookie
contains ``{"uid": <user_id>, "iat": <timestamp>}`` signed with the
configured ``session_secret``. No server-side session table — stateless,
cheap, and simple.

Passwords are hashed with bcrypt. Free trial credits are granted at
signup; afterwards credits come from active subscriptions.

The auth layer can be turned OFF entirely by setting
``OMI_REQUIRE_AUTH=false`` — useful for solo local installs where the
whole point of OMI is unrestricted personal use. In that mode every
endpoint passes the optional auth dependency and credit checks are a
no-op.
"""

from __future__ import annotations

import os
import re
import secrets
from dataclasses import dataclass
from datetime import datetime

from fastapi import Depends, HTTPException, Request, Response, status
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.core.config import Settings, get_settings
from app.storage.db import get_session
from app.storage.models import User


# ---------------------------------------------------------------------------
# Password hashing — bcrypt direct (no passlib dep)
# ---------------------------------------------------------------------------

try:
    import bcrypt  # type: ignore
except ImportError:  # pragma: no cover - declared as a dep
    bcrypt = None  # type: ignore


def hash_password(plain: str) -> str:
    if bcrypt is None:
        raise RuntimeError("bcrypt is not installed; run pip install -e .[auth]")
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode()


def verify_password(plain: str, hashed: str) -> bool:
    if bcrypt is None:
        return False
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


# ---------------------------------------------------------------------------
# Email validation — minimal, format-only
# ---------------------------------------------------------------------------

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def is_valid_email(email: str) -> bool:
    return bool(email and _EMAIL_RE.match(email.strip().lower()))


# ---------------------------------------------------------------------------
# Sessions — signed cookies
# ---------------------------------------------------------------------------

SESSION_COOKIE_NAME = "omi_session"
SESSION_MAX_AGE_SECONDS = 60 * 60 * 24 * 30  # 30 days


def _serializer(settings: Settings) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(settings.session_secret, salt="omi-session-v1")


def issue_session(response: Response, user: User, settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    token = _serializer(settings).dumps({"uid": user.id})
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        max_age=SESSION_MAX_AGE_SECONDS,
        httponly=True,
        samesite="lax",
        secure=settings.public_base_url.startswith("https://"),
    )


def clear_session(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE_NAME)


def _decode_session(token: str | None, settings: Settings) -> int | None:
    if not token:
        return None
    try:
        data = _serializer(settings).loads(token, max_age=SESSION_MAX_AGE_SECONDS)
    except (BadSignature, SignatureExpired):
        return None
    if not isinstance(data, dict):
        return None
    uid = data.get("uid")
    return int(uid) if isinstance(uid, int) else None


# ---------------------------------------------------------------------------
# Public-shape user (no password hash)
# ---------------------------------------------------------------------------

@dataclass
class CurrentUser:
    id: int
    email: str
    credits_remaining: int
    subscription_status: str | None
    subscription_renews_at: datetime | None
    is_admin: bool
    referral_code: str | None = None
    referral_credits_earned: int = 0

    @classmethod
    def from_row(cls, u: User) -> "CurrentUser":
        return cls(
            id=u.id,
            email=u.email,
            credits_remaining=u.credits_remaining,
            subscription_status=u.subscription_status,
            subscription_renews_at=u.subscription_renews_at,
            is_admin=bool(u.is_admin),
            referral_code=u.referral_code,
            referral_credits_earned=u.referral_credits_earned or 0,
        )


# ---------------------------------------------------------------------------
# FastAPI dependencies
# ---------------------------------------------------------------------------

def get_optional_user(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> CurrentUser | None:
    """Best-effort user resolution. Returns None when no/invalid session."""
    token = request.cookies.get(SESSION_COOKIE_NAME)
    uid = _decode_session(token, settings)
    if uid is None:
        return None
    with get_session() as session:
        u = session.get(User, uid)
        if u is None:
            return None
        return CurrentUser.from_row(u)


def require_user(
    current: CurrentUser | None = Depends(get_optional_user),
    settings: Settings = Depends(get_settings),
) -> CurrentUser:
    """Strict auth: 401 if no logged-in user. Bypassed when require_auth=False
    in local mode — returns a synthetic local user with unlimited credits."""
    if not settings.require_auth:
        return CurrentUser(
            id=0,
            email="local@omi.local",
            credits_remaining=999999,
            subscription_status="local",
            subscription_renews_at=None,
            is_admin=True,
        )
    if current is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Please log in to use OMI.",
        )
    return current


# ---------------------------------------------------------------------------
# Credit-gating
# ---------------------------------------------------------------------------

def consume_credits(
    user_id: int,
    credits: int,
    *,
    platform: str,
    scan_type: str,
    target_input: str | None,
    settings: Settings | None = None,
) -> int:
    """Atomically decrement the user's credits and write a ScanLog row.

    Returns the user's remaining credits after the deduction. Raises
    HTTPException(402) if the user doesn't have enough credits.

    No-op when require_auth is disabled (local mode).
    """
    settings = settings or get_settings()
    if not settings.require_auth:
        return 999999

    from app.storage.models import ScanLog

    with get_session() as session:
        u = session.get(User, user_id)
        if u is None:
            raise HTTPException(status_code=401, detail="Session invalid.")
        # Super-admins scan freely — log the call but don't decrement.
        if u.is_admin:
            from app.storage.models import ScanLog
            session.add(ScanLog(
                user_id=u.id,
                platform=platform,
                scan_type=scan_type,
                credits_cost=0,
                target_input=target_input,
                success=1,
            ))
            return u.credits_remaining
        if u.credits_remaining < credits:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail=(
                    f"Not enough credits ({u.credits_remaining} remaining, "
                    f"{credits} required). Subscribe or buy more to continue."
                ),
            )
        u.credits_remaining -= credits
        session.add(ScanLog(
            user_id=u.id,
            platform=platform,
            scan_type=scan_type,
            credits_cost=credits,
            target_input=target_input,
            success=1,
        ))
        return u.credits_remaining


def refund_credits(
    user_id: int,
    credits: int,
    *,
    reason: str,
    settings: Settings | None = None,
) -> int:
    """Atomically re-credit a user after a scan failed for a reason that
    isn't their fault (YouTube quota, gateway timeout, internal 5xx).

    Marks the most recent matching ScanLog row as failed so the audit
    trail reflects the refund. Returns the user's new balance.

    No-op when require_auth is disabled, when the user is an admin (they
    were never charged), or when ``credits`` is 0.
    """
    settings = settings or get_settings()
    if not settings.require_auth or credits <= 0:
        return 999999

    from app.storage.models import ScanLog

    with get_session() as session:
        u = session.get(User, user_id)
        if u is None:
            return 0
        if u.is_admin:
            return u.credits_remaining
        u.credits_remaining += credits
        # Flip the most recent successful ScanLog row to failed so the
        # audit history matches the refund. Best-effort; if there is no
        # matching row (clock skew, manual DB edit, etc.) the refund still
        # goes through.
        recent = (
            session.query(ScanLog)
            .filter(ScanLog.user_id == u.id, ScanLog.success == 1)
            .order_by(ScanLog.id.desc())
            .first()
        )
        if recent is not None and recent.credits_cost == credits:
            recent.success = 0
            recent.target_input = (recent.target_input or "")[:480] + f" [REFUND:{reason[:20]}]"
        return u.credits_remaining


def generate_secret() -> str:
    """For the deploy guide — print a fresh session_secret."""
    return secrets.token_urlsafe(64)


_ = os  # silence unused-import lints if any
