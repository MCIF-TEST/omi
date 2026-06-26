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
    """Pull ``generated_text`` from a non-streaming HF response body."""
    data = json.loads(raw.decode("utf-8"))
    if isinstance(data, list) and data:
        return str(data[0].get("generated_text") or "")
    if isinstance(data, dict):
        return str(data.get("generated_text") or "")
    return ""


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
    token_env: tuple[str, ...] = ("HF_TOKEN", "HUGGINGFACE_HUB_TOKEN")
    backoff_cap: float = 2.0
    name: str = "remote-hf-qwen"

    def _token(self) -> str | None:
        for key in self.token_env:
            val = os.environ.get(key)
            if val:
                return val
        return None

    def _fetch(self, body: bytes, headers: dict, stream: bool) -> tuple[str, int]:
        """Call the endpoint with capped-backoff retries on transient failures. Returns
        ``(text, attempts)``; raises ``ProviderTimeout``/``ProviderError`` when exhausted.
        Retries only NETWORK errors — protocol/parse errors are handled by the caller once."""
        last: BaseException | None = None
        for attempt in range(self.max_retries + 1):
            try:
                req = urllib.request.Request(self.endpoint_url, data=body, headers=headers)
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    text = assemble_stream(resp) if stream else _extract_generated(resp.read())
                return text, attempt + 1
            except Exception as exc:  # noqa: BLE001 — network/endpoint error → maybe retry
                last = exc
                if attempt < self.max_retries:
                    time.sleep(min(self.backoff_cap, 0.5 * (2 ** attempt)))
        if _is_timeout(last):
            raise ProviderTimeout(f"endpoint timed out after {self.max_retries + 1} attempts") from last
        raise ProviderError(f"endpoint unreachable: {last}") from last

    def complete(self, request: ReasoningRequest) -> ReasoningResponse:
        token = self._token()
        if not self.endpoint_url or not token:
            raise ProviderUnavailable("reasoning endpoint or token is not configured")
        body = json.dumps({
            "inputs": f"<|system|>\n{request.system}\n<|user|>\n{request.user}",
            "parameters": {
                "temperature": request.temperature,
                "max_new_tokens": request.max_tokens,
                "return_full_text": False,
            },
            "stream": bool(request.stream),
        }).encode("utf-8")
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

        t0 = time.perf_counter()
        text, attempts = self._fetch(body, headers, request.stream)
        latency_ms = (time.perf_counter() - t0) * 1000.0

        text = strip_thinking(text)
        structured = extract_json(text) if request.response_format == "json" else None
        if request.response_format == "json" and structured is None:
            raise ProviderProtocolError("model response was not a valid JSON object")
        return ReasoningResponse(
            text=text, model=self.model, revision=self.revision, structured=structured,
            diagnostics={
                "provider": self.name, "attempts": attempts,
                "latency_ms": round(latency_ms, 2), "streamed": bool(request.stream),
                "model": self.model, "revision": self.revision,
            },
        )
