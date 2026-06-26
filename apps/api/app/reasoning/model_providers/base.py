"""The model-agnostic reasoning-provider seam (OMI_REASONING_ORCHESTRATION_V1 / Sprint 006).

A ``ReasoningProvider`` turns a structured request into a structured response. It is the
single point of contact between Omi's deterministic architecture and any external model:
the council, the contracts, the blackboard, and the Governor know nothing about HTTP, HF,
Qwen, or tokens — they see only this protocol. A future OpenAI / Anthropic / local provider
is a new class implementing the same protocol with **no architectural change**.

Failures are typed (``ProviderError`` and subclasses) so a calling module can treat any of
them uniformly as "fall back to the deterministic analyst" — the provider never silently
fabricates an answer.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


class ProviderError(Exception):
    """Base class for any provider failure. A council module treats every subclass as a
    signal to fall back to its deterministic analyst."""


class ProviderUnavailable(ProviderError):
    """The provider cannot run at all — not configured, no endpoint, or no credentials."""


class ProviderTimeout(ProviderError):
    """The provider did not respond within the configured timeout (after retries)."""


class ProviderProtocolError(ProviderError):
    """The provider responded, but the response could not be understood (e.g. not JSON)."""


@dataclass(frozen=True)
class ReasoningRequest:
    """A model-agnostic completion request. ``revision`` pins the model version for
    reproducibility; ``response_format='json'`` asks for a structured object."""

    system: str
    user: str
    model: str = ""
    revision: str | None = None            # model revision pinning
    max_tokens: int = 1024
    temperature: float = 0.2
    stream: bool = False                   # streaming compatibility (where the provider supports it)
    response_format: str = "json"          # "json" | "text"


@dataclass
class ReasoningResponse:
    """A model-agnostic completion result. ``structured`` is the parsed JSON object when a
    JSON response was requested; ``diagnostics`` carries latency / attempts / streamed /
    model / revision for transparency."""

    text: str
    model: str = ""
    revision: str | None = None
    structured: dict | None = None
    diagnostics: dict = field(default_factory=dict)


@runtime_checkable
class ReasoningProvider(Protocol):
    """The permanent provider seam. Any implementation (HF/Qwen today, another model
    tomorrow) plugs into the council unchanged. ``complete`` either returns a
    ``ReasoningResponse`` or raises a ``ProviderError``."""

    name: str

    def complete(self, request: ReasoningRequest) -> ReasoningResponse: ...
