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
