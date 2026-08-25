import Link from 'next/link';
import { AGENT_PAGES } from '@/lib/agent-content';

/**
 * The root 404.
 *
 * Next.js already returns a real 404 STATUS for an unmatched path, which is the half the audit
 * scored as passing. What was missing is the half that lets an agent recover: a body naming where
 * to look next. A 404 whose body is a decorative apology tells a crawler only that it failed.
 *
 * So this page lists the real public surface and the machine-readable files, as links a crawler
 * follows and a person can click. The markdown variant of the same recovery list is served by the
 * middleware when the request asked for `Accept: text/markdown`.
 *
 * Deliberately built from `AGENT_PAGES`, so a page added to the site appears here without anyone
 * remembering to add it.
 */
export const metadata = {
  title: 'Page not found',
  robots: { index: false, follow: true },
};

const FILES = [
  { href: '/llms.txt', label: 'llms.txt', note: 'What this site is, for agents' },
  { href: '/sitemap.xml', label: 'sitemap.xml', note: 'Every indexable page' },
  { href: '/developers', label: '/developers', note: 'API, OpenAPI spec, error format' },
];

export default function NotFound() {
  return (
    <main className="min-h-[100dvh] flex flex-col justify-center px-5 py-16">
      <div className="w-full max-w-2xl mx-auto">
        <div className="flex items-center gap-2.5 mb-7">
          <span className="w-2 h-2 bg-accent shrink-0" aria-hidden />
          <span className="font-mono text-[0.625rem] tracking-[0.18em] uppercase text-fg-faint">
            OmiSphere
          </span>
          <span className="h-px flex-1 bg-border-1" aria-hidden />
          <span className="font-mono text-[0.625rem] tracking-[0.18em] uppercase text-fg-faint tabular-nums">
            404
          </span>
        </div>

        <h1 className="display-hard text-[clamp(2rem,7vw,3.25rem)] leading-[0.98] tracking-[-0.02em] text-fg mb-4">
          Page not found
        </h1>
        <p className="text-fg-dim leading-relaxed max-w-[52ch] mb-10">
          That address does not exist on OmiSphere. Everything public is listed below.
        </p>

        <h2 className="font-mono text-[0.625rem] tracking-[0.18em] uppercase text-fg-faint mb-3">
          Pages
        </h2>
        <ul className="border-t border-border-1 divide-y divide-border-1 mb-9">
          {AGENT_PAGES.map((p) => (
            <li key={p.path} className="py-2.5">
              <Link
                href={p.path}
                className="font-mono text-sm text-accent-text hover:underline focus-hard focus-visible:outline-none"
              >
                {p.path}
              </Link>
              <span className="text-sm text-fg-mute"> {p.summary}</span>
            </li>
          ))}
        </ul>

        <h2 className="font-mono text-[0.625rem] tracking-[0.18em] uppercase text-fg-faint mb-3">
          Machine-readable
        </h2>
        <ul className="border-t border-border-1 divide-y divide-border-1">
          {FILES.map((f) => (
            <li key={f.href} className="py-2.5">
              <Link
                href={f.href}
                className="font-mono text-sm text-accent-text hover:underline focus-hard focus-visible:outline-none"
              >
                {f.label}
              </Link>
              <span className="text-sm text-fg-mute"> {f.note}</span>
            </li>
          ))}
        </ul>
      </div>
    </main>
  );
}
