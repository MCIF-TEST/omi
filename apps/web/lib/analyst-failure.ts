/**
 * Turning the analyst's engineering-level failure reason into something a creator can act on.
 *
 * When the model is unreachable or its answer is rejected, the deterministic Floor stands in and the
 * investigation trace records a `fallback_reason` like `governor_reject: ['policy_violation']`. That
 * string is for us, not for the person who just paid for a scan.
 *
 * This lives in lib/ rather than in the panel because it is pure and it is the part worth pinning:
 * the panel's job is layout, and a wrong sentence here is a wrong claim about someone's scan.
 */

/** The subset of the trace this needs. Kept structural so it accepts the full AnalystAssessment
 *  trace without importing the whole API surface. */
export type FailureTrace = {
  endpoint_called?: boolean;
  fallback_reason?: string | null;
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
  const raw = String(t.fallback_reason ?? '');

  // The endpoint was never called: no credential, provider disabled, or the host was unreachable.
  // Nothing about the scan itself is wrong, so say that it is our side.
  if (t.endpoint_called === false || raw.startsWith('no_model_call')) {
    return 'The analysis service could not be reached.';
  }
  // The model answered and our own governance layer refused to publish it. The customer should know
  // the check exists rather than think the product silently produced nothing.
  if (raw.startsWith('governor_reject')) {
    return 'The written analysis was produced but did not pass our own quality checks, so it was withheld.';
  }
  // A 200 whose body was not usable: truncated, not JSON, or failing the schema.
  if (raw.startsWith('model_output_not_schema_valid_json')) {
    return 'The analysis came back in a form we could not read.';
  }
  return null;
}
