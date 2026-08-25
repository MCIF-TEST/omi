import type { MetadataRoute } from 'next';
import { indexablePaths } from '@/lib/agent-content';
import { env } from '@/lib/env';

/**
 * Sitemap for the public surface only.
 *
 * Deliberately hand-listed rather than generated: everything else in this app is either behind auth or
 * reachable only by an unlisted share token, and a sitemap that enumerated those would defeat the point
 * of them being unlisted. If a new marketing page is added, add it here, a missing entry costs a little
 * discovery time, whereas a wrong entry publishes something private.
 */
export default function sitemap(): MetadataRoute.Sitemap {
  const base = env.PUBLIC_BASE_URL.replace(/\/$/, '');
  const now = new Date();

  // DERIVED from the same module that feeds llms.txt, the markdown negotiation and the 404 recovery
  // links. Four surfaces have to agree about which pages are public, nothing at runtime reconciles
  // them, and every one of them is read only by machines, so a page added to one and forgotten in
  // the others fails silently and invisibly.
  const priority: Record<string, number> = {
    '/': 1.0, '/pricing': 0.8, '/developers': 0.7, '/accuracy': 0.6,
    '/about': 0.5, '/privacy': 0.3, '/terms': 0.3,
  };
  const frequency: Record<string, 'weekly' | 'monthly' | 'yearly'> = {
    '/': 'weekly', '/pricing': 'monthly', '/developers': 'monthly',
    '/accuracy': 'monthly', '/about': 'monthly', '/privacy': 'yearly', '/terms': 'yearly',
  };

  return indexablePaths().map((path) => ({
    url: path === '/' ? `${base}/` : `${base}${path}`,
    lastModified: now,
    changeFrequency: frequency[path] ?? 'monthly',
    priority: priority[path] ?? 0.5,
  }));
}
