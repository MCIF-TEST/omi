"""The deployed credit economy must agree with what the website prints, and with itself.

Three declarations of one set of facts, none of which the runtime reconciles:

  1. ``app/core/plans.py``      what the SERVER grants and enforces
  2. ``apps/web/lib/plan.ts``   what the SITE advertises, inlined into the bundle at build time
  3. ``render.yaml``            the trial figure, set once per service

A one-sided edit fails nothing. It just makes the product lie to customers about what they get for
paying, which is the kind of bug you learn about from a refund request. The trial value alone has
been changed by hand more than once, in two places, and went stale in a third.

These tests are that reconciliation. They read ``render.yaml`` and the TypeScript SOURCE directly,
because the values that matter are the deployed and shipped ones, not ``Settings``' local defaults.

Note the Render dashboard can also hold a manually-edited value. A blueprint sync re-applies what is
committed, so render.yaml is the source of truth and a dashboard edit that disagrees is temporary.
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


def test_trial_grant_is_a_sane_trial():
    """A trial is a taste, not a free month. Catches a fat-fingered extra digit."""
    from app.core.plans import paid_tiers

    granted = _env_int("OMI_FREE_TRIAL_CREDITS")
    entry = paid_tiers()[0].monthly_credits
    assert granted > 0, "a zero trial grant means new accounts cannot scan at all"
    assert granted <= entry, (
        f"the free trial grants {granted} credits while the cheapest paid plan grants {entry}. A "
        f"trial that matches or beats the entry tier removes the reason to subscribe, so this is "
        f"almost certainly a typo."
    )


# --------------------------------------------------------------------------------------------- #
# The two catalogs
# --------------------------------------------------------------------------------------------- #
WEB_PLAN_TS = _REPO_ROOT / "apps" / "web" / "lib" / "plan.ts"


def _ts_tiers() -> dict[str, dict]:
    """Parse the tier table out of the TypeScript source.

    A regex over source rather than a build step, matching how ``test_signal_names_contract.py`` and
    the floor-reason contract already read their TypeScript counterparts. The alternative is running
    the bundler inside a Python test, which is a much larger dependency for the same assertion.
    """
    text = WEB_PLAN_TS.read_text(encoding="utf-8")
    # Only the PURCHASABLE table. FREE_TIER below it has the identical shape, and including it made
    # this test demand the server "sell" a plan nobody buys.
    start = text.index("export const PLAN_TIERS")
    text = text[start:text.index("export const FREE_TIER", start)]
    out: dict[str, dict] = {}
    for block in re.finditer(
        r"\{\s*slug:\s*'([a-z]+)',\s*name:\s*'([^']+)',\s*price:\s*'([^']+)',\s*"
        r"credits:\s*(\d+),\s*callCeiling:\s*(\d+),",
        text,
    ):
        slug, name, price, credits, ceiling = block.groups()
        out[slug] = {
            "name": name, "price": price,
            "credits": int(credits), "ceiling": int(ceiling),
        }
    return out


def test_the_web_catalog_lists_exactly_the_plans_the_server_sells():
    from app.core.plans import paid_tiers

    server = [t.slug for t in paid_tiers()]
    web = list(_ts_tiers())
    assert web == server, (
        f"apps/web/lib/plan.ts advertises {web} but the server sells {server}. A plan on the site "
        f"that the server cannot resolve produces a checkout that 400s; a plan the server sells but "
        f"the site never shows is revenue nobody can reach."
    )


@pytest.mark.parametrize("field", ["name", "price", "credits", "ceiling"])
def test_every_tier_agrees_between_python_and_typescript(field):
    """The numbers a customer reads must be the numbers the server enforces.

    Each of these is a promise made on the pricing page and kept (or not) by the API: the price they
    are charged, the credits they receive, and the lookup ceiling that decides when they are cut
    off. Nothing at runtime compares them.
    """
    from app.core.plans import paid_tiers

    web = _ts_tiers()
    for tier in paid_tiers():
        got = web.get(tier.slug)
        assert got is not None, f"{tier.slug} is missing from apps/web/lib/plan.ts"
        expected = {
            "name": tier.display_name,
            "price": tier.price_display,
            "credits": tier.monthly_credits,
            "ceiling": tier.monthly_call_ceiling,
        }[field]
        assert got[field] == expected, (
            f"{tier.slug}.{field}: the server says {expected!r} and the site says {got[field]!r}."
        )


def test_the_accounts_per_credit_rate_agrees_across_both_languages():
    """What a credit BUYS is stated in three places and drives what customers are charged."""
    from app.core.config import Settings
    from app.core.plans import ACCOUNTS_PER_CREDIT

    text = WEB_PLAN_TS.read_text(encoding="utf-8")
    m = re.search(r"export const ACCOUNTS_PER_CREDIT = (\d+);", text)
    assert m, "ACCOUNTS_PER_CREDIT is not declared in apps/web/lib/plan.ts"
    assert int(m.group(1)) == ACCOUNTS_PER_CREDIT == Settings.model_fields["scan_batch_unit"].default


def test_every_tier_can_actually_spend_its_credits():
    """A ceiling below what the credits can buy would sell a plan that cannot be used.

    The ceiling exists to bound COMPILE, which charges no credits. If it ever dropped below the
    scan cost of the tier's own credits, customers would be refused part way through work they had
    already paid for, and the refusal would look like a bug rather than a limit.
    """
    from app.core.plans import CALLS_PER_ACCOUNT, paid_tiers

    for tier in paid_tiers():
        need = tier.monthly_accounts * CALLS_PER_ACCOUNT
        assert tier.monthly_call_ceiling > need, (
            f"{tier.slug} includes {tier.monthly_credits} credits ({tier.monthly_accounts} "
            f"accounts, {need} scan calls) but caps lookups at {tier.monthly_call_ceiling}. "
            f"The customer could not spend what they bought."
        )
