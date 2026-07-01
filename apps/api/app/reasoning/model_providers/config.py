"""Config-driven provider assembly — activation is configuration, never architecture.

``build_remote_provider`` reads the existing analyst settings (``analyst_endpoint_url``,
``analyst_hf_revision``, ``analyst_timeout_seconds``, ``analyst_max_retries``) and returns a
configured :class:`RemoteReasoningProvider`, or ``None`` when no endpoint is set — in which
case the council stays fully deterministic. Once the endpoint + token exist, the first AI
specialist activates with **no code change**.
"""
from __future__ import annotations

import os
from typing import Any

from .remote import RemoteReasoningProvider

# The model the omi-analyst endpoint serves today; informational (the endpoint pins the model).
_DEFAULT_MODEL = "Qwen/Qwen3-4B-Thinking-2507-FP8"


def build_remote_provider(settings: Any | None = None) -> RemoteReasoningProvider | None:
    """Construct the configured remote provider, or ``None`` when no endpoint is configured."""
    if settings is None:
        from app.core.config import get_settings
        settings = get_settings()
    endpoint = getattr(settings, "analyst_endpoint_url", None)
    if not endpoint:
        return None
    return RemoteReasoningProvider(
        endpoint_url=endpoint,
        model=getattr(settings, "analyst_hf_repo", None) or _DEFAULT_MODEL,
        revision=getattr(settings, "analyst_hf_revision", None),
        timeout=float(getattr(settings, "analyst_timeout_seconds", 30.0) or 30.0),
        max_retries=int(getattr(settings, "analyst_max_retries", 2) or 2),
        api=str(getattr(settings, "analyst_endpoint_api", "generate") or "generate"),
    )


def provider_status(settings: Any | None = None) -> dict:
    """Diagnostic snapshot of AI-specialist readiness — no secrets (token presence is a
    boolean). ``ai_specialist_ready`` is true only when the flag is on AND an endpoint AND a
    token are all present; otherwise the council runs deterministically."""
    if settings is None:
        from app.core.config import get_settings
        settings = get_settings()
    endpoint = getattr(settings, "analyst_endpoint_url", None)
    token_present = bool(os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACE_HUB_TOKEN"))
    enabled = bool(getattr(settings, "analyst_enabled", False))
    return {
        "analyst_enabled": enabled,
        "endpoint_configured": bool(endpoint),
        "hf_token_present": token_present,
        "model": getattr(settings, "analyst_hf_repo", None),
        "revision": getattr(settings, "analyst_hf_revision", None),
        "timeout_seconds": float(getattr(settings, "analyst_timeout_seconds", 30.0) or 30.0),
        "max_retries": int(getattr(settings, "analyst_max_retries", 2) or 2),
        "ai_specialist_ready": bool(enabled and endpoint and token_present),
        "governor": "mandatory",
        "deterministic_floor": "always-on",
    }
