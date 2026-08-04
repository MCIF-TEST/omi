"""The web app and the API must name the SAME Clerk instance, and production must not be on a dev one.

This is the reconciliation for a failure that was live on omisphere.online.

The two services learn which Clerk instance to trust independently. The browser gets
``NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY`` (web service) and signs the user in; the API gets
``CLERK_PUBLISHABLE_KEY`` (API service), base64-decodes it to an issuer, and verifies every session
JWT against that issuer's JWKS (``app/core/clerk_auth._issuer``). Nothing at runtime compares them.

So switching the dashboard to the production Clerk keys on one service and not the other produces a
state that looks like a network fault and is not one: sign-in succeeds, a perfectly valid session JWT
is minted by ``clerk.omisphere.online``, and the API rejects it because it still expects
``sweet-finch-45.clerk.accounts.dev``. ``verify_session_token`` swallows the mismatch and returns
``None`` (a token it cannot verify is normally just an anonymous request), so there is no log line, no
5xx, and no failed health check. The user is told they are signed in but has no workspace.

Two independent guards, because they fail in different places:

* ``_clerk_instance_problem`` refuses the BOOT of a production deploy holding a development key. It
  runs on the API only and catches the half of the mismatch the API can see.
* The render.yaml contract tests below catch the other half at commit time, by asserting the two
  committed values are byte-identical. Those values are what a blueprint sync re-applies, so a
  dashboard edit that disagrees with them is temporary and this file is the source of truth.
"""

from __future__ import annotations

import base64
import re
from pathlib import Path

import pytest

from app.core.config import Settings, get_settings
from app.main import (
    ProductionConfigError,
    _CLERK_DEV_HOST_SUFFIX,
    _clerk_instance_problem,
    _validate_production_config,
)

# apps/api/tests/ -> repo root
_REPO_ROOT = Path(__file__).resolve().parents[3]
RENDER_YAML = _REPO_ROOT / "render.yaml"

_PROD = {
    "env": "production",
    "database_url": "postgresql://u:p@db.internal:5432/omi",
    "youtube_api_key": "fake-key",
    "require_auth": True,
    "session_secret": "s" * 64,
}

_DEV_KEY = "pk_test_c3dlZXQtZmluY2gtNDUuY2xlcmsuYWNjb3VudHMuZGV2JA"      # sweet-finch-45.clerk.accounts.dev$
_LIVE_KEY = "pk_live_Y2xlcmsub21pc3BoZXJlLm9ubGluZSQ"                     # clerk.omisphere.online$

_CLERK_ENV_KEYS = (
    "NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY",
    "CLERK_PUBLISHABLE_KEY",
    "CLERK_ISSUER",
    "CLERK_JWKS_URL",
)


def _settings(**overrides) -> Settings:
    return Settings(**{**_PROD, **overrides})


@pytest.fixture(autouse=True)
def _clean_clerk_env(monkeypatch):
    """Start every test from no Clerk configuration at all.

    The developer running this suite may well have a real key exported, and these tests assert on the
    exact key in the environment. Clear rather than trust.
    """
    get_settings.cache_clear()
    for key in _CLERK_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    yield
    get_settings.cache_clear()


# --------------------------------------------------------------------------- #
# The boot guard
# --------------------------------------------------------------------------- #
def test_production_refuses_to_boot_on_a_development_clerk_instance(monkeypatch):
    """The exact live failure: production API still pinned to the pk_test instance."""
    monkeypatch.setenv("CLERK_PUBLISHABLE_KEY", _DEV_KEY)
    with pytest.raises(ProductionConfigError):
        _validate_production_config(_settings())


def test_a_production_clerk_key_boots(monkeypatch):
    """Guard against over-tightening: the correct pairing must still deploy."""
    monkeypatch.setenv("CLERK_PUBLISHABLE_KEY", _LIVE_KEY)
    _validate_production_config(_settings())


def test_the_next_public_key_wins_over_the_server_one(monkeypatch):
    """Match ``clerk_auth.clerk_publishable_key`` exactly, which prefers NEXT_PUBLIC_.

    If this check read the other variable, an API service carrying both would be validated against a
    key it does not actually use, which is a guard that reports on the wrong thing.
    """
    monkeypatch.setenv("CLERK_PUBLISHABLE_KEY", _LIVE_KEY)
    monkeypatch.setenv("NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY", _DEV_KEY)
    assert _clerk_instance_problem() is not None

    monkeypatch.setenv("CLERK_PUBLISHABLE_KEY", _DEV_KEY)
    monkeypatch.setenv("NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY", _LIVE_KEY)
    assert _clerk_instance_problem() is None


def test_an_absent_clerk_key_is_not_a_boot_failure(monkeypatch):
    """Clerk is optional in this codebase (the legacy cookie session path still authenticates), and
    render.yaml commits the publishable key as a value, so absence is not a state a real deploy of
    this blueprint reaches. Failing here would add a way to brick a deploy without catching a bug."""
    _validate_production_config(_settings())
    assert _clerk_instance_problem() is None


def test_a_blank_key_counts_as_absent(monkeypatch):
    """Render's shape for "declared but not filled in yet" is an empty string, not an unset var."""
    monkeypatch.setenv("CLERK_PUBLISHABLE_KEY", "   ")
    assert _clerk_instance_problem() is None


