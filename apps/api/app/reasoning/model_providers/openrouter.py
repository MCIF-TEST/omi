"""OpenRouter reasoning provider — the OpenRouter transport behind the ReasoningProvider seam (Phase 2).

OpenRouter is a standardized OpenAI-compatible model gateway. This provider satisfies the same
:class:`ReasoningProvider` protocol as the Hugging Face client, so the runtime, the canonical validation,
the Omi-owned metadata overlay, the Governor, persistence, and the frontend never learn which gateway
served the inference. It performs exactly ONE model inference per call.

Two modes, chosen by configuration:

* **Preset mode** (primary) — the request references an OpenRouter Preset (``model="@preset/<slug>"``) that
  holds Omi's stable Master Analyst Protocol (system prompt + model + routing). The dynamic request then
  sends ONLY the Investigation Package as the user message; it does NOT redundantly resend the master
  prompt. Omi records the local master-prompt version/hash it EXPECTS the preset to contain (it does not,
  and cannot, verify the remote preset content).
* **Direct mode** — no preset; the request sends the compiled system + user messages and an explicit model.

Structured output: when a canonical schema is supplied (the ONE Phase-1 ComprehensiveAssessment schema) the
request carries ``response_format={"type":"json_schema", ...}`` — the SAME schema the local validator uses.
Local canonical validation ALWAYS runs downstream regardless, so native structured output never weakens it.

Stdlib-only (``urllib``); typed failures (``ProviderUnavailable`` / ``ProviderTimeout`` /
``ProviderProtocolError`` / ``ProviderError``) so the runtime degrades to the deterministic Floor and never
fabricates an answer. The API key rides in the ``Authorization`` header only — never in the wire body, a
log, or the forensic capture.
"""
from __future__ import annotations

import json
import logging
import os
import socket
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

from .base import (
    ProviderError,
    ProviderProtocolError,
    ProviderTimeout,
    ProviderUnavailable,
    ReasoningRequest,
    ReasoningResponse,
)
from .remote import _extract_message, extract_json, forensic_on, strip_thinking

logger = logging.getLogger(__name__)

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


def _is_timeout(exc: BaseException | None) -> bool:
    return isinstance(exc, (TimeoutError, socket.timeout)) or "timed out" in str(exc or "").lower()


def classify_transport_failure(exc: BaseException, status: int | None) -> str:
    """Map a transport failure to one of the operational failure classes (Phase 5E). Derived from the
    typed error + the HTTP status; never inspects response bodies for secrets."""
    if isinstance(exc, ProviderTimeout):
        return "timeout"
    if isinstance(exc, ProviderProtocolError):
        return "invalid_json"
    if isinstance(exc, ProviderUnavailable):
        return "not_configured"
    if isinstance(status, int):
        if status in (401, 403):
            return "authentication"
        if status == 429:
            return "rate_limit"
        if status == 404:
            return "invalid_preset_or_model"
        if status == 400:
            return "invalid_request"
        if 500 <= status < 600:
            return "http_error"
    msg = str(exc).lower()
    if _is_timeout(exc):
        return "timeout"
    if "unreachable" in msg or "connection" in msg or "urlerror" in msg:
        return "transport"
    if "http" in msg:
        return "http_error"
    return "unexpected_response"


