/**
 * Turning the analyst's engineering-level failure reason into something a creator can act on.
 *
 * When the model is unreachable or its answer is rejected, the deterministic Floor stands in and the
 * investigation trace records a `fallback_reason` like `governor_reject: ['policy_violation']`. That
 * string is for us, not for the person who just paid for a scan.
 *
 * This lives in lib/ rather than in the panel because it is pure and it is the part worth pinning:
 * the panel's job is layout, and a wrong sentence here is a wrong claim about someone's scan.
 *
 * TOTALITY IS THE POINT. The reasons come from `app/reasoning/floor_reason.py`, which is the only
 * thing that writes the field. Every reason it can emit has an entry here, and a Python test
 * (`test_analyst_floor_classification.py`) reads THIS FILE and fails if one is added there without a
 * sentence here. Without that, a new reason renders as the generic line and nobody finds out: the
 * failure of a mapping is silence, which is exactly how `fallback_reason` came to be always null.
 */

/** The subset of the trace this needs. Kept structural so it accepts the full AnalystAssessment
 *  trace without importing the whole API surface. */
export type FailureTrace = {
  endpoint_called?: boolean;
  fallback_reason?: string | null;
};

/**
 * Every reason `classify_floor` can emit, mapped to what we tell the customer.
 *
 * `null` means "say nothing beyond that it failed", and only `deterministic_floor` gets it: that
 * reason IS "we could not tell why", and inventing a cause for it would be the confident wrong
 * explanation this whole module exists to avoid.
 *
 * Two rules the wording follows, both learned from copy that was already live:
 *
 * * **Never say "credit" about anything but the customer's own credits.** This product sells
 *   credits, so "the analysis service is out of credit" reads as "you are out of credit" and sends
 *   someone to the billing page over a fault of ours.
 * * **Name whose fault it is.** A configuration or balance problem on our side is not something the
 *   reader can fix, and saying so stops them re-running a scan that will fail identically.
 */
export const FAILURE_SENTENCES: Record<string, string | null> = {
  // Config faults. Ours, unfixable by the reader, and a retry will fail the same way.
  bad_api_key: 'The analysis service rejected our access, so no written analysis could be produced. That is a fault on our side.',
  no_credit: 'The written analysis could not be produced because of a billing problem with our analysis provider. That is on our side, not your account.',
  preset_or_model_not_found: 'The analysis model this scan asked for is not available right now. That is a fault on our side.',
  no_model_call: 'The analysis service could not be reached.',

  // Transient. Worth trying again, and the retry button is right there.
  rate_limited: 'The analysis service was busy and turned this request away. Trying again shortly usually works.',
  unreachable: 'The analysis service could not be reached.',
  gateway_error: 'The analysis service had an error of its own. Trying again shortly usually works.',
  model_timeout: 'The analysis took too long to come back and was stopped.',

  // The model answered, and what came back was not usable.
  truncated_output: 'The analysis was cut off before it finished.',
  // Ours, and self-correcting: the run asks for less room and tries again on its own. The customer
  // is told what happened without being told to do anything, because there is nothing for them to do.
  output_budget_too_large: 'This scan asked the analysis service for more room than it allows. That is a setting on our side, and the run retries itself with less.',
  http_error: 'The analysis service refused this request.',
  model_output_not_schema_valid_json: 'The analysis came back in a form we could not read.',
  governor_reject: 'The written analysis was produced but did not pass our own quality checks, so it was withheld.',

  // "We do not know." Deliberately unexplained.
  deterministic_floor: null,
};

/**
 * A customer-safe sentence explaining why no written analysis was produced, or `null` when the
 * cause cannot be classified.
 *
 * Returning `null` is deliberate and is the important case: a confident wrong explanation is worse
 * than admitting only that it failed. The caller shows the generic line on its own.
 */
export function failureReason(t: FailureTrace | null | undefined): string | null {
  if (!t) return null;
  const raw = String(t.fallback_reason ?? '').trim();

  // The endpoint was never called: no credential, provider disabled, or the host was unreachable.
  // Nothing about the scan itself is wrong, so say that it is our side. Checked before the reason
  // string because an older entry can carry this flag with no reason at all.
  if (t.endpoint_called === false) return FAILURE_SENTENCES.no_model_call;
  if (!raw) return null;

  // Match on the leading reason. `classify_floor` appends detail to several of them
  // ("governor_reject: ['S9_banned_phrase']", "http_error: 418") and older entries carry a trailing
  // parenthetical instead of a colon, so this is a prefix match rather than a split. No reason is a
  // prefix of another, which is what makes that unambiguous.
  const base = Object.keys(FAILURE_SENTENCES).find((k) => raw.startsWith(k));
  return base ? FAILURE_SENTENCES[base] : null;
}
