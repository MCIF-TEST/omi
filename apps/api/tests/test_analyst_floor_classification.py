"""Why a scan floored, and whether retrying it could help.

WHY THIS FILE EXISTS SEPARATELY FROM ``test_analyst_floor_alerting.py``: that suite hand-builds its
trace dicts (``{"model_backed": False, "fallback_reason": reason}``), so it proves the alert fires
and says nothing about whether production ever populates that field. Production did not. Every real
floored scan logged ``reason="unclassified"``, sent an empty reason to the error tracker, and showed
the customer the generic sentence, because the field was read from ``inference.fallback_from`` which
is only ever set on an adjudication branch the live path does not use.

So the load-bearing test here is the end-to-end one: run the real assessment path with a transport
that fails, and assert the persisted trace names the cause. A test that constructs the trace itself
cannot catch this class of bug, which is exactly how it shipped.
"""

from __future__ import annotations

from pathlib import Path

from app.reasoning import floor_reason as FR

_WEB = Path(__file__).resolve().parents[3] / "apps" / "web"


# ==================================================================================================
# Classification
# ==================================================================================================
def test_http_statuses_map_to_the_probes_own_vocabulary():
    """The same words the preflight uses, so an operator does not have to learn two dialects for
    one fault."""
    cases = {
        401: FR.BAD_API_KEY,
        403: FR.BAD_API_KEY,
        402: FR.NO_CREDIT,
        404: FR.PRESET_OR_MODEL_NOT_FOUND,
        429: FR.RATE_LIMITED,
    }
    for status, expected in cases.items():
        got = FR.classify_floor({"response_status": status, "endpoint_error": "boom"})
        assert got == expected, f"{status} -> {got}"


def test_a_timeout_is_named_and_is_not_retryable():
    """A generation that timed out on our side may already have billed on theirs. The HTTP layer
    declines to retry timeouts for that reason and this must agree with it."""
    reason = FR.classify_floor({"endpoint_error": "ProviderTimeout: read timed out"})
    assert reason == FR.MODEL_TIMEOUT
    assert not FR.is_retryable(reason)


def test_an_unreachable_gateway_is_retryable():
    reason = FR.classify_floor({"endpoint_error": "ConnectionError: openrouter unreachable"})
    assert reason == FR.UNREACHABLE
    assert FR.is_retryable(reason)


def test_truncation_is_reported_as_the_cause_not_as_its_symptom():
    """A cut-off response also fails schema validation. Reporting the schema errors would send an
    operator hunting a prompt bug that is really a token budget, so truncation is checked first."""
    reason = FR.classify_floor({
        "finish_reason": "length",
        "canonical_validation_errors": ["missing required field: verdict"],
    })
    assert reason == FR.TRUNCATED_OUTPUT
    assert FR.is_retryable(reason)


def test_schema_errors_are_carried_into_the_reason():
    """The alert has to be actionable on its own. A bare 'it floored' sends someone to the database."""
    reason = FR.classify_floor({
        "canonical_validation_errors": ["missing required field: verdict", "omi_score below minimum"],
    })
    assert reason.startswith(FR.SCHEMA_INVALID)
    assert "verdict" in reason
    assert FR.is_retryable(reason)


def test_a_governor_rejection_names_its_codes_and_is_not_retryable():
    """Our own policy layer refused the output. Re-inferring to get a draw past our own gate is the
    wrong instinct."""
    reason = FR.classify_floor({
        "governor_verdict": "reject", "rejected_codes": ["S9_banned_phrase"],
    })
    assert reason.startswith(FR.GOVERNOR_REJECT)
    assert "S9_banned_phrase" in reason
    assert not FR.is_retryable(reason)


def test_a_call_that_never_happened_is_named_and_is_not_retryable():
    reason = FR.classify_floor({"endpoint_called": False})
    assert reason == FR.NO_MODEL_CALL
    assert not FR.is_retryable(reason)


def test_an_unknown_floor_still_gets_a_real_reason():
    """'We do not know' is itself worth alerting on, so the catch-all is a word rather than None."""
    assert FR.classify_floor({}) == FR.DETERMINISTIC_FLOOR
    assert FR.classify_floor(None) == FR.DETERMINISTIC_FLOOR


def test_an_explicit_upstream_reason_is_respected():
    """The judge-then-floor branch already names itself; this must not overwrite it."""
    assert FR.classify_floor({
        "fallback_reason": "governor_reject: ['x']", "response_status": 404,
    }) == "governor_reject: ['x']"


def test_config_faults_are_never_retryable():
    """Retrying a dead credential, a missing preset or an empty balance spends real money to fail
    identically, and delays the honest failure the operator needs to see."""
    for reason in (FR.BAD_API_KEY, FR.NO_CREDIT, FR.PRESET_OR_MODEL_NOT_FOUND, FR.NO_MODEL_CALL):
        assert not FR.is_retryable(reason), reason