def test_non_production_environments_may_use_the_development_instance(monkeypatch):
    """Local and preview work is supposed to run on pk_test. Only production is constrained."""
    monkeypatch.setenv("CLERK_PUBLISHABLE_KEY", _DEV_KEY)
    _validate_production_config(_settings(env="development"))
    _validate_production_config(_settings(env="test"))


def test_an_explicit_issuer_overrides_the_key(monkeypatch):
    """``CLERK_ISSUER`` overrides the key-derived issuer in ``clerk_auth._issuer``, so when it is set
    it, not the key, is what the API verifies against. A guard that ignored it would refuse a deploy
    that is in fact configured correctly."""
    monkeypatch.setenv("CLERK_PUBLISHABLE_KEY", _DEV_KEY)
    monkeypatch.setenv("CLERK_ISSUER", "https://clerk.omisphere.online")
    assert _clerk_instance_problem() is None


def test_an_explicit_development_issuer_is_still_refused(monkeypatch):
    monkeypatch.setenv("CLERK_PUBLISHABLE_KEY", _LIVE_KEY)
    monkeypatch.setenv("CLERK_ISSUER", "https://sweet-finch-45.clerk.accounts.dev/")
    problem = _clerk_instance_problem()
    assert problem is not None
    assert "CLERK_ISSUER" in problem


def test_the_error_names_both_variables_and_the_redeploy(monkeypatch):
    """The message is the whole remedy: this failure gives an operator no other signal to work from,
    and the fix is not obvious (both services, and a redeploy, because the issuer and the JWKS client
    are cached in module globals for the life of the process)."""
    monkeypatch.setenv("CLERK_PUBLISHABLE_KEY", _DEV_KEY)
    problem = _clerk_instance_problem()
    assert problem is not None
    assert "CLERK_PUBLISHABLE_KEY" in problem
    assert "NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY" in problem
    assert "pk_live_" in problem
    assert "redeploy" in problem.lower()


# --------------------------------------------------------------------------- #
# The committed pairing in render.yaml
# --------------------------------------------------------------------------- #
def _committed_value(key: str) -> str:
    """The literal `value:` committed for an env var in render.yaml.

    A line scan rather than a YAML parse, matching test_deployed_credit_contract.py: pyyaml is not a
    declared dependency of apps/api and adding one to read two scalars is the worse trade.
    """
    text = RENDER_YAML.read_text(encoding="utf-8")
    matches = re.findall(
        rf"^\s*-\s*key:\s*{re.escape(key)}\s*$\n\s*value:\s*['\"]?([^'\"\n]+)['\"]?\s*$",
        text,
        re.MULTILINE,
    )
    if not matches:
        pytest.fail(
            f"{key} has no committed `value:` in render.yaml. If it moved to `sync: false` "
            f"(dashboard-owned) then a blueprint sync no longer pins the Clerk instance and the two "
            f"services can drift apart silently again. Rewrite this contract rather than deleting it."
        )
    assert len(matches) == 1, f"{key} is committed more than once in render.yaml: {matches}"
    return matches[0].strip()


def test_the_two_services_commit_the_same_publishable_key():
    """The one assertion that would have prevented the outage. The API and the web app name the Clerk
    instance in two different files' worth of configuration and nothing at runtime reconciles them."""
    api = _committed_value("CLERK_PUBLISHABLE_KEY")
    web = _committed_value("NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY")
    assert api == web, (
        "render.yaml commits a different Clerk publishable key to the API service than to the web "
        f"service ({api!r} vs {web!r}). Users will sign in and then have no workspace."
    )


def test_the_committed_key_is_a_production_instance():
    key = _committed_value("CLERK_PUBLISHABLE_KEY")
    assert key.startswith("pk_live_"), (
        f"render.yaml commits {key!r}, a Clerk development key, for a deployment that runs with "
        "OMI_ENV=production. The API would refuse to boot (see _clerk_instance_problem)."
    )


def test_the_committed_key_decodes_to_the_expected_issuer():
    """A publishable key is ``pk_(test|live)_<base64(frontend_api_host + '$')>``, which is how
    ``clerk_auth._issuer`` turns it into the issuer it verifies against. Asserting the decode keeps a
    typo in the base64 from becoming an unverifiable JWKS URL: a mistyped key does not fail the
    startswith check above, it just points the API at a host that does not exist, and every login
    fails with the same silent None."""
    key = _committed_value("CLERK_PUBLISHABLE_KEY")
    host = base64.b64decode(key.split("_", 2)[2] + "==").decode("utf-8").rstrip("$")
    assert host == "clerk.omisphere.online", (
        f"the committed Clerk key decodes to {host!r}. That is the host the API will fetch "
        "/.well-known/jwks.json from and the issuer it will require on every session token, so it "
        "must be the Clerk frontend API host for the production instance."
    )
    assert not host.endswith(_CLERK_DEV_HOST_SUFFIX)


def test_the_api_derives_that_issuer_from_the_committed_key(monkeypatch):
    """Close the loop: assert against the real derivation in clerk_auth, not a copy of it here."""
    from app.core import clerk_auth

    monkeypatch.setenv("CLERK_PUBLISHABLE_KEY", _committed_value("CLERK_PUBLISHABLE_KEY"))
    monkeypatch.setattr(clerk_auth, "_ISSUER", None)   # module-level cache, cleared only by restart
    try:
        assert clerk_auth._issuer() == "https://clerk.omisphere.online"
    finally:
        clerk_auth._ISSUER = None
