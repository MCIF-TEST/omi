/** @type {import('next').NextConfig} */
const API_ORIGIN = process.env.OMI_API_ORIGIN || 'http://127.0.0.1:8000';

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
