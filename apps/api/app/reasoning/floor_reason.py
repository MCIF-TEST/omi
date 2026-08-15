"""Why a scan fell back to the deterministic Floor.

The Floor is a *successful* code path: nothing raises, the scan completes, and the only symptom is a
sentence on a page. That is precisely how it once ran on every scan unnoticed, and it is why
``_report_floor`` exists. But an alert that says "unclassified" is barely better than no alert, and
that is what production was emitting.

THE BUG THIS FIXES. ``trace._fallback_reason`` can name five causes and is only reachable through
``audit_investigation``. Production sets ``investigation_trace["fallback_reason"]`` from
``inference.fallback_from``, which is only ever non-None in the ``judge_then_floor`` branch, while
the live comprehensive path runs ``adjudication="schema_only"``. So the field was **always None**:
the log said "unclassified", Sentry carried nothing useful, and ``lib/analyst-failure.ts`` fell
through to its generic sentence. Three symptoms, one disconnected wire.

Everything needed to classify was already being captured and simply never read: ``response_status``,
``endpoint_error``, ``finish_reason`` and ``canonical_validation_errors``.

THE VOCABULARY IS SHARED WITH THE PROBE on purpose. ``OpenRouterReasoningProvider.probe`` returns
``bad_api_key`` / ``no_credit`` / ``preset_or_model_not_found`` / ``rate_limited`` / ``timeout`` /
``unreachable``, and ``_PROBE_REMEDIES`` maps each to an operator action. Using the same words here
means ``GET /v1/investigations/analyst/preflight`` and a floored investigation describe an identical
problem identically, instead of an operator having to learn two dialects for one fault.
"""

from __future__ import annotations

# --------------------------------------------------------------------------------------------------
# The reasons
# --------------------------------------------------------------------------------------------------
BAD_API_KEY = "bad_api_key"
NO_CREDIT = "no_credit"
PRESET_OR_MODEL_NOT_FOUND = "preset_or_model_not_found"
RATE_LIMITED = "rate_limited"
MODEL_TIMEOUT = "model_timeout"
UNREACHABLE = "unreachable"
GATEWAY_ERROR = "gateway_error"
HTTP_ERROR = "http_error"
TRUNCATED_OUTPUT = "truncated_output"
SCHEMA_INVALID = "model_output_not_schema_valid_json"
GOVERNOR_REJECT = "governor_reject"
NO_MODEL_CALL = "no_model_call"
DETERMINISTIC_FLOOR = "deterministic_floor"

#: Every reason this module can emit, as a bare prefix. `analyst-failure.ts` must have a sentence
#: for each, pinned by a test, so a new reason can never render as the generic message by omission.
ALL_REASONS: tuple[str, ...] = (
    BAD_API_KEY, NO_CREDIT, PRESET_OR_MODEL_NOT_FOUND, RATE_LIMITED, MODEL_TIMEOUT,
    UNREACHABLE, GATEWAY_ERROR, HTTP_ERROR, TRUNCATED_OUTPUT, SCHEMA_INVALID, GOVERNOR_REJECT,
    NO_MODEL_CALL, DETERMINISTIC_FLOOR,
)

#: Reasons where trying again can plausibly succeed.
#:
#: The exclusions are the interesting half, and each one is a decision about spending money:
#:
#: * ``bad_api_key`` / ``no_credit`` / ``preset_or_model_not_found`` / ``no_model_call`` are
#:   deterministic config faults. The second call fails exactly like the first, so a retry is pure
#:   spend and pure delay in front of a failure the operator needs to see.
#: * ``model_timeout`` is excluded even though it looks transient: a generation that timed out on
#:   our side may already have been billed on theirs. This matches the HTTP layer's own policy in
#:   ``openrouter._fetch``, which deliberately does not retry timeouts, and softening it here would
#:   quietly double the cost of a slow model.
#: * ``governor_reject`` is our own policy layer refusing the output. Re-inferring to get a different
#:   draw past our own quality gate is the wrong instinct.
#: * ``http_error`` is a 4xx we have no specific word for. A 4xx says the request was wrong, and the
#:   second one would be identically wrong. ``gateway_error`` (5xx) is the opposite case and is
#:   retryable: the request was fine and the far side was not.
RETRYABLE: frozenset[str] = frozenset({
    RATE_LIMITED, UNREACHABLE, GATEWAY_ERROR, TRUNCATED_OUTPUT, SCHEMA_INVALID, DETERMINISTIC_FLOOR,
})

_TIMEOUT_HINTS = ("timeout", "timedout", "timed out", "readtimeout", "connecttimeout")


def _int_or_none(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def classify_floor(trace: dict | None) -> str:
    """Name the cause of a floor from what the run already recorded.

    Pure, and ordered from most specific to least: an HTTP status is a harder fact than an error
    string, and an error string is harder than "something else happened". The catch-all is a real
    reason rather than an empty string, because "we do not know" is itself worth alerting on.
    """
    if not isinstance(trace, dict):
        return DETERMINISTIC_FLOOR

    # An explicit upstream classification wins: the Governor path already names itself.
    existing = trace.get("fallback_reason")
    if isinstance(existing, str) and existing.strip():
        return existing.strip()

    verdict = str(trace.get("governor_verdict") or "").lower()
    if verdict == "reject":
        codes = trace.get("rejected_codes") or trace.get("violation_codes")
        return f"{GOVERNOR_REJECT}: {codes}" if codes else GOVERNOR_REJECT

    status = _int_or_none(trace.get("response_status"))
    if status in (401, 403):
        return BAD_API_KEY
    if status == 402:
        return NO_CREDIT
    if status == 404:
        return PRESET_OR_MODEL_NOT_FOUND
    if status == 429:
        return RATE_LIMITED
    if status and status >= 500:
        # Their fault, not ours, and the only class of status worth trying again.
        return f"{GATEWAY_ERROR}: {status}"

    error = str(trace.get("endpoint_error") or "")
    if error:
        lowered = error.lower()
        if any(hint in lowered for hint in _TIMEOUT_HINTS):
            return MODEL_TIMEOUT
        if status and status >= 400:
            # A 4xx we have no specific word for. Carry the status so the log is still actionable.
            return f"{HTTP_ERROR}: {status}"
        return UNREACHABLE

    # A 200 that produced nothing usable. Truncation is checked BEFORE the schema errors because it
    # is the cause and they are the symptom: a cut-off response fails validation, and reporting the
    # schema errors would send an operator hunting a prompt bug that is really a token budget.
    if str(trace.get("finish_reason") or "").lower() == "length":
        return TRUNCATED_OUTPUT

    errors = trace.get("canonical_validation_errors")
    if isinstance(errors, (list, tuple)) and errors:
        head = "; ".join(str(e) for e in list(errors)[:2])
        return f"{SCHEMA_INVALID}: {head}"

    if trace.get("endpoint_called") is False:
        return NO_MODEL_CALL

    return DETERMINISTIC_FLOOR


def base_reason(reason: str | None) -> str:
    """The bare reason, with any appended detail stripped.

    ``classify_floor`` returns things like ``"model_output_not_schema_valid_json: missing field x"``
    so the log is useful. Retry gating and the frontend mapping both key on the prefix, and doing
    that split in one place stops the two drifting into slightly different substring checks.
    """
    if not reason:
        return DETERMINISTIC_FLOOR
    return str(reason).split(":", 1)[0].strip()


def is_retryable(reason: str | None) -> bool:
    """Whether re-running this generation could plausibly produce a different result."""
    return base_reason(reason) in RETRYABLE
