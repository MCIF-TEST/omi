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
import logging
import os
import re
import socket
import time
import urllib.error
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

# --------------------------------------------------------------------------- #
# Temporary forensic capture — OMI_FORENSIC_CAPTURE=true logs the EXACT HF wire
# request + the raw response, unparsed. Off by default: when the flag is unset or
# false, none of this runs and the transport behaves byte-identically. Logging
# only — it never touches the request, the response, or control flow.
# --------------------------------------------------------------------------- #
_forensic_log = logging.getLogger("omi.reasoning.forensic")
_SECRET_HEADERS = {"authorization", "set-cookie", "cookie", "x-api-key", "api-key"}
_TOKEN_RE = re.compile(r"(hf_[A-Za-z0-9]+|Bearer\s+\S+)")


def forensic_on() -> bool:
    """True only when OMI_FORENSIC_CAPTURE is explicitly enabled. Read at call time."""
    return os.environ.get("OMI_FORENSIC_CAPTURE", "").strip().lower() in ("1", "true", "yes", "on")


def _emit_forensic(text: str) -> None:
    """Emit a forensic banner so it ALWAYS reaches the platform logs.

    Root cause of the missing banners in production: the previous implementation used
    ``_forensic_log.info(...)``. In production ``OMI_LOG_LEVEL`` is above INFO (e.g. WARNING),
    so ``_configure_logging()`` sets the root level above INFO and every INFO record — including
    these banners — is dropped before any handler sees it. The flag was on and the code was
    deployed, but the framework silently suppressed the output.

    The fix bypasses the logging level/formatter/handler stack entirely: write straight to
    stdout with an explicit flush. Render (and every other platform) captures process stdout,
    so the banner is visible whenever ``OMI_FORENSIC_CAPTURE`` is set, at any log level.
    A second (best-effort) emit at WARNING keeps the banner in the structured JSON log for
    environments that scrape the logger instead of raw stdout; it is never relied upon and can
    never raise. Emission must never perturb the request path, so everything is guarded."""
    try:
        print(text, flush=True)
    except Exception:  # noqa: BLE001 — forensic emission must never break the request
        pass
    try:
        _forensic_log.warning("%s", text)
    except Exception:  # noqa: BLE001
        pass


def _redact(text: str) -> str:
    """Scrub anything token-shaped. The wire body carries no secrets (the token rides in headers),
    but this is defensive per 'redact secrets only'."""
    return _TOKEN_RE.sub("<redacted>", text or "")


def _safe_headers(headers) -> dict:
    out = {}
    try:
        for k, v in dict(headers).items():
            out[k] = "<redacted>" if k.lower() in _SECRET_HEADERS else v
    except Exception:  # noqa: BLE001
        return {}
    return out


def _log_hf_request(*, endpoint_url: str, model: str, prompt_hash: str | None,
                    package_hash: str | None, body: bytes) -> None:
    decoded = body.decode("utf-8", "replace") if isinstance(body, (bytes, bytearray)) else str(body)
    _emit_forensic(
        "\n=====================\nHF REQUEST\n=====================\n"
        f"Endpoint URL : {endpoint_url}\nModel ID     : {model or '(unset)'}\n"
        f"Prompt hash  : {prompt_hash or 'n/a'}\nPackage hash : {package_hash or 'n/a'}\n"
        f"Request body : {_redact(decoded)}")


def _log_hf_response(status, headers, raw_body) -> None:
    body = raw_body.decode("utf-8", "replace") if isinstance(raw_body, (bytes, bytearray)) else str(raw_body)
    _emit_forensic(
        "\n=====================\nHF RESPONSE\n=====================\n"
        f"HTTP status : {status}\nHeaders     : {_safe_headers(headers)}\nRaw body    : {body}")


_REQUEST_ID_HEADERS = ("x-request-id", "x-inference-id", "x-amzn-requestid", "x-amzn-request-id",
                       "x-request-context", "request-id")


def _capture_endpoint_meta(capture: dict, resp, raw_body) -> None:
    """Record response-side endpoint metadata — HTTP status, the endpoint request id, and token
    usage — into the capture sidecar for the AI Investigation Runtime. Additive + best-effort +
    never raises; only invoked when a capture dict is supplied, so the no-capture path is
    byte-identical. Pure observability — it never alters the request, the response, or control flow."""
    try:
        capture["response_status"] = getattr(resp, "status", None) or resp.getcode()
    except Exception:  # noqa: BLE001
        pass
    try:
        headers = getattr(resp, "headers", None)
        if headers is not None:
            for key in _REQUEST_ID_HEADERS:
                val = headers.get(key)
                if val:
                    capture["endpoint_request_id"] = val
                    break
    except Exception:  # noqa: BLE001
        pass
    try:
        text = raw_body.decode("utf-8", "replace") if isinstance(raw_body, (bytes, bytearray)) else str(raw_body)
        obj = json.loads(text)
        usage = obj.get("usage") if isinstance(obj, dict) else None
        if isinstance(usage, dict):
            capture["usage"] = {
                "prompt_tokens": usage.get("prompt_tokens"),
                "completion_tokens": usage.get("completion_tokens"),
                "total_tokens": usage.get("total_tokens"),
            }
    except Exception:  # noqa: BLE001
        pass


