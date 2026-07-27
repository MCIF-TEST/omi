"""Error tracking — opt-in, inert when unconfigured.

Production had no error tracking at all, so the only record of a failure was Render's log stream:
ephemeral, unsearchable at volume, with no grouping, no alerting and no release correlation. Both
500-level bugs found during the launch audit were silent in production — the first signal would have
been a customer.

Design constraints, in order:

* **Zero effect when unset.** No DSN means this module imports nothing and does nothing. A monitoring
  integration that can break the service it monitors is a downgrade.
* **Never fatal.** A bad DSN, a missing package, or an unreachable ingest endpoint logs a warning and
  the app serves normally.
* **No secrets or user content by default.** ``send_default_pii`` stays off, and scan payloads are
  never attached — this product handles other people's social media data, and an error tracker is not
  the place for it.

Enable by installing the SDK (``pip install 'sentry-sdk>=2'``) and setting ``SENTRY_DSN``. Any
Sentry-compatible ingest works, self-hosted included, so this does not commit to a vendor.
"""
from __future__ import annotations

import logging
import os

log = logging.getLogger("omi.observability")

_initialised = False


def error_tracking_dsn() -> str:
    """The configured DSN, read from the environment only — never a settings field, never logged."""
    return (os.environ.get("SENTRY_DSN") or os.environ.get("OMI_SENTRY_DSN") or "").strip()


def error_tracking_enabled() -> bool:
    return bool(error_tracking_dsn())


def init_error_tracking(env: str, release: str | None = None) -> bool:
    """Initialise error tracking if a DSN is configured. Returns whether it is active.

    Idempotent: safe to call from both the app factory and a worker entry point.
    """
    global _initialised
    if _initialised:
        return True
    dsn = error_tracking_dsn()
    if not dsn:
        return False
    try:
        import sentry_sdk
    except Exception:  # noqa: BLE001 — SDK absent is a configuration state, not an error
        log.warning(
            "SENTRY_DSN is set but the sentry-sdk package is not installed; error tracking is OFF. "
            "Add 'sentry-sdk>=2' to the API dependencies."
        )
        return False
    try:
        sentry_sdk.init(
            dsn=dsn,
            environment=env,
            release=release,
            # Errors are the point. Tracing is sampled low so enabling this cannot become a
            # performance or cost surprise; raise deliberately if you want latency data.
            traces_sample_rate=float(os.environ.get("SENTRY_TRACES_SAMPLE_RATE", "0.0")),
            # Off by default: this service processes third parties' social media data, and none of it
            # belongs in an error tracker.
            send_default_pii=False,
            max_request_body_size="never",
        )
        _initialised = True
        log.info("Error tracking: ON (environment=%s)", env)
        return True
    except Exception as exc:  # noqa: BLE001 — never let monitoring break the service
        log.warning("Error tracking failed to initialise, continuing without it: %s", exc)
        return False


def capture_exception(exc: BaseException) -> None:
    """Report an exception if tracking is active; otherwise do nothing. Never raises."""
    if not _initialised:
        return
    try:
        import sentry_sdk

        sentry_sdk.capture_exception(exc)
    except Exception:  # noqa: BLE001
        pass


def reset_for_tests() -> None:
    global _initialised
    _initialised = False
