"""Production config gate — refuses to start a deploy that would lose data
or strand users. Dev mode (env=development) is always permissive."""

from __future__ import annotations

import pytest

from app.core.config import Settings
from app.main import (
    _DEV_SESSION_SECRET,
    ProductionConfigError,
    _validate_production_config,
)


def _prod_settings(**overrides) -> Settings:
    """Build a Settings object that would pass production validation, then
    apply the overrides under test."""
    base = dict(
        env="production",
        database_url="postgresql://omi:secret@localhost/omi",
        session_secret="x" * 64,
        youtube_api_key="AIzaTEST_KEY_FOR_VALIDATION_ONLY",
        require_auth=True,
    )
    base.update(overrides)
    return Settings(**base)


def test_passes_when_everything_is_configured():
    # No raise = pass.
    _validate_production_config(_prod_settings())


def test_dev_environment_is_always_permissive():
    # Even with every prod check failing, dev is allowed to boot.
    settings = Settings(
        env="development",
        database_url="sqlite:///./data/omi.db",
        session_secret=_DEV_SESSION_SECRET,
        youtube_api_key=None,
        require_auth=True,
    )
    _validate_production_config(settings)


def test_sqlite_in_production_is_refused():
    settings = _prod_settings(database_url="sqlite:///./data/omi.db")
    with pytest.raises(ProductionConfigError) as exc:
        _validate_production_config(settings)
    assert "1 issue" in str(exc.value)


def test_dev_session_secret_in_production_is_refused():
    settings = _prod_settings(session_secret=_DEV_SESSION_SECRET)
    with pytest.raises(ProductionConfigError):
        _validate_production_config(settings)


def test_short_session_secret_in_production_is_refused():
    settings = _prod_settings(session_secret="too-short")
    with pytest.raises(ProductionConfigError):
        _validate_production_config(settings)


def test_missing_youtube_key_in_production_is_refused():
    settings = _prod_settings(youtube_api_key=None)
    with pytest.raises(ProductionConfigError):
        _validate_production_config(settings)


def test_blank_youtube_key_in_production_is_refused():
    settings = _prod_settings(youtube_api_key="   ")
    with pytest.raises(ProductionConfigError):
        _validate_production_config(settings)


def test_session_secret_not_checked_when_auth_disabled():
    # require_auth=False is a documented "local mode" — the dev secret is
    # harmless because there are no sessions to forge.
    settings = _prod_settings(
        session_secret=_DEV_SESSION_SECRET,
        require_auth=False,
    )
    _validate_production_config(settings)


def test_multiple_issues_aggregated_into_one_error(caplog):
    settings = _prod_settings(
        database_url="sqlite:///./data/omi.db",
        session_secret=_DEV_SESSION_SECRET,
        youtube_api_key=None,
    )
    with pytest.raises(ProductionConfigError) as exc:
        _validate_production_config(settings)
    # All three problems mentioned in the rendered log block.
    log_output = caplog.text
    assert "OMI_DATABASE_URL" in log_output
    assert "OMI_SESSION_SECRET" in log_output
    assert "OMI_YOUTUBE_API_KEY" in log_output
    assert "3 issues" in str(exc.value)


def test_override_flag_downgrades_failure_to_warning(monkeypatch, caplog):
    monkeypatch.setenv("OMI_ALLOW_DEGRADED_PRODUCTION", "true")
    settings = _prod_settings(
        database_url="sqlite:///./data/omi.db",
        youtube_api_key=None,
    )
    # No raise — override was honored.
    _validate_production_config(settings)
    assert "OVERRIDDEN" in caplog.text


def test_override_flag_only_accepts_truthy_values(monkeypatch):
    monkeypatch.setenv("OMI_ALLOW_DEGRADED_PRODUCTION", "no")
    settings = _prod_settings(database_url="sqlite:///./data/omi.db")
    with pytest.raises(ProductionConfigError):
        _validate_production_config(settings)
