"""Omi Analyst — production wiring into app/reasoning (OMI_ANALYST_PRODUCTION_WIRING_V1).

Connects the completed Omi Analyst implementation (``ml/analyst/omi_analyst``) into the
backend as an OPTIONAL, feature-flagged, async, cached reasoning capability. Strictly
additive — exactly like the Phase-7 LLM layer, the Analyst:

  * is OFF by default (``settings.analyst_enabled = False``),
  * never makes a detection decision, never recomputes a score, never runs in the scan
    hot path, and is never required for the product to work,
  * does NOT touch detectors, scoring, OmiScore, or the existing commentary path.

The completed implementation lives in the decoupled ``ml/`` tree and is **lazily
imported only when the feature is enabled**, so the default (off) path imports nothing
from ``ml/`` and cannot affect production or the test suite. Any failure (feature off,
``ml/`` absent, model unreachable, invalid output) degrades to ``None`` — the caller
simply has no assessment, never an error in the request path.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.config import Settings, get_settings
# Module scope for the same reason as get_session below: this module runs work inside the
# background pool, which absorbs exceptions, so a sink that is not visible to a nested scope is
# a sink that silently does nothing.
from app.core.observability import capture_exception
# Module scope, not inside a function: this module runs closures on the background pool, and a
# function-level import is invisible inside one (see CLAUDE.md, "A bug class worth knowing").
# Module scope: this module runs closures on the background pool, where a
# function-level import is invisible (see CLAUDE.md, "A bug class worth knowing").
from app.reasoning.batch_plan import BATCH_SIZE, plan_batches
from app.reasoning.floor_reason import (
    base_reason as _floor_base_reason,
    classify_floor as _classify_floor,
    is_retryable as _floor_is_retryable,
)
# Module scope on purpose. The batched generation's progressive persist (_generate_batched ->
# _persist_progress) calls get_session(); when this import lived only inside generate_and_persist it
# was a LOCAL binding there, so the nested closure resolved the name against module globals, found
# nothing, and every batched run died with NameError on its first persist — silently, inside the
# background pool. The effect: NO investigation over one batch of accounts ever produced an
# assessment; the client just polled until it timed out. Keep this at module level.
from app.storage.db import get_session

logger = logging.getLogger("omi.reasoning.analyst")

# Where the cached structured assessment lives inside Investigation.payload_json.
CACHE_KEY = "analyst_assessment_v1"
# How many batches a selection large enough to need batching is split into. A COUNT, not a size:
# see `_split_batches` for why. Overridable per deployment via OMI_ANALYST_BATCH_COUNT, which is the
# lever to reach for if per-batch latency ever starts racing OMI_ANALYST_TIMEOUT_SECONDS — more
# batches means fewer accounts in each one.
DEFAULT_ANALYST_BATCHES = 4
# The hard ceiling on how many accounts may ride in ONE model request, whatever the batch count says.
#
# This is the guard that the fixed batch count quietly removed. Before it, `analyst_batch_accounts`
# was a per-request SIZE and therefore bounded the request; turning it into a threshold made the
# batch size scale with the selection instead, so a 197-account scan became four requests of ~50.
# Measured on the deployment: 25 per request works, ~50 per request fails within about 30 seconds
# with output that does not validate. 35 is the conservative middle, and it keeps the promised
# four-batch shape for every selection up to 140 accounts, which covers the operator cap of 150.
# Above that the count grows rather than the request, because a request nobody can serve returns
# nothing for every account inside it.
MAX_ACCOUNTS_PER_REQUEST = 35
# Repo root: apps/api/app/reasoning/analyst.py -> parents[4] == repo root.
_REPO_ROOT = Path(__file__).resolve().parents[4]
_ML_ANALYST_PATH = str(_REPO_ROOT / "ml" / "analyst")
_impl_cache: Any | None = None
_impl_failed = False


def analyst_enabled(settings: Settings | None = None) -> bool:
    settings = settings or get_settings()
    return bool(getattr(settings, "analyst_enabled", False))


def _qwen_transport(endpoint: str, *, timeout: float, max_retries: int, revision: str | None,
                    api: str = "generate", model: str | None = None, capture: dict | None = None,
                    prompt_hash: str | None = None, package_hash: str | None = None):
    """The ONE Qwen HTTP transport (Sprint 017). The production analyst's model call goes through
    the constitutional ``RemoteReasoningProvider`` — the same HF client the council uses — instead
    of a second bespoke HTTP implementation. ``api`` selects the raw ``generate`` or OpenAI-
    compatible ``messages`` serving contract; ``model`` names the served model in the request body
    (so a dedicated endpoint's logs attribute the call correctly instead of the generic ``tgi``).
    Returns the raw generated text, or None on any failure so the analyst degrades to its
    deterministic provider. Each call is logged at INFO so Render logs show the outbound model
    request and its outcome."""
    from app.reasoning.model_providers import ReasoningRequest, RemoteReasoningProvider

    provider = RemoteReasoningProvider(
        endpoint_url=endpoint, model=model or "", timeout=timeout, max_retries=max_retries,
        revision=revision, api=api, capture=capture, prompt_hash=prompt_hash, package_hash=package_hash)

    def _call(system: str, user: str, config: Any) -> str | None:
        t0 = time.perf_counter()
        try:
            resp = provider.complete(ReasoningRequest(
                system=system, user=user, response_format="text",
                temperature=getattr(config, "temperature", 0.2),
                max_tokens=getattr(config, "max_new_tokens", 1024), revision=revision,
            ))
            dt = (time.perf_counter() - t0) * 1000.0
            logger.info("analyst.model_call: OK endpoint=%s api=%s model=%s chars=%d latency_ms=%.0f",
                        _redact_endpoint(endpoint), api, model or "tgi", len(resp.text or ""), dt)
            return resp.text
        except Exception as exc:  # noqa: BLE001 — provider failure -> deterministic fallback
            dt = (time.perf_counter() - t0) * 1000.0
            # Record the exact endpoint failure (class + message + real elapsed) into the forensic
            # capture so the PERSISTED investigation trace self-diagnoses (timeout vs connection-refused
            # vs DNS/TLS) without needing the Render log. Redacted of the endpoint host; message only.
            if capture is not None:
                capture["endpoint_error"] = f"{type(exc).__name__}: {str(exc)[:200]}"
                capture["endpoint_latency_ms"] = round(dt, 2)
            logger.warning("analyst.model_call: FAILED endpoint=%s api=%s model=%s latency_ms=%.0f "
                           "err=%s: %s -> deterministic fallback", _redact_endpoint(endpoint), api,
                           model or "tgi", dt, type(exc).__name__, str(exc)[:160])
            return None

    return _call


def _redact_endpoint(url: str | None) -> str:
    """Host-only view of the endpoint URL for logs (never the full path/query)."""
    if not url:
        return "-"
    try:
        from urllib.parse import urlsplit
        return urlsplit(url).netloc or url[:40]
    except Exception:  # noqa: BLE001
        return url[:40]


def reasoning_provider(settings: Settings | None = None) -> str:
    """The active reasoning provider — ``"openrouter"`` or ``"huggingface"``. Selection is configuration,
    not architecture: both satisfy the same ReasoningProvider seam.

    OpenRouter-first auto-preference: if OpenRouter is FULLY configured (a preset or model is set AND
    ``OPENROUTER_API_KEY`` is present in the environment) we use OpenRouter even when ``analyst_provider``
    was left at its ``huggingface`` default. This closes the most common production misconfiguration —
    ``OPENROUTER_API_KEY`` set but ``OMI_ANALYST_PROVIDER`` never flipped — which otherwise silently served
    via the deprecated HuggingFace path and sent ZERO OpenRouter requests. An EXPLICIT
    ``OMI_ANALYST_PROVIDER=huggingface`` still wins (it is honored verbatim below when no OpenRouter preset/
    model is configured; a deployment that wants HF simply must not also configure an OpenRouter preset)."""
    settings = settings or get_settings()
    configured = str(getattr(settings, "analyst_provider", "huggingface") or "huggingface").strip().lower()
    if configured == "openrouter":
        return "openrouter"
    or_configured = bool(getattr(settings, "openrouter_preset", None)
                         or getattr(settings, "openrouter_model", None))
    if or_configured and os.environ.get("OPENROUTER_API_KEY"):
        return "openrouter"
    return configured


def reasoning_provider_name(settings: Settings | None = None) -> str:
    """The model-backed provider label recorded on a governed ruling. HF keeps its historical label so
    existing traces/tests are unchanged; OpenRouter records its own."""
    return "openrouter-omi-analyst-v1" if reasoning_provider(settings) == "openrouter" else "qwen-omi-analyst-v1"


def _provider_token_present(settings: Settings | None = None) -> bool:
    """Whether the SELECTED provider's credential is present in the environment (never in settings). HF:
    HF_TOKEN / HUGGINGFACE_HUB_TOKEN. OpenRouter: OPENROUTER_API_KEY."""
    if reasoning_provider(settings) == "openrouter":
        return bool(os.environ.get("OPENROUTER_API_KEY"))
    return bool(os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACE_HUB_TOKEN"))


def _openrouter_transport(settings: Settings, *, timeout: float, max_retries: int,
                          model: str | None = None, capture: dict | None = None,
                          prompt_hash: str | None = None, package_hash: str | None = None,
                          canonical_schema: dict | None = None):
    """The ONE OpenRouter transport — build the configured ``OpenRouterReasoningProvider`` (preset or
    direct mode) and return the same ``_call(system, user, config)`` closure shape the HF transport uses,
    so the runtime is provider-agnostic. Returns raw generated text, or None on any failure (→ Floor).
    Records the exact endpoint failure + latency into the forensic capture. Never sends a local
    system / base prompt on the OpenRouter wire — the operator's dashboard Preset owns the Master
    Analyst Protocol; the request carries only the investigation evidence package."""
    from app.reasoning.model_providers import OpenRouterReasoningProvider
    from app.reasoning.model_providers.openrouter import OPENROUTER_URL

    master_hash = None
    try:
        from app.reasoning.prompts.master_protocol import compile_master_analyst_protocol
        master_hash = compile_master_analyst_protocol(getattr(settings, "analyst_model_id", None))["hash"]
    except Exception:  # noqa: BLE001 — provenance is best-effort, never blocks the call
        master_hash = None

    provider = OpenRouterReasoningProvider(
        base_url=str(getattr(settings, "openrouter_base_url", OPENROUTER_URL) or OPENROUTER_URL),
        # OpenRouter's own model slug ONLY — never the HF ``pp.model_id``. In preset mode a null model
        # means "use the preset's model" (model_ref -> "@preset/<slug>"); in direct mode it is required.
        model=getattr(settings, "openrouter_model", None),
        preset=getattr(settings, "openrouter_preset", None),
        canonical_schema=canonical_schema,
        structured_output=bool(getattr(settings, "openrouter_structured_output", True)),
        referer=getattr(settings, "openrouter_referer", None),
        title=getattr(settings, "openrouter_title", None),
        reasoning_effort=getattr(settings, "openrouter_reasoning_effort", None),
        timeout=timeout, max_retries=max_retries, capture=capture,
        prompt_hash=prompt_hash, package_hash=package_hash, master_prompt_hash=master_hash)

    def _call(system: str, user: str, config: Any) -> str | None:
        from app.reasoning.model_providers import ReasoningRequest
        from app.reasoning.model_providers.remote import extract_json

        req = ReasoningRequest(
            system=system, user=user, response_format="text",
            temperature=getattr(config, "temperature", 0.2),
            max_tokens=getattr(config, "max_new_tokens", 1024))
        preset_label = getattr(settings, "openrouter_preset", None) or "-"
        text: str | None = None
        # One extra attempt as a SAFEGUARD: if a 200 reply yields no usable JSON (a rare empty/garbled
        # response), try once more. We do NOT retry a TRUNCATED reply (finish_reason=length) — the
        # extractor already salvaged what arrived and a retry would just truncate again at the same cap.
        for attempt in range(2):
            t0 = time.perf_counter()
            try:
                resp = provider.complete(req)
                dt = (time.perf_counter() - t0) * 1000.0
                text = resp.text
                parsed_ok = extract_json(text or "") is not None
                logger.info("analyst.model_call: OK provider=openrouter preset=%s model_ref=%s chars=%d "
                            "latency_ms=%.0f parsed=%s attempt=%d", preset_label,
                            provider._model_ref(), len(text or ""), dt, parsed_ok, attempt + 1)
                if parsed_ok:
                    return text
                truncated = (capture or {}).get("finish_reason") == "length"
                if truncated or attempt == 1:
                    return text  # let the extractor's salvage / the Floor take it from here
                logger.warning("analyst.model_call: 200 with no parseable JSON (finish=%s) — retrying once",
                               (capture or {}).get("finish_reason"))
                continue
            except Exception as exc:  # noqa: BLE001 — provider failure -> deterministic fallback
                dt = (time.perf_counter() - t0) * 1000.0
                if capture is not None:
                    capture["endpoint_error"] = f"{type(exc).__name__}: {str(exc)[:200]}"
                    capture["endpoint_latency_ms"] = round(dt, 2)
                logger.warning("analyst.model_call: FAILED provider=openrouter preset=%s latency_ms=%.0f "
                               "err=%s: %s -> deterministic fallback", preset_label, dt,
                               type(exc).__name__, str(exc)[:160])
                return None
        return text

    return _call


def _reasoning_transport(settings: Settings, endpoint: str | None, *, timeout: float, max_retries: int,
                         revision: str | None, api: str, model: str | None, capture: dict | None,
                         prompt_hash: str | None, package_hash: str | None,
                         canonical_schema: dict | None = None):
    """Select the transport by ``analyst_provider`` and return a ``_call(system, user, config)`` closure.
    ``huggingface`` (default) returns the existing HF transport UNCHANGED (byte-identical); ``openrouter``
    returns the OpenRouter transport. The runtime calls this and never learns which gateway served."""
    if reasoning_provider(settings) == "openrouter":
        return _openrouter_transport(settings, timeout=timeout, max_retries=max_retries, model=model,
                                     capture=capture, prompt_hash=prompt_hash, package_hash=package_hash,
                                     canonical_schema=canonical_schema)
    return _qwen_transport(endpoint, timeout=timeout, max_retries=max_retries, revision=revision, api=api,
                           model=model, capture=capture, prompt_hash=prompt_hash, package_hash=package_hash)


def _impl():
    """Lazily import the completed ``omi_analyst`` package. Cached; never raises."""
    global _impl_cache, _impl_failed
    if _impl_cache is not None:
        return _impl_cache
    if _impl_failed:
        return None
    try:
        if _ML_ANALYST_PATH not in sys.path:
            sys.path.append(_ML_ANALYST_PATH)  # append: never shadow app modules
        import omi_analyst  # type: ignore

        _impl_cache = omi_analyst
        return _impl_cache
    except Exception:  # noqa: BLE001 — ml/ absent or import error → feature unavailable
        logger.warning("omi_analyst implementation not importable; analyst disabled", exc_info=True)
        _impl_failed = True
        return None


def available(settings: Settings | None = None) -> bool:
    """True only when the flag is on AND the implementation imported."""
    return analyst_enabled(settings) and _impl() is not None


# --------------------------------------------------------------------------- #
# Projection: Investigation payload -> Evidence Bundle (comment_section grain)
# --------------------------------------------------------------------------- #
def _ref(value: str) -> str:
    """Pseudonymous, stable reference — the analyst never sees a raw handle/PII."""
    return "sub_" + hashlib.sha256((value or "").encode("utf-8")).hexdigest()[:12]


def _coordination_from_payload(payload: dict) -> dict:
    clusters_in = ((payload.get("video") or {}).get("clusters")) or payload.get("clusters") or []
    methods: list[str] = []
    clusters: list[dict] = []
    for cl in clusters_in:
        m = cl.get("method")
        if m and m not in methods:
            methods.append(m)
        members = cl.get("members")
        clusters.append({"method": m, "members": len(members) if isinstance(members, list) else members})
    return {
        "methods": methods,
        "clusters": clusters,
        "coordination_score": payload.get("coordination_score"),
        "single_axis_capped": bool(payload.get("single_axis_capped", False)),
    }


def _components_from_payload(payload: dict, impl) -> list[dict]:
    """Fold the top flagged commenters into compact component descriptors (no
    per-commenter model call) so the investigation summary can synthesize across them."""
    commenters = ((payload.get("video") or {}).get("commenters")) or []
    flagged = [c for c in commenters if c.get("tier") in ("moderate", "elevated", "high")]
    flagged.sort(key=lambda c: -(c.get("overall_probability") or 0))
    out = []
    for c in flagged[:5]:
        tier = c.get("tier")
        verdict = "likely_inauthentic" if tier in ("elevated", "high") else "mixed"
        out.append({
            "grain": "commenter", "ref": _ref(c.get("handle") or "?"),
            "verdict": verdict, "suspicion_tier": tier,
            "suspicion_probability": c.get("overall_probability") or 0.0,
            "headline": (c.get("summary") or c.get("intent_label") or "")[:160],
        })
    return out


def _commenters_by_author_ref(payload: dict) -> dict[str, dict]:
    """Reverse map: the pseudonymous account ref the model reasons over (``_ref(handle)``) -> the real
    commenter row. Lets an aliased per-account assessment be joined back to identity + the engine numbers
    it must echo. Covers the video commenters + a focus account when present."""
    out: dict[str, dict] = {}
    video = payload.get("video") or {}
    for c in (video.get("commenters") or []):
        handle = c.get("handle")
        if handle:
            out[_ref(handle)] = c
    focus = payload.get("focus_account") or video.get("focus_account")
    if isinstance(focus, dict) and focus.get("handle"):
        out.setdefault(_ref(focus["handle"]), focus)
    return out


def _served_model_matches(served: str | None, expected: str | None) -> bool | None:
    """Whether the model OpenRouter ACTUALLY served matches the one we expect (GPT-5 Mini). Returns None
    when the check is not applicable — no expectation configured, or no served model reported (e.g. the
    Floor path) — so "unknown" is never conflated with "mismatch". Matching normalizes case/whitespace and
    is prefix-tolerant in BOTH directions, so a dated snapshot (``openai/gpt-5-mini-2025-08-07``) verifies
    against the base slug ``openai/gpt-5-mini`` and vice-versa."""
    exp = (expected or "").strip().lower()
    got = (served or "").strip().lower()
    if not exp or not got:
        return None
    return got == exp or got.startswith(exp) or exp.startswith(got)


def _clamp_int(value, *, lo: int = 0, hi: int = 100) -> int | None:
    """An integer inside [lo, hi], or None. Never raises: a model can emit a string, a float or junk."""
    if value is None:
        return None
    try:
        return max(lo, min(hi, int(round(float(value)))))
    except (TypeError, ValueError):
        return None


def _normalise_signals(raw) -> list[dict]:
    """The eight per-account dimensions, in canonical order, whatever the model actually sent.

    Defensive on purpose. This is model output reaching persistence and then the UI, so it is
    normalised rather than trusted: unknown names are dropped, duplicates keep the first, and a
    dimension the model omitted is materialised with ``score: None``. The UI can then render eight
    rows unconditionally instead of branching per account.

    ``score: None`` is meaningful and must survive: it means the evidence for that dimension was
    never collected, which is different from scoring it zero. Collapsing the two would turn "we
    could not tell" into "this looks genuine", which is the exact overclaim the protocol forbids.
    """
    from app.reasoning.prompts.comprehensive_investigation_template import (
        COMPREHENSIVE_SIGNAL_NAMES,
    )

    seen: dict[str, dict] = {}
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        if name not in COMPREHENSIVE_SIGNAL_NAMES or name in seen:
            continue
        reason = item.get("reason")
        seen[name] = {
            "name": name,
            "score": _clamp_int(item.get("score")),
            "reason": reason.strip() if isinstance(reason, str) and reason.strip() else None,
        }
    return [
        seen.get(name, {"name": name, "score": None, "reason": None})
        for name in COMPREHENSIVE_SIGNAL_NAMES
    ]


def _dealias_investigation_prose(governed: dict, legend, payload: dict) -> None:
    """Rewrite aliases out of the investigation-level prose, in place.

    Account aliases become the account's real handle; a cluster alias has no public name at all, so
    it is removed along with any parenthetical it leaves empty. Best effort by construction: prose
    the reader can follow matters, but never at the cost of failing the investigation over it.
    """
    try:
        from app.reasoning.grounding import resolve_aliases_in_prose
        accounts = (legend.to_manifest() or {}).get("accounts") or {}
        by_ref = _commenters_by_author_ref(payload)
        handles = {}
        for alias, author_ref in accounts.items():
            c = by_ref.get(author_ref) or {}
            h = c.get("handle") or c.get("external_id")
            if h:
                handles[alias] = str(h)
        for key in ("headline", "assessment", "bottom_line"):
            if isinstance(governed.get(key), str):
                governed[key] = resolve_aliases_in_prose(governed[key], handles)
        for bucket in ("evidence_for", "evidence_against", "uncertainty",
                       "what_would_change_this"):
            for item in (governed.get(bucket) or []):
                if isinstance(item, dict) and isinstance(item.get("claim"), str):
                    item["claim"] = resolve_aliases_in_prose(item["claim"], handles)
    except Exception:  # noqa: BLE001 — presentation polish must never sink an investigation
        logger.exception("analyst: could not de-alias the investigation prose")


def _salvaged_account_reads(raw_obj: dict | None, legend, payload: dict, *,
                            governor_verdict: str | None) -> list[dict]:
    """The per-account reads from a response whose EXECUTIVE WRAPPER failed canonical validation.

    ``validate_comprehensive_model_output`` is all-or-nothing, so a reply whose twenty per-account
    paragraphs are perfect and whose synthesis wrapper is missing one field was thrown away whole:
    the customer paid a credit, the model did the expensive part of the work, and the product showed
    them nothing. The substantive output of an investigation is the per-account reads; the wrapper is
    a summary of them, and the deterministic Floor can stand in for a summary.

    So the wrapper still floors (the Floor's verdict is served, ``model_backed`` stays False, and the
    operator alert still fires: nothing here pretends the run succeeded) while the rows survive. They
    are not taken on trust either. Each one goes through the same join as a valid run, which derives
    the tier from the score and runs ``grounding`` over the prose, so an invented quote or a
    contradicted figure is withheld exactly as it would be on a clean run.

    Two refusals:

    * **A Governor rejection is never salvaged.** That is our own policy layer refusing the output,
      not a shape mismatch, and reaching around it to publish the rows it refused is the wrong
      instinct. (Today's live path runs ``adjudication="schema_only"`` so this cannot fire; it is
      here so that changing the adjudication mode cannot quietly turn salvage into a bypass.)
    * **Nothing that resolves to no account.** A row whose alias resolves to nobody is not a read of
      anything, and a wrapper-less entry carrying only unresolved rows is worse than an honest
      failure notice.
    """
    if str(governor_verdict or "").lower() == "reject":
        return []
    items = (raw_obj or {}).get("commenter_assessments")
    if not isinstance(items, list) or not items:
        return []
    rows = _join_commenter_assessments(raw_obj, legend, payload)
    return rows if any(r.get("resolved") for r in rows) else []


def _join_commenter_assessments(raw_obj: dict | None, legend, payload: dict) -> list[dict]:
    """Join each model-authored per-account assessment (keyed by alias) with the account's real identity.
    AI-first: the per-account OMI score + tier are the MODEL'S (it reasons them from that account's raw
    evidence); OmiSphere supplies only identity (handle/external_id) from the metadata. The engine's own
    probability is carried as a secondary reference (``engine_probability``) when present, never as the
    account's score. Aliases resolve through the reversible legend; an item whose alias does not resolve is
    kept but marked ``resolved: False`` (never dropped — the presentation layer flags it)."""
    items = (raw_obj or {}).get("commenter_assessments")
    if not isinstance(items, list):
        return []
    accounts = legend.to_manifest().get("accounts", {})     # alias -> author_ref
    by_ref = _commenters_by_author_ref(payload)
    joined: list[dict] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        alias = it.get("ref")
        author_ref = accounts.get(alias) or (legend.resolve(alias) if alias else None)
        commenter = by_ref.get(author_ref) if author_ref else None
        # The account's OMI score is MODEL-produced (clamped for safety). The TIER is DERIVED from it
        # here rather than taken from the model, because the two disagreed in production: one live
        # export rendered score 28 as "low" on two accounts and "moderate" on two others, and 29 as
        # both, so the tier badge a customer reads was not a function of the number printed beside
        # it. The band edges are one definition (`_tier_for_score`), the investigation-level tier has
        # always been derived that way (see `_merge_batch_parts`), and this makes the per-account
        # tier agree. Score is the single source of truth; the badge renders it.
        #
        # A disagreement is still worth knowing about, because it means the model's own banding drifted
        # from the protocol it was given, so it is logged rather than silently dropped. It is NOT
        # persisted on the row: adding a field here would put it through the viewer gate and the
        # export for no reader's benefit.
        omi_score = it.get("omi_score")
        try:
            omi_score = max(0, min(100, int(round(float(omi_score))))) if omi_score is not None else None
        except (TypeError, ValueError):
            omi_score = None
        model_tier = it.get("suspicion_tier")
        derived_tier = _tier_for_score(omi_score) if omi_score is not None else model_tier
        if omi_score is not None and model_tier and model_tier != derived_tier:
            logger.info("analyst tier drift on %s: model said %s for score %s, serving %s",
                        alias, model_tier, omi_score, derived_tier)
        row: dict = {
            "ref": alias,
            "omi_score": omi_score,
            "suspicion_tier": derived_tier,
            "confidence": _clamp_int(it.get("confidence")),
            "signals": _normalise_signals(it.get("signals")),
            "assessment": it.get("assessment"),
            "citations": it.get("citations") or [],
            "resolved": commenter is not None,
        }
        if commenter is not None:
            # Identity + the RAW metadata (from the scan, never a score) so the UI can show each account's
            # objective facts alongside the AI's per-account OMI score. The engine's probability rides
            # along as a secondary reference, distinct from the account's model-produced OMI score.
            row["handle"] = commenter.get("handle")
            row["external_id"] = commenter.get("external_id")
            for fld in ("follower_count", "following_count", "account_created_at"):
                if commenter.get(fld) is not None:
                    row[fld] = commenter.get(fld)
            _posts = commenter.get("recent_activity") or []
            if _posts:
                row["post_count"] = commenter.get("history_size") or len(_posts)
            _eng = (commenter.get("coordination_adjusted_probability")
                    if commenter.get("coordination_adjusted_probability") is not None
                    else commenter.get("overall_probability"))
            if _eng is not None:
                row["engine_probability"] = _eng
        joined.append(row)

    # Deterministic grounding pass. This is the ONLY thing inspecting the sentences that get
    # screenshotted: the Governor's S9 lint does not see `commenter_assessments[].assessment`, and
    # the comprehensive path runs adjudication="schema_only". Here is the one place holding both the
    # model's prose and the account's real posts, so here is where a quote it never wrote, or a
    # follower count that contradicts the evidence, gets caught rather than published.
    try:
        from app.reasoning.grounding import verify_batch

        accounts_by_ref = {}
        for r in joined:
            author_ref = accounts.get(r.get("ref")) or (
                legend.resolve(r["ref"]) if r.get("ref") else None
            )
            if author_ref and by_ref.get(author_ref):
                accounts_by_ref[r.get("ref")] = by_ref[author_ref]
        summary = verify_batch(joined, accounts_by_ref)
        if summary.get("withheld"):
            logger.warning(
                "grounding: withheld %s of %s per-account assessments (codes=%s)",
                summary["withheld"], summary["accounts"], ",".join(summary.get("codes") or []),
            )
    except Exception as exc:  # noqa: BLE001 — verification must never lose a whole assessment
        logger.exception("grounding pass failed; assessments served unverified")
        capture_exception(exc)

    return joined


def build_bundle(payload: dict, *, ref: str, platform: str, impl, prior_context: list | None = None) -> dict:
    scan = {
        "overall_probability": payload.get("overall_probability") or 0.0,
        "tier": payload.get("overall_tier") or payload.get("tier") or "low",
        "confidence": payload.get("confidence") or 0.0,
        "summary": payload.get("summary") or "",
        "weak_signals": payload.get("weak_signals") or [],
        "contributions": payload.get("contributions") or [],
        "coordination": _coordination_from_payload(payload),
    }
    bundle = impl.evidence_bundle.project_investigation_bundle(
        ref=ref, platform=platform, scan=scan,
        components=_components_from_payload(payload, impl),
        cross_links=payload.get("cross_links") or [],
    )
    # Sprint 021 — institutional memory reaches the AI specialist as labeled CONTEXT (never proof).
    # Additive: the deterministic provider ignores this key (so its output is unchanged), while the
    # Qwen provider serializes the whole bundle, so the live model reasons with prior context.
    if prior_context:
        bundle["prior_context"] = prior_context
    return bundle


def _retrieve_prior_context(store: Any, app_bundle: Any, *, now: Any = None, top_k: int = 5) -> list[dict]:
    """Retrieve institutional PriorContext for the analyst's input (Sprint 021). Each prior is
    background context — labeled, never proof, and carries NO resolvable evidence id (so the model
    cannot cite it as evidence; the memory boundary is preserved). Returns ``[]`` when memory is
    empty / unavailable. Never raises."""
    if store is None or app_bundle is None:
        return []
    try:
        from app.memory.graph import retrieve

        priors = retrieve(store, app_bundle, top_k=top_k, now=now)
        return [{
            "type": p.type, "label": p.label,
            "confidence": round(float(p.confidence), 3), "stability": round(float(p.stability_score), 3),
            "epistemic_status": p.epistemic_status, "influence_class": p.influence_class,
            "basis": p.match_basis, "note": "institutional memory — background context, never proof",
        } for p in priors]
    except Exception:  # noqa: BLE001 — memory must never break the analyst
        logger.warning("prior-context retrieval failed; proceeding without memory", exc_info=True)
        return []


# --------------------------------------------------------------------------- #
# Assessment (sync core) — off the hot path; safe to run in a worker thread
# --------------------------------------------------------------------------- #
# P3.2 — canonical runtime cutover. The council-wrapper layer (_AnalystJudge/_AnalystFloor/
# _attach_governance, Sprint 017) is retired: the AI Investigation Runtime (``runtime.infer``,
# judge_then_floor adjudication) now owns the endpoint call, the mandatory Governor, the
# deterministic Floor, and the forensic capture — with the same Binder evidence, the same
# registry prompt, and the same governance contract. The council Orchestrator remains only in
# Shadow Mode (admin-only evaluation), never in production. OmiScore is never touched.


# --------------------------------------------------------------------------- #
# Runtime measurement — per-investigation metrics + cache effectiveness
# --------------------------------------------------------------------------- #
_cache_stats = {"served_from_cache": 0, "generated": 0}


# Phase B — the origin of every report field: the MODEL reasons over the evidence and generates the
# analytical conclusions; the deterministic engine produces the authoritative measurable signals,
# which the model ECHOES and must never override (echo discipline). This map is the architectural
# contract surfaced in the forensic audit (items 8 & 9).
_MODEL_GENERATED_FIELDS = (
    # AI-first: the analyst produces its OWN scores — the OMI score + its tier band.
    "omi_score", "suspicion_tier",
    "verdict", "confidence_band", "confidence_rationale", "headline", "assessment",
    "evidence_for", "evidence_against", "uncertainty", "what_would_change_this",
    "limits_statement", "coordination_label", "legitimate_hypothesis", "supplemental_context",
    # Phase 1 — the six per-domain reasoning sections are FIRST-CLASS model-generated analytical
    # content in the ONE canonical comprehensive assessment (validated + persisted alongside the wrapper).
    "comment_reasoning", "commenter_history_reasoning", "account_reasoning",
    "narrative_reasoning", "coordination_reasoning", "campaign_reasoning",
)
# The engine owns these — the model echoes them and OmiSphere overwrites/overlays from the deterministic
# engine (never model-fabricated): the echoed suspicion numbers + the corroboration state.
# AI-first: nothing is echoed/overwritten anymore. Only the factual engine 'corroboration' state
# (which discriminative methods fired) is overlaid from the deterministic evidence.
_DETERMINISTIC_ECHOED_FIELDS = ("corroboration",)
_SYSTEM_FIELDS = ("governance", "ai_package", "prompt_build", "metrics", "subject",
                  "analyst_version", "prompt_version", "schema_version", "model_revision")


def field_provenance() -> dict:
    """Which report fields originate from the model vs the deterministic engine vs the system.
    Static architectural contract (Phase-B items 8/9): the AI is the analyst (it generates the
    reasoning), the deterministic engine is the evidence source (its measurable numbers are echoed,
    never overridden), and the Governor/package fields are system provenance."""
    return {
        "model_generated": list(_MODEL_GENERATED_FIELDS),
        "deterministic_echoed": list(_DETERMINISTIC_ECHOED_FIELDS),
        "system_provenance": list(_SYSTEM_FIELDS),
        "doctrine": ("the model generates the analytical conclusions FROM the evidence; the engine's "
                     "suspicion_probability/tier are authoritative measurable signals the model echoes "
                     "and never moves (echo discipline); the Governor re-validates every field"),
    }


def runtime_metrics() -> dict:
    """Process-lifetime AI runtime counters (cache effectiveness). Read-only; cheap; never raises."""
    c = dict(_cache_stats)
    total = c["served_from_cache"] + c["generated"]
    return {"assessment_cache": {**c, "total": total,
                                 "hit_rate": round(c["served_from_cache"] / total, 4) if total else 0.0}}


def _assessment_metrics(governed: dict, gov: dict, settings: Settings, *, store_ms: float,
                        reasoning_ms: float, model_backed: bool, prompt_meta: dict) -> dict:
    """Additive per-investigation measurement (never affects the assessment). App-measured latencies
    are precise; token/cost are clearly-labeled completion-side ESTIMATES — authoritative token
    usage is available from the endpoint's ``usage`` field (a Phase-2 capture in the provider)."""
    import json as _json

    model_ms = float(gov.get("latency_ms", 0.0) or 0.0)
    payload_only = {k: v for k, v in governed.items() if k not in ("governance", "metrics")}
    est_completion_tokens = round(len(_json.dumps(payload_only, ensure_ascii=False)) / 4)
    rate = float(getattr(settings, "analyst_cost_per_1k_tokens_usd", 0.0) or 0.0)
    return {
        "total_reasoning_ms": round(reasoning_ms, 2),
        "model_ms": round(model_ms, 2),
        "governor_and_assembly_ms": round(max(0.0, reasoning_ms - model_ms), 2),
        "memory_store_ms": round(store_ms, 2),
        "memory_durable": bool(getattr(settings, "memory_persistence_enabled", False)),
        "model_backed": model_backed,
        "est_completion_tokens": est_completion_tokens,
        "est_completion_cost_usd": round(est_completion_tokens / 1000.0 * rate, 6) if rate else None,
        "token_source": "estimate:chars/4 (authoritative usage is endpoint-side)",
        "prompt_version": prompt_meta.get("version"),
        "prompt_hash": prompt_meta.get("hash"),
    }


