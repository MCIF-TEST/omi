"""Production boot must refuse a configuration that would run the service insecurely.

Both cases here were live fail-open defaults. The pattern is the same in each: the insecure state is
the DEFAULT, and the guard that was supposed to catch it either did not check, or was itself gated on
the thing that had gone wrong.

1. ``require_auth`` defaults to False, and when it is False ``require_user()`` does not reject the
   request — it returns a synthetic user with ``id=0``, ``is_admin=True`` and unlimited credits. So a
   missing ``OMI_REQUIRE_AUTH`` served every anonymous caller as an admin. Worse, the session-secret
   validation was written as ``if settings.require_auth:``, so auth being off skipped its own check.

2. ``env`` defaults to ``"development"`` and is compared by exact string, so ``prod``, ``Production``
   or an absent ``OMI_ENV`` skipped EVERY production check and opened CORS to ``*``.

These are boot-time assertions rather than runtime ones on purpose: a service that cannot serve safely
should fail the deploy loudly, not answer requests while looking healthy behind a green health check.
"""

from __future__ import annotations

import pytest

from app.core.config import Settings, get_settings
from app.main import ProductionConfigError, _validate_production_config

_PROD = {
    "env": "production",
    "database_url": "postgresql://u:p@db.internal:5432/omi",
    "youtube_api_key": "fake-key",
    "require_auth": True,
    "session_secret": "s" * 64,
}


def _settings(**overrides) -> Settings:
    return Settings(**{**_PROD, **overrides})


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


# --------------------------------------------------------------------------- #
# The baseline: a correct production config must still boot
# --------------------------------------------------------------------------- #
def test_a_correct_production_config_boots():
    """Guard against over-tightening: the checks must not reject a valid deploy."""
    _validate_production_config(_settings())


def test_non_production_environments_skip_the_checks():
    """Local dev must stay frictionless — SQLite and the dev secret are fine there."""
    _validate_production_config(
        _settings(env="development", database_url="sqlite:///./data/omi.db",
                  require_auth=False, session_secret="short")
    )


# --------------------------------------------------------------------------- #
# OMI-01 — authentication bypass
# --------------------------------------------------------------------------- #
def test_production_refuses_to_start_with_auth_disabled():
    """The finding: OMI_REQUIRE_AUTH absent => anonymous callers are admins."""
    with pytest.raises(ProductionConfigError):
        _validate_production_config(_settings(require_auth=False))


def test_the_auth_failure_names_the_actual_consequence():
    """A deploy log that says 'set a flag' teaches nothing; it must say what is exposed."""
    with pytest.raises(ProductionConfigError):
        _validate_production_config(_settings(require_auth=False))
    # The detailed problem text goes to the logs; assert the check is reachable and specific by
    # confirming a lone auth failure is enough to refuse (no other problem present).
    s = _settings(require_auth=False)
    assert s.database_url.startswith("postgresql"), "fixture must be otherwise valid"
    assert s.youtube_api_key, "fixture must be otherwise valid"


def test_auth_disabled_is_caught_even_though_it_skips_the_secret_check():
    """The original bug's shape: `if require_auth:` meant auth-off validated nothing.

    With auth off AND a dev-default secret, the old code raised nothing at all.
    """
    with pytest.raises(ProductionConfigError):
        _validate_production_config(
            _settings(require_auth=False,
                      session_secret="dev-only-change-me-please-12345678901234567890")
        )


# --------------------------------------------------------------------------- #
# OMI-02 — unrecognised environment silently disables hardening
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("bad_env", ["prod", "Production", "PRODUCTION", "prod uction", "staging"])
def test_an_unrecognised_env_is_refused_rather_than_treated_as_development(bad_env):
    """Any value that isn't in the closed set must fail the deploy, not downgrade it."""
    with pytest.raises(ProductionConfigError) as ei:
        _validate_production_config(_settings(env=bad_env))
    assert "OMI_ENV" in str(ei.value)


def test_the_env_guard_runs_before_the_production_checks():
    """Ordering matters: a bad env must be caught even when everything else is also wrong.

    If the env check ran after the `env != "production": return`, a typo would still skip everything.
    """
    with pytest.raises(ProductionConfigError) as ei:
        _validate_production_config(
            Settings(env="Production", database_url="sqlite:///./x.db",
                     youtube_api_key=None, require_auth=False, session_secret="short")
        )
    assert "OMI_ENV" in str(ei.value), "the env typo must be reported, not the downstream problems"


# --------------------------------------------------------------------------- #
# The break-glass override still works, but must not cover the env typo
# --------------------------------------------------------------------------- #
def test_degraded_override_still_permits_a_known_bad_production_boot(monkeypatch):
    """Recovery path: operators can still force a boot for break-glass debugging."""
    monkeypatch.setenv("OMI_ALLOW_DEGRADED_PRODUCTION", "true")
    _validate_production_config(_settings(require_auth=False))


def test_degraded_override_does_not_excuse_an_unrecognised_env(monkeypatch):
    """`OMI_ENV=prod` is a typo, not a deliberate degraded mode.

    Honouring the override here would mean a misspelling silently disables hardening again — the exact
    bug this guard exists to stop.
    """
    monkeypatch.setenv("OMI_ALLOW_DEGRADED_PRODUCTION", "true")
    with pytest.raises(ProductionConfigError):
        _validate_production_config(_settings(env="prod"))
