"""Structured JSON errors, so an agent can act on a failure instead of guessing.

WHAT WAS WRONG. FastAPI's default handler returns ``{"detail": "..."}``. That is JSON, but the only
machine-readable part is the status code: the reason lives in an English sentence written for a
person, and there is nothing telling a client what to DO about it. An agent that hits 402 cannot
tell "you are out of credits" from "this feature needs a bigger plan", and both are recoverable in
different ways.

THE ENVELOPE. Every error now carries a stable ``code``, the human ``message``, a ``hint`` naming
the recovery, and a ``docs`` link.

**``detail`` is kept, unchanged, at the top level.** The web app reads it in a dozen places
(``ApiError.message``), the analyst's failure sentences key on it, and the Stripe surfaces render it
directly. Replacing it would have been a cleaner envelope and a broken product, so this ADDS
structure beside it rather than moving anything.

THE CODES ARE DERIVED FROM STATUS, NOT INVENTED PER ROUTE. A per-route code table would drift the
moment a route was added, and a code that only some routes set is worse than no code at all because
a client cannot rely on it. Where a route wants to be more specific it raises with an explicit code
(see ``coded``), and everything else gets an honest generic one.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

#: Where an agent is sent to understand any of this. One page, named, crawlable.
DOCS_URL = "https://omisphere.online/developers"

#: Status -> (code, hint). The hint names the RECOVERY, not the failure: a client that already knows
#: it got a 429 gains nothing from being told it was rate limited, and everything from being told
#: the response carries Retry-After.
_BY_STATUS: dict[int, tuple[str, str]] = {
    400: ("bad_request",
          "Check the request body and query parameters against the OpenAPI specification."),
    401: ("unauthenticated",
          "Sign in to obtain a session cookie, then repeat the request."),
    402: ("payment_required",
          "This needs a paid plan or more credits. Upgrade or buy a credit pack, then retry."),
    403: ("forbidden",
          "The account is authenticated but not entitled to this. It is not retryable as-is."),
    404: ("not_found",
          "Check the identifier. See /llms.txt or /openapi.json for what exists."),
    409: ("conflict",
          "The resource is not in a state that allows this. Re-read it and retry if appropriate."),
    413: ("payload_too_large",
          "The request body is over the 1 MiB limit. Split the work into smaller "
          "requests and send them in sequence."),
    422: ("validation_failed",
          "One or more fields are missing or the wrong type. The `fields` list names each one."),
    429: ("rate_limited",
          "Wait the number of seconds in the Retry-After header, then retry. Nothing was charged."),
    500: ("internal_error",
          "A fault on our side. Retrying an idempotent request is safe."),
    502: ("upstream_error", "An upstream provider failed. Retry shortly."),
    503: ("unavailable",
          "Temporarily unavailable, often a missing configuration or an exhausted daily budget. "
          "Retry later; the message says which."),
}

_FALLBACK = ("error", "See the message. If it persists, the status code describes the class.")


class CodedHTTPException(HTTPException):
    """An HTTPException that names its own machine-readable code and recovery hint.

    For the cases where the status alone is genuinely ambiguous. 402 covering both "out of credits"
    and "wrong plan" is the motivating example: same status, different recoveries, and a client
    should not have to pattern-match English to tell them apart.
    """

    def __init__(self, status_code: int, detail: str, *, code: str,
                 hint: str | None = None, headers: dict[str, str] | None = None) -> None:
        super().__init__(status_code=status_code, detail=detail, headers=headers)
        self.code = code
        self.hint = hint


def error_body(
    status_code: int, detail: Any, *, code: str | None = None,
    hint: str | None = None, fields: list[dict] | None = None,
) -> dict:
    """The response body. ``detail`` stays at the top level for every existing client."""
    default_code, default_hint = _BY_STATUS.get(status_code, _FALLBACK)
    error: dict[str, Any] = {
        "code": code or default_code,
        "message": detail if isinstance(detail, str) else str(detail),
        "hint": hint or default_hint,
        "docs": DOCS_URL,
        "status": status_code,
    }
    if fields:
        error["fields"] = fields
    return {"error": error, "detail": detail}


def install_error_handlers(app: FastAPI) -> None:
    """Replace the default handlers with ones that emit the envelope.

    Registered for HTTPException, RequestValidationError and the 404 a router never matched, which
    is the one an agent probing the API hits first and the one FastAPI would otherwise answer with a
    bare ``{"detail": "Not Found"}``.
    """

    # BOTH exception classes, and this is not belt-and-braces.
    #
    # FastAPI's HTTPException is what routes raise. Starlette's is what the ROUTER raises when no
    # route matched at all, and it is a different class, so registering only the FastAPI one leaves
    # the plain 404 answering `{"detail": "Not Found"}` with no code and no hint. That 404 is the
    # first thing an agent probing the API hits, so it is the worst one to leave unstructured.
    @app.exception_handler(StarletteHTTPException)
    @app.exception_handler(HTTPException)
    async def _http(request: Request, exc: HTTPException) -> JSONResponse:  # noqa: ARG001
        return JSONResponse(
            status_code=exc.status_code,
            content=error_body(
                exc.status_code, exc.detail,
                code=getattr(exc, "code", None),
                hint=getattr(exc, "hint", None),
            ),
            # Preserved deliberately: Retry-After and the X-RateLimit family are how a client knows
            # WHEN to retry, and the whole point of the hint is to send them to those headers.
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError) -> JSONResponse:  # noqa: ARG001
        fields = [
            {
                "field": ".".join(str(p) for p in (e.get("loc") or ()) if p != "body"),
                "problem": e.get("msg", ""),
                "type": e.get("type", ""),
            }
            for e in exc.errors()
        ]
        named = ", ".join(f["field"] for f in fields if f["field"]) or "the request body"
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=error_body(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                f"Invalid request: {named}.",
                fields=fields,
            ),
        )
