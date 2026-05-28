import Link from 'next/link';
import { Search, ArrowRight, CheckCircle2 } from 'lucide-react';
import { Card, CardLabel, CardTitle } from '@/components/ui/card';
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
    <div className="space-y-6">
      <header className="flex items-end justify-between gap-4 flex-wrap">
        <div>
          <p className="font-mono text-2xs tracking-[0.18em] text-fg-mute uppercase mb-1">
            Archive
          </p>
          <h1 className="text-2xl font-semibold text-fg tracking-tight">
            Investigations
          </h1>
        </div>
        <div className="flex gap-3">
          <Link href="/bulk">
            <Button variant="secondary">Bulk scan</Button>
          </Link>
          <Link href="/investigate">
            <Button size="lg">
              <Search size={16} />
              New investigation
            </Button>
          </Link>
        </div>
      </header>

      {investigations.length === 0 ? (
        <Card>
          <CardTitle>Nothing here yet</CardTitle>
          <p className="text-sm text-fg-dim mb-5">
            Run your first scan to start building your investigation archive.
          </p>
          <Link href="/investigate">
            <Button>
              <Search size={14} /> Run your first scan
            </Button>
          </Link>
        </Card>
      ) : (
        <>
          {/* Active / unresolved */}
          {pending.length > 0 && (
            <Card>
              <CardLabel className="mb-3">
                Open · {pending.length}
              </CardLabel>
              <InvList investigations={pending} />
            </Card>
          )}

          {/* Concluded */}
          {concluded.length > 0 && (
            <Card>
              <CardLabel className="mb-3">
                Concluded · {concluded.length}
              </CardLabel>
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
    <ul className="divide-y divide-border-1 -mx-2">
      {investigations.map((inv) => (
        <li key={inv.slug}>
          <Link
            href={`/investigations/${inv.slug}`}
            className="flex items-center justify-between gap-4 py-3 px-2 hover:bg-bg-elev-2/50 transition-colors rounded-sm"
          >
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-3 mb-1 flex-wrap">
                <span className="font-medium text-fg truncate">{inv.label}</span>
                <TierBadge tier={inv.overall_tier} size="sm" />
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
                <span>·</span>
                <span className="text-fg-dim">{Math.round(inv.overall_probability * 100)}%</span>
                <span>·</span>
                <span>{inv.batch_count} batch{inv.batch_count === 1 ? '' : 'es'}</span>
              </div>
            </div>
            <ArrowRight size={14} className="text-fg-mute shrink-0" />
          </Link>
        </li>
      ))}
    </ul>
  );
}
