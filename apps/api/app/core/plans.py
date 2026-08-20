"""The plan catalog: what each tier costs you, what it grants, and what it unlocks.

WHY A CATALOG RATHER THAN MORE SETTINGS FIELDS.

Before this, a plan was three unrelated values scattered across config (``monthly_credit_grant``,
``stripe_price_id``, ``subscription_price_display``) plus a hardcoded ``is_admin`` check wherever a
feature was gated. That works for exactly one plan. With three, every one of those values has to be
resolved *from the tier the customer actually bought*, and the resolution has to happen in the same
place every time or the tiers drift apart: a customer on Research granted Starter's credits, or a
feature gate that says Reporter in one file and Research in another.

So a tier is ONE object. Everything the rest of the codebase asks about a plan comes from here.

THE NUMBERS ARE DERIVED FROM UNIT ECONOMICS, NOT PICKED
-------------------------------------------------------
Each tier is sized so that a subscriber who burns *every* credit still leaves a ~70% gross margin
after Stripe's cut. That is the whole point of ``monthly_call_ceiling``: credits bound how many
accounts are SCORED, but before this change nothing bounded how many upstream calls a customer could
make, because compiling a comment section charges no credits and still hits the provider. One
subscriber could spend $270 of upstream against $14.99 of revenue without doing anything abusive.

Worst-case economics at ~$0.006/upstream-call, conservative model pricing (see docs/pricing.md):

    tier      credits  accounts  call ceiling   COGS      margin
    starter        12       240           640   ~$4.03-4.47   69-72%
    reporter       75     1,500         3,409   ~$21.59-24.22 68-72%
    research      250     5,000        10,869   ~$69.02-77.76 68-71%

COGS is PURELY VARIABLE and perfectly linear here: the ten-thousandth account costs exactly what the
first one did. So a per-unit volume discount comes straight out of margin rather than out of fixed
cost being amortised, and the higher tiers deliberately do NOT discount per account (all three sit
near $5 per 100 accounts). What justifies their price is FEATURES, whose marginal cost is zero.

CHANGING A NUMBER HERE CHANGES WHAT YOU EARN. Raising ``monthly_credits`` without moving the price
lowers the margin one-for-one; raising ``monthly_call_ceiling`` past what the credits can spend
re-opens the unbounded-compile hole this exists to close.
"""

from __future__ import annotations

from dataclasses import dataclass

#: Accounts one credit buys. Mirrors ``Settings.scan_batch_unit`` and ``ACCOUNTS_PER_CREDIT`` in
#: apps/web/lib/plan.ts; ``tests/test_deployed_credit_contract.py`` fails on drift between them.
ACCOUNTS_PER_CREDIT = 20

#: Upstream calls one scored account costs (profile + history). Compile is on top, which is what
#: ``COMPILE_HEADROOM`` below pays for.
CALLS_PER_ACCOUNT = 2

# Feature keys. Strings rather than an Enum so a stored/serialised entitlement stays readable in a
# JSON payload and in a log line.
FEATURE_SIGNAL_BREAKDOWN = "signal_breakdown"
FEATURE_SAVED_GRAPHS = "saved_graphs"
FEATURE_MONITORING = "monitoring"
FEATURE_COORDINATION = "coordination"
FEATURE_API_ACCESS = "api_access"

ALL_FEATURES: frozenset[str] = frozenset({
    FEATURE_SIGNAL_BREAKDOWN,
    FEATURE_SAVED_GRAPHS,
    FEATURE_MONITORING,
    FEATURE_COORDINATION,
    FEATURE_API_ACCESS,
})


@dataclass(frozen=True)
class PlanTier:
    """One purchasable plan.

    ``price_display`` is display-only and proves nothing: the amount actually charged lives in the
    Stripe Price, so no value in this repo can charge a customer the wrong number. It CAN advertise
    the wrong one, which is why the pricing page reads it from here.
    """

    slug: str
    display_name: str
    monthly_credits: int
    #: Hard ceiling on upstream provider calls per billing month. Sized at the credits' own scan
    #: cost plus a compile allowance, so browsing feels free without being free.
    monthly_call_ceiling: int
    price_display: str
    #: Settings attribute holding this tier's Stripe Price id. Not the id itself: it differs between
    #: test and live mode, so it has to stay an env var.
    price_setting: str | None
    features: frozenset[str]
    #: One line for the pricing page. Says who the tier is for, not what it contains.
    audience: str

    @property
    def monthly_accounts(self) -> int:
        return self.monthly_credits * ACCOUNTS_PER_CREDIT

    def has(self, feature: str) -> bool:
        return feature in self.features


def _ceiling(credits: int, compile_headroom: float) -> int:
    """Call ceiling for a tier: what its credits can spend on scans, plus a compile allowance.

    ``compile_headroom`` shrinks as tiers grow and that is not arbitrary. A casual user compiles five
    posts to scan one; a researcher compiles once and scans a hundred deep. Giving every tier the
    same proportional allowance would over-provision the tiers whose COGS is largest.
    """
    scan_calls = credits * ACCOUNTS_PER_CREDIT * CALLS_PER_ACCOUNT
    return int(scan_calls / (1.0 - compile_headroom))


