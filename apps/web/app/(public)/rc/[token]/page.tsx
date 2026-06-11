import { notFound } from 'next/navigation';
import Link from 'next/link';
import {
  Download, ShieldCheck, AlertTriangle, Network, Clock, Hash, AtSign, Megaphone,
} from 'lucide-react';
import { ApiError, type CampaignReportResponse } from '@/lib/api';
import { apiServer } from '@/lib/api-server';
import { Logo } from '@/components/shared/logo';
import { HowToRead } from '@/components/shared/how-to-read';
import { PrintButton, CopyLinkButton } from './print-button';

interface PageProps {
  params: { token: string };
}

export const dynamic = 'force-dynamic';

const METHOD_LABEL: Record<string, string> = {
  fingerprint_cluster: 'Fingerprint cluster',
  co_engagement: 'Co-engagement',
  co_tag: 'Co-tag / co-mention',
  style_match: 'Style match',
  temporal_semantic_clique: 'Temporal-semantic',
  age_cohort: 'Account-age cohort',
};

export async function generateMetadata({ params }: { params: { token: string } }) {
  try {
    const body = await apiServer<CampaignReportResponse>(`/rc/${encodeURIComponent(params.token)}`);
    return {
      title: `${body.view.meta.name} — OMISPHERE Campaign Report`,
      description: `Coordinated-account group: ${body.view.verdict.member_count} accounts, ${Math.round(body.view.verdict.max_coordination_score * 100)}% coordination.`,
    };
  } catch {
    return { title: 'OMISPHERE Campaign Report' };
  }
}

