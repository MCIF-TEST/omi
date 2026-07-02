"""Remote reasoning provider — an HTTP client for a Hugging Face text-generation endpoint.

Model-agnostic at the seam (it satisfies :class:`ReasoningProvider`); HF/Qwen-specific only
inside. Provides everything the council needs to host a real model safely:

- **revision pinning** (reproducibility), **timeout**, **capped-backoff retries** on transient
  network errors, and **diagnostics** (latency / attempts / streamed / model / revision);
- **structured output** parsing (strips a Qwen ``<think>`` trace, extracts the JSON object);
- **streaming compatibility** (``assemble_stream`` reassembles SSE token chunks);
- **typed failures** — it raises ``ProviderUnavailable`` / ``ProviderTimeout`` /
  ``ProviderProtocolError`` rather than ever fabricating an answer, so the calling module can
  fall back to its deterministic analyst.

Stdlib-only (``urllib``) — no new dependency; mirrors the proven Sprint-003 Qwen client.
"""
from __future__ import annotations

import json
import os
import re
import socket
import time
import urllib.request
from dataclasses import dataclass
from typing import Iterable

from .base import (
    ProviderError,
    ProviderProtocolError,
    ProviderTimeout,
    ProviderUnavailable,
    ReasoningRequest,
    ReasoningResponse,
)

_THINK = re.compile(r"<think>.*?</think>", re.DOTALL)


def strip_thinking(text: str) -> str:
    """Drop a leading ``<think>...</think>`` reasoning trace (Qwen-Thinking models)."""
    return _THINK.sub("", text or "").strip()


def extract_json(text: str) -> dict | None:
    """Parse the final JSON object out of a model completion (after stripping any think
    trace). Returns ``None`` if no JSON object is present — never raises."""
    text = strip_thinking(text)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        obj = json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return None
    return obj if isinstance(obj, dict) else None


def assemble_stream(chunks: Iterable[bytes | str]) -> str:
    """Reassemble HF SSE ``data:`` token chunks into the full generated text. Defensive:
    ignores keep-alives, ``[DONE]`` sentinels, and any unparseable line. Pure + testable so
    the streaming path has real coverage without a live endpoint."""
    out: list[str] = []
    for raw in chunks:
        line = (raw.decode("utf-8", "replace") if isinstance(raw, (bytes, bytearray)) else str(raw)).strip()
        if not line.startswith("data:"):
            continue
        payload = line[len("data:"):].strip()
        if not payload or payload == "[DONE]":
            continue
        try:
            obj = json.loads(payload)
        except json.JSONDecodeError:
            continue
        token = obj.get("token") or {}
        tok = token.get("text") if isinstance(token, dict) else None
        if tok is None:
            tok = obj.get("generated_text")
        if tok:
            out.append(str(tok))
    return "".join(out)


def _extract_generated(raw: bytes) -> str:
    """Pull ``generated_text`` from a non-streaming HF text-generation response body."""
    data = json.loads(raw.decode("utf-8"))
    if isinstance(data, list) and data:
        return str(data[0].get("generated_text") or "")
    if isinstance(data, dict):
        return str(data.get("generated_text") or "")
    return ""


def _extract_message(raw: bytes) -> str:
    """Pull the assistant content from a non-streaming OpenAI-compatible
    ``/v1/chat/completions`` response body (``choices[0].message.content``)."""
    data = json.loads(raw.decode("utf-8"))
    if isinstance(data, dict):
        choices = data.get("choices")
        if isinstance(choices, list) and choices:
            msg = choices[0].get("message") if isinstance(choices[0], dict) else None
            if isinstance(msg, dict):
                return str(msg.get("content") or "")
    return ""


def assemble_message_stream(chunks: Iterable[bytes | str]) -> str:
    """Reassemble OpenAI-compatible chat SSE ``data:`` chunks (``choices[].delta.content``) into
    the full message. Defensive: ignores keep-alives, ``[DONE]``, and unparseable lines — so the
    messages streaming path is testable without a live endpoint."""
    out: list[str] = []
    for raw in chunks:
        line = (raw.decode("utf-8", "replace") if isinstance(raw, (bytes, bytearray)) else str(raw)).strip()
        if not line.startswith("data:"):
            continue
        payload = line[len("data:"):].strip()
        if not payload or payload == "[DONE]":
            continue
        try:
            obj = json.loads(payload)
        except json.JSONDecodeError:
            continue
        choices = obj.get("choices") or []
        if choices and isinstance(choices[0], dict):
            delta = choices[0].get("delta") or {}
            tok = delta.get("content") if isinstance(delta, dict) else None
            if tok:
                out.append(str(tok))
    return "".join(out)


def _is_timeout(exc: BaseException | None) -> bool:
    return isinstance(exc, (TimeoutError, socket.timeout)) or "timed out" in str(exc or "").lower()


