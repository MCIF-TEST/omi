/**
 * One name for the analyst, everywhere a reader can see it.
 *
 * The product has exactly one analyst and it is called the Omi Analyst. The gateway it happens to
 * run on is an implementation detail of ours, and naming it on the site tells a customer that the
 * thing they are paying for is somebody else's. Nothing rendered anywhere, including the operator
 * diagnostics, says otherwise.
 *
 * WHY THIS IS A FUNCTION AND NOT A CODE REVIEW RULE. The vendor name does not appear in our copy at
 * all; it arrives inside VALUES that pass through the API and get rendered as data. The provider
 * string on a trace is `openrouter-omi-analyst-v1`, a floored one is
 * `openrouter->fallback:deterministic-analyst-v1`, and a transport failure is `ProviderError:
 * openrouter HTTP 404`. Every one of those is written by the backend and printed verbatim, so the
 * only reliable place to stop it is at the point of render.
 *
 * The diagnostics keep their meaning. An operator still needs to know whether the model answered or
 * the deterministic floor stood in, and that distinction is preserved in Omi's own words.
 */

export const ANALYST_NAME = 'Omi Analyst';

/** Anything that has ever appeared inside a provider or transport string on this path. */
const VENDOR = /open\s*router/gi;

/**
 * Whether a provider string describes a real model answer or the deterministic fallback.
 * Mirrors `entry_is_model_backed` on the API, which keys on the same two substrings.
 */
function isFallback(provider: string): boolean {
  return /fallback|deterministic|floor/i.test(provider);
}

/**
 * The analyst label for a raw provider string, for the operator diagnostics.
 *
 * Returns Omi's own vocabulary, never the gateway's: "Omi Analyst (model)" when the model authored
 * the result, "Omi Analyst (deterministic floor)" when it stood in. Both are more useful to a
 * reader than `openrouter->fallback:deterministic-analyst-v1`, and neither names a third party.
 */
export function analystProviderLabel(provider: string | null | undefined): string {
  const p = (provider ?? '').trim();
  if (!p) return ANALYST_NAME;
  return isFallback(p) ? `${ANALYST_NAME} (deterministic floor)` : `${ANALYST_NAME} (model)`;
}

/**
 * Strip the vendor name out of any free-text diagnostic before it is rendered.
 *
 * Used on transport error strings, which are built by the backend and can carry the gateway name in
 * the middle of an otherwise useful message ("openrouter HTTP 404", "openrouter unreachable"). The
 * rest of the message is exactly what an operator needs, so this replaces rather than discards.
 */
export function scrubVendor(text: string | null | undefined): string {
  const t = (text ?? '').trim();
  if (!t) return '';
  return t.replace(VENDOR, ANALYST_NAME).replace(/\s{2,}/g, ' ').trim();
}
