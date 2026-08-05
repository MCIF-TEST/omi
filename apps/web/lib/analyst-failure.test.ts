import { describe, expect, it } from 'vitest';
import { failureReason } from './analyst-failure';

/**
 * These sentences are shown to someone who just spent a credit and got no written analysis. Getting
 * one wrong tells them something false about their own scan, which is why the mapping is pinned
 * rather than left inline in the panel.
 */
describe('failureReason', () => {
  it('names an unreachable service when the endpoint was never called', () => {
    expect(failureReason({ endpoint_called: false }))
      .toBe('The analysis service could not be reached.');
    expect(failureReason({
      fallback_reason: 'no_model_call (endpoint unset/unreachable) -> deterministic floor',
    })).toBe('The analysis service could not be reached.');
  });

  it('says the analysis was withheld when our own governance refused it', () => {
    // The customer should know a check exists and caught something, not think the product
    // silently produced nothing.
    expect(failureReason({ fallback_reason: "governor_reject: ['policy_violation']" }))
      .toMatch(/did not pass our own quality checks/);
  });

  it('says the answer was unreadable when the model replied but the body was unusable', () => {
    expect(failureReason({
      fallback_reason: 'model_output_not_schema_valid_json (endpoint returned non-JSON ...)',
    })).toBe('The analysis came back in a form we could not read.');
  });

  it('returns null rather than guessing when the cause is unclassified', () => {
    // The important case. A confident wrong explanation is worse than admitting only that it
    // failed, so the caller falls back to the generic line on its own.
    expect(failureReason({ fallback_reason: 'deterministic_floor' })).toBeNull();
    expect(failureReason({})).toBeNull();
    expect(failureReason(null)).toBeNull();
    expect(failureReason(undefined)).toBeNull();
  });

  it('does not mistake a successful call for a failure', () => {
    // endpoint_called true with no reason is not a classifiable failure.
    expect(failureReason({ endpoint_called: true, fallback_reason: null })).toBeNull();
  });

  it('never leaks the raw engineering string to the reader', () => {
    const raws = [
      'no_model_call (endpoint unset/unreachable) -> deterministic floor',
      "governor_reject: ['policy_violation']",
      'model_output_not_schema_valid_json (endpoint returned non-JSON / invalid)',
    ];
    for (const fallback_reason of raws) {
      const out = failureReason({ fallback_reason });
      expect(out).not.toBeNull();
      expect(out).not.toContain('_');
      expect(out).not.toContain('governor_reject');
    }
  });
});
