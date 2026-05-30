import Link from 'next/link';
import {
  Search, Activity, Database, Zap, ArrowRight, CheckCircle2, Gift,
  Network, MessageSquareText, FileSearch, Radio, LayoutGrid,
} from 'lucide-react';
import { Card, CardLabel } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { TierBadge } from '@/components/shared/tier-badge';
import { type EngineStatus, type InvestigationsListResponse, VERDICT_LABELS } from '@/lib/api';
import { apiServer } from '@/lib/api-server';
import { getCurrentUser } from '@/lib/auth';
import { timeAgo } from '@/lib/format';
import { cn } from '@/lib/cn';
import { AnimatedNumber } from '@/components/shared/animated-number';

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
    <div className="space-y-7 animate-fade-up">

      {/* Header */}
      <header className="border border-border-1 rounded-lg bg-bg-elev px-6 py-5 md:px-7 md:py-6 shadow-inner-top">
        <div className="flex items-end justify-between gap-4 flex-wrap">
          <div className="min-w-0">
            <p className="font-mono text-2xs tracking-[0.18em] text-fg-mute uppercase mb-1.5 flex items-center gap-2">
              <span className="w-1.5 h-1.5 rounded-full bg-tier-low animate-pulse-dot" />
              OMISPHERE workspace
            </p>
            <h1 className="display text-xl md:text-2xl font-semibold text-fg tracking-tight truncate">
              {user?.email}
            </h1>
          </div>
          <Link href="/investigate" className="shrink-0">
            <Button size="lg" className="btn-glow">
              <Search size={14} />
              New investigation
            </Button>
          </Link>
        </div>
      </header>

      {/* Stats */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 stagger">
        <StatCard
          icon={<Zap size={13} />}
          label="Credits"
          value={user?.credits_remaining ?? 0}
          sub={user?.subscription_status === 'active' ? 'subscription active' : '3 free trial credits'}
          tone={user && user.credits_remaining === 0 ? 'danger' : 'accent'}
        />
        <StatCard
          icon={<Database size={13} />}
          label="Fingerprints"
          value={status?.fingerprints_stored ?? 0}
          sub="stored across all scans"
        />
        <StatCard
          icon={<Activity size={13} />}
          label="Total scans"
          value={status?.total_scans ?? 0}
          sub="self-improving database"
        />
        <StatCard
          icon={<Search size={13} />}
          label="Coord. edges"
          value={status?.total_engagement_edges ?? 0}
          sub="commenter ↔ video links"
        />
      </div>

      {/* Recent investigations */}
      <Card>
        <div className="flex items-center justify-between mb-4 gap-2">
          <CardLabel className="m-0">Recent investigations</CardLabel>
          <Link
            href="/investigate"
            className="font-mono text-2xs tracking-wider text-accent hover:text-accent-2 uppercase transition-colors"
          >
            + New scan
          </Link>
        </div>

        {investigations.length === 0 ? (
          <div className="py-4">
            <h3 className="text-base font-semibold text-fg mb-2">Nothing here yet</h3>
            <p className="text-sm text-fg-dim mb-5">
              Start an investigation to scan a YouTube video or channel.
              Every scan trains the OMISPHERE database — the engine sharpens with every use.
            </p>
            <Link href="/investigate">
              <Button>
                <Search size={13} /> Run your first scan
              </Button>
            </Link>
          </div>
        ) : (
          <ul className="divide-y divide-border-1 -mx-2">
            {investigations.map((inv) => (
              <li key={inv.slug}>
                <Link
                  href={`/investigations/${inv.slug}`}
                  className="group flex items-center gap-4 py-3 px-2 hover:bg-bg-elev-2/50 transition-colors rounded-sm"
                >
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2 mb-1 flex-wrap">
                      <span className="font-medium text-fg truncate text-sm">{inv.label}</span>
                      <TierBadge tier={inv.overall_tier} size="sm" />
                      {inv.verdict && inv.verdict !== 'pending' && (
                        <span className="inline-flex items-center gap-1 font-mono text-2xs text-fg-mute uppercase tracking-wider">
                          <CheckCircle2 size={9} />
                          {VERDICT_LABELS[inv.verdict]}
                        </span>
                      )}
                    </div>
                    <p className="text-xs text-fg-dim truncate">{inv.summary}</p>
                    <div className="mt-1 flex items-center gap-3 font-mono text-2xs text-fg-mute uppercase tracking-wider">
                      <span>{timeAgo(inv.created_at)}</span>
                      <span className="text-border-2">·</span>
                      <span className="text-fg-dim">{Math.round(inv.overall_probability * 100)}%</span>
                      <span className="text-border-2">·</span>
                      <span>{inv.batch_count} batch{inv.batch_count === 1 ? '' : 'es'}</span>
                    </div>
                  </div>
                  <ArrowRight size={12} className="text-fg-faint shrink-0 group-hover:text-fg-mute group-hover:translate-x-0.5 transition-all" />
                </Link>
              </li>
            ))}
          </ul>
        )}
      </Card>

      {/* Explore capabilities */}
      <div>
        <CardLabel className="mb-3">Explore capabilities</CardLabel>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
          {[
            { href: '/search',         icon: Search,            code: 'SR', label: 'Account search',   desc: 'Find any scanned account instantly' },
            { href: '/bulk',           icon: LayoutGrid,        code: 'BK', label: 'Bulk scan',        desc: 'Queue up to 20 URLs at once' },
            { href: '/narratives',     icon: MessageSquareText, code: 'NR', label: 'Narrative intel',  desc: 'Trending talking points across scans' },
            { href: '/graph',          icon: Network,           code: 'GR', label: 'Graph view',       desc: 'Coordination network explorer' },
            { href: '/investigations', icon: FileSearch,        code: 'IV', label: 'Investigations',   desc: 'Full archive with share & export' },
            { href: '/monitoring',     icon: Radio,             code: 'MN', label: 'Monitoring',       desc: 'Watchlists and anomaly alerts' },
          ].map(({ href, icon: Icon, label, desc }) => (
            <Link
              key={href}
              href={href}
              className="group flex items-center gap-3 p-3.5 rounded-lg border border-border-1 bg-bg-elev/30 card-interactive"
            >
              <span className="shrink-0 w-8 h-8 rounded-sm bg-bg-elev-2 border border-border-2 flex items-center justify-center text-fg-mute group-hover:text-accent group-hover:border-accent/35 transition-colors">
                <Icon size={14} strokeWidth={1.5} />
              </span>
              <div className="min-w-0">
                <div className="text-sm text-fg font-medium">{label}</div>
                <div className="text-xs text-fg-dim truncate">{desc}</div>
              </div>
            </Link>
          ))}
        </div>
      </div>

      {/* Referral nudge */}
      {user?.referral_code && (
        <Link href="/settings" className="block group">
          <div className="flex items-center gap-4 p-4 rounded-lg border border-accent/20 bg-accent/[0.04] hover:border-accent/35 transition-colors">
            <div className="shrink-0 w-9 h-9 rounded-sm border border-accent/25 bg-bg flex items-center justify-center text-accent">
              <Gift size={15} />
            </div>
            <div className="flex-1 min-w-0">
              <p className="font-mono text-2xs tracking-[0.16em] text-accent uppercase mb-0.5">
                Earn credits
              </p>
              <p className="text-sm text-fg">
                Invite a friend → +3 credits on signup, +5 on subscribe.
                {user.referral_credits_earned > 0 && (
                  <span className="font-medium ml-1">
                    You&apos;ve earned {user.referral_credits_earned} so far.
                  </span>
                )}
              </p>
            </div>
            <ArrowRight size={13} className="text-accent/50 shrink-0 group-hover:text-accent group-hover:translate-x-0.5 transition-all" />
          </div>
        </Link>
      )}

      {/* Platform roadmap */}
      <Card>
        <CardLabel className="mb-1">Platform roadmap</CardLabel>
        <p className="text-sm text-fg-dim mb-4">
          YouTube-first by design — deep intelligence on one platform beats surface-level coverage of many.
        </p>
        <div className="divide-y divide-border-1">
          <RoadmapRow platform="YouTube"    status="live"          description="Full comment analysis, channel intelligence, bulk scanning, coordination detection" />
          <RoadmapRow platform="X / Twitter" status="at 1,000 users" description="Thread analysis, account fingerprinting, bot-network detection" />
          <RoadmapRow platform="Reddit"     status="at 2,500 users" description="Subreddit coordination detection, post + comment analysis" />
          <RoadmapRow platform="TikTok"     status="at 5,000 users" description="Comment section analysis, creator audience intelligence" />
        </div>
      </Card>
    </div>
  );
}