@dataclass
class OpenRouterReasoningProvider:
    """OpenRouter chat-completions client. Configure a preset (preset mode) or a model (direct mode) plus
    ``OPENROUTER_API_KEY`` in the environment to activate; without a key ``complete`` raises
    ``ProviderUnavailable`` and the runtime stays on the deterministic Floor."""

    base_url: str = OPENROUTER_URL
    model: str | None = None                 # direct-mode model slug, or a base model to layer a preset on
    preset: str | None = None                # OpenRouter Preset slug (preset mode) — carries the system prompt
    canonical_schema: dict | None = None     # the ONE Phase-1 schema, for native structured output
    structured_output: bool = True           # send response_format json_schema when a schema is present
    referer: str | None = None               # optional HTTP-Referer (dashboard attribution) — not a secret
    title: str | None = None                 # optional X-Title (dashboard attribution) — not a secret
    timeout: float = 30.0
    max_retries: int = 2
    token_env: tuple[str, ...] = ("OPENROUTER_API_KEY",)
    backoff_cap: float = 2.0
    name: str = "openrouter"
    capture: dict | None = None
    # Provenance echoed into the forensic capture (never the request body). Set by the transport.
    prompt_hash: str | None = None
    package_hash: str | None = None
    master_prompt_hash: str | None = None

    # ----------------------------------------------------------------------- #
    def _token(self) -> str | None:
        for key in self.token_env:
            val = os.environ.get(key)
            if val:
                return val
        return None

    def _model_ref(self) -> str:
        """The ``model`` field: a preset reference in preset mode (optionally layering a base model), or the
        explicit model slug in direct mode."""
        if self.preset:
            slug = self.preset if self.preset.startswith("@preset/") else f"@preset/{self.preset}"
            return f"{self.model}{slug}" if self.model else slug
        return self.model or ""

    def _response_format(self) -> dict | None:
        if not (self.structured_output and isinstance(self.canonical_schema, dict)):
            return None
        schema = self.canonical_schema
        name = schema.get("schema_id") or "comprehensive_assessment_v1"
        return {"type": "json_schema", "json_schema": {"name": name, "strict": True, "schema": schema}}

    def _request_body(self, request: ReasoningRequest) -> bytes:
        # Preset mode: the preset supplies the system prompt, so send ONLY the dynamic user message — the
        # Master Analyst Protocol is NOT redundantly resent. Direct mode: send system + user.
        if self.preset:
            messages = [{"role": "user", "content": request.user}]
        else:
            messages = [{"role": "system", "content": request.system},
                        {"role": "user", "content": request.user}]
        body: dict = {
            "model": self._model_ref(),
            "messages": messages,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "stream": False,
        }
        rf = self._response_format()
        if rf is not None:
            body["response_format"] = rf
        return json.dumps(body).encode("utf-8")

    def _headers(self, token: str) -> dict:
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        if self.referer:
            headers["HTTP-Referer"] = self.referer
        if self.title:
            headers["X-Title"] = self.title
        return headers

    def _capture_request(self, body: bytes, request: ReasoningRequest) -> None:
        if self.capture is None:
            return
        # The wire body carries NO secret (the key rides in the Authorization header only).
        self.capture["endpoint_url"] = self.base_url
        self.capture["endpoint_api"] = "openrouter"
        self.capture["openrouter_preset"] = self.preset
        self.capture["configured_model"] = self.model
        self.capture["model_ref"] = self._model_ref()
        self.capture["structured_output"] = bool(self._response_format() is not None)
        self.capture["request_wire_body"] = body.decode("utf-8", "replace")[:12000]
        self.capture["final_prompt_user"] = request.user
        # In preset mode the system prompt lives in the preset; record what Omi EXPECTS it to be.
        self.capture["final_prompt_system"] = None if self.preset else request.system
        self.capture["master_prompt_hash"] = self.master_prompt_hash

    def _capture_response(self, status, raw: bytes) -> None:
        """Record OpenRouter response metadata into the forensic capture: HTTP status, the generation id
        (body ``id``), the served model, and token usage + USD cost. Best-effort; never raises; no secret."""
        if self.capture is None:
            return
        self.capture["response_status"] = status
        self.capture["response_bytes"] = len(raw)
        try:
            obj = json.loads(raw.decode("utf-8", "replace"))
        except Exception:  # noqa: BLE001
            obj = None
        self.capture["raw_response_body"] = raw.decode("utf-8", "replace")[:12000]
        if isinstance(obj, dict):
            if obj.get("id"):
                self.capture["endpoint_request_id"] = obj.get("id")   # OpenRouter generation id (gen-...)
            self.capture["served_model"] = obj.get("model")
            usage = obj.get("usage")
            if isinstance(usage, dict):
                self.capture["usage"] = {
                    "prompt_tokens": usage.get("prompt_tokens"),
                    "completion_tokens": usage.get("completion_tokens"),
                    "total_tokens": usage.get("total_tokens"),
                    "cost": usage.get("cost"),
                    "cost_details": usage.get("cost_details"),
                }

    def _fetch(self, body: bytes, headers: dict) -> tuple[str, int]:
        """POST once (one model inference), retrying ONLY transient transport failures that did NOT bill a
        generation — connection errors and HTTP 5xx/429. A 2xx-with-body is a completed generation and is
        never retried; a read-timeout is NOT retried (the model may have generated) so a second billable
        generation is never disguised as a network retry. Returns ``(text, attempts)``."""
        last: BaseException | None = None
        for attempt in range(self.max_retries + 1):
            try:
                req = urllib.request.Request(self.base_url, data=body, headers=headers)
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    raw = resp.read()
                    status = getattr(resp, "status", None) or resp.getcode()
                    self._capture_response(status, raw)
                    return _extract_message(raw), attempt + 1
            except urllib.error.HTTPError as he:
                last = he
                if self.capture is not None:
                    self.capture["response_status"] = he.code
                    try:
                        self.capture["raw_response_body"] = he.read().decode("utf-8", "replace")[:4000]
                    except Exception:  # noqa: BLE001
                        pass
                # retry only transient server-side / rate-limit statuses (no generation billed); never 4xx
                if he.code in (429, 500, 502, 503, 504) and attempt < self.max_retries:
                    time.sleep(min(self.backoff_cap, 0.5 * (2 ** attempt)))
                    continue
                raise ProviderError(f"openrouter HTTP {he.code}") from he
            except Exception as exc:  # noqa: BLE001 — connection error / timeout
                last = exc
                if _is_timeout(exc):  # do NOT retry a timeout — a generation may already have been billed
                    raise ProviderTimeout(f"openrouter timed out after {attempt + 1} attempt(s)") from exc
                if attempt < self.max_retries:
                    time.sleep(min(self.backoff_cap, 0.5 * (2 ** attempt)))
                    continue
        raise ProviderError(f"openrouter unreachable: {last}") from last

    def complete(self, request: ReasoningRequest) -> ReasoningResponse:
        token = self._token()
        if not token:
            raise ProviderUnavailable("OPENROUTER_API_KEY is not configured")
        if not (self.preset or self.model):
            raise ProviderUnavailable("no OpenRouter preset or model configured")
        body = self._request_body(request)
        headers = self._headers(token)
        self._capture_request(body, request)

        # Transport-lifecycle logging (Phase 5E). Sizes/status/ids ONLY — never the API key
        # (rides in the Authorization header, never logged), the prompt, or the investigation body.
        structured_output = bool(self._response_format() is not None)
        logger.info(
            "openrouter.transport START provider=%s endpoint=%s preset=%s model_ref=%s "
            "request_bytes=%d structured_output=%s",
            self.name, self.base_url, self.preset, self._model_ref(), len(body), structured_output,
        )

        t0 = time.perf_counter()
        try:
            text, attempts = self._fetch(body, headers)
            if self.capture is not None:
                self.capture["raw_text_pre_processing"] = (text or "")[:12000]
            text = strip_thinking(text)
            structured = extract_json(text) if request.response_format == "json" else None
            if request.response_format == "json" and structured is None:
                raise ProviderProtocolError("openrouter response was not a valid JSON object")
        except BaseException as exc:  # noqa: BLE001 — classify + log, then re-raise unchanged
            latency_ms = (time.perf_counter() - t0) * 1000.0
            status = (self.capture or {}).get("response_status") if self.capture else None
            logger.warning(
                "openrouter.transport FAIL class=%s status=%s latency_ms=%.2f detail=%s",
                classify_transport_failure(exc, status), status, latency_ms, type(exc).__name__,
            )
            raise
        latency_ms = (time.perf_counter() - t0) * 1000.0
        cap = self.capture or {}
        logger.info(
            "openrouter.transport OK status=%s request_id=%s latency_ms=%.2f bytes_received=%s "
            "attempts=%d completion=success",
            cap.get("response_status"), cap.get("endpoint_request_id"), latency_ms,
            cap.get("response_bytes"), attempts,
        )
        if self.capture is not None:
            self.capture["attempts"] = attempts
            self.capture["latency_ms"] = round(latency_ms, 2)

        served = (self.capture or {}).get("served_model") if self.capture else None
        return ReasoningResponse(
            text=text, model=served or self._model_ref(), revision=self.revision_of(),
            structured=structured,
            diagnostics={"provider": self.name, "attempts": attempts, "api": "openrouter",
                         "latency_ms": round(latency_ms, 2), "model_ref": self._model_ref(),
                         "preset": self.preset, "served_model": served,
                         "structured_output": bool(self._response_format() is not None)})

    def revision_of(self) -> str | None:
        return None


__all__ = ["OpenRouterReasoningProvider", "OPENROUTER_URL"]