export default async function PublicCampaignReportPage({ params }: PageProps) {
  let body: CampaignReportResponse;
  try {
    body = await apiServer<CampaignReportResponse>(`/rc/${encodeURIComponent(params.token)}`);
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) notFound();
    throw e;
  }
  const v = body.view;
  const maxPct = Math.round(v.verdict.max_coordination_score * 100);
  const confPct = Math.round(v.verdict.confidence * 100);
  const corroborated = v.verdict.corroborated;

  return (
    <div className="min-h-screen bg-bg-deep report-page">
      {/* Top banner — hidden on print */}
      <div className="no-print border-b border-border-1 bg-bg-elev/60 backdrop-blur sticky top-0 z-10">
        <div className="max-w-5xl mx-auto px-6 h-14 flex items-center justify-between">
          <Link href="/" aria-label="OMISPHERE home">
            <Logo />
          </Link>
          <div className="flex items-center gap-2">
            <a
              href={`/rc/${params.token}/markdown`}
              className="font-mono text-2xs tracking-wider uppercase px-2.5 h-7 inline-flex items-center gap-1.5 border border-border-2 rounded-sm text-fg-dim hover:text-fg"
            >
              <Download size={11} /> .md
            </a>
            <a
              href={`/rc/${params.token}/json`}
              className="font-mono text-2xs tracking-wider uppercase px-2.5 h-7 inline-flex items-center gap-1.5 border border-border-2 rounded-sm text-fg-dim hover:text-fg"
            >
              <Download size={11} /> .json
            </a>
            <CopyLinkButton url={`/rc/${params.token}`} />
            <PrintButton />
          </div>
        </div>
      </div>

      <article className="max-w-3xl mx-auto px-6 py-12 space-y-10">
        {/* Header */}
        <header>
          <div className="flex items-baseline justify-between gap-4 flex-wrap mb-4">
            <div className="font-mono text-2xs tracking-[0.18em] uppercase text-fg-mute report-muted">
              OMISPHERE · Campaign Intelligence Report
            </div>
            <div className="font-mono text-2xs tracking-wider text-fg-mute report-muted">
              {v.meta.platform} · {v.meta.status}
            </div>
          </div>
          <h1 className="text-3xl font-semibold text-fg tracking-tight leading-tight flex items-center gap-2">
            <Megaphone size={22} className="text-accent report-accent shrink-0" />
            {v.meta.name}
          </h1>
          <p className="mt-1 font-mono text-xs text-fg-faint report-muted">
            {v.verdict.member_count} accounts · seen {v.verdict.observation_count}× ·
            first detected {v.meta.first_detected_at?.slice(0, 10) || '—'} ·
            last seen {v.meta.last_seen_at?.slice(0, 10) || '—'}
          </p>
        </header>

        {/* First-view comprehension aid (dismissible, once) — the public
            report is many visitors' very first contact with Omi. */}
        <HowToRead storageKey="public-report" />

        {/* Verdict — score + confidence + corroboration, never a bare number */}
        <section className="report-card bg-bg-elev border border-border-1 rounded-md p-8">
          <div className="font-mono text-2xs tracking-[0.18em] uppercase text-accent report-accent mb-3">
            Coordination verdict
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <div>
              <div className="font-mono text-2xs uppercase tracking-wider text-fg-mute report-muted mb-1">Coordination</div>
              <div className="text-4xl font-bold mono text-fg tracking-tight leading-none">{maxPct}%</div>
              <div className="mt-1 font-mono text-2xs text-fg-mute report-muted">max observed</div>
            </div>
            <div>
              <div className="font-mono text-2xs uppercase tracking-wider text-fg-mute report-muted mb-1">Confidence</div>
              <div className="text-4xl font-bold mono text-fg tracking-tight leading-none">{confPct}%</div>
              <div className="mt-1 font-mono text-2xs text-fg-mute report-muted">
                {confPct >= 70 ? 'high' : confPct >= 40 ? 'moderate' : 'low — thin evidence'}
              </div>
            </div>
            <div>
              <div className="font-mono text-2xs uppercase tracking-wider text-fg-mute report-muted mb-1">Corroboration</div>
              <div className={`inline-flex items-center gap-1.5 mt-1 font-mono text-2xs uppercase tracking-wider px-2.5 py-1 rounded-sm border ${
                corroborated
                  ? 'border-accent/40 bg-accent/10 text-accent report-accent'
                  : 'border-tier-moderate/40 bg-tier-moderate/10 text-tier-moderate'
              }`}>
                {corroborated ? <ShieldCheck size={12} /> : <AlertTriangle size={12} />}
                {corroborated ? 'Corroborated' : 'Supporting only'}
              </div>
              <div className="mt-2 font-mono text-2xs text-fg-mute report-muted">
                {v.verdict.discriminative_methods.length > 0
                  ? `${v.verdict.discriminative_methods.length} discriminative`
                  : 'no discriminative detector'}
              </div>
            </div>
          </div>
          {!corroborated && (
            <p className="mt-5 text-sm text-fg-dim leading-relaxed border-l-2 border-tier-moderate/50 pl-3">
              Only one non-discriminative detector fired — capped at MODERATE under the
              corroboration gate. The cluster is real; the interpretation is not yet confirmed.
            </p>
          )}
        </section>

        {/* Evidence for / against */}
        <section className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="report-card bg-bg-elev border border-border-1 rounded-md p-6">
            <div className="font-mono text-2xs tracking-[0.18em] uppercase text-accent report-accent mb-3 flex items-center gap-1.5">
              <ShieldCheck size={12} /> Evidence for
            </div>
            <ul className="space-y-2 text-sm text-fg-dim">
              {v.evidence_for.length === 0
                ? <li className="text-fg-mute italic">No detectors fired.</li>
                : v.evidence_for.map((e, i) => (
                    <li key={i} className="leading-relaxed border-l border-border-2 pl-3">{e}</li>
                  ))}
            </ul>
          </div>
          <div className="report-card bg-bg-elev border border-border-1 rounded-md p-6">
            <div className="font-mono text-2xs tracking-[0.18em] uppercase text-tier-moderate mb-3 flex items-center gap-1.5">
              <AlertTriangle size={12} /> Evidence weakening
            </div>
            <ul className="space-y-2 text-sm text-fg-dim">
              {v.evidence_against.length === 0
                ? <li className="text-fg-mute italic">No counter-evidence surfaced.</li>
                : v.evidence_against.map((e, i) => (
                    <li key={i} className="leading-relaxed border-l border-border-2 pl-3">{e}</li>
                  ))}
            </ul>
          </div>
        </section>

        {/* Tags & targets */}
        {(v.hashtags.length > 0 || v.mentions.length > 0) && (
          <section>
            <div className="font-mono text-2xs tracking-[0.18em] uppercase text-accent report-accent mb-3">
              Tags &amp; targets
            </div>
            <div className="flex flex-wrap gap-1.5">
              {v.hashtags.map((h) => (
                <span key={`#${h}`} className="inline-flex items-center gap-1 font-mono text-xs px-2 py-1 rounded-sm bg-bg-elev border border-border-1 text-fg-dim">
                  <Hash size={10} className="text-fg-mute" />{h.replace(/^#/, '')}
                </span>
              ))}
              {v.mentions.map((m) => (
                <span key={`@${m}`} className="inline-flex items-center gap-1 font-mono text-xs px-2 py-1 rounded-sm bg-bg-elev border border-border-1 text-fg-dim">
                  <AtSign size={10} className="text-fg-mute" />{m.replace(/^@/, '')}
                </span>
              ))}
            </div>
          </section>
        )}

        {/* Members */}
        {v.members.length > 0 && (
          <section>
            <div className="font-mono text-2xs tracking-[0.18em] uppercase text-accent report-accent mb-3 flex items-center gap-1.5">
              <Network size={12} /> Members · {v.members.length} of {v.verdict.member_count}
            </div>
            <div className="report-card bg-bg-elev border border-border-1 rounded-md overflow-hidden">
              <table className="w-full text-sm">
                <thead className="bg-bg">
                  <tr className="text-left font-mono text-2xs tracking-[0.16em] uppercase text-fg-mute report-muted">
                    <th className="px-4 py-2.5 font-normal">Account</th>
                    <th className="px-4 py-2.5 font-normal text-right">Times</th>
                    <th className="px-4 py-2.5 font-normal">Methods</th>
                  </tr>
                </thead>
                <tbody>
                  {v.members.map((m) => (
                    <tr key={m.account_external_id} className="border-t border-border-1">
                      <td className="px-4 py-3 font-medium text-fg align-top break-all">{m.handle || m.account_external_id}</td>
                      <td className="px-4 py-3 mono text-right text-fg-dim align-top">{m.times_observed}×</td>
                      <td className="px-4 py-3 text-fg-dim align-top">
                        {(m.methods || []).map((x) => METHOD_LABEL[x] || x).join(', ') || '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        )}

        {/* Recurrence timeline */}
        {v.observations.length > 0 && (
          <section>
            <div className="font-mono text-2xs tracking-[0.18em] uppercase text-accent report-accent mb-3 flex items-center gap-1.5">
              <Clock size={12} /> Recurrence timeline · {v.observations.length}
            </div>
            <ul className="space-y-2">
              {v.observations.map((o, i) => (
                <li key={`${o.observed_at}-${i}`} className="report-card bg-bg-elev border border-border-1 rounded-md p-4">
                  <div className="flex items-center justify-between gap-3 flex-wrap">
                    <span className="font-mono text-2xs uppercase tracking-wider text-fg-dim">
                      {o.observed_at?.slice(0, 16).replace('T', ' ')} UTC
                    </span>
                    <span className="font-mono text-sm text-fg tabular-nums">
                      {Math.round((o.coordination_score || 0) * 100)}% · {o.member_count} members
                    </span>
                  </div>
                  <div className="mt-1 font-mono text-2xs text-fg-mute report-muted">
                    {(o.methods || []).map((x) => METHOD_LABEL[x] || x).join(', ') || '—'}
                  </div>
                </li>
              ))}
            </ul>
          </section>
        )}

        {/* Methodology */}
        <section>
          <div className="font-mono text-2xs tracking-[0.18em] uppercase text-accent report-accent mb-3">
            Methodology
          </div>
          <p className="text-sm text-fg-dim leading-relaxed">{v.methodology}</p>
        </section>

        {/* First-run conversion + cross-navigation — the anonymous visitor just
            experienced the value moment; offer the next step without friction. */}
        <section className="no-print border border-accent/25 bg-accent/[0.05] rounded-md p-5">
          <p className="text-sm text-fg leading-relaxed mb-3">
            This report was generated by OMISPHERE from the platform&apos;s own
            disclosure data — coordination re-derived from behaviour, with the
            evidence and the counter-evidence in one place.
          </p>
          <div className="flex flex-wrap items-center gap-2">
            <Link
              href="/signup"
              className="inline-flex items-center gap-1.5 bg-accent text-bg-deep font-semibold px-4 h-9 rounded-sm hover:bg-accent-2 transition-colors text-sm"
            >
              Investigate your own target — free
            </Link>
            {(v.other_featured ?? []).map((o) => (
              <a
                key={o.share_token}
                href={`/rc/${o.share_token}`}
                className="inline-flex items-center gap-1.5 px-3 h-9 border border-border-2 text-fg-dim rounded-sm font-mono text-xs tracking-wider uppercase hover:text-fg hover:border-border-hot"
              >
                Compare: {o.name.length > 38 ? `${o.name.slice(0, 38)}…` : o.name}
              </a>
            ))}
          </div>
        </section>

        {/* Verification + disclaimer */}
        <footer className="pt-8 border-t border-border-1 space-y-4">
          <div className="report-card bg-bg-elev/50 border border-border-1 rounded-md p-4 flex items-start gap-3">
            <ShieldCheck size={18} className="text-accent report-accent mt-0.5 shrink-0" />
            <div className="flex-1">
              <p className="font-mono text-2xs tracking-[0.18em] uppercase text-accent report-accent mb-1">
                OMISPHERE Campaign Intelligence
              </p>
              <p className="text-sm text-fg-dim leading-relaxed">
                Campaign <span className="mono text-fg">{v.meta.campaign_key}</span>
                {v.meta.published_at && <> · published {v.meta.published_at.slice(0, 10)}</>}.
                Observations, not verdicts — re-validate on{' '}
                <a href="/" className="text-accent hover:underline">omisphere.ai</a>.
              </p>
            </div>
          </div>
          <p className="font-mono text-2xs tracking-wider uppercase text-fg-mute report-muted leading-relaxed">
            {v.disclaimer}
          </p>
        </footer>
      </article>
    </div>
  );
}
