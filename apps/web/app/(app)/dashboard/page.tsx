import Link from 'next/link';
import {
  Search, Activity, Database, Zap, ArrowRight, CheckCircle2, Gift,
  Network, MessageSquareText, FileSearch, Radio, LayoutGrid,
  Megaphone, ShieldCheck, AlertTriangle, ExternalLink,
} from 'lucide-react';
import { Card, CardLabel } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { TierBadge } from '@/components/shared/tier-badge';
import {
  type EngineStatus, type InvestigationsListResponse, type FeaturedCampaignsResponse,
  type FeaturedCampaign, type WtpPromptStatus, isCorroborated, VERDICT_LABELS,
} from '@/lib/api';
import { WtpPrompt } from './wtp-prompt';
import { apiServer } from '@/lib/api-server';
import { getCurrentUser } from '@/lib/auth';
import { timeAgo } from '@/lib/format';
import { cn } from '@/lib/cn';
import { AnimatedNumber } from '@/components/shared/animated-number';

export const metadata = { title: 'Dashboard — OMISPHERE' };

export default async function DashboardPage() {
  const [user, status, invList, featured, wtp] = await Promise.all([
    getCurrentUser(),
    apiServer<EngineStatus>('/v1/status').catch(() => null),
    apiServer<InvestigationsListResponse>('/v1/investigations?limit=10').catch(
      () => ({ investigations: [] } as InvestigationsListResponse),
    ),
    apiServer<FeaturedCampaignsResponse>('/v1/campaigns/featured').catch(
      () => ({ campaigns: [] } as FeaturedCampaignsResponse),
    ),
    apiServer<WtpPromptStatus>('/v1/learning/prompt').catch(
      () => ({ show_wtp: false } as WtpPromptStatus),
    ),
  ]);
  const investigations = invList.investigations || [];
  const featuredCampaigns = featured.campaigns || [];

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

      {/* Founder-learning Q5: one willingness-to-pay question, returners only,
          server-gated to show exactly once ever. */}
      {wtp.show_wtp && <WtpPrompt />}

      {/* First-run value — a REAL disclosed campaign to explore immediately */}
      {featuredCampaigns.length > 0 && (
        <FeaturedSection campaigns={featuredCampaigns} isNew={investigations.length === 0} />
      )}

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
          sub="completed to date"
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
            <h3 className="text-base font-semibold text-fg mb-2">No investigations yet</h3>
            <p className="text-sm text-fg-dim mb-5">
              Scan a YouTube video / channel or an X account to start your own
              investigation — or explore one of the real disclosed campaigns above
              first to see how Omi reads coordination.
            </p>
            <div className="flex flex-wrap gap-2">
              <Link href="/investigate">
                <Button>
                  <Search size={13} /> Run your first scan
                </Button>
              </Link>
              <Link href="/campaigns">
                <Button variant="secondary">
                  <Megaphone size={13} /> Browse campaigns
                </Button>
              </Link>
            </div>
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

      {/* Platform roadmap deliberately removed from the dashboard (it lives on
          /about): "what's coming" is the wrong message before a user has
          experienced what's here. */}
    </div>
  );
}

function FeaturedSection({ campaigns, isNew }: { campaigns: FeaturedCampaign[]; isNew: boolean }) {
  return (
    <section className="border border-accent/25 bg-accent/[0.04] rounded-lg p-5 md:p-6">
      <div className="flex items-start gap-2 mb-1.5">
        <Megaphone size={15} className="text-accent mt-0.5 shrink-0" />
        <div>
          <p className="font-mono text-2xs tracking-[0.18em] text-accent uppercase">
            {isNew ? 'Start here · see a real campaign' : 'Featured campaigns'}
          </p>
          <h2 className="text-lg font-semibold text-fg tracking-tight mt-0.5">
            Real, disclosed influence operations Omi detects
          </h2>
        </div>
      </div>
      <p className="text-sm text-fg-dim max-w-2xl mb-4">
        These are genuine state-actor networks from the platform&apos;s own transparency
        disclosures. Omi re-derives the coordination from <span className="text-fg">behaviour
        alone</span> — shared fingerprints, hashtag/amplification networks, account-age cohorts —
        not from the label. This is the difference from a bot detector: it scores the{' '}
        <span className="text-fg">group acting together</span>, with evidence for and against,
        and never overclaims. Open one to see how.
      </p>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
        {campaigns.map((c) => (
          <FeaturedCard key={c.campaign_key} c={c} />
        ))}
      </div>
    </section>
  );
}

