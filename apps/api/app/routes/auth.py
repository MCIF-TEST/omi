"""Auth routes: signup, login, logout, me."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field

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
from app.storage.db import get_session
from app.storage.models import User


router = APIRouter(prefix="/v1/auth", tags=["auth"])


def _client_ip(request: Request) -> str:
    """Best-effort client IP. Honors X-Forwarded-For from the platform proxy."""
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return (request.client.host if request.client else "unknown") or "unknown"


class SignupRequest(BaseModel):
    email: str = Field(min_length=4, max_length=255)
    password: str = Field(min_length=8, max_length=200)


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


@router.post("/signup", response_model=UserOut)
def signup(req: SignupRequest, request: Request, response: Response, settings: Settings = Depends(get_settings)) -> UserOut:
    # Rate-limit account creation per IP (5/hour) to slow farming.
    from app.core.rate_limit import SIGNUP_LIMITER
    ip = _client_ip(request)
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
        user = User(
            email=email,
            password_hash=hash_password(req.password),
            credits_remaining=999999 if is_super_admin else settings.free_trial_credits,
            last_login_at=datetime.now(timezone.utc),
            is_admin=1 if is_super_admin else 0,
        )
        session.add(user)
        session.flush()  # populate user.id
        issue_session(response, user, settings)
        return UserOut(
            id=user.id,
            email=user.email,
            credits_remaining=user.credits_remaining,
            subscription_status=user.subscription_status,
            subscription_renews_at=user.subscription_renews_at,
            is_admin=bool(user.is_admin),
        )


@router.post("/login", response_model=UserOut)
def login(req: LoginRequest, request: Request, response: Response, settings: Settings = Depends(get_settings)) -> UserOut:
    # Rate-limit login per IP (10/min) to slow brute-force.
    from app.core.rate_limit import LOGIN_LIMITER
    ip = _client_ip(request)
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
        )


@router.post("/logout")
def logout(response: Response) -> dict:
    clear_session(response)
    return {"ok": True}


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
    )
