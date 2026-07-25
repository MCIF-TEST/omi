/** @type {import('next').NextConfig} */

// Normalise OMI_API_ORIGIN — Render's `fromService.hostport` returns a bare
// `host:port` with no scheme. Next.js rewrites require an absolute URL.
// Render's internal service mesh is plain HTTP — never HTTPS — so bare
// host:port values always get http://, not https://.
function resolveApiOrigin() {
  const raw = process.env.OMI_API_ORIGIN || 'http://127.0.0.1:8000';
  if (/^https?:\/\//i.test(raw)) return raw.replace(/\/$/, '');
  // Bare host or host:port (Render's fromService.hostport) — always HTTP.
  return `http://${raw}`.replace(/\/$/, '');
}

const API_ORIGIN = resolveApiOrigin();

/** Static security headers on every path (including _next/static). CSP with nonces is set in middleware. */
const SECURITY_HEADERS = [
  {
    key: 'Strict-Transport-Security',
    value: 'max-age=63072000; includeSubDomains; preload',
  },
  { key: 'X-Frame-Options', value: 'DENY' },
  { key: 'X-Content-Type-Options', value: 'nosniff' },
  { key: 'Referrer-Policy', value: 'strict-origin-when-cross-origin' },
  {
    key: 'Permissions-Policy',
    value:
      'camera=(), microphone=(), geolocation=(), payment=(), usb=(), interest-cohort=(), accelerometer=(), gyroscope=(), magnetometer=()',
  },
  { key: 'Cross-Origin-Opener-Policy', value: 'same-origin-allow-popups' },
  { key: 'Cross-Origin-Resource-Policy', value: 'same-site' },
  { key: 'X-XSS-Protection', value: '0' },
  { key: 'X-DNS-Prefetch-Control', value: 'off' },
];

const nextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  async headers() {
    return [
      {
        source: '/:path*',
        headers: SECURITY_HEADERS,
      },
    ];
  },
  // In dev, proxy /api/* to the FastAPI service so the browser sees a
  // single origin (auth cookies cross transparently). In production the
  // platform fronts both services behind the same domain — same effect.
  async rewrites() {
    return [
      {
        source: '/api/:path*',
        destination: `${API_ORIGIN}/:path*`,
      },
    ];
  },
};

export default nextConfig;
