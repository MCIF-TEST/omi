import { NextResponse } from 'next/server';

import { env } from '@/lib/env';

/**
 * The OpenAPI specification, at the conventional root address.
 *
 * The spec already existed, on the API service, at a path the web origin did not serve. So
 * /developers named it, llms.txt linked it, and both pointed at a 404: the discoverability work was
 * advertising a document nobody could fetch. It is proxied rather than duplicated because a second
 * committed copy would be stale the first time a route changed, and a stale API description is
 * worse than none.
 *
 * `servers` is rewritten to the browser-visible origin. FastAPI describes itself relative to the
 * host it is running on, which on this deployment is an internal hostname no client can reach.
 */
export const dynamic = 'force-dynamic';

export async function GET() {
  try {
    const upstream = await fetch(`${env.API_ORIGIN}/openapi.json`, {
      headers: { accept: 'application/json' },
      next: { revalidate: 300 },
    });
    if (!upstream.ok) throw new Error(`upstream ${upstream.status}`);

    const spec = await upstream.json();
    const base = env.PUBLIC_BASE_URL.replace(/\/$/, '');
    // The API is fronted at /api on this origin (see next.config rewrites), so that, and not the
    // API service's own hostname, is the prefix a client should send requests to.
    spec.servers = [{ url: `${base}/api`, description: 'OmiSphere API' }];

    return NextResponse.json(spec, {
      headers: {
        'Cache-Control': 'public, max-age=300, s-maxage=300',
        'Content-Type': 'application/json; charset=utf-8',
      },
    });
  } catch {
    // The same envelope the API itself emits, so a client parsing errors does not need a second
    // shape for the one endpoint that describes all the others.
    return NextResponse.json(
      {
        error: {
          code: 'upstream_error',
          message: 'The API specification is temporarily unavailable.',
          hint: 'Retry shortly. The API itself is unaffected by this endpoint being down.',
          docs: 'https://omisphere.online/developers',
          status: 502,
        },
        detail: 'The API specification is temporarily unavailable.',
      },
      { status: 502, headers: { 'Cache-Control': 'no-store' } },
    );
  }
}
