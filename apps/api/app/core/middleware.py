"""Production middleware — security headers, request IDs, latency capture, global rate limit."""

from __future__ import annotations

import secrets
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.metrics import get_registry


# Match web service headers (ScanMyVibe / modern browser baseline).
_SECURITY_HEADERS = {
    "Strict-Transport-Security": "max-age=63072000; includeSubDomains; preload",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": (
        "camera=(), microphone=(), geolocation=(), payment=(), usb=(), "
        "interest-cohort=(), accelerometer=(), gyroscope=(), magnetometer=()"
    ),
    "Cross-Origin-Opener-Policy": "same-origin-allow-popups",
    "Cross-Origin-Resource-Policy": "same-site",
    "X-XSS-Protection": "0",
    # API is JSON; CSP is mainly for HTML, but scanners check every origin.
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'; base-uri 'none'",
}


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Generate / propagate a request id; attach to response + state."""

    async def dispatch(self, request: Request, call_next):
        rid = request.headers.get("x-request-id") or secrets.token_hex(6)
        request.state.request_id = rid
        response = await call_next(request)
        response.headers["x-request-id"] = rid
        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)
        for k, v in _SECURITY_HEADERS.items():
            response.headers.setdefault(k, v)
        return response


class GlobalRateLimitMiddleware(BaseHTTPMiddleware):
    """Coarse per-IP limit on all API routes (scanners / abuse).

    Auth routes keep their stricter dedicated limiters. This catches bulk
    scraping of public endpoints that previously returned 200 with no throttle.
    """

    def __init__(self, app, *, max_hits: int | None = None, per_seconds: float | None = None):
        super().__init__(app)
        from app.core.config import get_settings
        from app.core.rate_limit import SlidingWindowLimiter

        s = get_settings()
        # Budgets come from settings so a traffic spike is absorbed by an env change, not a deploy.
        # Explicit args still win (tests construct this directly with tight values).
        self._limiter = SlidingWindowLimiter(
            max_hits=int(max_hits if max_hits is not None else s.rate_limit_global_max),
            per_seconds=float(
                per_seconds if per_seconds is not None else s.rate_limit_global_window_seconds
            ),
        )

    async def dispatch(self, request: Request, call_next):
        # Health checks must never be throttled (Render / load balancers).
        if request.url.path in ("/health", "/v1/health", "/"):
            return await call_next(request)

        from app.core.ip import client_ip

        # Keyed on IP deliberately. This middleware runs BEFORE auth, so any user identity available
        # here is an unverified claim that an attacker could rotate to escape the limit. Per-user
        # budgets belong at the route level, where the auth dependency has already run
        # (see rate_limit.enforce / rate_limit.user_key).
        ip = client_ip(request)
        if not self._limiter.hit(ip):
            retry = int(self._limiter.retry_after(ip)) + 1
            return JSONResponse(
                status_code=429,
                content={"detail": "Too many requests — please try again shortly."},
                headers={
                    "Retry-After": str(retry),
                    "X-RateLimit-Limit": str(self._limiter.max_hits),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(retry),
                    **{k: v for k, v in _SECURITY_HEADERS.items()},
                },
            )
        response = await call_next(request)
        # Advertise the remaining budget so a client can slow down BEFORE it gets refused.
        try:
            response.headers["X-RateLimit-Limit"] = str(self._limiter.max_hits)
            response.headers["X-RateLimit-Remaining"] = str(self._limiter.remaining(ip))
        except Exception:  # noqa: BLE001 — headers are advisory, never worth failing a response
            pass
        return response


class BodySizeLimitMiddleware:
    """Reject oversized request bodies before anything parses them.

    Neither Starlette nor uvicorn imposes a body limit, and ten routes accept an unvalidated
    ``payload: dict``, so FastAPI would parse whatever arrived fully into memory. On a small instance
    that is a cheap way to exhaust RAM, and it needs no account.

    Written as raw ASGI rather than ``BaseHTTPMiddleware`` for two reasons: it must refuse
    ``Content-Length`` before the body is ever read, and it must also count bytes as they stream, since
    a chunked request carries no ``Content-Length`` at all and would otherwise walk straight past a
    header-only check.

    The cap applies to request bodies only. It is not a limit on responses, and GET/HEAD/DELETE are
    unaffected because they carry no body.
    """

    def __init__(self, app, *, max_bytes: int | None = None):
        self.app = app
        if max_bytes is None:
            from app.core.config import get_settings
            max_bytes = int(get_settings().max_request_body_bytes)
        self.max_bytes = max_bytes

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        async def _refuse() -> None:
            resp = JSONResponse(
                status_code=413,
                content={
                    "detail": (
                        f"Request body too large. The limit is "
                        f"{self.max_bytes // 1024} KiB."
                    )
                },
                headers=dict(_SECURITY_HEADERS),
            )
            await resp(scope, receive, send)

        # Declared length: refuse before reading a single byte.
        for name, value in scope.get("headers") or []:
            if name == b"content-length":
                try:
                    if int(value) > self.max_bytes:
                        await _refuse()
                        return
                except ValueError:
                    pass  # malformed header; the streaming guard below still applies
                break

        received = 0
        exceeded = False

        async def counting_receive():
            nonlocal received, exceeded
            message = await receive()
            if message.get("type") == "http.request":
                received += len(message.get("body") or b"")
                if received > self.max_bytes:
                    exceeded = True
                    # Stop the stream so the app sees a truncated body rather than continuing to
                    # buffer an unbounded upload into memory.
                    return {"type": "http.disconnect"}
            return message

        await self.app(scope, counting_receive, send)


class MetricsMiddleware(BaseHTTPMiddleware):
    """Capture per-route latency + counts. Cheap; samples bounded."""

    async def dispatch(self, request: Request, call_next):
        start = time.perf_counter()
        registry = get_registry()
        registry.counter("http.requests.total").inc()
        status = 500
        try:
            response: Response = await call_next(request)
            status = response.status_code
            return response
        finally:
            elapsed_ms = (time.perf_counter() - start) * 1000
            route = request.url.path
            # Bucket by HTTP method + path prefix to avoid cardinality blowup
            key = f"{request.method} {_bucket(route)}"
            registry.histogram(f"http.latency_ms.{key}").observe(elapsed_ms)
            registry.counter(f"http.status.{status // 100}xx").inc()


def _bucket(path: str) -> str:
    """Collapse high-cardinality path segments to keep metrics readable."""
    parts = path.split("/")
    out: list[str] = []
    for p in parts:
        if not p:
            out.append(p)
            continue
        # Numeric ID, slug, or token — replace with placeholder.
        if p.isdigit():
            out.append("{id}")
        elif p.startswith("inv_") or p.startswith("rpt_"):
            out.append("{slug}")
        elif p.startswith("UC") and len(p) == 24:
            out.append("{channel_id}")
        else:
            out.append(p)
    return "/".join(out) or "/"
