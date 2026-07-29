/**
 * Plan facts shown in marketing/UI copy. Single source of truth so the
 * displayed numbers can never drift from the deployed configuration.
 *
 * NEXT_PUBLIC_TRIAL_CREDITS is inlined at build time (works in server AND
 * client components) and MUST be kept in sync with the API service's
 * OMI_FREE_TRIAL_CREDITS (see render.yaml, where both are set side by side).
 * Defaults match the API's config default so local dev stays truthful.
 */
export const TRIAL_CREDITS = Number(process.env.NEXT_PUBLIC_TRIAL_CREDITS || 3);

/**
 * What the paid plan is called, everywhere it is named.
 *
 * Not an env var on purpose: unlike the credit figures, this cannot disagree with anything the
 * server does, so a second copy in Render would be a liability rather than a safeguard.
 *
 * It DOES need to match the product name in the Stripe dashboard. The site says this, then Checkout
 * shows whatever Stripe has, and a customer who sees two different plan names at the moment they
 * hand over a card reasonably wonders what they are buying. Renaming the Stripe product is a
 * dashboard change, not a code one.
 */
export const PLAN_NAME = 'Omi Premium Member';

/** Credits granted monthly while a subscription is active (OMI_MONTHLY_CREDIT_GRANT). */
export const MONTHLY_CREDITS = Number(process.env.NEXT_PUBLIC_MONTHLY_CREDITS || 20);

/**
 * What the subscription costs, as displayed. Mirrors the API's
 * OMI_SUBSCRIPTION_PRICE_DISPLAY, which is itself display-only: the amount a customer is actually
 * charged lives in the Stripe Price that OMI_STRIPE_PRICE_ID points at, so no value here can ever
 * charge the wrong number. It CAN advertise the wrong number, which is why the pricing page reads
 * this instead of hardcoding a figure, and why test_deployed_credit_contract fails on drift.
 */
export const SUBSCRIPTION_PRICE = process.env.NEXT_PUBLIC_SUBSCRIPTION_PRICE || '$13.99';
