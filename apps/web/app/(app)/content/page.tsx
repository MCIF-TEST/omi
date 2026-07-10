import Link from 'next/link';
import {
  Database, ArrowRight, Shield, AlertTriangle, ShieldAlert, Flame,
  Users, Layers, MessageCircle, Network, Search as SearchIcon,
} from 'lucide-react';
import { Card, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { type ContentEntityListResponse, type ContentEntitySummary } from '@/lib/api';
import { apiServer } from '@/lib/api-server';
import { timeAgo } from '@/lib/format';

export const metadata = { title: 'Content database — OMISPHERE' };
export const dynamic = 'force-dynamic';

const PLATFORM_FILTERS = [
  { value: '', label: 'All' },
  { value: 'youtube', label: 'YouTube' },
] as const;

const RISK_FILTERS = [
  { value: 'low', label: 'All' },
  { value: 'moderate', label: 'Moderate+' },
  { value: 'high', label: 'High+' },
  { value: 'extreme', label: 'Extreme only' },
] as const;

const RISK_CONFIG: Record<string, { label: string; icon: React.ReactNode; cls: string }> = {
  extreme:  { label: 'Extreme',  icon: <Flame size={10} />,        cls: 'text-tier-high border-tier-high/40 bg-tier-high/10' },
  high:     { label: 'High',     icon: <ShieldAlert size={10} />,  cls: 'text-tier-elevated border-tier-elevated/40 bg-tier-elevated/10' },
  elevated: { label: 'High',     icon: <ShieldAlert size={10} />,  cls: 'text-tier-elevated border-tier-elevated/40 bg-tier-elevated/10' },
  moderate: { label: 'Moderate', icon: <AlertTriangle size={10} />,cls: 'text-tier-moderate border-tier-moderate/40 bg-tier-moderate/10' },
  low:      { label: 'Low',      icon: <Shield size={10} />,       cls: 'text-tier-low border-tier-low/40 bg-tier-low/10' },
};

const CHIP = 'font-mono text-2xs tracking-wider uppercase px-2.5 py-1.5 rounded-full border transition-colors';
const CHIP_ON = 'border-transparent bg-accent/15 text-accent shadow-[inset_0_0_0_1px_rgba(217,164,74,0.4)]';
const CHIP_OFF = 'border-border-2 text-fg-dim hover:text-fg hover:border-border-hot';

export default async function ContentPage({
  searchParams,
}: {
  searchParams: { platform?: string; min?: string; q?: string };
}) {
  const platform = searchParams.platform || '';
  const min_risk_tier = (['low', 'moderate', 'high', 'extreme'].includes(searchParams.min || '')
    ? searchParams.min : 'low') as string;
  const query = (searchParams.q || '').trim();

  let data: ContentEntityListResponse = { total: 0, platform: null, entities: [] };
  let loadError = false;
  try {
    const params = new URLSearchParams({ min_risk_tier, limit: '40' });
    if (platform) params.set('platform', platform);
    if (query) params.set('q', query);
    data = await apiServer<ContentEntityListResponse>(`/v1/content?${params}`);
  } catch {
    loadError = true;
  }

  const entities = data.entities;

  return (
    <div className="space-y-6 animate-fade-up">
      <header className="aurora relative overflow-hidden rounded-2xl border border-border-1 bg-bg-elev px-6 py-6 md:px-7">
        <span className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-accent/50 to-transparent" />
        <span className="section-label">Sources · Content database</span>
        <h1 className="display text-2xl font-semibold text-fg tracking-tight mt-3">
          What has been scanned
        </h1>
        <p className="mt-1.5 text-sm text-fg-dim max-w-2xl leading-relaxed">
          Every scanned video persists here. Multiple users scanning the same content merge into a
          single intelligence record — the more scans, the smarter the engine gets.
        </p>
      </header>

      {/* Search */}
      <form action="/content" method="GET" className="flex items-center gap-2">
        {platform && <input type="hidden" name="platform" value={platform} />}
        <input type="hidden" name="min" value={min_risk_tier} />
        <div className="relative flex-1 max-w-md">
          <SearchIcon size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-fg-mute pointer-events-none" />
          <input
            aria-label="Search content"
            type="search"
            name="q"
            defaultValue={query}
            placeholder="Search titles, IDs, channels…"
            className="w-full pl-9 pr-3 h-10 bg-bg-elev-2 border border-border-2 rounded-md text-sm text-fg placeholder:text-fg-mute focus:outline-none focus:border-accent focus:ring-2 focus:ring-accent/25 transition-colors"
            autoComplete="off"
          />
        </div>
        {query && (
          <Link href={`/content?platform=${platform}&min=${min_risk_tier}`} className={`${CHIP} ${CHIP_OFF}`}>
            Clear
          </Link>
        )}
      </form>

      {/* Filters */}
      <div className="flex flex-wrap gap-x-6 gap-y-3">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="font-mono text-2xs tracking-[0.18em] text-fg-mute uppercase">Platform</span>
          {PLATFORM_FILTERS.map((f) => (
            <Link key={f.value} href={buildHref({ platform: f.value, min: min_risk_tier, q: query })}
              className={`${CHIP} ${f.value === platform ? CHIP_ON : CHIP_OFF}`}>
              {f.label}
            </Link>
          ))}
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <span className="font-mono text-2xs tracking-[0.18em] text-fg-mute uppercase">Min risk</span>
          {RISK_FILTERS.map((f) => (
            <Link key={f.value} href={buildHref({ platform, min: f.value, q: query })}
              className={`${CHIP} ${f.value === min_risk_tier ? CHIP_ON : CHIP_OFF}`}>
              {f.label}
            </Link>
          ))}
        </div>
      </div>

      {query && (
        <p className="font-mono text-2xs text-fg-mute">
          Searching for <span className="text-accent">&ldquo;{query}&rdquo;</span> ·{' '}
          {data.total} result{data.total !== 1 ? 's' : ''}
        </p>
      )}

      {/* Stats */}
      {entities.length > 0 && (
        <div className="grid grid-cols-3 gap-3">
          <StatTile label="Tracked" value={data.total} icon={<Database size={13} />} />
          <StatTile label="Total comments" value={entities.reduce((s, e) => s + e.total_comments_collected, 0).toLocaleString()} icon={<MessageCircle size={13} />} />
          <StatTile label="Unique authors" value={entities.reduce((s, e) => s + e.total_distinct_authors, 0).toLocaleString()} icon={<Users size={13} />} />
        </div>
      )}

      {loadError ? (
        <Card className="text-center py-12">
          <div className="w-12 h-12 mx-auto mb-4 rounded-xl border border-tier-elevated/30 bg-tier-elevated/[0.08] flex items-center justify-center text-tier-elevated">
            <AlertTriangle size={20} strokeWidth={1.5} />
          </div>
          <CardTitle className="mb-1.5">Couldn&apos;t load the content database</CardTitle>
          <p className="text-sm text-fg-dim max-w-xl mx-auto mb-5 leading-relaxed">
            The request to the content service failed — a connection or server error, not an empty
            database. Your scanned content is safe. Try again in a moment.
          </p>
          <Link href={buildHref({ platform, min: min_risk_tier, q: query })}>
            <Button variant="secondary">Retry</Button>
          </Link>
        </Card>
      ) : entities.length === 0 ? (
        <Card className="text-center py-12">
          <div className="w-12 h-12 mx-auto mb-4 rounded-xl border border-border-2 bg-bg-elev-2 flex items-center justify-center text-accent">
            <Database size={20} strokeWidth={1.5} />
          </div>
          <CardTitle className="mb-1.5">
            {query ? `Nothing matched "${query}"` : 'No content has been scanned yet'}
          </CardTitle>
          {query ? (
            <p className="text-sm text-fg-dim max-w-lg mx-auto">
              Try a broader query, or <Link href="/content" className="text-accent hover:text-accent-2">clear the search</Link>.
            </p>
          ) : (
            <>
              <p className="text-sm text-fg-dim max-w-xl mx-auto mb-5 leading-relaxed">
                This database starts empty by design — no demo accounts to muddle real findings.
                Run your first scan to populate it; rescanning later layers in fresh batches so you
                can watch coordination evolve.
              </p>
              <Link href="/investigate">
                <Button><SearchIcon size={13} /> Start your first scan</Button>
              </Link>
            </>
          )}
        </Card>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
          {entities.map((e) => <ContentEntityCard key={e.id} entity={e} />)}
        </div>
      )}
    </div>
  );
}

function buildHref({ platform, min, q }: { platform: string; min: string; q: string }) {
  const params = new URLSearchParams();
  if (platform) params.set('platform', platform);
  if (min) params.set('min', min);
  if (q) params.set('q', q);
  const qs = params.toString();
  return qs ? `/content?${qs}` : '/content';
}

function ContentEntityCard({ entity: e }: { entity: ContentEntitySummary }) {
  const risk = RISK_CONFIG[e.latest_risk_tier] ?? RISK_CONFIG.low;
  const coord_pct = Math.round(e.latest_coordination_score * 100);

  return (
    <Link href={`/content/${e.platform}/${e.content_id}`} className="block group">
      <article className="h-full bg-bg-elev border border-border-1 rounded-xl p-5 card-interactive">
        <div className="flex items-start gap-3 mb-4">
          {e.thumbnail_url && (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={e.thumbnail_url} alt="" className="w-16 h-10 object-cover rounded-md shrink-0 border border-border-1" />
          )}
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-1.5 flex-wrap">
              <span className="font-mono text-2xs tracking-wider uppercase px-1.5 py-0.5 rounded-full border border-border-2 text-fg-mute">
                {e.platform}
              </span>
              <span className={`inline-flex items-center gap-1 font-mono text-2xs tracking-wider uppercase px-1.5 py-0.5 rounded-full border ${risk.cls}`}>
                {risk.icon}
                {risk.label}
              </span>
              {e.reply_pod_count > 0 && (
                <span className="inline-flex items-center gap-1 font-mono text-2xs tracking-wider uppercase px-1.5 py-0.5 rounded-full border border-accent/40 text-accent bg-accent/5">
                  <Network size={9} />
                  {e.reply_pod_count} pod{e.reply_pod_count !== 1 ? 's' : ''}
                </span>
              )}
            </div>
            <p className="text-sm text-fg font-medium leading-tight line-clamp-1">{e.title || e.content_id}</p>
            {e.author_handle && e.author_external_id && (
              <Link
                href={`/channels/${e.platform}/${encodeURIComponent(e.author_external_id)}`}
                className="text-2xs text-fg-mute hover:text-accent transition-colors mt-0.5 inline-block"
              >
                @{e.author_handle}
              </Link>
            )}
          </div>
          <span className="font-mono text-2xs text-fg-mute shrink-0">{timeAgo(e.last_scanned_at)}</span>
        </div>

        {/* Coordination bar */}
        <div className="mb-4">
          <div className="flex items-center justify-between font-mono text-2xs mb-1.5">
            <span className="text-fg-mute uppercase tracking-wider">Coordination</span>
            <span className="text-fg tabular">{coord_pct}%</span>
          </div>
          <div className="h-1.5 bg-bg-elev-3 rounded-full overflow-hidden">
            <div className="h-full rounded-full bg-accent transition-all" style={{ width: `${Math.min(100, coord_pct)}%` }} />
          </div>
        </div>

        {/* Stats */}
        <div className="grid grid-cols-4 gap-2 mb-3">
          <MiniStat label="Batches" value={e.total_batches} icon={<Layers size={9} />} />
          <MiniStat label="Comments" value={e.total_comments_collected.toLocaleString()} icon={<MessageCircle size={9} />} />
          <MiniStat label="Authors" value={e.total_distinct_authors.toLocaleString()} icon={<Users size={9} />} />
          <MiniStat label="Scanners" value={e.contributor_count} />
        </div>

        <div className="flex items-center justify-between font-mono text-2xs pt-1">
          <span className="text-fg-mute uppercase tracking-wider truncate">{e.kind} · {e.content_id}</span>
          <ArrowRight size={13} className="text-fg-faint group-hover:text-accent group-hover:translate-x-0.5 transition-all shrink-0" />
        </div>
      </article>
    </Link>
  );
}

function StatTile({ label, value, icon }: { label: string; value: string | number; icon?: React.ReactNode }) {
  return (
    <div className="bg-bg-elev border border-border-1 rounded-xl p-4 card-interactive">
      <div className="flex items-center gap-1.5 font-mono text-2xs text-fg-mute uppercase tracking-wider mb-1.5">
        {icon}{label}
      </div>
      <div className="stat-value text-xl font-semibold text-fg">{value}</div>
    </div>
  );
}

function MiniStat({ label, value, icon }: { label: string; value: string | number; icon?: React.ReactNode }) {
  return (
    <div className="surface-inset px-2 py-1.5">
      <div className="flex items-center gap-0.5 font-mono text-[0.55rem] text-fg-faint uppercase tracking-wider mb-0.5">
        {icon}{label}
      </div>
      <div className="text-sm font-medium tabular text-fg">{value}</div>
    </div>
  );
}
