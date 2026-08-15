"""Ask the gateway one question at boot, so a broken analyst config announces itself.

WHY THIS EXISTS. The analyst's dependencies are two-sided contracts with nothing reconciling them:
``OMI_OPENROUTER_PRESET`` names a preset in someone's dashboard, ``OPENROUTER_API_KEY`` names a
credential that can be revoked, and the OpenRouter balance is a number nothing here can see. Break
any of them and the product does not fail: every scan quietly persists the deterministic Floor, which
is a *successful* code path. Nothing raises, so ``background._wrap`` reports nothing, and the entire
signal is a sentence on a page a customer has to happen to read and then bother to complain about.

That has now happened twice for real. A preset renamed ``omi-master-v1`` -> ``omi-master-v2`` in the
dashboard floored every scan on the deployment until a human noticed, and a validator living outside
the deployed package did the same thing before it.

``GET /v1/investigations/analyst/preflight`` already answers this question properly, and answers it
against the live gateway rather than against the config. Its weakness is that somebody has to call
it, and the moment when nobody calls it is exactly the moment after a deploy that broke something.
So this fires the same probe once, automatically, and puts the answer in the deploy log and in the
error tracker.

FIVE PROPERTIES, and they are the whole design. Monitoring that can break the thing it monitors is a
downgrade, not an improvement:

* It **never blocks boot** — it runs on ``background.submit``, so the app is serving before it fires.
* It **never fails boot**, and **never raises**: every path is inside a try/except that logs.
* It **no-ops without a credential**. A dev machine or a test run with no ``OPENROUTER_API_KEY`` is
  not a misconfigured deployment, and an alert that fires there is an alert people learn to ignore.
* It **no-ops when the analyst is switched off**, for the same reason.
* It costs **one ``max_tokens: 1`` call per deploy**, not per scan.
"""

from __future__ import annotations

import logging

logger = logging.getLogger("omi.analyst.preflight")


class AnalystPreflightFailed(RuntimeError):
    """A typed carrier so the error tracker groups these together and they are searchable.

    Same reasoning as ``AnalystFellBackToFloor``: the tracker's value here is that a deploy which
    broke the analyst is one issue with a title, rather than a log line nobody greps for.
    """


def _should_run(settings) -> tuple[bool, str]:
    """Whether a live probe would mean anything on this deployment."""
    if not bool(getattr(settings, "analyst_enabled", False)):
        return False, "OMI_ANALYST_ENABLED is not true"
    if str(getattr(settings, "analyst_provider", "") or "").lower() != "openrouter":
        return False, "the configured provider is not openrouter"
    import os

    if not (os.getenv("OPENROUTER_API_KEY") or "").strip():
        return False, "no OPENROUTER_API_KEY is set"
    return True, ""


def run_boot_preflight(settings=None) -> dict | None:
    """Probe the gateway once and report. Returns the probe result, or None when it did not run.

    Never raises. The return value exists for the tests; nothing in production reads it.
    """
    try:
        if settings is None:
            from app.core.config import get_settings

            settings = get_settings()
        ok_to_run, why_not = _should_run(settings)
        if not ok_to_run:
            logger.info("analyst preflight skipped: %s", why_not)
            return None

        from app.reasoning.model_providers.openrouter import (
            OPENROUTER_URL,
            OpenRouterReasoningProvider,
        )

        provider = OpenRouterReasoningProvider(
            base_url=str(getattr(settings, "openrouter_base_url", OPENROUTER_URL) or OPENROUTER_URL),
            model=getattr(settings, "openrouter_model", None),
            preset=getattr(settings, "openrouter_preset", None),
            referer=getattr(settings, "openrouter_referer", None),
            title=getattr(settings, "openrouter_title", None),
        )
        probe = provider.probe() or {}
        if probe.get("ok"):
            logger.info("analyst preflight OK: gateway answered for %s (served %s)",
                        probe.get("model_ref"), probe.get("served_model"))
            return probe

        reason = str(probe.get("reason") or "unknown")
        detail = str(probe.get("detail") or "")[:400]
        # The remedy is the reason this is worth logging rather than just recording. It is imported
        # here rather than at module scope because it lives in the route package: a route importing
        # a reasoning module is the normal direction, and doing it the other way round at import
        # time would couple boot to the whole router graph.
        try:
            from app.routes.reasoning import _PROBE_REMEDIES

            remedy = (_PROBE_REMEDIES.get(reason) or "").format(model_ref=probe.get("model_ref"))
        except Exception:  # noqa: BLE001 — a missing remedy must not cost us the alert
            remedy = ""
        logger.error(
            "ANALYST PREFLIGHT FAILED at boot: reason=%s model_ref=%s detail=%s%s "
            "Every scan on this deployment will fall back to the deterministic Floor until this is "
            "fixed. GET /v1/investigations/analyst/preflight on the API host for the full report.",
            reason, probe.get("model_ref"), detail, f" REMEDY: {remedy}" if remedy else "",
        )
        try:
            from app.core.observability import capture_exception

            # The message carries the diagnosis because that is all the tracker gets: the reason
            # alone would group every fault into one unreadable issue.
            capture_exception(AnalystPreflightFailed(
                f"analyst preflight failed at boot: {reason} "
                f"(model_ref={probe.get('model_ref')!r}) {detail}".strip()))
        except Exception:  # noqa: BLE001 — a broken tracker must never be the thing that breaks boot
            logger.exception("analyst preflight: could not report the failure")
        return probe
    except Exception:  # noqa: BLE001 — this is a diagnostic; it may never affect the process
        logger.exception("analyst preflight: the check itself failed")
        return None


def schedule_boot_preflight() -> None:
    """Queue the probe on the background pool. Returns immediately; never raises."""
    try:
        from app.core import background

        background.submit(run_boot_preflight)
    except Exception:  # noqa: BLE001
        logger.exception("analyst preflight: could not be scheduled")
