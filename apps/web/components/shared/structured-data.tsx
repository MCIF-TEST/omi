import { structuredDataGraph } from '@/lib/structured-data';
import { env } from '@/lib/env';

/**
 * The JSON-LD script tag. The graph itself lives in `lib/structured-data.ts`; see there for what it
 * declares and why.
 *
 * Rendered with the CSP nonce, because this site runs a nonce CSP and an inline script without one
 * is silently dropped. That failure mode is invisible: the page renders fine and the structured
 * data simply never exists.
 */
export function StructuredData({ nonce }: { nonce?: string }) {
  const graph = structuredDataGraph(env.PUBLIC_BASE_URL);

  return (
    <script
      type="application/ld+json"
      nonce={nonce}
      // The content is built here from constants, never from user input, so there is nothing to
      // escape beyond closing-tag injection, which cannot occur in JSON produced by stringify.
      dangerouslySetInnerHTML={{ __html: JSON.stringify(graph) }}
    />
  );
}