function FeaturedCard({ c }: { c: FeaturedCampaign }) {
  const scorePct = Math.round(c.max_coordination_score * 100);
  const confPct = Math.round(c.confidence * 100);
  const corroborated = isCorroborated(c.methods);
  return (
    <div className="bg-bg-elev border border-border-1 rounded-md p-4 flex flex-col">
      <div className="flex items-center justify-between gap-2 mb-2 flex-wrap">
        <span className="text-sm font-semibold text-fg">{c.name}</span>
        <span
          title={corroborated
            ? 'Corroborated: a discriminative detector or ≥2 independent methods agree.'
            : 'Supporting evidence only — capped at MODERATE under the corroboration gate.'}
          className={cn(
            'inline-flex items-center gap-1 font-mono text-2xs uppercase tracking-wider px-1.5 py-0.5 rounded-sm border',
            corroborated
              ? 'text-accent border-accent/40 bg-accent/10'
              : 'text-tier-moderate border-tier-moderate/40 bg-tier-moderate/10',
          )}
        >
          {corroborated ? <ShieldCheck size={10} /> : <AlertTriangle size={10} />}
          {corroborated ? 'corroborated' : 'supporting only'}
        </span>
      </div>
      {c.blurb && <p className="text-xs text-fg-dim leading-relaxed mb-3">{c.blurb}</p>}
      <div className="grid grid-cols-3 gap-2 mb-3 mt-auto">
        <MiniMetric label="Coordination" value={`${scorePct}%`} tone="accent" />
        <MiniMetric label="Confidence" value={`${confPct}%`} />
        <MiniMetric label="Accounts" value={c.member_count} />
      </div>
      <div className="flex flex-wrap gap-1 mb-3">
        {c.methods.slice(0, 4).map((m) => (
          <span key={m} className="font-mono text-[0.55rem] uppercase tracking-wider px-1.5 py-0.5 rounded-sm border border-border-2 text-fg-mute">
            {m.replace(/_/g, ' ')}
          </span>
        ))}
      </div>
      <div className="flex flex-wrap gap-2">
        <Link
          // ?ref=featured: the activation marker (Phase-4 telemetry attributes
          // featured-driven value moments through it; harmless until then).
          href={`/campaigns/${c.campaign_key}?ref=featured`}
          className="inline-flex items-center gap-1.5 px-3 h-8 border border-accent-dim bg-accent/10 text-accent rounded-sm font-mono text-2xs tracking-wider uppercase hover:bg-accent/20"
        >
          Explore campaign <ArrowRight size={11} />
        </Link>
        {c.share_token && (
          <a
            href={`/rc/${c.share_token}`}
            target="_blank"
            rel="noopener"
            className="inline-flex items-center gap-1.5 px-3 h-8 border border-border-2 text-fg-dim rounded-sm font-mono text-2xs tracking-wider uppercase hover:text-fg hover:border-border-hot"
          >
            <ExternalLink size={11} /> Public report
          </a>
        )}
      </div>
    </div>
  );
}

function MiniMetric({ label, value, tone }: { label: string; value: string | number; tone?: 'accent' }) {
  return (
    <div className="bg-bg/40 border border-border-1/60 rounded-sm px-2 py-1.5">
      <div className="font-mono text-[0.55rem] uppercase tracking-wider text-fg-faint">{label}</div>
      <div className={cn('mt-0.5 text-sm font-semibold tabular-nums', tone === 'accent' ? 'text-accent' : 'text-fg')}>
        {value}
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
