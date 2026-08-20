/**
 * Plan facts shown in marketing and product copy. THE MIRROR OF app/core/plans.py.
 *
 * Two declarations in two languages with nothing reconciling them at runtime is the drift class this
 * codebase has been bitten by repeatedly (the signal-name contract, the floor-reason sentences, the
 * Clerk key pair). `tests/test_deployed_credit_contract.py` reads THIS FILE and fails when a tier's
 * credits, price or accounts disagree with the Python catalog, so the site can never advertise a
 * plan the server does not sell.
 *
 * NOTHING HERE CAN CHARGE A CUSTOMER. The amount actually billed lives in the Stripe Price that
 * OMI_STRIPE_PRICE_<TIER> points at, and the server sends a price id rather than an amount. What
 * these numbers CAN do is advertise the wrong thing, which is exactly why they are pinned.
 */

/** Accounts one credit buys. Mirrors `Settings.scan_batch_unit` and `plans.ACCOUNTS_PER_CREDIT`. */
export const ACCOUNTS_PER_CREDIT = 20;

export interface PlanTier {
  slug: string;
  name: string;
  /** Display only. The real charge is whatever the Stripe Price says. */
  price: string;
  credits: number;
  /** Hard ceiling on upstream lookups per billing month. */
  callCeiling: number;
  /** Who it is for. One line, in the customer's terms, not the product's. */
  audience: string;
  /** What this tier adds over the one below it. Empty on the entry tier. */
  adds: string[];
  features: string[];
}

export const FEATURE_SIGNAL_BREAKDOWN = 'signal_breakdown';
export const FEATURE_SAVED_GRAPHS = 'saved_graphs';
export const FEATURE_MONITORING = 'monitoring';
export const FEATURE_COORDINATION = 'coordination';
export const FEATURE_API_ACCESS = 'api_access';

/**
 * The three purchasable plans, cheapest first.
 *
 * The per-account price is deliberately FLAT across all three (~$5 per 100 accounts). Upstream cost
 * here is purely variable and perfectly linear, so a volume discount would come straight out of
 * margin rather than out of fixed cost being spread. What justifies the higher tiers is features,
 * whose marginal cost is zero. Do not "fix" this by discounting the big plans.
 */
export const PLAN_TIERS: PlanTier[] = [
  {
    slug: 'starter',
    name: 'Starter',
    price: '$14.99',
    credits: 12,
    callCeiling: 640,
    audience: 'For scanning a post here and there.',
    adds: [],
    features: [],
  },
  {
    slug: 'reporter',
    name: 'Reporter',
    price: '$79',
    credits: 75,
    callCeiling: 3409,
    audience: 'For journalists working a story across many posts.',
    adds: [
      'The eight-dimension breakdown behind every score',
      'Saved graphs',
      'Monitoring and watchlists',
    ],
    features: [FEATURE_SIGNAL_BREAKDOWN, FEATURE_SAVED_GRAPHS, FEATURE_MONITORING],
  },
  {
    slug: 'research',
    name: 'Research',
    price: '$249',
    credits: 250,
    callCeiling: 10869,
    audience: 'For open-source intelligence work across whole networks.',
    adds: [
      'Coordination detection across your scans',
      'Evidence that accumulates between investigations',
      'API access',
    ],
    features: [
      FEATURE_SIGNAL_BREAKDOWN,
      FEATURE_SAVED_GRAPHS,
      FEATURE_MONITORING,
      FEATURE_COORDINATION,
      FEATURE_API_ACCESS,
    ],
  },
];

export const FREE_TIER: PlanTier = {
  slug: 'free',
  name: 'Free',
  price: '$0',
  credits: 0,
  callCeiling: 307,
  audience: 'Try a scan before you pay.',
  adds: [],
  features: [],
};

export function tierBySlug(slug: string | null | undefined): PlanTier {
  if (!slug) return FREE_TIER;
  const want = String(slug).trim().toLowerCase();
  if (want === FREE_TIER.slug) return FREE_TIER;
  return PLAN_TIERS.find((t) => t.slug === want) ?? FREE_TIER;
}

/** How many accounts a tier's monthly credits buy. DERIVED — never write the number out. */
export function accountsFor(tier: PlanTier): number {
  return tier.credits * ACCOUNTS_PER_CREDIT;
}

