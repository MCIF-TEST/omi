"""In-process reasoning providers for tests and fully-offline runs.

``MockReasoningProvider`` is scriptable: it returns a canned structured/text response, or
raises a chosen ``ProviderError`` — so every branch (success, unavailable, timeout, malformed
output, streaming) is exercisable deterministically without a network or GPU.
"""
from __future__ import annotations

import json

from .base import ReasoningRequest, ReasoningResponse


class MockReasoningProvider:
    """A deterministic provider stand-in. Pass ``structured`` (or ``text``) for the success
    path, or ``error=`` an exception instance to simulate a failure."""

    def __init__(
        self, *, structured: dict | None = None, text: str = "",
        error: BaseException | None = None, name: str = "mock-reasoning",
        streamed: bool = False, latency_ms: float = 0.0,
    ) -> None:
        self._structured = structured
        self._text = text
        self._error = error
        self.name = name
        self._streamed = streamed
        self._latency = latency_ms
        self.calls = 0
        self.last_request: ReasoningRequest | None = None

    def complete(self, request: ReasoningRequest) -> ReasoningResponse:
        self.calls += 1
        self.last_request = request
        if self._error is not None:
            raise self._error
        structured = self._structured
        text = self._text
        if structured is not None and not text:
            text = json.dumps(structured)
        if structured is None and request.response_format == "json" and text:
            try:
                structured = json.loads(text)
            except json.JSONDecodeError:
                structured = None
        return ReasoningResponse(
            text=text, model=request.model, revision=request.revision, structured=structured,
            diagnostics={
                "provider": self.name, "attempts": 1, "latency_ms": float(self._latency),
                "streamed": bool(self._streamed), "mocked": True,
            },
        )
