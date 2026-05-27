"""Production middleware — security headers, request IDs, latency capture."""

from __future__ import annotations

import secrets
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.metrics import get_registry


_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
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