function RoadmapRow({ platform, status, description }: { platform: string; status: string; description: string }) {
  const isLive = status === 'live';
  return (
    <div className={`flex items-start gap-3 py-3 first:pt-0 last:pb-0`}>
      <span className={`shrink-0 font-mono text-xs mt-0.5 ${isLive ? 'text-accent' : 'text-fg-faint'}`}>
        {isLive ? '✓' : '○'}
      </span>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap mb-0.5">
          <span className="text-sm font-medium text-fg">{platform}</span>
          <span className={cn(
            'font-mono text-2xs uppercase tracking-wider px-1.5 py-0.5 rounded-sm border',
            isLive ? 'text-accent border-accent/25 bg-accent/[0.08]' : 'text-fg-faint border-border-1',
          )}>
            {status}
          </span>
        </div>
        <p className="text-xs text-fg-dim">{description}</p>
      </div>
    </div>
  );
}

function StatCard({
  icon, label, value, sub, tone,
}: {
  icon: React.ReactNode;
  label: string;
  value: number;
  sub: string;
  tone?: 'accent' | 'danger';
}) {
  return (
    <div className="bg-bg-elev border border-border-1 rounded-lg p-4 shadow-inner-top">
      <div className="flex items-center justify-between mb-3">
        <span className="font-mono text-2xs tracking-[0.16em] text-fg-mute uppercase">{label}</span>
        <span className={cn(
          'w-6 h-6 rounded-sm flex items-center justify-center border',
          tone === 'danger'
            ? 'text-danger border-danger/25 bg-danger/[0.08]'
            : tone === 'accent'
              ? 'text-accent border-accent/25 bg-accent/[0.08]'
              : 'text-fg-mute border-border-2 bg-bg-elev-2',
        )}>
          {icon}
        </span>
      </div>
      <div className={cn(
        'font-mono text-2xl font-semibold tabular-nums mb-1',
        tone === 'danger' ? 'text-danger' : tone === 'accent' ? 'text-accent' : 'text-fg',
      )}>
        <AnimatedNumber value={value} />
      </div>
      <div className="text-xs text-fg-mute">{sub}</div>
    </div>
  );
}
