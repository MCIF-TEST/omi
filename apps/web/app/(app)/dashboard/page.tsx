import Link from 'next/link';
import {
  Search, Activity, Database, Zap, ArrowRight, CheckCircle2, Gift,
  Network, MessageSquareText, FileSearch, Radio, LayoutGrid,
  Megaphone, ShieldCheck, AlertTriangle, ExternalLink,
} from 'lucide-react';
import { Card, CardLabel } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { TierBadge } from '@/components/shared/tier-badge';
import { TRIAL_CREDITS } from '@/lib/plan';
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

// Persistent cluster hue from a campaign key — navigate by colour, not just label.
function clusterIndex(key: string): number {
  let h = 0;
  for (let i = 0; i < key.length; i++) h = (h * 31 + key.charCodeAt(i)) >>> 0;
  return (h % 8) + 1;
}

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
    <div className="space-y-8 animate-fade-up">

      {/* Command header — aurora-lit intelligence workspace */}
      <header className="aurora relative overflow-hidden rounded-2xl border border-border-1 bg-bg-elev px-6 py-7 md:px-8 md:py-8">
        <span className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-accent/50 to-transparent" />
        <div className="flex items-end justify-between gap-4 flex-wrap">
          <div className="min-w-0">
            <span className="section-label">OmiSphere · Intelligence workspace</span>
            <h1 className="display text-2xl md:text-[1.7rem] font-semibold text-fg tracking-tight mt-3">
              Operations overview
            </h1>
            <p className="text-sm text-fg-mute mt-1.5 font-mono truncate">{user?.email}</p>
          </div>
          <Link href="/investigate" className="shrink-0">
            <Button size="lg" className="btn-glow">
              <Search size={15} />
              New investigation
            </Button>
          </Link>
        </div>
      </header>

      {/* Founder-learning Q5: one willingness-to-pay question, returners only. */}
      {wtp.show_wtp && <WtpPrompt />}

      {/* First-run value — a REAL disclosed campaign to explore immediately */}
      {featuredCampaigns.length > 0 && (
        <FeaturedSection campaigns={featuredCampaigns} isNew={investigations.length === 0} />
      )}

      {/* Telemetry */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 stagger">
        <StatCard
          icon={<Zap size={14} />}
          label="Credits"
          value={user?.credits_remaining ?? 0}
          sub={user?.subscription_status === 'active' ? 'subscription active' : `${TRIAL_CREDITS} free trial credits`}
          tone={user && user.credits_remaining === 0 ? 'danger' : 'accent'}
        />
        <StatCard
          icon={<Database size={14} />}
          label="Fingerprints"
          value={status?.fingerprints_stored ?? 0}
          sub="behavioral profiles stored"
        />
        <StatCard
          icon={<Activity size={14} />}
          label="Total scans"
          value={status?.total_scans ?? 0}
          sub="completed to date"
        />
        <StatCard
          icon={<Network size={14} />}
          label="Coord. edges"
          value={status?.total_engagement_edges ?? 0}
          sub="cross-account links"
        />
      </div>

      {/* Recent investigations */}
      <Card className="p-0 overflow-hidden">
        <div className="flex items-center justify-between gap-2 px-5 py-4 border-b border-border-1">
          <CardLabel className="m-0">Recent investigations</CardLabel>
          <Link
            href="/investigate"
            className="font-mono text-2xs tracking-wider text-accent hover:text-accent-2 uppercase transition-colors"
          >
            + New scan
          </Link>
        </div>

        {investigations.length === 0 ? (
          <div className="px-6 py-10 text-center max-w-md mx-auto">
            <div className="w-12 h-12 mx-auto mb-4 rounded-xl border border-border-2 bg-bg-elev-2 flex items-center justify-center text-accent">
              <FileSearch size={20} strokeWidth={1.5} />
            </div>
            <h3 className="display text-base font-semibold text-fg mb-1.5">No investigations yet</h3>
            <p className="text-sm text-fg-dim mb-5 leading-relaxed">
              Scan a YouTube video / channel or an X account to begin — or open one of the
              real disclosed campaigns above to see how Omi reads coordination.
            </p>
            <div className="flex flex-wrap gap-2 justify-center">
              <Link href="/investigate">
                <Button><Search size={13} /> Run your first scan</Button>
              </Link>
              <Link href="/campaigns">
                <Button variant="secondary"><Megaphone size={13} /> Browse campaigns</Button>
              </Link>
            </div>
          </div>
        ) : (
          <ul className="divide-y divide-border-1">
            {investigations.map((inv) => (
              <li key={inv.slug}>
                <Link
                  href={`/investigations/${inv.slug}`}
                  className="group flex items-center gap-4 py-3 px-5 hover:bg-bg-elev-2/60 transition-colors"
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
                      <span className="text-fg-dim tabular">{Math.round(inv.overall_probability * 100)}%</span>
                      <span className="text-border-2">·</span>
                      <span>{inv.batch_count} batch{inv.batch_count === 1 ? '' : 'es'}</span>
                    </div>
                  </div>
                  <ArrowRight size={13} className="text-fg-faint shrink-0 group-hover:text-accent group-hover:translate-x-0.5 transition-all" />
                </Link>
              </li>
            ))}
          </ul>
        )}
      </Card>

      {/* Explore capabilities */}
      <div>
        <CardLabel className="mb-3">Explore capabilities</CardLabel>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2.5">
          {[
            { href: '/search',         icon: Search,            label: 'Account search',   desc: 'Find any scanned account instantly' },
            { href: '/bulk',           icon: LayoutGrid,        label: 'Bulk scan',        desc: 'Queue up to 20 URLs at once' },
            { href: '/narratives',     icon: MessageSquareText, label: 'Narrative intel',  desc: 'How talking points spread' },
            { href: '/graph',          icon: Network,           label: 'Graph view',       desc: 'Coordination network explorer' },
            { href: '/investigations', icon: FileSearch,        label: 'Investigations',   desc: 'Full archive with share & export' },
            { href: '/monitoring',     icon: Radio,             label: 'Monitoring',       desc: 'Watchlists and anomaly alerts' },
          ].map(({ href, icon: Icon, label, desc }) => (
            <Link
              key={href}
              href={href}
              className="group flex items-center gap-3 p-3.5 rounded-xl border border-border-1 bg-bg-elev/40 card-interactive"
            >
              <span className="shrink-0 w-9 h-9 rounded-lg bg-bg-elev-2 border border-border-2 flex items-center justify-center text-fg-mute group-hover:text-accent group-hover:border-accent/40 transition-colors">
                <Icon size={15} strokeWidth={1.6} />
              </span>
              <div className="min-w-0">
                <div className="text-sm text-fg font-medium">{label}</div>
                <div className="text-xs text-fg-dim truncate">{desc}</div>
              </div>
              <ArrowRight size={13} className="ml-auto text-fg-faint shrink-0 group-hover:text-fg-mute group-hover:translate-x-0.5 transition-all" />
            </Link>
          ))}
        </div>
      </div>

      {/* Referral nudge */}
      {user?.referral_code && (
        <Link href="/settings" className="block group">
          <div className="aurora relative overflow-hidden flex items-center gap-4 p-4 rounded-xl border border-border-1 bg-bg-elev hover:border-border-hot transition-colors">
            <div className="shrink-0 w-10 h-10 rounded-lg border border-violet/30 bg-violet/[0.08] flex items-center justify-center text-violet-2">
              <Gift size={16} />
            </div>
            <div className="flex-1 min-w-0">
              <p className="font-mono text-2xs tracking-[0.16em] text-violet-2 uppercase mb-0.5">
                Earn credits
              </p>
              <p className="text-sm text-fg-dim">
                Invite a friend → <span className="text-fg">+3 credits</span> on signup,
                <span className="text-fg"> +5</span> on subscribe.
                {user.referral_credits_earned > 0 && (
                  <span className="text-fg font-medium ml-1">
                    You&apos;ve earned {user.referral_credits_earned} so far.
                  </span>
                )}
              </p>
            </div>
            <ArrowRight size={14} className="text-fg-faint shrink-0 group-hover:text-violet-2 group-hover:translate-x-0.5 transition-all" />
          </div>
        </Link>
      )}
    </div>
  );
}

