"""Shared client-IP helpers.

Centralises IP extraction and hashing so signup fraud prevention, demo
rate-limiting, and any future abuse checks all use the same canonical
representation. IPs are never stored raw — only their SHA-256 hash with a
domain-separated salt — so this stays GDPR-friendly.
"""

from __future__ import annotations

import hashlib

from fastapi import Request


_IP_HASH_SALT = b"omi-ip-hash-v1"


def client_ip(request: Request) -> str:
    """Best-effort client IP. Honours ``X-Forwarded-For`` from the edge proxy.

    Returns ``"unknown"`` when no usable address is present so downstream
    hashing is deterministic.
    """
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return (request.client.host if request.client else "unknown") or "unknown"


def hash_ip(ip: str | None) -> str:
    """Hash an IP for storage/equality comparisons.

    Domain-separated so the same IP gets the same hash across all callers
    (signup, demo scan log, etc.) but cannot be back-correlated against
    hashes from other systems even if they share a hashing scheme.
    """
    h = hashlib.sha256()
    h.update((ip or "unknown").encode("utf-8"))
    h.update(_IP_HASH_SALT)
    return h.hexdigest()
