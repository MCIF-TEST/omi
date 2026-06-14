/**
 * Plan facts shown in marketing/UI copy — single source of truth so the
 * displayed numbers can never drift from the deployed configuration.
 *
 * NEXT_PUBLIC_TRIAL_CREDITS is inlined at build time (works in server AND
 * client components) and MUST be kept in sync with the API service's
 * OMI_FREE_TRIAL_CREDITS (see render.yaml, where both are set side by side).
 * Defaults match the API's config default so local dev stays truthful.
 */
export const TRIAL_CREDITS = Number(process.env.NEXT_PUBLIC_TRIAL_CREDITS || 3);

/** Credits granted monthly while a subscription is active (OMI_MONTHLY_CREDIT_GRANT). */
export const MONTHLY_CREDITS = Number(process.env.NEXT_PUBLIC_MONTHLY_CREDITS || 20);
