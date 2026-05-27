/**
 * Runtime environment configuration. Server-side only.
 * Public values that the browser needs must be prefixed with NEXT_PUBLIC_.
 */

function required(name: string, value: string | undefined): string {
  if (!value) {
    if (process.env.NODE_ENV === 'production') {
      throw new Error(`Missing required env var: ${name}`);
    }
    return '';
  }
  return value;
}

// Render's fromService.hostport returns a bare host:port with no scheme.
// fetch() requires an absolute URL, so prefix https:// when it's missing.
function resolveApiOrigin(): string {
  const raw = process.env.OMI_API_ORIGIN ?? 'http://127.0.0.1:8000';
  if (/^https?:\/\//i.test(raw)) return raw.replace(/\/$/, '');
  const isLocal = raw.startsWith('127.0.0.1') || raw.startsWith('localhost');
  return `${isLocal ? 'http' : 'https'}://${raw}`.replace(/\/$/, '');
}

export const env = {
  // Internal: where Next.js server-side code calls the API. Within the
  // same Render service group this can be an internal hostname.
  API_ORIGIN: resolveApiOrigin(),

  // Publicly visible — included in pages.
  PUBLIC_BASE_URL: required('OMI_PUBLIC_BASE_URL', process.env.OMI_PUBLIC_BASE_URL ?? 'http://localhost:3000'),
} as const;
