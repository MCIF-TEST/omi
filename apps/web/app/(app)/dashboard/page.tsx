import Link from 'next/link';
import { Search, Activity, Database, Zap, ArrowRight, CheckCircle2, Gift } from 'lucide-react';
import { Card, CardLabel, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { TierBadge } from '@/components/shared/tier-badge';
import { type EngineStatus, type InvestigationsListResponse, VERDICT_LABELS } from '@/lib/api';
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

      {/* Quick-links to key features */}
      <Card>
        <CardLabel className="mb-3">Explore capabilities</CardLabel>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-sm">
          <Link href="/search" className="flex items-center gap-3 p-3 rounded-sm border border-border-1 hover:border-border-hot hover:bg-bg-elev-2/50 transition-colors">
            <span className="font-mono text-2xs text-accent">SR</span>
            <span className="text-fg-dim">Account search — find any scanned account instantly</span>
          </Link>
          <Link href="/bulk" className="flex items-center gap-3 p-3 rounded-sm border border-border-1 hover:border-border-hot hover:bg-bg-elev-2/50 transition-colors">
            <span className="font-mono text-2xs text-accent">BK</span>
            <span className="text-fg-dim">Bulk scan — queue up to 20 URLs at once</span>
          </Link>
          <Link href="/narratives" className="flex items-center gap-3 p-3 rounded-sm border border-border-1 hover:border-border-hot hover:bg-bg-elev-2/50 transition-colors">
            <span className="font-mono text-2xs text-accent">NR</span>
            <span className="text-fg-dim">Narrative intelligence — trending talking points</span>
          </Link>
          <Link href="/graph" className="flex items-center gap-3 p-3 rounded-sm border border-border-1 hover:border-border-hot hover:bg-bg-elev-2/50 transition-colors">
            <span className="font-mono text-2xs text-accent">GR</span>
            <span className="text-fg-dim">Graph view — coordination network explorer</span>
          </Link>
          <Link href="/investigations" className="flex items-center gap-3 p-3 rounded-sm border border-border-1 hover:border-border-hot hover:bg-bg-elev-2/50 transition-colors">
            <span className="font-mono text-2xs text-accent">IV</span>
            <span className="text-fg-dim">Investigations — full archive with share/export</span>
          </Link>
          <Link href="/monitoring" className="flex items-center gap-3 p-3 rounded-sm border border-border-1 hover:border-border-hot hover:bg-bg-elev-2/50 transition-colors">
            <span className="font-mono text-2xs text-accent">MN</span>
            <span className="text-fg-dim">Monitoring — watchlists and anomaly alerts</span>
          </Link>
        </div>
      </Card>

      {/* Referral nudge */}
      {user?.referral_code && (
        <Link
          href="/settings"
          className="block group"
        >
          <div className="flex items-center gap-4 p-4 rounded-md border border-accent/30 bg-accent/5 hover:border-accent hover:bg-accent/10 transition-colors">
            <div className="shrink-0 w-10 h-10 rounded-sm border border-accent/40 bg-bg flex items-center justify-center text-accent">
              <Gift size={18} />
            </div>
            <div className="flex-1 min-w-0">
              <p className="font-mono text-2xs tracking-[0.18em] text-accent uppercase mb-0.5">
                Earn credits
              </p>
              <p className="text-sm text-fg">
                Invite a friend → +3 credits when they sign up, +5 more when they subscribe.
                {user.referral_credits_earned > 0 && (
                  <span className="font-medium ml-1">
                    You&apos;ve earned {user.referral_credits_earned} so far.
                  </span>
                )}
              </p>
            </div>
            <ArrowRight size={16} className="text-accent shrink-0 group-hover:translate-x-1 transition-transform" />
          </div>
        </Link>
      )}

      {/* Platform roadmap */}
      <Card>
        <CardLabel className="mb-1">Platform roadmap</CardLabel>
        <p className="text-sm text-fg-dim mb-4">
          OMISPHERE is YouTube-first by design — deep intelligence on one platform beats
          surface-level coverage of many. As our community grows, we unlock new platforms.
          Share OMISPHERE with a colleague to help hit the next milestone.
        </p>
        <div className="space-y-2">
          <RoadmapRow
            platform="YouTube"
            status="live"
            description="Full comment analysis, channel intelligence, bulk scanning, coordination detection"
          />
          <RoadmapRow
            platform="X / Twitter"
            status="at 1,000 users"
            description="Thread analysis, account fingerprinting, bot-network detection"
          />
          <RoadmapRow
            platform="Reddit"
            status="at 2,500 users"
            description="Subreddit coordination detection, post + comment analysis"
          />
          <RoadmapRow
            platform="TikTok"
            status="at 5,000 users"
            description="Comment section analysis, creator audience intelligence"
          />
        </div>
      </Card>
    </div>
  );
}

function RoadmapRow({
  platform,
  status,
  description,
}: {
  platform: string;
  status: string;
  description: string;
}) {
  const isLive = status === 'live';
  return (
    <div
      className={`flex items-start gap-3 p-3 rounded-sm border transition-colors ${
        isLive ? 'border-accent/30 bg-accent/5' : 'border-border-1'
      }`}
    >
      <span
        className={`shrink-0 font-mono text-sm mt-0.5 ${isLive ? 'text-accent' : 'text-fg-mute'}`}
      >
        {isLive ? '✓' : '○'}
      </span>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-sm font-medium text-fg">{platform}</span>
          <span
            className={`font-mono text-2xs uppercase tracking-wider px-1.5 py-0.5 rounded-sm border ${
              isLive
                ? 'text-accent border-accent/30 bg-accent/10'
                : 'text-fg-mute border-border-2'
            }`}
          >
            {status}
          </span>
        </div>
        <p className="text-xs text-fg-dim mt-0.5">{description}</p>
      </div>
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