def strip_thinking(text: str) -> str:
    """Drop a leading ``<think>...</think>`` reasoning trace (Qwen-Thinking models)."""
    return _THINK.sub("", text or "").strip()


_FENCE_RE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.IGNORECASE)


def _strip_code_fences(text: str) -> str:
    """Drop a surrounding markdown code fence (```json … ```), if present."""
    return _FENCE_RE.sub("", text or "").strip()


def _repair_truncated_json(s: str) -> dict | None:
    """Best-effort salvage of a JSON object that was CUT OFF (the model hit the output-token cap).

    A truncated comprehensive assessment loses every per-account result it already produced when a
    strict parse fails. This closes the structures that were still open — an unterminated string, and
    any unclosed arrays/objects — after trimming a dangling trailing token, so the accounts that DID
    arrive survive. Returns the parsed object, or ``None`` if it still cannot be made valid (never
    raises). It only ever recovers a PREFIX of what the model emitted; it never invents content."""
    stack: list[str] = []
    in_str = False
    escape = False
    for ch in s:
        if escape:
            escape = False
            continue
        if in_str:
            if ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch in "{[":
            stack.append("}" if ch == "{" else "]")
        elif ch in "}]":
            if stack:
                stack.pop()
    # Try progressively shorter prefixes: close what's open, and on failure trim back to the last
    # element boundary (a comma / closing brace at the top of the truncated tail) and retry. Bounded.
    for _ in range(6):
        candidate = s
        if in_str:
            candidate += '"'
        candidate = candidate.rstrip().rstrip(",")
        candidate += "".join(reversed(stack))
        try:
            obj = json.loads(candidate)
            return obj if isinstance(obj, dict) else None
        except json.JSONDecodeError:
            pass
        # Trim the dangling tail back to the last complete element, then re-close and retry.
        cut = max(s.rfind("},"), s.rfind("],"), s.rfind('",'))
        if cut <= 0:
            break
        trimmed = s[: cut + 1]
        # Recompute the open-structure stack for the trimmed prefix.
        stack, in_str, escape = [], False, False
        for ch in trimmed:
            if escape:
                escape = False
                continue
            if in_str:
                if ch == "\\":
                    escape = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch in "{[":
                stack.append("}" if ch == "{" else "]")
            elif ch in "}]":
                if stack:
                    stack.pop()
        s = trimmed
    return None


