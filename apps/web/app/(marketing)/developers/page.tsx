import Link from 'next/link';
import { PageMasthead, PageSection } from '@/components/shared/page-masthead';

/**
 * A named, crawlable home for the developer surface.
 *
 * The audit's finding was that a search for this product's developer resources returned nothing
 * relevant, which is what happens when the OpenAPI spec and the API reference exist but live at
 * generic paths with no page naming them. Discovery works on names, so the product name is in the
 * title, the H1 and the headings, and every machine-readable file is listed at a predictable URL.
 */
export const metadata = {
  title: 'Developer resources: API, OpenAPI spec and llms.txt',
  description:
    'OMISPHERE developer resources: the JSON HTTP API, its OpenAPI specification, authentication, '
    + 'error format, rate limits, and the machine-readable files agents can read.',
  // No `alternates` here on purpose: the key REPLACES the root layout's whole object, and the
  // layout derives both the canonical and the `<link rel="alternate" type="text/markdown">`
  // from the path. Setting a canonical here silently dropped the markdown link from this page,
  // which is the one page whose whole job is machine discoverability.
};

const FILES = [
  { href: '/openapi.json', name: 'OpenAPI specification', note: 'Machine-readable description of the OMISPHERE HTTP API.' },
  { href: '/docs', name: 'API reference', note: 'Interactive reference generated from the specification.' },
  { href: '/llms.txt', name: 'llms.txt', note: 'Agent index: what this site is and where to look.' },
  { href: '/sitemap.xml', name: 'Sitemap', note: 'Every indexable page.' },
  { href: '/robots.txt', name: 'Crawl rules', note: 'What may be crawled.' },
];

export default function DevelopersPage() {
  return (
    <div>
      <PageMasthead
        index="006"
        eyebrow="Developers"
        title="The OMISPHERE API"
        lede="A JSON HTTP API over the same engine the app uses. API access is included on the Research plan."
      />

      <PageSection label="Machine-readable files">
        <dl className="border border-border-1 divide-y divide-border-1">
          {FILES.map((f) => (
            <div key={f.href} className="flex flex-col sm:flex-row sm:items-baseline gap-1 sm:gap-4 p-4">
              <dt className="sm:w-52 shrink-0">
                <Link href={f.href} className="font-mono text-sm text-accent-text hover:underline focus-hard focus-visible:outline-none">
                  {f.href}
                </Link>
              </dt>
              <dd className="text-sm text-fg-dim min-w-0">
                <span className="text-fg">{f.name}.</span> {f.note}
              </dd>
            </div>
          ))}
        </dl>
      </PageSection>

      <PageSection label="Content negotiation">
        <p className="text-sm text-fg-dim leading-relaxed max-w-[68ch]">
          Every public page on this site is available as markdown. Send{' '}
          <code className="font-mono text-2xs bg-bg-elev border border-border-1 px-1 py-0.5">
            Accept: text/markdown
          </code>{' '}
          and the response comes back as{' '}
          <code className="font-mono text-2xs bg-bg-elev border border-border-1 px-1 py-0.5">
            text/markdown
          </code>{' '}
          with{' '}
          <code className="font-mono text-2xs bg-bg-elev border border-border-1 px-1 py-0.5">
            Vary: Accept
          </code>
          .
        </p>
        <p className="text-sm text-fg-dim leading-relaxed max-w-[68ch] mt-4">
          Each page also has its own markdown address, which needs no negotiation and has a single
          representation:{' '}
          <code className="font-mono text-2xs bg-bg-elev border border-border-1 px-1 py-0.5">
            /index.md
          </code>,{' '}
          <code className="font-mono text-2xs bg-bg-elev border border-border-1 px-1 py-0.5">
            /pricing.md
          </code>,{' '}
          <code className="font-mono text-2xs bg-bg-elev border border-border-1 px-1 py-0.5">
            /accuracy.md
          </code>, and so on for every page listed in{' '}
          <Link href="/llms.txt" className="text-accent-text hover:underline focus-hard focus-visible:outline-none">
            llms.txt
          </Link>
          .
        </p>
      </PageSection>

      <PageSection label="Errors">
        <p className="text-sm text-fg-dim leading-relaxed max-w-[68ch] mb-4">
          Errors are JSON. Every body carries a stable machine-readable <code className="font-mono text-2xs">code</code>,
          a human <code className="font-mono text-2xs">message</code>, a{' '}
          <code className="font-mono text-2xs">hint</code> describing what to do about it, and a{' '}
          <code className="font-mono text-2xs">docs</code> link. The legacy{' '}
          <code className="font-mono text-2xs">detail</code> field is kept so existing clients keep working.
        </p>
        <pre className="border border-border-1 bg-bg-deep p-4 overflow-x-auto font-mono text-2xs text-fg-dim leading-relaxed">
{`{
  "error": {
    "code": "payment_required",
    "message": "Your plan does not include this feature.",
    "hint": "Upgrade the plan on the billing page, or buy a credit pack.",
    "docs": "https://omisphere.online/developers",
    "status": 402
  },
  "detail": "Your plan does not include this feature."
}`}
        </pre>
      </PageSection>

      <PageSection label="Authentication and limits">
        <ul className="space-y-2.5">
          {[
            'Requests authenticate with a session cookie issued by the sign-in flow. Programmatic API keys are not yet issued.',
            'Requests are rate limited per IP and per user. A refused request answers 429 with Retry-After and X-RateLimit headers.',
            'A refused request never consumes credits.',
          ].map((s) => (
            <li key={s} className="flex gap-3 text-sm text-fg-dim leading-relaxed">
              <span className="mt-[0.45rem] h-px w-3 shrink-0 bg-border-hot" aria-hidden />
              <span className="min-w-0">{s}</span>
            </li>
          ))}
        </ul>
      </PageSection>
    </div>
  );
}
