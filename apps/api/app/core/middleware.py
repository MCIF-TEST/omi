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

    def __init__(self, app, *, max_hits: int = 120, per_seconds: float = 60.0):
        super().__init__(app)
        from app.core.rate_limit import SlidingWindowLimiter

        self._limiter = SlidingWindowLimiter(max_hits=max_hits, per_seconds=per_seconds)

    async def dispatch(self, request: Request, call_next):
        # Health checks must never be throttled (Render / load balancers).
        if request.url.path in ("/health", "/v1/health", "/"):
            return await call_next(request)

        from app.core.ip import client_ip

        ip = client_ip(request)
        if not self._limiter.hit(ip):
            retry = int(self._limiter.retry_after(ip)) + 1
            return JSONResponse(
                status_code=429,
                content={"detail": "Too many requests — please try again shortly."},
                headers={
                    "Retry-After": str(retry),
                    **{k: v for k, v in _SECURITY_HEADERS.items()},
                },
            )
        return await call_next(request)


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
