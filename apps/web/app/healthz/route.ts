/**
 * Liveness probe for the web service.
 *
 * The API declared `healthCheckPath`; the web service did not, so Render had no way to tell a wedged
 * Next process from a healthy one and would never restart it. A hung frontend is a full outage even
 * while the API is fine.
 *
 * Deliberately shallow: it answers "is this process still serving?" and nothing else. It must not call
 * the API or the database, a health check that depends on downstream services turns one dependency's
 * slowness into a restart loop here, which is strictly worse than reporting healthy while degraded.
 */
export const dynamic = 'force-dynamic';

export function GET() {
  return new Response(JSON.stringify({ status: 'ok', service: 'omisphere-web' }), {
    status: 200,
    headers: {
      'Content-Type': 'application/json',
      'Cache-Control': 'no-store',
    },
  });
}
