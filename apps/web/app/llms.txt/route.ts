import { llmsTxt } from '@/lib/agent-content';
import { env } from '@/lib/env';

/**
 * /llms.txt — the llmstxt.org index.
 *
 * A route handler rather than a static file in `public/`, because the body has to carry the
 * deployment's own origin on every link. A hardcoded domain in a static file is wrong the moment
 * anyone runs a preview deploy, and wrong quietly: the file still serves, it just points every
 * agent at production.
 *
 * Served as text/plain per the convention. `Vary: Accept` is not needed here (there is only one
 * representation) but the cache headers are, because this is read far more often than it changes.
 */
export const dynamic = 'force-static';
export const revalidate = 3600;

export function GET(): Response {
  return new Response(llmsTxt(env.PUBLIC_BASE_URL), {
    status: 200,
    headers: {
      'Content-Type': 'text/plain; charset=utf-8',
      'Cache-Control': 'public, max-age=3600, s-maxage=3600',
    },
  });
}