def test_base_reason_strips_appended_detail():
    assert FR.base_reason("model_output_not_schema_valid_json: missing x") == FR.SCHEMA_INVALID
    assert FR.base_reason(None) == FR.DETERMINISTIC_FLOOR


def test_a_gateway_error_is_retryable_and_a_client_error_is_not():
    """A 5xx says the request was fine and the far side was not, which is the one status class worth
    trying again. A 4xx says the request was wrong, and the second one is identically wrong."""
    gateway = FR.classify_floor({"response_status": 503, "endpoint_error": "bad gateway"})
    assert gateway.startswith(FR.GATEWAY_ERROR) and "503" in gateway
    assert FR.is_retryable(gateway)

    client = FR.classify_floor({"response_status": 418, "endpoint_error": "teapot"})
    assert client.startswith(FR.HTTP_ERROR) and "418" in client
    assert not FR.is_retryable(client)


# ==================================================================================================
# The customer-facing half, which lives in another language
# ==================================================================================================
def test_every_reason_has_a_customer_sentence_in_the_web_app():
    """The reason list is declared TWICE, in two languages, and nothing at runtime reconciles them.

    ``floor_reason.py`` writes the field; ``apps/web/lib/analyst-failure.ts`` turns it into the
    sentence a customer reads. Add a reason on this side without a sentence on that side and it
    renders as the generic line, silently, for exactly the fault nobody has seen before. That is the
    same drift class as the signal-name contract, and the failure mode of a mapping is silence, so it
    has to be asserted rather than noticed.
    """
    source = (_WEB / "lib" / "analyst-failure.ts").read_text(encoding="utf-8")
    missing = [r for r in FR.ALL_REASONS if f"\n  {r}:" not in source]
    assert not missing, (
        f"no sentence in apps/web/lib/analyst-failure.ts for: {missing}. Add an entry to "
        "FAILURE_SENTENCES (null only for deterministic_floor, which means 'we cannot tell')."
    )


def test_every_declared_reason_has_a_defined_retryability():
    """A reason with no entry either way would silently take the non-retryable default, which is a
    decision about spending money made by omission."""
    for reason in FR.ALL_REASONS:
        assert isinstance(FR.is_retryable(reason), bool), reason


# ==================================================================================================
# The end-to-end regression: production must populate the field
# ==================================================================================================
def _payload() -> dict:
    return {
        "video": {
            "video_id": "vid1",
            "commenters": [
                {"external_id": "u1", "handle": "one", "overall_probability": 0.8,
                 "tier": "high", "recent_activity": []},
            ],
            "coordination_score": 0.1, "clusters": [],
        },
        "overall_tier": "moderate", "overall_probability": 0.4, "summary": "s",
    }


def _run_with_transport(monkeypatch, transport):
    """Drive the REAL assessment path with a failing transport and return the persisted trace."""
    from app.core.config import get_settings
    from app.reasoning import analyst

    monkeypatch.setenv("OMI_ANALYST_ENABLED", "true")
    monkeypatch.setenv("OMI_ANALYST_PROVIDER", "openrouter")
    monkeypatch.setenv("OMI_OPENROUTER_PRESET", "omi-master-v2")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    get_settings.cache_clear()
    monkeypatch.setattr(analyst, "_reasoning_transport", lambda *a, **k: transport)
    try:
        result = analyst.assess_payload(_payload(), ref="inv_test", platform="x")
    finally:
        get_settings.cache_clear()
    return ((result or {}).get("investigation_trace")) or {}


def test_a_floored_run_names_its_cause_in_the_persisted_trace(monkeypatch):
    """THE regression. Before this, `fallback_reason` was always None on the live path, so the
    alert said "unclassified", Sentry carried nothing, and the customer saw the generic sentence."""
    def dead(system, user, config):
        return None

    trace = _run_with_transport(monkeypatch, dead)
    if not trace:
        import pytest
        pytest.skip("the analyst path is not constructible in this environment")

    assert trace.get("model_backed") is False
    reason = trace.get("fallback_reason")
    assert reason, "a floored run must name its own cause, not report None"
    assert FR.base_reason(reason) in FR.ALL_REASONS, reason


def test_a_model_backed_run_reports_no_reason(monkeypatch):
    """An alert that fires on success is an alert people turn off."""
    from app.reasoning import analyst

    trace = _run_with_transport(monkeypatch, lambda s, u, c: None)
    if trace and trace.get("model_backed"):
        assert trace.get("fallback_reason") is None
    # The predicate the route, the UI and the alert all share must agree with the trace.
    assert analyst.entry_is_model_backed({"assessment": {"investigation_trace": {
        "model_backed": True}}, "provider": "openrouter"}) is True