def _assess_core(
    payload: dict, *, ref: str, platform: str = "youtube", settings: Settings | None = None,
    capture: dict | None = None, completion_budget_multiplier: float = 1.0,
) -> dict | None:
    """Produce a Governor-validated structured assessment for an investigation payload, or None if
    the feature is off / unavailable / errored. Never raises.

    P2.1 — reach this ONLY through the runtime (``app.reasoning.runtime.assess_investigation``) /
    the ``assess_payload`` compatibility wrapper below, never directly.

    P3.2 — canonical runtime cutover: execution is owned by the **AI Investigation Runtime**
    (``runtime.infer`` — the ONE endpoint path, the ONE mandatory Governor invocation, the ONE
    deterministic Floor, the ONE forensic capture), with the legacy council's judge-then-floor
    adjudication semantics preserved exactly. This stage assembles the same evidence (ONE Binder,
    prior-context retrieval, lossy bundle) and the same prompt (ONE Prompt Registry system prompt
    via the package Prompt Builder + the ml-impl user message) as before — byte-identical model
    inputs, governance block, and metrics. The Governor is never skipped; the Floor is never
    bypassed; OmiScore is never touched.
    """
    settings = settings or get_settings()
    if not analyst_enabled(settings):
        return None
    impl = _impl()
    if impl is None:
        return None
    # Ensure a forensic capture sidecar exists so the ONE transport records the actually-served model
    # (e.g. the model an OpenRouter preset routed to) for provenance. This changes no inference behavior
    # — the runtime writes into this dict exactly as it already does for the trace/audit routes.
    capture = {} if capture is None else capture
    try:
        from app.reasoning.prompts import default_registry

        config = impl.load_analyst_config(
            repo_id=settings.analyst_hf_repo, revision=settings.analyst_hf_revision,
        )
        # Phase 5H — dynamic completion budget. Replace the fixed output-token cap with a value sized from
        # THIS investigation: enough to give every commenter a concise per-account assessment plus the
        # executive synthesis, clamped to a safe ceiling. Small investigations request little; a
        # ~150-commenter investigation requests enough to finish. Overrides decoding.max_new_tokens without
        # mutating the shared config dict (fresh copy on the instance).
        from app.reasoning.completion import (
            COMPLETION_BASE_TOKENS,
            COMPLETION_CEILING_TOKENS,
            COMPLETION_FLOOR_TOKENS,
            COMPLETION_PER_COMMENTER_TOKENS,
            completion_budget,
        )
        _commenter_count = len(((payload.get("video") or {}).get("commenters")) or [])
        # Cost guardrail: the budget knobs are env-overridable (OMI_ANALYST_COMPLETION_*), so per-scan
        # OpenRouter spend can be tuned WITHOUT a code deploy. The ceiling caps any single inference.
        _completion_max_tokens = completion_budget(
            _commenter_count,
            base=int(getattr(settings, "analyst_completion_base_tokens", COMPLETION_BASE_TOKENS)),
            per_commenter=int(getattr(settings, "analyst_completion_per_commenter_tokens",
                                     COMPLETION_PER_COMMENTER_TOKENS)),
            floor=int(getattr(settings, "analyst_completion_floor_tokens", COMPLETION_FLOOR_TOKENS)),
            ceiling=int(getattr(settings, "analyst_completion_ceiling_tokens", COMPLETION_CEILING_TOKENS)),
        )
        # A retry after a TRUNCATED reply asks for more room. Retrying a truncation at the same cap
        # would truncate again in the same place, which is exactly why the in-transport retry
        # declines to do it; raising the budget makes the second attempt a different question.
        # Still clamped by the ceiling, so the cost guardrail keeps the last word.
        if completion_budget_multiplier and completion_budget_multiplier != 1.0:
            _ceiling = int(getattr(settings, "analyst_completion_ceiling_tokens",
                                   COMPLETION_CEILING_TOKENS))
            _completion_max_tokens = min(
                _ceiling, int(_completion_max_tokens * float(completion_budget_multiplier)),
            )
        config.decoding = {**(config.decoding or {}), "max_new_tokens": _completion_max_tokens}
        spec = default_registry().resolve("omi_analyst", getattr(settings, "analyst_prompt_version", None))
        prompt_meta = {"analyst": "omi_analyst", "version": spec.prompt_version,
                       "hash": spec.prompt_hash, "source": "registry"}
        # The canonical AI deployment package (published to HF; loaded from bundled data) that this
        # investigation reasons with — consumed through the ONE Canonical Package Loader (P3.2,
        # fail-closed verified); ``identity`` is the same content-addressed AIPackage as before.
        from app.reasoning.package_loader import load_package
        ai_package = load_package(getattr(settings, "analyst_model_id", None)).identity
        # P3.4 — the Investigation Summary is a canonical reasoning stage: its prompt is assembled below
        # by the ONE Canonical Stage Prompt Builder over an InvestigationSummaryBundle, EXCLUSIVELY from
        # package assets (zero embedded prompt text) — not the legacy PromptBuilder / build_user_message.
        # The LoadedPackage is the stage builder's verified asset source; ``prompt_mode`` labels the
        # forensic provenance.
        loaded = load_package(getattr(settings, "analyst_model_id", None))
        prompt_mode = "stage:comprehensive_investigation"

        endpoint = getattr(settings, "analyst_endpoint_url", None)
        provider_sel = reasoning_provider(settings)
        if provider_sel == "openrouter":
            _or_preset = getattr(settings, "openrouter_preset", None)
            _or_model = getattr(settings, "openrouter_model", None)
            if _or_preset or _or_model:
                logger.info("analyst.assess: OPENROUTER path selected ref=%s preset=%s model=%s "
                            "key_present=%s prompt=%s(%s) assembly=%s -> model call will be made by the runtime",
                            ref, _or_preset or "-", _or_model or "-",
                            bool(os.environ.get("OPENROUTER_API_KEY")), spec.prompt_version,
                            spec.prompt_hash, prompt_mode)
            else:
                logger.info("analyst.assess: provider=openrouter but no preset/model configured ref=%s -> "
                            "deterministic floor (NO model call). Set OMI_OPENROUTER_PRESET or "
                            "OMI_OPENROUTER_MODEL.", ref)
        elif endpoint:
            logger.info("analyst.assess: REMOTE path selected ref=%s endpoint=%s api=%s model=%s "
                        "prompt=%s(%s) assembly=%s -> model call will be made by the runtime",
                        ref, _redact_endpoint(endpoint),
                        str(getattr(settings, "analyst_endpoint_api", "generate") or "generate"),
                        getattr(settings, "analyst_model_id", None), spec.prompt_version,
                        spec.prompt_hash, prompt_mode)
        else:
            logger.info("analyst.assess: no analyst_endpoint_url configured ref=%s -> deterministic "
                        "floor (NO model call). Set OMI_ANALYST_ENDPOINT_URL to reach the endpoint.", ref)

        model_revision = getattr(config, "model_revision", None)
        # Sprint 021 — wire institutional memory into the AI specialist's input. ``get_memory_store``
        # returns the durable store when memory persistence is enabled, else an empty in-memory store
        # (so retrieval naturally no-ops). Memory is CONTEXT only; it never moves the engine number.
        t_store0 = time.perf_counter()
        from app.memory.repository import get_memory_store
        store = get_memory_store(settings)
        store_ms = (time.perf_counter() - t_store0) * 1000.0

        # P3.2/P3.4 — the AI Investigation Runtime owns execution (endpoint + Governor + Floor +
        # forensics). This stage assembles the SAME governance evidence (ONE Binder bind) and, as of
        # P3.4, the MODEL prompt via the ONE Canonical Stage Prompt Builder over an
        # InvestigationSummaryBundle (built from the ONE Investigation Context) — exclusively from
        # package assets — then hands ONE PromptPackage to the runtime under the legacy
        # judge-then-floor adjudication semantics. The deterministic Floor keeps MEASURING the evidence
        # from the lossy bundle (byte-identical output); only the model's prompt moved onto the
        # canonical stage architecture.
        from app.reasoning.comprehensive_investigation_analysis import (
            build_comprehensive_investigation_prompt_package,
        )
        from app.reasoning.evidence_repository import EvidenceRepository
        from app.reasoning.investigation_composer import InvestigationComposer
        from app.reasoning.package_loader import load_comprehensive_investigation_assets
        from app.reasoning.runtime import run_stage_inference

        t_run0 = time.perf_counter()
        # The Evidence Repository is the ONE read-facade: it reads all of this investigation's evidence
        # once (the governance bundle, the institutional-memory priors, the InvestigationContext) and
        # freezes it into an immutable, content-addressed snapshot. The reasoning path consumes the
        # snapshot; it never reads the stores itself. (R1 is behavior-preserving — identical reads.)
        snapshot = EvidenceRepository().snapshot(
            payload, ref=ref, platform=platform, settings=settings, store=store)
        gov_bundle = snapshot.gov_bundle
        lossy = build_bundle(payload, ref=ref, platform=platform, impl=impl,
                             prior_context=list(snapshot.prior_context))
        floor_response = impl.DeterministicAnalystProvider().generate(lossy, config).response

        # The Investigation Composer assembles the COMPLETE, content-addressed InvestigationPackage from
        # the snapshot; the comprehensive stage renders its full budgeted evidence into ONE prompt. This
        # is the single production investigation inference: Mistral receives the actual structured
        # evidence content of the complete package (seven domains) in ONE endpoint request.
        package = InvestigationComposer().compose(snapshot)
        # Teach the governance bundle to resolve the citation universe the model is SHOWN — the complete
        # package's stable evidence ids + the reversible short aliases — so the ONE Governor's citation
        # guard ACCEPTS legitimate alias citations while still rejecting fabricated ones.
        from app.reasoning.investigation_render import build_alias_legend
        investigation_legend = build_alias_legend(package)
        gov_bundle.extra_citable = set(package.evidence_index) | investigation_legend.alias_tokens()
        ci_assets = load_comprehensive_investigation_assets()
        pp = build_comprehensive_investigation_prompt_package(package, loaded=loaded, assets=ci_assets)

        # Forensic provenance of the assembled prompt — preserves the trace/audit contract (mode,
        # system_prompt_sha, knowledge_entries_used), now sourced from the comprehensive stage package.
        prompt_build = {
            "mode": prompt_mode,
            "assembled_from": pp.manifest.get("assembled_from"),
            "package_hash": pp.manifest.get("package_hash"),
            "prompt_hash": pp.manifest.get("prompt_hash"),
            "system_prompt_sha": pp.manifest.get("system_prompt_sha"),
            "system_prompt_chars": len(pp.system),
            "knowledge_entries_used": [e["id"] for e in loaded.knowledge()[:12]],
            "comprehensive_investigation_template_hash": pp.manifest.get(
                "comprehensive_investigation_template_hash"),
            "investigation_package_id": package.package_id,
            "evidence_coverage_mode": pp.manifest.get("evidence_coverage_mode"),
            "evidence_tokens_est": pp.manifest.get("evidence_tokens_est"),
            "evidence_sampling_truncated": pp.manifest.get("evidence_sampling_truncated"),
            "evidence_snapshot_id": snapshot.snapshot_id,
            "prompt_package_id": pp.prompt_package_id,
        }
        if capture is not None:
            # Item 2 — the prompt version/hash loaded from the (HF-published) package.
            capture["prompt_version"] = spec.prompt_version
            capture["prompt_hash"] = spec.prompt_hash
            capture["ai_package"] = ai_package.provenance()
            capture["prompt_build"] = prompt_build
        t_model0 = time.perf_counter()
        inference = run_stage_inference(
            pp, gov_bundle, settings=settings, config=config, floor_ruling=floor_response,
            schema_prefilter=True, require_hf_token=True, capture=capture,
            # AI-first investigation refactor: the model IS the investigator. Its schema-valid output is
            # accepted verbatim — structural validation only, no interpretive Governor gate on the AI's
            # reasoning. Floor stands in on schema-invalid output.
            adjudication="schema_only",
            # Phase 1 — the ONE canonical comprehensive contract: the model's full output (synthesis
            # wrapper + six first-class reasoning domains) is validated against this schema; Omi-owned
            # provenance/subject + engine corroboration are overlaid from the Floor AFTER validation, so
            # the model never fabricates system-owned metadata.
            canonical_output_schema=ci_assets.output_schema())
        model_ms = (time.perf_counter() - t_model0) * 1000.0
        reasoning_ms = (time.perf_counter() - t_run0) * 1000.0

        from app.governor import Governor, validate_comprehensive_sections
        governed = dict(inference.ruling)
        gov: dict[str, Any] = {
            "verdict": inference.trace.verdict,
            "trace_id": inference.trace.trace_id(),
            "violation_codes": list(inference.trace.violation_codes),
            "provider": inference.provider,
            "model_revision": model_revision,
            "prompt": prompt_meta,
            "latency_ms": 0.0 if inference.fallback_from else round(model_ms, 2),
            "constitution_version": Governor.constitution_version,
        }
        if inference.fallback_from:
            gov["fallback_from"] = inference.fallback_from
            gov["rejected_codes"] = list(inference.rejected_codes)
        governed["governance"] = gov
        # The comprehensive response's six per-domain reasoning sidecars ride alongside the
        # Governor-validated synthesis wrapper. Structurally validate them + resolve their citations
        # against the complete package's evidence universe (the stable evidence index + the reversible
        # alias legend + the governance bundle). This is validation only — it moves no number and
        # discards no served ruling; unresolved citations are recorded for the presentation layer.
        sections_report = validate_comprehensive_sections(
            inference.raw_obj, section_keys=ci_assets.section_keys,
            evidence_index=package.evidence_index,
            legend=investigation_legend.to_manifest(), gov_bundle=gov_bundle)
        governed["comprehensive_sections"] = {
            k: v for k, v in (inference.raw_obj or {}).items() if k in ci_assets.section_keys
        }
        governed["comprehensive_validation"] = sections_report
        # Per-account (per-commenter) reasoning: echo-join the model's aliased assessments back to real
        # identity + the engine's tier/probability (the model never emits a per-account number). Overwrites
        # the raw passthrough with the enriched, presentation-ready list. Empty when the model emitted none.
        prov = str(gov.get("provider", "?"))
        model_backed = ("fallback" not in prov) and ("deterministic" not in prov)
        # Only surface the model's per-account reasoning when the model output was ACCEPTED (not the Floor):
        # a rejected candidate's raw_obj must never leak its per-account assessments to the UI.
        #
        # When the model output was REFUSED, the per-account rows can still be salvageable: the
        # wrapper is what failed validation, and the rows are the part the customer paid for. See
        # `_salvaged_account_reads` for the two cases it refuses. `account_reads_salvaged` on the
        # trace is what tells the UI it is looking at real reads under a Floor wrapper, so it can
        # show them instead of a bare "could not be produced".
        governed["commenter_assessments"] = (
            _join_commenter_assessments(inference.raw_obj, investigation_legend, payload)
            if model_backed
            else _salvaged_account_reads(inference.raw_obj, investigation_legend, payload,
                                         governor_verdict=gov.get("verdict")))
        salvaged = bool(not model_backed and governed["commenter_assessments"])
        if salvaged:
            logger.warning(
                "analyst: ref=%s wrapper floored but %d per-account read(s) were salvaged from the "
                "model response", ref, len(governed["commenter_assessments"]))
        # Internal aliases must not reach a reader in the INVESTIGATION-LEVEL prose either. This
        # shipped live: "style-match clusters (C4, C6, C1, C5, C3, C7)" and "few or no collected
        # posts (A24, A20, A19)" rendered on the page a customer screenshots. `check_alias_in_prose`
        # is HARD but only guards the per-account paragraphs; this text goes through the Governor's
        # S9 lint, which has no alias rule. Resolving beats refusing here: withholding the whole
        # summary would be far too blunt, and a real handle is strictly more useful than the label
        # the model wrote.
        _dealias_investigation_prose(governed, investigation_legend, payload)
        # Phase 5H — completion verification. Decide explicitly whether the AI reasoned over the COMPLETE
        # investigation: did generation stop normally (vs hit the token ceiling), did every commenter shown
        # to the model receive an assessment, was any commenter omitted upstream. Nothing is silently
        # truncated — an incomplete investigation is MARKED incomplete, with the reason + remaining work.
        from app.reasoning.completion import verify_completion
        _total_commenters = len(((payload.get("video") or {}).get("commenters")) or [])
        # Accounts actually SHOWN to the model (carried into the evidence package). Anything the upstream
        # evidence budget could not carry is honestly counted as omitted input — never silently dropped.
        _represented = int(pp.manifest.get("evidence_represented_accounts") or _total_commenters)
        _represented = min(_represented, _total_commenters) if _total_commenters else _represented
        _omitted_input = max(0, _total_commenters - _represented)
        _assessed = sum(1 for r in governed["commenter_assessments"] if r.get("resolved"))
        _completion = verify_completion(
            model_backed=model_backed, finish_reason=capture.get("finish_reason"),
            represented_commenters=_represented, assessed_commenters=_assessed,
            omitted_input_commenters=_omitted_input, max_output_tokens=_completion_max_tokens,
            output_tokens=(inference.tokens or {}).get("completion_tokens"),
            json_received=(inference.raw_obj is not None),
            # A model-backed result passed BOTH canonical-schema validation and the Governor (that is what
            # makes it model-backed) — certify them explicitly. On the Floor path both are False.
            schema_valid=model_backed, governor_valid=bool(inference.trace.permitted),
            # Salvage is neither a success nor a Floor, and reporting it as a Floor produced a
            # coverage box that denied the reasoning printed directly beneath it.
            salvaged_reads=salvaged)
        governed["completion"] = _completion.to_dict()
        governed["ai_package"] = ai_package.provenance()
        governed["prompt_build"] = prompt_build
        # One correlated production trace for the single comprehensive investigation inference — reuses
        # the existing forensic capture (no second logging subsystem). ``inference_count`` is the
        # endpoint-request cardinality for THIS investigation: the architecture makes exactly one
        # ``run_stage_inference`` call, so it is 1 when the endpoint was reached, else 0 (floor). It
        # makes a second inference for one investigation immediately visible. IDs/hashes/counts only —
        # no secrets, no tokens, no auth headers.
        _provider = reasoning_provider(settings)
        _usage = inference.tokens or {}          # round-trips through the runtime (cost + token counts)
        if _provider == "openrouter":
            _or_preset = getattr(settings, "openrouter_preset", None)
            _or_model = getattr(settings, "openrouter_model", None)
            # Prefer the model reference the transport ACTUALLY put on the wire (it drops a misconfigured
            # display-name model and falls back to preset-only), so the trace matches reality rather than
            # the raw configured concatenation. Fall back to the computed value if the wire never fired.
            _requested_model = capture.get("model_ref") or (
                f"{_or_model}@preset/{_or_preset}" if (_or_preset and _or_model)
                else (f"@preset/{_or_preset}" if _or_preset else _or_model))
        else:
            _requested_model = inference.served_model
        try:
            from app.reasoning.prompts.comprehensive_investigation_template import (
                COMPREHENSIVE_ASSESSMENT_SCHEMA_ID,
            )
            from app.reasoning.prompts.master_protocol import master_analyst_protocol_identity
            _master = master_analyst_protocol_identity(getattr(settings, "analyst_model_id", None))
            _schema_id = COMPREHENSIVE_ASSESSMENT_SCHEMA_ID
        except Exception:  # noqa: BLE001 — provenance is best-effort, never blocks a trace
            _master, _schema_id = {}, None
        investigation_trace = {
            "ref": ref,
            # Provider transport identity (Phase 2). Which gateway served the ONE inference + the
            # deployment provenance for the OpenRouter Preset path. Secrets never appear here.
            "provider": _provider,
            "requested_model": _requested_model,
            "openrouter_preset": (getattr(settings, "openrouter_preset", None)
                                  if _provider == "openrouter" else None),
            "master_prompt_version": _master.get("version"),
            "master_prompt_hash": _master.get("hash"),
            "canonical_schema_id": _schema_id,
            # Phase 5H — completion budgeting + verification (full-investigation coverage).
            "finish_reason": capture.get("finish_reason"),
            "max_output_tokens": _completion_max_tokens,
            "commenters_total": _total_commenters,
            "commenters_assessed": _assessed,
            "completion_complete": _completion.complete,
            "completion_incomplete_kind": _completion.incomplete_kind,
            "endpoint_cost_usd": _usage.get("cost"),
            # Authoritative token usage reported by the gateway (OpenRouter `usage`), for production
            # verification + cost transparency. None on the Floor path (no billed generation).
            "input_tokens": _usage.get("prompt_tokens"),
            "output_tokens": _usage.get("completion_tokens"),
            "total_tokens": _usage.get("total_tokens"),
            "inference_count": 1 if inference.endpoint_called else 0,
            "endpoint_called": inference.endpoint_called,
            # Crisp pipeline-stage flags for the verification surface (all derived from existing state):
            # the request completed with a body, a JSON object was parsed, and it passed canonical
            # validation + the Governor (i.e. the served assessment is the model's, not the Floor's).
            "request_completed": bool(inference.endpoint_called and inference.response_status
                                      and not inference.endpoint_error),
            "json_received": inference.raw_obj is not None,
            "validation_passed": bool(model_backed),
            "model_backed": model_backed,
            # The wrapper floored but the model's per-account reads survived. Deliberately a field of
            # its own rather than a softening of `model_backed`: that flag gates the operator alert,
            # the self-heal regeneration and the "is this prose the model's" question about the
            # SYNTHESIS, and all three answers are still no. This one answers a different question,
            # for the one reader who needs it: the customer looking at reads that really are the
            # analyst's, under a summary that is not.
            "account_reads_salvaged": salvaged,
            # Classified from what this run actually recorded, NOT from `inference.fallback_from`.
            # That field is only ever set on the `judge_then_floor` branch, and the live
            # comprehensive path runs `adjudication="schema_only"`, so it was always None here: the
            # floor alert logged "unclassified", Sentry carried nothing, and the customer got the
            # generic sentence. Everything needed to name the cause was already being captured a
            # few lines below and simply never read. See app/reasoning/floor_reason.py.
            "fallback_reason": (
                inference.fallback_from
                or (None if model_backed else _classify_floor({
                    "governor_verdict": gov.get("verdict"),
                    "rejected_codes": gov.get("rejected_codes"),
                    "violation_codes": gov.get("violation_codes"),
                    "response_status": inference.response_status,
                    "endpoint_error": inference.endpoint_error,
                    "endpoint_called": inference.endpoint_called,
                    "finish_reason": capture.get("finish_reason"),
                    "canonical_validation_errors": capture.get("canonical_validation_errors"),
                }))
            ),
            "snapshot_id": snapshot.snapshot_id,
            "investigation_package_id": package.package_id,
            "prompt_package_id": pp.prompt_package_id,
            # Content address of the ACTUAL compiled system instructions delivered to the provider
            # (sha of pp.system; stage_builder.py). Additive forensic identity — no prompt body is
            # persisted — so a stored assessment can answer "what exact compiled Omi instruction set
            # produced this?". Completes the trace chain: investigation_package_id -> prompt_package_id
            # -> compiled_system_instruction_hash -> asset hashes (prompt/package) -> model.
            "compiled_system_instruction_hash": pp.manifest.get("system_prompt_sha"),
            "prompt_hash": pp.manifest.get("prompt_hash"),
            "package_hash": pp.manifest.get("package_hash"),
            "evidence_coverage_mode": pp.manifest.get("evidence_coverage_mode"),
            "evidence_tokens_est": pp.manifest.get("evidence_tokens_est"),
            "evidence_represented_accounts": pp.manifest.get("evidence_represented_accounts"),
            "evidence_omitted_accounts": pp.manifest.get("evidence_omitted_accounts"),
            "evidence_deduplicated_comments": pp.manifest.get("evidence_deduplicated_comments"),
            "model_id": inference.served_model,
            # The model the gateway ACTUALLY served (e.g. the model an OpenRouter preset routed to), when
            # the provider reports one — distinct from the configured/requested model above. Provenance
            # only; captured by the transport, never fabricated.
            "served_model": capture.get("served_model"),
            # Verification (not routing): the model we EXPECT (GPT-5 Mini) and whether the model OpenRouter
            # reported serving matches it. True proves this investigation's assessments + OMI scores came
            # from GPT-5 Mini; False means the gateway routed to a different model (surfaced + logged so a
            # silent swap can't hide); None when not applicable (no expectation set, or the Floor path).
            "served_model_expected": (getattr(settings, "openrouter_expected_model", None) or None
                                      if _provider == "openrouter" else None),
            "served_model_verified": (
                _served_model_matches(capture.get("served_model"),
                                      getattr(settings, "openrouter_expected_model", None))
                if _provider == "openrouter" else None),
            "endpoint_request_id": inference.endpoint_request_id,
            "endpoint_attempts": inference.attempts,
            "endpoint_latency_ms": round(inference.latency_ms, 2),
            "response_status": inference.response_status,
            "endpoint_error": inference.endpoint_error,
            "governor_verdict": gov.get("verdict"),
            "comprehensive_structurally_valid": sections_report.get("structurally_valid"),
            "comprehensive_unresolved_citations": sections_report.get("unresolved_total"),
            # Why a successful (HTTP 200) model response was rejected by canonical validation and fell to the
            # Floor — the exact schema errors, so a floored-after-success scan is self-explaining on the page.
            "canonical_validation_errors": capture.get("canonical_validation_errors"),
        }
        governed["investigation_trace"] = investigation_trace
        governed["metrics"] = _assessment_metrics(
            governed, gov, settings, store_ms=store_ms, reasoning_ms=reasoning_ms,
            model_backed=model_backed, prompt_meta=prompt_meta)
        governed["metrics"]["package_hash"] = ai_package.package_hash
        m = governed["metrics"]
        logger.info("analyst.assess: DONE ref=%s provider=%s model_backed=%s governor=%s revision=%s "
                    "| inference_count=%d endpoint_called=%s pkg=%s snapshot=%s coverage=%s ev_tokens=%s "
                    "| metrics total=%.0fms model=%.0fms governor+assembly=%.0fms est_completion_tokens=%d",
                    ref, prov, model_backed, gov.get("verdict"), gov.get("model_revision"),
                    investigation_trace["inference_count"], inference.endpoint_called,
                    package.package_id, snapshot.snapshot_id,
                    investigation_trace["evidence_coverage_mode"], investigation_trace["evidence_tokens_est"],
                    m["total_reasoning_ms"], m["model_ms"], m["governor_and_assembly_ms"],
                    m["est_completion_tokens"])
        # Concise production-verification summary (one line; no secrets). Answers "did this
        # investigation come from the model, via which gateway/model, at what latency/cost?".
        logger.info("analyst.verify: ref=%s transport=%s served_model=%s expected=%s served_verified=%s "
                    "preset=%s request_id=%s json_received=%s validation_passed=%s model_backed=%s "
                    "fallback=%s latency_ms=%.0f in_tok=%s out_tok=%s cost_usd=%s",
                    ref, _provider, investigation_trace["served_model"],
                    investigation_trace["served_model_expected"],
                    investigation_trace["served_model_verified"],
                    investigation_trace["openrouter_preset"], investigation_trace["endpoint_request_id"],
                    investigation_trace["json_received"], investigation_trace["validation_passed"],
                    model_backed, investigation_trace["fallback_reason"] or "-",
                    investigation_trace["endpoint_latency_ms"], investigation_trace["input_tokens"],
                    investigation_trace["output_tokens"], investigation_trace["endpoint_cost_usd"])
        # Loud, explicit alert when OpenRouter served a DIFFERENT model than expected: the assessments +
        # OMI scores were produced, but NOT by GPT-5 Mini. Never blocks the result (the model still
        # reasoned) — it makes a silent gateway/preset model swap impossible to miss in production logs.
        if investigation_trace["served_model_verified"] is False:
            logger.warning("analyst.verify: SERVED-MODEL MISMATCH ref=%s expected=%s served=%s preset=%s "
                           "— assessments/OMI scores did NOT come from the expected model; check the "
                           "OpenRouter preset's model selection.",
                           ref, investigation_trace["served_model_expected"],
                           investigation_trace["served_model"], investigation_trace["openrouter_preset"])
        return governed
    except Exception:  # noqa: BLE001 — never let the analyst break a caller
        logger.exception("omi_analyst assessment failed")
        return None


