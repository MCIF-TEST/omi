import Link from 'next/link';
import { Search, Activity, Database, Zap, ArrowRight } from 'lucide-react';
import { Card, CardLabel, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { TierBadge } from '@/components/shared/tier-badge';
import { type EngineStatus, type InvestigationsListResponse } from '@/lib/api';
import { apiServer } from '@/lib/api-server';
import { getCurrentUser } from '@/lib/auth';
import { timeAgo } from '@/lib/format';

export const metadata = { title: 'Dashboard — OMISPHERE' };

export default async function DashboardPage() {
  const [user, status, invList] = await Promise.all([
    getCurrentUser(),
    apiServer<EngineStatus>('/v1/status').catch(() => null),
    apiServer<InvestigationsListResponse>('/v1/investigations?limit=10').catch(
      () => ({ investigations: [] } as InvestigationsListResponse),
    ),
  ]);
  const investigations = invList.investigations || [];

  return (
    <div className="space-y-8">
      <header className="flex items-end justify-between gap-4 flex-wrap">
        <div>
          <p className="font-mono text-2xs tracking-[0.18em] text-fg-mute uppercase mb-1">
            Welcome back
          </p>
          <h1 className="text-2xl font-semibold text-fg tracking-tight">
            {user?.email}
          </h1>
        </div>
        <Link href="/investigate">
          <Button size="lg">
            <Search size={16} />
            Start an investigation
          </Button>
        </Link>
      </header>

      {/* Stat grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <Stat
          icon={<Zap size={14} />}
          label="Credits remaining"
          value={user?.credits_remaining ?? 0}
          sub={
            user?.subscription_status === 'active'
              ? 'subscription active'
              : '3 free trial credits'
          }
          tone={user && user.credits_remaining === 0 ? 'danger' : 'accent'}
        />
        <Stat
          icon={<Database size={14} />}
          label="Fingerprints stored"
          value={status?.fingerprints_stored ?? '—'}
          sub="across all scans"
        />
        <Stat
          icon={<Activity size={14} />}
          label="Total scans (lifetime)"
          value={status?.total_scans ?? '—'}
          sub="self-improving database"
        />
        <Stat
          icon={<Search size={14} />}
          label="Coordination edges"
          value={status?.total_engagement_edges ?? '—'}
          sub="commenter ↔ video links"
        />
      </div>

      <Card>
        <div className="flex items-center justify-between mb-3 gap-2">
          <CardLabel className="m-0">Recent investigations</CardLabel>
          <Link
            href="/investigate"
            className="font-mono text-2xs tracking-wider text-accent hover:text-accent-2 uppercase"
          >
            + new scan
          </Link>
        </div>
        {investigations.length === 0 ? (
          <div>
            <CardTitle>Nothing here yet</CardTitle>
            <p className="text-sm text-fg-dim mb-5">
              Start an investigation to scan a YouTube video or channel.
              Every scan trains the OMISPHERE database — the engine
              sharpens with every use.
            </p>
            <Link href="/investigate">
              <Button>
                <Search size={14} /> Run your first scan
              </Button>
            </Link>
          </div>
        ) : (
          <ul className="divide-y divide-border-1 -mx-2">
            {investigations.map((inv) => (
              <li key={inv.slug}>
                <Link
                  href={`/investigations/${inv.slug}`}
                  className="flex items-center justify-between gap-4 py-3 px-2 hover:bg-bg-elev-2/50 transition-colors rounded-sm"
                >
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-3 mb-1">
                      <span className="font-medium text-fg truncate">{inv.label}</span>
                      <TierBadge tier={inv.overall_tier} size="sm" />
                    </div>
                    <p className="text-xs text-fg-dim truncate">{inv.summary}</p>
                    <div className="mt-1 flex items-center gap-3 font-mono text-2xs text-fg-mute uppercase tracking-wider">
                      <span>{timeAgo(inv.created_at)}</span>
                      <span>·</span>
                      <span className="mono text-fg-dim">{Math.round(inv.overall_probability * 100)}%</span>
                      <span>·</span>
                      <span>{inv.batch_count} batch{inv.batch_count === 1 ? '' : 'es'}</span>
                      <span>·</span>
                      <span>{inv.quota_used} quota</span>
                    </div>
                  </div>
                  <ArrowRight size={14} className="text-fg-mute shrink-0" />
                </Link>
              </li>
            ))}
          </ul>
        )}
      </Card>

      {/* Coming-soon strip */}
      <Card className="border-dashed">
        <CardLabel>Capabilities — coming in later phases</CardLabel>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-2 text-sm text-fg-dim">
          <SoonItem n="03">Narrative intelligence — track talking points across accounts</SoonItem>
          <SoonItem n="04">Graph view — coordination networks in Cytoscape</SoonItem>
          <SoonItem n="06">Investigative report export (PDF, shareable links)</SoonItem>
          <SoonItem n="08">Live monitoring — watchlists, anomaly alerts</SoonItem>
        </div>
      </Card>
    </div>
  );
}

interface StatProps {
  icon: React.ReactNode;
  label: string;
  value: number | string;
  sub: string;
  tone?: 'accent' | 'danger';
}

function Stat({ icon, label, value, sub, tone }: StatProps) {
  return (
    <div className="bg-bg-elev border border-border-1 rounded-md p-5">
      <div className="flex items-center justify-between mb-3">
        <span className="font-mono text-2xs tracking-[0.18em] text-fg-mute uppercase">
          {label}
        </span>
        <span
          className={
            tone === 'danger'
              ? 'text-danger'
              : tone === 'accent'
                ? 'text-accent'
                : 'text-fg-mute'
          }
        >
          {icon}
        </span>
      </div>
      <div className="text-3xl font-semibold text-fg tracking-tight mono mb-1">
        {value}
      </div>
      <div className="text-xs text-fg-mute">{sub}</div>
    </div>
  );
}

function SoonItem({ n, children }: { n: string; children: React.ReactNode }) {
  return (
    <div className="flex items-baseline gap-3 py-1">
      <span className="font-mono text-2xs text-accent">{n}</span>
      <span>{children}</span>
      <Badge variant="warn" className="ml-auto">soon</Badge>
    </div>
  );
}
