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
// Render's internal service mesh is plain HTTP: bare host:port always gets http://.
function resolveApiOrigin(): string {
  const raw = process.env.OMI_API_ORIGIN ?? 'http://127.0.0.1:8000';
  if (/^https?:\/\//i.test(raw)) return raw.replace(/\/$/, '');
  return `http://${raw}`.replace(/\/$/, '');
}

export const env = {
  // Internal: where Next.js server-side code calls the API. Within the
  // same Render service group this can be an internal hostname.
  API_ORIGIN: resolveApiOrigin(),

  // Publicly visible. Baked into pages at BUILD time: the canonical link, the sitemap, llms.txt,
  // the JSON-LD graph and every share URL are built from it.
  //
  // The localhost fallback used to apply in production too, because it was passed as the value
  // rather than after the check, so `required()` never saw an empty string. A deploy missing the
  // variable therefore published a sitemap and a set of canonical links pointing at
  // http://localhost:3000, which tells every search engine that the real pages are duplicates of a
  // host that does not exist. Nothing fails, nothing logs, and the site simply does not get
  // indexed. Failing the build is the only signal that arrives in time to be useful.
  PUBLIC_BASE_URL: required('OMI_PUBLIC_BASE_URL', process.env.OMI_PUBLIC_BASE_URL)
    || 'http://localhost:3000',
} as const;
