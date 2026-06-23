import Link from 'next/link';
import { Search, ArrowRight, CheckCircle2, FolderSearch } from 'lucide-react';
import { Card, CardLabel } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { TierBadge } from '@/components/shared/tier-badge';
import { type InvestigationsListResponse, VERDICT_LABELS } from '@/lib/api';
import { apiServer } from '@/lib/api-server';
import { timeAgo } from '@/lib/format';

export const metadata = { title: 'Investigations — OMISPHERE' };

export default async function InvestigationsPage() {
  const data = await apiServer<InvestigationsListResponse>(
    '/v1/investigations?limit=100',
  ).catch(() => ({ investigations: [] } as InvestigationsListResponse));
  const investigations = data.investigations ?? [];

  const pending = investigations.filter((i) => !i.verdict || i.verdict === 'pending');
  const concluded = investigations.filter((i) => i.verdict && i.verdict !== 'pending');

  return (
    <div className="space-y-6 animate-fade-up">
      <header className="aurora relative overflow-hidden rounded-2xl border border-border-1 bg-bg-elev px-6 py-6 md:px-7">
        <span className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-accent/50 to-transparent" />
        <div className="flex items-end justify-between gap-4 flex-wrap">
          <div className="min-w-0">
            <span className="section-label">Intelligence · Archive</span>
            <h1 className="display text-2xl font-semibold text-fg tracking-tight mt-3">
              Investigations
            </h1>
            <p className="text-sm text-fg-dim mt-1.5">
              {investigations.length} saved {investigations.length === 1 ? 'investigation' : 'investigations'}
              {concluded.length > 0 && <> · <span className="text-fg-dim">{concluded.length} concluded</span></>}
            </p>
          </div>
          <div className="flex gap-2.5 shrink-0">
            <Link href="/bulk"><Button variant="secondary">Bulk scan</Button></Link>
            <Link href="/investigate"><Button size="lg" className="btn-glow"><Search size={15} /> New investigation</Button></Link>
          </div>
        </div>
      </header>

      {investigations.length === 0 ? (
        <Card className="text-center py-12">
          <div className="w-12 h-12 mx-auto mb-4 rounded-xl border border-border-2 bg-bg-elev-2 flex items-center justify-center text-accent">
            <FolderSearch size={20} strokeWidth={1.5} />
          </div>
          <h3 className="display text-base font-semibold text-fg mb-1.5">Nothing here yet</h3>
          <p className="text-sm text-fg-dim mb-5 max-w-md mx-auto leading-relaxed">
            Run your first scan to start building your investigation archive — every scan is
            saved here with its verdict, evidence, and share link.
          </p>
          <Link href="/investigate">
            <Button><Search size={14} /> Run your first scan</Button>
          </Link>
        </Card>
      ) : (
        <>
          {pending.length > 0 && (
            <Card className="p-0 overflow-hidden">
              <div className="px-5 py-3.5 border-b border-border-1 flex items-center gap-2">
                <span className="w-1.5 h-1.5 rounded-full bg-tier-moderate" />
                <CardLabel className="m-0">Open · {pending.length}</CardLabel>
              </div>
              <InvList investigations={pending} />
            </Card>
          )}
          {concluded.length > 0 && (
            <Card className="p-0 overflow-hidden">
              <div className="px-5 py-3.5 border-b border-border-1 flex items-center gap-2">
                <span className="w-1.5 h-1.5 rounded-full bg-tier-low" />
                <CardLabel className="m-0">Concluded · {concluded.length}</CardLabel>
              </div>
              <InvList investigations={concluded} />
            </Card>
          )}
        </>
      )}
    </div>
  );
}

function InvList({ investigations }: { investigations: InvestigationsListResponse['investigations'] }) {
  return (
    <ul className="divide-y divide-border-1">
      {investigations.map((inv) => (
        <li key={inv.slug}>
          <Link
            href={`/investigations/${inv.slug}`}
            className="group flex items-center justify-between gap-4 py-3 px-5 hover:bg-bg-elev-2/60 transition-colors"
          >
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2.5 mb-1 flex-wrap">
                <span className="font-medium text-fg truncate">{inv.label}</span>
                <TierBadge tier={inv.overall_tier} size="sm" />
                {inv.confidence != null && inv.confidence < 0.4 && (
                  <span
                    title={`Low confidence (${Math.round(inv.confidence * 100)}%) — limited data backed this verdict; treat cautiously when comparing.`}
                    className="font-mono text-[0.55rem] tracking-wider uppercase text-confidence-weak border border-border-2 rounded-full px-1.5 py-px"
                  >
                    low&nbsp;conf
                  </span>
                )}
                {inv.verdict && inv.verdict !== 'pending' && (
                  <span className="inline-flex items-center gap-1 font-mono text-2xs text-fg-mute uppercase tracking-wider">
                    <CheckCircle2 size={10} />
                    {VERDICT_LABELS[inv.verdict]}
                  </span>
                )}
              </div>
              <p className="text-xs text-fg-dim truncate">{inv.summary}</p>
              <div className="mt-1 flex items-center gap-3 font-mono text-2xs text-fg-mute uppercase tracking-wider">
                <span>{timeAgo(inv.created_at)}</span>
                <span className="text-border-2">·</span>
                <span
                  className="text-fg-dim tabular"
                  title={inv.confidence != null
                    ? `${Math.round(inv.overall_probability * 100)}% probability · ${Math.round(inv.confidence * 100)}% confidence (how much data backed it)`
                    : undefined}
                >{Math.round(inv.overall_probability * 100)}%</span>
                <span className="text-border-2">·</span>
                <span>{inv.batch_count} batch{inv.batch_count === 1 ? '' : 'es'}</span>
              </div>
            </div>
            <ArrowRight size={14} className="text-fg-faint shrink-0 group-hover:text-accent group-hover:translate-x-0.5 transition-all" />
          </Link>
        </li>
      ))}
    </ul>
  );
}
