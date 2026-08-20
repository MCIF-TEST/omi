"""The plan catalog, the call ceiling, and the entitlements they grant.

WHY THESE ARE WORTH PINNING. Every number in ``app/core/plans.py`` is a pricing decision derived
from measured unit economics, and each one is load-bearing in a different direction:

* ``monthly_credits`` too high and the tier loses money on its heaviest customers.
* ``monthly_call_ceiling`` too high and the compile hole reopens: browsing comment sections charges
  no credits and still bills a provider, which is how one $14.99 subscriber could spend $270.
* ``monthly_call_ceiling`` too LOW and the customer cannot spend the credits they bought.
* the entitlements decide what somebody actually receives for their money.

None of it is enforced by types, so this file is where a careless edit gets caught.
"""

from __future__ import annotations

import pytest

from app.core import plans


# --------------------------------------------------------------------------------------------- #
# The catalog
# --------------------------------------------------------------------------------------------- #
def test_tiers_are_ordered_cheapest_first_and_ranked_by_that_order():
    """``at_least`` reads the order, so a reshuffle silently changes every gate."""
    assert [t.slug for t in plans.TIERS] == ["free", "starter", "reporter", "research"]
    assert plans.at_least(plans.RESEARCH, plans.REPORTER)
    assert plans.at_least(plans.REPORTER, plans.REPORTER)
    assert not plans.at_least(plans.STARTER, plans.REPORTER)


def test_entitlements_accumulate_up_the_ladder():
    """A more expensive plan must never LOSE a feature. Nobody would be able to explain that."""
    seen: set[str] = set()
    for tier in plans.TIERS:
        assert seen <= tier.features, f"{tier.slug} drops a feature a cheaper tier had"
        seen = set(tier.features)
    assert plans.RESEARCH.features == plans.ALL_FEATURES


def test_an_unknown_or_missing_slug_fails_closed_to_free():
    """Rows written before ``plan_tier`` existed, and any typo, must not grant a paid tier.

    The asymmetry is the point: a customer wrongly shown Free fixes it in one click, while the
    reverse gives the product away silently and forever.
    """
    assert plans.get_tier(None) is plans.FREE
    assert plans.get_tier("") is plans.FREE
    assert plans.get_tier("enterprise") is plans.FREE
    assert plans.get_tier("RESEARCH") is plans.RESEARCH      # case is tolerated
    assert plans.get_tier("  reporter ") is plans.REPORTER   # whitespace is tolerated


def test_only_the_paid_tiers_carry_a_stripe_price_setting():
    assert [t.slug for t in plans.paid_tiers()] == ["starter", "reporter", "research"]
    assert plans.FREE.price_setting is None, "nobody buys Free; it must not be sellable"


# --------------------------------------------------------------------------------------------- #
# Resolving a payment into an entitlement
# --------------------------------------------------------------------------------------------- #
class _S:
    stripe_price_id = "price_legacy"
    stripe_price_starter = "price_s"
    stripe_price_reporter = "price_r"
    stripe_price_research = "price_x"
    stripe_price_topup = "price_t"


def test_a_price_id_resolves_to_the_tier_that_sells_it():
    assert plans.tier_for_price_id("price_r", _S()) is plans.REPORTER
    assert plans.tier_for_price_id("price_x", _S()) is plans.RESEARCH


def test_the_legacy_single_plan_price_still_resolves_to_starter():
    """Every CURRENT subscriber is on the pre-tier Price, and renewal invoices carry it forever.

    Dropping it would leave the only people already paying unable to name a tier on their next
    renewal, which fails closed to Free: a silent downgrade of exactly the customers you have.
    """
    assert plans.tier_for_price_id("price_legacy", _S()) is plans.STARTER


def test_an_unknown_price_resolves_to_nothing_rather_than_a_default():
    """Guessing at what somebody paid for is worse than refusing to guess.

    A default here would pay out a subscription tier for a one-off credit pack, and would hide a
    misconfigured Price id behind credits that happen to arrive.
    """
    assert plans.tier_for_price_id("price_unknown", _S()) is None
    assert plans.tier_for_price_id(None, _S()) is None
    # ...and a top-up is not a tier, even though it is a real configured Price.
    assert plans.tier_for_price_id("price_t", _S()) is None
    assert plans.is_topup_price("price_t", _S())
    assert not plans.is_topup_price("price_s", _S())


