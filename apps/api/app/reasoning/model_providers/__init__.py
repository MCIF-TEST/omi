"""Model-agnostic reasoning providers (Sprint 006).

The seam between Omi's deterministic architecture and any external model. The council, the
contracts, the blackboard, and the Governor depend only on the :class:`ReasoningProvider`
protocol and the typed errors here — never on HTTP/HF/Qwen specifics. A future provider is a
new class implementing the protocol, activated by configuration.
"""
from __future__ import annotations

from .base import (
    ProviderError,
    ProviderProtocolError,
    ProviderTimeout,
    ProviderUnavailable,
    ReasoningProvider,
    ReasoningRequest,
    ReasoningResponse,
)
from .config import build_remote_provider, provider_status
from .mock import MockReasoningProvider
from .openrouter import OPENROUTER_URL, OpenRouterReasoningProvider
from .remote import RemoteReasoningProvider, assemble_stream, extract_json, strip_thinking

__all__ = [
    "ReasoningProvider", "ReasoningRequest", "ReasoningResponse",
    "ProviderError", "ProviderUnavailable", "ProviderTimeout", "ProviderProtocolError",
    "RemoteReasoningProvider", "MockReasoningProvider",
    "OpenRouterReasoningProvider", "OPENROUTER_URL",
    "assemble_stream", "extract_json", "strip_thinking",
    "build_remote_provider", "provider_status",
]