#: The free tier. No Stripe price: nobody buys it, it is what an account has before it pays and what
#: it falls back to when a subscription lapses. Its ceiling still exists, because an unpaid account
#: making unbounded compile calls is the same hole as a paid one making them.
FREE = PlanTier(
    slug="free",
    display_name="Free",
    monthly_credits=0,          # the signup trial grants credits separately; this is the recurring rate
    monthly_call_ceiling=_ceiling(5, 0.35),   # sized to let the 5-credit trial actually be spent
    price_display="$0",
    price_setting=None,
    features=frozenset(),
    audience="Try a scan before you pay.",
)

STARTER = PlanTier(
    slug="starter",
    display_name="Starter",
    monthly_credits=12,
    monthly_call_ceiling=_ceiling(12, 0.25),
    price_display="$14.99",
    price_setting="stripe_price_starter",
    features=frozenset(),
    audience="For scanning a post here and there.",
)

REPORTER = PlanTier(
    slug="reporter",
    display_name="Reporter",
    monthly_credits=75,
    monthly_call_ceiling=_ceiling(75, 0.12),
    price_display="$79",
    price_setting="stripe_price_reporter",
    features=frozenset({
        FEATURE_SIGNAL_BREAKDOWN,
        FEATURE_SAVED_GRAPHS,
        FEATURE_MONITORING,
    }),
    audience="For journalists working a story across many posts.",
)

RESEARCH = PlanTier(
    slug="research",
    display_name="Research",
    monthly_credits=250,
    monthly_call_ceiling=_ceiling(250, 0.08),
    price_display="$249",
    price_setting="stripe_price_research",
    features=ALL_FEATURES,
    audience="For open-source intelligence work across whole networks.",
)

#: Ordered cheapest first. Order is load-bearing for the pricing page and for ``at_least``.
TIERS: tuple[PlanTier, ...] = (FREE, STARTER, REPORTER, RESEARCH)

BY_SLUG: dict[str, PlanTier] = {t.slug: t for t in TIERS}

#: The tier an account has when it has never paid, or when its subscription has lapsed.
DEFAULT_TIER = FREE

#: Accounts one top-up credit buys, and what it sells for. Priced at ~70% margin on the same
#: arithmetic as the tiers, so buying overage is never cheaper per account than subscribing (which
#: would make the subscription pointless) and never so expensive that a heavy user churns instead.
TOPUP_PRICE_DISPLAY = "$1.00"


def get_tier(slug: str | None) -> PlanTier:
    """The tier for a stored slug. An unknown or absent value is FREE, never a paid tier.

    Failing closed matters: a typo'd slug, or a row written before ``plan_tier`` existed, must not
    hand somebody Research entitlements. The customer sees an upgrade prompt (recoverable in one
    click); the alternative silently gives away the product.
    """
    if not slug:
        return DEFAULT_TIER
    return BY_SLUG.get(str(slug).strip().lower(), DEFAULT_TIER)


def rank(tier: PlanTier) -> int:
    """Position in TIERS. Used to answer "is this at least Reporter?"."""
    try:
        return TIERS.index(tier)
    except ValueError:
        return 0


def at_least(tier: PlanTier, minimum: PlanTier) -> bool:
    return rank(tier) >= rank(minimum)


def paid_tiers() -> tuple[PlanTier, ...]:
    """The tiers a customer can actually buy, cheapest first."""
    return tuple(t for t in TIERS if t.price_setting)


def tier_for_price_id(price_id: str | None, settings) -> PlanTier | None:
    """Which tier a Stripe Price id belongs to, or None if it is not a subscription price.

    This is how a payment becomes an entitlement. It returns None rather than a default on purpose:
    the caller must be able to tell "this invoice bought Reporter" from "this invoice was for
    something else entirely" (a top-up pack), and defaulting would silently grant a subscription
    tier for a one-off credit purchase.
    """
    if not price_id:
        return None
    wanted = str(price_id).strip()
    for tier in paid_tiers():
        configured = getattr(settings, tier.price_setting, None)
        if configured and str(configured).strip() == wanted:
            return tier

    # The LEGACY single-plan price, from before tiers existed. Every current subscriber's renewal
    # invoices carry it forever, so it has to keep resolving or the people already paying would fail
    # closed to Free on their next renewal. It maps to Starter: the tier whose price it was.
    legacy = getattr(settings, "stripe_price_id", None)
    if legacy and str(legacy).strip() == wanted:
        return STARTER
    return None


def is_topup_price(price_id: str | None, settings) -> bool:
    """Whether a Price id is the one-off top-up pack.

    Kept separate from ``tier_for_price_id`` because the two answers drive different behaviour: a
    tier changes the subscription and its recurring grant, a top-up adds credits and must touch
    nothing else. A single function returning "some plan" would invite the caller to conflate them.
    """
    if not price_id:
        return False
    configured = getattr(settings, "stripe_price_topup", None)
    return bool(configured and str(configured).strip() == str(price_id).strip())
