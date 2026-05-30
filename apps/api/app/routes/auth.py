"""Auth routes: signup, login, logout, me."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError

from app.core.auth import (
    CurrentUser,
    clear_session,
    get_optional_user,
    hash_password,
    is_valid_email,
    issue_session,
    verify_password,
)
from app.core.config import Settings, get_settings
from app.core.ip import client_ip, hash_ip
from app.core.referrals import (
    generate_unique_code,
    grant_signup_bonus,
    resolve_referrer,
)
from app.storage.db import get_session
from app.storage.models import User


router = APIRouter(prefix="/v1/auth", tags=["auth"])


class SignupRequest(BaseModel):
    email: str = Field(min_length=4, max_length=255)
    password: str = Field(min_length=8, max_length=200)
    # Optional referral code captured from the ?ref= query param on /signup.
    # Invalid codes are silently ignored (we don't want to block real signups
    # over a typo'd link).
    referral_code: str | None = Field(default=None, max_length=16)


class LoginRequest(BaseModel):
    email: str
    password: str


class UserOut(BaseModel):
    id: int
    email: str
    credits_remaining: int
    subscription_status: str | None
    subscription_renews_at: datetime | None
    is_admin: bool
    referral_code: str | None = None
    referral_credits_earned: int = 0


@router.post("/signup", response_model=UserOut)
def signup(req: SignupRequest, request: Request, response: Response, settings: Settings = Depends(get_settings)) -> UserOut:
    # Rate-limit account creation per IP (5/hour) to slow farming.
    from app.core.rate_limit import SIGNUP_LIMITER
    ip = client_ip(request)
    if not SIGNUP_LIMITER.hit(ip):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many signups from this address. Try again later.",
        )
    email = req.email.strip().lower()
    if not is_valid_email(email):
        raise HTTPException(status_code=400, detail="Please use a valid email address.")
    if len(req.password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters.")

    ip_hash = hash_ip(ip)

    with get_session() as session:
        existing = session.query(User).filter(User.email == email).first()
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An account with that email already exists. Try logging in.",
            )
        admin_emails = {
            e.strip().lower()
            for e in (settings.super_admin_emails or "").split(",")
            if e.strip()
        }
        is_super_admin = email in admin_emails

        # ---- Free-credit fraud check ----
        # If another account already exists from this IP and received the
        # free trial credits, suppress this signup's free credits. Real
        # signups still work; this just denies the trial-stacking trick.
        # Super admins are exempt — they're seeded by env config, not abuse.
        ip_already_credited = False
        if not is_super_admin and settings.free_trial_credits > 0:
            ip_already_credited = (
                session.query(User.id)
                .filter(User.signup_ip_hash == ip_hash)
                .first()
                is not None
            )

        if is_super_admin:
            initial_credits = 999999
        elif ip_already_credited:
            initial_credits = 0
        else:
            initial_credits = settings.free_trial_credits

        # ---- Resolve the referrer (optional) ----
        referrer = resolve_referrer(session, req.referral_code)

        user = User(
            email=email,
            password_hash=hash_password(req.password),
            credits_remaining=initial_credits,
            last_login_at=datetime.now(timezone.utc),
            is_admin=1 if is_super_admin else 0,
            signup_ip_hash=ip_hash,
            referral_code=generate_unique_code(session),
            referred_by_user_id=referrer.id if referrer else None,
        )
        session.add(user)
        try:
            session.flush()  # populate user.id; surfaces unique violations
        except IntegrityError:
            # Two signups for the same email raced past the existence check
            # above (or some other unique constraint tripped). Roll the failed
            # INSERT back and return the same clean 409 the check would have.
            session.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An account with that email already exists. Try logging in.",
            )

        # Grant the referrer's +3 signup bonus only when the referee is a
        # "real" signup. Same-IP suppressed signups don't qualify, which
        # closes the self-referral-on-same-IP scam vector.
        if referrer is not None and not ip_already_credited:
            grant_signup_bonus(session, referrer)

        issue_session(response, user, settings)
        return UserOut(
            id=user.id,
            email=user.email,
            credits_remaining=user.credits_remaining,
            subscription_status=user.subscription_status,
            subscription_renews_at=user.subscription_renews_at,
            is_admin=bool(user.is_admin),
            referral_code=user.referral_code,
            referral_credits_earned=user.referral_credits_earned,
        )


@router.post("/login", response_model=UserOut)
def login(req: LoginRequest, request: Request, response: Response, settings: Settings = Depends(get_settings)) -> UserOut:
    # Rate-limit login per IP (10/min) to slow brute-force.
    from app.core.rate_limit import LOGIN_LIMITER
    ip = client_ip(request)
    if not LOGIN_LIMITER.hit(ip):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts. Try again in a minute.",
        )
    email = (req.email or "").strip().lower()
    with get_session() as session:
        user = session.query(User).filter(User.email == email).first()
        if user is None or not verify_password(req.password, user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Email or password is incorrect.",
            )
        user.last_login_at = datetime.now(timezone.utc)
        issue_session(response, user, settings)
        return UserOut(
            id=user.id,
            email=user.email,
            credits_remaining=user.credits_remaining,
            subscription_status=user.subscription_status,
            subscription_renews_at=user.subscription_renews_at,
            is_admin=bool(user.is_admin),
            referral_code=user.referral_code,
            referral_credits_earned=user.referral_credits_earned,
        )


@router.post("/logout")
def logout(response: Response) -> dict:
    clear_session(response)
    return {"ok": True}


# ---------------------------------------------------------------------------
# Password reset — request a token by email, then set a new password.
# ---------------------------------------------------------------------------

# Reset tokens live for one hour. Long enough to walk away from the inbox,
# short enough that a leaked link is mostly stale.
_RESET_TOKEN_TTL_MINUTES = 60


class ForgotPasswordRequest(BaseModel):
    email: str = Field(min_length=4, max_length=255)


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=16, max_length=128)
    password: str = Field(min_length=8, max_length=200)


def _hash_reset_token(raw: str) -> str:
    import hashlib
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@router.post("/forgot-password")
def forgot_password(
    req: ForgotPasswordRequest,
    request: Request,
    settings: Settings = Depends(get_settings),
) -> dict:
    """Issue a password-reset token and email it.

    Always returns the same 200 response whether or not the email exists —
    this prevents the endpoint from being used to enumerate registered
    accounts. The token is single-use, hashed at rest, and expires in an hour.
    """
    from datetime import timedelta
    import secrets

    from app.core.rate_limit import RESET_LIMITER

    ip = client_ip(request)
    if not RESET_LIMITER.hit(ip):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many reset requests. Try again later.",
        )

    generic_ok = {
        "ok": True,
        "message": "If an account exists for that email, a reset link is on its way.",
    }

    email = req.email.strip().lower()
    if not is_valid_email(email):
        # Don't leak validity — same generic response.
        return generic_ok

    with get_session() as session:
        user = session.query(User).filter(User.email == email).first()
        if user is None:
            return generic_ok

        raw_token = secrets.token_urlsafe(32)
        user.reset_token_hash = _hash_reset_token(raw_token)
        user.reset_token_expires = datetime.now(timezone.utc) + timedelta(
            minutes=_RESET_TOKEN_TTL_MINUTES
        )
        session.commit()

    # Build the reset link against the public web origin and email it.
    base = (settings.public_base_url or "").rstrip("/")
    link = f"{base}/reset-password?token={raw_token}"
    text = (
        "We received a request to reset your OMISPHERE password.\n\n"
        f"Reset it here (valid for {_RESET_TOKEN_TTL_MINUTES} minutes):\n"
        f"{link}\n\n"
        "If you didn't request this, you can safely ignore this email — your "
        "password won't change.\n\n"
        "— OMISPHERE"
    )
    try:
        from app.notifications.delivery import send_transactional_email
        send_transactional_email(email, "[OMISPHERE] Reset your password", text)
    except Exception:  # noqa: BLE001 — delivery failure must not 500 the request
        pass

    return generic_ok


@router.post("/reset-password", response_model=UserOut)
def reset_password(
    req: ResetPasswordRequest,
    response: Response,
    settings: Settings = Depends(get_settings),
) -> UserOut:
    """Consume a reset token and set a new password.

    On success the token is cleared (single-use) and the user is logged in
    so they land straight in the app.
    """
    if len(req.password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters.")

    token_hash = _hash_reset_token(req.token)
    now = datetime.now(timezone.utc)

    with get_session() as session:
        user = session.query(User).filter(User.reset_token_hash == token_hash).first()
        expires = user.reset_token_expires if user else None
        # Normalize to aware UTC — SQLite can hand back naive datetimes.
        if expires is not None and expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if user is None or expires is None or expires < now:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This reset link is invalid or has expired. Request a new one.",
            )

        user.password_hash = hash_password(req.password)
        user.reset_token_hash = None
        user.reset_token_expires = None
        user.last_login_at = now
        session.commit()

        issue_session(response, user, settings)
        return UserOut(
            id=user.id,
            email=user.email,
            credits_remaining=user.credits_remaining,
            subscription_status=user.subscription_status,
            subscription_renews_at=user.subscription_renews_at,
            is_admin=bool(user.is_admin),
            referral_code=user.referral_code,
            referral_credits_earned=user.referral_credits_earned,
        )


@router.get("/me", response_model=UserOut | None)
def me(
    current: CurrentUser | None = Depends(get_optional_user),
    settings: Settings = Depends(get_settings),
) -> UserOut | None:
    """Returns the current user, or null when not logged in.

    In local mode (``require_auth=False``) this always returns null — there
    is no concept of a logged-in user; everything is unrestricted.
    """
    if current is None or current.id == 0:
        return None
    return UserOut(
        id=current.id,
        email=current.email,
        credits_remaining=current.credits_remaining,
        subscription_status=current.subscription_status,
        subscription_renews_at=current.subscription_renews_at,
        is_admin=current.is_admin,
        referral_code=current.referral_code,
        referral_credits_earned=current.referral_credits_earned,
    )


class NotificationPrefs(BaseModel):
    email_enabled: bool
    webhook_enabled: bool
    webhook_url: str | None = None
    email: str


class NotificationPrefsIn(BaseModel):
    email_enabled: bool | None = None
    webhook_enabled: bool | None = None
    webhook_url: str | None = None


@router.get("/notifications", response_model=NotificationPrefs)
def get_notification_prefs(
    current: CurrentUser | None = Depends(get_optional_user),
) -> NotificationPrefs:
    if current is None or current.id == 0:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Log in to manage notifications.")
    with get_session() as session:
        u = session.get(User, current.id)
        if u is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
        return NotificationPrefs(
            email_enabled=bool(u.notify_alerts_email),
            webhook_enabled=bool(u.notify_alerts_webhook),
            webhook_url=u.webhook_url,
            email=u.email,
        )


@router.put("/notifications", response_model=NotificationPrefs)
def update_notification_prefs(
    payload: NotificationPrefsIn,
    current: CurrentUser | None = Depends(get_optional_user),
) -> NotificationPrefs:
    if current is None or current.id == 0:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Log in to manage notifications.")
    with get_session() as session:
        u = session.get(User, current.id)
        if u is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

        if payload.email_enabled is not None:
            u.notify_alerts_email = 1 if payload.email_enabled else 0
        if payload.webhook_enabled is not None:
            u.notify_alerts_webhook = 1 if payload.webhook_enabled else 0
        if payload.webhook_url is not None:
            url = payload.webhook_url.strip()
            if url and not (url.startswith("http://") or url.startswith("https://")):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="webhook_url must start with http:// or https://",
                )
            if url and len(url) > 500:
                raise HTTPException(status_code=400, detail="webhook_url too long (max 500 chars).")
            u.webhook_url = url or None
            # If they set a webhook URL but didn't explicitly disable webhooks, enable them.
            if url and payload.webhook_enabled is None:
                u.notify_alerts_webhook = 1

        session.commit()
        return NotificationPrefs(
            email_enabled=bool(u.notify_alerts_email),
            webhook_enabled=bool(u.notify_alerts_webhook),
            webhook_url=u.webhook_url,
            email=u.email,
        )
