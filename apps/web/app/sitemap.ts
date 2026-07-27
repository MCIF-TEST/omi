import type { MetadataRoute } from 'next';
import { env } from '@/lib/env';

/**
 * Sitemap for the public surface only.
 *
 * Deliberately hand-listed rather than generated: everything else in this app is either behind auth or
 * reachable only by an unlisted share token, and a sitemap that enumerated those would defeat the point
 * of them being unlisted. If a new marketing page is added, add it here — a missing entry costs a little
 * discovery time, whereas a wrong entry publishes something private.
 */
export default function sitemap(): MetadataRoute.Sitemap {
  const base = env.PUBLIC_BASE_URL.replace(/\/$/, '');
  const now = new Date();

  return [
    { url: `${base}/`,                       lastModified: now, changeFrequency: 'weekly',  priority: 1.0 },
    { url: `${base}/bot-detector`,            lastModified: now, changeFrequency: 'monthly', priority: 0.9 },
    { url: `${base}/twitter-bot-checker`,     lastModified: now, changeFrequency: 'monthly', priority: 0.9 },
    { url: `${base}/youtube-bot-comments`,    lastModified: now, changeFrequency: 'monthly', priority: 0.9 },
    { url: `${base}/pricing`,                 lastModified: now, changeFrequency: 'monthly', priority: 0.8 },
    { url: `${base}/about`,                   lastModified: now, changeFrequency: 'monthly', priority: 0.5 },
    { url: `${base}/privacy`,                 lastModified: now, changeFrequency: 'yearly',  priority: 0.3 },
    { url: `${base}/terms`,                   lastModified: now, changeFrequency: 'yearly',  priority: 0.3 },
  ];
}
