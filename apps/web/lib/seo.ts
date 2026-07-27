import type { Metadata } from 'next';
import { env } from '@/lib/env';

/**
 * Single source of truth for site-wide SEO facts — shared between the root metadata export,
 * JSON-LD structured data, and per-page metadata so the site's name, description, and canonical
 * origin can never drift between pages the way `lib/plan.ts` keeps credit figures from drifting.
 */
export const SITE_URL = env.PUBLIC_BASE_URL.replace(/\/$/, '');

export const SITE_NAME = 'OMISPHERE';
export const SITE_TAGLINE = 'Social Authenticity Intelligence';

export const SITE_DESCRIPTION =
  'Probabilistic bot and coordinated-inauthentic-behavior detection for X (Twitter) and YouTube. ' +
  'Paste a post, see every commenter scored 0-100 with the behavioral evidence behind each read.';

/** Broad terms the site is legitimately about — not stuffed into visible copy, just metadata. */
export const SITE_KEYWORDS = [
  'bot detector',
  'social media bot detector',
  'twitter bot checker',
  'x bot checker',
  'youtube bot comments',
  'fake follower checker',
  'fake engagement detector',
  'coordinated inauthentic behavior detection',
  'bought engagement detection',
  'astroturfing detection',
];

export function absoluteUrl(path: string): string {
  return `${SITE_URL}${path.startsWith('/') ? path : `/${path}`}`;
}

/**
 * Per-page metadata builder. Next.js metadata merging only replaces the top-level keys a page
 * declares — a page that sets `title`/`description` but not `openGraph`/`twitter` inherits the
 * ROOT layout's `openGraph`/`twitter` verbatim, so every shared link showed the homepage's card
 * regardless of which page was actually shared. This sets all four consistently from one title +
 * description so a new page can never forget the OG/Twitter half.
 */
export function pageMetadata({
  title,
  description,
  path,
}: {
  title: string;
  description: string;
  path: string;
}): Metadata {
  return {
    title,
    description,
    alternates: { canonical: path },
    openGraph: { title: `${title} · ${SITE_NAME}`, description, url: path },
    twitter: { title: `${title} · ${SITE_NAME}`, description },
  };
}
