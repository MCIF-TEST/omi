import { NextResponse } from 'next/server';

/**
 * The interactive API reference.
 *
 * FastAPI renders it, on the API service, which this origin fronts at /api. A redirect rather than
 * a second rendering: the reference is generated from the live spec, so anything served from here
 * would describe the API as it was at build time.
 */
export function GET(req: Request) {
  return NextResponse.redirect(new URL('/api/docs', req.url), 308);
}
