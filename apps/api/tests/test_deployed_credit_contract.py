"""The deployed credit grants must agree with the numbers the website prints.

`render.yaml` sets the credit economy twice, on purpose: the API service owns the real grant
(`OMI_FREE_TRIAL_CREDITS`, `OMI_MONTHLY_CREDIT_GRANT`) and the web service carries a display-only
mirror that Next inlines into marketing copy at build time (`NEXT_PUBLIC_TRIAL_CREDITS`,
`NEXT_PUBLIC_MONTHLY_CREDITS`). Nothing at runtime reconciles the two: the API grants what it grants,
and the landing page, pricing page, and sign-up page independently print whatever the mirror says.

So a one-sided edit does not fail anything. It just makes the site lie to customers about what they
get for signing up or paying, which is the kind of bug you find out about from a refund request. The
trial value has already been changed more than once, each time by hand, in two places.

These tests are the reconciliation. They read `render.yaml` directly, because the value that matters
is the DEPLOYED one, not `Settings`' local default.

Note the Render dashboard can also hold a manually-edited value for these keys. A blueprint sync
re-applies what is committed here, so this file is the source of truth and a dashboard edit that
disagrees with it is temporary.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

# apps/api/tests/ -> repo root
_REPO_ROOT = Path(__file__).resolve().parents[3]
RENDER_YAML = _REPO_ROOT / "render.yaml"


def _env_value(key: str) -> str:
    """The literal `value:` committed for an env var in render.yaml.

    Deliberately a narrow line scan rather than a YAML parse: pyyaml is not a declared dependency of
    apps/api, and adding one so a test can read two scalars is a worse trade than matching the two
    lines that hold them. render.yaml writes every one of these as a `- key:` / `value:` pair.
    """
    text = RENDER_YAML.read_text(encoding="utf-8")
    # `- key: NAME` followed (next non-blank line) by `value: '123'`
    m = re.search(
        rf"^\s*-\s*key:\s*{re.escape(key)}\s*$\n\s*value:\s*['\"]?([^'\"\n]+)['\"]?\s*$",
        text,
        re.MULTILINE,
    )
    if m is None:
        pytest.fail(
            f"{key} has no committed `value:` in render.yaml. If it moved to `sync: false` "
            f"(dashboard-owned), this contract can no longer be checked here and the test needs "
            f"rewriting rather than deleting."
        )
    return m.group(1).strip()


def _env_int(key: str) -> int:
    raw = _env_value(key)
    try:
        return int(raw)
    except ValueError:
        pytest.fail(f"{key} in render.yaml is {raw!r}, which is not an integer.")


def test_render_yaml_exists():
    assert RENDER_YAML.is_file(), f"expected the deploy blueprint at {RENDER_YAML}"


def test_displayed_trial_credits_match_the_granted_trial_credits():
    """The signup grant and the number the site advertises must be the same number."""
    granted = _env_int("OMI_FREE_TRIAL_CREDITS")
    displayed = _env_int("NEXT_PUBLIC_TRIAL_CREDITS")
    assert granted == displayed, (
        f"render.yaml grants {granted} trial credits on signup (OMI_FREE_TRIAL_CREDITS, "
        f"omisphere-api) but the site advertises {displayed} (NEXT_PUBLIC_TRIAL_CREDITS, "
        f"omisphere-web). Change both or the site lies to new users."
    )


def test_displayed_monthly_credits_match_the_granted_monthly_credits():
    """Same contract for the paid grant: what an invoice buys vs what pricing claims it buys."""
    granted = _env_int("OMI_MONTHLY_CREDIT_GRANT")
    displayed = _env_int("NEXT_PUBLIC_MONTHLY_CREDITS")
    assert granted == displayed, (
        f"render.yaml grants {granted} credits per paid invoice (OMI_MONTHLY_CREDIT_GRANT) but the "
        f"pricing page advertises {displayed} (NEXT_PUBLIC_MONTHLY_CREDITS). A subscriber who "
        f"counts what they received will notice."
    )


def test_trial_grant_is_a_sane_trial():
    """A trial is a taste, not a free month. Catches a fat-fingered extra digit."""
    granted = _env_int("OMI_FREE_TRIAL_CREDITS")
    monthly = _env_int("OMI_MONTHLY_CREDIT_GRANT")
    assert granted > 0, "a zero trial grant means new accounts cannot scan at all"
    assert granted <= monthly, (
        f"the free trial grants {granted} credits while a paid month grants {monthly}. A trial that "
        f"matches or beats the paid tier removes the reason to subscribe, so this is almost "
        f"certainly a typo."
    )


def test_the_pre_login_free_scans_are_independent_of_the_signup_grant():
    """The front page's free scans and the signup credits are two separate free tiers.

    A visitor gets N real scans before signing up (metered per IP, hardcoded and pinned here), and a
    NEW ACCOUNT separately gets `OMI_FREE_TRIAL_CREDITS`. Neither number is derived from the other,
    which is exactly why it is easy to change one believing you changed both. This test states the
    boundary so a future edit to the trial grant does not silently look like it also re-tuned the
    anonymous demo.
    """
    from app.routes.scan import DEMO_MAX_COMMENTERS
    from app.routes.scan_async import DEMO_FREE_SCANS_PER_IP

    assert DEMO_FREE_SCANS_PER_IP == 2, (
        "the pre-login front page is specified as two free scans per visitor; this constant is the "
        "only thing enforcing that and it is not read from settings or render.yaml"
    )
    assert DEMO_MAX_COMMENTERS == 25, (
        "each free pre-login scan analyzes up to 25 accounts; this is a separate cap from "
        "OMI_SCAN_MAX_COMMENTERS, which bounds a signed-in scan"
    )