def assess_payload(
    payload: dict, *, ref: str, platform: str = "youtube", settings: Settings | None = None,
    capture: dict | None = None, completion_budget_multiplier: float = 1.0,
) -> dict | None:
    """Compatibility wrapper (P2.1 AI-runtime cutover). The **AI Investigation Runtime** is now the
    ONE orchestration layer for AI execution; every investigation executes through it. This delegates
    unchanged, so all legacy callers (routes, forensic trace/audit, training data) keep working with
    byte-identical behavior, governance, metadata, and package/prompt hashes — only the orchestration
    entry point moved into the runtime. Never raises."""
    from app.reasoning.runtime import assess_investigation

    return assess_investigation(
        payload, ref=ref, platform=platform, settings=settings, capture=capture,
        completion_budget_multiplier=completion_budget_multiplier,
    )


def runtime_status(settings: Settings | None = None) -> dict:
    """Diagnostic snapshot of the AI runtime path — which links are configured / ready.

    No secrets: ``HF_TOKEN`` presence is a boolean, never the value. Only imports the
    ``ml/`` impl when the feature is enabled (the off path stays import-free)."""
    settings = settings or get_settings()
    enabled = analyst_enabled(settings)
    endpoint = getattr(settings, "analyst_endpoint_url", None)
    token_present = bool(os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACE_HUB_TOKEN"))
    impl_ok: bool | None = (_impl() is not None) if enabled else None
    provider_sel = reasoning_provider(settings)
    # OpenRouter readiness — a preset OR a model, plus OPENROUTER_API_KEY (presence only, never the value).
    or_preset = getattr(settings, "openrouter_preset", None)
    or_model = getattr(settings, "openrouter_model", None)
    or_configured = bool(or_preset or or_model)
    or_key_present = bool(os.environ.get("OPENROUTER_API_KEY"))
    ready_hf = bool(enabled and endpoint and token_present and impl_ok is True)
    ready_or = bool(enabled and or_configured and or_key_present and impl_ok is True)
    ready_for_live_model = ready_or if provider_sel == "openrouter" else ready_hf
    active_provider = (
        "openrouter" if (provider_sel == "openrouter" and enabled and or_configured)
        else "qwen" if (enabled and endpoint) else "deterministic-floor")
    return {
        "enabled": enabled,
        # ``provider`` keeps its historical meaning — the ACTIVE/effective provider ("qwen" |
        # "openrouter" | "deterministic-floor"). ``selected_provider`` is the configured choice.
        "provider": active_provider,
        "selected_provider": provider_sel,
        "impl_importable": impl_ok,
        # Hugging Face path
        "endpoint_configured": bool(endpoint),
        "hf_token_present": token_present,
        "model_repo": getattr(settings, "analyst_hf_repo", None),
        "model_revision": getattr(settings, "analyst_hf_revision", None),
        "timeout_seconds": float(getattr(settings, "analyst_timeout_seconds", 30.0) or 30.0),
        # OpenRouter path
        "openrouter_preset_configured": bool(or_preset),
        "openrouter_model_configured": bool(or_model),
        "openrouter_configured": or_configured,
        "openrouter_api_key_present": or_key_present,
        "provider_token_present": _provider_token_present(settings),
        "provider_label": reasoning_provider_name(settings),
        "governor": "mandatory",
        "deterministic_floor": "always-on",
        # ``ready_for_live_qwen`` is kept for backward compatibility (the HF path); the provider-aware
        # answer is ``ready_for_live_model`` and the OpenRouter-specific ``ready_for_live_openrouter``.
        "ready_for_live_qwen": ready_hf,
        "ready_for_live_openrouter": ready_or,
        "ready_for_live_model": ready_for_live_model,
    }


def runtime_path(settings: Settings | None = None) -> dict:
    """The full AI runtime **dependency graph** (Sprint 016): every link from the website to Qwen
    and back, each marked ``verified`` / ``operator_action`` / ``blocked``, so *what prevents live
    Qwen reasoning* is one verifiable answer instead of a guess. Read-only; no secrets (token
    presence is a boolean); never raises. Ordered to mirror the runtime path."""
    settings = settings or get_settings()
    enabled = analyst_enabled(settings)
    endpoint = getattr(settings, "analyst_endpoint_url", None)
    token_present = bool(os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACE_HUB_TOKEN"))
    impl_ok: bool | None = (_impl() is not None) if enabled else None

    def node(step: str, ok: bool, detail: str, *, operator: bool = False) -> dict:
        return {"step": step, "status": "verified" if ok else ("operator_action" if operator else "blocked"),
                "detail": detail}

    # The Prompt Registry is the single source of truth — verified independently of the feature flag.
    try:
        from app.reasoning.prompts import default_registry
        spec = default_registry().resolve("omi_analyst", getattr(settings, "analyst_prompt_version", None))
        prompt_node = node("prompt_registry", True, f"omi_analyst {spec.prompt_version} ({spec.prompt_hash})")
    except Exception as exc:  # noqa: BLE001 — a registry failure is a real (code) blocker
        prompt_node = node("prompt_registry", False, f"resolve failed: {str(exc)[:100]}")

    try:
        from app.governor import Governor
        gov_detail = f"mandatory (constitution {Governor.constitution_version})"
    except Exception:  # noqa: BLE001
        gov_detail = "mandatory"

    common = [
        node("feature_flag", enabled, f"analyst_enabled={enabled}", operator=not enabled),
        node("analyst_impl", impl_ok is True,
             "ml/analyst importable" if impl_ok else ("import failed" if enabled else "not checked (flag off)"),
             operator=(impl_ok is None)),
        node("evidence_bundle", True, "app.evidence.Binder available"),
        prompt_node,
    ]
    # The transport links differ by provider — HF needs endpoint + HF token; OpenRouter needs a preset
    # or model + OPENROUTER_API_KEY. Everything else (Governor, Floor) is provider-agnostic.
    provider_sel = reasoning_provider(settings)
    if provider_sel == "openrouter":
        or_preset = getattr(settings, "openrouter_preset", None)
        or_model = getattr(settings, "openrouter_model", None)
        or_configured = bool(or_preset or or_model)
        or_key_present = bool(os.environ.get("OPENROUTER_API_KEY"))
        transport = [
            node("openrouter_config", or_configured,
                 f"preset={or_preset or '-'} model={or_model or '-'}" if or_configured
                 else "OMI_OPENROUTER_PRESET / OMI_OPENROUTER_MODEL unset", operator=not or_configured),
            node("openrouter_api_key", or_key_present,
                 "OPENROUTER_API_KEY present" if or_key_present else "OPENROUTER_API_KEY unset",
                 operator=not or_key_present),
            node("model", True,
                 f"openrouter {('@preset/' + or_preset) if or_preset else (or_model or '-')}"),
        ]
        configured_ok = or_configured and or_key_present
    else:
        transport = [
            node("hf_endpoint", bool(endpoint), "configured" if endpoint else "analyst_endpoint_url unset",
                 operator=not endpoint),
            node("hf_token", token_present,
                 "present" if token_present else "HF_TOKEN / HUGGINGFACE_HUB_TOKEN unset",
                 operator=not token_present),
            node("model", True,
                 f"{getattr(settings, 'analyst_hf_repo', None)}@{getattr(settings, 'analyst_hf_revision', None) or 'main'}"),
        ]
        configured_ok = bool(endpoint) and token_present

    nodes = common + transport + [
        node("governor", True, gov_detail),
        node("deterministic_floor", True, "always-on fallback"),
    ]
    prompt_ok = prompt_node["status"] == "verified"
    ready_hf = bool(enabled and endpoint and token_present and impl_ok is True and prompt_ok)
    ready_model = bool(enabled and configured_ok and impl_ok is True and prompt_ok)
    active_provider = (
        "openrouter" if (provider_sel == "openrouter" and enabled
                         and (getattr(settings, "openrouter_preset", None)
                              or getattr(settings, "openrouter_model", None)))
        else "qwen" if (enabled and endpoint) else "deterministic-floor")
    return {
        "selected_provider": provider_sel,
        "ready_for_live_qwen": ready_hf,          # kept for backward compatibility (HF path)
        "ready_for_live_model": ready_model,      # provider-aware readiness
        "active_provider": active_provider,
        "nodes": nodes,
        "blockers": [n["step"] for n in nodes if n["status"] != "verified"],
        "governor": "mandatory",
        "deterministic_floor": "always-on",
    }


# --------------------------------------------------------------------------- #
# Caching on the Investigation row (SAVEPOINT-isolated best-effort write)
# --------------------------------------------------------------------------- #
def cached_assessment(inv) -> dict | None:
    payload = inv.payload_json or {}
    entry = payload.get(CACHE_KEY)
    if isinstance(entry, dict) and entry.get("assessment"):
        return entry
    return None


#: Per-account fields behind the admin gate. The eight-signal breakdown is an UNFINISHED feature
#: (product decision 2026-07-29): a customer sees each account's OMI score, tier and written read,
#: and not the per-dimension scoring behind it. `confidence` is part of the same block and goes with
#: it. Flip the feature on by emptying this set; nothing else needs touching.
#:
ADMIN_ONLY_ACCOUNT_FIELDS = frozenset({"signals", "confidence"})

#: Fields that are admin-only FOREVER, not pending a product decision. Kept in a separate set from
#: the one above precisely so "empty the set to ship the breakdown" stays a one-line change that
#: cannot also release these by accident.
#:
#: These are the verification pass's working notes (app/reasoning/grounding.py): which checks a
#: paragraph failed, and the refused paragraph itself. An operator needs both to see whether the
#: model is drifting. A customer shown the refused text beside the notice explaining that it was
#: refused would simply read the refused text, which defeats the entire point of refusing it.
NEVER_PUBLIC_ACCOUNT_FIELDS = frozenset({"grounding", "assessment_unverified"})


def assessment_for_viewer(assessment: dict | None, *, is_admin: bool) -> dict | None:
    """The assessment as this viewer is allowed to see it.

    Filtered on SERVE, never on persist, and that distinction is the whole point. The signals stay
    in ``payload_json``, so the day the breakdown ships to customers every investigation already
    generated has one, and no model output anyone paid for is thrown away. Stripping at persist time
    would make the gate irreversible for all history.

    It also stops a 150-account investigation shipping the better part of 150 KB of JSON that the
    page renders nowhere: eight dimensions per account, each with a reason up to 240 chars.

    Returns a copy. Mutating the cached entry in place would poison it for the next reader (it is the
    live ``payload_json`` object) and could be flushed back to the database by SQLAlchemy.
    """
    if is_admin or not isinstance(assessment, dict):
        return assessment
    rows = assessment.get("commenter_assessments")
    if not isinstance(rows, list) or not rows:
        return assessment
    hidden = ADMIN_ONLY_ACCOUNT_FIELDS | NEVER_PUBLIC_ACCOUNT_FIELDS
    out = dict(assessment)
    out["commenter_assessments"] = [
        {k: v for k, v in r.items() if k not in hidden}
        if isinstance(r, dict) else r
        for r in rows
    ]
    return out


def entry_is_model_backed(entry: dict | None) -> bool:
    """Whether a CACHED analyst entry is a real model-backed assessment (vs the deterministic Floor).
    Prefer the explicit trace flag; fall back to the provider label for entries persisted before it."""
    if not isinstance(entry, dict):
        return False
    a = entry.get("assessment") or {}
    tr = a.get("investigation_trace") or {}
    if isinstance(tr.get("model_backed"), bool):
        return tr["model_backed"]
    prov = str(entry.get("provider") or "")
    return bool(prov) and "fallback" not in prov and "deterministic" not in prov


def entry_has_model_account_reads(entry: dict | None) -> bool:
    """Whether this entry's PER-ACCOUNT reads are the model's own prose.

    Distinct from :func:`entry_is_model_backed`, which answers a question about the SYNTHESIS
    wrapper. The two come apart on the salvage path, and that gap is the whole reason this exists:
    ``validate_comprehensive_model_output`` is all-or-nothing, so a reply whose twenty per-account
    paragraphs were perfect and whose wrapper was missing one field floors the wrapper while
    ``_salvaged_account_reads`` keeps the rows.

    ``commenter_assessments`` is only ever populated from a model-backed part or from an explicit
    salvage, so a non-empty list means real model prose either way.
    """
    if not isinstance(entry, dict):
        return False
    a = entry.get("assessment") or {}
    return bool(a.get("commenter_assessments"))


def entry_warrants_auto_regeneration(entry: dict | None) -> bool:
    """Whether an automatic, unrequested, FULL BILLABLE re-run would actually buy anything.

    THIS IS THE MONEY QUESTION, and it is deliberately not the same one
    :func:`entry_is_model_backed` answers.

    Reported live: a 100-account scan finished, the customer read its per-account verdicts, and then
    watched the panel reset to "1 of 4" and analyse the whole thing again. The chain was: batch 1's
    wrapper failed validation, its rows were salvaged, ``_merge_batch_parts`` marked the merged entry
    non-model-backed on the strength of that one part, and the route's floor self-heal keys on
    exactly that flag. So it set ``refresh=True``, which also bypasses the live-run guard, and
    submitted a second full run of every batch. Nothing outside the OpenRouter bill would have shown
    it, and the customer's only symptom was the UI apparently restarting.

    A regeneration is worth spending only when there is nothing of the model's to lose: no
    per-account reads at all. When the reads ARE there, the customer already has the substance they
    paid for and what is missing is the synthesis paragraph above them, which is not worth a second
    run of every batch nobody asked for. `AiUnavailable summaryOnly` already says so on the page,
    and the Retry button is still there for a customer who decides otherwise. That is the difference
    that matters: their choice, not ours.
    """
    if entry_is_model_backed(entry):
        return False
    return not entry_has_model_account_reads(entry)


# Slugs whose FLOORED cache we've already auto-regenerated once this process. Kept as a cheap local
# short-circuit in front of the durable claim below, so a poll loop on one worker does not hit the
# database to be told "no" every 2.5 seconds.
_floor_autorefreshed: set[str] = set()
_floor_autorefresh_lock = threading.Lock()

#: Where the durable "we already auto-healed this one" marker lives inside ``Investigation.payload_json``.
FLOOR_HEAL_KEY = "analyst_floor_autoheal_v1"


def claim_floor_autorefresh(slug: str, session=None, inv=None) -> bool:
    """Return True exactly ONCE per investigation: the caller may trigger one automatic regeneration.

    An automatic regeneration is a full billable run that the customer did not ask for, so "once"
    has to mean once, and a process-local set cannot deliver that. It was one: N web workers each
    held their own copy, so N of them each granted a regeneration for the same floored scan, and a
    restart wiped the set and granted another. Nothing anywhere would have shown that except the
    OpenRouter bill. Exactly the shape of bug the durable generation lease was introduced to fix,
    still present one function away from it.

    The marker is persisted on the investigation. The in-process set stays in front of it purely to
    keep a 2.5s poll loop off the database; correctness comes from the stored value, so passing no
    session degrades to the old process-local behaviour rather than failing open on every call.
    """
    with _floor_autorefresh_lock:
        if slug in _floor_autorefreshed:
            return False
        _floor_autorefreshed.add(slug)

    if session is None or inv is None:
        return True
    try:
        if (inv.payload_json or {}).get(FLOOR_HEAL_KEY):
            return False
        # SAVEPOINT-isolated and reassigning the whole dict, the same shape as `_write_lease`: a
        # marker write must never break the request it rides on, and SQLAlchemy only notices a JSON
        # column that was reassigned.
        with session.begin_nested():
            payload = {**(inv.payload_json or {}),
                       FLOOR_HEAL_KEY: {"at": datetime.now(timezone.utc).isoformat()}}
            inv.payload_json = payload
            session.add(inv)
        return True
    except Exception:  # noqa: BLE001
        # A failed read or write must not strand a genuinely floored scan with no attempt at all.
        # The in-process set above still bounds it to one per worker, which is the old behaviour.
        logger.exception("analyst: could not record the floor auto-heal claim for %s", slug)
        return True


def is_generation_inflight(slug: str) -> bool:
    """Whether a background generation for this investigation is currently running (the in-flight guard)."""
    with _autogen_lock:
        return slug in _autogen_inflight


class AnalystFellBackToFloor(Exception):
    """Raised NOWHERE. It exists only to give the error tracker a typed, greppable event for a
    floored assessment, which is otherwise a completely silent failure (see ``_report_floor``)."""


def _report_floor(inv, assessment: dict, provider: str) -> None:
    """Make a Floor result LOUD. It is otherwise invisible by construction.

    A floored assessment is a *successful* code path: the model was unreachable or its output was
    rejected, the deterministic Floor stood in, and nothing raised. ``background._wrap`` only reports
    exceptions, so the tracker never hears about it, and the only symptom is a customer reading "the
    AI analysis isn't ready yet" on every investigation. That is exactly how this went unnoticed
    across every scan until someone looked at the screen.

    The trace already classifies WHY (``fallback_reason``), so log that rather than a bare "it
    floored", and hand the tracker a typed exception so the alert is greppable and groupable.
    Best-effort throughout: monitoring must never be able to fail the thing it monitors.
    """
    try:
        trace = (assessment or {}).get("investigation_trace") or {}
        # Fall back to classifying here as well as at the trace-building site. An entry can reach
        # this function from a path that did not build a full trace (a batched merge, a rehydrated
        # cache entry), and "unclassified" in an alert is barely better than no alert at all.
        reason = trace.get("fallback_reason") or _classify_floor(trace)
        slug = getattr(inv, "slug", "?")
        logger.error(
            "analyst FLOORED inv=%s provider=%s reason=%s status=%s model=%s "
            "(the customer sees the 'analysis not ready' notice for this investigation)",
            slug, provider, reason, trace.get("response_status"), trace.get("served_model"),
        )
        capture_exception(AnalystFellBackToFloor(f"{slug}: {reason}"))
    except Exception:  # noqa: BLE001 — a broken alert must never break the scan
        logger.exception("failed to report a floored analyst assessment")


def persist_assessment(session, inv, assessment: dict, provider: str) -> dict:
    """Cache the assessment inside payload_json. SAVEPOINT-isolated so a write hiccup
    can never corrupt the surrounding transaction (Platform Guardian §4)."""
    entry = {
        "assessment": assessment,
        "provider": provider,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    # Alert BEFORE the write, so a persist failure cannot also swallow the alert. Reuses the same
    # predicate the route and the UI use, so all three agree on what "the model wrote this" means.
    #
    # A RUN STILL IN PROGRESS HAS NOT FAILED, so it is not alerted on. This function is called once
    # per batch that lands, and one floored batch makes the merged entry non-model-backed for the
    # whole rest of the run, so a four-batch scan raised FOUR AnalystFellBackToFloor events and four
    # ERROR logs for a single fault. An alert that fires four times per fault is the same problem as
    # one that fires on success: it is the reason people stop reading them. A later batch can also
    # still land and make the entry model-backed, which would make the earlier alerts simply wrong.
    # The final merge sets `complete`, so the settled state is still reported exactly once.
    _batching = (assessment or {}).get("batching") or {}
    _run_finished = (not _batching) or bool(_batching.get("complete"))
    if _run_finished and not entry_is_model_backed(entry):
        _report_floor(inv, assessment, provider)
    try:
        with session.begin_nested():
            # Reassign so SQLAlchemy detects the JSON mutation.
            inv.payload_json = {**(inv.payload_json or {}), CACHE_KEY: entry}
            session.add(inv)
    except Exception:  # noqa: BLE001 — caching is best-effort
        logger.exception("failed to persist analyst assessment for inv=%s", getattr(inv, "slug", "?"))
    return entry


_autogen_inflight: set[str] = set()
_autogen_lock = threading.Lock()


#: Durable "somebody is generating this right now" marker, kept OUTSIDE the assessment cache so it
#: cannot be mistaken for a result: ``cached_assessment`` only returns an entry carrying an
#: ``assessment``, and this key never has one.
LEASE_KEY = "analyst_run_lease_v1"


def generation_lease_is_live(inv) -> bool:
    """Whether some process claimed this investigation's generation recently.

    THIS CLOSES THE STARTUP WINDOW, which the batch heartbeat cannot. ``batched_run_looks_alive``
    reads ``batching.heartbeat``, and that only exists once the FIRST batch has been persisted,
    which is minutes into a run. Until then a batched generation is completely invisible to any
    other process: ``maybe_autogenerate`` schedules the run when the scan finishes, the user opens
    the investigation seconds later, that POST lands on a different worker whose ``_autogen_inflight``
    set is empty, and it submits a SECOND full run. That is the "it scans twice" report, and it bills
    twice.
    """
    lease = (getattr(inv, "payload_json", None) or {}).get(LEASE_KEY)
    if not isinstance(lease, dict):
        return False
    beat = lease.get("heartbeat")
    if not isinstance(beat, str) or not beat:
        return False
    try:
        seen = datetime.fromisoformat(beat.replace("Z", "+00:00"))
    except ValueError:
        return False
    if seen.tzinfo is None:
        seen = seen.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - seen).total_seconds() < batch_heartbeat_stale_sec()


def claim_generation_lease(session, inv, run_id: str) -> bool:
    """Take the lease unless a live one is already held by someone else. Returns whether we own it.

    Read-modify-write rather than a locked row, deliberately. It narrows the duplicate-run window
    from the length of a first batch (minutes) to the length of this function (milliseconds), and
    two claims landing inside that remaining window are already handled downstream by
    ``_entry_is_ahead``, which stops the loser publishing over the leader. A row lock here would buy
    the last few milliseconds at the cost of holding a write lock on the investigation across a
    multi-minute generation if anything ever moved the release.
    """
    if generation_lease_is_live(inv) and (inv.payload_json or {}).get(LEASE_KEY, {}).get(
            "run_id") != run_id:
        return False
    _write_lease(session, inv, {"run_id": run_id,
                                "heartbeat": datetime.now(timezone.utc).isoformat()})
    return True


def touch_generation_lease(session, inv, run_id: str) -> None:
    """Re-stamp our own lease so a long run does not look abandoned while it is working.

    THE LEASE HEARTBEAT WAS WRITTEN ONCE, AT CLAIM TIME, AND NEVER AGAIN. Liveness is judged against
    that single stamp, so the lease expired a fixed number of seconds after the run STARTED rather
    than a fixed number of seconds after it last did anything. With batches measured at 857s and a
    four-batch scan running close to an hour, the lease went stale while the run was healthy and
    mid-flight, and another worker was then free to claim it and start a duplicate billable run.

    Widening the staleness window cannot fix this, only postpone it: a long enough scan always
    outlives a fixed window measured from its start. The heartbeat has to be evidence of RECENT
    work, so it is re-stamped every time a batch lands.

    Never raises, and never steals: if the stored lease belongs to somebody else we leave it alone,
    exactly like ``release_generation_lease``.
    """
    try:
        if (inv.payload_json or {}).get(LEASE_KEY, {}).get("run_id") != run_id:
            return
        _write_lease(session, inv, {"run_id": run_id,
                                    "heartbeat": datetime.now(timezone.utc).isoformat()})
    except Exception:  # noqa: BLE001 — advisory; a failed touch must never sink a persisted batch
        logger.exception("analyst: could not refresh the generation lease")


def release_generation_lease(session, inv, run_id: str) -> None:
    """Drop our lease so a later refresh is not made to wait out the staleness window."""
    if (inv.payload_json or {}).get(LEASE_KEY, {}).get("run_id") != run_id:
        return  # someone else's lease, or already replaced; leave it alone
    _write_lease(session, inv, None)


def _write_lease(session, inv, lease: dict | None) -> None:
    """Best effort, and SAVEPOINT-isolated: a lease write must never break the surrounding work."""
    try:
        with session.begin_nested():
            payload = {**(inv.payload_json or {})}
            if lease is None:
                payload.pop(LEASE_KEY, None)
            else:
                payload[LEASE_KEY] = lease
            inv.payload_json = payload  # reassign so SQLAlchemy sees the JSON mutation
            session.add(inv)
    except Exception:  # noqa: BLE001
        logger.exception("analyst.lease: write failed for inv=%s", getattr(inv, "slug", "?"))


# --------------------------------------------------------------------------- #
# Batched inference — a single OpenRouter request carries at most N accounts.
# --------------------------------------------------------------------------- #
# WHY: per-account quality (and score individuality) degrades as one generation is asked to reason
# over more accounts — the model starts batching mentally, and scores collapse toward one number.
# Splitting a big selection into ≤50-account requests keeps every generation in the regime where the
# Dossier-Loop protocol holds, and running the batches in PARALLEL keeps the wall-clock flat. Results
# merge in batch order (first-to-last) and persist progressively, so the UI shows batch 1's accounts
# while later batches are still generating.


def _split_batches(payload: dict, batch_size: int, *, batches: int = 0) -> list[dict] | None:
    """Split an investigation payload into per-request chunk payloads, or None when it fits in one.

    A FIXED SIZE, remainder last: 100 accounts is 4 requests of 25, 200 is 8 of 25, and 92 is
    25/25/25/17. `app.reasoning.batch_plan.plan_batches` owns the arithmetic.

    THE SIZE IS WHAT BOUNDS THE REQUEST, AND THE REQUEST IS WHAT FAILS. A previous revision divided
    the selection into a fixed NUMBER of batches instead, which made the size grow with the
    selection: a 197-account scan became four calls of roughly 50 accounts each and every one of
    them came back empty within about thirty seconds. Measured on this deployment, 25 per call
    works. With a fixed size a larger scan is more requests, never a larger request.

    ``batches`` is accepted and ignored. It is the old fixed-count argument, kept so an existing
    caller or test cannot silently start passing something that no longer means anything.

    Selection order is preserved. Each chunk shares the investigation's non-account context; only
    ``video.commenters`` is sliced, since the evidence composer renders the Accounts table (and the
    per-account evidence budget) from that list.
    """
    video = payload.get("video") or {}
    commenters = video.get("commenters") or []
    size = max(1, int(batch_size or BATCH_SIZE))
    if len(commenters) <= size:
        return None
    chunks: list[dict] = []
    for lo, hi in plan_batches(len(commenters), size):
        chunk_payload = {k: v for k, v in payload.items() if k != CACHE_KEY}
        chunk_payload["video"] = {**video, "commenters": commenters[lo:hi]}
        chunks.append(chunk_payload)
    return chunks


def _tier_for_score(score: int) -> str:
    return "low" if score <= 24 else "moderate" if score <= 49 else "elevated" if score <= 74 else "high"


def _merge_batch_parts(parts: list[dict | None], *, batch_size: int, done: int,
                       run_finished: bool = False, run_id: str | None = None,
                       attempts: dict[int, int] | None = None,
                       running: set[int] | None = None) -> dict | None:
    """Merge per-batch assessments into ONE progressive assessment, strictly first-to-last.

    ``parts`` is indexed by batch; entries still pending (or failed) are None. The first completed
    part supplies the executive wrapper + domain sections; commenter_assessments concatenate in batch
    order; the OVERALL omi_score is recomputed as the account-count-weighted mean of the completed
    batches' overall scores (each batch's overall already synthesizes ITS accounts, so the weighted
    mean preserves the model's judgment at full-selection scale). Token/cost telemetry sums across
    batches. Returns None until at least one part exists."""
    completed = [(i, p) for i, p in enumerate(parts) if p is not None]
    if not completed:
        return None
    base = json.loads(json.dumps(completed[0][1], default=str))

    merged_accounts: list[dict] = []
    for _i, p in completed:
        merged_accounts.extend(p.get("commenter_assessments") or [])
    base["commenter_assessments"] = merged_accounts

    # Overall = weighted mean of each batch's overall score by its account count (model judgment,
    # rescaled to the whole selection — never pushed down onto any individual account).
    weights = []
    for _i, p in completed:
        n = len(p.get("commenter_assessments") or []) or 1
        s = p.get("omi_score")
        if isinstance(s, (int, float)):
            weights.append((n, float(s)))
    if weights:
        total_n = sum(n for n, _ in weights)
        overall = int(round(sum(n * s for n, s in weights) / total_n))
        base["omi_score"] = max(0, min(100, overall))
        base["suspicion_tier"] = _tier_for_score(base["omi_score"])

    # Evidence / uncertainty: concatenate across batches (bounded so the payload stays readable).
    for key, cap in (("evidence_for", 16), ("evidence_against", 16),
                     ("uncertainty", 12), ("what_would_change_this", 12)):
        acc: list = []
        seen: set[str] = set()
        for _i, p in completed:
            for item in (p.get(key) or []):
                marker = json.dumps(item, default=str, sort_keys=True)
                if marker not in seen:
                    seen.add(marker)
                    acc.append(item)
        base[key] = acc[:cap]

    # Completion: sums across completed batches; complete only when EVERY batch landed and completed.
    total_batches = len(parts)
    rep = sum((p.get("completion") or {}).get("represented_commenters") or 0 for _i, p in completed)
    ass = sum((p.get("completion") or {}).get("assessed_commenters") or 0 for _i, p in completed)
    all_complete = (len(completed) == total_batches) and all(
        (p.get("completion") or {}).get("complete") for _i, p in completed)
    # THE REASON MUST DESCRIBE THE MERGE, NOT BATCH ONE.
    #
    # `base` is the first completed batch's payload, so every unstated key here is inherited from it,
    # and `reason` is the one a reader actually sees. A four-batch run whose first batch was clean
    # and whose third floored therefore rendered "Complete, every commenter received AI reasoning"
    # inside a box whose own heading said the coverage was partial. The counts were merged and the
    # sentence explaining them was not.
    _reason = (base.get("completion") or {}).get("reason")
    if not all_complete:
        _still_running = total_batches - len(completed)
        _empty = sum(1 for _i, p in completed if not (p.get("commenter_assessments") or []))
        _short = max(0, rep - ass)
        if _still_running > 0:
            _reason = (
                f"{len(completed)} of {total_batches} passes have landed. "
                f"{_still_running} more {'is' if _still_running == 1 else 'are'} still running."
            )
        elif _empty:
            _reason = (
                f"{_empty} of {total_batches} passes came back empty, so their accounts have no "
                "written read. Every score shown is final."
            )
        elif _short:
            # EVERY PASS LANDED AND SOME ACCOUNTS STILL DID NOT GET A READ.
            #
            # Caught in an end-to-end run: `complete` was false with `missing_commenters: 2`, while
            # the reason inherited from batch one still read "Complete, every commenter in the
            # investigation received AI reasoning". The two earlier branches only cover passes that
            # are missing or empty, and a pass can land, be counted, and still return fewer accounts
            # than it was shown (the model skips one, or grounding withholds it).
            _reason = (
                f"{_short} of {rep} accounts did not receive a written read, though every pass "
                "landed. Every score shown is final."
            )
        else:
            # Not complete for a reason none of the above explains (the output did not certify).
            # Whatever it is, it is NOT "complete", and inheriting batch one's sentence said exactly
            # that inside a box whose own heading said otherwise.
            _reason = (
                "The analysis finished but did not fully certify. Every score shown is final."
            )
    base["completion"] = {**(base.get("completion") or {}),
                          "represented_commenters": rep, "assessed_commenters": ass,
                          "reason": _reason,
                          # Inherited from batch one otherwise, where it meant "the accounts THIS
                          # batch still owes". Merged, that read as 25 remaining beside 25 assessed.
                          # Across the run, what is still owed is whatever the landed batches were
                          # shown and did not assess; the batches yet to run are counted in passes,
                          # by the progress strip, which is the only place that number belongs.
                          "missing_commenters": max(0, rep - ass),
                          "estimated_remaining_commenters": max(0, rep - ass),
                          "complete": bool(all_complete)}

    # Trace: keep the base trace, overlay batch telemetry + summed usage; model_backed = every
    # completed batch model-backed (a floored batch marks the whole merged result non-model-backed
    # so the self-heal path can regenerate it).
    tr = dict(base.get("investigation_trace") or {})
    in_tok = out_tok = tot_tok = 0
    cost = 0.0
    have_usage = False
    batch_traces: list[dict] = []
    # model_backed asks "is the prose in this entry the model's?", and for a run still in progress the
    # answer is about the batches that HAVE landed, not the ones still queued.
    #
    # This used to be seeded `len(completed) == total_batches`, so every partial merge came out
    # model_backed=False even when every completed batch was genuinely model-authored. A 100-account
    # scan whose first batch returned 25 real assessments was therefore served as though the Floor had
    # written it, and the UI refused to render the accounts it already had until the whole run ended.
    #
    # Only once the run is OVER does a missing batch make the entry non-model-backed, which is what the
    # self-heal path keys on to regenerate it.
    all_model_backed = bool(completed)
    for i, p in completed:
        pt = p.get("investigation_trace") or {}
        if not pt.get("model_backed"):
            all_model_backed = False
        for k_src, agg in (("input_tokens", "in"), ("output_tokens", "out"), ("total_tokens", "tot")):
            v = pt.get(k_src)
            if isinstance(v, (int, float)):
                have_usage = True
                if agg == "in":
                    in_tok += int(v)
                elif agg == "out":
                    out_tok += int(v)
                else:
                    tot_tok += int(v)
        c = pt.get("endpoint_cost_usd")
        if isinstance(c, (int, float)):
            cost += float(c)
        batch_traces.append({
            "batch": i + 1, "accounts": len(p.get("commenter_assessments") or []),
            "model_backed": pt.get("model_backed"), "served_model": pt.get("served_model"),
            "endpoint_request_id": pt.get("endpoint_request_id"),
            "input_tokens": pt.get("input_tokens"), "output_tokens": pt.get("output_tokens"),
            "endpoint_cost_usd": pt.get("endpoint_cost_usd"),
            "endpoint_latency_ms": pt.get("endpoint_latency_ms"),
        })
    # MISSING COVERAGE IS NOT THE SAME THING AS FLOORED, and conflating them restarted finished
    # scans. A run that landed 3 of 4 batches used to be marked non-model-backed on the strength of
    # the fourth, which is the exact signal the route's floor self-heal keys on. So the moment the
    # scan finished, the route regenerated the WHOLE thing: the customer watched a completed result
    # start batching again from "1 of 4", and it billed a second full run every time.
    #
    # `model_backed` answers "is the prose in this entry the model's?", and for three real batches it
    # is yes. How much of the selection was covered is a separate fact, carried by `landed` below and
    # rendered by IncompleteCoverageNotice, which offers a retry the user chooses to spend.
    if have_usage:
        tr["input_tokens"], tr["output_tokens"], tr["total_tokens"] = in_tok, out_tok, tot_tok
        tr["endpoint_cost_usd"] = round(cost, 6)
    tr["model_backed"] = bool(all_model_backed)
    # Real per-account reads under a floored wrapper. Two ways a merged entry gets here and both are
    # worth showing: one batch of four floored (so the merged entry is not model-backed while three
    # batches of reads are perfectly good), or a single response's wrapper failed validation and
    # `_salvaged_account_reads` kept its rows. `commenter_assessments` is only ever populated from a
    # model-backed part or an explicit salvage, so anything in this list IS the model's prose and
    # showing it is not presenting the Floor as AI reasoning.
    tr["account_reads_salvaged"] = bool(not all_model_backed and merged_accounts)
    tr["inference_count"] = len(completed)
    tr["batches"] = {"total": total_batches, "done": done, "size": batch_size,
                     "traces": batch_traces}
    tr["commenters_assessed"] = ass
    base["investigation_trace"] = tr

    # The progressive marker the route + UI read: how far the batched generation has come.
    #
    # ``complete`` means THE RUN IS OVER, not "every batch succeeded" — ``run_finished`` is set on the
    # final merge even when some batches produced nothing. That distinction is load-bearing: an
    # incomplete marker makes the route treat the entry as an interrupted run and resubmit a FULL
    # regeneration on every poll, so a batch that fails deterministically would bill OpenRouter for a
    # fresh run every few seconds, forever, and the client would poll for a batch that is never coming.
    # ``landed`` is how many batches actually PRODUCED accounts, which is the coverage figure.
    # ``done`` cannot serve that purpose: it counts batches ATTEMPTED (so the progress readout moves
    # when a batch fails rather than freezing), which means ``done == total`` on any finished run,
    # successful or not. ``landed`` < ``total`` with ``complete`` true is the honest "finished, but N
    # batches yielded nothing" state; the UI says so and offers a retry the user chooses to spend.
    #
    # ``run_id`` + ``heartbeat`` make a live run visible ACROSS PROCESSES, which the in-flight set
    # cannot do (see ``batched_run_looks_alive``). Without them a second worker saw an incomplete
    # entry, concluded the run had been interrupted, and started a duplicate whose first write
    # replaced "3 of 4" with "1 of 4" and no accounts.
    # `landed` counts batches that PRODUCED ACCOUNTS, not batches that returned an object. It used
    # to be `len(completed)`, which is every part that is not None, and a FLOORED batch is not None:
    # it returns a complete deterministic Floor assessment carrying zero accounts. So a run where
    # three of four batches floored reported `landed == 4`, restating exactly the lie `done` already
    # tells. Two consequences, both live: the coverage figure was wrong, and `IncompleteCoverageNotice`
    # is gated on `landed < total`, so the one notice whose entire job is to say "finished, but N
    # batches yielded nothing" could never fire in the case it was written for.
    landed = sum(1 for _i, p in completed if (p.get("commenter_assessments") or []))
    base["batching"] = {"total": total_batches, "done": done, "landed": landed,
                        "batch_size": batch_size,
                        "complete": bool(run_finished) or done >= total_batches,
                        "run_id": run_id,
                        "heartbeat": datetime.now(timezone.utc).isoformat()}
    # THE PER-BATCH RECORD, and the reason it is here rather than derived by each reader.
    #
    # `total` / `done` / `landed` above are three numbers that look interchangeable and are not, and
    # every reader that guessed wrong shipped a bug: a strip reading "3 of 4 done" beside 25
    # accounts, a coverage notice that could never fire, a counter that ran backwards. This list says
    # what actually happened to each request, so a caller never has to infer it from a count. The
    # three legacy keys stay for entries written before this existed and for callers not yet moved
    # over; `app.reasoning.batch_plan` is what derives everything from the list.
    base["batching"]["batches"] = [
        {"index": i,
         # WHICH BATCH IS ON THE WIRE, said by the only party that knows.
         #
         # This used to be "pending" for every incomplete batch, and the client's own reconstruction
         # was the only thing that ever produced "running" — but the client prefers this record
         # whenever it exists, so the moment the record shipped, "Waiting on batch N of M"
         # became unreachable on every modern entry. A reader watching a long batch was told
         # nothing at all about what the run was doing.
         #
         # In flight is not the same as "the first one without a result": a batch that floored to
         # None is finished and failed, and under concurrency several are in flight at once. So the
         # caller passes the set it is actually holding open rather than having this infer it.
         "state": ("done" if (p.get("commenter_assessments") or []) else "failed")
                  if p is not None
                  else ("failed" if run_finished
                        else ("running" if i in (running or set()) else "pending")),
         "accounts": len(p.get("commenter_assessments") or []) if p is not None else 0,
         # WHICH ATTEMPT THIS BATCH IS ON. Reported live: "the fourth batch has been running about
         # ten minutes and the others were quick." A batch that failed once and is now on its
         # second attempt looked exactly like one still on its first, because nothing recorded the
         # difference. One batch can legitimately occupy a long time across attempts (a per-request
         # timeout of 1800s, up to two in-transport retries on 429/5xx, then one whole re-attempt),
         # and through all of it the strip said only "batch 4 of 4".
         "attempt": int((attempts or {}).get(i, 1) or 1)}
        for i, p in enumerate(parts)
    ]
    return base


#: How long a batched run's entry may go without a progress write before another worker is allowed
#: to conclude it died and regenerate.
#:
#: THIS IS DERIVED FROM THE PER-CALL TIMEOUT, and it must be. The heartbeat is written when a batch
#: LANDS, so between two writes sits one whole model call. A fixed 420 was therefore a bet that no
#: batch would ever take seven minutes, and it lost: a measured 25-account batch took 857s, so for
#: 437 of those seconds a perfectly healthy run looked dead. Another worker then concluded it had
#: crashed and started a duplicate, which republished "1 of 4" over the "3 of 4" the customer was
#: reading and billed a second run to do it.
#:
#: A run cannot be declared dead until longer than one model call could possibly take, so the floor
#: is the configured timeout plus a margin for the persist that follows it. Raising
#: OMI_ANALYST_TIMEOUT_SECONDS now moves this automatically instead of silently re-opening the bug.
#: THE FLOOR IS 1800, NOT 420, AND THE ASYMMETRY IS THE WHOLE ARGUMENT.
#:
#: Declaring a live run dead too EARLY starts a duplicate: a second full billable generation, and a
#: customer watching results they were reading get republished from "1 of 4". Declaring a genuinely
#: crashed run dead too LATE costs a delayed self-heal on a run that produced nothing, and the Retry
#: button is right there. Those two mistakes are nowhere near equally expensive, so the window is
#: sized for the expensive one.
#:
#: The old floor could not survive this deployment's own measurements. A batch has been measured at
#: 857s. `Settings.analyst_timeout_seconds` defaults to 500, so a service where
#: OMI_ANALYST_TIMEOUT_SECONDS is not actually applied (render.yaml commits 1800, and CLAUDE.md
#: records that a Render dashboard value can disagree with what is committed) computed a window of
#: max(420, 800) = 800s. An 857s batch outlives that by a minute, mid-run, while perfectly healthy.
#: A guard whose correctness depends on an env var being right is not a guard.
BATCH_HEARTBEAT_MARGIN_SEC = 300
BATCH_HEARTBEAT_STALE_SEC = 1800     # the floor, and what a caller with no settings falls back to


def batch_heartbeat_stale_sec(settings: Settings | None = None) -> float:
    """How long since the last progress write before a batched run counts as dead."""
    try:
        timeout = float(getattr(settings or get_settings(), "analyst_timeout_seconds", 0) or 0)
    except Exception:  # noqa: BLE001 — liveness must never raise; fall back to the floor
        timeout = 0.0
    return max(BATCH_HEARTBEAT_STALE_SEC, timeout + BATCH_HEARTBEAT_MARGIN_SEC)


def batched_run_looks_alive(entry: dict | None) -> bool:
    """Whether an incomplete batched entry is being actively worked on by SOME process.

    ``is_generation_inflight`` answers this for the current process only, and that is not enough:
    the in-flight set is per-process, so with more than one worker (or after a restart) a live run
    is invisible to whichever worker handles the next poll. That worker treated the partial entry as
    an interrupted run and launched a duplicate, and the duplicate's first progress write published
    ``done=1`` with one batch of accounts over the ``done=3`` the user was already looking at.

    A fresh heartbeat is durable evidence that someone is still writing, whoever and wherever they
    are. Absent heartbeat means the entry predates this field, and is treated as NOT alive so an
    genuinely interrupted old run still self-heals.
    """
    batching = ((entry or {}).get("assessment") or {}).get("batching") or {}
    if not batching or batching.get("complete"):
        return False
    beat = batching.get("heartbeat")
    if not isinstance(beat, str) or not beat:
        return False
    try:
        seen = datetime.fromisoformat(beat.replace("Z", "+00:00"))
    except ValueError:
        return False
    if seen.tzinfo is None:
        seen = seen.replace(tzinfo=timezone.utc)
    age = (datetime.now(timezone.utc) - seen).total_seconds()
    return age < batch_heartbeat_stale_sec()


def _scored_accounts(assessment: dict | None) -> int:
    return len(((assessment or {}).get("commenter_assessments")) or [])


def _entry_is_ahead(existing: dict | None, mine: dict, run_id: str | None) -> bool:
    """Whether a stored entry belongs to a different, still-live run that has more results than we do.

    Every clause is a reason not to defer, so the normal single-run path is untouched:

    * no stored entry, or no batching on it: nothing to lose, write.
    * same ``run_id``: our own earlier write, and ours must always advance.
    * not alive: a crashed or interrupted run, which is exactly what we are here to replace.
    * fewer accounts, and no further through the run: we lose nobody's work by publishing.

    ON EQUAL ACCOUNT COUNTS, HOW FAR THROUGH THE RUN EACH ONE IS BREAKS THE TIE, and that clause is
    not hypothetical. A leader that had attempted three batches and got accounts out of one held 25
    accounts at "3 of 4"; a duplicate starting fresh held 25 at "1 of 4". Equal counts meant the
    duplicate published, and the customer watched the counter run backwards. Comparing accounts
    alone cannot see that, because the two runs genuinely had the same number of them.
    """
    stored = ((existing or {}).get("assessment") or {})
    batching = stored.get("batching") or {}
    if not batching:
        return False
    if run_id and batching.get("run_id") == run_id:
        return False
    if not batched_run_looks_alive(existing):
        return False
    stored_accounts, my_accounts = _scored_accounts(stored), _scored_accounts(mine)
    if stored_accounts != my_accounts:
        return stored_accounts > my_accounts
    return int(batching.get("done") or 0) > int(((mine or {}).get("batching") or {}).get("done") or 0)


#: Where an in-flight run's per-batch results live inside ``Investigation.payload_json``.
#:
#: WHY THIS EXISTS. A batched run held every landed batch in a local ``parts`` list and nothing else.
#: The merged view was persisted, but the per-batch pieces the merge is built FROM were not, so a run
#: that died mid-flight — a redeploy (``background.shutdown`` cancels in-flight work after a 5s
#: grace), a container restart, an OOM — left the investigation with results it could not continue
#: from. The route's interrupted-run branch then resubmitted the whole thing, and ``parts`` started
#: as ``[None] * total`` again, so batches 1 and 2 were re-sent to OpenRouter and re-billed to
#: produce answers already sitting in the database.
#:
#: Reported live: a scan finished 2 of 4 batches, stopped, and the elapsed clock kept running.
#:
#: Cleared the moment the run completes, so the cost is transient and only ever paid by a run that
#: is actually in flight.
BATCH_PARTS_KEY = "analyst_batch_parts_v1"


def _chunk_signature(chunks: list[dict]) -> str:
    """A fingerprint of the batch LAYOUT: which accounts are in which batch, in order.

    Resuming is only safe when the stored parts describe the same work this run is about to do. A
    different selection, a different batch size, or a re-ordered list all produce a different
    signature, and a mismatch means the stored parts are ignored rather than misapplied — a batch 3
    result stapled onto a run whose batch 3 holds different accounts would publish real prose against
    the wrong handles, which is the single worst thing this product can do.
    """
    h = hashlib.blake2b(digest_size=16)
    for chunk in chunks:
        ids = [
            str(c.get("external_id") or c.get("handle") or "")
            for c in ((chunk.get("video") or {}).get("commenters") or [])
        ]
        h.update(b"|".join(i.encode("utf-8", "replace") for i in ids))
        h.update(b"//")
    return h.hexdigest()


def _load_batch_parts(inv, signature: str, total: int) -> dict[int, dict]:
    """Per-batch results a previous, interrupted run of this exact layout already paid for."""
    store = (getattr(inv, "payload_json", None) or {}).get(BATCH_PARTS_KEY)
    if not isinstance(store, dict):
        return {}
    if store.get("signature") != signature or int(store.get("total") or 0) != total:
        return {}
    parts = store.get("parts")
    if not isinstance(parts, dict):
        return {}
    out: dict[int, dict] = {}
    for k, v in parts.items():
        try:
            i = int(k)
        except (TypeError, ValueError):
            continue
        # A stored part with no accounts is a floored batch. Deliberately NOT resumed: re-running it
        # is the retry the customer is owed, and treating an empty result as done would make an
        # interruption permanently lose the batch it happened to interrupt.
        if 0 <= i < total and isinstance(v, dict) and (v.get("commenter_assessments") or []):
            out[i] = v
    return out


def _save_batch_part(session, inv, signature: str, total: int, index: int, part: dict) -> None:
    """Checkpoint one landed batch. Best effort: a failed checkpoint must never sink the batch."""
    try:
        with session.begin_nested():
            payload = {**(inv.payload_json or {})}
            store = payload.get(BATCH_PARTS_KEY)
            if (not isinstance(store, dict) or store.get("signature") != signature
                    or int(store.get("total") or 0) != total):
                store = {"signature": signature, "total": total, "parts": {}}
            store = {**store, "parts": {**(store.get("parts") or {}), str(index): part}}
            payload[BATCH_PARTS_KEY] = store
            inv.payload_json = payload  # reassign so SQLAlchemy sees the JSON mutation
            session.add(inv)
    except Exception:  # noqa: BLE001
        logger.exception("analyst.batched: could not checkpoint batch %d for inv=%s",
                         index + 1, getattr(inv, "slug", "?"))


def _clear_batch_parts(session, inv) -> None:
    """Drop the checkpoint once the run is over, so the payload does not carry it forever."""
    try:
        payload = inv.payload_json or {}
        if BATCH_PARTS_KEY not in payload:
            return
        with session.begin_nested():
            trimmed = {k: v for k, v in payload.items() if k != BATCH_PARTS_KEY}
            inv.payload_json = trimmed
            session.add(inv)
    except Exception:  # noqa: BLE001
        logger.exception("analyst.batched: could not clear the batch checkpoint for inv=%s",
                         getattr(inv, "slug", "?"))


def _generate_batched(inv_slug: str, user_id: int | None, payload: dict, chunks: list[dict],
                      *, platform: str, settings: Settings,
                      lease_id: str | None = None) -> dict | None:
    """Run one analyst inference PER ≤N-account batch, merging + persisting the combined assessment
    after each batch lands (strictly first-to-last) so the UI can show batch 1's accounts while the
    rest are still generating. Returns the final persisted entry.

    Batches run SEQUENTIALLY by default (``analyst_batch_concurrency`` = 1): one unshared request at a
    time means the first 25 accounts land as early as possible instead of every batch finishing
    together at the end. Raising the concurrency restores bounded parallelism; the prefix-flush below
    keeps results appearing in order either way."""
    from app.storage.repository import AccountRepository

    ref = _ref(inv_slug)
    total = len(chunks)
    workers = max(1, min(total, int(getattr(settings, "analyst_batch_concurrency", 1) or 1)))
    # The size the chunks ACTUALLY have, not the configured threshold. Since the split is by count,
    # the two disagree (a 100-account scan is four batches of 25 against a threshold of 12), and the
    # `batching` marker below is what the progress strip renders to the customer.
    batch_size = max((len((c.get("video") or {}).get("commenters") or []) for c in chunks),
                     default=int(getattr(settings, "analyst_batch_accounts", 50) or 50))
    logger.info("analyst.batched: slug=%s accounts=%d -> %d batches of <=%d (%s)",
                inv_slug, len((payload.get("video") or {}).get("commenters") or []),
                total, batch_size,
                "sequential" if workers == 1 else f"concurrency={workers}")

    parts: list[dict | None] = [None] * total
    # How many model calls each batch has cost so far. Reported live, because a batch on its second
    # attempt is indistinguishable from a slow first one otherwise: "the fourth batch has been
    # running about ten minutes and the others were quick" is exactly that state, and nothing in the
    # UI could say so.
    attempts: dict[int, int] = {}
    # The batches whose request is open right now. Sequential runs hold exactly one; the set is what
    # lets the merge say "running" instead of "pending" without guessing which index that is.
    inflight: set[int] = set()
    flushed = 0    # longest contiguous run of completed batches (0..total)
    attempted = 0  # batches whose model call has returned, succeeded or not — what the UI counts
    # Identifies THIS run's writes, so a concurrent one can tell our progress from its own.
    run_id = uuid.uuid4().hex[:12]

    # RESUME, DO NOT RESTART. An interrupted run left its landed batches checkpointed; re-sending
    # them to OpenRouter would re-bill for answers already in the database and make the customer
    # wait through work that was finished. A resumed run picks up at the first batch that has no
    # result, which is also exactly the behaviour a reader expects from the progress strip.
    signature = _chunk_signature(chunks)
    resumed: set[int] = set()
    with get_session() as session:
        _inv = AccountRepository(session).get_investigation(slug=inv_slug, user_id=user_id)
        if _inv is not None:
            for i, part in _load_batch_parts(_inv, signature, total).items():
                parts[i] = part
                resumed.add(i)
    if resumed:
        logger.info("analyst.batched: slug=%s resuming, %d of %d batches already landed (%s)",
                    inv_slug, len(resumed), total,
                    ", ".join(str(i + 1) for i in sorted(resumed)))

    def _persist_progress(done: int, *, run_finished: bool = False) -> dict | None:
        merged = _merge_batch_parts(parts, batch_size=batch_size, done=done,
                                    run_finished=run_finished, run_id=run_id, attempts=attempts,
                                    running=inflight)
        if merged is None:
            return None
        gov = merged.get("governance") or {}
        provider = gov.get("provider") or "omi-analyst"
        with get_session() as session:
            repo = AccountRepository(session)
            inv = repo.get_investigation(slug=inv_slug, user_id=user_id)
            if inv is None:
                return None
            # PROGRESS NEVER GOES BACKWARDS ON SCREEN.
            #
            # The heartbeat above stops most duplicate runs from starting. This stops the damage if
            # one starts anyway (two workers racing, a redeploy mid-run, a manual refresh landing on
            # a live run): a younger run's first write would otherwise replace the "3 of 4" and 75
            # accounts the user is reading with "1 of 4" and 25.
            #
            # Deliberately narrow. It only defers to an entry from a DIFFERENT run that is still
            # being written to and is genuinely ahead of us. Our own writes, a stale entry, and a
            # finished entry all fall through to the normal write, so a single run behaves exactly
            # as before and a crashed run is still replaceable.
            # Advisory only, so it must never be the reason a batch fails to persist. If the stored
            # entry cannot be read we write, which is exactly the behaviour that existed before this
            # guard: losing the guard costs a cosmetic regression, losing the write costs results.
            try:
                existing = cached_assessment(inv)
            except Exception:  # noqa: BLE001
                existing = None
            # The FINAL write is guarded too, and that is the important half. It used to be exempt,
            # which made this the worst version of the bug rather than a cosmetic one: a duplicate
            # run finishing with one batch published 25 accounts over the leader's 75 AND set
            # `complete: true`, so the entry stopped being regenerable and the customer was left
            # permanently with a quarter of what they paid for. Our run just ends quietly instead;
            # the leader is still going and will mark the row complete itself.
            # Evidence of recent work, written on the same beat as the progress itself. Without
            # this the lease expires a fixed time after the run STARTED, which a long scan always
            # outlives.
            if lease_id:
                touch_generation_lease(session, inv, lease_id)
            if _entry_is_ahead(existing, merged, run_id):
                logger.info(
                    "analyst.batched: slug=%s another run is further ahead; not publishing this "
                    "run's %s over it", inv_slug, "final result" if run_finished else "progress")
                return existing
            return persist_assessment(session, inv, merged, provider)

    entry: dict | None = None

    def _landed(i: int) -> None:
        """Record batch ``i``'s outcome and persist what has landed so far.

        Persisting on EVERY landing, not only when the completed prefix grows. The prefix used to gate
        this, which stalled the run visibly and materially the moment any single batch failed: with
        batch 2 floored, the UI froze on "1 of 4 done" and batches 3 and 4 kept their accounts
        unpersisted until the whole run ended, minutes later. That reads as a hung scan and hides work
        that is already finished.

        The prefix is not needed to keep results ordered. ``_merge_batch_parts`` walks ``parts`` by
        index and merges every completed one, so accounts always appear in batch order regardless of
        the order the batches finish in; a gap left by a failed or slow batch simply fills in when it
        lands. ``flushed`` is still tracked, because the final merge below uses it to tell a run that
        finished short of every batch from one that completed.
        """
        nonlocal flushed, entry, attempted
        attempted += 1
        if parts[i] is None:
            logger.warning("analyst.batched: batch %d/%d returned no assessment (slug=%s)",
                           i + 1, total, inv_slug)
        elif i not in resumed:
            # Checkpointed the moment it lands, so an interruption after this point never re-bills
            # this batch. Only new work is written: a resumed part is already stored.
            with get_session() as _session:
                _inv = AccountRepository(_session).get_investigation(slug=inv_slug, user_id=user_id)
                if _inv is not None:
                    _save_batch_part(_session, _inv, signature, total, i, parts[i])
        while flushed < total and parts[flushed] is not None:
            flushed += 1
        # `done` drives only the progress readout; the merge itself always uses every completed part.
        entry = _persist_progress(attempted) or entry
        logger.info("analyst.batched: slug=%s progress %d/%d batches attempted, %d landed",
                    inv_slug, attempted, total, sum(1 for p in parts if p is not None))

    # Run-level circuit breaker. Counts batches that floored for a reason a retry cannot fix (a dead
    # credential, a missing preset, an exhausted balance). Without it, a 12-batch scan against a
    # broken config would double its generations before giving up, spending real money to fail
    # twice as slowly. Two is enough to tell a config fault from a one-off bad draw.
    # Guarded because `analyst_batch_concurrency` can put several batches in this counter at once,
    # and `+= 1` on a shared cell is a read-modify-write. An undercount here means the breaker opens
    # late and the run spends another generation against a config that cannot work.
    _dead_config_floors = [0]
    _dead_config_lock = threading.Lock()
    MAX_DEAD_CONFIG_FLOORS = 2

    def _attempt(i: int, *, budget_multiplier: float = 1.0) -> dict | None:
        # The multiplier is passed ONLY when it is actually an escalation, so the ordinary call is
        # byte-identical to what it always was. That keeps the hot path unchanged and means a
        # caller or test double that predates the parameter still works.
        extra = ({"completion_budget_multiplier": budget_multiplier}
                 if budget_multiplier and budget_multiplier != 1.0 else {})
        try:
            return assess_payload(
                chunks[i], ref=f"{ref}.b{i + 1}", platform=platform, settings=settings, **extra,
            )
        except Exception:  # noqa: BLE001 — one failed batch must not sink the others
            logger.exception("analyst.batched: batch %d/%d crashed for slug=%s", i + 1, total, inv_slug)
            return None

    def _run(i: int) -> dict | None:
        """One batch, retried at most once and only when a retry could plausibly change anything.

        A failed batch used to be lost outright: ``parts[i] = None`` was never re-attempted, so a
        single bad draw cost the customer that batch's accounts permanently and the only recovery
        was them noticing and pressing Retry. One bounded retry fixes the stochastic failures
        (a malformed response, a truncated one, a transient 429) without spending anything on the
        deterministic ones.
        """
        attempts[i] = 1
        inflight.add(i)
        # Published when the request OPENS, not only when it closes. Progress used to be written
        # exclusively on landing, which left the whole duration of a batch — the only part of a run
        # a reader actually waits through — described by a record saying that batch was "pending".
        # It also re-stamps the lease heartbeat here, so the gap between two heartbeats is no longer
        # one entire model call.
        _persist_progress(attempted)
        try:
            return _run_inner(i)
        finally:
            inflight.discard(i)

    def _run_inner(i: int) -> dict | None:
        result = _attempt(i)
        if result is not None and entry_is_model_backed({"assessment": result}):
            return result

        reason = _classify_floor(((result or {}).get("investigation_trace")) or {})
        if not _floor_is_retryable(reason):
            with _dead_config_lock:
                _dead_config_floors[0] += 1
            logger.error(
                "analyst.batched: batch %d/%d floored for slug=%s reason=%s — NOT retrying, a "
                "second call would fail identically", i + 1, total, inv_slug, reason,
            )
            return result
        with _dead_config_lock:
            _circuit_open = _dead_config_floors[0] >= MAX_DEAD_CONFIG_FLOORS
        if _circuit_open:
            logger.error("analyst.batched: slug=%s circuit open after %d unfixable floors, "
                         "not retrying batch %d/%d", inv_slug, _dead_config_floors[0], i + 1, total)
            return result

        # Two reasons make retrying UNCHANGED pointless, and they pull in opposite directions:
        # a truncated reply would truncate again at the same cap, and a budget the provider refused
        # as too large would be refused identically. Both are budget faults, so both are retried at a
        # different budget rather than with the same question asked twice. `budget_multiplier_for`
        # owns which way and by how much, so the rule lives beside the reasons it keys on.
        from app.reasoning.floor_reason import budget_multiplier_for
        multiplier = budget_multiplier_for(reason)
        logger.warning("analyst.batched: batch %d/%d floored for slug=%s reason=%s — retrying once "
                       "(budget x%.1f)", i + 1, total, inv_slug, reason, multiplier)
        # Published BEFORE the second call, not after it. A retry is the slowest thing that can
        # happen to one batch (a per-request timeout, up to two in-transport retries, then the whole
        # call again), so saying so once it is over is saying so too late to be of any use to
        # somebody watching the strip. This also re-stamps the lease heartbeat mid-batch.
        attempts[i] = 2
        _persist_progress(attempted)
        retried = _attempt(i, budget_multiplier=multiplier)
        if retried is not None and entry_is_model_backed({"assessment": retried}):
            logger.info("analyst.batched: batch %d/%d recovered on retry for slug=%s", i + 1, total,
                        inv_slug)
            return retried
        # Keep whichever attempt produced something at all; a floored result still carries every
        # deterministic score, and discarding it would lose the accounts entirely.
        return retried if result is None else result

    if workers == 1:
        # Sequential: one bundle of accounts goes to the model, its response is persisted the moment
        # it lands so the UI can show it, and only then does the next bundle start. That order is the
        # product behaviour, not an implementation detail — it is why batch 1's accounts are readable
        # while batch 4 has not been asked for yet.
        for i in range(total):
            if i in resumed:
                logger.info("analyst.batched: slug=%s batch %d/%d already landed, not re-sending",
                            inv_slug, i + 1, total)
            else:
                parts[i] = _run(i)
            _landed(i)
    else:
        from concurrent.futures import ThreadPoolExecutor, as_completed
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="omi-batch") as pool:
            futures = {pool.submit(_run, i): i for i in range(total) if i not in resumed}
            for i in sorted(resumed):
                _landed(i)
            for fut in as_completed(futures):
                i = futures[fut]
                parts[i] = fut.result()
                _landed(i)

    # Final merge. When every batch landed, the last _landed() already persisted a complete entry —
    # writing it again would be a pointless round trip. Otherwise some batch produced nothing, so the
    # prefix flush stalled short of the end: persist what DID land and mark the run finished, so the
    # client stops polling for a batch that will never arrive and the cache stops re-triggering a full
    # (billable) regeneration on every subsequent request.
    if flushed < total:
        landed = sum(1 for p in parts if p is not None)
        # `done` counts ATTEMPTS, not successes, and every batch has now been attempted. Reporting the
        # success count here instead made the readout run 1, 2, 3, 4 and then drop back to 3 on the
        # final write, which reads as the scan losing work it had already shown. How many batches
        # actually produced accounts is visible in the accounts themselves.
        entry = _persist_progress(attempted, run_finished=True) or entry
        logger.warning("analyst.batched: slug=%s finished with %d/%d batches (failed batches keep "
                       "their accounts unassessed; a refresh re-runs the generation)",
                       inv_slug, landed, total)
    else:
        logger.info("analyst.batched: slug=%s complete — %d batches merged", inv_slug, total)

    # The run is over either way, so the checkpoint has nothing left to protect. Dropped rather than
    # left behind: it duplicates every landed batch's per-account prose, and `payload_json` is
    # already the heaviest column in the product. The cost of resumability is paid only while a run
    # is actually in flight.
    with get_session() as session:
        _inv = AccountRepository(session).get_investigation(slug=inv_slug, user_id=user_id)
        if _inv is not None:
            _clear_batch_parts(session, _inv)
    return entry


def generate_and_persist(slug: str, user_id: int | None, refresh: bool = False) -> dict | None:
    """Background worker: open an own session, generate the assessment, cache it.
    Idempotent. Runs off the request hot path via app.core.background.submit.

    Exactly-once per investigation: the durable on-row cache is the cross-process guard, and an
    in-process in-flight set collapses the scan-time auto-trigger racing a UI-triggered request —
    so a single investigation makes at most ONE model (HF endpoint) call."""
    settings = get_settings()
    if not analyst_enabled(settings):
        return None
    with _autogen_lock:
        if slug in _autogen_inflight and not refresh:
            logger.info("analyst.generate: already in flight for slug=%s; skipping duplicate model call", slug)
            return None
        _autogen_inflight.add(slug)
    run_lease_id = uuid.uuid4().hex[:12]
    try:
        # get_session is imported at module scope (see the note there — a local import here is what
        # broke the batched path's nested closure).
        from app.storage.repository import AccountRepository

        payload: dict = {}
        platform = "unknown"
        inv_slug = slug
        with get_session() as session:
            repo = AccountRepository(session)
            inv = repo.get_investigation(slug=slug, user_id=user_id)
            if inv is None:
                logger.info("analyst.generate: investigation slug=%s not found (user_id=%s); skipping",
                            slug, user_id)
                return None
            current = cached_assessment(inv)
            # Checked BEFORE the refresh branch, deliberately. `refresh` used to skip reading the
            # entry at all, so every forced regeneration (the route's one-shot floor auto-heal, the
            # UI's Retry button) started a second run even when one was healthily mid-flight. A
            # refresh exists to heal a dead or floored result, not to race a live one: the duplicate
            # publishes its first batch over the leader's third, and whichever finishes first marks
            # the row complete with a fraction of the accounts. Whoever is mid-run will finish.
            if batched_run_looks_alive(current):
                logger.info("analyst.generate: slug=%s a batched run is already live elsewhere "
                            "(fresh heartbeat); serving its partial instead of starting a duplicate",
                            slug)
                return current
            cached = None if refresh else current
            if cached is not None:
                batching = (cached.get("assessment") or {}).get("batching") or {}
                if not batching or batching.get("complete"):
                    _cache_stats["served_from_cache"] += 1
                    logger.info("analyst.generate: slug=%s already has a cached assessment; no model call "
                                "(cache hit_rate=%.2f)", slug,
                                runtime_metrics()["assessment_cache"]["hit_rate"])
                    return cached
                # Otherwise this is a PARTIAL batched entry whose run is not alive (the liveness
                # check above already returned for the ones that are), so it is a genuinely
                # interrupted run: fall through and regenerate it.

            # Durable claim, taken BEFORE any model call. The heartbeat above only exists once the
            # first batch has landed, which is minutes in; until then a run is invisible to every
            # other process, so the page's first POST (arriving seconds after the scan scheduled
            # this one) landed on another worker and started a whole second run. That is the
            # "it scans twice" report, and it billed twice.
            if not claim_generation_lease(session, inv, run_lease_id):
                logger.info("analyst.generate: slug=%s another process holds the generation lease; "
                            "not starting a duplicate run", slug)
                return current
            payload = inv.payload_json or {}
            platform = _platform_of(inv)
            inv_slug = inv.slug

        # Batched path — a single OpenRouter request carries at most N accounts; a larger selection
        # runs as ≤N-account requests issued ONE AT A TIME, each persisted the moment it lands, so the
        # first accounts are readable while the rest are still being generated.
        batch_size = max(1, int(getattr(settings, "analyst_batch_accounts", 50) or 50))
        batch_count = max(1, int(getattr(settings, "analyst_batch_count", DEFAULT_ANALYST_BATCHES)
                                 or DEFAULT_ANALYST_BATCHES))
        chunks = _split_batches(payload, batch_size, batches=batch_count)
        if chunks:
            entry = _generate_batched(inv_slug, user_id, payload, chunks,
                                      platform=platform, settings=settings,
                                      lease_id=run_lease_id)
            if entry is not None:
                _cache_stats["generated"] += 1
            return entry

        assessment = assess_payload(
            payload, ref=_ref(inv_slug), platform=platform, settings=settings,
        )
        if assessment is None:
            return None
        _cache_stats["generated"] += 1
        gov = assessment.get("governance") or {}
        provider = gov.get("provider") or assessment.get("model_revision", "omi-analyst")
        with get_session() as session:
            repo = AccountRepository(session)
            inv = repo.get_investigation(slug=slug, user_id=user_id)
            if inv is None:
                return None
            return persist_assessment(session, inv, assessment, provider)
    finally:
        with _autogen_lock:
            _autogen_inflight.discard(slug)
        # Drop the durable claim so a later refresh is not made to wait out the staleness window.
        # Never allowed to raise: the generation is already done and its result is already written.
        try:
            with get_session() as _s:
                from app.storage.repository import AccountRepository as _Repo
                _inv = _Repo(_s).get_investigation(slug=slug, user_id=user_id)
                if _inv is not None:
                    release_generation_lease(_s, _inv, run_lease_id)
        except Exception:  # noqa: BLE001
            logger.exception("analyst.generate: could not release the lease for slug=%s", slug)
        # Pass 2 of the coordination detector: re-cut the 70+ cohort on the OMI scores this run
        # just produced. Hooked here rather than at the two return sites because `finally` covers
        # both the batched path and the single-shot one, and it is reached even when the run ends
        # early (the job itself no-ops when there is nothing to refine). Deterministic, no model
        # call, and scheduled on the normal pool so it never occupies a slow-pool worker.
        try:
            from app.campaigns.detector import run as campaign_detector

            campaign_detector.schedule(slug, user_id, "analyst")
        except Exception:  # noqa: BLE001
            logger.exception("analyst.generate: could not schedule coordination refinement "
                             "for slug=%s", slug)


def maybe_autogenerate(slug: str, user_id: int | None) -> bool:
    """Schedule a background analyst assessment for a freshly persisted investigation, so that
    EVERY real investigation reaches the model exactly once — the wire that was missing.

    Before this, ``assess_payload`` (→ the RemoteReasoningProvider → the HF endpoint) was reachable
    only through an explicit ``POST /v1/investigations/{slug}/analyst`` (the UI "Generate
    assessment" button); a normal scan never triggered it, so a live endpoint received zero
    requests. This runs off the scan's hot path via the background pool, is idempotent (cache +
    in-flight guard), and is a NO-OP unless the analyst is enabled — so it is fully backward
    compatible (endpoint unset → deterministic floor, exactly as before). Never raises."""
    try:
        settings = get_settings()
        if not analyst_enabled(settings):
            return False
        from app.core import background
        # The SLOW pool: a batched generation holds its worker for the whole run (batches are issued
        # one at a time), so it must never share threads with the scan jobs.
        fut = background.submit_slow(generate_and_persist, slug, user_id, False)
        scheduled = fut is not None
        # Provider-aware target — HF needs the endpoint; OpenRouter needs a preset or model. Log only.
        if reasoning_provider(settings) == "openrouter":
            _or_ok = bool(getattr(settings, "openrouter_preset", None)
                          or getattr(settings, "openrouter_model", None))
            target = "openrouter-model" if _or_ok else "deterministic-floor"
        else:
            target = "remote-model" if getattr(settings, "analyst_endpoint_url", None) else "deterministic-floor"
        logger.info("analyst.autogenerate: %s assessment for investigation slug=%s (target=%s)",
                    "scheduled" if scheduled else "could not schedule", slug, target)
        return scheduled
    except Exception:  # noqa: BLE001 — auto-generation must never disturb a scan
        logger.exception("analyst.autogenerate: failed to schedule for slug=%s", slug)
        return False


def _platform_of(inv) -> str:
    url = (getattr(inv, "input_url", "") or "").lower()
    if "twitter" in url or "x.com" in url:
        return "twitter"
    if "youtube" in url or "youtu.be" in url:
        return "youtube"
    return "unknown"