def test_an_unset_price_setting_never_matches_an_empty_price_id():
    """A deployment with no Reporter Price must not resolve '' to Reporter."""

    class Blank:
        stripe_price_id = None
        stripe_price_starter = None
        stripe_price_reporter = ""
        stripe_price_research = None
        stripe_price_topup = None

    assert plans.tier_for_price_id("", Blank()) is None
    assert plans.tier_for_price_id(None, Blank()) is None


# --------------------------------------------------------------------------------------------- #
# The economics the numbers encode
# --------------------------------------------------------------------------------------------- #
@pytest.mark.parametrize("tier", plans.paid_tiers(), ids=lambda t: t.slug)
def test_a_tier_can_spend_every_credit_it_includes(tier):
    """The ceiling bounds COMPILE. It must never bound the scans the customer already paid for."""
    need = tier.monthly_accounts * plans.CALLS_PER_ACCOUNT
    assert tier.monthly_call_ceiling > need


@pytest.mark.parametrize("tier", plans.paid_tiers(), ids=lambda t: t.slug)
def test_the_compile_allowance_stays_a_minority_of_the_ceiling(tier):
    """Compile is the free half of the product and the half that has no credit to charge.

    Sized generously it stops feeling free and starts being the cost centre; the allowance is
    supposed to make browsing comfortable, not to be where the money goes.
    """
    scan = tier.monthly_accounts * plans.CALLS_PER_ACCOUNT
    allowance = tier.monthly_call_ceiling - scan
    assert 0 < allowance < scan


#: What one upstream provider call costs, in dollars. The figure the tiers were sized against.
#: If the real rate moves, every tier's margin moves with it and these bounds are what say so.
COST_PER_CALL = 0.006


def _worst_case_upstream_share(tier) -> float:
    """Upstream spend as a fraction of list price, for a customer who uses the whole ceiling.

    Upstream dominates COGS here (the model call is single-digit percent), so this is a good proxy
    for gross margin and, unlike a full cost model, it depends on nothing that changes weekly.
    """
    return (tier.monthly_call_ceiling * COST_PER_CALL) / float(tier.price_display.lstrip("$"))


@pytest.mark.parametrize("tier", plans.paid_tiers(), ids=lambda t: t.slug)
def test_no_tier_can_be_used_into_a_loss(tier):
    """The number that decides whether this business works.

    A customer burning their entire allowance must still leave a healthy margin. Before the tiers,
    twenty credits at fifty accounts each bought ~1,000 accounts for $11-15 of upstream against
    ~$14 of net revenue: a ~6% gross margin on X, and negative on a metered API.
    """
    share = _worst_case_upstream_share(tier)
    assert share < 0.35, (
        f"{tier.slug} spends {share:.0%} of its list price on upstream calls at full use. "
        f"After Stripe's cut and the model call there is not enough left."
    )


def test_margin_does_not_erode_as_the_tiers_grow():
    """The bigger plans must not be quietly less profitable than the small one.

    Upstream cost here is purely VARIABLE and perfectly linear: the ten-thousandth account costs
    what the first did. So a per-unit volume discount comes straight out of margin rather than out
    of fixed cost being spread, and modelled that way Reporter and Research fell to 46% and 41%.
    The ladder instead holds margin roughly flat and lets FEATURES justify the price, which cost
    nothing to serve. The mild per-account taper that remains is paid for by the compile allowance
    shrinking as tiers grow, not by giving away margin.
    """
    shares = [_worst_case_upstream_share(t) for t in plans.paid_tiers()]
    assert max(shares) - min(shares) < 0.05, (
        f"worst-case upstream share diverges across the ladder: "
        f"{[f'{s:.1%}' for s in shares]}. A tier is being sold at a materially worse margin than "
        f"its neighbours, which is almost always an unintended volume discount."
    )


def test_free_has_no_recurring_credits_but_still_has_a_ceiling():
    """An unpaid account making unbounded compile calls is the same hole as a paid one."""
    assert plans.FREE.monthly_credits == 0
    assert plans.FREE.monthly_call_ceiling > 0
