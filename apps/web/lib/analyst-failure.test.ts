import { describe, expect, it } from 'vitest';
import { FAILURE_SENTENCES, failureReason } from './analyst-failure';

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

  it('explains a config fault as ours, without sending anyone to their billing page', () => {
    // This product sells credits, so "the analysis service is out of credit" reads as "you are out
    // of credit". Naming whose fault it is stops someone re-running a scan that will fail the same
    // way, or worse, paying us again over a fault of ours.
    const noCredit = failureReason({ fallback_reason: 'no_credit' }) ?? '';
    expect(noCredit).toMatch(/our side/i);
    expect(noCredit).not.toMatch(/your credit|out of credits/i);
    expect(failureReason({ fallback_reason: 'bad_api_key' })).toMatch(/our side/i);
    expect(failureReason({ fallback_reason: 'preset_or_model_not_found' })).toMatch(/our side/i);
  });

  it('invites another try only for the faults a retry can fix', () => {
    for (const reason of ['rate_limited', 'gateway_error']) {
      expect(failureReason({ fallback_reason: reason })).toMatch(/again/i);
    }
    // A dead credential will fail identically, so telling someone to try again wastes their time.
    for (const reason of ['bad_api_key', 'no_credit', 'preset_or_model_not_found']) {
      expect(failureReason({ fallback_reason: reason })).not.toMatch(/trying again/i);
    }
  });

  it('reads the detail appended after a reason without tripping over it', () => {
    // classify_floor appends detail so the LOG stays actionable ("http_error: 418",
    // "governor_reject: ['S9_banned_phrase']"). The customer sentence must survive that.
    expect(failureReason({ fallback_reason: 'gateway_error: 502' }))
      .toBe(FAILURE_SENTENCES.gateway_error);
    expect(failureReason({ fallback_reason: 'model_output_not_schema_valid_json: missing verdict' }))
      .toBe(FAILURE_SENTENCES.model_output_not_schema_valid_json);
  });

  it('has a usable sentence for every reason except the one that means "we cannot tell"', () => {
    // Totality. The Python side pins the other direction (every reason it can emit has a key here);
    // this pins that a key is not an empty string or a placeholder.
    for (const [reason, sentence] of Object.entries(FAILURE_SENTENCES)) {
      if (reason === 'deterministic_floor') {
        expect(sentence).toBeNull();
        continue;
      }
      expect(sentence, reason).toBeTruthy();
      expect(sentence!.trim().length, reason).toBeGreaterThan(20);
      expect(sentence, reason).not.toContain('_');
      expect(sentence!.endsWith('.'), reason).toBe(true);
    }
  });

  it('has no reason that is a prefix of another', () => {
    // The lookup is a prefix match, which is only unambiguous while that holds.
    const keys = Object.keys(FAILURE_SENTENCES);
    for (const a of keys) {
      for (const b of keys) {
        if (a !== b) expect(a.startsWith(b), `${a} starts with ${b}`).toBe(false);
      }
    }
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

// ---------------------------------------------------------------------------
// A batched run that is still going is not a failed run.
//
// Live symptom: the panel showed "SCORING IN BATCHES: 1 OF 4 DONE ... 3 more batches to go" AND
// "The written analysis could not be produced for this scan" at the same time. The first batch had
// floored, so isModelBacked() was false over the merged-so-far assessment, and the terminal notice
// rendered while the run was visibly still working. A later batch can still land a model-backed
// result. The rule the panel now applies is encoded here so it cannot drift back.
// ---------------------------------------------------------------------------
type Batching = { total: number; done: number; batch_size: number; complete: boolean } | undefined;

/** Mirror of the guard in AssessmentView: only judge a run once it has finished. */
function showsTerminalFailure(modelBacked: boolean, batching: Batching): boolean {
  const stillBatching = batching ? batching.complete === false : false;
  if (!modelBacked && stillBatching) return false;
  return !modelBacked;
}

describe('when the failed-analysis notice may appear', () => {
  it('stays hidden while more batches are still queued', () => {
    // The exact live case: batch 1 of 4 floored, three still to run.
    expect(showsTerminalFailure(false, { total: 4, done: 1, batch_size: 25, complete: false }))
      .toBe(false);
  });

  it('appears once the batched run is over and nothing was model-backed', () => {
    expect(showsTerminalFailure(false, { total: 4, done: 4, batch_size: 25, complete: true }))
      .toBe(true);
  });

  it('appears for a single-shot run that failed, where there is no batching block at all', () => {
    expect(showsTerminalFailure(false, undefined)).toBe(true);
  });

  it('never appears for a model-backed result, mid-run or finished', () => {
    expect(showsTerminalFailure(true, { total: 4, done: 1, batch_size: 25, complete: false }))
      .toBe(false);
    expect(showsTerminalFailure(true, undefined)).toBe(false);
  });
});
