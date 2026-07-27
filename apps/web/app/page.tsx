import { headers } from 'next/headers';
import { LandingPage } from './landing-page';
import { SITE_DESCRIPTION, SITE_NAME, SITE_URL } from '@/lib/seo';
import { MONTHLY_CREDITS } from '@/lib/plan';

/**
 * The public front door. No user lookup, no API call.
 *
 * This used to be `force-dynamic` and `await getCurrentUser()`, so every anonymous visitor triggered a
 * blocking internal call to FastAPI (`/v1/auth/me`) that hit the database — to answer nothing more than
 * "are you already signed in?". That put the API and the database in the critical path of the one page
 * traffic is bought for, capped its throughput at theirs, and took the marketing site down with the API.
 *
 * The signed-in redirect moved to `middleware.ts`, which checks for a session cookie at the edge with no
 * network call. Cookie presence is not proof of a valid session and does not need to be: a stale cookie
 * lands on `/investigate`, which does the real server-side verification and bounces to sign-in.
 *
 * NOT fully static, and not because of anything here. The root layout reads `headers()` to get the CSP
 * nonce, which opts the whole tree into per-request rendering. That is a deliberate trade — a nonce CSP
 * is worth more than CDN caching — so this page is still rendered per request, just cheaply, with no
 * downstream dependency. Removing `force-dynamic` here keeps that honest: if the nonce requirement ever
 * goes away, this page becomes static with no further change.
 */
/**
 * SoftwareApplication JSON-LD for the product itself, so a search result for a bot-detection query
 * can render as a rich product result (name, description, price, rating surface if one is ever
 * added) rather than a bare blue link. Reuses the same nonce the root layout reads, since this is a
 * separate inline script and the CSP has no 'unsafe-inline'.
 */
function softwareApplicationJsonLd() {
  return {
    '@context': 'https://schema.org',
    '@type': 'SoftwareApplication',
    name: SITE_NAME,
    url: SITE_URL,
    applicationCategory: 'SecurityApplication',
    operatingSystem: 'Web',
    description: SITE_DESCRIPTION,
    offers: {
      '@type': 'Offer',
      price: '9.99',
      priceCurrency: 'USD',
      description: `$9.99/month for ${MONTHLY_CREDITS} scan credits, with a free trial to start`,
    },
  };
}

export default function Root() {
  const nonce = headers().get('x-nonce') ?? undefined;
  return (
    <>
      <script
        type="application/ld+json"
        nonce={nonce}
        dangerouslySetInnerHTML={{ __html: JSON.stringify(softwareApplicationJsonLd()) }}
      />
      <LandingPage />
    </>
  );
}