@dataclass
class RemoteReasoningProvider:
    """HF inference-endpoint client. Configure ``endpoint_url`` + a token (env) to activate;
    without them ``complete`` raises ``ProviderUnavailable`` and the council stays
    deterministic."""

    endpoint_url: str
    model: str = ""
    revision: str | None = None
    timeout: float = 30.0
    max_retries: int = 2
    api: str = "generate"                    # "generate" (raw TGI) | "messages" (OpenAI chat)
    token_env: tuple[str, ...] = ("HF_TOKEN", "HUGGINGFACE_HUB_TOKEN")
    backoff_cap: float = 2.0
    name: str = "remote-hf"

    def _token(self) -> str | None:
        for key in self.token_env:
            val = os.environ.get(key)
            if val:
                return val
        return None

    def _fetch(self, body: bytes, headers: dict, stream: bool, parse, parse_stream) -> tuple[str, int]:
        """Call the endpoint with capped-backoff retries on transient failures. Returns
        ``(text, attempts)``; raises ``ProviderTimeout``/``ProviderError`` when exhausted.
        Retries only NETWORK errors — protocol/parse errors are handled by the caller once. The
        response parser (``parse`` non-stream / ``parse_stream`` SSE) is API-specific."""
        last: BaseException | None = None
        for attempt in range(self.max_retries + 1):
            try:
                req = urllib.request.Request(self.endpoint_url, data=body, headers=headers)
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    text = parse_stream(resp) if stream else parse(resp.read())
                return text, attempt + 1
            except Exception as exc:  # noqa: BLE001 — network/endpoint error → maybe retry
                last = exc
                if attempt < self.max_retries:
                    time.sleep(min(self.backoff_cap, 0.5 * (2 ** attempt)))
        if _is_timeout(last):
            raise ProviderTimeout(f"endpoint timed out after {self.max_retries + 1} attempts") from last
        raise ProviderError(f"endpoint unreachable: {last}") from last

    def _request_body(self, request: ReasoningRequest):
        """Build the wire body + the matching (non-stream, stream) parsers for the configured
        serving API. ``generate`` is the raw TGI text-generation contract (unchanged, byte-
        identical); ``messages`` is the OpenAI-compatible chat contract, which lets the endpoint
        apply the served model's chat template server-side."""
        if self.api == "messages":
            body = json.dumps({
                "model": self.model or "tgi",
                "messages": [
                    {"role": "system", "content": request.system},
                    {"role": "user", "content": request.user},
                ],
                "temperature": request.temperature,
                "max_tokens": request.max_tokens,
                "stream": bool(request.stream),
            }).encode("utf-8")
            return body, _extract_message, assemble_message_stream
        body = json.dumps({
            "inputs": f"<|system|>\n{request.system}\n<|user|>\n{request.user}",
            "parameters": {
                "temperature": request.temperature,
                "max_new_tokens": request.max_tokens,
                "return_full_text": False,
            },
            "stream": bool(request.stream),
        }).encode("utf-8")
        return body, _extract_generated, assemble_stream

    def complete(self, request: ReasoningRequest) -> ReasoningResponse:
        token = self._token()
        if not self.endpoint_url or not token:
            raise ProviderUnavailable("reasoning endpoint or token is not configured")
        body, parse, parse_stream = self._request_body(request)
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

        t0 = time.perf_counter()
        text, attempts = self._fetch(body, headers, request.stream, parse, parse_stream)
        latency_ms = (time.perf_counter() - t0) * 1000.0

        text = strip_thinking(text)
        structured = extract_json(text) if request.response_format == "json" else None
        if request.response_format == "json" and structured is None:
            raise ProviderProtocolError("model response was not a valid JSON object")
        return ReasoningResponse(
            text=text, model=self.model, revision=self.revision, structured=structured,
            diagnostics={
                "provider": self.name, "attempts": attempts, "api": self.api,
                "latency_ms": round(latency_ms, 2), "streamed": bool(request.stream),
                "model": self.model, "revision": self.revision,
            },
        )

    # ----------------------------------------------------------------------- #
    # Served-model identity probe — VERIFICATION ONLY (never on the hot path).
    # ----------------------------------------------------------------------- #
    def _info_url(self) -> str:
        """Derive the TGI ``/info`` route (root-relative) from the configured inference URL, so a
        raw ``generate`` endpoint can still report which model it loaded."""
        from urllib.parse import urlsplit, urlunsplit

        parts = urlsplit(self.endpoint_url)
        return urlunsplit((parts.scheme, parts.netloc, "/info", "", ""))

    def probe_served_model(self) -> dict:
        """Report the model the endpoint is **actually serving** — the missing evidence for
        "the endpoint is Mistral, not some other model". Off the hot path; best-effort; never raises.

        * ``messages`` API — the OpenAI-compatible completion echoes the served model in the
          top-level ``model`` field; that is authoritative and free (one 1-token call).
        * ``generate`` API — raw TGI completions carry no model id, so we GET the standard TGI
          ``/info`` route (``model_id``). If the endpoint shape doesn't expose it we report
          ``served_model=None`` with a reason rather than guessing.

        Returns ``served_model`` / ``source`` / ``reachable`` / ``latency_ms`` (+ ``detail`` on
        failure). The caller compares ``served_model`` against the configured model id."""
        token = self._token()
        if not self.endpoint_url or not token:
            return {"served_model": None, "source": "not_configured", "reachable": None,
                    "endpoint_configured": bool(self.endpoint_url), "hf_token_present": bool(token)}
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        t0 = time.perf_counter()
        try:
            if self.api == "messages":
                body = json.dumps({
                    "model": self.model or "tgi",
                    "messages": [{"role": "user", "content": "ping"}],
                    "max_tokens": 1, "stream": False,
                }).encode("utf-8")
                req = urllib.request.Request(self.endpoint_url, data=body, headers=headers)
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                served = data.get("model") if isinstance(data, dict) else None
                source = "chat_completion_model_field"
            else:
                req = urllib.request.Request(self._info_url(), headers=headers)  # GET
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                served = data.get("model_id") if isinstance(data, dict) else None
                source = "tgi_info_endpoint"
            return {"served_model": served or None, "source": source, "reachable": True,
                    "latency_ms": round((time.perf_counter() - t0) * 1000.0, 2)}
        except Exception as exc:  # noqa: BLE001 — report, never raise
            return {"served_model": None, "source": "probe_failed", "reachable": False,
                    "detail": f"{type(exc).__name__}: {str(exc)[:160]}",
                    "latency_ms": round((time.perf_counter() - t0) * 1000.0, 2)}
