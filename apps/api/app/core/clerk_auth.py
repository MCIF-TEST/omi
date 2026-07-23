"""Clerk session-token verification for the FastAPI backend.

The browser authenticates with Clerk and sends its short-lived Clerk **session JWT** to this API as an
``Authorization: Bearer <token>`` header. This module verifies that JWT against Clerk's public JWKS
(RS256) and returns the claims, so the API can trust the caller without ever seeing a password.

Secrets discipline: the ``CLERK_SECRET_KEY`` is read from the environment ONLY, server-side, and is
never logged or returned to a client. The publishable key is public by design. Nothing here is
hard-coded. All heavy crypto imports are lazy so a machine without a working ``cryptography`` build can
still import the app.

Enabled only when a Clerk publishable key is present in the environment; otherwise every function is a
no-op and the app falls back to its existing cookie sessions.
"""
from __future__ import annotations

import base64
import logging
import os
import time
from typing import Any

log = logging.getLogger("omi.clerk")

# Cache the JWKS client + resolved issuer so we don't refetch keys on every request.
_JWKS_CLIENT: Any = None
_ISSUER: str | None = None
_USER_EMAIL_CACHE: dict[str, tuple[float, str | None]] = {}
_EMAIL_TTL_SECONDS = 300


def clerk_publishable_key() -> str:
    return (os.environ.get("NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY")
            or os.environ.get("CLERK_PUBLISHABLE_KEY") or "").strip()


def clerk_secret_key() -> str:
    return (os.environ.get("CLERK_SECRET_KEY") or "").strip()


def clerk_enabled() -> bool:
    return bool(clerk_publishable_key())


def _issuer() -> str | None:
    """Derive the Clerk instance issuer from the publishable key. A Clerk publishable key is
    ``pk_(test|live)_<base64(frontend_api_host + '$')>``, so the host — and thus the issuer
    ``https://<host>`` — decodes straight out of it. An explicit ``CLERK_ISSUER`` env overrides."""
    global _ISSUER
    if _ISSUER is not None:
        return _ISSUER or None
    explicit = (os.environ.get("CLERK_ISSUER") or "").strip().rstrip("/")
    if explicit:
        _ISSUER = explicit
        return _ISSUER
    pk = clerk_publishable_key()
    try:
        b64 = pk.split("_", 2)[2]
        host = base64.b64decode(b64 + "==").decode("utf-8").rstrip("$").rstrip("/")
        _ISSUER = f"https://{host}" if host else ""
    except Exception:
        log.warning("could not derive Clerk issuer from the publishable key")
        _ISSUER = ""
    return _ISSUER or None


def _jwks_client():
    """Lazily build a cached PyJWKClient pointed at the instance JWKS. Lazy import keeps the heavy
    crypto dependency out of module import so the app loads even where cryptography can't."""
    global _JWKS_CLIENT
    if _JWKS_CLIENT is not None:
        return _JWKS_CLIENT
    iss = _issuer()
    if not iss:
        return None
    from jwt import PyJWKClient  # lazy: pulls in cryptography

    jwks_url = (os.environ.get("CLERK_JWKS_URL") or f"{iss}/.well-known/jwks.json").strip()
    _JWKS_CLIENT = PyJWKClient(jwks_url)
    return _JWKS_CLIENT


def verify_session_token(token: str) -> dict | None:
    """Verify a Clerk session JWT and return its claims, or None if it is missing/invalid/expired.
    Verifies the RS256 signature against Clerk's JWKS and checks the issuer + expiry. On any error the
    caller simply treats the request as unauthenticated (and may fall back to a cookie session)."""
    if not token or not clerk_enabled():
        return None
    iss = _issuer()
    try:
        import jwt  # lazy

        client = _jwks_client()
        if client is None:
            return None
        signing_key = client.get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            issuer=iss,
            options={"verify_aud": False},
            leeway=10,
        )
        return claims
    except Exception as e:  # noqa: BLE001 — any verification failure = unauthenticated
        log.debug("clerk token verification failed: %s", e)
        return None


def email_from_claims(claims: dict) -> str | None:
    """Best-effort email from the session claims. Clerk's default session token does NOT carry the
    email, so this only returns one when a JWT template adds an ``email`` (or ``primary_email``)
    claim. When absent, the caller falls back to :func:`fetch_user_email` (Backend API)."""
    for key in ("email", "primary_email", "email_address"):
        v = claims.get(key)
        if isinstance(v, str) and "@" in v:
            return v.strip().lower()
    return None


def fetch_user_email(user_id: str) -> str | None:
    """Fetch a Clerk user's primary email via the Clerk Backend API, using the secret key. Cached
    briefly. Used only when the session token itself doesn't carry an email claim."""
    sk = clerk_secret_key()
    if not sk or not user_id:
        return None
    cached = _USER_EMAIL_CACHE.get(user_id)
    if cached and cached[0] > time.time():
        return cached[1]
    try:
        import httpx

        r = httpx.get(
            f"https://api.clerk.com/v1/users/{user_id}",
            headers={"Authorization": f"Bearer {sk}"},
            timeout=6.0,
        )
        r.raise_for_status()
        data = r.json()
        primary_id = data.get("primary_email_address_id")
        email = None
        for addr in data.get("email_addresses", []) or []:
            if addr.get("id") == primary_id or email is None:
                email = addr.get("email_address")
                if addr.get("id") == primary_id:
                    break
        email = email.strip().lower() if isinstance(email, str) else None
        _USER_EMAIL_CACHE[user_id] = (time.time() + _EMAIL_TTL_SECONDS, email)
        return email
    except Exception as e:  # noqa: BLE001
        log.warning("could not fetch Clerk user email: %s", e)
        # Negative-cache the failure briefly so a misconfigured secret / unreachable Backend API can't
        # turn every user-resolution into a multi-second blocking call.
        _USER_EMAIL_CACHE[user_id] = (time.time() + 60, None)
        return None