function FeaturedSection({ campaigns, isNew }: { campaigns: FeaturedCampaign[]; isNew: boolean }) {
  return (
    <section className="aurora relative overflow-hidden gradient-border p-5 md:p-6">
      <div className="flex items-start gap-3 mb-2">
        <span className="shrink-0 mt-0.5 w-8 h-8 rounded-lg border border-accent/30 bg-accent/[0.08] flex items-center justify-center text-accent">
          <Megaphone size={15} />
        </span>
        <div>
          <p className="section-label">
            {isNew ? 'Start here · see a real campaign' : 'Featured campaigns'}
          </p>
          <h2 className="display text-lg font-semibold text-fg tracking-tight mt-1.5">
            Real, disclosed influence operations Omi detects
          </h2>
        </div>
      </div>
      <p className="text-sm text-fg-dim max-w-2xl mb-4 leading-relaxed">
        Genuine state-actor networks from the platform&apos;s own transparency disclosures.
        Omi re-derives the coordination from <span className="text-fg">behaviour alone</span> —
        shared fingerprints, hashtag/amplification networks, account-age cohorts — not from the
        label. It scores the <span className="text-fg">group acting together</span>, with
        evidence for and against. Open one to see how.
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
  const cluster = clusterIndex(c.campaign_key);
  return (
    <div className="group bg-bg-elev border border-border-1 rounded-xl p-4 flex flex-col card-interactive">
      <div className="flex items-center justify-between gap-2 mb-2 flex-wrap">
        <span className="flex items-center gap-2 min-w-0">
          <span className="cluster-dot" style={{ ['--c' as string]: `var(--cluster-${cluster})` }} />
          <span className="text-sm font-semibold text-fg truncate">{c.name}</span>
        </span>
        <span
          title={corroborated
            ? 'Corroborated: a discriminative detector or ≥2 independent methods agree.'
            : 'Supporting evidence only — capped at MODERATE under the corroboration gate.'}
          className={cn(
            'inline-flex items-center gap-1 font-mono text-2xs uppercase tracking-wider px-1.5 py-0.5 rounded-full border',
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
          <span key={m} className="font-mono text-[0.55rem] uppercase tracking-wider px-1.5 py-0.5 rounded-full border border-border-2 text-fg-mute">
            {m.replace(/_/g, ' ')}
          </span>
        ))}
      </div>
      <div className="flex flex-wrap gap-2">
        <Link
          href={`/campaigns/${c.campaign_key}?ref=featured`}
          className="inline-flex items-center gap-1.5 px-3 h-8 border border-accent-dim bg-accent/10 text-accent rounded-md font-mono text-2xs tracking-wider uppercase hover:bg-accent/20 transition-colors"
        >
          Explore campaign <ArrowRight size={11} />
        </Link>
        {c.share_token && (
          <a
            href={`/rc/${c.share_token}`}
            target="_blank"
            rel="noopener"
            className="inline-flex items-center gap-1.5 px-3 h-8 border border-border-2 text-fg-dim rounded-md font-mono text-2xs tracking-wider uppercase hover:text-fg hover:border-border-hot transition-colors"
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
    <div className="surface-inset px-2.5 py-2">
      <div className="font-mono text-[0.55rem] uppercase tracking-wider text-fg-faint">{label}</div>
      <div className={cn('stat-value mt-1 text-base font-semibold', tone === 'accent' ? 'text-accent' : 'text-fg')}>
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
    <div className="group relative overflow-hidden rounded-xl border border-border-1 bg-bg-elev p-4 card-interactive">
      <div className="flex items-center justify-between mb-3">
        <span className="font-mono text-2xs tracking-[0.16em] text-fg-mute uppercase">{label}</span>
        <span className={cn(
          'w-7 h-7 rounded-lg flex items-center justify-center border transition-colors',
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
        'stat-value text-[1.9rem] font-semibold',
        tone === 'danger' ? 'text-danger' : tone === 'accent' ? 'text-accent' : 'text-fg',
      )}>
        <AnimatedNumber value={value} />
      </div>
      <div className="text-xs text-fg-mute mt-1.5">{sub}</div>
    </div>
  );
}
