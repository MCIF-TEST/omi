/**
 * Resolve which platform an account deep-scan should target.
 *
 * Rules (see the founder-reported X→YouTube routing defect):
 *  - The investigation's platform is AUTHORITATIVE. A comment-level platform
 *    must never silently override it.
 *  - Nothing ever assumes YouTube. An unset/unrecognized value is 'unknown'.
 *  - When the investigation platform is unavailable, fall back to the
 *    commenter's own platform ONLY if it is itself a known value; otherwise the
 *    result is 'unknown' and the caller MUST refuse to scan (no credit, error).
 */
export type ScanPlatform = 'x' | 'youtube' | 'unknown';

function normalize(p: string | null | undefined): ScanPlatform {
  const v = (p || '').toLowerCase();
  if (v === 'x' || v === 'twitter') return 'x';
  if (v === 'youtube') return 'youtube';
  return 'unknown';
}

export function resolveScanPlatform(
  investigationPlatform?: string | null,
  commenterPlatform?: string | null,
): ScanPlatform {
  const inv = normalize(investigationPlatform);
  if (inv !== 'unknown') return inv; // investigation platform is authoritative
  return normalize(commenterPlatform); // fall back only to a KNOWN commenter platform
}

/** The account-scan endpoint for a resolved platform, or null when unknown. */
export function accountScanEndpoint(p: ScanPlatform): string | null {
  if (p === 'x') return '/v1/scan/twitter/account';
  if (p === 'youtube') return '/v1/scan/youtube/account';
  return null; // unknown. Caller must not scan
}
