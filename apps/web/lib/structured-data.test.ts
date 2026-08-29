import { describe, it, expect } from 'vitest';

import { structuredDataGraph } from './structured-data';
import { PLAN_TIERS } from './plan';

/**
 * Structured data is read only by machines, so an error in it is invisible on the page, in the
 * browser, and in every log. It is also the copy of the price that search engines quote back to
 * people, which makes a stale one worse than a missing one.
 */

const BASE = 'https://omisphere.online';
const graph = structuredDataGraph(BASE) as { '@graph': Record<string, unknown>[] };
const nodes = graph['@graph'];
const byType = (t: string) => nodes.find((n) => n['@type'] === t)!;

describe('structured data', () => {
  it('declares the three entity types a brand query needs', () => {
    expect(nodes.map((n) => n['@type'])).toEqual(
      expect.arrayContaining(['Organization', 'WebSite', 'SoftwareApplication']),
    );
  });

  it('names the brand on every node, which is the point of the whole graph', () => {
    for (const node of nodes) {
      if ('name' in node) expect(node.name).toBe('OMISPHERE');
    }
  });

  it('ties the site and the software to the organisation by id', () => {
    const org = byType('Organization');
    for (const type of ['WebSite', 'SoftwareApplication']) {
      expect((byType(type).publisher as { '@id': string })['@id']).toBe(org['@id']);
    }
  });

  it('quotes the plan catalog rather than a second copy of the prices', () => {
    const offers = byType('SoftwareApplication').offers as { name: string; price: string }[];
    expect(offers.map((o) => o.name)).toEqual(PLAN_TIERS.map((t) => t.name));
    expect(offers.map((o) => o.price)).toEqual(
      PLAN_TIERS.map((t) => t.price.replace(/[^0-9.]/g, '')),
    );
  });

  it('states a price a parser can read, with a currency', () => {
    for (const offer of byType('SoftwareApplication').offers as { price: string; priceCurrency: string }[]) {
      expect(Number.isFinite(Number(offer.price))).toBe(true);
      expect(offer.priceCurrency).toBe('USD');
    }
  });

  it('does not double a slash when the base URL carries one', () => {
    const withSlash = structuredDataGraph(`${BASE}/`);
    expect(JSON.stringify(withSlash)).not.toContain(`${BASE}//`);
    expect(JSON.stringify(withSlash)).toBe(JSON.stringify(graph));
  });

  it('serialises without a closing tag that could break out of the script element', () => {
    expect(JSON.stringify(graph)).not.toContain('</');
  });
});
