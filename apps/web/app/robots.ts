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
        allow: '/',
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
