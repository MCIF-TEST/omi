/**
 * acceptmarkdown.com content negotiation.
 *
 * THE RULE THE AUDIT FAILED ON WAS THE Vary HEADER, NOT THE NEGOTIATION.
 *
 * Serving markdown to an agent is only half of it. Without `Vary: Accept`, a CDN that has already
 * cached the HTML variant of `/pricing` will hand that HTML to the next agent asking for markdown,
 * and vice versa, decided by nothing more than which variant happened to land in the cache first.
 * The bug is intermittent, invisible in development where there is no shared cache, and it makes
 * the negotiation look broken at random. Every response this module touches carries `Vary` whether
 * or not it ended up serving markdown, because the HTML response is equally a variant.
 *
 * Parsing is deliberate about q-values. An ordinary browser sends
 * `text/html,application/xhtml+xml,...;q=0.9,*\/*;q=0.8`, and a naive substring check for "markdown"
 * is fine there but a naive check for a wildcard is not: `*\/*` must NOT win markdown, or every
 * browser on earth gets a markdown file instead of the site.
 */

export const MARKDOWN_TYPE = 'text/markdown; charset=utf-8';

/** The Vary value for any response that participated in negotiation. */
export const VARY = 'Accept, Accept-Encoding';

interface Offer {
  type: string;
  q: number;
}

function parseAccept(header: string | null): Offer[] {
  if (!header) return [];
  return header
    .split(',')
    .map((part) => {
      const [raw, ...params] = part.trim().split(';');
      const qParam = params.map((p) => p.trim()).find((p) => p.startsWith('q='));
      const q = qParam ? Number.parseFloat(qParam.slice(2)) : 1;
      return { type: raw.trim().toLowerCase(), q: Number.isFinite(q) ? q : 1 };
    })
    .filter((o) => o.type.length > 0);
}

/**
 * Whether this request wants markdown MORE than it wants HTML.
 *
 * A strict preference, not a mere mention. A client that lists both at equal quality is served
 * HTML, because that client is overwhelmingly a browser sending a long default Accept header, and
 * the cost of guessing wrong in that direction is every human visitor downloading a text file.
 */
export function prefersMarkdown(accept: string | null): boolean {
  const offers = parseAccept(accept);
  if (offers.length === 0) return false;

  let markdown = 0;
  let html = 0;
  for (const { type, q } of offers) {
    if (type === 'text/markdown' || type === 'text/x-markdown') markdown = Math.max(markdown, q);
    // A wildcard is not a request for markdown. Browsers send one on every navigation.
    else if (type === 'text/html' || type === 'application/xhtml+xml' || type === '*/*'
             || type === 'text/*') {
      html = Math.max(html, q);
    }
  }
  return markdown > 0 && markdown > html;
}