/**
 * The tier a feature first appears on, for an upgrade prompt that names the right plan.
 *
 * Returning the CHEAPEST tier carrying the feature matters: telling a customer that the breakdown
 * needs Research when Reporter would do it is asking them for triple the money to solve their
 * problem, which reads as a shakedown rather than as pricing.
 */
export function tierForFeature(feature: string): PlanTier | null {
  return PLAN_TIERS.find((t) => t.features.includes(feature)) ?? null;
}

// ---------------------------------------------------------------------------
// The signup trial. A SEPARATE thing from the plans above, and confusing the two is easy because
// both get called "the free scans". This is a one-off grant at signup; a plan is recurring.
// ---------------------------------------------------------------------------

/** Mirrors OMI_FREE_TRIAL_CREDITS on the API service. */
export const TRIAL_CREDITS = Number(process.env.NEXT_PUBLIC_TRIAL_CREDITS || 5);

/**
 * The trial figure is configurable, so the copy around it has to agree with whatever it is set to.
 * Hardcoding "credits" read fine at 3 and became "1 free credits" the moment the trial was cut to
 * one, in five separate places. Use these rather than writing the noun out.
 */
export const CREDIT_NOUN = TRIAL_CREDITS === 1 ? 'credit' : 'credits';
export const TRIAL_CREDITS_LABEL = `${TRIAL_CREDITS} free ${CREDIT_NOUN}`;

/**
 * What the signup trial actually buys.
 *
 * DERIVED, because the last hardcoding of it went stale the moment the trial figure moved: copy on
 * the investigate page read "your 1 free credit covers up to 50 more", and at five credits the same
 * sentence became "your 5 free credits covers up to 50 more" — wrong about the number and wrong
 * about the verb.
 */
export const TRIAL_ACCOUNTS = TRIAL_CREDITS * ACCOUNTS_PER_CREDIT;

/**
 * The trial is spendable on X and YouTube only.
 *
 * Reddit runs on a metered API that bills per call, so an unrestricted trial is ~$3 of upstream per
 * signup before anybody has paid anything. At paid-acquisition scale that is a bigger number than
 * the marketing budget. The funnel keeps its strongest moment (compile is still free everywhere, so
 * a trial user pastes a Reddit link and SEES the commenters); what needs a plan is scoring them.
 */
export const TRIAL_PLATFORMS = ['x', 'youtube'] as const;

export function trialCoversPlatform(platform: string | null | undefined): boolean {
  return TRIAL_PLATFORMS.includes(String(platform || '').toLowerCase() as never);
}

// ---------------------------------------------------------------------------
// Top-ups
// ---------------------------------------------------------------------------

/**
 * Overage, and the reason the plan ceilings are not simply walls.
 *
 * A hard stop at the end of an allowance turns the most engaged customers into churn. Selling more
 * at a price that covers what it costs to serve turns the same customer into revenue, and it is
 * what makes a bounded plan honest: you are not being cut off, you are being metered.
 */
export const TOPUP_PRICE = '$1.00';
export const TOPUP_CREDITS = Number(process.env.NEXT_PUBLIC_TOPUP_PACK_CREDITS || 25);
export const TOPUP_ACCOUNTS = TOPUP_CREDITS * ACCOUNTS_PER_CREDIT;

// ---------------------------------------------------------------------------
// Legacy single-plan exports, still imported by settings and marketing copy.
// ---------------------------------------------------------------------------

/**
 * What the paid product is called as a whole. The TIER names (Starter/Reporter/Research) are what a
 * customer picks between; this is the family they belong to.
 *
 * Deliberately not an env var, unlike the credit and price figures. Those exist as env vars because
 * they can disagree with what the server actually charges and grants; a family name cannot.
 *
 * It DOES need to match the product names in the Stripe dashboard: the site says this, then Stripe
 * Checkout shows whatever the product is called, and a customer who sees two different names at the
 * moment they hand over a card reasonably wonders what they are buying. Nothing in the repo can
 * detect that drift.
 */
export const PLAN_NAME = 'Omi Premium';

/** The entry price, for copy that names one figure ("from $14.99"). */
export const SUBSCRIPTION_PRICE = PLAN_TIERS[0].price;

/** The entry tier's monthly credits. Prefer reading the tier directly where the tier is known. */
export const MONTHLY_CREDITS = PLAN_TIERS[0].credits;
