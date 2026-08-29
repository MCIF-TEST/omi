import type { MetadataRoute } from 'next';
import { env } from '@/lib/env';

/**
 * Crawl rules. Public marketing pages are indexable; everything that is private or link-shared is not.
 *
 * `/r/` is the tokenised share route. It carries no auth by design. Anyone with the link
 * can read the report, so keeping them out of an index is the only thing preserving "unlisted".
 * Disallowing them here is belt to the per-route `robots: { index: false }` braces, because a crawler
 * that never fetches the page never sees the meta tag.
 */
export default function robots(): MetadataRoute.Robots {
  const base = env.PUBLIC_BASE_URL.replace(/\/$/, '');
  return {
    rules: [
      {
        userAgent: '*',
        // The two developer documents live on the API service, which this origin fronts at /api.
        // /api/ is disallowed wholesale below, so without these the only machine-readable
        // description of the API would be blocked by our own crawl rules while being advertised on
        // /developers and in llms.txt. A more specific Allow wins over a broader Disallow.
        allow: ['/', '/api/openapi.json', '/api/docs'],
        disallow: [
          '/api/',
          '/r/',        // shared investigation reports (unlisted by token)
          '/sign-in',
          '/sign-up',
          '/login',
          '/signup',
          '/forgot-password',
          '/reset-password',
          '/signed-out',
          '/settings',
          '/investigate',
          '/investigations',
          '/graph',
          '/monitoring',
          '/search',
          '/bulk',
          '/accounts',
          '/channels',
          '/content',
        ],
      },
    ],
    sitemap: base ? `${base}/sitemap.xml` : undefined,
  };
}
