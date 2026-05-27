/** @type {import('next').NextConfig} */

// Normalise OMI_API_ORIGIN — Render's `fromService.hostport` returns a bare
// `host:port` with no scheme. Next.js rewrites require an absolute URL, so
// prefix `https://` when missing. Local dev uses http://127.0.0.1:8000.
function resolveApiOrigin() {
  const raw = process.env.OMI_API_ORIGIN || 'http://127.0.0.1:8000';
  if (/^https?:\/\//i.test(raw)) return raw.replace(/\/$/, '');
  // Bare host or host:port — assume https in prod, http for localhost.
  const isLocal = raw.startsWith('127.0.0.1') || raw.startsWith('localhost');
  return `${isLocal ? 'http' : 'https'}://${raw}`.replace(/\/$/, '');
}

const API_ORIGIN = resolveApiOrigin();

const nextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
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
