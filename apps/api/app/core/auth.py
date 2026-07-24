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

import math
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


# bcrypt only considers the first 72 bytes of a password, and bcrypt>=4
# *raises* on anything longer instead of silently truncating. SignupRequest
# allows passwords up to 200 chars, so without this a long passphrase would
# 500 the signup endpoint. Truncate to 72 bytes in BOTH hash and verify so
# the behavior is consistent (a long password set at signup still logs in)
# and backward-compatible (passwords <= 72 bytes are untouched).
_BCRYPT_MAX_BYTES = 72


def _bcrypt_bytes(plain: str) -> bytes:
    return (plain or "").encode("utf-8")[:_BCRYPT_MAX_BYTES]


def hash_password(plain: str) -> str:
    if bcrypt is None:
        raise RuntimeError("bcrypt is not installed; run pip install -e .[auth]")
    return bcrypt.hashpw(_bcrypt_bytes(plain), bcrypt.gensalt(rounds=12)).decode()


def verify_password(plain: str, hashed: str) -> bool:
    if bcrypt is None:
        return False
    try:
        return bcrypt.checkpw(_bcrypt_bytes(plain), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


# ---------------------------------------------------------------------------
# Email validation — minimal, format-only
# ---------------------------------------------------------------------------

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def is_valid_email(email: str) -> bool:
    return bool(email and _EMAIL_RE.match(email.strip().lower()))


# Placeholder identity for a Clerk account we could verify (valid signed token) but whose email we
# can't read yet (development session tokens carry no email, and the Backend API lookup may be
# unconfigured or briefly unreachable). Keyed on the Clerk user id so it's stable and unique; the real
# email is backfilled on a later request. This guarantees a valid sign-in always resolves to a user,
# which is what prevents the sign-in ↔ app redirect loop.
_PLACEHOLDER_EMAIL_DOMAIN = "placeholder.omisphere.local"


def _placeholder_email(clerk_uid: str) -> str:
    return f"clerk_{clerk_uid.lower()}@{_PLACEHOLDER_EMAIL_DOMAIN}"


def _is_placeholder_email(email: str | None) -> bool:
    return bool(email) and email.strip().lower().endswith("@" + _PLACEHOLDER_EMAIL_DOMAIN)


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
    # A response that hands out a session cookie must NEVER be cached: if an edge/CDN/proxy caches it,
    # one user's Set-Cookie is replayed to everyone who hits the cache — they all get logged into that
    # one account (the "auto-logged into someone else's admin" class of bug). Force it private+no-store.
    response.headers["Cache-Control"] = "private, no-store, max-age=0"
    response.headers["Vary"] = "Cookie"


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

def _resolve_clerk_user(request: Request, settings: Settings) -> CurrentUser | None:
    """Resolve the caller from a Clerk session JWT (``Authorization: Bearer <token>`` OR the Clerk
    ``__session`` cookie).

    Verifies the token against Clerk's JWKS, then maps the Clerk user to the LOCAL account: by
    ``clerk_user_id`` if already linked, otherwise by email (linking an existing account so its
    credits/subscription/investigations carry over), otherwise creating a fresh local account. The
    local row remains the source of truth for credits + data; Clerk is only the identity. Returns None
    when Clerk is disabled, no token is present, or the token is invalid — the caller then falls back
    to the legacy cookie session.

    Token source (either works, so a request authenticates whether or not the frontend managed to
    attach the Bearer header): the ``Authorization: Bearer`` header first, then the ``__session``
    cookie Clerk sets on the app's own domain (browsers send it automatically on same-origin requests,
    so a client fetch fired before ``window.Clerk.session`` is ready still authenticates)."""
    from app.core.clerk_auth import (
        clerk_enabled, email_from_claims, fetch_user_email, verify_session_token,
    )

    if not clerk_enabled():
        return None
    header = request.headers.get("authorization") or request.headers.get("Authorization") or ""
    token = header[7:].strip() if header.lower().startswith("bearer ") else ""
    if not token:
        # Fall back to the Clerk session cookie (__session, or a suffixed __session_<hash> on a dev
        # instance with suffixed cookies). Reaches FastAPI via the web app's /api rewrite, which
        # forwards the browser's cookies.
        token = (request.cookies.get("__session") or "").strip()
        if not token:
            for name, value in request.cookies.items():
                if name.startswith("__session_") and value:
                    token = value.strip()
                    break
    if not token:
        return None
    claims = verify_session_token(token)
    if not claims:
        return None
    clerk_uid = claims.get("sub")
    if not isinstance(clerk_uid, str) or not clerk_uid:
        return None

    admin_emails = {
        e.strip().lower() for e in (settings.super_admin_emails or "").split(",") if e.strip()
    }

    with get_session() as session:
        u = session.query(User).filter(User.clerk_user_id == clerk_uid).first()

        # Fast path: a known, fully-provisioned account. No email lookup, no network call — this is the
        # request-time hot path (every page/API call resolves the user), so it must stay cheap.
        if u is not None and not _is_placeholder_email(u.email):
            u.last_login_at = datetime.utcnow()
            session.flush()
            return CurrentUser.from_row(u)

        # We need the email only to finish provisioning a NEW account or to upgrade a placeholder one.
        # A Clerk development session token carries no email, so the claim is usually empty and we ask
        # the Clerk Backend API (cached, incl. negative results, so a failing call can't slow the app).
        email = email_from_claims(claims) or fetch_user_email(clerk_uid)
        email = email.strip().lower() if isinstance(email, str) and is_valid_email(email) else None
        is_super = bool(email) and email in admin_emails

        # Existing PLACEHOLDER account: upgrade it to the real email once we can get one (and grant
        # admin if it now matches). Never dead-ends — the account already works either way.
        if u is not None:
            if email and email != u.email and (
                session.query(User).filter(User.email == email, User.id != u.id).first() is None
            ):
                u.email = email
                if is_super:
                    u.is_admin = 1
            u.last_login_at = datetime.utcnow()
            session.flush()
            return CurrentUser.from_row(u)

        # No local row for this Clerk id yet. If we have a real email, link an existing account by it
        # (carry over its credits/data), else fall through to create.
        if email:
            existing = session.query(User).filter(User.email == email).first()
            if existing is not None:
                if not existing.clerk_user_id:
                    existing.clerk_user_id = clerk_uid
                existing.last_login_at = datetime.utcnow()
                session.flush()
                return CurrentUser.from_row(existing)

        # Create a fresh account. Use the real email when we have one; otherwise a STABLE placeholder
        # keyed on the Clerk id so a valid sign-in ALWAYS resolves to a user (no redirect loop). The
        # real email is backfilled on a later request via the placeholder-upgrade path above.
        acct_email = email or _placeholder_email(clerk_uid)
        u = User(
            email=acct_email,
            password_hash="",  # Clerk-managed identity — no local password
            clerk_user_id=clerk_uid,
            credits_remaining=999999 if is_super else settings.free_trial_credits,
            is_admin=1 if is_super else 0,
            last_login_at=datetime.utcnow(),
        )
        session.add(u)
        try:
            session.flush()
        except Exception:  # noqa: BLE001 — a race created it; re-read
            session.rollback()
            u = session.query(User).filter(User.clerk_user_id == clerk_uid).first() \
                or session.query(User).filter(User.email == acct_email).first()
            if u is None:
                return None
        return CurrentUser.from_row(u)


def get_optional_user(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> CurrentUser | None:
    """Best-effort user resolution. Prefers a Clerk session token (the new auth), then falls back to
    the legacy signed cookie. Returns None when neither is present/valid."""
    clerk_user = _resolve_clerk_user(request, settings)
    if clerk_user is not None:
        return clerk_user
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


def compute_scan_credits(
    platform: str,
    max_commenters: int,
    settings: Settings | None = None,
) -> int:
    """Credits for one batch scan.

    Formula: ceil(max_commenters / scan_batch_unit) × credits_per_batch[platform].
    Minimum 1. Unknown platforms fall back to the YouTube rate.
    """
    settings = settings or get_settings()
    batches = math.ceil(max_commenters / settings.scan_batch_unit) if max_commenters > 0 else 1
    per_batch = (
        settings.credits_per_batch_twitter
        if platform == "twitter"
        else settings.credits_per_batch_youtube
    )
    return max(1, batches * per_batch)


def generate_secret() -> str:
    """For the deploy guide — print a fresh session_secret."""
    return secrets.token_urlsafe(64)


_ = os  # silence unused-import lints if any
