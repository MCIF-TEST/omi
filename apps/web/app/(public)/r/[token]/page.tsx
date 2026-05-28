import { notFound } from 'next/navigation';
import Link from 'next/link';
import { Download, FileText, Printer, ExternalLink, ShieldCheck } from 'lucide-react';
import { ApiError, type PublicReportResponse } from '@/lib/api';
import { apiServer } from '@/lib/api-server';
import { Logo } from '@/components/shared/logo';
import { TierBadge } from '@/components/shared/tier-badge';
import { ProbabilityBar } from '@/components/shared/probability-bar';
import { PrintButton, CopyLinkButton } from './print-button';

interface PageProps {
  params: { token: string };
  searchParams: { template?: 'executive' | 'evidence' };
}

export const dynamic = 'force-dynamic';

export async function generateMetadata({ params }: { params: { token: string } }) {
  try {
    const body = await apiServer<PublicReportResponse>(`/r/${encodeURIComponent(params.token)}`);
    return {
      title: `${body.view.meta.label} — OMISPHERE Report`,
      description: body.view.verdict.summary?.slice(0, 200),
    };
  } catch {
    return { title: 'OMISPHERE Report' };
  }
}

export default async function PublicReportPage({ params, searchParams }: PageProps) {
  const template = (searchParams.template === 'evidence' ? 'evidence' : 'executive') as 'executive' | 'evidence';
  let body: PublicReportResponse;
  try {
    body = await apiServer<PublicReportResponse>(
      `/r/${encodeURIComponent(params.token)}?template=${template}`,
    );
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) notFound();
    throw e;
  }
  const v = body.view;
  const pct = Math.round(v.verdict.overall_probability * 100);

  return (
    <div className="min-h-screen bg-bg-deep report-page">
      {/* Top banner — hidden on print */}
      <div className="no-print border-b border-border-1 bg-bg-elev/60 backdrop-blur sticky top-0 z-10">
        <div className="max-w-5xl mx-auto px-6 h-14 flex items-center justify-between">
          <Link href="/" aria-label="OMISPHERE home">
            <Logo />
          </Link>
          <div className="flex items-center gap-2">
            <Link
              href={`?template=${template === 'executive' ? 'evidence' : 'executive'}`}
              className="font-mono text-2xs tracking-wider uppercase px-2.5 h-7 inline-flex items-center border border-border-2 rounded-sm text-fg-dim hover:text-fg"
            >
              {template === 'executive' ? '→ Evidence view' : '→ Executive view'}
            </Link>
            <a
              href={`/r/${params.token}/markdown?template=${template}`}
              className="font-mono text-2xs tracking-wider uppercase px-2.5 h-7 inline-flex items-center gap-1.5 border border-border-2 rounded-sm text-fg-dim hover:text-fg"
            >
              <Download size={11} /> .md
            </a>
            <a
              href={`/r/${params.token}/json`}
              className="font-mono text-2xs tracking-wider uppercase px-2.5 h-7 inline-flex items-center gap-1.5 border border-border-2 rounded-sm text-fg-dim hover:text-fg"
            >
              <Download size={11} /> .json
            </a>
            <CopyLinkButton url={`/r/${params.token}`} />
            <PrintButton />
          </div>
        </div>
      </div>

      <article className="max-w-3xl mx-auto px-6 py-12 space-y-10">
        {/* Header */}
        <header>
          <div className="flex items-baseline justify-between gap-4 flex-wrap mb-4">
            <div className="font-mono text-2xs tracking-[0.18em] uppercase text-fg-mute report-muted">
              OMISPHERE · Authenticity Intelligence Report
            </div>
            <div className="font-mono text-2xs tracking-wider text-fg-mute report-muted">
              {v.meta.slug} · {template}
            </div>
          </div>
          <h1 className="text-3xl font-semibold text-fg tracking-tight leading-tight">
            {v.meta.label}
          </h1>
          <p className="mt-1 font-mono text-xs text-fg-faint break-all report-muted">
            {v.meta.input_url}
          </p>
        </header>

        {/* Verdict */}
        <section className="report-card bg-bg-elev border border-border-1 rounded-md p-8">
          <div className="font-mono text-2xs tracking-[0.18em] uppercase text-accent report-accent mb-3">
            Verdict
          </div>
          <div className="flex items-baseline gap-5 flex-wrap mb-3">
            <span className="text-6xl font-bold mono text-fg tracking-tight leading-none">{pct}%</span>
            <span className="report-tier-pill">
              <TierBadge tier={v.verdict.overall_tier} size="lg" />
            </span>
          </div>
          <ProbabilityBar value={v.verdict.overall_probability} tier={v.verdict.overall_tier} showLabel={false} />
          <p className="mt-5 text-base text-fg leading-relaxed">{v.verdict.summary}</p>
          <div className="mt-4 flex items-center gap-3 font-mono text-2xs tracking-wider uppercase text-fg-mute report-muted flex-wrap">
            {v.inputs_provided.map((i) => <span key={i}>· {i}</span>)}
          </div>
        </section>

        {/* Commentary (if owner has generated) */}
        {(v as any).commentary && (
          <section>
            <div className="font-mono text-2xs tracking-[0.18em] uppercase text-accent report-accent mb-3">
              Analyst commentary
            </div>
            <div className="report-card bg-bg-elev border border-border-1 rounded-md p-6">
              <p className="text-base text-fg leading-relaxed whitespace-pre-line">
                {(v as any).commentary.text}
              </p>
              <div className="mt-3 font-mono text-2xs tracking-wider uppercase text-fg-mute report-muted">
                Generated by {(v as any).commentary.provider}
                {(v as any).commentary.generated_at && (
                  <> · {(v as any).commentary.generated_at.slice(0, 10)}</>
                )}
              </div>
            </div>
          </section>
        )}

        {/* Headline finding */}
        {v.headline_cross_link && (
          <section>
            <div className="font-mono text-2xs tracking-[0.18em] uppercase text-accent report-accent mb-3">
              The finding
            </div>
            <div className="report-card bg-bg-elev border border-border-1 rounded-md p-6">
              <div className="flex items-center gap-3 mb-3">
                <span className="font-mono text-2xs tracking-wider uppercase text-tier-elevated report-accent">
                  {String(v.headline_cross_link.kind || '').replace(/_/g, ' ')}
                </span>
                <span className="font-mono text-2xs tracking-wider uppercase text-fg-mute report-muted">
                  · severity {v.headline_cross_link.severity}
                </span>
              </div>
              <p className="text-base text-fg leading-relaxed mb-3">
                {v.headline_cross_link.summary}
              </p>
              {(v.headline_cross_link.evidence || []).slice(0, 3).map((e: string, i: number) => (
                <p key={i} className="text-sm text-fg-dim leading-relaxed mt-1 border-l border-tier-elevated/50 pl-3">
                  {e}
                </p>
              ))}
            </div>
          </section>
        )}

        {/* Focus account (executive + evidence) */}
        {v.focus_account && (
          <section>
            <div className="font-mono text-2xs tracking-[0.18em] uppercase text-accent report-accent mb-3">
              Focus account
            </div>
            <div className="report-card bg-bg-elev border border-border-1 rounded-md p-6">
              <div className="flex items-baseline justify-between gap-3 flex-wrap mb-2">
                <h3 className="text-lg font-semibold text-fg">{v.focus_account.handle}</h3>
                <div className="flex items-center gap-3">
                  <span className="font-mono text-xl text-fg mono">
                    {Math.round((v.focus_account.overall_probability || 0) * 100)}%
                  </span>
                  <TierBadge tier={v.focus_account.tier} />
                </div>
              </div>
              {v.focus_account.intent_label && v.focus_account.tier !== 'low' && (
                <p className="font-mono text-2xs tracking-wider uppercase text-tier-elevated report-accent mb-2">
                  ▸ {v.focus_account.intent_label}
                </p>
              )}
              {v.focus_account.summary && (
                <p className="text-sm text-fg-dim leading-relaxed">{v.focus_account.summary}</p>
              )}
              {(v.focus_account.reasons || []).length > 0 && (
                <ul className="mt-3 space-y-1">
                  {v.focus_account.reasons.slice(0, 6).map((r: string, i: number) => (
                    <li key={i} className="text-sm text-fg-dim border-l border-border-2 pl-3">{r}</li>
                  ))}
                </ul>
              )}
            </div>
          </section>
        )}

        {/* Top flagged commenters */}
        {v.top_flagged.length > 0 && (
          <section>
            <div className="font-mono text-2xs tracking-[0.18em] uppercase text-accent report-accent mb-3">
              Flagged commenters · {v.total_flagged}
            </div>
            <div className="report-card bg-bg-elev border border-border-1 rounded-md overflow-hidden">
              <table className="w-full text-sm">
                <thead className="bg-bg">
                  <tr className="text-left font-mono text-2xs tracking-[0.16em] uppercase text-fg-mute report-muted">
                    <th className="px-4 py-2.5 font-normal">Handle</th>
                    <th className="px-4 py-2.5 font-normal">Tier</th>
                    <th className="px-4 py-2.5 font-normal text-right">Prob.</th>
                    <th className="px-4 py-2.5 font-normal">Intent</th>
                  </tr>
                </thead>
                <tbody>
                  {v.top_flagged.map((c) => (
                    <tr key={c.external_id} className="border-t border-border-1">
                      <td className="px-4 py-3 font-medium text-fg align-top">{c.handle}</td>
                      <td className="px-4 py-3 align-top"><TierBadge tier={c.tier} size="sm" /></td>
                      <td className="px-4 py-3 mono text-right text-fg align-top">
                        {Math.round((c.overall_probability || 0) * 100)}%
                      </td>
                      <td className="px-4 py-3 text-fg-dim align-top">{c.intent_label || '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {v.top_flagged.length < v.total_flagged && template === 'executive' && (
              <p className="mt-2 font-mono text-2xs tracking-wider uppercase text-fg-mute report-muted">
                Showing {v.top_flagged.length} of {v.total_flagged}. Switch to evidence view for the full list.
              </p>
            )}
          </section>
        )}

        {/* Evidence-only: full cross-links */}
        {template === 'evidence' && v.cross_links.length > 0 && (
          <section>
            <div className="font-mono text-2xs tracking-[0.18em] uppercase text-accent report-accent mb-3">
              Cross-links · {v.cross_links.length}
            </div>
            <div className="space-y-3">
              {v.cross_links.map((cl: any, i: number) => (
                <div key={i} className="report-card bg-bg-elev border border-border-1 rounded-md p-4">
                  <div className="flex items-center justify-between mb-2">
                    <span className="font-mono text-2xs tracking-wider uppercase text-tier-elevated report-accent">
                      {String(cl.kind || '').replace(/_/g, ' ')}
                    </span>
                    <span className="font-mono text-2xs tracking-wider uppercase text-fg-mute report-muted">
                      severity {cl.severity}
                    </span>
                  </div>
                  <p className="text-sm text-fg leading-relaxed">{cl.summary}</p>
                  {(cl.evidence || []).slice(0, 4).map((e: string, j: number) => (
                    <p key={j} className="mt-2 text-xs text-fg-dim font-mono leading-relaxed pl-3 border-l border-border-2">
                      ↳ {e}
                    </p>
                  ))}
                </div>
              ))}
            </div>
          </section>
        )}

        {/* Stats */}
        <section>
          <div className="font-mono text-2xs tracking-[0.18em] uppercase text-accent report-accent mb-3">
            Data
          </div>
          <div className="report-card bg-bg-elev border border-border-1 rounded-md p-6">
            <dl className="grid grid-cols-2 sm:grid-cols-3 gap-x-6 gap-y-4 text-sm">
              {Object.entries(v.stats).map(([k, val]) => (
                <div key={k}>
                  <dt className="font-mono text-2xs tracking-[0.16em] uppercase text-fg-mute report-muted mb-0.5">{k}</dt>
                  <dd className="text-fg mono">{val}</dd>
                </div>
              ))}
            </dl>
          </div>
        </section>

        {/* Methodology */}
        <section>
          <div className="font-mono text-2xs tracking-[0.18em] uppercase text-accent report-accent mb-3">
            Methodology
          </div>
          <p className="text-sm text-fg-dim leading-relaxed">{v.methodology}</p>
        </section>

        {/* Verification + footer */}
        <footer className="pt-8 border-t border-border-1 space-y-4">
          <div className="report-card bg-bg-elev/50 border border-border-1 rounded-md p-4 flex items-start gap-3">
            <ShieldCheck size={18} className="text-accent report-accent mt-0.5 shrink-0" />
            <div className="flex-1">
              <p className="font-mono text-2xs tracking-[0.18em] uppercase text-accent report-accent mb-1">
                Verified by OMISPHERE
              </p>
              <p className="text-sm text-fg-dim leading-relaxed">
                Report ID <span className="mono text-fg">{v.meta.slug}</span> · generated{' '}
                {v.meta.created_at?.slice(0, 10) || '—'}.
                Re-validate by re-scanning the source URL on{' '}
                <a href="/" className="text-accent hover:underline">omisphere.ai</a>.
              </p>
            </div>
          </div>
          <p className="font-mono text-2xs tracking-wider uppercase text-fg-mute report-muted leading-relaxed">
            All output is probabilistic and evidence-bearing — never a definitive judgement about
            the account or person behind it.
          </p>
        </footer>
      </article>
    </div>
  );
}