def extract_json(text: str) -> dict | None:
    """Parse the final JSON object out of a model completion (after stripping any think trace and any
    markdown code fence). Returns ``None`` if no JSON object can be recovered — never raises.

    Robust by design so a good-faith model response is not lost to a formatting quirk: it tries a
    direct parse of the outermost ``{ … }`` first, then falls back to salvaging a TRUNCATED object
    (the model hit the output-token cap) so the per-account results that DID arrive are preserved."""
    text = _strip_code_fences(strip_thinking(text))
    start = text.find("{")
    if start < 0:
        return None
    body = text[start:]
    end = body.rfind("}")
    if end > 0:
        try:
            obj = json.loads(body[: end + 1])
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            pass
    # Direct parse failed (most often a truncated response) — attempt a bounded repair.
    return _repair_truncated_json(body)


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
    # Optional forensic sidecar. When a dict is supplied, ``complete`` records the EXACT wire body,
    # the final system/user prompt, the raw response body, the served model id, and the pre-Governor
    # raw text into it. Off the production hot path (None by default) — pure observability, never
    # alters the request, the response, or control flow.
    capture: dict | None = None
    # Provenance for the forensic HF-REQUEST log (OMI_FORENSIC_CAPTURE). Set by the analyst
    # transport; ``None`` on bare probes -> logged as "n/a". Never affects the request.
    prompt_hash: str | None = None
    package_hash: str | None = None

    def _token(self) -> str | None:
        for key in self.token_env:
            val = os.environ.get(key)
            if val:
                return val
        return None

    def _target_url(self) -> str:
        """The URL to POST to. The ``messages`` (OpenAI-compatible) API lives at
        ``/v1/chat/completions`` on HF TGI / vLLM inference endpoints; the raw ``generate`` API uses
        the endpoint root (unchanged). Idempotent: if the operator already pointed the URL at the chat
        route, it is left as-is — so both a bare endpoint URL and a full chat-completions URL work."""
        url = self.endpoint_url
        if self.api == "messages":
            base = url.split("?", 1)[0].rstrip("/")
            return base if base.endswith("/v1/chat/completions") else base + "/v1/chat/completions"
        return url

    def _fetch(self, body: bytes, headers: dict, stream: bool, parse, parse_stream) -> tuple[str, int]:
        """Call the endpoint with capped-backoff retries on transient failures. Returns
        ``(text, attempts)``; raises ``ProviderTimeout``/``ProviderError`` when exhausted.
        Retries only NETWORK errors — protocol/parse errors are handled by the caller once. The
        response parser (``parse`` non-stream / ``parse_stream`` SSE) is API-specific."""
        last: BaseException | None = None
        forensic = forensic_on()
        target_url = self._target_url()
        for attempt in range(self.max_retries + 1):
            try:
                req = urllib.request.Request(target_url, data=body, headers=headers)
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    if stream:
                        text = parse_stream(resp)
                    else:
                        raw = resp.read()
                        if forensic:  # log the RAW body exactly as returned, BEFORE any parsing
                            _log_hf_response(getattr(resp, "status", None) or resp.getcode(),
                                             resp.headers, raw)
                        if self.capture is not None:  # additive endpoint metadata for the AI runtime
                            _capture_endpoint_meta(self.capture, resp, raw)
                        text = parse(raw)
                return text, attempt + 1
            except urllib.error.HTTPError as he:  # 4xx/5xx — the endpoint DID respond with a body
                last = he
                # Record the HTTP status even on failure so the forensic trace shows WHY a call fell
                # back (e.g. 404 wrong route, 401 auth, 503 endpoint initializing) — not just null.
                if self.capture is not None:
                    self.capture["response_status"] = he.code
                if forensic:
                    try:
                        _log_hf_response(he.code, he.headers, he.read())
                    except Exception:  # noqa: BLE001 — logging must never mask the error
                        pass
                if attempt < self.max_retries:
                    time.sleep(min(self.backoff_cap, 0.5 * (2 ** attempt)))
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

            def parse(raw: bytes) -> str:
                if self.capture is not None:
                    self.capture["raw_response_body"] = raw.decode("utf-8", "replace")[:12000]
                    try:
                        self.capture["served_model"] = json.loads(raw).get("model")
                    except Exception:  # noqa: BLE001
                        self.capture["served_model"] = None
                return _extract_message(raw)

            return body, parse, assemble_message_stream
        body = json.dumps({
            "inputs": f"<|system|>\n{request.system}\n<|user|>\n{request.user}",
            "parameters": {
                "temperature": request.temperature,
                "max_new_tokens": request.max_tokens,
                "return_full_text": False,
            },
            "stream": bool(request.stream),
        }).encode("utf-8")

        def parse_gen(raw: bytes) -> str:
            if self.capture is not None:
                self.capture["raw_response_body"] = raw.decode("utf-8", "replace")[:12000]
                self.capture["served_model"] = None  # raw TGI /generate does not echo the model id
            return _extract_generated(raw)

        return body, parse_gen, assemble_stream

    def complete(self, request: ReasoningRequest) -> ReasoningResponse:
        token = self._token()
        if not self.endpoint_url or not token:
            raise ProviderUnavailable("reasoning endpoint or token is not configured")
        body, parse, parse_stream = self._request_body(request)
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        if self.capture is not None:
            self.capture["endpoint_url"] = self._target_url()
            self.capture["endpoint_api"] = self.api
            self.capture["configured_model"] = self.model
            self.capture["revision"] = self.revision
            self.capture["request_wire_body"] = body.decode("utf-8", "replace")[:12000]
            self.capture["final_prompt_system"] = request.system
            self.capture["final_prompt_user"] = request.user

        if forensic_on():  # temporary forensic capture — log the EXACT request before sending
            _log_hf_request(endpoint_url=self.endpoint_url, model=self.model,
                            prompt_hash=self.prompt_hash, package_hash=self.package_hash, body=body)

        t0 = time.perf_counter()
        text, attempts = self._fetch(body, headers, request.stream, parse, parse_stream)
        latency_ms = (time.perf_counter() - t0) * 1000.0
        if self.capture is not None:
            # The RAW model text, BEFORE thinking-strip / JSON-extract / Governor.
            self.capture["raw_text_pre_processing"] = (text or "")[:12000]
            self.capture["attempts"] = attempts
            self.capture["latency_ms"] = round(latency_ms, 2)

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
