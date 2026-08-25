import { PLAN_TIERS } from './plan';

/**
 * Schema.org JSON-LD for the organisation and the site.
 *
 * This is how a search engine learns that OMISPHERE is an ENTITY rather than a word that happens to
 * appear on a page. The audit found a brand search returning nine results without this domain among
 * them, and while most of that fix is off-platform (links, mentions, time), an unclaimed entity is
 * the part that can be fixed in the markup: without it there is nothing for a knowledge panel to
 * attach to and nothing declaring which domain the name belongs to.
 *
 * Pure and in `lib` rather than beside the component, so it can be asserted on directly. Structured
 * data is read only by machines, so a mistake in it is invisible on the page and in every log, the
 * same property as llms.txt and the sitemap, and it gets the same treatment.
 */
export function structuredDataGraph(base: string) {
  const origin = base.replace(/\/$/, '');
  return {
    '@context': 'https://schema.org',
    '@graph': [
      {
        '@type': 'Organization',
        '@id': `${origin}/#organization`,
        name: 'OMISPHERE',
        alternateName: 'OmiSphere',
        url: origin,
        description:
          'OMISPHERE detects bots, bought engagement, and AI-written replies in social media '
          + 'comment sections.',
        slogan: 'The transparency layer of the internet.',
      },
      {
        '@type': 'WebSite',
        '@id': `${origin}/#website`,
        url: origin,
        name: 'OMISPHERE',
        publisher: { '@id': `${origin}/#organization` },
        inLanguage: 'en',
      },
      {
        '@type': 'SoftwareApplication',
        '@id': `${origin}/#software`,
        name: 'OMISPHERE',
        applicationCategory: 'SecurityApplication',
        operatingSystem: 'Web',
        url: origin,
        description:
          'Paste a link to an X post or a YouTube video, choose which commenters to analyse, and '
          + 'receive a score for each account with the evidence behind it.',
        publisher: { '@id': `${origin}/#organization` },
        // DERIVED from the plan catalog, never a second copy of it. The prices are already
        // declared in two languages with a test reconciling them (`test_deployed_credit_contract`);
        // a third copy here would be the one nothing checks, and it would be published to search
        // engines as the authoritative price of the product.
        offers: PLAN_TIERS.map((tier) => ({
          '@type': 'Offer',
          name: tier.name,
          price: tier.price.replace(/[^0-9.]/g, ''),
          priceCurrency: 'USD',
          category: 'subscription',
        })),
      },
    ],
  };
}
